"""
Tests for the scoring engine — ScoringProfile loading, preset validation,
and RoundEngine profile integration.

Covers:
- ScoringProfile defaults and custom values
- Loading all 3 preset TOML files and validating their values
- RoundEngine uses profile values instead of hardcoded constants
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock

from wargames.models import (
    ScoringProfile,
    AttackPoints,
    DefenseRewards,
    WinConditions,
    PhaseAdvanceSettings,
    Phase,
    AttackResult,
    DefenseResult,
    Severity,
    BugReport,
    Patch,
    Domain,
    DraftPick,
)
from wargames.config import load_scoring_preset, load_config
from wargames.engine.round import RoundEngine


# ---------------------------------------------------------------------------
# ScoringProfile model tests
# ---------------------------------------------------------------------------


def test_scoring_profile_has_v4_defaults():
    """ScoringProfile default values match the V4 hardcoded baseline."""
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


def test_scoring_profile_accepts_custom_values():
    """ScoringProfile fields can be overridden; unset fields keep defaults."""
    profile = ScoringProfile(
        attack_points=AttackPoints(low=2, medium=4, high=6, critical=10),
        defense_rewards=DefenseRewards(full_block_points=3),
    )
    assert profile.attack_points.low == 2
    assert profile.attack_points.critical == 10
    assert profile.defense_rewards.full_block_points == 3
    # Unset sub-fields keep their defaults
    assert profile.defense_rewards.partial_block_points == 1
    assert profile.defense_rewards.full_block_threshold == 0.7


# ---------------------------------------------------------------------------
# Preset loading tests
# ---------------------------------------------------------------------------


def test_balanced_preset_matches_v4_defaults():
    """Balanced preset exactly mirrors V4 hardcoded values."""
    profile = load_scoring_preset("balanced")
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


def test_red_favored_preset_higher_attack_points():
    """Red-favored preset has higher attack points than balanced."""
    balanced = load_scoring_preset("balanced")
    red = load_scoring_preset("red-favored")

    assert red.attack_points.low >= balanced.attack_points.low
    assert red.attack_points.medium >= balanced.attack_points.medium
    assert red.attack_points.high >= balanced.attack_points.high
    assert red.attack_points.critical >= 10  # At least 10 per spec


def test_red_favored_preset_harder_defense_thresholds():
    """Red-favored preset makes it harder for Blue to earn defense points."""
    balanced = load_scoring_preset("balanced")
    red = load_scoring_preset("red-favored")

    # Higher full_block_threshold = harder to earn full block points
    assert red.defense_rewards.full_block_threshold > balanced.defense_rewards.full_block_threshold
    # Lower defense rewards
    assert red.defense_rewards.full_block_points <= balanced.defense_rewards.full_block_points


def test_red_favored_preset_validates():
    """Red-favored preset deserializes into a valid ScoringProfile."""
    profile = load_scoring_preset("red-favored")
    assert isinstance(profile, ScoringProfile)
    assert 0.0 < profile.defense_rewards.partial_block_threshold < profile.defense_rewards.full_block_threshold
    assert profile.attack_points.low > 0
    assert profile.phase_advance.min_rounds >= 1


def test_blue_favored_preset_higher_defense_rewards():
    """Blue-favored preset grants higher defense rewards than balanced."""
    balanced = load_scoring_preset("balanced")
    blue = load_scoring_preset("blue-favored")

    assert blue.defense_rewards.full_block_points >= 3  # Per spec
    assert blue.defense_rewards.full_block_points > balanced.defense_rewards.full_block_points
    assert blue.defense_rewards.partial_block_points > balanced.defense_rewards.partial_block_points


def test_blue_favored_preset_lower_attack_points():
    """Blue-favored preset reduces red team attack points."""
    balanced = load_scoring_preset("balanced")
    blue = load_scoring_preset("blue-favored")

    assert blue.attack_points.critical < balanced.attack_points.critical
    assert blue.attack_points.high < balanced.attack_points.high


def test_blue_favored_preset_validates():
    """Blue-favored preset deserializes into a valid ScoringProfile."""
    profile = load_scoring_preset("blue-favored")
    assert isinstance(profile, ScoringProfile)
    assert 0.0 < profile.defense_rewards.partial_block_threshold < profile.defense_rewards.full_block_threshold
    assert profile.win_conditions.score_threshold > 0
    assert profile.phase_advance.min_avg_score > 0.0


def test_unknown_preset_raises():
    """Requesting a preset that does not exist raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="Scoring preset not found"):
        load_scoring_preset("nonexistent-preset")


