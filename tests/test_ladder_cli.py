"""Tests for `wargames ladder` CLI command."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wargames.cli import parse_args


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def test_parse_ladder_command():
    args = parse_args(["ladder"])
    assert args.command == "ladder"


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def test_ladder_prints_table_with_ratings(tmp_path, capsys):
    """ladder command prints a formatted leaderboard when ratings exist."""
    mock_ratings = [
        {
            "model_name": "gpt-4o",
            "rating": 1532.5,
            "wins": 10,
            "losses": 3,
            "draws": 1,
            "last_played": "2026-03-01T12:00:00+00:00",
        },
        {
            "model_name": "claude-sonnet-4-5",
            "rating": 1487.3,
            "wins": 7,
            "losses": 6,
            "draws": 1,
            "last_played": "2026-03-02T08:00:00+00:00",
        },
    ]

    mock_db = MagicMock()
    mock_db.init = AsyncMock()
    mock_db.get_all_ratings = AsyncMock(return_value=mock_ratings)
    mock_db.close = AsyncMock()

    with patch("wargames.cli.Database", return_value=mock_db), \
         patch("wargames.cli._default_db_path", return_value=tmp_path / "test.db"):
        from wargames.cli import main
        main(["ladder"])

    output = capsys.readouterr().out
    assert "gpt-4o" in output
    assert "1532" in output
    assert "claude-sonnet-4-5" in output
    # Rank column headers
    assert "Rank" in output
    assert "Rating" in output


def test_ladder_no_ratings_message(tmp_path, capsys):
    """ladder command prints helpful message when no ratings exist."""
    mock_db = MagicMock()
    mock_db.init = AsyncMock()
    mock_db.get_all_ratings = AsyncMock(return_value=[])
    mock_db.close = AsyncMock()

    with patch("wargames.cli.Database", return_value=mock_db), \
         patch("wargames.cli._default_db_path", return_value=tmp_path / "test.db"):
        from wargames.cli import main
        main(["ladder"])

    output = capsys.readouterr().out
    assert "No ratings yet" in output


def test_ladder_rank_ordering(tmp_path, capsys):
    """Rank 1 is the highest-rated model (DB already returns DESC order)."""
    mock_ratings = [
        {"model_name": "top-model", "rating": 1600.0, "wins": 20, "losses": 0, "draws": 0, "last_played": "2026-03-01"},
        {"model_name": "mid-model", "rating": 1500.0, "wins": 10, "losses": 10, "draws": 0, "last_played": "2026-03-01"},
    ]

    mock_db = MagicMock()
    mock_db.init = AsyncMock()
    mock_db.get_all_ratings = AsyncMock(return_value=mock_ratings)
    mock_db.close = AsyncMock()

    with patch("wargames.cli.Database", return_value=mock_db), \
         patch("wargames.cli._default_db_path", return_value=tmp_path / "test.db"):
        from wargames.cli import main
        main(["ladder"])

    output = capsys.readouterr().out
    # "1" then "top-model" should appear before "2" then "mid-model"
    pos_top = output.find("top-model")
    pos_mid = output.find("mid-model")
    assert pos_top < pos_mid, "Highest-rated model should be ranked first"
