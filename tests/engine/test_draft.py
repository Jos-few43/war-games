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
async def test_draft_pool_from_cves():
    from pathlib import Path
    from wargames.output.db import Database
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        await db.init()
        await db.save_cve({
            "cve_id": "CVE-2021-44228",
            "source": "nvd",
            "severity": "critical",
            "domain": "code-vuln",
            "description": "Log4Shell RCE via JNDI lookup",
            "exploit_code": "",
            "fix_hint": "Upgrade log4j",
            "fetched_at": "2026-03-06",
        })
        pool = await DraftPool.from_cves(db)
        cve_resources = [r for r in pool.resources if r.category == "cve"]
        assert len(cve_resources) == 1
        assert cve_resources[0].name == "CVE-2021-44228"
        assert "Log4Shell" in cve_resources[0].description
        # Should also have default resources
        assert len(pool.resources) > 1
        await db.close()


def test_mixed_pool_has_defaults_and_cves():
    default_pool = DraftPool.default()
    cve_resource = Resource("CVE-2021-44228", "cve", "Log4Shell RCE")
    mixed = DraftPool(default_pool.resources + [cve_resource])
    assert any(r.category == "cve" for r in mixed.resources)
    assert any(r.category == "offensive" for r in mixed.resources)


@pytest.mark.asyncio
async def test_draft_pool_from_cves_no_defaults():
    from pathlib import Path
    from wargames.output.db import Database
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        await db.init()
        await db.save_cve({
            "cve_id": "CVE-2021-44228",
            "source": "nvd", "severity": "critical", "domain": "code-vuln",
            "description": "Log4Shell", "exploit_code": "", "fix_hint": "",
            "fetched_at": "2026-03-06",
        })
        pool = await DraftPool.from_cves(db, include_defaults=False)
        assert len(pool.resources) == 1
        assert pool.resources[0].category == "cve"
        await db.close()


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
