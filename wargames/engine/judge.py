"""Judge module for War Games competition framework.

This module contains the Judge class that evaluates attack and defense
submissions using an LLM to score severity, effectiveness, and completeness.
Includes confidence scoring and calibration for improved reliability.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from wargames.models import AttackResult, DefenseResult, Severity

logger = logging.getLogger(__name__)

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
{"valid": bool, "severity": str|null, "points": int, "auto_win": bool, "confidence": float, "reasoning": str, "summary": str}

Where severity is one of: "low", "medium", "high", "critical", or null if the attack is invalid.
Set auto_win to true only for full privilege escalation or confirmed zero-day exploits.
confidence is 0.0-1.0 indicating your certainty in this assessment.
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
{"blocked": bool, "effectiveness": float, "confidence": float, "reasoning": str}

Set blocked=true if effectiveness >= 0.7.
confidence is 0.0-1.0 indicating your certainty in this assessment."""

PATCH_SYSTEM_PROMPT = """You are an impartial judge evaluating a security patch against a vulnerability report.

Respond ONLY with valid JSON:
{"addressed": bool, "completeness": float, "confidence": float, "reasoning": str}

completeness is 0.0-1.0: 0=useless, 0.5=partial, 1.0=complete fix.
confidence is 0.0-1.0 indicating your certainty in this assessment."""


@dataclass
class JudgmentResult:
    """Result of a judgment with confidence scoring."""

    success: bool
    severity: Severity | None
    points: int
    auto_win: bool
    confidence: float
    reasoning: str
    summary: str


@dataclass
class CalibrationExample:
    """Known benchmark example for judge calibration."""

    description: str
    expected_severity: Severity
    expected_points: int
    category: str  # "attack", "defense", "patch"


class JudgeCalibration:
    """Calibration system for reducing judge variance against known benchmarks."""

    CALIBRATION_EXAMPLES: list[CalibrationExample] = [
        # Low severity examples
        CalibrationExample(
            description='Attacker sends a crafted HTTP header to enumerate server software version.',
            expected_severity=Severity.LOW,
            expected_points=1,
            category='attack',
        ),
        # Medium severity examples
        CalibrationExample(
            description="Attacker exploits an IDOR vulnerability to read another user's profile data.",
            expected_severity=Severity.MEDIUM,
            expected_points=3,
            category='attack',
        ),
        # High severity examples
        CalibrationExample(
            description='Attacker chains an SSRF with a metadata endpoint to extract cloud IAM credentials.',
            expected_severity=Severity.HIGH,
            expected_points=5,
            category='attack',
        ),
        # Critical severity examples
        CalibrationExample(
            description='Attacker exploits a deserialization flaw to achieve remote code execution on the application server.',
            expected_severity=Severity.CRITICAL,
            expected_points=8,
            category='attack',
        ),
    ]

    def __init__(self):
        self.calibration_drift: dict[str, float] = {}
        self.judgment_history: list[dict[str, Any]] = []

    def record_judgment(
        self,
        judgment_type: str,
        input_data: dict[str, Any],
        output_data: dict[str, Any],
        confidence: float,
    ) -> None:
        """Record a judgment for future calibration analysis."""
        self.judgment_history.append(
            {
                'type': judgment_type,
                'input': input_data,
                'output': output_data,
                'confidence': confidence,
            }
        )

    def calculate_variance(self) -> float:
        """Calculate variance in recent judgments against expected values."""
        if not self.judgment_history:
            return 0.0

        variances = []
        for judgment in self.judgment_history[-20:]:  # Last 20 judgments
            # Find matching calibration example
            for example in self.CALIBRATION_EXAMPLES:
                if example.description in str(judgment['input']):
                    actual_points = judgment['output'].get('points', 0)
                    expected_points = example.expected_points
                    variance = abs(actual_points - expected_points) / max(expected_points, 1)
                    variances.append(variance)
                    break

        return sum(variances) / len(variances) if variances else 0.0

    def get_confidence_adjustment(self, base_confidence: float, judgment_type: str) -> float:
        """Adjust confidence based on historical calibration data."""
        variance = self.calculate_variance()
        # Higher variance = lower confidence
        adjustment = max(0.0, 1.0 - variance) * 0.2
        return min(1.0, base_confidence * (1.0 - adjustment))

    def get_calibration_report(self) -> dict[str, Any]:
        """Generate a calibration report for monitoring."""
        variance = self.calculate_variance()
        return {
            'total_judgments': len(self.judgment_history),
            'variance_score': variance,
            'calibration_status': 'good'
            if variance < 0.2
            else 'fair'
            if variance < 0.4
            else 'poor',
            'recommended_action': (
                'continue' if variance < 0.2 else 'review_prompts' if variance < 0.4 else 'retrain'
            ),
        }


