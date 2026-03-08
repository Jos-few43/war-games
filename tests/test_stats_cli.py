"""Tests for `wargames stats` CLI command and CostsSettings model."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wargames.cli import parse_args
from wargames.models import CostsSettings, GameConfig


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def test_parse_stats_command():
    args = parse_args(["stats"])
    assert args.command == "stats"


# ---------------------------------------------------------------------------
# CostsSettings model
# ---------------------------------------------------------------------------

def test_costs_settings_defaults_to_empty_rates():
    cs = CostsSettings()
    assert cs.rates == {}


def test_costs_settings_stores_rates():
    cs = CostsSettings(rates={"model": 0.001})
    assert cs.rates == {"model": 0.001}


def test_costs_settings_multiple_rates():
    rates = {"llama-3-70b": 0.00059, "qwen3:4b": 0.0}
    cs = CostsSettings(rates=rates)
    assert cs.rates["llama-3-70b"] == 0.00059
    assert cs.rates["qwen3:4b"] == 0.0


# ---------------------------------------------------------------------------
# GameConfig with costs field
# ---------------------------------------------------------------------------

def _minimal_game_config_dict():
    return {
        "game": {
            "name": "test-game",
            "rounds": 3,
            "turn_limit": 5,
            "score_threshold": 10,
            "phase_advance_score": 5.0,
        },
        "draft": {"picks_per_team": 3, "style": "snake"},
        "teams": {
            "red": {
                "name": "Red",
                "model": "gpt-4o",
                "model_name": "gpt-4o",
                "temperature": 0.7,
            },
            "blue": {
                "name": "Blue",
                "model": "claude-sonnet-4-5",
                "model_name": "claude-sonnet-4-5",
                "temperature": 0.7,
            },
            "judge": {
                "name": "Judge",
                "model": "gpt-4o",
                "model_name": "gpt-4o",
                "temperature": 0.0,
            },
        },
    }


def test_game_config_with_costs_field():
    data = _minimal_game_config_dict()
    data["costs"] = {"rates": {"llama-3-70b": 0.00059}}
    cfg = GameConfig.model_validate(data)
    assert cfg.costs.rates["llama-3-70b"] == 0.00059


def test_game_config_without_costs_defaults_to_empty():
    data = _minimal_game_config_dict()
    cfg = GameConfig.model_validate(data)
    assert isinstance(cfg.costs, CostsSettings)
    assert cfg.costs.rates == {}


# ---------------------------------------------------------------------------
# Stats command output
# ---------------------------------------------------------------------------

def test_stats_prints_season_section(tmp_path, capsys):
    mock_db = MagicMock()
    mock_db.init = AsyncMock()
    mock_db.get_season_stats = AsyncMock(return_value={
        "total_rounds": 10,
        "red_wins": 6,
        "blue_wins": 3,
        "auto_wins": 1,
    })
    mock_db.get_all_ratings = AsyncMock(return_value=[])
    mock_db.get_token_totals = AsyncMock(return_value={
        "prompt_tokens": 5000,
        "completion_tokens": 2000,
        "cost": 0.0042,
    })
    mock_db.close = AsyncMock()

    with patch("wargames.cli.Database", return_value=mock_db), \
         patch("wargames.cli._default_db_path", return_value=tmp_path / "test.db"):
        from wargames.cli import main
        main(["stats"])

    out = capsys.readouterr().out
    assert "=== Season Stats ===" in out
    assert "10" in out   # total rounds
    assert "Red wins" in out
    assert "Blue wins" in out
    assert "Auto wins" in out


def test_stats_prints_model_ratings_section(tmp_path, capsys):
    mock_ratings = [
        {
            "model_name": "gpt-4o",
            "rating": 1532.5,
            "wins": 6,
            "losses": 3,
            "draws": 1,
            "last_played": "2026-03-01",
        }
    ]
    mock_db = MagicMock()
    mock_db.init = AsyncMock()
    mock_db.get_season_stats = AsyncMock(return_value={
        "total_rounds": 10,
        "red_wins": 6,
        "blue_wins": 3,
        "auto_wins": 1,
    })
    mock_db.get_all_ratings = AsyncMock(return_value=mock_ratings)
    mock_db.get_token_totals = AsyncMock(return_value={
        "prompt_tokens": 5000,
        "completion_tokens": 2000,
        "cost": 0.0042,
    })
    mock_db.close = AsyncMock()

    with patch("wargames.cli.Database", return_value=mock_db), \
         patch("wargames.cli._default_db_path", return_value=tmp_path / "test.db"):
        from wargames.cli import main
        main(["stats"])

    out = capsys.readouterr().out
    assert "=== Model Ratings ===" in out
    assert "gpt-4o" in out
    assert "1532" in out


def test_stats_no_ratings_shows_message(tmp_path, capsys):
    mock_db = MagicMock()
    mock_db.init = AsyncMock()
    mock_db.get_season_stats = AsyncMock(return_value={
        "total_rounds": 0,
        "red_wins": 0,
        "blue_wins": 0,
        "auto_wins": 0,
    })
    mock_db.get_all_ratings = AsyncMock(return_value=[])
    mock_db.get_token_totals = AsyncMock(return_value={
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cost": 0.0,
    })
    mock_db.close = AsyncMock()

    with patch("wargames.cli.Database", return_value=mock_db), \
         patch("wargames.cli._default_db_path", return_value=tmp_path / "test.db"):
        from wargames.cli import main
        main(["stats"])

    out = capsys.readouterr().out
    assert "No ratings yet." in out


def test_stats_prints_token_usage_section(tmp_path, capsys):
    mock_db = MagicMock()
    mock_db.init = AsyncMock()
    mock_db.get_season_stats = AsyncMock(return_value={
        "total_rounds": 4,
        "red_wins": 2,
        "blue_wins": 2,
        "auto_wins": 0,
    })
    mock_db.get_all_ratings = AsyncMock(return_value=[])
    mock_db.get_token_totals = AsyncMock(return_value={
        "prompt_tokens": 8000,
        "completion_tokens": 4000,
        "cost": 0.0096,
    })
    mock_db.close = AsyncMock()

    with patch("wargames.cli.Database", return_value=mock_db), \
         patch("wargames.cli._default_db_path", return_value=tmp_path / "test.db"):
        from wargames.cli import main
        main(["stats"])

    out = capsys.readouterr().out
    assert "=== Token Usage ===" in out
    assert "8,000" in out   # prompt tokens formatted with comma
    assert "4,000" in out   # completion tokens
    assert "0.0096" in out  # total cost
    assert "Avg tokens / round" in out
    assert "Avg cost / round" in out
