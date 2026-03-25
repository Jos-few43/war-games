from __future__ import annotations

from dataclasses import dataclass

from wargames.engine.loadouts import resolve_loadout
from wargames.models import (
    DraftPick,
    EnhancedDraftPick,
    EnhancedDraftState,
    ToolBan,
    ToolPool,
)


@dataclass
class Resource:
    name: str
    category: str  # "offensive", "defensive", "recon", "utility"
    description: str


class DraftPool:
    def __init__(self, resources: list[Resource]):
        self.resources = list(resources)
        self._drafted: set[str] = set()

    def available(self) -> list[Resource]:
        return [r for r in self.resources if r.name not in self._drafted]

    def pick(self, name: str) -> Resource:
        if name in self._drafted:
            raise ValueError(f"'{name}' already drafted")
        for r in self.resources:
            if r.name == name:
                self._drafted.add(name)
                return r
        raise ValueError(f"'{name}' not found in pool")

    @classmethod
    async def from_cves(cls, db, include_defaults: bool = True) -> DraftPool:
        """Build a draft pool that includes crawled CVEs as draftable resources."""
        cve_rows = await db.get_cves()
        cve_resources = [
            Resource(
                name=row['cve_id'],
                category='cve',
                description=row['description'][:200],
            )
            for row in cve_rows
        ]
        if include_defaults:
            base = cls.default()
            return cls(base.resources + cve_resources)
        return cls(cve_resources)

    @classmethod
    def default(cls) -> DraftPool:
        resources = [
            # Offensive
            Resource(
                'port_scanner',
                'offensive',
                'Scans target systems for open ports and running services.',
            ),
            Resource(
                'fuzzer',
                'offensive',
                'Sends malformed or unexpected inputs to discover vulnerabilities.',
            ),
            Resource(
                'sqli_kit',
                'offensive',
                'SQL injection toolkit for exploiting database query flaws.',
            ),
            Resource(
                'prompt_injector',
                'offensive',
                'Crafts adversarial prompts to manipulate LLM behavior.',
            ),
            Resource(
                'social_eng_kit',
                'offensive',
                'Phishing and pretexting tools for social engineering attacks.',
            ),
            Resource(
                'priv_esc_toolkit',
                'offensive',
                'Exploits misconfigured permissions to escalate privileges.',
            ),
            # Defensive
            Resource(
                'waf_rules',
                'defensive',
                'Web Application Firewall rules to block common attack patterns.',
            ),
            Resource(
                'ids_signatures',
                'defensive',
                'Intrusion Detection System signatures for known threats.',
            ),
            Resource(
                'input_sanitizer',
                'defensive',
                'Strips and validates user input to prevent injection attacks.',
            ),
            Resource(
                'rate_limiter',
                'defensive',
                'Throttles requests to prevent brute-force and DoS attempts.',
            ),
            Resource(
                'logging_alerting',
                'defensive',
                'Centralized logging and real-time alerting for anomalies.',
            ),
            Resource(
                'sandboxing',
                'defensive',
                'Isolates untrusted code execution in a restricted environment.',
            ),
            # Recon
            Resource(
                'cve_database', 'recon', 'Searchable database of known CVEs and exploit details.'
            ),
            Resource('network_mapper', 'recon', 'Maps network topology and identifies live hosts.'),
            Resource(
                'code_analyzer',
                'recon',
                'Static analysis tool for finding vulnerabilities in source code.',
            ),
            # Utility
            Resource(
                'extra_time', 'utility', 'Grants additional time to complete the current challenge.'
            ),
            Resource(
                'second_attempt',
                'utility',
                'Allows one retry on a failed attack or defense action.',
            ),
            Resource(
                'hint',
                'utility',
                'Reveals a partial hint about the target vulnerability or defense gap.',
            ),
        ]
        return cls(resources)


