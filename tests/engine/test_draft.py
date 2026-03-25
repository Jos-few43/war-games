import pytest
from unittest.mock import AsyncMock
from wargames.engine.draft import DraftPool, DraftEngine, EnhancedDraftEngine, Resource


def test_draft_pool_has_resources():
    pool = DraftPool.default()
    assert len(pool.resources) >= 12
    offensive = [r for r in pool.resources if r.category == 'offensive']
    defensive = [r for r in pool.resources if r.category == 'defensive']
    assert len(offensive) >= 4
    assert len(defensive) >= 4


def test_snake_draft_order():
    engine = DraftEngine(picks_per_team=3, style='snake')
    order = engine.draft_order()
    assert order == ['red', 'blue', 'blue', 'red', 'red', 'blue']


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
    with pytest.raises(ValueError, match='already drafted'):
        pool.pick(resource.name)


@pytest.mark.asyncio
async def test_draft_pool_from_cves():
    from pathlib import Path
    from wargames.output.db import Database
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / 'test.db')
        await db.init()
        await db.save_cve(
            {
                'cve_id': 'CVE-2021-44228',
                'source': 'nvd',
                'severity': 'critical',
                'domain': 'code-vuln',
                'description': 'Log4Shell RCE via JNDI lookup',
                'exploit_code': '',
                'fix_hint': 'Upgrade log4j',
                'fetched_at': '2026-03-06',
            }
        )
        pool = await DraftPool.from_cves(db)
        cve_resources = [r for r in pool.resources if r.category == 'cve']
        assert len(cve_resources) == 1
        assert cve_resources[0].name == 'CVE-2021-44228'
        assert 'Log4Shell' in cve_resources[0].description
        # Should also have default resources
        assert len(pool.resources) > 1
        await db.close()


def test_mixed_pool_has_defaults_and_cves():
    default_pool = DraftPool.default()
    cve_resource = Resource('CVE-2021-44228', 'cve', 'Log4Shell RCE')
    mixed = DraftPool(default_pool.resources + [cve_resource])
    assert any(r.category == 'cve' for r in mixed.resources)
    assert any(r.category == 'offensive' for r in mixed.resources)


@pytest.mark.asyncio
async def test_draft_pool_from_cves_no_defaults():
    from pathlib import Path
    from wargames.output.db import Database
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / 'test.db')
        await db.init()
        await db.save_cve(
            {
                'cve_id': 'CVE-2021-44228',
                'source': 'nvd',
                'severity': 'critical',
                'domain': 'code-vuln',
                'description': 'Log4Shell',
                'exploit_code': '',
                'fix_hint': '',
                'fetched_at': '2026-03-06',
            }
        )
        pool = await DraftPool.from_cves(db, include_defaults=False)
        assert len(pool.resources) == 1
        assert pool.resources[0].category == 'cve'
        await db.close()


@pytest.mark.asyncio
async def test_run_draft_calls_llm_for_each_pick():
    mock_red_llm = AsyncMock()
    mock_blue_llm = AsyncMock()
    pool = DraftPool.default()
    available_names = [r.name for r in pool.available()]

    mock_red_llm.chat.side_effect = [available_names[0], available_names[3], available_names[4]]
    mock_blue_llm.chat.side_effect = [available_names[1], available_names[2], available_names[5]]

    engine = DraftEngine(picks_per_team=3, style='snake')
    red_picks, blue_picks = await engine.run(pool, mock_red_llm, mock_blue_llm)

    assert len(red_picks) == 3
    assert len(blue_picks) == 3
    assert mock_red_llm.chat.call_count == 3
    assert mock_blue_llm.chat.call_count == 3


# --- Enhanced Draft Engine Tests ---


from wargames.engine.draft import EnhancedDraftEngine
from wargames.models import ToolBan, ToolCategory, ToolPool


def test_enhanced_draft_engine_initialization():
    """EnhancedDraftEngine initializes with correct parameters."""
    engine = EnhancedDraftEngine(picks_per_team=3, bans_per_team=2, style='snake')
    assert engine.picks_per_team == 3
    assert engine.bans_per_team == 2
    assert engine.style == 'snake'
    assert engine.red_pools == []
    assert engine.blue_pools == []
    assert engine.shared_pools == []


def test_enhanced_draft_add_pool():
    """Tool pools can be added and categorized correctly."""
    engine = EnhancedDraftEngine(picks_per_team=3)

    red_pool = ToolPool(
        name='red_exploits', category=ToolCategory.EXPLOIT, team='red', available_tools=['exploit1']
    )
    blue_pool = ToolPool(
        name='blue_defense',
        category=ToolCategory.DEFENSE,
        team='blue',
        available_tools=['defense1'],
    )
    shared_pool = ToolPool(
        name='shared_recon', category=ToolCategory.RECON, available_tools=['recon1']
    )

    engine.add_pool(red_pool)
    engine.add_pool(blue_pool)
    engine.add_pool(shared_pool)

    assert len(engine.red_pools) == 1
    assert len(engine.blue_pools) == 1
    assert len(engine.shared_pools) == 1


