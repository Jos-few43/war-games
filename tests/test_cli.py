import pytest
from wargames.cli import parse_args


def test_parse_start_command():
    args = parse_args(["start", "--config", "config/default.toml"])
    assert args.command == "start"
    assert args.config == "config/default.toml"


def test_parse_attach_command():
    args = parse_args(["attach"])
    assert args.command == "attach"


def test_parse_status_command():
    args = parse_args(["status"])
    assert args.command == "status"


def test_parse_crawl_command():
    args = parse_args(["crawl", "--sources", "nvd,exploitdb"])
    assert args.command == "crawl"
    assert args.sources == "nvd,exploitdb"


def test_parse_report_command():
    args = parse_args(["report", "14"])
    assert args.command == "report"
    assert args.round_number == 14


def test_parse_pause_resume():
    args = parse_args(["pause"])
    assert args.command == "pause"
    args = parse_args(["resume"])
    assert args.command == "resume"


from unittest.mock import patch, AsyncMock, MagicMock


def test_crawl_calls_crawlers(tmp_path):
    """crawl command should invoke NVD and ExploitDB crawlers."""
    mock_nvd = MagicMock()
    mock_nvd.fetch = AsyncMock(return_value=[{"cve_id": "CVE-2024-0001", "source": "nvd"}])
    mock_nvd.store = AsyncMock()

    mock_edb = MagicMock()
    mock_edb.fetch = AsyncMock(return_value=[{"cve_id": "EDB-1234", "source": "exploitdb"}])
    mock_edb.store = AsyncMock()

    mock_db = MagicMock()
    mock_db.init = AsyncMock()
    mock_db.close = AsyncMock()

    with patch("wargames.cli.NVDCrawler", return_value=mock_nvd), \
         patch("wargames.cli.ExploitDBCrawler", return_value=mock_edb), \
         patch("wargames.cli.Database", return_value=mock_db), \
         patch("wargames.cli._default_db_path", return_value=tmp_path / "test.db"):
        from wargames.cli import main
        main(["crawl", "--sources", "nvd,exploitdb"])
        mock_nvd.fetch.assert_called_once()
        mock_edb.fetch.assert_called_once()


def test_report_prints_round_summary(tmp_path, capsys):
    """report command should print a formatted round summary."""
    from wargames.models import RoundResult, Phase, MatchOutcome, AttackResult, DefenseResult, Severity

    mock_result = RoundResult(
        round_number=1,
        phase=Phase.PROMPT_INJECTION,
        outcome=MatchOutcome.RED_WIN,
        red_score=12,
        blue_score=3,
        blue_threshold=10,
        red_draft=[],
        blue_draft=[],
        attacks=[AttackResult(turn=1, description="SQL injection", severity=Severity.HIGH, points=5, success=True)],
        defenses=[DefenseResult(turn=1, description="WAF block", blocked=True, points_deducted=3)],
    )

    mock_db = MagicMock()
    mock_db.init = AsyncMock()
    mock_db.get_round = AsyncMock(return_value=mock_result)
    mock_db.close = AsyncMock()

    with patch("wargames.cli.Database", return_value=mock_db), \
         patch("wargames.cli._default_db_path", return_value=tmp_path / "test.db"):
        from wargames.cli import main
        main(["report", "1"])

    output = capsys.readouterr().out
    assert "Round 1" in output
    assert "red_win" in output
    assert "SQL injection" in output


import json


def test_export_json(tmp_path, capsys):
    """export --format json should print valid JSON."""
    from wargames.models import RoundResult, Phase, MatchOutcome

    mock_results = [
        RoundResult(
            round_number=1, phase=Phase.PROMPT_INJECTION,
            outcome=MatchOutcome.RED_WIN, red_score=12, blue_score=3,
            blue_threshold=10, red_draft=[], blue_draft=[],
            attacks=[], defenses=[],
        ),
    ]

    mock_db = MagicMock()
    mock_db.init = AsyncMock()
    mock_db.get_all_rounds = AsyncMock(return_value=mock_results)
    mock_db.close = AsyncMock()

    with patch("wargames.cli.Database", return_value=mock_db), \
         patch("wargames.cli._default_db_path", return_value=tmp_path / "test.db"):
        from wargames.cli import main
        main(["export", "--format", "json"])

    output = capsys.readouterr().out
    data = json.loads(output)
    assert len(data["rounds"]) == 1
    assert data["rounds"][0]["outcome"] == "red_win"


def test_export_markdown(tmp_path, capsys):
    """export --format markdown should print a markdown table."""
    from wargames.models import RoundResult, Phase, MatchOutcome

    mock_results = [
        RoundResult(
            round_number=1, phase=Phase.PROMPT_INJECTION,
            outcome=MatchOutcome.RED_WIN, red_score=12, blue_score=3,
            blue_threshold=10, red_draft=[], blue_draft=[],
            attacks=[], defenses=[],
        ),
    ]

    mock_db = MagicMock()
    mock_db.init = AsyncMock()
    mock_db.get_all_rounds = AsyncMock(return_value=mock_results)
    mock_db.close = AsyncMock()

    with patch("wargames.cli.Database", return_value=mock_db), \
         patch("wargames.cli._default_db_path", return_value=tmp_path / "test.db"):
        from wargames.cli import main
        main(["export", "--format", "markdown"])

    output = capsys.readouterr().out
    assert "| Round |" in output
    assert "| 1 |" in output
