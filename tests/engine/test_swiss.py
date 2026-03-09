"""Tests for the Swiss-system pairing engine."""

import pytest

from wargames.engine.swiss import StandingsEntry, swiss_pair


def _names(pairs):
    """Return pairs as sorted tuples of names for easy assertion."""
    return {tuple(sorted((a.name, b.name))) for a, b in pairs}


def test_swiss_pair_round_1_by_seed():
    """Round 1: no wins, so all grouped together. Highest rated pairs with middle."""
    players = [
        StandingsEntry(name="A", rating=2000),
        StandingsEntry(name="B", rating=1800),
        StandingsEntry(name="C", rating=1600),
        StandingsEntry(name="D", rating=1400),
    ]

    pairs = swiss_pair(players)
    names = _names(pairs)

    assert len(pairs) == 2
    # Top half [A, B] pairs with bottom half [C, D]:
    # A (2000) vs C (1600), B (1800) vs D (1400)
    assert ("A", "C") in names
    assert ("B", "D") in names


def test_swiss_pair_avoids_rematches():
    """When A has played B and C has played D, the engine avoids rematches."""
    players = [
        StandingsEntry(name="A", rating=2000, played_against={"B"}),
        StandingsEntry(name="B", rating=1800, played_against={"A"}),
        StandingsEntry(name="C", rating=1600, played_against={"D"}),
        StandingsEntry(name="D", rating=1400, played_against={"C"}),
    ]

    pairs = swiss_pair(players)
    names = _names(pairs)

    assert len(pairs) == 2
    # A-B and C-D are rematches, so engine must find alternatives.
    assert ("A", "B") not in names
    assert ("C", "D") not in names
    # Valid pairings: A-C & B-D, or A-D & B-C.
    valid_option_1 = {("A", "C"), ("B", "D")}
    valid_option_2 = {("A", "D"), ("B", "C")}
    assert names == valid_option_1 or names == valid_option_2


def test_swiss_pair_groups_by_wins():
    """Players are grouped by win count; same-win players pair together."""
    players = [
        StandingsEntry(name="A", wins=2, rating=1900),
        StandingsEntry(name="B", wins=2, rating=1700),
        StandingsEntry(name="C", wins=1, rating=1800),
        StandingsEntry(name="D", wins=1, rating=1500),
    ]

    pairs = swiss_pair(players)
    names = _names(pairs)

    assert len(pairs) == 2
    # 2-win group: A vs B; 1-win group: C vs D.
    assert ("A", "B") in names
    assert ("C", "D") in names


def test_swiss_pair_odd_number_gives_bye():
    """With 3 players, one pair is returned and the lowest-rated gets a bye."""
    players = [
        StandingsEntry(name="A", rating=2000),
        StandingsEntry(name="B", rating=1800),
        StandingsEntry(name="C", rating=1400),
    ]

    pairs = swiss_pair(players)

    assert len(pairs) == 1
    paired_names = {pairs[0][0].name, pairs[0][1].name}
    # A (highest) should pair with B (next); C gets the bye.
    assert paired_names == {"A", "B"}


@pytest.mark.asyncio
async def test_tournament_runner_completes(tmp_path):
    """Tournament runner should complete all Swiss rounds and update standings."""
    from unittest.mock import AsyncMock, patch

    from wargames.engine.swiss import TournamentRunner
    from wargames.models import (
        MatchOutcome,
        ModelEntry,
        Phase,
        RoundResult,
        TournamentConfig,
    )
    from wargames.output.db import Database

    config = TournamentConfig(
        name="test-tourney",
        rounds=2,
        games_per_match=2,
        game_rounds=1,
        turn_limit=4,
        score_threshold=10,
        models=[
            ModelEntry(name="model-a", endpoint="http://localhost/v1", model_name="a"),
            ModelEntry(name="model-b", endpoint="http://localhost/v1", model_name="b"),
            ModelEntry(name="model-c", endpoint="http://localhost/v1", model_name="c"),
            ModelEntry(name="model-d", endpoint="http://localhost/v1", model_name="d"),
        ],
    )

    db = Database(tmp_path / "test.db")
    await db.init()

    mock_result = RoundResult(
        round_number=1,
        phase=Phase.PROMPT_INJECTION,
        outcome=MatchOutcome.RED_WIN,
        red_score=8,
        blue_score=3,
        blue_threshold=10,
        red_draft=[],
        blue_draft=[],
        attacks=[],
        defenses=[],
    )

    with patch("wargames.engine.sandbox.SandboxRunner") as MockSandbox:
        mock_runner = AsyncMock()
        mock_runner.run.return_value = mock_result
        MockSandbox.return_value = mock_runner

        runner = TournamentRunner(config, db)
        final_standings = await runner.run()

    assert len(final_standings) == 4
    matches = await db.get_tournament_matches("test-tourney")
    # 2 Swiss rounds x 2 pairs x 2 games_per_match = 8 matches
    assert len(matches) == 8
    await db.close()