def test_enhanced_draft_get_available_tools():
    """Available tools include team-specific and shared pools."""
    engine = EnhancedDraftEngine(picks_per_team=3)

    engine.add_pool(
        ToolPool(
            name='red_only', category=ToolCategory.EXPLOIT, team='red', available_tools=['red_tool']
        )
    )
    engine.add_pool(
        ToolPool(
            name='blue_only',
            category=ToolCategory.DEFENSE,
            team='blue',
            available_tools=['blue_tool'],
        )
    )
    engine.add_pool(
        ToolPool(name='shared', category=ToolCategory.RECON, available_tools=['shared_tool'])
    )

    red_tools = engine.get_available_tools('red')
    blue_tools = engine.get_available_tools('blue')

    assert 'red_tool' in red_tools
    assert 'shared_tool' in red_tools
    assert 'blue_tool' not in red_tools

    assert 'blue_tool' in blue_tools
    assert 'shared_tool' in blue_tools
    assert 'red_tool' not in blue_tools


def test_enhanced_draft_ban_order():
    """Ban order alternates between red and blue."""
    engine = EnhancedDraftEngine(picks_per_team=3, bans_per_team=2)
    order = engine._get_ban_order()
    assert order == ['red', 'blue', 'red', 'blue']


def test_enhanced_draft_draft_order():
    """Draft order follows snake pattern."""
    engine = EnhancedDraftEngine(picks_per_team=3)
    order = engine._get_draft_order()
    assert order == ['red', 'blue', 'blue', 'red', 'red', 'blue']


@pytest.mark.asyncio
async def test_enhanced_draft_ban_phase():
    """Ban phase removes tools from play."""
    mock_red_llm = AsyncMock()
    mock_blue_llm = AsyncMock()

    engine = EnhancedDraftEngine(picks_per_team=2, bans_per_team=1)
    engine.add_pool(
        ToolPool(
            name='shared_pool',
            category=ToolCategory.EXPLOIT,
            available_tools=['tool_a', 'tool_b', 'tool_c', 'tool_d'],
        )
    )

    # Red bans tool_a, blue bans tool_b
    mock_red_llm.chat.return_value = 'tool_a'
    mock_blue_llm.chat.return_value = 'tool_b'

    state = await engine.run(mock_red_llm, mock_blue_llm)

    assert len(state.red_bans) == 1
    assert len(state.blue_bans) == 1
    assert state.red_bans[0].tool_name == 'tool_a'
    assert state.blue_bans[0].tool_name == 'tool_b'


@pytest.mark.asyncio
async def test_enhanced_draft_pick_phase():
    """Draft phase selects tools from available pool."""
    mock_red_llm = AsyncMock()
    mock_blue_llm = AsyncMock()

    engine = EnhancedDraftEngine(picks_per_team=2, bans_per_team=0)
    engine.add_pool(
        ToolPool(
            name='shared_pool',
            category=ToolCategory.EXPLOIT,
            available_tools=['tool_a', 'tool_b', 'tool_c', 'tool_d'],
        )
    )

    # Alternating picks: red, blue, blue, red
    mock_red_llm.chat.side_effect = ['tool_a', 'tool_d']
    mock_blue_llm.chat.side_effect = ['tool_b', 'tool_c']

    state = await engine.run(mock_red_llm, mock_blue_llm)

    assert len(state.red_picks) == 2
    assert len(state.blue_picks) == 2


@pytest.mark.asyncio
async def test_enhanced_draft_with_asymmetric_pools():
    """Teams can have access to different tool pools."""
    mock_red_llm = AsyncMock()
    mock_blue_llm = AsyncMock()

    engine = EnhancedDraftEngine(picks_per_team=2, bans_per_team=0)
    engine.add_pool(
        ToolPool(
            name='red_only',
            category=ToolCategory.EXPLOIT,
            team='red',
            available_tools=['red_exploit'],
        )
    )
    engine.add_pool(
        ToolPool(
            name='blue_only',
            category=ToolCategory.DEFENSE,
            team='blue',
            available_tools=['blue_defense'],
        )
    )
    engine.add_pool(
        ToolPool(name='shared', category=ToolCategory.RECON, available_tools=['shared_recon'])
    )

    mock_red_llm.chat.side_effect = ['red_exploit', 'shared_recon']
    mock_blue_llm.chat.side_effect = ['blue_defense', 'shared_recon']

    state = await engine.run(mock_red_llm, mock_blue_llm)

    # Red should only pick from red + shared pools
    red_tool_names = [p.resource_name for p in state.red_picks]
    assert 'red_exploit' in red_tool_names or 'shared_recon' in red_tool_names

    # Blue should only pick from blue + shared pools
    blue_tool_names = [p.resource_name for p in state.blue_picks]
    assert 'blue_defense' in blue_tool_names or 'shared_recon' in blue_tool_names
