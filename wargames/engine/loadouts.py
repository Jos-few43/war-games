from __future__ import annotations

from wargames.models import DraftPick

PRESETS: dict[str, list[str]] = {
    "aggressive": ["fuzzer", "sqli_kit", "prompt_injector", "priv_esc_toolkit"],
    "defensive": ["waf_rules", "rate_limiter", "input_sanitizer", "sandboxing"],
    "balanced": ["fuzzer", "waf_rules", "port_scanner", "input_sanitizer"],
    "recon": ["port_scanner", "code_analyzer", "network_mapper", "cve_database"],
}


def resolve_loadout(team, team_name: str = "", loadout: str = "", loadout_custom: list[str] | None = None) -> list[DraftPick]:
    """
    Resolve a team's loadout into DraftPick objects.

    Priority: custom loadout > named preset > empty (normal draft).

    Args:
        team: TeamSettings instance with .loadout and .loadout_custom fields.
        team_name: The team identifier string ("red" or "blue"). Falls back to team.name.
        loadout: Override named preset (if not using team object).
        loadout_custom: Override custom list (if not using team object).

    Returns:
        List of DraftPick objects with round=0 and resource_category="loadout",
        or empty list if no loadout is configured or preset is unknown.
    """
    # Read from team object if not overridden
    effective_loadout = loadout or getattr(team, "loadout", "")
    effective_custom = loadout_custom if loadout_custom is not None else getattr(team, "loadout_custom", [])
    effective_team_name = team_name or getattr(team, "name", "")

    # Custom list takes priority
    if effective_custom:
        resources = effective_custom
    elif effective_loadout:
        resources = PRESETS.get(effective_loadout)
        if resources is None:
            return []
    else:
        return []

    return [
        DraftPick(
            round=0,
            team=effective_team_name,
            resource_name=name,
            resource_category="loadout",
        )
        for name in resources
    ]