# ---------------------------------------------------------------------------
# Config loading with [scoring] section
# ---------------------------------------------------------------------------


def test_default_config_loads_balanced_profile():
    """default.toml loads the balanced preset into GameConfig.scoring."""
    config = load_config(Path("config/default.toml"))
    assert isinstance(config.scoring, ScoringProfile)
    assert config.scoring.attack_points.critical == 8
    assert config.scoring.defense_rewards.full_block_points == 2
    assert config.scoring.phase_advance.min_rounds == 3


def test_config_scoring_section_overrides_preset(tmp_path):
    """Inline [scoring.attack_points] overrides merge on top of the preset."""
    toml = """\
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
critical = 15

[scoring.defense_rewards]
full_block_points = 6
"""
    cfg_file = tmp_path / "override.toml"
    cfg_file.write_text(toml)
    config = load_config(cfg_file)

    # Overridden values
    assert config.scoring.attack_points.critical == 15
    assert config.scoring.defense_rewards.full_block_points == 6
    # Non-overridden values come from balanced preset
    assert config.scoring.attack_points.low == 1
    assert config.scoring.defense_rewards.partial_block_points == 1


def test_config_without_scoring_section_uses_defaults(tmp_path):
    """Config with no [scoring] section defaults to balanced-equivalent profile."""
    toml = """\
[game]
name = "bare"
rounds = 3
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
"""
    cfg_file = tmp_path / "bare.toml"
    cfg_file.write_text(toml)
    config = load_config(cfg_file)

    assert config.scoring.attack_points.critical == 8
    assert config.scoring.defense_rewards.full_block_points == 2
    assert config.scoring.phase_advance.min_rounds == 3


# ---------------------------------------------------------------------------
# RoundEngine integration — uses profile instead of hardcoded values
# ---------------------------------------------------------------------------


def _make_round_engine(mock_red, mock_blue, mock_judge, mock_draft, mock_db,
                       turn_limit=1, score_threshold=100,
                       scoring: ScoringProfile | None = None) -> RoundEngine:
    mock_red.llm = AsyncMock()
    mock_blue.llm = AsyncMock()
    engine = RoundEngine(
        red=mock_red, blue=mock_blue, judge=mock_judge,
        draft_engine=mock_draft, db=mock_db,
        turn_limit=turn_limit, score_threshold=score_threshold,
        scoring=scoring,
    )
    return engine


def _setup_draft(mock_draft, red_picks=None, blue_picks=None):
    mock_draft.run.return_value = (
        red_picks or [DraftPick(round=1, team="red", resource_name="fuzzer", resource_category="offensive")],
        blue_picks or [DraftPick(round=1, team="blue", resource_name="waf_rules", resource_category="defensive")],
    )


def _setup_bug_patch(mock_red, mock_blue):
    mock_red.generate_bug_report.return_value = BugReport(
        round_number=0, title="SQLi", severity=Severity.HIGH, domain=Domain.CODE_VULN,
        target="/api/users", steps_to_reproduce="", proof_of_concept="", impact="",
    )
    mock_blue.generate_patch.return_value = Patch(
        round_number=0, title="Fix", fixes="", strategy="", changes="", verification="",
    )


