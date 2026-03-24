from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from wargames.engine.strategy import (
    extract_strategies,
    get_top_strategies,
    prune_strategies,
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


def _make_round_result(
    round_number: int = 1, red_debrief: str = '', blue_debrief: str = ''
) -> RoundResult:
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
        {'strategy_type': 'attack', 'content': 'Use prompt injection to bypass guardrails'},
        {'strategy_type': 'defense', 'content': 'Rate-limit repeated injection attempts'},
    ]
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = json.dumps(extracted)

    result = _make_round_result(
        round_number=3,
        red_debrief='We used prompt injection techniques successfully.',
    )

    strategies = await extract_strategies(result, team='red', llm=mock_llm)

    assert len(strategies) == 2

    attack_strat = next(s for s in strategies if s.strategy_type == 'attack')
    assert attack_strat.team == 'red'
    assert attack_strat.phase == Phase.PROMPT_INJECTION.value
    assert attack_strat.content == 'Use prompt injection to bypass guardrails'
    assert attack_strat.created_round == 3
    assert attack_strat.win_rate == 0.0
    assert attack_strat.usage_count == 0

    defense_strat = next(s for s in strategies if s.strategy_type == 'defense')
    assert defense_strat.strategy_type == 'defense'


@pytest.mark.asyncio
async def test_extract_strategies_empty_debrief():
    """Empty debrief returns empty list without calling LLM."""
    mock_llm = AsyncMock()
    result = _make_round_result(red_debrief='')

    strategies = await extract_strategies(result, team='red', llm=mock_llm)

    assert strategies == []
    mock_llm.chat.assert_not_called()


@pytest.mark.asyncio
async def test_extract_strategies_invalid_json():
    """LLM returning non-JSON results in empty list."""
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = 'This is not JSON at all.'

    result = _make_round_result(red_debrief='Some debrief text.')
    strategies = await extract_strategies(result, team='red', llm=mock_llm)

    assert strategies == []


@pytest.mark.asyncio
async def test_save_and_load_strategies(tmp_path: Path):
    """Real DB: save a strategy, load it back, verify fields match."""
    db = Database(tmp_path / 'test.db')
    await db.init()

    strategy = Strategy(
        team='blue',
        phase=2,
        strategy_type='defense',
        content='Block SQL injection patterns at WAF',
        win_rate=0.75,
        usage_count=4,
        created_round=5,
    )

    await save_strategies([strategy], db)

    loaded = await get_top_strategies(team='blue', phase=2, db=db, limit=10)

    assert len(loaded) == 1
    s = loaded[0]
    assert s.team == 'blue'
    assert s.phase == 2
    assert s.strategy_type == 'defense'
    assert s.content == 'Block SQL injection patterns at WAF'
    assert s.win_rate == pytest.approx(0.75)
    assert s.usage_count == 4
    assert s.created_round == 5

    await db.close()


@pytest.mark.asyncio
async def test_get_top_strategies_ordering(tmp_path: Path):
    """Strategies are returned ordered by win_rate DESC."""
    db = Database(tmp_path / 'test.db')
    await db.init()

    strategies = [
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='Low rate',
            win_rate=0.2,
            usage_count=5,
            created_round=1,
        ),
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='High rate',
            win_rate=0.9,
            usage_count=5,
            created_round=2,
        ),
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='Mid rate',
            win_rate=0.5,
            usage_count=5,
            created_round=3,
        ),
    ]
    await save_strategies(strategies, db)

    loaded = await get_top_strategies(team='red', phase=1, db=db, limit=5)

    assert len(loaded) == 3
    assert loaded[0].content == 'High rate'
    assert loaded[1].content == 'Mid rate'
    assert loaded[2].content == 'Low rate'

    await db.close()


