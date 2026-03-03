import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from wargames.engine.game import GameEngine
from wargames.models import GameConfig, Phase, MatchOutcome, RoundResult
from wargames.config import load_config


@pytest.fixture
def config(tmp_path):
    c = load_config(Path("config/default.toml"))
    c.game.rounds = 3
    c.output.database.path = str(tmp_path / "test.db")
    c.output.vault.enabled = False
    return c


@pytest.mark.asyncio
async def test_game_engine_runs_rounds(config):
    mock_round_result = RoundResult(
        round_number=1, phase=Phase.PROMPT_INJECTION,
        outcome=MatchOutcome.BLUE_WIN, red_score=4, blue_threshold=10,
        red_draft=[], blue_draft=[], attacks=[], defenses=[],
        red_debrief="red notes", blue_debrief="blue notes",
    )

    with patch("wargames.engine.game.RoundEngine") as MockRound:
        MockRound.return_value.play = AsyncMock(return_value=mock_round_result)
        with patch("wargames.engine.game.LLMClient") as MockLLMClient:
            mock_llm_instance = MagicMock()
            mock_llm_instance.close = AsyncMock()
            MockLLMClient.return_value = mock_llm_instance
            engine = GameEngine(config)
            await engine.init()
            results = []
            async for result in engine.run():
                results.append(result)
            await engine.cleanup()
            assert len(results) == 3


def test_phase_advances_on_threshold():
    config = load_config(Path("config/default.toml"))
    config.game.phase_advance_score = 5.0
    engine = GameEngine(config)
    engine._round_scores = [6.0] * 10
    new_phase = engine._check_phase_advance(Phase.PROMPT_INJECTION)
    assert new_phase == Phase.CODE_VULNS


def test_phase_does_not_advance_below_threshold():
    config = load_config(Path("config/default.toml"))
    config.game.phase_advance_score = 5.0
    engine = GameEngine(config)
    engine._round_scores = [3.0] * 10
    new_phase = engine._check_phase_advance(Phase.PROMPT_INJECTION)
    assert new_phase == Phase.PROMPT_INJECTION


def test_phase_does_not_advance_with_few_rounds():
    config = load_config(Path("config/default.toml"))
    engine = GameEngine(config)
    engine._round_scores = [10.0] * 5  # Only 5 rounds, need 10
    new_phase = engine._check_phase_advance(Phase.PROMPT_INJECTION)
    assert new_phase == Phase.PROMPT_INJECTION
