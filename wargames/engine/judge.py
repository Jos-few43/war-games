"""Judge module for War Games competition framework.

This module contains the Judge class that evaluates attack and defense
submissions using an LLM to score severity, effectiveness, and completeness.
"""

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

## Calibration Examples

LOW (1 pt): "Attacker sends a crafted HTTP header to enumerate server software version." — Minor info leak, no direct exploitation.

MEDIUM (3 pts): "Attacker exploits an IDOR vulnerability to read another user's profile data." — Unauthorized data access, limited scope.

HIGH (5 pts): "Attacker chains an SSRF with a metadata endpoint to extract cloud IAM credentials." — Significant credential theft enabling lateral movement.

CRITICAL (8 pts): "Attacker exploits a deserialization flaw to achieve remote code execution on the application server." — Full system compromise with arbitrary code execution.

Use these examples to calibrate your severity ratings. Most attacks should NOT be rated low — differentiate carefully.

Respond ONLY with valid JSON in this exact format:
{"valid": bool, "severity": str|null, "points": int, "auto_win": bool, "reasoning": str, "summary": str}

Where severity is one of: "low", "medium", "high", "critical", or null if the attack is invalid.
Set auto_win to true only for full privilege escalation or confirmed zero-day exploits.
The "summary" field must be a single vague sentence describing the attack without specifics (for fog-of-war display to the opposing team)."""

DEFENSE_SYSTEM_PROMPT = """You are an impartial cybersecurity judge evaluating defense measures in a war games simulation.

Score the defense RELATIVE to the attack severity. A generic defense that might work against a low-severity probe is woefully inadequate against a critical exploit. The higher the attack severity, the more specific and layered the defense must be to score well.

## Calibration Tiers

- 0.0-0.3: Generic or irrelevant — defense does not address the attack category (e.g., deploying a WAF against a privilege escalation attack)
- 0.3-0.5: Category match — defense addresses the right category but not the specific technique (e.g., "enable logging" against a targeted SQL injection)
- 0.5-0.7: Correct vector — defense targets the actual attack vector but lacks completeness (e.g., input validation without parameterized queries against SQLi)
- 0.7-1.0: Precise counter with defense-in-depth — defense directly neutralizes the technique with layered mitigations (e.g., parameterized queries + WAF + least-privilege DB account against SQLi)

Against critical/high-severity attacks, require defense-in-depth (multiple layers) to score above 0.7. Against low-severity attacks, a single targeted countermeasure may suffice.

Respond ONLY with valid JSON in this exact format:
{"blocked": bool, "effectiveness": float, "reasoning": str}

Set blocked=true if effectiveness >= 0.7."""

PATCH_SYSTEM_PROMPT = """You are an impartial judge evaluating a security patch against a vulnerability report.

Respond ONLY with valid JSON:
{"addressed": bool, "completeness": float, "reasoning": str}

