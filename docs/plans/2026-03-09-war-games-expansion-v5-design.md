# War Games Expansion V5 Design — Scoring Engine + PostgreSQL + Grafana + Leagues

**Date:** 2026-03-09
**Status:** Approved
**Prereq:** V4 (competitive rebalance + Swiss tournament) merged
**Future:** V6 will add tiered leagues with promotion/relegation, custom judge plugins

## Overview

Three workstreams: configurable scoring engine (data-driven balance tuning), PostgreSQL migration with Grafana dashboards (observability), and a league system (persistent multi-season competition). Scoring engine is prerequisite for leagues (leagues need customizable rules). Postgres is prerequisite for Grafana.

## 1. Configurable Scoring Engine

### Problem

All scoring values are hardcoded in `round.py` and `judge.py`. Tuning balance requires code changes. Different tournaments may want different rules.

### Design

New `[scoring]` section in game config TOML. New `ScoringProfile` Pydantic model.

```toml
[scoring]
profile = "balanced"

[scoring.attack_points]
low = 1
medium = 3
high = 5
critical = 8

[scoring.defense_rewards]
full_block_threshold = 0.7
partial_block_threshold = 0.3
full_block_points = 2
partial_block_points = 1

[scoring.win_conditions]
score_threshold = 10
auto_win_defense_threshold = 0.5
critical_neutralize_bonus = 5

[scoring.phase_advance]
min_rounds = 3
min_avg_score = 5.0
```

Ship 3 presets in `config/scoring/`:
- `balanced.toml` — current V4 values
- `red-favored.toml` — lower thresholds, higher attack points
- `blue-favored.toml` — higher defense rewards

`RoundEngine` reads from `ScoringProfile` instead of hardcoded values. Judge prompts unchanged — they handle calibration, the profile controls only mechanical point calculations.

### File Map

| File | Change |
|---|---|
| `wargames/models.py` | Add `ScoringProfile`, `AttackPoints`, `DefenseRewards`, `WinConditions`, `PhaseAdvanceSettings` |
| `wargames/config.py` | Load `[scoring]` from TOML, merge with presets |
| `wargames/engine/round.py` | Read points/thresholds from `ScoringProfile` |
| `wargames/engine/game.py` | Read phase advance from `ScoringProfile` |
| `config/scoring/balanced.toml` | Default preset |
| `config/scoring/red-favored.toml` | Aggressive preset |
| `config/scoring/blue-favored.toml` | Defensive preset |

## 2. PostgreSQL Migration

### Problem

SQLite has write locking (no concurrent game + dashboard), no native Grafana support, and doesn't scale for multi-season leagues.

### Design

Replace `aiosqlite` with `asyncpg`. The `Database` class API stays identical — only the internals change.

**Connection:** Config TOML `[output.database]` or `$WARGAMES_DATABASE_URL` env var.

```toml
[output.database]
url = "postgresql://wargames:wargames@localhost:5432/wargames"
```

**Schema:** All 13 existing tables migrated to Postgres dialect. Single migration file `migrations/001_initial.sql`.

**SQLite fallback:** `sandbox` command continues to work with no DB (`db=None`). Only `start`, `tournament`, and `league` commands require Postgres.

**Migration CLI:** `wargames migrate --from-sqlite ~/.local/share/wargames/state.db` — one-time import of historical data.

### File Map

| File | Change |
|---|---|
| `wargames/output/db.py` | Replace aiosqlite with asyncpg, update all queries to Postgres dialect |
| `migrations/001_initial.sql` | Full schema DDL (all 13 tables + new league tables) |
| `wargames/cli.py` | Add `migrate` subcommand |
| `wargames/models.py` | Update `DatabaseOutput` to accept URL string |
| `pyproject.toml` | Replace aiosqlite with asyncpg dependency |

## 3. Grafana Dashboard (Podman Pod)

### Problem

No way to visualize game data, tournament standings, or model performance over time.

### Design

Podman pod with PostgreSQL 16 + Grafana OSS. Grafana queries Postgres directly via provisioned datasource. No custom web code.