@pytest.mark.asyncio
async def test_update_win_rates(tmp_path: Path):
    """Save strategy with win_rate=0.5/count=2, update with round_won=True, verify new rate ≈ 0.667."""
    db = Database(tmp_path / 'test.db')
    await db.init()

    strategy = Strategy(
        team='red',
        phase=1,
        strategy_type='attack',
        content='Test strategy',
        win_rate=0.5,
        usage_count=2,
        created_round=1,
    )
    await save_strategies([strategy], db)

    loaded = await get_top_strategies(team='red', phase=1, db=db)
    await update_win_rates(strategy_ids=[loaded[0].id], round_won=True, db=db)

    loaded = await get_top_strategies(team='red', phase=1, db=db)
    assert len(loaded) == 1
    # new_rate = (0.5 * 2 + 1.0) / 3 = 2.0 / 3 ≈ 0.6667
    assert loaded[0].win_rate == pytest.approx(2.0 / 3, rel=1e-4)
    assert loaded[0].usage_count == 3

    await db.close()


@pytest.mark.asyncio
async def test_update_win_rates_loss(tmp_path: Path):
    """Update with round_won=False reduces win_rate correctly."""
    db = Database(tmp_path / 'test.db')
    await db.init()

    strategy = Strategy(
        team='blue',
        phase=3,
        strategy_type='defense',
        content='Defensive play',
        win_rate=1.0,
        usage_count=2,
        created_round=1,
    )
    await save_strategies([strategy], db)

    loaded = await get_top_strategies(team='blue', phase=3, db=db)
    await update_win_rates(strategy_ids=[loaded[0].id], round_won=False, db=db)

    loaded = await get_top_strategies(team='blue', phase=3, db=db)
    # new_rate = (1.0 * 2 + 0.0) / 3 = 2.0 / 3 ≈ 0.6667
    assert loaded[0].win_rate == pytest.approx(2.0 / 3, rel=1e-4)
    assert loaded[0].usage_count == 3

    await db.close()


@pytest.mark.asyncio
async def test_get_top_strategies_limit(tmp_path: Path):
    """Limit parameter restricts returned results."""
    db = Database(tmp_path / 'test.db')
    await db.init()

    strategies = [
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content=f'Strategy {i}',
            win_rate=float(i) / 10,
            usage_count=1,
            created_round=1,
        )
        for i in range(8)
    ]
    await save_strategies(strategies, db)

    loaded = await get_top_strategies(team='red', phase=1, db=db, limit=3)
    assert len(loaded) == 3

    await db.close()


@pytest.mark.asyncio
async def test_strategy_has_id_after_load(tmp_path: Path):
    """Strategies loaded from DB have their integer id set."""
    db = Database(tmp_path / 'test.db')
    await db.init()
    strategy = Strategy(
        team='red',
        phase=1,
        strategy_type='attack',
        content='Test strategy with id',
        win_rate=0.5,
        usage_count=1,
        created_round=1,
    )
    await save_strategies([strategy], db)
    loaded = await get_top_strategies(team='red', phase=1, db=db)
    assert len(loaded) == 1
    assert loaded[0].id is not None
    assert isinstance(loaded[0].id, int)
    await db.close()


@pytest.mark.asyncio
async def test_update_win_rates_by_id(tmp_path: Path):
    """Only strategies with specified IDs get their win rates updated."""
    db = Database(tmp_path / 'test.db')
    await db.init()
    strategies = [
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='Used strategy',
            win_rate=0.5,
            usage_count=2,
            created_round=1,
        ),
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='Not used strategy',
            win_rate=0.5,
            usage_count=2,
            created_round=1,
        ),
    ]
    await save_strategies(strategies, db)
    loaded = await get_top_strategies(team='red', phase=1, db=db)
    used_id = next(s.id for s in loaded if s.content == 'Used strategy')
    await update_win_rates(strategy_ids=[used_id], round_won=True, db=db)
    reloaded = await get_top_strategies(team='red', phase=1, db=db)
    used = next(s for s in reloaded if s.content == 'Used strategy')
    not_used = next(s for s in reloaded if s.content == 'Not used strategy')
    assert used.win_rate == pytest.approx(2.0 / 3, rel=1e-4)
    assert used.usage_count == 3
    assert not_used.win_rate == pytest.approx(0.5)
    assert not_used.usage_count == 2
    await db.close()


