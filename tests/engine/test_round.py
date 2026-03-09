import pytest
from unittest.mock import AsyncMock, call
from wargames.engine.round import RoundEngine
from wargames.models import Phase, MatchOutcome, RoundResult, DraftPick, AttackResult, DefenseResult, Severity, BugReport, Patch, Domain


def _make_engine(mock_red, mock_blue, mock_judge, mock_draft_engine, mock_db,
                 turn_limit=2, score_threshold=10):
    mock_red.llm = AsyncMock()
    mock_blue.llm = AsyncMock()
    return RoundEngine(
        red=mock_red, blue=mock_blue, judge=mock_judge,
        draft_engine=mock_draft_engine, db=mock_db,
        turn_limit=turn_limit, score_threshold=score_threshold,
    )


def _setup_draft(mock_draft_engine, red_picks=None, blue_picks=None):
    mock_draft_engine.run.return_value = (
        red_picks or [DraftPick(round=1, team="red", resource_name="fuzzer", resource_category="offensive")],
        blue_picks or [DraftPick(round=1, team="blue", resource_name="waf_rules", resource_category="defensive")],
    )


def _setup_bug_patch(mock_red, mock_blue):
    mock_red.generate_bug_report.return_value = BugReport(
        round_number=0, title="SQLi", severity=Severity.HIGH, domain=Domain.CODE_VULN,
        target="/api/users", steps_to_reproduce="", proof_of_concept="", impact="",
    )
    mock_blue.generate_patch.return_value = Patch(
        round_number=0, title="Fix SQLi", fixes="", strategy="", changes="", verification="",
    )


@pytest.mark.asyncio
async def test_round_runs_to_completion():
    """Red scores enough to win via threshold. Blue blocks nothing."""
    mock_red, mock_blue, mock_judge = AsyncMock(), AsyncMock(), AsyncMock()
    mock_draft_engine, mock_db = AsyncMock(), AsyncMock()
    _setup_draft(mock_draft_engine)
    _setup_bug_patch(mock_red, mock_blue)

    mock_red.attack.return_value = "SQLi on /api/users"
    mock_judge.evaluate_attack.return_value = (AttackResult(
        turn=0, description="", success=True, severity=Severity.HIGH, points=5, auto_win=False,
    ), "A database attack was attempted.")
    # Defense fails — effectiveness 0.1
    mock_judge.evaluate_defense.return_value = (False, 0.1, "Defense failed")
    mock_blue.defend.return_value = "Added input validation"
    mock_red.write_debrief.return_value = "Red debrief text"
    mock_blue.write_debrief.return_value = "Blue debrief text"

    engine = _make_engine(mock_red, mock_blue, mock_judge, mock_draft_engine, mock_db)
    result = await engine.play(round_number=1, phase=Phase.PROMPT_INJECTION)

    assert isinstance(result, RoundResult)
    assert result.round_number == 1
    assert result.phase == Phase.PROMPT_INJECTION
    assert mock_red.attack.call_count == 2
    assert mock_blue.defend.call_count == 2
    assert result.outcome == MatchOutcome.RED_WIN  # 5pts * 2 turns = 10 >= threshold
    assert result.red_score == 10
    assert result.blue_score == 0
    mock_db.save_round.assert_called_once()


@pytest.mark.asyncio
async def test_round_critical_attack_contested_blue_fails():
    """Critical attack: Blue defends but effectiveness < 0.5 → RED_CRITICAL_WIN."""
    mock_red, mock_blue, mock_judge = AsyncMock(), AsyncMock(), AsyncMock()
    mock_draft_engine, mock_db = AsyncMock(), AsyncMock()
    _setup_draft(mock_draft_engine, red_picks=[], blue_picks=[])
    _setup_bug_patch(mock_red, mock_blue)

    mock_red.attack.return_value = "Kernel exploit for root"
    mock_judge.evaluate_attack.return_value = (AttackResult(
        turn=0, description="", success=True, severity=Severity.CRITICAL, points=8, auto_win=True,
    ), "A critical system compromise was attempted.")
    mock_blue.defend.return_value = "Attempted containment"
    mock_judge.evaluate_defense.return_value = (False, 0.3, "Cannot block kernel exploit")
    mock_red.write_debrief.return_value = "Red debrief"
    mock_blue.write_debrief.return_value = "Blue debrief"

    engine = _make_engine(mock_red, mock_blue, mock_judge, mock_draft_engine, mock_db,
                          turn_limit=12)
    result = await engine.play(round_number=1, phase=Phase.PROMPT_INJECTION)

    assert result.outcome == MatchOutcome.RED_CRITICAL_WIN
    assert mock_red.attack.call_count == 1  # Stopped after critical


