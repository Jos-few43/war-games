import pytest
from pathlib import Path
from wargames.config import load_config
from wargames.models import GameConfig


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
