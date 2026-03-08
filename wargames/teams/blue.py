import json

from wargames.models import Patch


class BlueTeamAgent:
    def __init__(self, llm):
        self.llm = llm

    async def defend(self, attack_description: str, target: str, tools: list[str],
                     past_lessons: list[str], strategies: list[str] = None,
                     attack_severity: str = "unknown") -> str:
        """Generate a defense against the described attack."""
        lessons_text = "\n".join(f"- {l}" for l in past_lessons) if past_lessons else "None yet."
        strategies_text = "\n".join(f"- {s}" for s in strategies) if strategies else "None yet."
        system = (
            "You are a blue team security engineer. Your job is to defend the target system "
            "against attacks. Analyze the attack and deploy appropriate countermeasures.\n\n"
            "Scoring: Each successful block earns you 3 points AND costs the red team 2 points. "
            "Partial mitigation (reducing attack effectiveness) earns 1 point. "
            "If you reach the score threshold, you win decisively.\n\n"
            f"Attack severity assessed as: {attack_severity}. Higher severity = more points at stake.\n\n"
            f"Your available tools: {', '.join(tools)}\n\n"
            f"Proven tactics from past seasons:\n{strategies_text}\n\n"
            f"Lessons from past rounds:\n{lessons_text}"
        )
        return await self.llm.chat(
            [{"role": "user", "content": (
                f"Target system: {target}\n"
                f"Attack detected: {attack_description}\n\n"
                "Describe your defensive response in detail."
            )}],
            system=system,
        )

    async def generate_patch(self, bug_report, target: str, tools: list[str]) -> Patch:
        """Generate a structured patch for a vulnerability report."""
        system = (
            "You are a blue team engineer writing a patch for a vulnerability.\n"
            "Respond ONLY with valid JSON matching this schema:\n"
            '{"title": str, "fixes": str, "strategy": str, "changes": str, "verification": str}'
        )
        response = await self.llm.chat(
            [{"role": "user", "content": (
                f"Vulnerability: {bug_report.title}\n"
                f"Severity: {bug_report.severity.value}\n"
                f"Steps: {bug_report.steps_to_reproduce}\n"
                f"Target: {target}\nTools: {', '.join(tools)}\n\nWrite the patch."
            )}],
            system=system,
        )
        try:
            data = json.loads(response)
            return Patch(
                round_number=0,
                title=data.get("title", "Untitled Patch"),
                fixes=data.get("fixes", ""),
                strategy=data.get("strategy", ""),
                changes=data.get("changes", ""),
                verification=data.get("verification", ""),
            )
        except (json.JSONDecodeError, ValueError):
            return Patch(
                round_number=0, title=f"Patch for {bug_report.title}",
                fixes="See defense description", strategy="reactive",
                changes="", verification="manual review",
            )

    async def write_debrief(self, defenses_summary: str, draft_picks: list[str], outcome: str) -> str:
        """Write a structured debrief report."""
        system = (
            "You are a blue team lead writing a post-match debrief. Be analytical and constructive. "
            "Include: attacks detected vs missed, draft pick effectiveness, defensive gaps identified, "
            "what you would draft differently, and attack patterns you'd recommend the red team explore."
        )
        return await self.llm.chat(
            [{"role": "user", "content": (
                f"Match outcome: {outcome}\n"
                f"Draft picks: {', '.join(draft_picks)}\n"
                f"Defenses summary:\n{defenses_summary}\n\n"
                "Write your debrief report in markdown."
            )}],
            system=system,
        )
