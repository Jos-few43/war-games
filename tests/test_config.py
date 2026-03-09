import os
import pytest
from pathlib import Path
from wargames.config import load_config, load_roster
from wargames.models import GameConfig, TeamSettings, TournamentConfig


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


def test_load_roster(tmp_path):
    roster = tmp_path / "roster.toml"
    roster.write_text(
        '[tournament]\n'
        'name = "test-tourney"\n'
        'rounds = 2\n'
        'games_per_match = 4\n'
        'game_rounds = 1\n'
        'turn_limit = 6\n'
        'score_threshold = 8\n'
        '\n'
        '[[models]]\n'
        'name = "model-a"\n'
        'endpoint = "http://localhost:8000/v1"\n'
        'model_name = "a"\n'
        '\n'
        '[[models]]\n'
        'name = "model-b"\n'
        'endpoint = "http://localhost:8001/v1"\n'
        'model_name = "b"\n'
        'api_key = "$TEST_ROSTER_KEY"\n'
    )
    os.environ["TEST_ROSTER_KEY"] = "secret-123"
    try:
        cfg = load_roster(roster)
        assert isinstance(cfg, TournamentConfig)
        assert cfg.name == "test-tourney"
        assert cfg.rounds == 2
        assert cfg.games_per_match == 4
        assert cfg.turn_limit == 6
        assert cfg.score_threshold == 8
        assert len(cfg.models) == 2
        assert cfg.models[0].name == "model-a"
        assert cfg.models[0].api_key == ""
        assert cfg.models[1].api_key == "secret-123"
    finally:
        del os.environ["TEST_ROSTER_KEY"]


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
