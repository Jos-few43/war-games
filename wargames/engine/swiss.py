"""Swiss-system tournament pairing engine.

Implements the Swiss pairing algorithm: sort by points then rating,
group by win count, pair top-half vs bottom-half within each group,
and avoid rematches.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from itertools import groupby

from wargames.models import (
    DraftSettings,
    DraftStyle,
    GameConfig,
    GameSettings,
    MatchOutcome,
    ModelEntry,
    Phase,
    TeamSettings,
    TeamsSettings,
    TournamentConfig,
)
from wargames.engine.elo import calculate_elo


@dataclass
class StandingsEntry:
    """A single player's tournament standing."""

    name: str
    wins: int = 0
    losses: int = 0
    draws: int = 0
    rating: float = 1500.0
    played_against: set[str] = field(default_factory=set)

    @property
    def points(self) -> float:
        return self.wins + self.draws * 0.5


def swiss_pair(
    standings: list[StandingsEntry],
) -> list[tuple[StandingsEntry, StandingsEntry]]:
    """Pair players using the Swiss system.

    Algorithm:
    1. Sort by wins descending, then rating descending.
    2. Group by win count.
    3. Within each group, pair top half vs bottom half.
    4. Skip rematches; try alternative partners from the same group.
    5. Odd player out gets a bye (omitted from returned pairs).
    6. Unpaired players overflow into the next group.

    Returns a list of (player_a, player_b) tuples.
    """
    sorted_players = sorted(
        standings, key=lambda e: (e.wins, e.rating), reverse=True
    )

    groups: list[list[StandingsEntry]] = []
    for _, group_iter in groupby(sorted_players, key=lambda e: e.wins):
        groups.append(list(group_iter))

    pairs: list[tuple[StandingsEntry, StandingsEntry]] = []
    overflow: list[StandingsEntry] = []

    for group in groups:
        pool = overflow + group
        overflow = []

        paired_in_group: set[str] = set()
        group_pairs: list[tuple[StandingsEntry, StandingsEntry]] = []

        mid = len(pool) // 2
        top_half = pool[:mid]
        bottom_half = pool[mid:]

        for player in top_half:
            if player.name in paired_in_group:
                continue

            partner = _find_partner(player, bottom_half, paired_in_group)
            if partner is None:
                # Try finding a partner in the top half as fallback.
                partner = _find_partner(player, top_half, paired_in_group)

            if partner is not None:
                group_pairs.append((player, partner))
                paired_in_group.add(player.name)
                paired_in_group.add(partner.name)

        # Any remaining unpaired from bottom half try to pair among themselves.
        unpaired_bottom = [
            p for p in bottom_half if p.name not in paired_in_group
        ]
        i = 0
        while i < len(unpaired_bottom) - 1:
            a = unpaired_bottom[i]
            if a.name in paired_in_group:
                i += 1
                continue
            partner = _find_partner(
                a, unpaired_bottom[i + 1 :], paired_in_group
            )
            if partner is not None:
                group_pairs.append((a, partner))
                paired_in_group.add(a.name)
                paired_in_group.add(partner.name)
            i += 1

        pairs.extend(group_pairs)

        # Collect everyone who wasn't paired — they overflow.
        for p in pool:
            if p.name not in paired_in_group:
                overflow.append(p)

    # Overflow after all groups = bye candidates (lowest rated, unpaired).
    # They simply don't appear in the pairs list.
    return pairs


def _find_partner(
    player: StandingsEntry,
    candidates: list[StandingsEntry],
    already_paired: set[str],
) -> StandingsEntry | None:
    """Find the first valid partner for *player* among *candidates*."""
    for candidate in candidates:
        if candidate.name == player.name:
            continue
        if candidate.name in already_paired:
            continue
        if candidate.name in player.played_against:
            continue
        return candidate
    return None


logger = logging.getLogger(__name__)