@pytest.mark.asyncio
async def test_round_engine_default_scoring_matches_balanced():
    """RoundEngine with no explicit profile applies balanced-equivalent scoring."""
    mock_red, mock_blue, mock_judge = AsyncMock(), AsyncMock(), AsyncMock()
    mock_draft, mock_db = AsyncMock(), AsyncMock()
    _setup_draft(mock_draft)
    _setup_bug_patch(mock_red, mock_blue)

    mock_red.attack.return_value = "Test attack"
    mock_judge.evaluate_attack.return_value = (
        AttackResult(turn=0, description="", success=True, severity=Severity.MEDIUM, points=3, auto_win=False),
        "A moderate attack was attempted.",
    )
    # Effectiveness 0.8 — full block under default (0.7) threshold
    mock_judge.evaluate_defense.return_value = (True, 0.8, "Blocked", 0.8)
    mock_blue.defend.return_value = "Defense"
    mock_red.write_debrief.return_value = "Red"
    mock_blue.write_debrief.return_value = "Blue"

    engine = _make_round_engine(mock_red, mock_blue, mock_judge, mock_draft, mock_db)
    result = await engine.play(round_number=1, phase=Phase.PROMPT_INJECTION)

    # Default full block = 2 points
    assert result.blue_score == 2
    assert result.defenses[0].points_earned == 2


@pytest.mark.asyncio
async def test_round_engine_custom_full_block_threshold_and_points():
    """Custom full_block_threshold and full_block_points are used instead of hardcoded."""
    mock_red, mock_blue, mock_judge = AsyncMock(), AsyncMock(), AsyncMock()
    mock_draft, mock_db = AsyncMock(), AsyncMock()
    _setup_draft(mock_draft)
    _setup_bug_patch(mock_red, mock_blue)

    mock_red.attack.return_value = "Attack"
    mock_judge.evaluate_attack.return_value = (
        AttackResult(turn=0, description="", success=True, severity=Severity.MEDIUM, points=3, auto_win=False),
        "A moderate attack.",
    )
    # Effectiveness 0.5 — between default partial (0.3) and full (0.7)
    # With custom profile: full_block_threshold=0.4 → 0.5 qualifies as full block
    mock_judge.evaluate_defense.return_value = (True, 0.5, "Good block", 0.8)
    mock_blue.defend.return_value = "Defense"
    mock_red.write_debrief.return_value = "Red"
    mock_blue.write_debrief.return_value = "Blue"

    custom = ScoringProfile(
        defense_rewards=DefenseRewards(full_block_threshold=0.4, full_block_points=7),
    )
    engine = _make_round_engine(mock_red, mock_blue, mock_judge, mock_draft, mock_db, scoring=custom)
    result = await engine.play(round_number=1, phase=Phase.PROMPT_INJECTION)

    assert result.blue_score == 7
    assert result.defenses[0].points_earned == 7


@pytest.mark.asyncio
async def test_round_engine_custom_partial_block_points():
    """Custom partial_block_points replace the hardcoded value."""
    mock_red, mock_blue, mock_judge = AsyncMock(), AsyncMock(), AsyncMock()
    mock_draft, mock_db = AsyncMock(), AsyncMock()
    _setup_draft(mock_draft)
    _setup_bug_patch(mock_red, mock_blue)

    mock_red.attack.return_value = "Attack"
    mock_judge.evaluate_attack.return_value = (
        AttackResult(turn=0, description="", success=True, severity=Severity.LOW, points=1, auto_win=False),
        "A minor probe was detected.",
    )
    # Effectiveness 0.5 — partial block under default thresholds
    mock_judge.evaluate_defense.return_value = (False, 0.5, "Partial", 0.8)
    mock_blue.defend.return_value = "Partial defense"
    mock_red.write_debrief.return_value = "Red"
    mock_blue.write_debrief.return_value = "Blue"

    custom = ScoringProfile(
        defense_rewards=DefenseRewards(partial_block_points=4),
    )
    engine = _make_round_engine(mock_red, mock_blue, mock_judge, mock_draft, mock_db, scoring=custom)
    result = await engine.play(round_number=1, phase=Phase.PROMPT_INJECTION)

    assert result.blue_score == 4
    assert result.defenses[0].points_earned == 4