@pytest.mark.asyncio
async def test_update_win_rates_empty_ids(tmp_path: Path):
    """Empty ID list is a no-op."""
    db = Database(tmp_path / 'test.db')
    await db.init()
    strategy = Strategy(
        team='red',
        phase=1,
        strategy_type='attack',
        content='Some strat',
        win_rate=0.5,
        usage_count=2,
        created_round=1,
    )
    await save_strategies([strategy], db)
    await update_win_rates(strategy_ids=[], round_won=True, db=db)
    loaded = await get_top_strategies(team='red', phase=1, db=db)
    assert loaded[0].win_rate == pytest.approx(0.5)
    assert loaded[0].usage_count == 2
    await db.close()


@pytest.mark.asyncio
async def test_prune_underperformers(tmp_path: Path):
    """Strategies with usage >= 3 and win_rate < 0.2 get deactivated."""
    db = Database(tmp_path / 'test.db')
    await db.init()
    strategies = [
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='Winner',
            win_rate=0.8,
            usage_count=5,
            created_round=1,
        ),
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='Loser',
            win_rate=0.1,
            usage_count=4,
            created_round=1,
        ),
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='New loser',
            win_rate=0.0,
            usage_count=1,
            created_round=3,
        ),
    ]
    await save_strategies(strategies, db)
    await prune_strategies(team='red', phase=1, db=db)
    loaded = await get_top_strategies(team='red', phase=1, db=db)
    contents = [s.content for s in loaded]
    assert 'Winner' in contents
    assert 'New loser' in contents  # kept — not enough usage to judge
    assert 'Loser' not in contents  # pruned — low win rate with enough data
    await db.close()


@pytest.mark.asyncio
async def test_prune_caps_pool_size(tmp_path: Path):
    """Pool is capped at 20 active strategies per team/phase."""
    db = Database(tmp_path / 'test.db')
    await db.init()
    strategies = [
        Strategy(
            team='blue',
            phase=1,
            strategy_type='defense',
            content=f'Strategy {i}',
            win_rate=float(i) / 25,
            usage_count=1,
            created_round=1,
        )
        for i in range(25)
    ]
    await save_strategies(strategies, db)
    await prune_strategies(team='blue', phase=1, db=db)
    loaded = await get_top_strategies(team='blue', phase=1, db=db, limit=50)
    assert len(loaded) == 20
    assert loaded[0].content == 'Strategy 24'  # highest win_rate
    await db.close()


@pytest.mark.asyncio
async def test_pruned_strategies_remain_in_graveyard(tmp_path: Path):
    """Pruned strategies are soft-deleted (active=0), not hard-deleted."""
    db = Database(tmp_path / 'test.db')
    await db.init()
    strategy = Strategy(
        team='red',
        phase=1,
        strategy_type='attack',
        content='Bad strat',
        win_rate=0.05,
        usage_count=5,
        created_round=1,
    )
    await save_strategies([strategy], db)
    await prune_strategies(team='red', phase=1, db=db)
    loaded = await get_top_strategies(team='red', phase=1, db=db)
    assert len(loaded) == 0
    cursor = await db._conn.execute("SELECT active FROM strategies WHERE content = 'Bad strat'")
    row = await cursor.fetchone()
    assert row is not None
    assert row['active'] == 0
    await db.close()


@pytest.mark.asyncio
async def test_inactive_strategies_not_returned(tmp_path: Path):
    """Strategies with active=0 are excluded from get_top_strategies."""
    db = Database(tmp_path / 'test.db')
    await db.init()
    strategies = [
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='Active one',
            win_rate=0.8,
            usage_count=3,
            created_round=1,
        ),
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='Inactive one',
            win_rate=0.9,
            usage_count=3,
            created_round=1,
        ),
    ]
    await save_strategies(strategies, db)
    await db._conn.execute("UPDATE strategies SET active = 0 WHERE content = 'Inactive one'")
    await db._conn.commit()
    loaded = await get_top_strategies(team='red', phase=1, db=db)
    assert len(loaded) == 1
    assert loaded[0].content == 'Active one'
    await db.close()