class DraftEngine:
    def __init__(self, picks_per_team: int, style: str):
        self.picks_per_team = picks_per_team
        self.style = style

    def draft_order(self) -> list[str]:
        """
        Snake draft order: round 1 goes R,B; round 2 reverses to B,R; etc.
        For picks_per_team=3 this yields: R, B, B, R, R, B
        """
        order: list[str] = []
        for round_num in range(self.picks_per_team):
            if round_num % 2 == 0:
                order.extend(['red', 'blue'])
            else:
                order.extend(['blue', 'red'])
        return order

    async def run(
        self,
        pool: DraftPool,
        red_llm,
        blue_llm,
        red_settings=None,
        blue_settings=None,
    ) -> tuple[list[DraftPick], list[DraftPick]]:
        # Check for loadouts early — skip LLM draft if configured
        red_loadout_picks: list[DraftPick] = []
        blue_loadout_picks: list[DraftPick] = []

        if red_settings is not None:
            red_loadout_picks = resolve_loadout(red_settings, team_name='red')
        if blue_settings is not None:
            blue_loadout_picks = resolve_loadout(blue_settings, team_name='blue')

        # Both teams have loadouts — skip LLM entirely
        if red_loadout_picks and blue_loadout_picks:
            return red_loadout_picks, blue_loadout_picks

        # One team has loadout — draft normally for the other
        if red_loadout_picks:
            blue_picks = await self._draft_for_team('blue', pool, blue_llm)
            return red_loadout_picks, blue_picks

        if blue_loadout_picks:
            red_picks = await self._draft_for_team('red', pool, red_llm)
            return red_picks, blue_loadout_picks

        # Neither team has loadout — normal snake draft
        red_picks: list[DraftPick] = []
        blue_picks: list[DraftPick] = []

        round_num = 1
        red_pick_num = 0
        blue_pick_num = 0

        for team in self.draft_order():
            llm = red_llm if team == 'red' else blue_llm
            available = pool.available()
            available_names = [r.name for r in available]

            prompt = (
                f'You are the {team} team. Choose one resource to draft.\n'
                f'Available resources: {", ".join(available_names)}\n'
                'Reply with only the resource name, nothing else.'
            )

            chosen = await llm.chat([{'role': 'user', 'content': prompt}])
            chosen = chosen.strip()

            # Validate; re-prompt once on bad pick
            if chosen not in available_names:
                chosen = await llm.chat([{'role': 'user', 'content': prompt}])
                chosen = chosen.strip()
                if chosen not in available_names:
                    # Fall back to first available
                    chosen = available_names[0]

            resource = pool.pick(chosen)

            pick = DraftPick(
                round=round_num,
                team=team,
                resource_name=resource.name,
                resource_category=resource.category,
            )

            if team == 'red':
                red_picks.append(pick)
                red_pick_num += 1
            else:
                blue_picks.append(pick)
                blue_pick_num += 1

            # Advance round number after each pair
            round_num += 1

        return red_picks, blue_picks

    async def _draft_for_team(self, team: str, pool: DraftPool, llm) -> list[DraftPick]:
        """Run an LLM draft for a single team (used when the other team has a loadout)."""
        picks: list[DraftPick] = []
        for round_num in range(1, self.picks_per_team + 1):
            available = pool.available()
            available_names = [r.name for r in available]

            prompt = (
                f'You are the {team} team. Choose one resource to draft.\n'
                f'Available resources: {", ".join(available_names)}\n'
                'Reply with only the resource name, nothing else.'
            )

            chosen = await llm.chat([{'role': 'user', 'content': prompt}])
            chosen = chosen.strip()

            if chosen not in available_names:
                chosen = await llm.chat([{'role': 'user', 'content': prompt}])
                chosen = chosen.strip()
                if chosen not in available_names:
                    chosen = available_names[0]

            resource = pool.pick(chosen)
            picks.append(
                DraftPick(
                    round=round_num,
                    team=team,
                    resource_name=resource.name,
                    resource_category=resource.category,
                )
            )

        return picks


