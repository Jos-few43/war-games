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
