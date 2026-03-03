import pytest
import json
from pathlib import Path
from unittest.mock import patch
from wargames.config import load_config
from wargames.engine.game import GameEngine
from wargames.models import Phase
from wargames.output.vault import VaultWriter


@pytest.mark.asyncio
async def test_full_round_pipeline(tmp_path):
    """End-to-end: config -> init -> draft -> match -> debrief -> DB -> vault."""
    config = load_config(Path("config/default.toml"))
    config.game.rounds = 1
    config.game.turn_limit = 2
    config.output.database.path = str(tmp_path / "test.db")
    config.output.vault.enabled = True
    config.output.vault.path = str(tmp_path / "vault")

    # Draft order for picks_per_team=5, snake:
    # Round 0 (even): R, B
    # Round 1 (odd):  B, R
    # Round 2 (even): R, B
    # Round 3 (odd):  B, R
    # Round 4 (even): R, B
    # => picks: R, B, B, R, R, B, B, R, R, B
    #
    # Call sequence (all three LLMClient instances share the same patched method):
    #   0:  red  draft pick 1  -> "fuzzer"
    #   1:  blue draft pick 2  -> "waf_rules"
    #   2:  blue draft pick 3  -> "sqli_kit"   (blue picks again in snake round 1)
    #   3:  red  draft pick 4  -> "input_sanitizer"
    #   4:  red  draft pick 5  -> "cve_database"
    #   5:  blue draft pick 6  -> "logging_alerting"
    #   6:  blue draft pick 7  -> "port_scanner"
    #   7:  red  draft pick 8  -> "sandboxing"
    #   8:  red  draft pick 9  -> "priv_esc_toolkit"
    #   9:  blue draft pick 10 -> "rate_limiter"
    #  10:  red  attack (turn 1)
    #  11:  judge evaluate_attack (turn 1)  -> JSON
    #  12:  blue defend (turn 1)
    #  13:  judge evaluate_defense (turn 1) -> JSON
    #  14:  red  attack (turn 2)
    #  15:  judge evaluate_attack (turn 2)  -> JSON
    #  16:  blue defend (turn 2)
    #  17:  judge evaluate_defense (turn 2) -> JSON
    #  18:  red  write_debrief
    #  19:  blue write_debrief

    responses = [
        # Draft picks (indices 0-9)
        "fuzzer",
        "waf_rules",
        "sqli_kit",
        "input_sanitizer",
        "cve_database",
        "logging_alerting",
        "port_scanner",
        "sandboxing",
        "priv_esc_toolkit",
        "rate_limiter",
        # Turn 1
        "SQL injection on /api/users with ' OR 1=1--",  # red attack
        json.dumps({                                     # judge evaluate_attack
            "valid": True, "severity": "high", "points": 5, "auto_win": False,
            "reasoning": "SQLi worked",
        }),
        "Deployed parameterized queries",               # blue defend
        json.dumps({                                     # judge evaluate_defense
            "blocked": False, "reasoning": "Defense was too late",
        }),
        # Turn 2
        "Path traversal on /uploads with ../../etc/passwd",  # red attack
        json.dumps({                                          # judge evaluate_attack
            "valid": True, "severity": "medium", "points": 3, "auto_win": False,
            "reasoning": "Partial path traversal",
        }),
        "Added path validation",                             # blue defend
        json.dumps({                                         # judge evaluate_defense
            "blocked": True, "reasoning": "Path validation caught it",
        }),
        # Debriefs
        "# Red Debrief\n- SQLi effective\n- Path traversal partially worked",
        "# Blue Debrief\n- Missed SQLi\n- Caught path traversal",
    ]

    call_count = 0

    async def mock_chat(messages, system=None):
        nonlocal call_count
        idx = call_count
        call_count += 1
        if idx < len(responses):
            return responses[idx]
        return "fallback response"

    with patch("wargames.llm.client.LLMClient.chat", side_effect=mock_chat):
        engine = GameEngine(config)
        await engine.init()

        vault_writer = VaultWriter(Path(tmp_path / "vault"))

        results = []
        async for result in engine.run():
            results.append(result)
            vault_writer.write_round(result)

        await engine.cleanup()

    # Verify result structure
    assert len(results) == 1
    r = results[0]
    assert r.round_number == 1
    assert r.phase == Phase.PROMPT_INJECTION
    assert len(r.attacks) == 2
    assert len(r.defenses) == 2
    assert r.red_debrief != ""
    assert r.blue_debrief != ""

    # Verify vault files were created
    vault = tmp_path / "vault"
    assert (vault / "rounds" / "round-001.md").exists()
    assert (vault / "debriefs" / "R001-red-debrief.md").exists()
    assert (vault / "debriefs" / "R001-blue-debrief.md").exists()

    # Verify DB has data (open a fresh connection since engine.cleanup() closed it)
    from wargames.output.db import Database
    db = Database(Path(tmp_path / "test.db"))
    await db.init()
    stats = await db.get_season_stats()
    assert stats["total_rounds"] == 1
    loaded = await db.get_round(1)
    assert loaded.round_number == 1
    await db.close()
