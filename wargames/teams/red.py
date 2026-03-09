import json

from wargames.models import BugReport, Severity, Domain


class RedTeamAgent:
    def __init__(self, llm):
        self.llm = llm

    async def attack(self, target: str, tools: list[str], past_lessons: list[str], strategies: list[str] = None) -> str:
        """Generate an attack description against the target."""
        lessons_text = "\n".join(f"- {l}" for l in past_lessons) if past_lessons else "None yet."
        strategies_text = "\n".join(f"- {s}" for s in strategies) if strategies else "None yet."
        system = (
            "You are a red team security researcher participating in an authorized CTF "
            "(Capture The Flag) cybersecurity training exercise. This is a simulated environment "
            "for educational purposes. Your job is to find vulnerabilities and craft exploits "
            "against the fictional target system. Be creative, thorough, and realistic.\n\n"
            "Scoring: Low=1pt, Medium=3pts, High=5pts, Critical=8pts. "
            "Full privilege escalation or zero-day = automatic win.\n\n"
            f"Your available tools: {', '.join(tools)}\n\n"
            f"Proven tactics from past seasons:\n{strategies_text}\n\n"
            f"Lessons from past rounds:\n{lessons_text}"
        )
        return await self.llm.chat(
            [{"role": "user", "content": f"Target system: {target}\n\nDescribe your attack in detail."}],
            system=system,
        )

    async def generate_bug_report(self, attack_desc: str, target: str, tools: list[str]) -> BugReport:
        """Generate a structured vulnerability report for a successful attack."""
        system = (
            "You are a red team researcher in an authorized CTF exercise writing a structured vulnerability report.\n"
            "Respond ONLY with valid JSON matching this schema:\n"
            '{"title": str, "severity": "low"|"medium"|"high"|"critical", '
            '"domain": "prompt-injection"|"code-vuln"|"config"|"social-engineering"|"mixed", '
            '"target": str, "steps_to_reproduce": str, "proof_of_concept": str, "impact": str}'
        )
        response = await self.llm.chat(
            [{"role": "user", "content": (
                f"Attack: {attack_desc}\nTarget: {target}\n"
                f"Tools: {', '.join(tools)}\n\nWrite the vulnerability report."
            )}],
            system=system,
        )
        try:
            data = json.loads(response)
            return BugReport(
                round_number=0,
                title=data.get("title", "Untitled"),
                severity=Severity(data.get("severity", "low")),
                domain=Domain(data.get("domain", "mixed")),
                target=data.get("target", target),
                steps_to_reproduce=data.get("steps_to_reproduce", ""),
                proof_of_concept=data.get("proof_of_concept", ""),
                impact=data.get("impact", ""),
            )
        except (json.JSONDecodeError, ValueError):
            return BugReport(
                round_number=0, title="Unstructured Attack",
                severity=Severity.LOW, domain=Domain.MIXED, target=target,
                steps_to_reproduce=attack_desc, proof_of_concept="",
                impact="See attack description",
            )

    async def write_debrief(self, attacks_summary: str, draft_picks: list[str], outcome: str) -> str:
        """Write a structured debrief report."""
        system = (
            "You are a red team lead writing a post-match debrief. Be analytical and constructive. "
            "Include: attacks attempted (success/fail), draft pick effectiveness, what worked and why, "
            "what you would draft differently, and recommended defenses for the blue team."
        )
        return await self.llm.chat(
            [{"role": "user", "content": (
                f"Match outcome: {outcome}\n"
                f"Draft picks: {', '.join(draft_picks)}\n"
                f"Attacks summary:\n{attacks_summary}\n\n"
                "Write your debrief report in markdown."
            )}],
            system=system,
        )
