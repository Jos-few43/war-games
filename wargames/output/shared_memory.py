"""Shared Memory integration for War Games.

This module provides integration with the ~/shared-memory/ system
for cross-session knowledge persistence.
"""

from pathlib import Path
from datetime import datetime
import json


class SharedMemoryExporter:
    """Export War Games findings to shared memory system."""

    SHARED_MEMORY_PATH = Path('~/shared-memory/core').expanduser()

    def __init__(self, vault_path: Path | None = None):
        self.vault_path = (
            vault_path or Path('~/Documents/OpenClaw-Vault/01-RESEARCH/WarGames').expanduser()
        )

    def _ensure_dirs(self):
        self.vault_path.mkdir(parents=True, exist_ok=True)

    def export_strategy_insight(self, phase: str, strategy_content: str, win_rate: float):
        self._ensure_dirs()
        content = f"""## Strategy Insight

- **Phase:** {phase}
- **Win Rate:** {win_rate:.0%}
- **Content:** {strategy_content}
- **Discovered:** {datetime.now().isoformat()}

"""
        path = self.vault_path / 'strategy-insights.md'
        existing = path.read_text() if path.exists() else '# War Games Strategy Insights\n'
        path.write_text(existing + '\n' + content)

    def export_exploit_finding(self, title: str, severity: str, domain: str, description: str):
        self._ensure_dirs()
        content = f"""## Exploit Discovery

### {title}

- **Severity:** {severity}
- **Domain:** {domain}
- **Discovered:** {datetime.now().isoformat()}

{description}

"""
        path = self.vault_path / 'exploit-discoveries.md'
        existing = path.read_text() if path.exists() else '# War Games Exploit Discoveries\n'
        path.write_text(existing + '\n' + content)

    def export_model_performance(self, model_name: str, elo: int, games_played: int):
        self._ensure_dirs()
        content = f"""## Model Performance

- **Model:** {model_name}
- **ELO:** {elo}
- **Games:** {games_played}
- **Updated:** {datetime.now().isoformat()}

"""
        path = self.vault_path / 'model-rankings.md'
        existing = path.read_text() if path.exists() else '# War Games Model Rankings\n'
        path.write_text(existing + '\n' + content)

    def export_phase_progression(self, phase: str, rounds_completed: int, avg_score: float):
        self._ensure_dirs()
        content = f"""## Phase Progression

- **Current Phase:** {phase}
- **Rounds:** {rounds_completed}
- **Average Score:** {avg_score:.1f}
- **Updated:** {datetime.now().isoformat()}

"""
        path = self.vault_path / 'phase-progress.md'
        existing = path.read_text() if path.exists() else '# War Games Phase Progress\n'
        path.write_text(existing + '\n' + content)

    def write_round_summary(
        self, round_number: int, outcome: str, red_score: int, blue_threshold: int
    ):
        self._ensure_dirs()
        content = f"""## Round {round_number}

- **Outcome:** {outcome}
- **Red Score:** {red_score}/{blue_threshold}
- **Timestamp:** {datetime.now().isoformat()}

"""
        path = self.vault_path / 'round-summaries.md'
        existing = path.read_text() if path.exists() else '# War Games Round Summaries\n'
        path.write_text(existing + '\n' + content)


class SharedMemoryQuery:
    """Query shared memory for context."""

    SHARED_MEMORY_PATH = Path('~/shared-memory/core').expanduser()

    def get_strategy_context(self, phase: str | None = None) -> str:
        path = self.SHARED_MEMORY_PATH / 'technical-decisions.md'
        if not path.exists():
            return ''
        return path.read_text()

    def get_model_context(self) -> str:
        path = self.SHARED_MEMORY_PATH / 'technical-decisions.md'
        if not path.exists():
            return ''
        content = path.read_text()
        if 'War Games' in content or 'wargames' in content:
            lines = [l for l in content.split('\n') if 'War Games' in l or 'ELO' in l]
            return '\n'.join(lines[:10])
        return ''
