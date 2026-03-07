import asyncio
import logging
from pathlib import Path
from collections.abc import AsyncGenerator
from wargames.models import GameConfig, Phase, RoundResult, MatchOutcome
from wargames.output.db import Database
from wargames.llm.client import LLMClient
from wargames.teams.red import RedTeamAgent
from wargames.teams.blue import BlueTeamAgent
from wargames.engine.judge import Judge
from wargames.engine.draft import DraftEngine
from wargames.engine.round import RoundEngine
from wargames.engine.strategy import extract_strategies, save_strategies, get_top_strategies, update_win_rates

logger = logging.getLogger(__name__)


class GameEngine:
    def __init__(self, config: GameConfig):
        self.config = config
        self.db: Database | None = None
        self._red_client: LLMClient | None = None
        self._blue_client: LLMClient | None = None
        self._judge_client: LLMClient | None = None
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused initially
        self._stop = False
        self._round_scores: list[float] = []
        self._current_phase = Phase.PROMPT_INJECTION
        self._current_round = 0
        self._on_event = None

    def on_event(self, callback):
        """Set event callback for live updates."""
        self._on_event = callback

    async def init(self):
        """Initialize database and LLM clients."""
        db_path = Path(self.config.output.database.path).expanduser()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = Database(db_path)
        await self.db.init()

        self._red_client = LLMClient(self.config.teams.red)
        self._blue_client = LLMClient(self.config.teams.blue)
        self._judge_client = LLMClient(self.config.teams.judge)

    async def run(self) -> AsyncGenerator[RoundResult, None]:
        """Run the season, yielding results round by round."""
        red_agent = RedTeamAgent(self._red_client)
        blue_agent = BlueTeamAgent(self._blue_client)
        judge = Judge(self._judge_client)
        draft_engine = DraftEngine(
            picks_per_team=self.config.draft.picks_per_team,
            style=self.config.draft.style.value,
        )

        red_lessons = []
        blue_lessons = []

        for round_num in range(1, self.config.game.rounds + 1):
            if self._stop:
                break

            # Wait if paused
            await self._pause_event.wait()

            self._current_round = round_num

            round_engine = RoundEngine(
                red=red_agent, blue=blue_agent, judge=judge,
                draft_engine=draft_engine, db=self.db,
                turn_limit=self.config.game.turn_limit,
                score_threshold=self.config.game.score_threshold,
            )

            if self._on_event:
                round_engine.on_event(self._on_event)

            # Load top strategies for current phase before each round
            red_top = await get_top_strategies("red", self._current_phase.value, self.db)
            blue_top = await get_top_strategies("blue", self._current_phase.value, self.db)
            red_strat_texts = [s.content for s in red_top]
            blue_strat_texts = [s.content for s in blue_top]

            try:
                result = await round_engine.play(
                    round_number=round_num,
                    phase=self._current_phase,
                    red_lessons=red_lessons,
                    blue_lessons=blue_lessons,
                    red_strategies=red_strat_texts,
                    blue_strategies=blue_strat_texts,
                )
            except Exception as exc:
                logger.error("Round %d failed: %s — skipping to next round", round_num, exc)
                if self._on_event:
                    self._on_event("round_error", {
                        "round": round_num, "error": str(exc),
                    })
                continue

            # Track scores for phase advancement
            self._round_scores.append(float(result.red_score))

            # Update lessons from debriefs
            if result.red_debrief:
                blue_lessons.append(result.red_debrief[:500])
            if result.blue_debrief:
                red_lessons.append(result.blue_debrief[:500])

            # Extract and save strategies, then update win rates
            try:
                red_strats = await extract_strategies(result, "red", self._judge_client)
                blue_strats = await extract_strategies(result, "blue", self._judge_client)
                await save_strategies(red_strats + blue_strats, self.db)
                won_red = result.outcome in (MatchOutcome.RED_WIN, MatchOutcome.RED_AUTO_WIN)
                await update_win_rates("red", self._current_phase.value, won_red, self.db)
                await update_win_rates("blue", self._current_phase.value, not won_red, self.db)
            except Exception as exc:
                logger.warning("Strategy extraction failed for round %d: %s", round_num, exc)

            # Check phase advancement
            new_phase = self._check_phase_advance(self._current_phase)
            if new_phase != self._current_phase:
                self._current_phase = new_phase

            yield result

    def _check_phase_advance(self, current_phase: Phase) -> Phase:
        """Check if average scores warrant advancing to next phase."""
        if len(self._round_scores) < 10:
            return current_phase

        recent_avg = sum(self._round_scores[-10:]) / 10
        if recent_avg >= self.config.game.phase_advance_score:
            phase_order = [Phase.PROMPT_INJECTION, Phase.CODE_VULNS, Phase.REAL_CVES, Phase.OPEN_ENDED]
            current_idx = phase_order.index(current_phase)
            if current_idx < len(phase_order) - 1:
                return phase_order[current_idx + 1]
        return current_phase

    def pause(self):
        self._pause_event.clear()

    def resume(self):
        self._pause_event.set()

    def stop(self):
        self._stop = True
        self._pause_event.set()  # Unblock if paused

    async def cleanup(self):
        """Close all resources."""
        if self._red_client:
            await self._red_client.close()
        if self._blue_client:
            await self._blue_client.close()
        if self._judge_client:
            await self._judge_client.close()
        if self.db:
            await self.db.close()
