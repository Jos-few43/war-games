import pytest
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from wargames.worker import Worker


@pytest.mark.asyncio
async def test_worker_starts_and_stops(tmp_path):
    mock_config = MagicMock()
    mock_config.output.database.path = str(tmp_path / "test.db")
    mock_config.output.vault.enabled = False
    mock_config.game.rounds = 2

    mock_result = MagicMock(round_number=1)

    with patch("wargames.worker.GameEngine") as MockEngine:
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