@pytest.mark.asyncio
async def test_round_engine_custom_critical_neutralize_points():
    """Custom critical_neutralize_points replace the hardcoded 5."""
    mock_red, mock_blue, mock_judge = AsyncMock(), AsyncMock(), AsyncMock()
    mock_draft, mock_db = AsyncMock(), AsyncMock()
    _setup_draft(mock_draft, red_picks=[], blue_picks=[])
    _setup_bug_patch(mock_red, mock_blue)

    mock_red.attack.return_value = "Kernel exploit"
    mock_judge.evaluate_attack.return_value = (
        AttackResult(turn=0, description="", success=True, severity=Severity.CRITICAL, points=8, auto_win=True),
        "Critical attack detected.",
    )
    mock_blue.defend.return_value = "Containment"
    # Effectiveness 0.7 — above default critical_neutralize_threshold (0.5)
    mock_judge.evaluate_defense.return_value = (True, 0.7, "Neutralized", 0.8)
    mock_red.write_debrief.return_value = "Red"
    mock_blue.write_debrief.return_value = "Blue"

    custom = ScoringProfile(
        defense_rewards=DefenseRewards(critical_neutralize_points=12),
    )
    engine = _make_round_engine(mock_red, mock_blue, mock_judge, mock_draft, mock_db, scoring=custom)
    result = await engine.play(round_number=1, phase=Phase.PROMPT_INJECTION)

    assert result.blue_score == 12
    assert result.defenses[0].points_earned == 12


@pytest.mark.asyncio
async def test_round_engine_custom_critical_neutralize_threshold():
    """Custom critical_neutralize_threshold controls when Blue neutralizes a critical attack."""
    mock_red, mock_blue, mock_judge = AsyncMock(), AsyncMock(), AsyncMock()
    mock_draft, mock_db = AsyncMock(), AsyncMock()
    _setup_draft(mock_draft, red_picks=[], blue_picks=[])
    _setup_bug_patch(mock_red, mock_blue)

    mock_red.attack.return_value = "Critical exploit"
    mock_judge.evaluate_attack.return_value = (
        AttackResult(turn=0, description="", success=True, severity=Severity.CRITICAL, points=8, auto_win=True),
        "Critical system attack.",
    )
    mock_blue.defend.return_value = "Response"
    # Effectiveness 0.4 — below default threshold (0.5) → critical win
    # With custom threshold=0.3 → 0.4 >= 0.3 → neutralized
    mock_judge.evaluate_defense.return_value = (True, 0.4, "Barely neutralized", 0.8)
    mock_red.write_debrief.return_value = "Red"
    mock_blue.write_debrief.return_value = "Blue"

    custom = ScoringProfile(
        defense_rewards=DefenseRewards(critical_neutralize_threshold=0.3, critical_neutralize_points=3),
    )
    engine = _make_round_engine(mock_red, mock_blue, mock_judge, mock_draft, mock_db, scoring=custom)
    result = await engine.play(round_number=1, phase=Phase.PROMPT_INJECTION)

    # Should be neutralized (not critical win) because 0.4 >= 0.3
    from wargames.models import MatchOutcome
    assert result.outcome != MatchOutcome.RED_CRITICAL_WIN
    assert result.blue_score == 3