**Infrastructure files:**

```
infra/
├── podman-compose.yml          # Postgres + Grafana pod
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/
│   │   │   └── postgres.yml    # Auto-configure Postgres datasource
│   │   └── dashboards/
│   │       └── default.yml     # Dashboard provisioning config
│   └── dashboards/
│       ├── live-game.json      # Current round scores, attack timeline
│       ├── tournament.json     # ELO ratings, win records, head-to-head
│       ├── season.json         # Red vs blue rates, phase progression
│       └── model-compare.json  # Per-model stats, cost analysis
└── init.sql                    # Postgres init (create DB + user)
```

**CLI shortcut:**
- `wargames stack up` — `podman-compose -f infra/podman-compose.yml up -d`
- `wargames stack down` — `podman-compose -f infra/podman-compose.yml down`

### Dashboards

1. **Live Game** — current round score, attack/defense timeline, draft picks
2. **Tournament Standings** — ELO ratings over time, win/loss records, head-to-head matrix
3. **Season Overview** — red vs blue win rates, phase progression, score distributions
4. **Model Comparison** — per-model attack success rate, defense effectiveness, cost per round

## 4. League System

### Problem

Tournaments are one-off. No persistent competition or ELO tracking across multiple events.

### Design

Seasons wrap Swiss tournaments with persistent ELO. Simple extension of existing `TournamentRunner`.

**New tables:**

```sql
CREATE TABLE leagues (
    league_id   SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW(),
    config      JSONB  -- scoring profile + tournament settings
);

CREATE TABLE league_seasons (
    season_id     SERIAL PRIMARY KEY,
    league_id     INTEGER REFERENCES leagues(league_id),
    season_number INTEGER NOT NULL,
    started_at    TIMESTAMP DEFAULT NOW(),
    ended_at      TIMESTAMP,
    status        TEXT DEFAULT 'pending'  -- pending, active, complete
);
```

**Modified tables:**
- `model_ratings` gets `league_id` column (ELO is per-league)
- `tournament_matches` gets `season_id` column

**Season lifecycle:**
1. `wargames league create --name "cloud-arena" --roster config/roster.toml`
2. `wargames league season start --league cloud-arena`
3. Season runs Swiss tournament, updates per-league ELO
4. `wargames league standings --league cloud-arena`
5. ELO carries forward between seasons (no reset)

**Config:** Optional `[league]` section in roster TOML:

```toml
[league]
name = "cloud-arena"
```

### File Map

| File | Change |
|---|---|
| `wargames/engine/league.py` | New: `LeagueRunner` class |
| `wargames/engine/swiss.py` | Accept `league_id`/`season_id` for DB persistence |
| `wargames/output/db.py` | Add league/season tables and methods |
| `wargames/models.py` | Add `LeagueConfig` model |
| `wargames/cli.py` | Add `league` and `stack` subcommands |
| `migrations/001_initial.sql` | Include league tables |

## 5. Task Order

Tasks ordered by dependency:

1. **Scoring engine models + presets** — foundation for everything
2. **Scoring engine integration** — wire into RoundEngine + GameEngine
3. **PostgreSQL migration** — replace aiosqlite with asyncpg
4. **Migration CLI** — sqlite-to-postgres import tool
5. **Podman pod + Grafana provisioning** — infrastructure setup
6. **Grafana dashboards** — 4 dashboard JSON files
7. **League data model + DB** — tables, models, methods
8. **League runner + CLI** — LeagueRunner class, league/stack CLI commands
9. **Validation** — run tournament with scoring profile, verify Grafana shows data

## 6. Validation Plan

1. After scoring engine (tasks 1-2): run sandbox with each preset, verify different balance behavior
2. After Postgres (tasks 3-4): run tournament, verify data in Postgres, migrate old SQLite data
3. After Grafana (tasks 5-6): start pod, run a game, see live data in dashboards
4. After leagues (tasks 7-8): create league, run 2 seasons, verify ELO persistence
