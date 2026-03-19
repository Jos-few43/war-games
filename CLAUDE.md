# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## What This Is

War Games is a red team / blue team LLM competition framework with evolutionary learning. Two LLM agents compete across structured phases: the red team launches attacks (prompt injection, code vulnerabilities, real CVEs, open-ended exploits) while the blue team defends. A third LLM acts as judge. Strategies extracted from each round are stored and used to improve future performance. A Swiss-system tournament mode allows ranking multiple models against each other with ELO ratings.

## Tech Stack

| Component | Library / Version |
|---|---|
| Language | Python 3.12+ |
| TUI | Textual >= 0.85 |
| HTTP client | httpx >= 0.27 |
| Database | aiosqlite >= 0.20 (SQLite) |
| Data models | Pydantic v2 >= 2.10 |
| Config parsing | tomli >= 2.0 |
| Test runner | pytest + pytest-asyncio (strict mode) |
| Build system | setuptools >= 75 |

## Project Structure

```
wargames/               # Main Python package
  cli.py               # CLI entry point — all subcommands
  config.py            # Config loading (load_config, load_roster)
  models.py            # Pydantic models: GameConfig, RoundResult, Strategy, etc.
  worker.py            # Background worker — runs the season loop, writes PID file
  engine/
    game.py            # GameEngine — season loop, phase advancement, ELO updates
    round.py           # RoundEngine — per-round draft/combat/debrief orchestration
    draft.py           # DraftEngine — snake/linear draft pick selection
    judge.py           # Judge — scores attacks and defenses via LLM
    strategy.py        # Strategy extraction, storage, win-rate updates, pruning
    elo.py             # ELO rating calculation
    swiss.py           # TournamentRunner — Swiss-system pairing and standings
    sandbox.py         # SandboxRunner — single-round quick test mode
    scenario.py        # Scenario/CVE scenario generation
    loadouts.py        # Named loadout presets for teams
  teams/
    red.py             # RedTeamAgent — generates attacks and bug reports
    blue.py            # BlueTeamAgent — generates defenses and patches
  llm/
    client.py          # LLMClient — async httpx wrapper with token usage tracking
  crawler/
    cve.py             # NVDCrawler — fetches CVEs from NVD API
    exploitdb.py       # ExploitDBCrawler — fetches from ExploitDB
  output/
    db.py              # Database — aiosqlite persistence layer
    vault.py           # Vault writer — optional OpenClaw Vault integration
  tui/
    app.py             # WarGamesTUI — Textual live dashboard
    bridge.py          # Event bridge between worker and TUI

config/                # TOML config files
  default.toml         # Default local config
  tournament.toml      # Tournament config
  roster-example.toml  # Example roster for tournaments
  scoring/             # Scoring profile overrides

tests/                 # Pytest test suite (mirrors package structure)
```

## Key Commands

```bash
# Install in editable mode with dev deps
pip install -e ".[dev]"

# Start a new season (runs in foreground, use nohup/tmux for background)
wargames start --config config/default.toml

# Attach the live TUI dashboard to a running season
wargames attach

# Check current season status
wargames status

# Pause / resume a running season
wargames pause
wargames resume

# Run a single-round sandbox (no DB, quick iteration)
wargames sandbox --config config/default.toml
wargames sandbox --config config/default.toml --loadout red=aggressive,blue=defensive

# Run a Swiss tournament across multiple models
wargames tournament --roster config/roster-example.toml

# Crawl CVEs from NVD and ExploitDB
wargames crawl --sources nvd,exploitdb

# View results
wargames report <round_number>
wargames ladder
wargames stats
wargames export --format markdown
wargames export --format json --output results.json

# Run tests
pytest
pytest tests/engine/
pytest -k "test_scoring"
```

## Architecture

### Game Loop

