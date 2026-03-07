import pytest
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch as mock_patch
from pathlib import Path
from wargames.worker import Worker
from wargames.models import (
    BugReport, Patch, RoundResult, Phase, MatchOutcome,
    Severity, Domain,
)


@pytest.mark.asyncio
async def test_worker_starts_and_stops(tmp_path):
    mock_config = MagicMock()
    mock_config.output.database.path = str(tmp_path / "test.db")
    mock_config.output.vault.enabled = False
    mock_config.game.rounds = 2

    mock_result = MagicMock(round_number=1)

    with mock_patch("wargames.worker.GameEngine") as MockEngine:
        instance = MagicMock()

        async def fake_run():
            yield mock_result

        instance.run = fake_run
        instance.init = AsyncMock()
        instance.cleanup = AsyncMock()
        instance.stop = MagicMock()
        MockEngine.return_value = instance

        worker = Worker(mock_config, pid_file=tmp_path / "test.pid")
        task = asyncio.create_task(worker.run())
        await asyncio.sleep(0.1)
        worker.stop()
        await task

        assert not (tmp_path / "test.pid").exists()


def test_worker_writes_pid_file(tmp_path):
    worker = Worker(MagicMock(), pid_file=tmp_path / "test.pid")
    worker._write_pid()
    assert (tmp_path / "test.pid").exists()
    pid = int((tmp_path / "test.pid").read_text())
    assert pid == os.getpid()


@pytest.mark.asyncio
async def test_worker_writes_bug_reports_and_patches_to_vault(tmp_path):
    """Verify vault writer receives bug reports and patches after each round."""
    vault_path = tmp_path / "vault"

    mock_config = MagicMock()
    mock_config.output.database.path = str(tmp_path / "test.db")
    mock_config.output.vault.enabled = True
    mock_config.output.vault.path = str(vault_path)

    bug = BugReport(
        round_number=1,
        title="SQL Injection in login",
        severity=Severity.HIGH,
        domain=Domain.CODE_VULN,
        target="auth-service",
        steps_to_reproduce="1. Send malformed input",
        proof_of_concept="' OR 1=1 --",
        impact="Full DB read access",
    )
    patch = Patch(
        round_number=1,
        title="Parameterize login query",
        fixes="SQL Injection in login",
        strategy="Use prepared statements",
        changes="Replace raw SQL with ORM query",
        verification="Fuzz tested with 1000 payloads",
    )

    mock_result = MagicMock(spec=RoundResult)
    mock_result.round_number = 1
    mock_result.phase = Phase.CODE_VULNS
    mock_result.outcome = MatchOutcome.RED_WIN
    mock_result.red_score = 8
    mock_result.blue_threshold = 10
    mock_result.red_draft = []
    mock_result.blue_draft = []
    mock_result.attacks = []
    mock_result.defenses = []
    mock_result.red_debrief = "red analysis"
    mock_result.blue_debrief = "blue analysis"
    mock_result.bug_reports = [bug]
    mock_result.patches = [patch]

    with mock_patch("wargames.worker.GameEngine") as MockEngine:
        instance = MagicMock()

        async def fake_run():
            yield mock_result

        instance.run = fake_run
        instance.init = AsyncMock()
        instance.cleanup = AsyncMock()
        instance.stop = MagicMock()
        instance.on_event = MagicMock()
        MockEngine.return_value = instance

        worker = Worker(mock_config, pid_file=tmp_path / "test.pid")
        await worker.run()

    bug_files = list((vault_path / "bug-reports").glob("*.md"))
    patch_files = list((vault_path / "patches").glob("*.md"))

    assert len(bug_files) == 1, f"Expected 1 bug report file, found {len(bug_files)}"
    assert len(patch_files) == 1, f"Expected 1 patch file, found {len(patch_files)}"
    assert "sql-injection-in-login" in bug_files[0].name
    assert "parameterize-login-query" in patch_files[0].name


def test_worker_vault_config_respected(tmp_path):
    """Verify vault is enabled when config sets vault.enabled = True."""
    from wargames.models import (
        GameConfig, GameSettings, DraftSettings, DraftStyle,
        TeamsSettings, TeamSettings, OutputSettings, VaultOutput, DatabaseOutput,
    )

    config = GameConfig(
        game=GameSettings(name="test", rounds=1, turn_limit=2, score_threshold=10, phase_advance_score=5.0),
        draft=DraftSettings(picks_per_team=2, style=DraftStyle.SNAKE),
        teams=TeamsSettings(
            red=TeamSettings(name="R", model="http://x", model_name="m", temperature=0.5),
            blue=TeamSettings(name="B", model="http://x", model_name="m", temperature=0.5),
            judge=TeamSettings(name="J", model="http://x", model_name="m", temperature=0.2),
        ),
        output=OutputSettings(
            vault=VaultOutput(enabled=True, path=str(tmp_path / "vault")),
            database=DatabaseOutput(path=str(tmp_path / "db.sqlite")),
        ),
    )
    worker = Worker(config)
    assert worker.config.output.vault.enabled is True