@pytest.mark.asyncio
async def test_dedup_skips_similar_active(tmp_path: Path):
    """New strategy with >70% word overlap to existing active strategy is skipped."""
    db = Database(tmp_path / 'test.db')
    await db.init()
    existing = Strategy(
        team='red',
        phase=1,
        strategy_type='attack',
        content='Use SQL injection to bypass authentication and access admin panel',
        win_rate=0.5,
        usage_count=2,
        created_round=1,
    )
    await save_strategies([existing], db)
    duplicate = Strategy(
        team='red',
        phase=1,
        strategy_type='attack',
        content='Use SQL injection to bypass authentication and access the admin panel directly',
        win_rate=0.0,
        usage_count=0,
        created_round=2,
    )
    await save_strategies([duplicate], db)
    loaded = await get_top_strategies(team='red', phase=1, db=db, limit=10)
    assert len(loaded) == 1  # duplicate was skipped
    await db.close()


@pytest.mark.asyncio
async def test_dedup_skips_similar_inactive(tmp_path: Path):
    """New strategy with >70% word overlap to graveyard strategy is also skipped."""
    db = Database(tmp_path / 'test.db')
    await db.init()
    graveyard = Strategy(
        team='blue',
        phase=1,
        strategy_type='defense',
        content='Deploy WAF rules to block SQL injection patterns at the perimeter',
        win_rate=0.1,
        usage_count=5,
        created_round=1,
    )
    await save_strategies([graveyard], db)
    await db._conn.execute("UPDATE strategies SET active = 0 WHERE content LIKE '%WAF rules%'")
    await db._conn.commit()
    rehash = Strategy(
        team='blue',
        phase=1,
        strategy_type='defense',
        content='Deploy WAF rules to block SQL injection patterns at the network perimeter',
        win_rate=0.0,
        usage_count=0,
        created_round=3,
    )
    await save_strategies([rehash], db)
    loaded = await get_top_strategies(team='blue', phase=1, db=db, limit=10)
    assert len(loaded) == 0
    await db.close()


@pytest.mark.asyncio
async def test_dedup_allows_different_strategies(tmp_path: Path):
    """Strategies with <70% word overlap are allowed."""
    db = Database(tmp_path / 'test.db')
    await db.init()
    existing = Strategy(
        team='red',
        phase=1,
        strategy_type='attack',
        content='Use SQL injection to bypass authentication',
        win_rate=0.5,
        usage_count=2,
        created_round=1,
    )
    await save_strategies([existing], db)
    different = Strategy(
        team='red',
        phase=1,
        strategy_type='attack',
        content='Social engineering phishing campaign targeting admin credentials',
        win_rate=0.0,
        usage_count=0,
        created_round=2,
    )
    await save_strategies([different], db)
    loaded = await get_top_strategies(team='red', phase=1, db=db, limit=10)
    assert len(loaded) == 2
    await db.close()


@pytest.mark.asyncio
async def test_time_decay_favors_recent(tmp_path: Path):
    """Recent strategy with moderate win rate beats old strategy with high win rate."""
    db = Database(tmp_path / 'test.db')
    await db.init()
    strategies = [
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='Old winner',
            win_rate=0.8,
            usage_count=10,
            created_round=1,
        ),
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='Recent moderate',
            win_rate=0.7,
            usage_count=3,
            created_round=9,
        ),
    ]
    await save_strategies(strategies, db)
    # At round 10, recent strategy should rank higher due to recency bonus
    loaded = await get_top_strategies(team='red', phase=1, db=db, current_round=10)
    assert loaded[0].content == 'Recent moderate'
    await db.close()


@pytest.mark.asyncio
async def test_time_decay_without_round_falls_back(tmp_path: Path):
    """Without current_round, ordering falls back to pure win_rate DESC."""
    db = Database(tmp_path / 'test.db')
    await db.init()
    strategies = [
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='Lower rate',
            win_rate=0.5,
            usage_count=5,
            created_round=1,
        ),
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='Higher rate',
            win_rate=0.9,
            usage_count=5,
            created_round=1,
        ),
    ]
    await save_strategies(strategies, db)
    loaded = await get_top_strategies(team='red', phase=1, db=db)
    assert loaded[0].content == 'Higher rate'
    await db.close()