```
wargames start
  └── Worker.run()
        └── GameEngine.run()  [async generator]
              for each round:
                1. Draft phase    — DraftEngine assigns loadout resources to each team
                2. Combat phase   — N turns:
                     RedTeamAgent  generates attack
                     BlueTeamAgent generates defense
                     Judge         scores attack severity + defense effectiveness
                3. Debrief        — each team reflects on the round outcome
                4. Strategy extract — Judge distills reusable strategies from the round
                5. Strategy update — win rates updated; low-rate strategies pruned
                6. ELO update     — model ratings adjusted based on outcome
                7. Phase check    — advance phase if avg score threshold met
              yield RoundResult
```

### Phase Progression

Phases advance automatically when recent round average score exceeds `phase_advance.min_avg_score` over `min_rounds` consecutive rounds:

| Phase | Domain |
|---|---|
| 1 — PROMPT_INJECTION | Prompt injection attacks |
| 2 — CODE_VULNS | Code vulnerability exploitation |
| 3 — REAL_CVES | CVEs fetched from NVD/ExploitDB |
| 4 — OPEN_ENDED | Unconstrained red team attacks |

### Scoring

- Attacks scored by severity: LOW=1, MEDIUM=3, HIGH=5, CRITICAL=8 points
- Defense effectiveness thresholds determine full block (2pts), partial block (1pt), or miss
- Blue wins if red never reaches `score_threshold` across all turns
- Red wins on threshold breach; red critical win on auto-win trigger
- Timeout (no resolution in `turn_limit` turns) counts as a draw for ELO

### Swiss Tournament

`TournamentRunner` runs a configurable number of Swiss rounds, pairing models by current standing. Each match plays `games_per_match` games (roles swapped for fairness). ELO ratings persist to the shared database. Final standings are printed ranked by rating.

### Evolutionary Learning

After each round, `extract_strategies` asks the judge to distill what worked into structured strategy objects (attack, defense, draft). These are stored in the DB keyed by team + phase. Before each round, `get_top_strategies` retrieves the highest win-rate strategies and injects them into agent prompts. Strategies with low win rates are pruned to prevent stale advice from accumulating.

### ELO Ratings

Starting rating: 1500. K-factor is dynamic (higher for new models with fewer games). `calculate_elo` follows standard Elo formula. Ratings are persisted in the `model_ratings` table and viewable via `wargames ladder`.

## Container

Run inside **wargames-dev** (Fedora toolbox 43):

```bash
distrobox enter wargames-dev
cd ~/PROJECTz/war-games
```

Or via the container router:

```bash
ctr wargames
```

The worker PID file and SQLite database are written to `~/.local/share/wargames/` inside the container.

## Configuration

Config files are TOML. Key sections:

- `[game]` — name, rounds, turn_limit, score_threshold, phase_advance_score
- `[draft]` — picks_per_team, style (snake/linear)
- `[teams.red]` / `[teams.blue]` / `[teams.judge]` — model endpoint, temperature, loadout
- `[costs]` — per-model $/1K token rates for usage tracking
- `[scoring]` — override attack points, defense rewards, win conditions, phase advance thresholds
- `[output.database]` — path to state.db (use `$HOME` not hardcoded `/home/yish`)
- `[output.vault]` — optional OpenClaw Vault integration

API keys in config files must use env var refs (`$LITELLM_MASTER_KEY`), never plaintext.

## Things to Avoid

- Do not hardcode `/home/yish` — use `$HOME` or `Path("~/.local/share/wargames/").expanduser()`
- Do not commit `state.db` — it contains runtime game state and grows unboundedly
- Do not commit `litellm.pid` — runtime artifact
- Do not skip tests — run `pytest` before committing engine changes; async tests require `pytest-asyncio` with `asyncio_mode = "strict"`
- Do not install Python deps on the host — use the `wargames-dev` distrobox container
- Do not put API keys in TOML config files directly — use `$ENV_VAR` refs resolved by `TeamSettings.resolve_env_vars`
- Do not mix tournament DB state with season DB state if sharing a database path across configs
