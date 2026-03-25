"""Tests for the ELO rating engine."""

import re
from datetime import datetime, timezone

import pytest
from hypothesis import given, settings, strategies as st

from wargames.engine.elo import ModelRating, calculate_elo

K_FACTOR = 32
INITIAL_RATING = 1500.0


# ---------------------------------------------------------------------------
# calculate_elo tests
# ---------------------------------------------------------------------------


class TestCalculateEloWinLoss:
    def test_winner_gains_points(self):
        new_winner, new_loser = calculate_elo(1500.0, 1500.0)
        assert new_winner > 1500.0

    def test_loser_loses_points(self):
        new_winner, new_loser = calculate_elo(1500.0, 1500.0)
        assert new_loser < 1500.0

    def test_rating_sum_conserved(self):
        """Total points are conserved in a win/loss outcome."""
        ra, rb = 1600.0, 1400.0
        new_a, new_b = calculate_elo(ra, rb)
        assert abs((new_a + new_b) - (ra + rb)) < 1e-9

    def test_symmetric_equal_ratings(self):
        """At equal ratings winner gains exactly K/2, loser loses K/2."""
        new_winner, new_loser = calculate_elo(1500.0, 1500.0)
        assert abs(new_winner - (1500.0 + K_FACTOR / 2)) < 1e-9
        assert abs(new_loser - (1500.0 - K_FACTOR / 2)) < 1e-9

    def test_underdog_wins_gains_more_than_favourite_wins(self):
        """When the weaker player wins they gain more points."""
        # Underdog (1200) beats favourite (1800)
        new_underdog, _ = calculate_elo(1200.0, 1800.0)
        underdog_gain = new_underdog - 1200.0

        # Favourite (1800) beats underdog (1200)
        new_favourite, _ = calculate_elo(1800.0, 1200.0)
        favourite_gain = new_favourite - 1800.0

        assert underdog_gain > favourite_gain

    def test_returns_floats(self):
        a, b = calculate_elo(1500.0, 1500.0)
        assert isinstance(a, float)
        assert isinstance(b, float)

    def test_high_rated_beats_low_rated_small_gain(self):
        """Heavily favoured winner gains only a small amount."""
        new_winner, _ = calculate_elo(2000.0, 1000.0)
        gain = new_winner - 2000.0
        assert gain < 2.0  # expected score ~0.997, gain ~ K*(1 - 0.997) ~ 0.1


class TestCalculateEloDraw:
    def test_draw_equal_ratings_no_change(self):
        new_a, new_b = calculate_elo(1500.0, 1500.0, draw=True)
        assert abs(new_a - 1500.0) < 1e-9
        assert abs(new_b - 1500.0) < 1e-9

    def test_draw_rating_sum_conserved(self):
        ra, rb = 1700.0, 1300.0
        new_a, new_b = calculate_elo(ra, rb, draw=True)
        assert abs((new_a + new_b) - (ra + rb)) < 1e-9

    def test_draw_favours_underdog(self):
        """In a draw, the lower-rated player should gain points."""
        # a_rating=1700 (favourite), b_rating=1300 (underdog)
        new_a, new_b = calculate_elo(1700.0, 1300.0, draw=True)
        assert new_b > 1300.0  # underdog gains
        assert new_a < 1700.0  # favourite loses

    def test_draw_keyword_only(self):
        """draw must be passed as keyword argument."""
        with pytest.raises(TypeError):
            calculate_elo(1500.0, 1500.0, True)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ModelRating dataclass tests
# ---------------------------------------------------------------------------


class TestModelRatingDefaults:
    def test_default_rating(self):
        mr = ModelRating(model_name='test-model')
        assert mr.rating == INITIAL_RATING

    def test_default_wins(self):
        mr = ModelRating(model_name='test-model')
        assert mr.wins == 0

    def test_default_losses(self):
        mr = ModelRating(model_name='test-model')
        assert mr.losses == 0

    def test_default_draws(self):
        mr = ModelRating(model_name='test-model')
        assert mr.draws == 0

    def test_default_last_played(self):
        mr = ModelRating(model_name='test-model')
        assert mr.last_played == ''

    def test_model_name_stored(self):
        mr = ModelRating(model_name='gpt-4o')
        assert mr.model_name == 'gpt-4o'


