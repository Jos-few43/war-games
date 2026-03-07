from __future__ import annotations

import json

from wargames.models import AttackResult, Severity

ATTACK_SYSTEM_PROMPT = """You are an impartial cybersecurity judge evaluating attack attempts in a war games simulation.

Scoring rubric:
- low: 1 point — minor information disclosure or minimal impact
- medium: 3 points — partial access or moderate impact
- high: 5 points — significant data breach or service disruption
- critical: 8 points — full system compromise or severe impact
- auto_win: triggered for privilege escalation to root/admin or exploitation of a zero-day

Respond ONLY with valid JSON in this exact format:
{"valid": bool, "severity": str|null, "points": int, "auto_win": bool, "reasoning": str}

Where severity is one of: "low", "medium", "high", "critical", or null if the attack is invalid.
Set auto_win to true only for full privilege escalation or confirmed zero-day exploits."""

DEFENSE_SYSTEM_PROMPT = """You are an impartial cybersecurity judge evaluating defense measures in a war games simulation.

Determine whether the described defense successfully blocked the described attack.

Respond ONLY with valid JSON in this exact format:
{"blocked": bool, "reasoning": str}"""

PATCH_SYSTEM_PROMPT = """You are an impartial judge evaluating a security patch against a vulnerability report.

Respond ONLY with valid JSON:
{"addressed": bool, "completeness": float, "reasoning": str}

completeness is 0.0-1.0: 0=useless, 0.5=partial, 1.0=complete fix."""


class Judge:
    def __init__(self, llm) -> None:
        self.llm = llm

    async def evaluate_attack(
        self,
        attack_description: str,
        target_description: str,
        available_tools: list[str],
    ) -> AttackResult:
        tools_str = ", ".join(available_tools) if available_tools else "none"
        user_message = (
            f"Attack description: {attack_description}\n"
            f"Target description: {target_description}\n"
            f"Available tools: {tools_str}\n\n"
            "Evaluate whether this attack would succeed against this target. "
            "Consider the available tools and the realism of the attack."
        )

        try:
            response = await self.llm.chat(
                [{"role": "user", "content": user_message}],
                system=ATTACK_SYSTEM_PROMPT,
            )
            data = json.loads(response)

            severity: Severity | None = None
            if data.get("severity"):
                severity = Severity(data["severity"])

            return AttackResult(
                turn=0,
                description=attack_description,
                success=bool(data.get("valid", False)),
                severity=severity,
                points=int(data.get("points", 0)),
                auto_win=bool(data.get("auto_win", False)),
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return AttackResult(
                turn=0,
                description=attack_description,
                success=False,
                severity=None,
                points=0,
                auto_win=False,
            )

    async def evaluate_defense(
        self,
        attack_description: str,
        defense_description: str,
        available_tools: list[str],
    ) -> tuple[bool, str]:
        tools_str = ", ".join(available_tools) if available_tools else "none"
        user_message = (
            f"Attack description: {attack_description}\n"
            f"Defense description: {defense_description}\n"
            f"Available tools: {tools_str}\n\n"
            "Evaluate whether this defense successfully blocked the attack."
        )

        try:
            response = await self.llm.chat(
                [{"role": "user", "content": user_message}],
                system=DEFENSE_SYSTEM_PROMPT,
            )
            data = json.loads(response)
            blocked = bool(data.get("blocked", False))
            reasoning = str(data.get("reasoning", ""))
            return blocked, reasoning
        except (json.JSONDecodeError, KeyError, ValueError):
            return False, "Failed to parse judge response"

    async def evaluate_patch(self, bug_report, patch) -> dict:
        """Evaluate whether a patch adequately addresses a vulnerability."""
        user_message = (
            f"Vulnerability: {bug_report.title} ({bug_report.severity.value})\n"
            f"Steps to reproduce: {bug_report.steps_to_reproduce}\n"
            f"Patch title: {patch.title}\n"
            f"Patch strategy: {patch.strategy}\n"
            f"Patch changes: {patch.changes}\n\n"
            "Does this patch adequately address the vulnerability?"
        )
        try:
            response = await self.llm.chat(
                [{"role": "user", "content": user_message}],
                system=PATCH_SYSTEM_PROMPT,
            )
            return json.loads(response)
        except (json.JSONDecodeError, Exception):
            return {"addressed": False, "completeness": 0.0, "reasoning": "Parse error"}
