import pytest
import pytest_asyncio
from pathlib import Path
from wargames.output.db import Database
from wargames.models import (
    RoundResult, Phase, MatchOutcome, AttackResult,
    DefenseResult, DraftPick, Severity,
)

@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.init()
    yield database
    await database.close()

@pytest.mark.asyncio
async def test_init_creates_tables(db):
    tables = await db.list_tables()
    assert "rounds" in tables
    assert "attacks" in tables
    assert "defenses" in tables
    assert "draft_picks" in tables
    assert "crawled_cves" in tables
    assert "game_state" in tables

@pytest.mark.asyncio
async def test_save_and_load_round(db):
    result = RoundResult(
        round_number=1,
        phase=Phase.PROMPT_INJECTION,
        outcome=MatchOutcome.RED_WIN,
        red_score=12,
        blue_threshold=10,
        red_draft=[DraftPick(round=1, team="red", resource_name="fuzzer", resource_category="offensive")],
        blue_draft=[DraftPick(round=1, team="blue", resource_name="WAF", resource_category="defensive")],
        attacks=[AttackResult(turn=1, description="SQLi on /users", severity=Severity.HIGH, points=5, success=True)],
        defenses=[DefenseResult(turn=2, description="Blocked with parameterized queries", blocked=True, points_deducted=2)],
        red_debrief="SQLi worked well.",
        blue_debrief="Need better input validation.",
    )
    await db.save_round(result)
    loaded = await db.get_round(1)
    assert loaded.round_number == 1
    assert loaded.outcome == MatchOutcome.RED_WIN
    assert loaded.red_score == 12
    assert len(loaded.attacks) == 1
    assert len(loaded.defenses) == 1

@pytest.mark.asyncio
async def test_get_season_stats(db):
    for i, outcome in enumerate([MatchOutcome.RED_WIN, MatchOutcome.BLUE_WIN, MatchOutcome.RED_AUTO_WIN], 1):
        result = RoundResult(
            round_number=i, phase=Phase.PROMPT_INJECTION, outcome=outcome,
            red_score=i * 3, blue_threshold=10,
            red_draft=[], blue_draft=[], attacks=[], defenses=[],
        )
        await db.save_round(result)
    stats = await db.get_season_stats()
    assert stats["red_wins"] == 1
    assert stats["blue_wins"] == 1
    assert stats["auto_wins"] == 1
    assert stats["total_rounds"] == 3

@pytest.mark.asyncio
async def test_game_state_persistence(db):
    await db.set_game_state("current_round", "5")
    await db.set_game_state("current_phase", "2")
    assert await db.get_game_state("current_round") == "5"
    assert await db.get_game_state("current_phase") == "2"
    await db.set_game_state("current_round", "6")
    assert await db.get_game_state("current_round") == "6"


@pytest.mark.asyncio
async def test_save_and_get_tournament_match(db):
    await db.save_tournament_match(
        tournament_name="test-tourney",
        swiss_round=1,
        red_model="model-a",
        blue_model="model-b",
        red_score=12,
        blue_score=8,
        outcome="red_win",
    )
    await db.save_tournament_match(
        tournament_name="test-tourney",
        swiss_round=1,
        red_model="model-c",
        blue_model="model-d",
        red_score=5,
        blue_score=10,
        outcome="blue_win",
    )
    matches = await db.get_tournament_matches("test-tourney")
    assert len(matches) == 2
    assert matches[0]["red_model"] == "model-a"
    assert matches[0]["blue_model"] == "model-b"
    assert matches[0]["red_score"] == 12
    assert matches[0]["blue_score"] == 8
    assert matches[0]["outcome"] == "red_win"
    assert matches[0]["swiss_round"] == 1
    assert matches[0]["played_at"] is not None
    assert matches[1]["outcome"] == "blue_win"
    # Different tournament returns empty
    other = await db.get_tournament_matches("other-tourney")
    assert other == []
