import asyncio
import os
from pathlib import Path
from wargames.models import GameConfig
from wargames.engine.game import GameEngine
from wargames.output.vault import VaultWriter
from wargames.tui.bridge import EventBridge


class Worker:
    def __init__(self, config: GameConfig, pid_file: Path | None = None):
        self.config = config
        self.pid_file = pid_file or Path("~/.local/share/wargames/worker.pid").expanduser()
        self._engine: GameEngine | None = None
        self._vault: VaultWriter | None = None
        self._stop = False
        self._bridge = EventBridge()

    @property
    def bridge(self) -> EventBridge:
        return self._bridge

    def _write_pid(self):
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(os.getpid()))

    def _cleanup_pid(self):
        if self.pid_file.exists():
            self.pid_file.unlink()

    async def run(self):
        """Run the war games season."""
        self._write_pid()
        try:
            self._engine = GameEngine(self.config)
            await self._engine.init()
            self._engine.on_event(lambda etype, data: self._bridge.push(etype, data))

            if self.config.output.vault.enabled:
                vault_path = Path(self.config.output.vault.path).expanduser()
                self._vault = VaultWriter(vault_path)

            async for result in self._engine.run():
                if self._stop:
                    break
                if self._vault:
                    self._vault.write_round(result)
                    phase_name = result.phase.name.lower().replace("_", "-")
                    # Strategy vault output will be populated when strategies are extracted
                    self._vault.write_strategy_update(result.round_number, phase_name, [])
                    for bug in result.bug_reports:
                        self._vault.write_bug_report(bug)
                    for patch in result.patches:
                        self._vault.write_patch(patch)
        except asyncio.CancelledError:
            pass
        finally:
            if self._engine:
                await self._engine.cleanup()
            self._cleanup_pid()

    def stop(self):
        self._stop = True
        if self._engine:
            self._engine.stop()

    def pause(self):
        if self._engine:
            self._engine.pause()

    def resume(self):
        if self._engine:
            self._engine.resume()
