"""Swiss-system tournament pairing engine.

Implements the Swiss pairing algorithm: sort by points then rating,
group by win count, pair top-half vs bottom-half within each group,
and avoid rematches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import groupby


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
