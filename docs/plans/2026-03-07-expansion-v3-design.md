# Expansion v3: Tournament + Gameplay + Observability

## Goal

Add MVP tournament system (ELO ratings, leaderboards, season tracking), richer gameplay (sandbox mode, team loadouts), and observability (token tracking, cost metrics, stats command).

## Architecture

Three independent pillars built sequentially. Each pillar adds new modules, DB tables, and CLI commands without modifying existing gameplay logic. Feature pillars approach keeps changes isolated and testable.

## Pillar 1: Tournament System

### ELO Rating Engine

New module: `wargames/engine/elo.py`

- Standard ELO calculation: K-factor=32, initial rating=1500
- Each model gets a persistent rating updated after each round
- Win = full K adjustment, draw = half, loss = negative

### Database Schema

New table `model_ratings`:

```sql
CREATE TABLE model_ratings (
    model_name TEXT PRIMARY KEY,
    rating REAL DEFAULT 1500.0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    draws INTEGER DEFAULT 0,
    last_played TEXT
);
```

New table `seasons`:

```sql
CREATE TABLE seasons (
    season_id TEXT PRIMARY KEY,
    config_name TEXT,
    started_at TEXT,
    ended_at TEXT,
    winner TEXT
);
```

- `rounds` table gets new `season_id TEXT` column linking to current season.

### CLI: `wargames ladder`

- Reads `model_ratings` table, prints ranked table sorted by ELO
- Columns: Rank, Model, Rating, W/L/D, Last Played

### Integration

- `GameEngine` calls `update_elo()` after each round outcome
- `wargames start` creates a new season record; sets `ended_at` + `winner` on completion

---

## Pillar 2: Gameplay

### Sandbox Mode

New module: `wargames/engine/sandbox.py`

- Single-round execution, no DB persistence, no season tracking
- Reuses existing TOML config format (ignores `rounds` field)
- Runs: draft → match → print results to stdout
- Use case: prompt tuning, model comparison, quick experiments

### CLI: `wargames sandbox`

- `wargames sandbox --config config/fallback-cloud.toml`
- Optional `--loadout red=aggressive,blue=defensive` override
- Prints round result as formatted text (reuse report formatter)

### Team Loadouts

New module: `wargames/engine/loadouts.py`

4 built-in presets:

| Preset | Resources |
|---|---|
| `aggressive` | fuzzer, sqli_kit, prompt_injector, priv_esc_toolkit |
| `defensive` | waf_rules, rate_limiter, input_validation, anomaly_detector |
| `balanced` | fuzzer, waf_rules, port_scanner, input_validation |
| `recon` | port_scanner, log_analyzer, network_mapper |

### TOML Config

```toml
[teams.red]
loadout = "aggressive"  # or custom list below
# loadout_custom = ["fuzzer", "sqli_kit", "custom_tool"]

[teams.blue]
loadout = "defensive"
```

### Integration

- `DraftEngine` checks for loadout in team config
- If loadout set, skips random draft and uses preset picks
- Custom loadout (`loadout_custom`) takes priority over named preset

---

## Pillar 3: Observability

### Token Tracking

Modify: `wargames/llm/client.py`

- Parse `usage.prompt_tokens` and `usage.completion_tokens` from OpenAI-compatible response
- `LLMClient` accumulates `total_prompt_tokens` and `total_completion_tokens` as instance attributes
- New method: `get_usage() -> dict` returns current totals and resets counters

### Database Schema

New table `token_usage`:

```sql
CREATE TABLE token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_number INTEGER,
    team TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    model_used TEXT,
    cost REAL
);
```

### Cost Configuration

Optional TOML section:

```toml
[costs]
"llama-3-70b" = 0.00059      # $/1K input tokens
"qwen3:4b" = 0.0             # local = free
```

Cost calculation: `(prompt_tokens / 1000) * rate + (completion_tokens / 1000) * rate`

### TUI: TokenPanel Widget

- New widget in `wargames/tui/app.py`
- Shows per-team running token count and cost
- Updates after each turn via EventBridge

### CLI: `wargames stats`

- Aggregates from `token_usage` and `model_ratings` tables
- Output: total tokens, total cost, win rates by model, tokens per round average
- Formatted table output

---

## New Files Summary

| File | Purpose |
|---|---|
| `wargames/engine/elo.py` | ELO rating calculations |
| `wargames/engine/sandbox.py` | Single-round sandbox executor |
| `wargames/engine/loadouts.py` | Team loadout presets |
| `tests/engine/test_elo.py` | ELO calculation tests |
| `tests/engine/test_sandbox.py` | Sandbox mode tests |
| `tests/engine/test_loadouts.py` | Loadout resolution tests |
| `tests/test_stats.py` | Stats command tests |

## Modified Files Summary

| File | Changes |
|---|---|
| `wargames/models.py` | Add `loadout`, `loadout_custom`, `CostsSettings` fields |
| `wargames/llm/client.py` | Parse token usage from responses |
| `wargames/output/db.py` | Add `model_ratings`, `seasons`, `token_usage` tables + methods |
| `wargames/cli.py` | Add `ladder`, `sandbox`, `stats` commands |
| `wargames/engine/game.py` | ELO updates after rounds, season lifecycle |
| `wargames/engine/draft.py` | Loadout support in draft phase |
| `wargames/tui/app.py` | TokenPanel widget |

## Success Criteria

1. `wargames ladder` shows ELO rankings after a completed season
2. `wargames sandbox --config ...` runs a single round and prints results
3. Loadout presets skip draft and use configured tools
4. Token usage tracked and visible in TUI during live game
5. `wargames stats` shows aggregated metrics
6. All existing tests continue to pass
