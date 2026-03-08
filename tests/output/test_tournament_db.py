import pytest
import pytest_asyncio
from pathlib import Path
from wargames.output.db import Database


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test_tournament.db")
    await database.init()
    yield database
    await database.close()


# --- table existence ---

@pytest.mark.asyncio
async def test_tournament_tables_exist(db):
    tables = await db.list_tables()
    assert "model_ratings" in tables
    assert "seasons" in tables
    assert "token_usage" in tables


# --- model_ratings ---

@pytest.mark.asyncio
async def test_save_and_get_model_rating(db):
    await db.save_model_rating("gpt-4o", 1600.0, wins=5, losses=2, draws=1)
    result = await db.get_model_rating("gpt-4o")
    assert result is not None
    assert result["model_name"] == "gpt-4o"
    assert result["rating"] == 1600.0
    assert result["wins"] == 5
    assert result["losses"] == 2
    assert result["draws"] == 1
    assert result["last_played"] is not None


@pytest.mark.asyncio
async def test_get_model_rating_nonexistent_returns_none(db):
    result = await db.get_model_rating("does-not-exist")
    assert result is None


@pytest.mark.asyncio
async def test_save_model_rating_upsert(db):
    await db.save_model_rating("claude-3", 1500.0, wins=0, losses=0, draws=0)
    await db.save_model_rating("claude-3", 1550.0, wins=1, losses=0, draws=0)
    result = await db.get_model_rating("claude-3")
    assert result["rating"] == 1550.0
    assert result["wins"] == 1


@pytest.mark.asyncio
async def test_get_all_ratings_sorted_desc(db):
    await db.save_model_rating("low-model", 1400.0, wins=0, losses=5, draws=0)
    await db.save_model_rating("high-model", 1700.0, wins=8, losses=1, draws=0)
    await db.save_model_rating("mid-model", 1550.0, wins=3, losses=3, draws=1)

    ratings = await db.get_all_ratings()
    assert len(ratings) == 3
    assert ratings[0]["model_name"] == "high-model"
    assert ratings[1]["model_name"] == "mid-model"
    assert ratings[2]["model_name"] == "low-model"

    # Verify descending order by rating value
    rating_values = [r["rating"] for r in ratings]
    assert rating_values == sorted(rating_values, reverse=True)


# --- seasons ---

@pytest.mark.asyncio
async def test_save_and_get_season(db):
    await db.save_season("s-001", "standard_5round", "2026-01-01T00:00:00")
    season = await db.get_season("s-001")
    assert season is not None
    assert season["season_id"] == "s-001"
    assert season["config_name"] == "standard_5round"
    assert season["started_at"] == "2026-01-01T00:00:00"
    assert season["ended_at"] is None
    assert season["winner"] is None


@pytest.mark.asyncio
async def test_get_season_nonexistent_returns_none(db):
    result = await db.get_season("no-such-season")
    assert result is None


@pytest.mark.asyncio
async def test_end_season_updates_ended_at_and_winner(db):
    await db.save_season("s-002", "blitz_3round", "2026-02-01T10:00:00")
    await db.end_season("s-002", "2026-02-01T12:30:00", "red")
    season = await db.get_season("s-002")
    assert season["ended_at"] == "2026-02-01T12:30:00"
    assert season["winner"] == "red"


# --- token_usage ---

@pytest.mark.asyncio
async def test_save_and_get_token_usage(db):
    await db.save_token_usage(
        round_number=1,
        team="red",
        prompt_tokens=500,
        completion_tokens=200,
        model_used="gpt-4o",
        cost=0.012,
    )
    rows = await db.get_token_usage()
    assert len(rows) == 1
    row = rows[0]
    assert row["round_number"] == 1
    assert row["team"] == "red"
    assert row["prompt_tokens"] == 500
    assert row["completion_tokens"] == 200
    assert row["model_used"] == "gpt-4o"
    assert row["cost"] == pytest.approx(0.012)


@pytest.mark.asyncio
async def test_get_token_usage_ordered_by_id(db):
    await db.save_token_usage(1, "red", 100, 50, "gpt-4o", 0.005)
    await db.save_token_usage(2, "blue", 200, 80, "claude-3", 0.008)
    await db.save_token_usage(3, "red", 150, 60, "gpt-4o", 0.006)

    rows = await db.get_token_usage()
    assert len(rows) == 3
    ids = [r["id"] for r in rows]
    assert ids == sorted(ids)


@pytest.mark.asyncio
async def test_get_token_totals_aggregates_correctly(db):
    await db.save_token_usage(1, "red", 100, 50, "gpt-4o", 0.005)
    await db.save_token_usage(2, "blue", 200, 80, "claude-3", 0.008)
    await db.save_token_usage(3, "red", 150, 60, "gpt-4o", 0.006)

    totals = await db.get_token_totals()
    assert totals["prompt_tokens"] == 450
    assert totals["completion_tokens"] == 190
    assert totals["cost"] == pytest.approx(0.019)


@pytest.mark.asyncio
async def test_get_token_totals_empty_returns_zeros(db):
    totals = await db.get_token_totals()
    assert totals["prompt_tokens"] == 0
    assert totals["completion_tokens"] == 0
    assert totals["cost"] == 0.0
