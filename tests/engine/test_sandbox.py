"""Tests for SandboxRunner and the `wargames sandbox` CLI command."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from wargames.models import (
    GameConfig, GameSettings, DraftSettings, DraftStyle,
    TeamsSettings, TeamSettings, CrawlerSettings,
)
from wargames.engine.sandbox import SandboxRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**team_overrides) -> GameConfig:
    """Return a minimal GameConfig suitable for sandbox tests."""
    team_defaults = dict(
        model="http://localhost:4002",
        model_name="test-model",
        temperature=0.7,
        timeout=30.0,
    )
    red_kw = {**team_defaults, "name": "Red", **team_overrides}
    blue_kw = {**team_defaults, "name": "Blue", **team_overrides}
    judge_kw = {**team_defaults, "name": "Judge", **team_overrides}

    return GameConfig(
        game=GameSettings(
            name="sandbox-test",
            rounds=1,
            turn_limit=2,
            score_threshold=10,
            phase_advance_score=5.0,
        ),
        draft=DraftSettings(picks_per_team=2, style=DraftStyle.SNAKE),
        teams=TeamsSettings(
            red=TeamSettings(**red_kw),
            blue=TeamSettings(**blue_kw),
            judge=TeamSettings(**judge_kw),
        ),
        crawler=CrawlerSettings(enabled=False, sources=[]),
    )


# ---------------------------------------------------------------------------
# Construction tests
# ---------------------------------------------------------------------------

def test_sandbox_runner_can_be_instantiated():
    """SandboxRunner should accept a GameConfig without error."""
    config = _make_config()
    runner = SandboxRunner(config)
    assert runner.config is config


def test_sandbox_runner_stores_config():
    """SandboxRunner.config should be the exact object passed in."""
    config = _make_config()
    runner = SandboxRunner(config)
    assert runner.config.game.name == "sandbox-test"
    assert runner.config.game.turn_limit == 2


# ---------------------------------------------------------------------------
# CLI parser tests
# ---------------------------------------------------------------------------

def test_parse_sandbox_command():
    """parse_args should recognise the 'sandbox' subcommand."""
    from wargames.cli import parse_args
    args = parse_args(["sandbox"])
    assert args.command == "sandbox"


def test_parse_sandbox_default_config():
    """sandbox --config should default to config/default.toml."""
    from wargames.cli import parse_args
    args = parse_args(["sandbox"])
    assert args.config == "config/default.toml"


def test_parse_sandbox_custom_config():
    """sandbox --config <path> should capture the path."""
    from wargames.cli import parse_args
    args = parse_args(["sandbox", "--config", "config/test-local.toml"])
    assert args.config == "config/test-local.toml"


def test_parse_sandbox_loadout_arg():
    """sandbox --loadout should capture the raw loadout string."""
    from wargames.cli import parse_args
    args = parse_args(["sandbox", "--loadout", "red=aggressive,blue=defensive"])
    assert args.loadout == "red=aggressive,blue=defensive"


def test_parse_sandbox_loadout_defaults_to_none():
    """sandbox without --loadout should have loadout=None."""
    from wargames.cli import parse_args
    args = parse_args(["sandbox"])
    assert args.loadout is None


# ---------------------------------------------------------------------------
# Loadout override parsing test (via CLI main)
# ---------------------------------------------------------------------------

def test_sandbox_cli_parses_loadout_overrides(capsys):
    """
    The CLI handler should split 'red=aggressive,blue=defensive' into a dict
    and pass it to SandboxRunner.run(). We verify the call reaches run() with
    the correct overrides without actually running an LLM.
    """
    from wargames.models import RoundResult, Phase, MatchOutcome

    mock_result = RoundResult(
        round_number=1,
        phase=Phase.PROMPT_INJECTION,
        outcome=MatchOutcome.RED_WIN,
        red_score=5,
        blue_score=2,
        blue_threshold=10,
        red_draft=[],
        blue_draft=[],
        attacks=[],
        defenses=[],
    )

    mock_runner = MagicMock()
    mock_runner.run = AsyncMock(return_value=mock_result)

    config = _make_config()

    with patch("wargames.cli.load_config", return_value=config), \
         patch("wargames.cli.SandboxRunner", return_value=mock_runner) as mock_cls:
        from wargames.cli import main
        main(["sandbox", "--config", "config/default.toml",
              "--loadout", "red=aggressive,blue=defensive"])

    # run() should have been called with parsed overrides dict
    mock_runner.run.assert_called_once_with(
        loadout_overrides={"red": "aggressive", "blue": "defensive"}
    )

    out = capsys.readouterr().out
    assert "red_win" in out or "RED_WIN" in out or "Outcome" in out


def test_sandbox_cli_no_loadout(capsys):
    """When --loadout is omitted, run() should be called with None."""
    from wargames.models import RoundResult, Phase, MatchOutcome

    mock_result = RoundResult(
        round_number=1,
        phase=Phase.PROMPT_INJECTION,
        outcome=MatchOutcome.BLUE_WIN,
        red_score=2,
        blue_score=5,
        blue_threshold=10,
        red_draft=[],
        blue_draft=[],
        attacks=[],
        defenses=[],
    )

    mock_runner = MagicMock()
    mock_runner.run = AsyncMock(return_value=mock_result)

    config = _make_config()

    with patch("wargames.cli.load_config", return_value=config), \
         patch("wargames.cli.SandboxRunner", return_value=mock_runner):
        from wargames.cli import main
        main(["sandbox", "--config", "config/default.toml"])

    mock_runner.run.assert_called_once_with(loadout_overrides=None)