@pytest.mark.asyncio
async def test_evolution_full_cycle(tmp_path: Path):
    """Simulate a 3-round evolution cycle: extract, save, select, update, prune."""
    db = Database(tmp_path / 'test.db')
    await db.init()

    # Round 1: cold start — no strategies
    r1_top = await get_top_strategies('red', 1, db, current_round=1)
    assert len(r1_top) == 0

    # Simulate: round 1 extracts 3 strategies
    r1_strats = [
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='SQL injection via login form',
            created_round=1,
        ),
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='XSS in comment field',
            created_round=1,
        ),
        Strategy(
            team='red',
            phase=1,
            strategy_type='defense',
            content='Input validation on all fields',
            created_round=1,
        ),
    ]
    await save_strategies(r1_strats, db)

    # Round 2: load strategies, use them
    r2_top = await get_top_strategies('red', 1, db, current_round=2)
    assert len(r2_top) == 3
    r2_used_ids = [s.id for s in r2_top if s.id]

    # Red lost round 2
    await update_win_rates(strategy_ids=r2_used_ids, round_won=False, db=db)

    # Check: all used strategies now have usage=1, win_rate=0.0
    after_r2 = await get_top_strategies('red', 1, db, current_round=2)
    for s in after_r2:
        assert s.usage_count == 1
        assert s.win_rate == pytest.approx(0.0)

    # Round 2 also extracts 2 new strategies
    r2_new = [
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='Phishing with crafted email',
            created_round=2,
        ),
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='SQL injection via login form and API',
            created_round=2,
        ),
        # ^ this should be deduped against "SQL injection via login form"
    ]
    await save_strategies(r2_new, db)

    all_active = await get_top_strategies('red', 1, db, current_round=2, limit=20)
    contents = [s.content for s in all_active]
    assert 'Phishing with crafted email' in contents
    # The near-duplicate should NOT be saved
    assert 'SQL injection via login form and API' not in contents

    # Round 3: use top 5, win
    r3_top = await get_top_strategies('red', 1, db, current_round=3)
    r3_used_ids = [s.id for s in r3_top if s.id]
    await update_win_rates(strategy_ids=r3_used_ids, round_won=True, db=db)

    # After 2 uses (1 loss, 1 win) the round-1 strategies should have win_rate ≈ 0.5
    r1_reloaded = await get_top_strategies('red', 1, db, current_round=3, limit=20)
    sql_strat = next(s for s in r1_reloaded if 'SQL injection' in s.content)
    assert sql_strat.usage_count == 2
    assert sql_strat.win_rate == pytest.approx(0.5)

    # The phishing strat (round 2, 1 use, 1 win) should have win_rate=1.0
    phishing = next(s for s in r1_reloaded if 'Phishing' in s.content)
    assert phishing.usage_count == 1
    assert phishing.win_rate == pytest.approx(1.0)

    # With time decay at round 3: phishing (round 2, wr=1.0) should outrank SQL (round 1, wr=0.5)
    assert r3_top[0].content != 'SQL injection via login form' or r3_top[0].win_rate >= 0.5

    await db.close()


# =============================================================================
# Tests for Advanced Strategy Learning Features
# =============================================================================


@pytest.mark.asyncio
async def test_temporal_difference_learning_adaptive_rate(tmp_path: Path):
    """TD learning uses adaptive learning rate (1/(n+1)) equivalent to incremental averaging."""
    db = Database(tmp_path / 'test.db')
    await db.init()

    strategy = Strategy(
        team='red',
        phase=1,
        strategy_type='attack',
        content='TD test strategy',
        win_rate=0.0,
        usage_count=0,
        created_round=1,
    )
    await save_strategies([strategy], db)

    loaded = await get_top_strategies(team='red', phase=1, db=db)
    strategy_id = loaded[0].id

    # First win: new_rate = 0 + 1/1 * (1 - 0) = 1.0
    await update_win_rates(strategy_ids=[strategy_id], round_won=True, db=db)
    loaded = await get_top_strategies(team='red', phase=1, db=db)
    assert loaded[0].win_rate == pytest.approx(1.0)
    assert loaded[0].usage_count == 1

    # Second loss: new_rate = 1.0 + 1/2 * (0 - 1.0) = 1.0 - 0.5 = 0.5
    await update_win_rates(strategy_ids=[strategy_id], round_won=False, db=db)
    loaded = await get_top_strategies(team='red', phase=1, db=db)
    assert loaded[0].win_rate == pytest.approx(0.5)
    assert loaded[0].usage_count == 2

    # Third win: new_rate = 0.5 + 1/3 * (1 - 0.5) = 0.5 + 0.1667 = 0.6667
    await update_win_rates(strategy_ids=[strategy_id], round_won=True, db=db)
    loaded = await get_top_strategies(team='red', phase=1, db=db)
    assert loaded[0].win_rate == pytest.approx(2.0 / 3, rel=1e-4)
    assert loaded[0].usage_count == 3

    await db.close()