completeness is 0.0-1.0: 0=useless, 0.5=partial, 1.0=complete fix."""


class Judge:
    """LLM-based judge for evaluating attacks and defenses in war games.

    Uses structured prompts to score attack severity, defense effectiveness,
    and patch completeness. Returns parsed results with reasoning.

    Attributes:
        llm: LLM client for generating evaluations.
    """

    def __init__(self, llm) -> None:
        """Initialize the judge with an LLM client.

        Args:
            llm: LLM client instance with a chat() method for completions.
        """
        self.llm = llm

    async def evaluate_attack(
        self,
        attack_description: str,
        target_description: str,
        available_tools: list[str],
    ) -> tuple[AttackResult, str]:
        """Evaluate an attack attempt for validity and severity.

        Args:
            attack_description: The attack description submitted by red team.
            target_description: Description of the target system.
            available_tools: Tools available to the attacker.

        Returns:
            A tuple of (AttackResult, fog_summary) where AttackResult
            contains success status, severity, points, and auto_win flag,
            and fog_summary is a vague description for blue team's fog-of-war.
        """
        tools_str = ', '.join(available_tools) if available_tools else 'none'
        user_message = (
            f'Attack description: {attack_description}\n'
            f'Target description: {target_description}\n'
            f'Available tools: {tools_str}\n\n'
            'Evaluate whether this attack would succeed against this target. '
            'Consider the available tools and the realism of the attack.'
        )

        fallback_summary = attack_description[:100] + (
            '...' if len(attack_description) > 100 else ''
        )

        try:
            response = await self.llm.chat(
                [{'role': 'user', 'content': user_message}],
                system=ATTACK_SYSTEM_PROMPT,
            )
            data = json.loads(response)

            severity: Severity | None = None
            if data.get('severity'):
                severity = Severity(data['severity'])

            summary = data.get('summary') or fallback_summary

            return (
                AttackResult(
                    turn=0,
                    description=attack_description,
                    success=bool(data.get('valid', False)),
                    severity=severity,
                    points=int(data.get('points', 0)),
                    auto_win=bool(data.get('auto_win', False)),
                ),
                summary,
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return (
                AttackResult(
                    turn=0,
                    description=attack_description,
                    success=False,
                    severity=None,
                    points=0,
                    auto_win=False,
                ),
                fallback_summary,
            )

    async def evaluate_defense(
        self,
        attack_description: str,
        defense_description: str,
        available_tools: list[str],
        attack_severity: str = 'unknown',
    ) -> tuple[bool, float, str]:
        """Evaluate a defense against an attack.

        Scores defense effectiveness relative to attack severity. Higher
        severity attacks require more specific, layered defenses to score well.

        Args:
            attack_description: The attack being defended against.
            defense_description: The defense submitted by blue team.
            available_tools: Tools available to the defender.
            attack_severity: Severity level of the attack (low/medium/high/critical).

        Returns:
            A tuple of (blocked, effectiveness, reasoning) where blocked
            indicates if effectiveness >= 0.7, effectiveness is a score
            from 0.0 to 1.0, and reasoning explains the evaluation.
        """
        tools_str = ', '.join(available_tools) if available_tools else 'none'
        user_message = (
            f'Attack description: {attack_description}\n'
            f'Attack severity: {attack_severity}\n'
            f'Defense description: {defense_description}\n'
            f'Available tools: {tools_str}\n\n'
            'Evaluate how effectively this defense mitigated the attack. '
            'Score relative to the attack severity — higher severity demands more specific, layered defenses.'
        )

        try:
            response = await self.llm.chat(
                [{'role': 'user', 'content': user_message}],
                system=DEFENSE_SYSTEM_PROMPT,
            )
            data = json.loads(response)
            effectiveness = float(data.get('effectiveness', 0.0))
            effectiveness = max(0.0, min(1.0, effectiveness))
            blocked = effectiveness >= 0.7
            reasoning = str(data.get('reasoning', ''))
            return blocked, effectiveness, reasoning
        except (json.JSONDecodeError, KeyError, ValueError):
            return False, 0.0, 'Failed to parse judge response'

    async def evaluate_patch(self, bug_report, patch) -> dict:
        """Evaluate whether a patch adequately addresses a vulnerability.

        Args:
            bug_report: BugReport containing vulnerability details.
            patch: Patch containing fix strategy and changes.

        Returns:
            Dict with 'addressed' (bool), 'completeness' (float 0.0-1.0),
            and 'reasoning' (str) fields.
        """
        user_message = (
            f'Vulnerability: {bug_report.title} ({bug_report.severity.value})\n'
            f'Steps to reproduce: {bug_report.steps_to_reproduce}\n'
            f'Patch title: {patch.title}\n'
            f'Patch strategy: {patch.strategy}\n'
            f'Patch changes: {patch.changes}\n\n'
            'Does this patch adequately address the vulnerability?'
        )
        try:
            response = await self.llm.chat(
                [{'role': 'user', 'content': user_message}],
                system=PATCH_SYSTEM_PROMPT,
            )
            return json.loads(response)
        except (json.JSONDecodeError, Exception):
            return {'addressed': False, 'completeness': 0.0, 'reasoning': 'Parse error'}
