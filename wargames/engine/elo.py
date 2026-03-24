"""ELO rating engine for war-games model tournaments.

Standard ELO implementation with K-factor=32 and initial rating=1500.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

K_FACTOR: int = 32
INITIAL_RATING: float = 1500.0


def _expected_score(rating_a: float, rating_b: float) -> float:
    """Return the expected score for player A against player B."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def calculate_elo(
    winner_rating: float,
    loser_rating: float,
    *,
    draw: bool = False,
) -> tuple[float, float]:
    """Calculate new ELO ratings after a game.

    Parameters
    ----------
    winner_rating:
        Current rating of player A (the winner when draw=False).
    loser_rating:
        Current rating of player B (the loser when draw=False).
    draw:
        If True, treat the result as a draw — both players score 0.5.

    Returns
    -------
    tuple[float, float]
        (new_rating_a, new_rating_b)
    """
    expected_a = _expected_score(winner_rating, loser_rating)
    expected_b = _expected_score(loser_rating, winner_rating)

    if draw:
        score_a = 0.5
        score_b = 0.5
    else:
        score_a = 1.0
        score_b = 0.0

    new_a = winner_rating + K_FACTOR * (score_a - expected_a)
    new_b = loser_rating + K_FACTOR * (score_b - expected_b)
    return new_a, new_b


@dataclass
class ModelRating:
    """Tracks ELO rating and game statistics for a model.

    Attributes
    ----------
    model_name:
        Identifier for the model (e.g. ``"gpt-4o"``).
    rating:
        Current ELO rating. Defaults to :data:`INITIAL_RATING` (1500).
    wins:
        Total number of wins recorded.
    losses:
        Total number of losses recorded.
    draws:
        Total number of draws recorded.
    last_played:
        UTC ISO-8601 timestamp of the most recent game, or ``""`` if no
        games have been played yet.
    """

    model_name: str
    rating: float = field(default=INITIAL_RATING)
    wins: int = field(default=0)
    losses: int = field(default=0)
    draws: int = field(default=0)
    last_played: str = field(default="")

    def _touch(self) -> None:
        self.last_played = datetime.now(UTC).isoformat()

    def record_win(self, new_rating: float) -> None:
        """Update state after a win."""
        self.rating = new_rating
        self.wins += 1
        self._touch()

    def record_loss(self, new_rating: float) -> None:
        """Update state after a loss."""
        self.rating = new_rating
        self.losses += 1
        self._touch()

    def record_draw(self, new_rating: float) -> None:
        """Update state after a draw."""
        self.rating = new_rating
        self.draws += 1
        self._touch()