class TournamentRunner:
    """Runs a Swiss-system tournament using SandboxRunner for individual games."""

    def __init__(self, config: TournamentConfig, db=None):
        self.config = config
        self.db = db
        self.standings: dict[str, StandingsEntry] = {}

        for model in config.models:
            self.standings[model.name] = StandingsEntry(
                name=model.name,
                rating=1500.0,
            )

    def _model_by_name(self, name: str) -> ModelEntry:
        for m in self.config.models:
            if m.name == name:
                return m
        raise ValueError(f"Model {name!r} not found in roster")

    def _build_game_config(
        self, red: ModelEntry, blue: ModelEntry, judge: ModelEntry,
    ) -> GameConfig:
        """Build a GameConfig for a single game between two models."""
        return GameConfig(
            game=GameSettings(
                name=f"{red.name}-vs-{blue.name}",
                rounds=self.config.game_rounds,
                turn_limit=self.config.turn_limit,
                score_threshold=self.config.score_threshold,
                phase_advance_score=999.0,
            ),
            draft=DraftSettings(picks_per_team=3, style=DraftStyle.SNAKE),
            teams=TeamsSettings(
                red=TeamSettings(
                    name=red.name,
                    model=red.endpoint,
                    model_name=red.model_name,
                    temperature=red.temperature,
                    timeout=red.timeout,
                    api_key=red.api_key,
                ),
                blue=TeamSettings(
                    name=blue.name,
                    model=blue.endpoint,
                    model_name=blue.model_name,
                    temperature=blue.temperature,
                    timeout=blue.timeout,
                    api_key=blue.api_key,
                ),
                judge=TeamSettings(
                    name="judge",
                    model=judge.endpoint,
                    model_name=judge.model_name,
                    temperature=0.2,
                    timeout=judge.timeout,
                    api_key=judge.api_key,
                ),
            ),
        )

    async def _play_game(
        self, red: ModelEntry, blue: ModelEntry,
    ) -> tuple[int, int, str]:
        """Play a single game. Returns (red_score, blue_score, outcome)."""
        from wargames.engine.sandbox import SandboxRunner

        red_rating = self.standings[red.name].rating
        blue_rating = self.standings[blue.name].rating
        judge = red if red_rating >= blue_rating else blue

        if self.config.judge_model:
            judge = self._model_by_name(self.config.judge_model)

        config = self._build_game_config(red, blue, judge)
        runner = SandboxRunner(config)
        result = await runner.run()

        return result.red_score, result.blue_score, result.outcome.value

    async def _play_match(
        self, p1: StandingsEntry, p2: StandingsEntry, swiss_round: int,
    ) -> str:
        """Play a match (N games with role swaps). Returns 'p1', 'p2', or 'draw'."""
        m1 = self._model_by_name(p1.name)
        m2 = self._model_by_name(p2.name)

        p1_game_wins = 0
        p2_game_wins = 0

        for game_num in range(self.config.games_per_match):
            if game_num % 2 == 0:
                red, blue = m1, m2
                red_name, blue_name = p1.name, p2.name
            else:
                red, blue = m2, m1
                red_name, blue_name = p2.name, p1.name

            red_score, blue_score, outcome = await self._play_game(red, blue)
            logger.info(
                "  %s (Red) vs %s (Blue) -> %s (%d-%d)",
                red_name, blue_name, outcome, red_score, blue_score,
            )

            if self.db:
                await self.db.save_tournament_match(
                    tournament_name=self.config.name,
                    swiss_round=swiss_round,
                    red_model=red_name,
                    blue_model=blue_name,
                    red_score=red_score,
                    blue_score=blue_score,
                    outcome=outcome,
                )

            won_red = outcome in ("red_win", "red_auto_win", "red_critical_win")
            won_blue = outcome in ("blue_win", "blue_decisive_win")
            if won_red:
                if red_name == p1.name:
                    p1_game_wins += 1
                else:
                    p2_game_wins += 1
            elif won_blue:
                if blue_name == p1.name:
                    p1_game_wins += 1
                else:
                    p2_game_wins += 1
            # else: timeout — no game win awarded

        if p1_game_wins > p2_game_wins:
            return "p1"
        elif p2_game_wins > p1_game_wins:
            return "p2"
        return "draw"

    async def run(self) -> list[StandingsEntry]:
        """Run the full tournament. Returns final standings sorted by rating."""
        for swiss_round in range(1, self.config.rounds + 1):
            logger.info("Swiss Round %d/%d", swiss_round, self.config.rounds)

            standings_list = sorted(
                self.standings.values(),
                key=lambda s: (-s.wins, -s.rating),
            )
            pairs = swiss_pair(standings_list)

            for p1, p2 in pairs:
                logger.info("Match: %s vs %s", p1.name, p2.name)
                match_result = await self._play_match(p1, p2, swiss_round)

                p1.played_against.add(p2.name)
                p2.played_against.add(p1.name)

                if match_result == "p1":
                    p1.wins += 1
                    p2.losses += 1
                    new_p1_r, new_p2_r = calculate_elo(p1.rating, p2.rating)
                elif match_result == "p2":
                    p2.wins += 1
                    p1.losses += 1
                    new_p2_r, new_p1_r = calculate_elo(p2.rating, p1.rating)
                else:
                    p1.draws += 1
                    p2.draws += 1
                    new_p1_r, new_p2_r = calculate_elo(
                        p1.rating, p2.rating, draw=True,
                    )

                p1.rating = new_p1_r
                p2.rating = new_p2_r

                if self.db:
                    await self.db.save_model_rating(
                        p1.name, p1.rating, p1.wins, p1.losses, p1.draws,
                    )
                    await self.db.save_model_rating(
                        p2.name, p2.rating, p2.wins, p2.losses, p2.draws,
                    )

                logger.info(
                    "  Result: %s (ELO: %.0f) vs %s (ELO: %.0f)",
                    p1.name, p1.rating,
                    p2.name, p2.rating,
                )

        return sorted(self.standings.values(), key=lambda s: (-s.points, -s.rating))
