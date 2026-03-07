class BlueTeamAgent:
    def __init__(self, llm):
        self.llm = llm

    async def defend(self, attack_description: str, target: str, tools: list[str], past_lessons: list[str], strategies: list[str] = None) -> str:
        """Generate a defense against the described attack."""
        lessons_text = "\n".join(f"- {l}" for l in past_lessons) if past_lessons else "None yet."
        strategies_text = "\n".join(f"- {s}" for s in strategies) if strategies else "None yet."
        system = (
            "You are a blue team security engineer. Your job is to defend the target system "
            "against attacks. Analyze the attack and deploy appropriate countermeasures.\n\n"
            "If you successfully block an attack, the red team loses 2 points.\n\n"
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