@pytest.mark.asyncio
async def test_temporal_difference_learning_converges_to_true_winrate(tmp_path: Path):
    """TD learning with adaptive rate should converge to true win rate over many rounds."""
    db = Database(tmp_path / 'test.db')
    await db.init()

    strategy = Strategy(
        team='blue',
        phase=2,
        strategy_type='defense',
        content='Convergence test strategy',
        win_rate=0.0,
        usage_count=0,
        created_round=1,
    )
    await save_strategies([strategy], db)

    loaded = await get_top_strategies(team='blue', phase=2, db=db)
    strategy_id = loaded[0].id

    # Simulate 10 rounds with 7 wins (70% true win rate)
    wins = [True, True, True, True, True, True, True, False, False, False]
    for won in wins:
        await update_win_rates(strategy_ids=[strategy_id], round_won=won, db=db)

    loaded = await get_top_strategies(team='blue', phase=2, db=db)
    # After 10 rounds, win_rate should be close to 0.7
    assert loaded[0].win_rate == pytest.approx(0.7, rel=0.1)
    assert loaded[0].usage_count == 10

    await db.close()


@pytest.mark.asyncio
async def test_opponent_modeling_fields_persisted(tmp_path: Path):
    """Opponent modeling fields (opp_usage_count, opp_effectiveness) are saved and loaded."""
    db = Database(tmp_path / 'test.db')
    await db.init()

    strategy = Strategy(
        team='red',
        phase=1,
        strategy_type='attack',
        content='Opponent modeling test',
        win_rate=0.5,
        usage_count=5,
        created_round=1,
        opp_usage_count=3,
        opp_effectiveness=0.7,
    )
    await save_strategies([strategy], db)

    # Directly update the opponent modeling fields in the database
    cursor = await db._conn.execute(
        'UPDATE strategies SET opp_usage_count = 5, opp_effectiveness = 0.8 WHERE content = ?',
        ('Opponent modeling test',),
    )
    await db._conn.commit()

    loaded = await get_top_strategies(team='red', phase=1, db=db)
    assert len(loaded) == 1
    assert loaded[0].opp_usage_count == 5
    assert loaded[0].opp_effectiveness == pytest.approx(0.8)

    await db.close()


@pytest.mark.asyncio
async def test_strategy_diversity_identical_strategies(tmp_path: Path):
    """Diversity score is 0.0 when all strategies are identical."""
    from wargames.engine.strategy import _calculate_strategy_diversity

    strategies = [
        Strategy(
            team='red', phase=1, strategy_type='attack', content='SQL injection', created_round=1
        ),
        Strategy(
            team='red', phase=1, strategy_type='attack', content='SQL injection', created_round=1
        ),
        Strategy(
            team='red', phase=1, strategy_type='attack', content='SQL injection', created_round=1
        ),
    ]

    diversity = _calculate_strategy_diversity(strategies)
    assert diversity == pytest.approx(0.0, abs=1e-6)


@pytest.mark.asyncio
async def test_strategy_diversity_completely_different(tmp_path: Path):
    """Diversity score approaches 1.0 when strategies are completely different."""
    from wargames.engine.strategy import _calculate_strategy_diversity

    strategies = [
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='SQL injection database',
            created_round=1,
        ),
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='XSS cross site scripting',
            created_round=1,
        ),
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='phishing social engineering',
            created_round=1,
        ),
    ]

    diversity = _calculate_strategy_diversity(strategies)
    # With no overlapping words, diversity should be close to 1.0
    assert diversity > 0.8


