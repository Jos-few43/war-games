import re
from pathlib import Path
from wargames.models import RoundResult, BugReport, Patch


class VaultWriter:
    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        self._ensure_dirs()

    def _ensure_dirs(self):
        for subdir in ["rounds", "bug-reports", "patches", "debriefs", "knowledge"]:
            (self.base_path / subdir).mkdir(parents=True, exist_ok=True)

    def _slugify(self, title: str) -> str:
        slug = title.lower().strip()
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        slug = re.sub(r'[\s]+', '-', slug)
        return slug[:60]

    def write_round(self, result: RoundResult):
        """Write round summary, red debrief, and blue debrief."""
        num = f"{result.round_number:03d}"

        # Round summary
        content = (
            f"---\n"
            f"type: round\n"
            f"round: {result.round_number}\n"
            f"phase: {result.phase.value}\n"
            f"outcome: {result.outcome.value}\n"
            f"red_score: {result.red_score}\n"
            f"blue_threshold: {result.blue_threshold}\n"
            f"tags: [wargames]\n"
            f"---\n\n"
            f"# Round {result.round_number}\n\n"
            f"**Phase:** {result.phase.name}  \n"
            f"**Outcome:** {result.outcome.value}  \n"
            f"**Red Score:** {result.red_score} / {result.blue_threshold}\n\n"
            f"## Attacks\n\n"
        )
        for a in result.attacks:
            status = "SUCCESS" if a.success else "FAIL"
            content += f"- Turn {a.turn}: [{status}] {a.description[:100]}\n"
        content += f"\n## Defenses\n\n"
        for d in result.defenses:
            status = "BLOCKED" if d.blocked else "MISSED"
            content += f"- Turn {d.turn}: [{status}] {d.description[:100]}\n"

        (self.base_path / "rounds" / f"round-{num}.md").write_text(content)

        # Debriefs
        for team, debrief_text in [("red", result.red_debrief), ("blue", result.blue_debrief)]:
            debrief_content = (
                f"---\n"
                f"type: debrief\n"
                f"round: {result.round_number}\n"
                f"team: {team}\n"
                f"outcome: {result.outcome.value}\n"
                f"tags: [wargames, debrief]\n"
                f"---\n\n"
                f"{debrief_text}\n"
            )
            (self.base_path / "debriefs" / f"R{num}-{team}-debrief.md").write_text(debrief_content)

    def write_bug_report(self, report: BugReport):
        num = f"{report.round_number:03d}"
        slug = self._slugify(report.title)
        content = (
            f"---\n"
            f"type: bug-report\n"
            f"round: {report.round_number}\n"
            f"severity: {report.severity.value}\n"
            f"domain: {report.domain.value}\n"
            f"tags: [wargames, bug-report]\n"
            f"---\n\n"
            f"# Bug Report: {report.title}\n\n"
            f"- **Severity:** {report.severity.value}\n"
            f"- **Domain:** {report.domain.value}\n"
            f"- **Target:** {report.target}\n\n"
            f"## Steps to Reproduce\n\n{report.steps_to_reproduce}\n\n"
            f"## Proof of Concept\n\n{report.proof_of_concept}\n\n"
            f"## Impact\n\n{report.impact}\n"
        )
        (self.base_path / "bug-reports" / f"R{num}-{slug}.md").write_text(content)

    def write_patch(self, patch: Patch):
        num = f"{patch.round_number:03d}"
        slug = self._slugify(patch.title)
        content = (
            f"---\n"
            f"type: patch\n"
            f"round: {patch.round_number}\n"
            f"fixes: {patch.fixes}\n"
            f"tags: [wargames, patch]\n"
            f"---\n\n"
            f"# Patch: {patch.title}\n\n"
            f"- **Fixes:** [[{patch.fixes}]]\n"
            f"- **Strategy:** {patch.strategy}\n\n"
            f"## Changes\n\n{patch.changes}\n\n"
            f"## Verification\n\n{patch.verification}\n"
        )
        (self.base_path / "patches" / f"R{num}-{slug}.md").write_text(content)

    def append_knowledge(self, filename: str, content: str):
        path = self.base_path / "knowledge" / f"{filename}.md"
        existing = path.read_text() if path.exists() else ""
        path.write_text(existing + "\n" + content if existing else content)
