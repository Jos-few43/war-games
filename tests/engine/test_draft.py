import pytest
from unittest.mock import AsyncMock
from wargames.engine.draft import DraftPool, DraftEngine, Resource


def test_draft_pool_has_resources():
    pool = DraftPool.default()
    assert len(pool.resources) >= 12
    offensive = [r for r in pool.resources if r.category == "offensive"]
    defensive = [r for r in pool.resources if r.category == "defensive"]
    assert len(offensive) >= 4
    assert len(defensive) >= 4


def test_snake_draft_order():
    engine = DraftEngine(picks_per_team=3, style="snake")
    order = engine.draft_order()
    assert order == ["red", "blue", "blue", "red", "red", "blue"]


def test_draft_pick_removes_from_pool():
    pool = DraftPool.default()
    initial_count = len(pool.available())
    resource = pool.available()[0]
    pool.pick(resource.name)
    assert len(pool.available()) == initial_count - 1
    assert resource.name not in [r.name for r in pool.available()]


def test_cannot_pick_already_drafted():
    pool = DraftPool.default()
    resource = pool.available()[0]
    pool.pick(resource.name)
    with pytest.raises(ValueError, match="already drafted"):
        pool.pick(resource.name)


@pytest.mark.asyncio
async def test_run_draft_calls_llm_for_each_pick():
    mock_red_llm = AsyncMock()
    mock_blue_llm = AsyncMock()
    pool = DraftPool.default()
    available_names = [r.name for r in pool.available()]

    mock_red_llm.chat.side_effect = [available_names[0], available_names[3], available_names[4]]
    mock_blue_llm.chat.side_effect = [available_names[1], available_names[2], available_names[5]]

    engine = DraftEngine(picks_per_team=3, style="snake")
    red_picks, blue_picks = await engine.run(pool, mock_red_llm, mock_blue_llm)

    assert len(red_picks) == 3
    assert len(blue_picks) == 3
    assert mock_red_llm.chat.call_count == 3
    assert mock_blue_llm.chat.call_count == 3
