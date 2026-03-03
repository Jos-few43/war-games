import pytest
from unittest.mock import AsyncMock
from wargames.engine.round import RoundEngine
from wargames.models import Phase, MatchOutcome, RoundResult, DraftPick, AttackResult, Severity


@pytest.mark.asyncio
async def test_round_runs_to_completion():
    mock_red = AsyncMock()
    mock_blue = AsyncMock()
    mock_judge = AsyncMock()
    mock_draft_engine = AsyncMock()
    mock_db = AsyncMock()

    mock_draft_engine.run.return_value = (
        [DraftPick(round=1, team="red", resource_name="fuzzer", resource_category="offensive")],
        [DraftPick(round=1, team="blue", resource_name="waf_rules", resource_category="defensive")],
    )

    mock_red.attack.return_value = "SQLi on /api/users"
    mock_red.llm = AsyncMock()
    mock_blue.llm = AsyncMock()

    attack_result = AttackResult(
        turn=0, description="", success=True, severity=Severity.HIGH, points=5, auto_win=False
    )
    mock_judge.evaluate_attack.return_value = attack_result

    mock_judge.evaluate_defense.return_value = (False, "Defense failed")
    mock_blue.defend.return_value = "Added input validation"
    mock_red.write_debrief.return_value = "Red debrief text"
    mock_blue.write_debrief.return_value = "Blue debrief text"

    engine = RoundEngine(
        red=mock_red, blue=mock_blue, judge=mock_judge,
        draft_engine=mock_draft_engine, db=mock_db,
        turn_limit=2, score_threshold=10,
    )
    result = await engine.play(round_number=1, phase=Phase.PROMPT_INJECTION)

    assert isinstance(result, RoundResult)
    assert result.round_number == 1
    assert result.phase == Phase.PROMPT_INJECTION
    assert mock_red.attack.call_count == 2
    assert mock_blue.defend.call_count == 2
    assert result.outcome == MatchOutcome.RED_WIN  # 5pts * 2 turns = 10 >= threshold
    mock_db.save_round.assert_called_once()


@pytest.mark.asyncio
async def test_round_auto_win_ends_early():
    mock_red = AsyncMock()
    mock_blue = AsyncMock()
    mock_judge = AsyncMock()
    mock_draft_engine = AsyncMock()
    mock_db = AsyncMock()

    mock_draft_engine.run.return_value = ([], [])
    mock_red.attack.return_value = "Kernel exploit for root"
    mock_red.llm = AsyncMock()
    mock_blue.llm = AsyncMock()

    attack_result = AttackResult(
        turn=0, description="", success=True, severity=Severity.CRITICAL, points=0, auto_win=True
    )
    mock_judge.evaluate_attack.return_value = attack_result

    mock_blue.defend.return_value = "Attempted containment"
    mock_judge.evaluate_defense.return_value = (False, "Cannot block kernel exploit")
    mock_red.write_debrief.return_value = "Red debrief"
    mock_blue.write_debrief.return_value = "Blue debrief"

    engine = RoundEngine(
        red=mock_red, blue=mock_blue, judge=mock_judge,
        draft_engine=mock_draft_engine, db=mock_db,
        turn_limit=12, score_threshold=10,
    )
    result = await engine.play(round_number=1, phase=Phase.PROMPT_INJECTION)

    assert result.outcome == MatchOutcome.RED_AUTO_WIN
    assert mock_red.attack.call_count == 1  # Stopped after first turn
