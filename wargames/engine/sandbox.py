"""Sandbox mode: single-round execution with no database or season state."""
from __future__ import annotations

import logging

from wargames.engine.draft import DraftEngine
from wargames.engine.judge import Judge
from wargames.engine.round import RoundEngine
from wargames.llm.client import LLMClient
from wargames.models import GameConfig, Phase, RoundResult
from wargames.teams.blue import BlueTeamAgent
from wargames.teams.red import RedTeamAgent

logger = logging.getLogger(__name__)


class SandboxRunner:
    """Single-round sandbox executor. No DB, no season, no strategies."""

    def __init__(self, config: GameConfig):
        self.config = config

    async def run(self, loadout_overrides: dict[str, str] | None = None) -> RoundResult:
        """Run one round and return the result.

        Args:
            loadout_overrides: Optional mapping of team name to loadout preset,
                e.g. ``{"red": "aggressive", "blue": "defensive"}``.
        """
        # Apply loadout overrides to a copy of the team settings.
        config = self.config
        if loadout_overrides:
            red_loadout = loadout_overrides.get("red")
            blue_loadout = loadout_overrides.get("blue")
            if red_loadout is not None:
                config.teams.red.loadout = red_loadout
                logger.debug("Sandbox: red loadout overridden to %r", red_loadout)
            if blue_loadout is not None:
                config.teams.blue.loadout = blue_loadout
                logger.debug("Sandbox: blue loadout overridden to %r", blue_loadout)

        red_client: LLMClient | None = None
        blue_client: LLMClient | None = None
        judge_client: LLMClient | None = None

        try:
            red_client = LLMClient(config.teams.red)
            blue_client = LLMClient(config.teams.blue)
            judge_client = LLMClient(config.teams.judge)

            red_agent = RedTeamAgent(red_client)
            blue_agent = BlueTeamAgent(blue_client)
            judge = Judge(judge_client)

            draft_engine = DraftEngine(
                picks_per_team=config.draft.picks_per_team,
                style=config.draft.style,
            )

            round_engine = RoundEngine(
                red=red_agent,
                blue=blue_agent,
                judge=judge,
                draft_engine=draft_engine,
                db=None,  # no persistence in sandbox mode
                turn_limit=config.game.turn_limit,
                score_threshold=config.game.score_threshold,
            )

            # Determine settings objects to pass to play() so that loadouts
            # (if any) are honoured during the draft phase.
            red_settings = config.teams.red if config.teams.red.loadout or config.teams.red.loadout_custom else None
            blue_settings = config.teams.blue if config.teams.blue.loadout or config.teams.blue.loadout_custom else None

            result = await round_engine.play(
                round_number=1,
                phase=Phase.PROMPT_INJECTION,
                red_settings=red_settings,
                blue_settings=blue_settings,
            )
            return result

        finally:
            for client in (red_client, blue_client, judge_client):
                if client is not None:
                    await client.close()