@pytest.mark.asyncio
async def test_round_critical_attack_contested_blue_wins():
    """Critical attack: Blue defends with effectiveness >= 0.5 → neutralized, game continues."""
    mock_red, mock_blue, mock_judge = AsyncMock(), AsyncMock(), AsyncMock()
    mock_draft_engine, mock_db = AsyncMock(), AsyncMock()
    _setup_draft(mock_draft_engine)
    _setup_bug_patch(mock_red, mock_blue)

    # Turn 1: critical attack, Blue neutralizes it
    # Turn 2: normal attack, Blue blocks
    attack_results = [
        (AttackResult(turn=0, description="", success=True, severity=Severity.CRITICAL, points=8, auto_win=True), "A critical attack was launched."),
        (AttackResult(turn=0, description="", success=True, severity=Severity.MEDIUM, points=3, auto_win=False), "A moderate attack was attempted."),
    ]
    mock_judge.evaluate_attack.side_effect = attack_results
    mock_red.attack.return_value = "Attack"
    mock_blue.defend.return_value = "Strong defense"
    # First call: critical defense (eff=0.6 → neutralized), second: normal block (eff=0.8)
    mock_judge.evaluate_defense.side_effect = [
        (True, 0.6, "Partially contained critical"),
        (True, 0.8, "Blocked"),
    ]
    mock_red.write_debrief.return_value = "Red debrief"
    mock_blue.write_debrief.return_value = "Blue debrief"

    engine = _make_engine(mock_red, mock_blue, mock_judge, mock_draft_engine, mock_db)
    result = await engine.play(round_number=1, phase=Phase.PROMPT_INJECTION)

    assert result.outcome != MatchOutcome.RED_CRITICAL_WIN
    assert mock_red.attack.call_count == 2  # Game continued past critical
    assert result.blue_score >= 5  # At least the critical neutralize bonus


@pytest.mark.asyncio
async def test_blue_decisive_win():
    """Blue blocks enough attacks to reach score threshold → BLUE_DECISIVE_WIN."""
    mock_red, mock_blue, mock_judge = AsyncMock(), AsyncMock(), AsyncMock()
    mock_draft_engine, mock_db = AsyncMock(), AsyncMock()
    _setup_draft(mock_draft_engine)

    mock_red.attack.return_value = "Weak attack"
    # Attacks succeed but with low points
    mock_judge.evaluate_attack.return_value = (AttackResult(
        turn=0, description="", success=True, severity=Severity.LOW, points=1, auto_win=False,
    ), "A minor attack was attempted.")
    _setup_bug_patch(mock_red, mock_blue)
    # Blue blocks every time with high effectiveness
    mock_judge.evaluate_defense.return_value = (True, 0.9, "Excellent defense")
    mock_blue.defend.return_value = "Comprehensive defense"
    mock_red.write_debrief.return_value = "Red debrief"
    mock_blue.write_debrief.return_value = "Blue debrief"

    # score_threshold=6, each block gives Blue +3, so 2 blocks = 6 → decisive win
    engine = _make_engine(mock_red, mock_blue, mock_judge, mock_draft_engine, mock_db,
                          turn_limit=5, score_threshold=6)
    result = await engine.play(round_number=1, phase=Phase.PROMPT_INJECTION)

    assert result.outcome == MatchOutcome.BLUE_DECISIVE_WIN
    assert result.blue_score >= 6


