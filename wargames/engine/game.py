"""Game engine module for War Games competition framework.

This module contains the main GameEngine class that orchestrates a complete
season of red team vs blue team LLM competitions. Handles phase progression,
strategy evolution, ELO ratings, and database persistence.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path

from wargames.engine.draft import DraftEngine
from wargames.engine.elo import calculate_elo
from wargames.engine.judge import Judge
from wargames.engine.round import RoundEngine
from wargames.engine.strategy import (
    extract_strategies,
    get_top_strategies,
    prune_strategies,
    save_strategies,
    update_win_rates,
)
from wargames.llm.client import LLMClient
from wargames.models import GameConfig, MatchOutcome, Phase, RoundResult
from wargames.output.db import Database
from wargames.teams.blue import BlueTeamAgent
from wargames.teams.red import RedTeamAgent

logger = logging.getLogger(__name__)


class GameEngine:
    """Orchestrates a complete season of red team vs blue team competitions.

    The GameEngine manages the full game lifecycle including initialization,
    round execution, phase advancement, strategy evolution, ELO rating updates,
    and cleanup. It yields results asynchronously for real-time TUI updates.

    Attributes:
        config: Game configuration containing rounds, scoring, and team settings.
        db: Database instance for persisting game state.
    """

    def __init__(self, config: GameConfig):
        """Initialize the game engine with configuration.

        Args:
            config: GameConfig containing all game settings including teams,
                scoring profiles, phase advancement thresholds, and output paths.
        """
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
        self._season_id: str = ''

    def on_event(self, callback):
        """Set event callback for live TUI updates.

        Args:
            callback: Callable accepting (event_type: str, data: dict) for
                broadcasting events like round completion, attacks, and defenses.
        """
        self._on_event = callback

    async def init(self):
        """Initialize database and LLM clients.

        Creates the database directory if needed, initializes the SQLite
        database, generates a season ID, and creates LLM clients for each team.

        Raises:
            OSError: If database directory creation fails.
            aiosqlite.Error: If database initialization fails.
        """
        db_path = Path(self.config.output.database.path).expanduser()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = Database(db_path)
        await self.db.init()

        # Generate and persist a new season record
        self._season_id = str(uuid.uuid4())[:8]
        started_at = datetime.now(UTC).isoformat()
        await self.db.save_season(
            season_id=self._season_id,
            config_name=self.config.game.name,
            started_at=started_at,
        )

        self._red_client = LLMClient(self.config.teams.red)
        self._blue_client = LLMClient(self.config.teams.blue)
        self._judge_client = LLMClient(self.config.teams.judge)

    async def run(self) -> AsyncGenerator[RoundResult, None]:
        """Run the complete season, yielding results round by round.

        Executes rounds sequentially, handling draft, combat, debrief, strategy
        extraction, ELO updates, and phase advancement. Yields after each round
        for real-time TUI updates.

        Yields:
            RoundResult: Complete result of each round including scores,
                attacks, defenses, debriefs, and outcome.

        Raises:
            Exception: Round failures are logged and skipped; does not stop
                the season unless stop() is called.
        """
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
                red=red_agent,
                blue=blue_agent,
                judge=judge,
                draft_engine=draft_engine,
                db=self.db,
                turn_limit=self.config.game.turn_limit,
                score_threshold=self.config.game.score_threshold,
                scoring=self.config.scoring,
            )

            if self._on_event:
                round_engine.on_event(self._on_event)

            # Load top strategies for current phase before each round
            red_top = await get_top_strategies(
                'red', self._current_phase.value, self.db, current_round=round_num
            )
            blue_top = await get_top_strategies(
                'blue', self._current_phase.value, self.db, current_round=round_num
            )
            red_strat_texts = [s.content for s in red_top]
            blue_strat_texts = [s.content for s in blue_top]
            red_used_ids = [s.id for s in red_top if s.id is not None]
            blue_used_ids = [s.id for s in blue_top if s.id is not None]

            try:
                result = await round_engine.play(
                    round_number=round_num,
                    phase=self._current_phase,
                    red_lessons=red_lessons,
                    blue_lessons=blue_lessons,
                    red_strategies=red_strat_texts,
                    blue_strategies=blue_strat_texts,
                    red_settings=self.config.teams.red,
                    blue_settings=self.config.teams.blue,
                )
            except Exception as exc:
                logger.error('Round %d failed: %s — skipping to next round', round_num, exc)
                if self._on_event:
                    self._on_event(
                        'round_error',
                        {
                            'round': round_num,
                            'error': str(exc),
                        },
                    )
                continue

            # Track scores for phase advancement
            self._round_scores.append(float(result.red_score))

            # Update lessons from debriefs
            if result.red_debrief:
                blue_lessons.append(result.red_debrief[:500])
            if result.blue_debrief:
                red_lessons.append(result.blue_debrief[:500])

            won_red = result.outcome in (
                MatchOutcome.RED_WIN,
                MatchOutcome.RED_AUTO_WIN,
                MatchOutcome.RED_CRITICAL_WIN,
            )

            # Extract and save strategies, then update win rates and opponent modeling
            try:
                red_strats = await extract_strategies(result, 'red', self._judge_client)
                blue_strats = await extract_strategies(result, 'blue', self._judge_client)
                await save_strategies(red_strats + blue_strats, self.db)
                await update_win_rates(strategy_ids=red_used_ids, round_won=won_red, db=self.db)
                await update_win_rates(
                    strategy_ids=blue_used_ids, round_won=not won_red, db=self.db
                )

                # Update opponent modeling: track how opponent's strategies performed
                # For red team's perspective: track how blue's strategies performed against red
                # For blue team's perspective: track how red's strategies performed against blue
                await self._update_opponent_modeling(red_used_ids, blue_used_ids, won_red, self.db)

                await prune_strategies('red', self._current_phase.value, self.db)
                await prune_strategies('blue', self._current_phase.value, self.db)
            except Exception as exc:
                logger.warning('Strategy extraction failed for round %d: %s', round_num, exc)

            # Update ELO ratings for both models
            try:
                red_model = self.config.teams.red.model_name
                blue_model = self.config.teams.blue.model_name

                red_row = await self.db.get_model_rating(red_model)
                blue_row = await self.db.get_model_rating(blue_model)

                red_rating = red_row['rating'] if red_row else 1500.0
                blue_rating = blue_row['rating'] if blue_row else 1500.0
                red_wins = red_row['wins'] if red_row else 0
                red_losses = red_row['losses'] if red_row else 0
                red_draws = red_row['draws'] if red_row else 0
                blue_wins = blue_row['wins'] if blue_row else 0
                blue_losses = blue_row['losses'] if blue_row else 0
                blue_draws = blue_row['draws'] if blue_row else 0

                is_draw = result.outcome == MatchOutcome.TIMEOUT

                if is_draw:
                    new_red_rating, new_blue_rating = calculate_elo(
                        red_rating, blue_rating, draw=True
                    )
                    red_draws += 1
                    blue_draws += 1
                elif won_red:
                    new_red_rating, new_blue_rating = calculate_elo(red_rating, blue_rating)
                    red_wins += 1
                    blue_losses += 1
                else:
                    new_blue_rating, new_red_rating = calculate_elo(blue_rating, red_rating)
                    blue_wins += 1
                    red_losses += 1

                await self.db.save_model_rating(
                    red_model, new_red_rating, red_wins, red_losses, red_draws
                )
                await self.db.save_model_rating(
                    blue_model, new_blue_rating, blue_wins, blue_losses, blue_draws
                )
            except Exception as exc:
                logger.warning('ELO update failed for round %d: %s', round_num, exc)

            # Save token usage
            try:
                costs = self.config.costs.rates if self.config.costs else {}
                for team_name, client in [
                    ('red', self._red_client),
                    ('blue', self._blue_client),
                    ('judge', self._judge_client),
                ]:
                    usage = client.get_usage(reset=True)
                    model = usage['model_used']
                    rate = costs.get(model, 0.0)
                    total_tokens = usage['prompt_tokens'] + usage['completion_tokens']
                    cost = (total_tokens / 1000.0) * rate
                    await self.db.save_token_usage(
                        round_number=round_num,
                        team=team_name,
                        prompt_tokens=usage['prompt_tokens'],
                        completion_tokens=usage['completion_tokens'],
                        model_used=model,
                        cost=cost,
                    )
            except Exception as exc:
                logger.warning('Token usage tracking failed for round %d: %s', round_num, exc)

            # Check phase advancement
            new_phase = self._check_phase_advance(self._current_phase)
            if new_phase != self._current_phase:
                self._current_phase = new_phase

            yield result

    def _check_phase_advance(self, current_phase: Phase) -> Phase:
        """Check if average scores warrant advancing to next phase.

        Args:
            current_phase: The current game phase.

        Returns:
            The next phase if advancement threshold is met, otherwise
            the current phase.
        """
        min_rounds = self.config.scoring.phase_advance.min_rounds
        min_avg = self.config.scoring.phase_advance.min_avg_score
        if len(self._round_scores) < min_rounds:
            return current_phase

        recent_avg = sum(self._round_scores[-min_rounds:]) / min_rounds
        if recent_avg >= min_avg:
            phase_order = [
                Phase.PROMPT_INJECTION,
                Phase.CODE_VULNS,
                Phase.REAL_CVES,
                Phase.OPEN_ENDED,
            ]
            current_idx = phase_order.index(current_phase)
            if current_idx < len(phase_order) - 1:
                return phase_order[current_idx + 1]
        return current_phase

    def pause(self):
        """Pause the game loop.

        Blocks the run() generator until resume() is called.
        """
        self._pause_event.clear()

    def resume(self):
        """Resume a paused game loop.

        Unblocks the run() generator to continue round execution.
        """
        self._pause_event.set()

    def stop(self):
        """Stop the game loop completely.

        Signals the run() generator to exit after the current round.
        Also unblocks if currently paused.
        """
        self._stop = True
        self._pause_event.set()  # Unblock if paused

    async def _update_opponent_modeling(
        self, red_used_ids: list[int], blue_used_ids: list[int], red_won: bool, db
    ) -> None:
        """Update opponent modeling: track how opponent's strategies performed."""
        # Update blue team's perspective on red team's strategies
        for strategy_id in red_used_ids:
            # Get the strategy to check current opponent modeling values
            cursor = await db._conn.execute(
                'SELECT opp_usage_count, opp_effectiveness FROM strategies WHERE id = ?',
                (strategy_id,),
            )
            row = await cursor.fetchone()
            if row:
                old_opp_usage = row['opp_usage_count'] or 0
                old_opp_effectiveness = row['opp_effectiveness'] or 0.0

                # Increment opponent usage count
                new_opp_usage = old_opp_usage + 1

                # Update opponent effectiveness:
                # If red won, blue's defense was less effective (lower effectiveness)
                # If red lost, blue's defense was more effective (higher effectiveness)
                # Using incremental averaging similar to TD learning
                new_opp_effectiveness = old_opp_effectiveness + 0.1 * (
                    0.0 if red_won else 1.0 - old_opp_effectiveness
                )

                await db._conn.execute(
                    """UPDATE strategies
                       SET opp_usage_count = ?, opp_effectiveness = ?
                       WHERE id = ?""",
                    (new_opp_usage, new_opp_effectiveness, strategy_id),
                )

        # Update red team's perspective on blue team's strategies
        for strategy_id in blue_used_ids:
            # Get the strategy to check current opponent modeling values
            cursor = await db._conn.execute(
                'SELECT opp_usage_count, opp_effectiveness FROM strategies WHERE id = ?',
                (strategy_id,),
            )
            row = await cursor.fetchone()
            if row:
                old_opp_usage = row['opp_usage_count'] or 0
                old_opp_effectiveness = row['opp_effectiveness'] or 0.0

                # Increment opponent usage count
                new_opp_usage = old_opp_usage + 1

                # Update opponent effectiveness:
                # If blue won (red lost), red's offense was less effective
                # If blue lost (red won), red's offense was more effective
                new_opp_effectiveness = old_opp_effectiveness + 0.1 * (
                    0.0 if not red_won else 1.0 - old_opp_effectiveness
                )

                await db._conn.execute(
                    """UPDATE strategies
                       SET opp_usage_count = ?, opp_effectiveness = ?
                       WHERE id = ?""",
                    (new_opp_usage, new_opp_effectiveness, strategy_id),
                )
        await db._conn.commit()

    async def cleanup(self):
        """Close all resources and finalize the season.

        Closes LLM clients and database connection. Records final season
        statistics including winner determination.

        Raises:
            Exception: Logs warning if season finalization fails.
        """
        if self._red_client:
            await self._red_client.close()
        if self._blue_client:
            await self._blue_client.close()
        if self._judge_client:
            await self._judge_client.close()
        if self.db and self._season_id:
            try:
                stats = await self.db.get_season_stats()
                if stats['red_wins'] > stats['blue_wins']:
                    winner = self.config.teams.red.model_name
                elif stats['blue_wins'] > stats['red_wins']:
                    winner = self.config.teams.blue.model_name
                else:
                    winner = 'draw'
                ended_at = datetime.now(UTC).isoformat()
                await self.db.end_season(
                    season_id=self._season_id,
                    ended_at=ended_at,
                    winner=winner,
                )
            except Exception as exc:
                logger.warning('Failed to finalize season %s: %s', self._season_id, exc)
        if self.db:
            await self.db.close()
