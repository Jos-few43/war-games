from __future__ import annotations
import os
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator


class DraftStyle(str, Enum):
    SNAKE = "snake"
    LINEAR = "linear"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Domain(str, Enum):
    PROMPT_INJECTION = "prompt-injection"
    CODE_VULN = "code-vuln"
    CONFIG = "config"
    SOCIAL_ENGINEERING = "social-engineering"
    MIXED = "mixed"


class Phase(int, Enum):
    PROMPT_INJECTION = 1
    CODE_VULNS = 2
    REAL_CVES = 3
    OPEN_ENDED = 4


class MatchOutcome(str, Enum):
    RED_WIN = "red_win"
    BLUE_WIN = "blue_win"
    BLUE_DECISIVE_WIN = "blue_decisive_win"
    RED_AUTO_WIN = "red_auto_win"  # Legacy — kept for historical DB rows
    RED_CRITICAL_WIN = "red_critical_win"
    TIMEOUT = "timeout"


# --- Config models ---

class GameSettings(BaseModel):
    name: str
    rounds: int = Field(gt=0)
    turn_limit: int = Field(gt=0)
    score_threshold: int = Field(gt=0)
    phase_advance_score: float = Field(gt=0)


class DraftSettings(BaseModel):
    picks_per_team: int = Field(gt=0)
    style: DraftStyle


class TeamSettings(BaseModel):
    name: str
    model: str
    model_name: str
    temperature: float = Field(ge=0.0, le=2.0)
    timeout: float = Field(default=120.0, description="HTTP timeout per LLM call in seconds")
    api_key: str = Field(default="", description="API key or env var ref like $LITELLM_MASTER_KEY")
    fallback_model: str = Field(default="", description="Fallback base URL")
    fallback_model_name: str = Field(default="", description="Fallback model name")
    fallback_api_key: str = Field(default="", description="Fallback API key or env var ref")
    loadout: str = Field(default="", description="Named loadout preset")
    loadout_custom: list[str] = Field(default_factory=list, description="Custom resource list")

    @model_validator(mode="after")
    def resolve_env_vars(self):
        if self.api_key.startswith("$"):
            self.api_key = os.environ.get(self.api_key[1:], "")
        if self.fallback_api_key.startswith("$"):
            self.fallback_api_key = os.environ.get(self.fallback_api_key[1:], "")
        return self


class TeamsSettings(BaseModel):
    red: TeamSettings
    blue: TeamSettings
    judge: TeamSettings


class CrawlerSettings(BaseModel):
    enabled: bool = True
    sources: list[str] = []
    refresh_interval: str = "24h"


class VaultOutput(BaseModel):
    enabled: bool = True
    path: str


class DatabaseOutput(BaseModel):
    path: str


class OutputSettings(BaseModel):
    vault: VaultOutput
    database: DatabaseOutput


class CostsSettings(BaseModel):
    rates: dict[str, float] = Field(default_factory=dict, description="Model name to $/1K tokens rate")

    @model_validator(mode="before")
    @classmethod
    def _absorb_flat_rates(cls, data: object) -> object:
        """Allow flat TOML [costs] sections where keys are model names directly."""
        if not isinstance(data, dict):
            return data
        known_fields = {"rates"}
        flat_rates = {k: v for k, v in data.items() if k not in known_fields and isinstance(v, (int, float))}
        if flat_rates:
            merged = dict(data.get("rates") or {})
            merged.update(flat_rates)
            cleaned = {k: v for k, v in data.items() if k in known_fields}
            cleaned["rates"] = merged
            return cleaned
        return data


class GameConfig(BaseModel):
    game: GameSettings
    draft: DraftSettings
    teams: TeamsSettings
    crawler: CrawlerSettings = CrawlerSettings()
    output: OutputSettings | None = None
    costs: CostsSettings = CostsSettings()


# --- Game state models ---

class DraftPick(BaseModel):
    round: int
    team: str
    resource_name: str
    resource_category: str


class AttackResult(BaseModel):
    turn: int
    description: str
    severity: Severity | None = None
    points: int = 0
    success: bool = False
    auto_win: bool = False


class DefenseResult(BaseModel):
    turn: int
    description: str
    blocked: bool = False
    effectiveness: float = 0.0
    points_deducted: int = 0
    points_earned: int = 0


class BugReport(BaseModel):
    round_number: int
    title: str
    severity: Severity
    domain: Domain
    target: str
    steps_to_reproduce: str
    proof_of_concept: str
    impact: str


class Patch(BaseModel):
    round_number: int
    title: str
    fixes: str
    strategy: str
    changes: str
    verification: str


class PatchScore(BaseModel):
    addressed: bool = False
    completeness: float = 0.0
    reasoning: str = ""


class RoundResult(BaseModel):
    round_number: int
    phase: Phase
    outcome: MatchOutcome
    red_score: int
    blue_score: int = 0
    blue_threshold: int
    red_draft: list[DraftPick]
    blue_draft: list[DraftPick]
    attacks: list[AttackResult]
    defenses: list[DefenseResult]
    red_debrief: str = ""
    blue_debrief: str = ""
    bug_reports: list[BugReport] = []
    patches: list[Patch] = []


class Strategy(BaseModel):
    team: str
    phase: int
    strategy_type: str  # "attack", "defense", "draft"
    content: str
    win_rate: float = 0.0
    usage_count: int = 0
    created_round: int = 0