class Judge:
    """LLM-based judge for evaluating attacks and defenses in war games.

    Uses structured prompts to score attack severity, defense effectiveness,
    and patch completeness. Includes confidence scoring and calibration.

    Attributes:
        llm: LLM client for generating evaluations.
        calibration: JudgeCalibration instance for variance reduction.
    """

    def __init__(self, llm, enable_calibration: bool = True) -> None:
        """Initialize the judge with an LLM client.

        Args:
            llm: LLM client instance with a chat() method for completions.
            enable_calibration: Whether to enable calibration system.
        """
        self.llm = llm
        self.calibration = JudgeCalibration() if enable_calibration else None

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

        response = ''
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
            confidence = float(data.get('confidence', 0.5))
            confidence = max(0.0, min(1.0, confidence))

            if self.calibration:
                confidence = self.calibration.get_confidence_adjustment(confidence, 'attack')
                self.calibration.record_judgment(
                    'attack',
                    {'description': attack_description, 'target': target_description},
                    {
                        'severity': data.get('severity'),
                        'points': data.get('points'),
                        'valid': data.get('valid'),
                    },
                    confidence,
                )

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
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(
                f'Judge JSON parse error: {type(e).__name__} - response was: {response[:200] if response else "empty"}'
            )
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
    ) -> tuple[bool, float, str, float]:
        """Evaluate a defense against an attack.

        Scores defense effectiveness relative to attack severity. Higher
        severity attacks require more specific, layered defenses to score well.

        Args:
            attack_description: The attack being defended against.
            defense_description: The defense submitted by blue team.
            available_tools: Tools available to the defender.
            attack_severity: Severity level of the attack (low/medium/high/critical).

        Returns:
            A tuple of (blocked, effectiveness, reasoning, confidence) where blocked
            indicates if effectiveness >= 0.7, effectiveness is a score
            from 0.0 to 1.0, reasoning explains the evaluation, and confidence
            indicates certainty in the assessment.
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
            confidence = float(data.get('confidence', 0.5))
            confidence = max(0.0, min(1.0, confidence))
            blocked = effectiveness >= 0.7
            reasoning = str(data.get('reasoning', ''))

            if self.calibration:
                confidence = self.calibration.get_confidence_adjustment(confidence, 'defense')
                self.calibration.record_judgment(
                    'defense',
                    {
                        'attack': attack_description,
                        'defense': defense_description,
                        'severity': attack_severity,
                    },
                    {'effectiveness': effectiveness, 'blocked': blocked},
                    confidence,
                )

            return blocked, effectiveness, reasoning, confidence
        except (json.JSONDecodeError, KeyError, ValueError):
            return False, 0.0, 'Failed to parse judge response', 0.0

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
            data = json.loads(response)
            confidence = float(data.get('confidence', 0.5))
            confidence = max(0.0, min(1.0, confidence))

            if self.calibration:
                confidence = self.calibration.get_confidence_adjustment(confidence, 'patch')
                self.calibration.record_judgment(
                    'patch',
                    {'bug': bug_report.title, 'severity': bug_report.severity.value},
                    {'addressed': data.get('addressed'), 'completeness': data.get('completeness')},
                    confidence,
                )

            data['confidence'] = confidence
            return data
        except (json.JSONDecodeError, Exception):
            return {
                'addressed': False,
                'completeness': 0.0,
                'confidence': 0.0,
                'reasoning': 'Parse error',
            }
