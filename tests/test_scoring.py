import pytest
from wargames.models import (
    ScoringProfile, AttackPoints, DefenseRewards, WinConditions,
    PhaseAdvanceSettings, GameConfig,
)


def test_scoring_profile_defaults():
    """ScoringProfile should have V4-equivalent defaults."""
    profile = ScoringProfile()
    assert profile.attack_points.low == 1
    assert profile.attack_points.medium == 3
    assert profile.attack_points.high == 5
    assert profile.attack_points.critical == 8
    assert profile.defense_rewards.full_block_threshold == 0.7
    assert profile.defense_rewards.partial_block_threshold == 0.3
    assert profile.defense_rewards.full_block_points == 2
    assert profile.defense_rewards.partial_block_points == 1
    assert profile.defense_rewards.critical_neutralize_threshold == 0.5
    assert profile.defense_rewards.critical_neutralize_points == 5
    assert profile.win_conditions.score_threshold == 10
    assert profile.phase_advance.min_rounds == 3
    assert profile.phase_advance.min_avg_score == 7.5


def test_scoring_profile_custom_values():
    """ScoringProfile accepts custom values."""
    profile = ScoringProfile(
        attack_points=AttackPoints(low=2, medium=4, high=6, critical=10),
        defense_rewards=DefenseRewards(full_block_points=3),
    )
    assert profile.attack_points.low == 2
    assert profile.defense_rewards.full_block_points == 3
    # Other fields keep defaults
    assert profile.defense_rewards.partial_block_points == 1


def test_game_config_has_scoring():
    """GameConfig should accept an optional scoring field."""
    from wargames.config import load_config
    from pathlib import Path
    config = load_config(Path("config/default.toml"))
    assert hasattr(config, "scoring")
    assert isinstance(config.scoring, ScoringProfile)


from wargames.config import load_config, load_scoring_preset
from pathlib import Path


def test_load_balanced_preset():
    """Balanced preset matches V4 defaults."""
    profile = load_scoring_preset("balanced")
    assert profile.attack_points.critical == 8
    assert profile.defense_rewards.full_block_points == 2
    assert profile.phase_advance.min_rounds == 3


def test_load_red_favored_preset():
    """Red-favored preset has higher attack points and lower thresholds."""
    profile = load_scoring_preset("red-favored")
    assert profile.attack_points.critical >= 10
    assert profile.defense_rewards.full_block_threshold > 0.7


def test_load_blue_favored_preset():
    """Blue-favored preset has higher defense rewards."""
    profile = load_scoring_preset("blue-favored")
    assert profile.defense_rewards.full_block_points >= 3


def test_load_config_with_scoring_section(tmp_path):
    """Config TOML with [scoring] section overrides defaults."""
    toml_content = '''
[game]
name = "test"
rounds = 5
turn_limit = 4
score_threshold = 10
phase_advance_score = 5.0

[draft]
picks_per_team = 3
style = "snake"

[teams.red]
name = "Red"
model = "http://localhost:4000/v1"
model_name = "test"
temperature = 0.5

[teams.blue]
name = "Blue"
model = "http://localhost:4000/v1"
model_name = "test"
temperature = 0.5

[teams.judge]
name = "Judge"
model = "http://localhost:4000/v1"
model_name = "test"
temperature = 0.2

[scoring]
profile = "balanced"

[scoring.attack_points]
critical = 12

[scoring.defense_rewards]
full_block_points = 4
'''
    config_file = tmp_path / "test.toml"
    config_file.write_text(toml_content)
    config = load_config(config_file)
    assert config.scoring.attack_points.critical == 12
    assert config.scoring.defense_rewards.full_block_points == 4
    # Non-overridden values come from balanced preset
    assert config.scoring.attack_points.low == 1


def test_load_config_without_scoring_uses_defaults():
    """Existing configs without [scoring] get V4 defaults."""
    config = load_config(Path("config/default.toml"))
    assert config.scoring.attack_points.critical == 8