@pytest.mark.asyncio
async def test_partial_defense_scoring():
    """Effectiveness 0.3-0.7 gives partial credit: Blue +1, Red -1."""
    mock_red, mock_blue, mock_judge = AsyncMock(), AsyncMock(), AsyncMock()
    mock_draft_engine, mock_db = AsyncMock(), AsyncMock()
    _setup_draft(mock_draft_engine)
    _setup_bug_patch(mock_red, mock_blue)

    mock_red.attack.return_value = "Medium attack"
    mock_judge.evaluate_attack.return_value = (AttackResult(
        turn=0, description="", success=True, severity=Severity.MEDIUM, points=3, auto_win=False,
    ), "A moderate attack was attempted.")
    # Partial defense — effectiveness 0.5
    mock_judge.evaluate_defense.return_value = (False, 0.5, "Partial mitigation")
    mock_blue.defend.return_value = "Partial defense"
    mock_red.write_debrief.return_value = "Red debrief"
    mock_blue.write_debrief.return_value = "Blue debrief"

    engine = _make_engine(mock_red, mock_blue, mock_judge, mock_draft_engine, mock_db,
                          turn_limit=1, score_threshold=10)
    result = await engine.play(round_number=1, phase=Phase.PROMPT_INJECTION)

    assert result.blue_score == 1  # Partial: +1
    assert result.red_score == 2  # 3 points from attack, -1 from partial defense
    # Check the defense result
    assert result.defenses[0].points_earned == 1
    assert result.defenses[0].points_deducted == 1
    assert result.defenses[0].effectiveness == 0.5


@pytest.mark.asyncio
async def test_even_turn_defense_context():
    """On even turns, judge receives Blue's prior defense as context."""
    mock_red, mock_blue, mock_judge = AsyncMock(), AsyncMock(), AsyncMock()
    mock_draft_engine, mock_db = AsyncMock(), AsyncMock()
    _setup_draft(mock_draft_engine)
    _setup_bug_patch(mock_red, mock_blue)

    mock_red.attack.return_value = "Attack attempt"
    mock_judge.evaluate_attack.return_value = (AttackResult(
        turn=0, description="", success=True, severity=Severity.LOW, points=1, auto_win=False,
    ), "A minor reconnaissance attempt was detected.")
    mock_judge.evaluate_defense.return_value = (True, 0.8, "Blocked")
    mock_blue.defend.return_value = "Deployed WAF and IDS monitoring"
    mock_red.write_debrief.return_value = "Red debrief"
    mock_blue.write_debrief.return_value = "Blue debrief"

    engine = _make_engine(mock_red, mock_blue, mock_judge, mock_draft_engine, mock_db,
                          turn_limit=2, score_threshold=100)
    await engine.play(round_number=1, phase=Phase.PROMPT_INJECTION)

    # Turn 1 (odd): normal target context
    first_call_target = mock_judge.evaluate_attack.call_args_list[0][0][1]
    assert "Blue team has already deployed" not in first_call_target

    # Turn 2 (even): target context includes Blue's turn-1 defense
    second_call_target = mock_judge.evaluate_attack.call_args_list[1][0][1]
    assert "Blue team has already deployed" in second_call_target
    assert "Deployed WAF and IDS monitoring" in second_call_target


@pytest.mark.asyncio
async def test_blue_receives_attack_severity():
    """Blue's defend() receives attack_severity parameter."""
    mock_red, mock_blue, mock_judge = AsyncMock(), AsyncMock(), AsyncMock()
    mock_draft_engine, mock_db = AsyncMock(), AsyncMock()
    _setup_draft(mock_draft_engine)
    _setup_bug_patch(mock_red, mock_blue)

    mock_red.attack.return_value = "Critical attack"
    mock_judge.evaluate_attack.return_value = (AttackResult(
        turn=0, description="", success=True, severity=Severity.CRITICAL, points=8, auto_win=False,
    ), "A critical attack was attempted.")
    mock_judge.evaluate_defense.return_value = (True, 0.8, "Blocked")
    mock_blue.defend.return_value = "Defense"
    mock_red.write_debrief.return_value = "Red debrief"
    mock_blue.write_debrief.return_value = "Blue debrief"

    engine = _make_engine(mock_red, mock_blue, mock_judge, mock_draft_engine, mock_db,
                          turn_limit=1, score_threshold=100)
    await engine.play(round_number=1, phase=Phase.PROMPT_INJECTION)

    # Verify Blue.defend was called with attack_severity="critical"
    defend_call = mock_blue.defend.call_args
    assert defend_call.kwargs.get("attack_severity") == "critical" or \
           (len(defend_call.args) > 5 and defend_call.args[5] == "critical")