class TestModelRatingRecordWin:
    def test_record_win_updates_rating(self):
        mr = ModelRating(model_name='test-model')
        mr.record_win(1516.0)
        assert mr.rating == 1516.0

    def test_record_win_increments_wins(self):
        mr = ModelRating(model_name='test-model')
        mr.record_win(1516.0)
        assert mr.wins == 1

    def test_record_win_does_not_change_losses_or_draws(self):
        mr = ModelRating(model_name='test-model')
        mr.record_win(1516.0)
        assert mr.losses == 0
        assert mr.draws == 0

    def test_record_win_sets_last_played(self):
        mr = ModelRating(model_name='test-model')
        before = datetime.now(timezone.utc)
        mr.record_win(1516.0)
        after = datetime.now(timezone.utc)
        ts = datetime.fromisoformat(mr.last_played)
        assert before <= ts <= after

    def test_record_win_last_played_is_utc_iso(self):
        mr = ModelRating(model_name='test-model')
        mr.record_win(1516.0)
        # Should parse cleanly and end with +00:00 or Z
        ts = datetime.fromisoformat(mr.last_played)
        assert ts.tzinfo is not None

    def test_record_win_multiple(self):
        mr = ModelRating(model_name='test-model')
        mr.record_win(1516.0)
        mr.record_win(1530.0)
        assert mr.wins == 2
        assert mr.rating == 1530.0


class TestModelRatingRecordLoss:
    def test_record_loss_updates_rating(self):
        mr = ModelRating(model_name='test-model')
        mr.record_loss(1484.0)
        assert mr.rating == 1484.0

    def test_record_loss_increments_losses(self):
        mr = ModelRating(model_name='test-model')
        mr.record_loss(1484.0)
        assert mr.losses == 1

    def test_record_loss_does_not_change_wins_or_draws(self):
        mr = ModelRating(model_name='test-model')
        mr.record_loss(1484.0)
        assert mr.wins == 0
        assert mr.draws == 0

    def test_record_loss_sets_last_played(self):
        mr = ModelRating(model_name='test-model')
        before = datetime.now(timezone.utc)
        mr.record_loss(1484.0)
        after = datetime.now(timezone.utc)
        ts = datetime.fromisoformat(mr.last_played)
        assert before <= ts <= after


class TestModelRatingRecordDraw:
    def test_record_draw_updates_rating(self):
        mr = ModelRating(model_name='test-model')
        mr.record_draw(1500.0)
        assert mr.rating == 1500.0

    def test_record_draw_increments_draws(self):
        mr = ModelRating(model_name='test-model')
        mr.record_draw(1500.0)
        assert mr.draws == 1

    def test_record_draw_does_not_change_wins_or_losses(self):
        mr = ModelRating(model_name='test-model')
        mr.record_draw(1500.0)
        assert mr.wins == 0
        assert mr.losses == 0

    def test_record_draw_sets_last_played(self):
        mr = ModelRating(model_name='test-model')
        before = datetime.now(timezone.utc)
        mr.record_draw(1500.0)
        after = datetime.now(timezone.utc)
        ts = datetime.fromisoformat(mr.last_played)
        assert before <= ts <= after


# ---------------------------------------------------------------------------
# Property-based tests using Hypothesis
# ---------------------------------------------------------------------------


