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
