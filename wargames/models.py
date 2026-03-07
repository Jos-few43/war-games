from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field, field_validator


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
    RED_AUTO_WIN = "red_auto_win"
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


class GameConfig(BaseModel):
    game: GameSettings
    draft: DraftSettings
    teams: TeamsSettings
    crawler: CrawlerSettings = CrawlerSettings()
    output: OutputSettings | None = None


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
    points_deducted: int = 0


class RoundResult(BaseModel):
    round_number: int
    phase: Phase
    outcome: MatchOutcome
    red_score: int
    blue_threshold: int
    red_draft: list[DraftPick]
    blue_draft: list[DraftPick]
    attacks: list[AttackResult]
    defenses: list[DefenseResult]
    red_debrief: str = ""
    blue_debrief: str = ""


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


class Strategy(BaseModel):
    team: str
    phase: int
    strategy_type: str  # "attack", "defense", "draft"
    content: str
    win_rate: float = 0.0
    usage_count: int = 0
    created_round: int = 0
