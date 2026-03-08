from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from wargames.engine.strategy import (
    extract_strategies,
    get_top_strategies,
    save_strategies,
    update_win_rates,
)
from wargames.models import (
    AttackResult,
    DefenseResult,
    DraftPick,
    MatchOutcome,
    Phase,
    RoundResult,
    Severity,
    Strategy,
)
from wargames.output.db import Database


def _make_round_result(round_number: int = 1, red_debrief: str = "", blue_debrief: str = "") -> RoundResult:
    return RoundResult(
        round_number=round_number,
        phase=Phase.PROMPT_INJECTION,
        outcome=MatchOutcome.RED_WIN,
        red_score=10,
        blue_threshold=10,
        red_draft=[],
        blue_draft=[],
        attacks=[],
        defenses=[],
        red_debrief=red_debrief,
        blue_debrief=blue_debrief,
    )


@pytest.mark.asyncio
async def test_extract_strategies():
    """Mock LLM returns JSON array; verify Strategy objects created with correct fields."""
    extracted = [
        {"strategy_type": "attack", "content": "Use prompt injection to bypass guardrails"},
        {"strategy_type": "defense", "content": "Rate-limit repeated injection attempts"},
    ]
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = json.dumps(extracted)

    result = _make_round_result(
        round_number=3,
        red_debrief="We used prompt injection techniques successfully.",
    )

    strategies = await extract_strategies(result, team="red", llm=mock_llm)

    assert len(strategies) == 2

    attack_strat = next(s for s in strategies if s.strategy_type == "attack")
    assert attack_strat.team == "red"
    assert attack_strat.phase == Phase.PROMPT_INJECTION.value
    assert attack_strat.content == "Use prompt injection to bypass guardrails"
    assert attack_strat.created_round == 3
    assert attack_strat.win_rate == 0.0
    assert attack_strat.usage_count == 0

    defense_strat = next(s for s in strategies if s.strategy_type == "defense")
    assert defense_strat.strategy_type == "defense"


@pytest.mark.asyncio
async def test_extract_strategies_empty_debrief():
    """Empty debrief returns empty list without calling LLM."""
    mock_llm = AsyncMock()
    result = _make_round_result(red_debrief="")

    strategies = await extract_strategies(result, team="red", llm=mock_llm)

    assert strategies == []
    mock_llm.chat.assert_not_called()


@pytest.mark.asyncio
async def test_extract_strategies_invalid_json():
    """LLM returning non-JSON results in empty list."""
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = "This is not JSON at all."

    result = _make_round_result(red_debrief="Some debrief text.")
    strategies = await extract_strategies(result, team="red", llm=mock_llm)

    assert strategies == []


@pytest.mark.asyncio
async def test_save_and_load_strategies(tmp_path: Path):
    """Real DB: save a strategy, load it back, verify fields match."""
    db = Database(tmp_path / "test.db")
    await db.init()

    strategy = Strategy(
        team="blue",
        phase=2,
        strategy_type="defense",
        content="Block SQL injection patterns at WAF",
        win_rate=0.75,
        usage_count=4,
        created_round=5,
    )

    await save_strategies([strategy], db)

    loaded = await get_top_strategies(team="blue", phase=2, db=db, limit=10)

    assert len(loaded) == 1
    s = loaded[0]
    assert s.team == "blue"
    assert s.phase == 2
    assert s.strategy_type == "defense"
    assert s.content == "Block SQL injection patterns at WAF"
    assert s.win_rate == pytest.approx(0.75)
    assert s.usage_count == 4
    assert s.created_round == 5

    await db.close()


@pytest.mark.asyncio
async def test_get_top_strategies_ordering(tmp_path: Path):
    """Strategies are returned ordered by win_rate DESC."""
    db = Database(tmp_path / "test.db")
    await db.init()

    strategies = [
        Strategy(team="red", phase=1, strategy_type="attack", content="Low rate", win_rate=0.2, usage_count=5, created_round=1),
        Strategy(team="red", phase=1, strategy_type="attack", content="High rate", win_rate=0.9, usage_count=5, created_round=2),
        Strategy(team="red", phase=1, strategy_type="attack", content="Mid rate", win_rate=0.5, usage_count=5, created_round=3),
    ]
    await save_strategies(strategies, db)

    loaded = await get_top_strategies(team="red", phase=1, db=db, limit=5)

    assert len(loaded) == 3
    assert loaded[0].content == "High rate"
    assert loaded[1].content == "Mid rate"
    assert loaded[2].content == "Low rate"

    await db.close()


@pytest.mark.asyncio
async def test_update_win_rates(tmp_path: Path):
    """Save strategy with win_rate=0.5/count=2, update with round_won=True, verify new rate ≈ 0.667."""
    db = Database(tmp_path / "test.db")
    await db.init()

    strategy = Strategy(
        team="red",
        phase=1,
        strategy_type="attack",
        content="Test strategy",
        win_rate=0.5,
        usage_count=2,
        created_round=1,
    )
    await save_strategies([strategy], db)

    await update_win_rates(team="red", phase=1, round_won=True, db=db)

    loaded = await get_top_strategies(team="red", phase=1, db=db)
    assert len(loaded) == 1
    # new_rate = (0.5 * 2 + 1.0) / 3 = 2.0 / 3 ≈ 0.6667
    assert loaded[0].win_rate == pytest.approx(2.0 / 3, rel=1e-4)
    assert loaded[0].usage_count == 3

    await db.close()


@pytest.mark.asyncio
async def test_update_win_rates_loss(tmp_path: Path):
    """Update with round_won=False reduces win_rate correctly."""
    db = Database(tmp_path / "test.db")
    await db.init()

    strategy = Strategy(
        team="blue",
        phase=3,
        strategy_type="defense",
        content="Defensive play",
        win_rate=1.0,
        usage_count=2,
        created_round=1,
    )
    await save_strategies([strategy], db)

    await update_win_rates(team="blue", phase=3, round_won=False, db=db)

    loaded = await get_top_strategies(team="blue", phase=3, db=db)
    # new_rate = (1.0 * 2 + 0.0) / 3 = 2.0 / 3 ≈ 0.6667
    assert loaded[0].win_rate == pytest.approx(2.0 / 3, rel=1e-4)
    assert loaded[0].usage_count == 3

    await db.close()


@pytest.mark.asyncio
async def test_get_top_strategies_limit(tmp_path: Path):
    """Limit parameter restricts returned results."""
    db = Database(tmp_path / "test.db")
    await db.init()

    strategies = [
        Strategy(team="red", phase=1, strategy_type="attack", content=f"Strategy {i}", win_rate=float(i) / 10, usage_count=1, created_round=1)
        for i in range(8)
    ]
    await save_strategies(strategies, db)

    loaded = await get_top_strategies(team="red", phase=1, db=db, limit=3)
    assert len(loaded) == 3

    await db.close()
