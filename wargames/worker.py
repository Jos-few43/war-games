import asyncio
import logging
import os
from pathlib import Path
from wargames.models import GameConfig
from wargames.engine.game import GameEngine
from wargames.output.vault import VaultWriter
from wargames.tui.bridge import EventBridge

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, config: GameConfig, pid_file: Path | None = None):
        self.config = config
        self.pid_file = pid_file or Path("~/.local/share/wargames/worker.pid").expanduser()
        self._engine: GameEngine | None = None
        self._vault: VaultWriter | None = None
        self._stop = False
        self._bridge = EventBridge()
        self._resmgr = None

    @property
    def bridge(self) -> EventBridge:
        return self._bridge

    def _write_pid(self):
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(os.getpid()))

    def _cleanup_pid(self):
        if self.pid_file.exists():
            self.pid_file.unlink()

    async def _init_resmgr(self):
        """Try to connect to resmgr daemon. Gracefully degrades if unavailable."""
        try:
            from resmgr.client import ResmgrClient
            client = ResmgrClient()
            if await client.is_available():
                self._resmgr = client
                # Register this worker process
                await client.request_spawn(
                    team="system", role="wargames-worker",
                    priority=8, pid=os.getpid(),
                )
        except ImportError:
            pass  # resmgr not installed, continue without it

    async def _check_resources(self) -> bool:
        """Check if resources are OK to continue. Returns True if OK."""
        if not self._resmgr:
            return True
        status = await self._resmgr.status()
        ram_pct = status.get("ram_used_pct", 0)
        vram_mb = status.get("vram_used_mb", 0)
        vram_total = status.get("vram_total_mb", 6144)
        # Auto-pause if RAM > 90% or VRAM > 90%
        if ram_pct > 90 or (vram_total > 0 and vram_mb / vram_total > 0.9):
            return False
        return True

    async def run(self):
        """Run the war games season."""
        self._write_pid()
        try:
            await self._init_resmgr()

            self._engine = GameEngine(self.config)
            await self._engine.init()
            self._engine.on_event(lambda etype, data: self._bridge.push(etype, data))

            if self.config.output and self.config.output.vault.enabled:
                vault_path = Path(self.config.output.vault.path).expanduser()
                self._vault = VaultWriter(vault_path)

            async for result in self._engine.run():
                if self._stop:
                    break

                # Check resources before next round
                if not await self._check_resources():
                    self._bridge.push("resource_warning", {
                        "message": "Resources critical, pausing simulation",
                    })
                    self._engine.pause()
                    # Wait for resources to recover (check every 10s)
                    while not await self._check_resources():
                        await asyncio.sleep(10)
                    self._engine.resume()
                    self._bridge.push("resource_recovered", {
                        "message": "Resources recovered, resuming simulation",
                    })

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
        except Exception as exc:
            logger.error("Worker crashed: %s", exc, exc_info=True)
            self._bridge.push("worker_error", {"error": str(exc)})
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
