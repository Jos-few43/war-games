from __future__ import annotations

import pytest
from wargames.engine.draft import DraftPool
from wargames.engine.loadouts import PRESETS, resolve_loadout
from wargames.models import DraftPick, TeamSettings


def _make_team(loadout: str = "", loadout_custom: list[str] | None = None) -> TeamSettings:
    return TeamSettings(
        name="test",
        model="http://localhost:4000",
        model_name="gpt-4o",
        temperature=0.7,
        loadout=loadout,
        loadout_custom=loadout_custom or [],
    )


# --- PRESET STRUCTURE ---

def test_four_presets_exist():
    assert set(PRESETS.keys()) == {"aggressive", "defensive", "balanced", "recon"}


def test_preset_resources_exist_in_default_pool():
    pool = DraftPool.default()
    pool_names = {r.name for r in pool.resources}
    for preset_name, resources in PRESETS.items():
        for resource in resources:
            assert resource in pool_names, (
                f"Preset '{preset_name}' references '{resource}' which is not in DraftPool.default()"
            )


def test_aggressive_preset_contents():
    assert PRESETS["aggressive"] == ["fuzzer", "sqli_kit", "prompt_injector", "priv_esc_toolkit"]


def test_defensive_preset_contents():
    assert PRESETS["defensive"] == ["waf_rules", "rate_limiter", "input_sanitizer", "sandboxing"]


def test_balanced_preset_contents():
    assert PRESETS["balanced"] == ["fuzzer", "waf_rules", "port_scanner", "input_sanitizer"]


def test_recon_preset_contents():
    assert PRESETS["recon"] == ["port_scanner", "code_analyzer", "network_mapper", "cve_database"]


# --- resolve_loadout: named preset ---

def test_resolve_named_preset_returns_draft_picks():
    team = _make_team(loadout="aggressive")
    picks = resolve_loadout(team)
    assert len(picks) == 4
    names = [p.resource_name for p in picks]
    assert names == ["fuzzer", "sqli_kit", "prompt_injector", "priv_esc_toolkit"]


def test_resolve_named_preset_pick_fields():
    team = _make_team(loadout="defensive")
    picks = resolve_loadout(team)
    for pick in picks:
        assert isinstance(pick, DraftPick)
        assert pick.round == 0
        assert pick.resource_category == "loadout"


def test_resolve_named_preset_team_field():
    team = _make_team(loadout="recon")
    team_name = "red"
    picks = resolve_loadout(team, team_name=team_name)
    for pick in picks:
        assert pick.team == "red"


# --- resolve_loadout: custom list ---

def test_resolve_custom_loadout():
    team = _make_team(loadout_custom=["fuzzer", "waf_rules"])
    picks = resolve_loadout(team)
    assert len(picks) == 2
    assert picks[0].resource_name == "fuzzer"
    assert picks[1].resource_name == "waf_rules"


def test_resolve_custom_loadout_overrides_named_preset():
    team = _make_team(loadout="aggressive", loadout_custom=["waf_rules", "sandboxing"])
    picks = resolve_loadout(team)
    names = [p.resource_name for p in picks]
    # custom takes priority — should NOT be the aggressive preset
    assert names == ["waf_rules", "sandboxing"]


def test_resolve_custom_loadout_pick_fields():
    team = _make_team(loadout_custom=["port_scanner"])
    picks = resolve_loadout(team)
    assert picks[0].round == 0
    assert picks[0].resource_category == "loadout"


# --- resolve_loadout: no loadout ---

def test_resolve_no_loadout_returns_empty():
    team = _make_team()
    picks = resolve_loadout(team)
    assert picks == []


# --- resolve_loadout: unknown preset ---

def test_resolve_unknown_preset_returns_empty():
    team = _make_team(loadout="nonexistent_preset")
    picks = resolve_loadout(team)
    assert picks == []


# --- DraftEngine integration ---

@pytest.mark.asyncio
async def test_draft_engine_both_teams_loadout_skips_llm():
    from unittest.mock import AsyncMock
    from wargames.engine.draft import DraftEngine, DraftPool

    red_team = _make_team(loadout="aggressive")
    blue_team = _make_team(loadout="defensive")

    red_llm = AsyncMock()
    blue_llm = AsyncMock()
    pool = DraftPool.default()
    engine = DraftEngine(picks_per_team=3, style="snake")

    red_picks, blue_picks = await engine.run(
        pool, red_llm, blue_llm,
        red_settings=red_team, blue_settings=blue_team
    )

    # LLM should never be called when both teams use loadouts
    red_llm.chat.assert_not_called()
    blue_llm.chat.assert_not_called()
    assert len(red_picks) == 4
    assert len(blue_picks) == 4


@pytest.mark.asyncio
async def test_draft_engine_one_team_loadout_other_drafts_normally():
    from unittest.mock import AsyncMock
    from wargames.engine.draft import DraftEngine, DraftPool

    red_team = _make_team(loadout="aggressive")
    blue_team = _make_team()  # no loadout

    pool = DraftPool.default()
    available_names = [r.name for r in pool.available()]

    blue_llm = AsyncMock()
    blue_llm.chat.side_effect = [
        available_names[0],
        available_names[1],
        available_names[2],
    ]
    red_llm = AsyncMock()

    engine = DraftEngine(picks_per_team=3, style="snake")
    red_picks, blue_picks = await engine.run(
        pool, red_llm, blue_llm,
        red_settings=red_team, blue_settings=blue_team
    )

    # Red used loadout, so red LLM never called
    red_llm.chat.assert_not_called()
    # Blue drafted normally
    assert blue_llm.chat.call_count == 3
    # Red has 4 loadout picks (aggressive preset)
    assert len(red_picks) == 4
    assert len(blue_picks) == 3
