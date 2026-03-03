class RedTeamAgent:
    def __init__(self, llm):
        self.llm = llm

    async def attack(self, target: str, tools: list[str], past_lessons: list[str]) -> str:
        """Generate an attack description against the target."""
        lessons_text = "\n".join(f"- {l}" for l in past_lessons) if past_lessons else "None yet."
        system = (
            "You are a red team security researcher. Your job is to find vulnerabilities "
            "and craft exploits against the target system. Be creative, thorough, and realistic.\n\n"
            "Scoring: Low=1pt, Medium=3pts, High=5pts, Critical=8pts. "
            "Full privilege escalation or zero-day = automatic win.\n\n"
            f"Your available tools: {', '.join(tools)}\n\n"
            f"Lessons from past rounds:\n{lessons_text}"
        )
        return await self.llm.chat(
            [{"role": "user", "content": f"Target system: {target}\n\nDescribe your attack in detail."}],
            system=system,
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