class TestEloProperties:
    """Property-based tests for ELO calculation invariants."""

    @given(
        rating_a=st.floats(min_value=100.0, max_value=3000.0),
        rating_b=st.floats(min_value=100.0, max_value=3000.0),
    )
    @settings(max_examples=100)
    def test_elo_rating_sum_conserved(self, rating_a, rating_b):
        """Total rating points are always conserved (within floating-point precision)."""
        new_a, new_b = calculate_elo(rating_a, rating_b)
        assert abs((new_a + new_b) - (rating_a + rating_b)) < 1e-6

    @given(
        rating_a=st.floats(min_value=100.0, max_value=3000.0),
        rating_b=st.floats(min_value=100.0, max_value=3000.0),
    )
    @settings(max_examples=100)
    def test_winner_always_gains_points(self, rating_a, rating_b):
        """The winner always gains rating points."""
        new_winner, _ = calculate_elo(rating_a, rating_b)
        assert new_winner > rating_a

    @given(
        rating_a=st.floats(min_value=100.0, max_value=3000.0),
        rating_b=st.floats(min_value=100.0, max_value=3000.0),
    )
    @settings(max_examples=100)
    def test_loser_always_loses_points(self, rating_a, rating_b):
        """The loser always loses rating points."""
        _, new_loser = calculate_elo(rating_a, rating_b)
        assert new_loser < rating_b

    @given(
        rating_a=st.floats(min_value=100.0, max_value=3000.0),
        rating_b=st.floats(min_value=100.0, max_value=3000.0),
    )
    @settings(max_examples=100)
    def test_draw_equal_ratings_no_change(self, rating_a, rating_b):
        """In a draw, ratings move toward each other but sum is conserved."""
        new_a, new_b = calculate_elo(rating_a, rating_b, draw=True)
        # Sum is conserved
        assert abs((new_a + new_b) - (rating_a + rating_b)) < 1e-6
        # If ratings were equal, they stay equal
        if abs(rating_a - rating_b) < 0.01:
            assert abs(new_a - rating_a) < 0.01
            assert abs(new_b - rating_b) < 0.01

    @given(
        rating_a=st.floats(min_value=100.0, max_value=3000.0),
        rating_b=st.floats(min_value=100.0, max_value=3000.0),
    )
    @settings(max_examples=100)
    def test_point_exchange_symmetry(self, rating_a, rating_b):
        """Points gained by winner equals points lost by loser (approximately)."""
        new_a, new_b = calculate_elo(rating_a, rating_b)
        gain_a = new_a - rating_a
        loss_b = rating_b - new_b
        assert abs(gain_a - loss_b) < 1e-6

    @given(
        rating=st.floats(min_value=100.0, max_value=3000.0),
    )
    @settings(max_examples=50)
    def test_elo_change_bounded_by_k_factor(self, rating):
        """Maximum rating change per game is bounded by K-factor."""
        # Against a much lower-rated opponent
        new_rating, _ = calculate_elo(rating, 100.0)
        change = abs(new_rating - rating)
        assert change <= 32.0  # K_FACTOR

        # Against a much higher-rated opponent
        new_rating, _ = calculate_elo(rating, 2900.0)
        change = abs(new_rating - rating)
        assert change <= 32.0  # K_FACTOR


class TestModelRatingProperties:
    """Property-based tests for ModelRating dataclass."""

    @given(
        initial_rating=st.floats(min_value=100.0, max_value=3000.0),
        new_rating=st.floats(min_value=100.0, max_value=3000.0),
    )
    @settings(max_examples=50)
    def test_record_win_updates_rating(self, initial_rating, new_rating):
        """Recording a win updates the rating to the specified value."""
        mr = ModelRating(model_name="test", rating=initial_rating)
        mr.record_win(new_rating)
        assert mr.rating == new_rating
        assert mr.wins == 1

    @given(
        wins=st.integers(min_value=0, max_value=100),
        losses=st.integers(min_value=0, max_value=100),
        draws=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=50)
    def test_total_games_equals_sum(self, wins, losses, draws):
        """Total games played equals wins + losses + draws."""
        mr = ModelRating(model_name="test", wins=wins, losses=losses, draws=draws)
        assert mr.wins + mr.losses + mr.draws == wins + losses + draws