@pytest.mark.asyncio
async def test_strategy_diversity_single_strategy(tmp_path: Path):
    """Diversity score is 0.0 when there's only one strategy."""
    from wargames.engine.strategy import _calculate_strategy_diversity

    strategies = [
        Strategy(
            team='red', phase=1, strategy_type='attack', content='SQL injection', created_round=1
        ),
    ]

    diversity = _calculate_strategy_diversity(strategies)
    assert diversity == 0.0


@pytest.mark.asyncio
async def test_strategy_diversity_empty_list(tmp_path: Path):
    """Diversity score is 0.0 for empty strategy list."""
    from wargames.engine.strategy import _calculate_strategy_diversity

    diversity = _calculate_strategy_diversity([])
    assert diversity == 0.0


@pytest.mark.asyncio
async def test_strategy_diversity_partial_overlap(tmp_path: Path):
    """Diversity score reflects partial word overlap between strategies."""
    from wargames.engine.strategy import _calculate_strategy_diversity

    # Strategies with ~50% word overlap
    strategies = [
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='SQL injection attack database',
            created_round=1,
        ),
        Strategy(
            team='red',
            phase=1,
            strategy_type='attack',
            content='SQL injection bypass authentication',
            created_round=1,
        ),
    ]

    diversity = _calculate_strategy_diversity(strategies)
    # Two strategies with partial overlap should have moderate diversity
    assert 0.3 < diversity < 0.8


@pytest.mark.asyncio
async def test_opponent_modeling_integration(tmp_path: Path):
    """Integration test: simulate opponent modeling through direct DB updates."""
    db = Database(tmp_path / 'test.db')
    await db.init()

    # Create strategies for both teams
    red_strategy = Strategy(
        team='red',
        phase=1,
        strategy_type='attack',
        content='Red team attack',
        win_rate=0.6,
        usage_count=10,
        created_round=1,
        opp_usage_count=0,
        opp_effectiveness=0.0,
    )
    blue_strategy = Strategy(
        team='blue',
        phase=1,
        strategy_type='defense',
        content='Blue team defense',
        win_rate=0.7,
        usage_count=8,
        created_round=1,
        opp_usage_count=0,
        opp_effectiveness=0.0,
    )

    await save_strategies([red_strategy, blue_strategy], db)

    loaded = await get_top_strategies(team='red', phase=1, db=db)
    red_id = loaded[0].id

    # Simulate opponent usage: blue used this strategy 3 times against red
    await db._conn.execute(
        'UPDATE strategies SET opp_usage_count = 3, opp_effectiveness = 0.4 WHERE id = ?', (red_id,)
    )
    await db._conn.commit()

    # Reload and verify opponent modeling data
    loaded = await get_top_strategies(team='red', phase=1, db=db)
    assert loaded[0].opp_usage_count == 3
    assert loaded[0].opp_effectiveness == pytest.approx(0.4)

    await db.close()


@pytest.mark.asyncio
async def test_td_learning_with_multiple_strategies(tmp_path: Path):
    """TD learning updates multiple strategies independently."""
    db = Database(tmp_path / 'test.db')
    await db.init()

    strategies = [
        Strategy(
            team='red', phase=1, strategy_type='attack', content='Strategy A', created_round=1
        ),
        Strategy(
            team='red', phase=1, strategy_type='attack', content='Strategy B', created_round=1
        ),
        Strategy(
            team='red', phase=1, strategy_type='attack', content='Strategy C', created_round=1
        ),
    ]
    await save_strategies(strategies, db)

    loaded = await get_top_strategies(team='red', phase=1, db=db, limit=10)
    ids = [s.id for s in loaded]

    # Update only first two strategies with wins
    await update_win_rates(strategy_ids=ids[:2], round_won=True, db=db)

    # Update third strategy with loss
    await update_win_rates(strategy_ids=[ids[2]], round_won=False, db=db)

    loaded = await get_top_strategies(team='red', phase=1, db=db, limit=10)

    # First two should have win_rate = 1.0
    assert loaded[0].win_rate == pytest.approx(1.0)
    assert loaded[1].win_rate == pytest.approx(1.0)

    # Third should have win_rate = 0.0
    strat_c = next(s for s in loaded if s.content == 'Strategy C')
    assert strat_c.win_rate == pytest.approx(0.0)

    await db.close()