@pytest.mark.asyncio
async def test_round_engine_assigned_profile_overrides_constructor_profile():
    """Assigning engine.scoring after construction takes effect on the next play() call."""
    mock_red, mock_blue, mock_judge = AsyncMock(), AsyncMock(), AsyncMock()
    mock_draft, mock_db = AsyncMock(), AsyncMock()
    _setup_draft(mock_draft)
    _setup_bug_patch(mock_red, mock_blue)

    mock_red.attack.return_value = "Attack"
    mock_judge.evaluate_attack.return_value = (
        AttackResult(turn=0, description="", success=True, severity=Severity.MEDIUM, points=3, auto_win=False),
        "A moderate attack.",
    )
    mock_judge.evaluate_defense.return_value = (True, 0.8, "Full block", 0.8)
    mock_blue.defend.return_value = "Defense"
    mock_red.write_debrief.return_value = "Red"
    mock_blue.write_debrief.return_value = "Blue"

    engine = _make_round_engine(mock_red, mock_blue, mock_judge, mock_draft, mock_db)
    # Override the profile via attribute assignment
    engine.scoring = ScoringProfile(
        defense_rewards=DefenseRewards(full_block_points=9),
    )
    result = await engine.play(round_number=1, phase=Phase.PROMPT_INJECTION)

    assert result.blue_score == 9
    assert result.defenses[0].points_earned == 9


@pytest.mark.asyncio
async def test_red_favored_preset_lowers_blue_defense_reward():
    """Using the red-favored preset in a RoundEngine gives Blue fewer defense points."""
    mock_red, mock_blue, mock_judge = AsyncMock(), AsyncMock(), AsyncMock()
    mock_draft, mock_db = AsyncMock(), AsyncMock()
    _setup_draft(mock_draft)
    _setup_bug_patch(mock_red, mock_blue)

    mock_red.attack.return_value = "Attack"
    mock_judge.evaluate_attack.return_value = (
        AttackResult(turn=0, description="", success=True, severity=Severity.MEDIUM, points=3, auto_win=False),
        "Moderate attack.",
    )
    # Effectiveness 0.75 — full block under balanced (0.7), but red-favored threshold is 0.8
    # So under red-favored: 0.75 is a partial block, not a full block
    mock_judge.evaluate_defense.return_value = (True, 0.75, "Decent block", 0.8)
    mock_blue.defend.return_value = "Defense"
    mock_red.write_debrief.return_value = "Red"
    mock_blue.write_debrief.return_value = "Blue"

    red_profile = load_scoring_preset("red-favored")
    engine = _make_round_engine(
        mock_red, mock_blue, mock_judge, mock_draft, mock_db,
        scoring=red_profile,
    )
    result = await engine.play(round_number=1, phase=Phase.PROMPT_INJECTION)

    # 0.75 < 0.8 (red-favored full_block_threshold) → partial block
    # partial_block_points for red-favored = 0
    assert result.blue_score == 0


@pytest.mark.asyncio
async def test_blue_favored_preset_increases_defense_reward():
    """Using the blue-favored preset in a RoundEngine gives Blue more defense points."""
    mock_red, mock_blue, mock_judge = AsyncMock(), AsyncMock(), AsyncMock()
    mock_draft, mock_db = AsyncMock(), AsyncMock()
    _setup_draft(mock_draft)
    _setup_bug_patch(mock_red, mock_blue)

    mock_red.attack.return_value = "Attack"
    mock_judge.evaluate_attack.return_value = (
        AttackResult(turn=0, description="", success=True, severity=Severity.MEDIUM, points=3, auto_win=False),
        "Moderate attack.",
    )
    # Effectiveness 0.65 — full block under blue-favored (0.6), partial under balanced (0.7)
    mock_judge.evaluate_defense.return_value = (True, 0.65, "Good block", 0.8)
    mock_blue.defend.return_value = "Defense"
    mock_red.write_debrief.return_value = "Red"
    mock_blue.write_debrief.return_value = "Blue"

    blue_profile = load_scoring_preset("blue-favored")
    engine = _make_round_engine(
        mock_red, mock_blue, mock_judge, mock_draft, mock_db,
        scoring=blue_profile,
    )
    result = await engine.play(round_number=1, phase=Phase.PROMPT_INJECTION)

    # 0.65 >= 0.6 (blue-favored full_block_threshold) → full block = 3 points
    assert result.blue_score == blue_profile.defense_rewards.full_block_points
    assert result.blue_score == 3
