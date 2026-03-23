# System Architecture

The War Games framework implements a red team / blue team LLM competition system with evolutionary learning.

## Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              War Games Framework                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐     ┌──────────────────┐     ┌──────────────────────┐   │
│  │   CLI Input   │────▶│   Game Engine    │────▶│   Results Output     │   │
│  │  (Commands)   │     │  (Orchestrator)  │     │  (DB / Vault / TUI)  │   │
│  └──────────────┘     └──────────────────┘     └──────────────────────┘   │
│         │                     │                        │                   │
│         ▼                     ▼                        ▼                   │
│  ┌──────────────┐     ┌──────────────────┐     ┌──────────────────────┐   │
│  │   Crawler    │     │   Round Engine   │     │   Strategy Store     │   │
│  │ (NVD/ExploitDB)    │  (Draft/Combat)  │     │  (Evolutionary)      │   │
│  └──────────────┘     └──────────────────┘     └──────────────────────┘   │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                        LLM Client Layer                               │  │
│  │              (LiteLLM: OpenAI, Anthropic, Local)                     │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Core Components

### CLI (`wargames/cli.py`)

Entry point for all command-line operations. Handles subcommands like `start`, `attach`, `status`, `crawl`, `report`, `export`, `tournament`, `crew`.

### Game Engine (`wargames/engine/game.py`)

Main orchestrator. Runs the season loop, manages phase progression, tracks ELO ratings.

### Round Engine (`wargames/engine/round.py`)

Per-round execution: draft phase → combat phase → debrief → strategy extraction.

### Strategy Store (`wargames/engine/strategy.py`)

Evolutionary learning component. Stores, retrieves, and prunes strategies based on win rates.

### Team Agents (`wargames/teams/`)

- **RedTeamAgent**: Generates attacks (prompt injection, code vulnerabilities, CVEs)
- **BlueTeamAgent**: Generates defenses and patches

### Judge (`wargames/engine/judge.py`)

Third LLM that scores attacks and defenses, extracts reusable strategies.

## Phase Progression

| Phase | Domain | Description |
|-------|--------|-------------|
| 1 | PROMPT_INJECTION | Prompt injection attacks |
| 2 | CODE_VULNS | Code vulnerability exploitation |
| 3 | REAL_CVES | CVEs from NVD/ExploitDB |
| 4 | OPEN_ENDED | Unconstrained red team attacks |

Phases advance automatically when average score exceeds threshold over consecutive rounds.

## Data Flow

```
1. CLI receives start command
2. Worker spawns GameEngine in background
3. GameEngine runs async season loop:
   a. RoundEngine executes each round
   b. RedTeamAgent generates attack
   c. BlueTeamAgent generates defense  
   d. Judge scores and extracts strategies
   e. Strategy store updates win rates
   f. ELO ratings adjusted
4. Results written to database
5. Optional: Export to OpenClaw Vault
```

## Tournament Mode

Swiss-system tournament pairs models by rating. Each match plays multiple games with roles swapped. ELO persists to shared database.
