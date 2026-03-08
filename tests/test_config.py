import pytest
from pathlib import Path
from wargames.config import load_config
from wargames.models import GameConfig, TeamSettings


def test_load_default_config():
    config = load_config(Path("config/default.toml"))
    assert isinstance(config, GameConfig)
    assert config.game.name == "season-01"
    assert config.game.rounds == 50
    assert config.game.turn_limit == 12
    assert config.game.score_threshold == 10
    assert config.draft.picks_per_team == 5
    assert config.draft.style == "snake"
    assert config.teams.red.name == "Red Team"
    assert config.teams.blue.name == "Blue Team"
    assert config.teams.judge.model_name == "claude-sonnet-4-5"


def test_team_settings_fallback_fields():
    ts = TeamSettings(
        name="Test",
        model="http://cloud:4002",
        model_name="openrouter/auto",
        temperature=0.7,
        fallback_model="http://localhost:11434",
        fallback_model_name="qwen3:4b",
        fallback_api_key="",
    )
    assert ts.fallback_model == "http://localhost:11434"
    assert ts.fallback_model_name == "qwen3:4b"
    assert ts.fallback_api_key == ""


def test_team_settings_fallback_defaults():
    ts = TeamSettings(
        name="Test",
        model="http://cloud:4002",
        model_name="openrouter/auto",
        temperature=0.7,
    )
    assert ts.fallback_model == ""
    assert ts.fallback_model_name == ""


def test_team_settings_fallback_env_var_resolution():
    import os
    os.environ["TEST_FALLBACK_KEY"] = "fb-secret"
    ts = TeamSettings(
        name="Test",
        model="http://cloud:4002",
        model_name="openrouter/auto",
        temperature=0.7,
        fallback_api_key="$TEST_FALLBACK_KEY",
    )
    assert ts.fallback_api_key == "fb-secret"
    del os.environ["TEST_FALLBACK_KEY"]


def test_config_validates_score_threshold():
    with pytest.raises(ValueError):
        GameConfig.model_validate({
            "game": {"name": "t", "rounds": 1, "turn_limit": 1,
                     "score_threshold": -1, "phase_advance_score": 1},
            "draft": {"picks_per_team": 5, "style": "snake"},
            "teams": {
                "red": {"name": "R", "model": "http://x", "model_name": "m", "temperature": 0.5},
                "blue": {"name": "B", "model": "http://x", "model_name": "m", "temperature": 0.5},
                "judge": {"name": "J", "model": "http://x", "model_name": "m", "temperature": 0.2},
            },
            "crawler": {"enabled": False, "sources": [], "refresh_interval": "1h"},
            "output": {
                "vault": {"enabled": False, "path": "/tmp"},
                "database": {"path": "/tmp/test.db"},
            },
        })