class EnhancedDraftEngine:
    """Enhanced draft engine with ban phase and separate tool pools.

    Supports asymmetric gameplay where red and blue teams have access to
    different tool categories, and teams can ban tools before drafting.
    """

    def __init__(
        self,
        picks_per_team: int,
        bans_per_team: int = 1,
        style: str = 'snake',
    ):
        self.picks_per_team = picks_per_team
        self.bans_per_team = bans_per_team
        self.style = style
        self.red_pools: list[ToolPool] = []
        self.blue_pools: list[ToolPool] = []
        self.shared_pools: list[ToolPool] = []

    def add_pool(self, pool: ToolPool) -> None:
        """Add a tool pool to the draft."""
        if pool.team is None:
            self.shared_pools.append(pool)
        elif pool.team == 'red':
            self.red_pools.append(pool)
        elif pool.team == 'blue':
            self.blue_pools.append(pool)

    def get_available_tools(self, team: str) -> list[str]:
        """Get all available tools for a team, excluding banned ones."""
        tools: set[str] = set()

        if team == 'red':
            for pool in self.red_pools:
                tools.update(pool.available_tools)
        else:
            for pool in self.blue_pools:
                tools.update(pool.available_tools)

        for pool in self.shared_pools:
            tools.update(pool.available_tools)

        return sorted(list(tools))

    def _get_ban_order(self) -> list[str]:
        """Generate ban order: alternating red/blue."""
        order: list[str] = []
        for i in range(self.bans_per_team):
            order.extend(['red', 'blue'])
        return order

    def _get_draft_order(self) -> list[str]:
        """Generate snake draft order for picks."""
        order: list[str] = []
        for round_num in range(self.picks_per_team):
            if round_num % 2 == 0:
                order.extend(['red', 'blue'])
            else:
                order.extend(['blue', 'red'])
        return order

    async def run(
        self,
        red_llm,
        blue_llm,
        red_settings=None,
        blue_settings=None,
    ) -> EnhancedDraftState:
        """Run the enhanced draft with ban phase and asymmetric pools."""
        state = EnhancedDraftState(
            round=1,
            phase=1,
            current_turn='red',
            available_pools=self.red_pools + self.blue_pools + self.shared_pools,
        )

        red_loadout = resolve_loadout(red_settings, team_name='red') if red_settings else []
        blue_loadout = resolve_loadout(blue_settings, team_name='blue') if blue_settings else []

        if red_loadout and blue_loadout:
            for pick in red_loadout:
                state.red_picks.append(
                    EnhancedDraftPick(
                        round=pick.round,
                        team=pick.team,
                        resource_name=pick.resource_name,
                        resource_category=pick.resource_category,
                    )
                )
            for pick in blue_loadout:
                state.blue_picks.append(
                    EnhancedDraftPick(
                        round=pick.round,
                        team=pick.team,
                        resource_name=pick.resource_name,
                        resource_category=pick.resource_category,
                    )
                )
            return state

        banned_tools: set[str] = set()
        for team in self._get_ban_order():
            llm = red_llm if team == 'red' else blue_llm
            available = self.get_available_tools(team)
            available = [t for t in available if t not in banned_tools]

            if not available:
                continue

            prompt = (
                f"You are the {team} team. Choose one tool to BAN (remove from play).\n"
                f"Available tools: {', '.join(available)}\n"
                "Reply with only the tool name to ban, nothing else."
            )

            chosen = await llm.chat([{"role": "user", "content": prompt}])
            chosen = chosen.strip()

            if chosen not in available:
                chosen = await llm.chat([{"role": "user", "content": prompt}])
                chosen = chosen.strip()
                if chosen not in available:
                    chosen = available[0]

            banned_tools.add(chosen)
            ban = ToolBan(
                tool_name=chosen,
                banned_by=team,
                banned_at_round=state.round,
            )
            if team == "red":
                state.red_bans.append(ban)
            else:
                state.blue_bans.append(ban)

        for team in self._get_draft_order():
            llm = red_llm if team == 'red' else blue_llm
            available = self.get_available_tools(team)
            available = [t for t in available if t not in banned_tools]

            if not available:
                continue

            opponent_bans = state.blue_bans if team == 'red' else state.red_bans
            ban_info = (
                f"Opponent banned: {', '.join(b.tool_name for b in opponent_bans)}"
                if opponent_bans
                else "No bans from opponent"
            )

            prompt = (
                f"You are the {team} team. Choose one tool to draft.\n"
                f"Available tools: {', '.join(available)}\n"
                f"{ban_info}\n"
                "Reply with only the tool name, nothing else."
            )

            chosen = await llm.chat([{"role": "user", "content": prompt}])
            chosen = chosen.strip()

            if chosen not in available:
                chosen = await llm.chat([{"role": "user", "content": prompt}])
                chosen = chosen.strip()
                if chosen not in available:
                    chosen = available[0]

            category = 'unknown'
            for pool in state.available_pools:
                if chosen in pool.available_tools:
                    category = pool.category.value
                    break

            pick = EnhancedDraftPick(
                round=state.round,
                team=team,
                resource_name=chosen,
                resource_category=category,
            )

            if team == "red":
                state.red_picks.append(pick)
            else:
                state.blue_picks.append(pick)

            state.round += 1

        return state
