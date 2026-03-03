from __future__ import annotations

from dataclasses import dataclass

from wargames.models import DraftPick


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
    def default(cls) -> "DraftPool":
        resources = [
            # Offensive
            Resource("port_scanner", "offensive", "Scans target systems for open ports and running services."),
            Resource("fuzzer", "offensive", "Sends malformed or unexpected inputs to discover vulnerabilities."),
            Resource("sqli_kit", "offensive", "SQL injection toolkit for exploiting database query flaws."),
            Resource("prompt_injector", "offensive", "Crafts adversarial prompts to manipulate LLM behavior."),
            Resource("social_eng_kit", "offensive", "Phishing and pretexting tools for social engineering attacks."),
            Resource("priv_esc_toolkit", "offensive", "Exploits misconfigured permissions to escalate privileges."),
            # Defensive
            Resource("waf_rules", "defensive", "Web Application Firewall rules to block common attack patterns."),
            Resource("ids_signatures", "defensive", "Intrusion Detection System signatures for known threats."),
            Resource("input_sanitizer", "defensive", "Strips and validates user input to prevent injection attacks."),
            Resource("rate_limiter", "defensive", "Throttles requests to prevent brute-force and DoS attempts."),
            Resource("logging_alerting", "defensive", "Centralized logging and real-time alerting for anomalies."),
            Resource("sandboxing", "defensive", "Isolates untrusted code execution in a restricted environment."),
            # Recon
            Resource("cve_database", "recon", "Searchable database of known CVEs and exploit details."),
            Resource("network_mapper", "recon", "Maps network topology and identifies live hosts."),
            Resource("code_analyzer", "recon", "Static analysis tool for finding vulnerabilities in source code."),
            # Utility
            Resource("extra_time", "utility", "Grants additional time to complete the current challenge."),
            Resource("second_attempt", "utility", "Allows one retry on a failed attack or defense action."),
            Resource("hint", "utility", "Reveals a partial hint about the target vulnerability or defense gap."),
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
                order.extend(["red", "blue"])
            else:
                order.extend(["blue", "red"])
        return order

    async def run(
        self,
        pool: DraftPool,
        red_llm,
        blue_llm,
    ) -> tuple[list[DraftPick], list[DraftPick]]:
        red_picks: list[DraftPick] = []
        blue_picks: list[DraftPick] = []

        round_num = 1
        red_pick_num = 0
        blue_pick_num = 0

        for team in self.draft_order():
            llm = red_llm if team == "red" else blue_llm
            available = pool.available()
            available_names = [r.name for r in available]

            prompt = (
                f"You are the {team} team. Choose one resource to draft.\n"
                f"Available resources: {', '.join(available_names)}\n"
                "Reply with only the resource name, nothing else."
            )

            chosen = await llm.chat([{"role": "user", "content": prompt}])
            chosen = chosen.strip()

            # Validate; re-prompt once on bad pick
            if chosen not in available_names:
                chosen = await llm.chat([{"role": "user", "content": prompt}])
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

            if team == "red":
                red_picks.append(pick)
                red_pick_num += 1
            else:
                blue_picks.append(pick)
                blue_pick_num += 1

            # Advance round number after each pair
            round_num += 1

        return red_picks, blue_picks
