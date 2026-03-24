# PROJECT KNOWLEDGE BASE

**Generated:** Tue Mar 24 2026
**Commit:** 0977a81
**Branch:** main

## OVERVIEW
War Games is a red team / blue team LLM competition framework with evolutionary learning. Two LLM agents compete across structured phases while a third LLM acts as judge. Built with Python 3.12+, Textual TUI, httpx, aiosqlite, Pydantic v2.

## STRUCTURE
```
war-games/
├── wargames/              # Main package: engine, teams, CLI, loadouts
├── tests/                 # Test suite (mirrors package structure)
├── config/                # TOML configuration files (default, tournament, roster)
└── antigravity-bridge/    # Experimental/unrelated bridge utility
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Run a season | `wargames/worker.py` | Background worker; entry: `wargames start` |
| Red team attacks | `wargames/teams/red.py` | Generates attacks and bug reports |
| Blue team defenses | `wargames/teams/blue.py` | Generates defenses and patches |
| Judge scoring | `wargames/engine/judge.py` | Scores attacks/defenses via LLM |
| Strategy extraction | `wargames/engine/strategy.py` | Extracts, stores, updates win-rates |
| ELO rating calc | `wargames/engine/elo.py` | Standard ELO with dynamic K-factor |
| Swiss tournament | `wargames/engine/swiss.py` | Pairing, standings, ELO persistence |
| TUI dashboard | `wargames/tui/app.py` | Textual live dashboard |
| CLI commands | `wargames/cli.py` | All subcommands (start, attach, status, etc.) |
| Config loading | `wargames/config.py` | TOML parsing with env var resolution |
| CVE crawling | `wargames/crawler/` | NVD and ExploitDB scrapers |
| Loadout presets | `wargames/loadouts.py` | Named configurations for teams |
| Database layer | `wargames/output/db.py` | aiosqlite persistence layer |
| Test fixtures | `tests/` | Mirrors `wargames/` package structure |

## CONVENTIONS
- **Type hints**: Strict mypy (`strict = true`) with Python 3.12+ syntax (`list[str] | None`)
- **Linter**: Ruff with line length 100, single quotes, ignores E501
- **Test runner**: Pytest with `asyncio_mode = "strict"` and 10s timeout
- **Entry point**: CLI via `pyproject.toml` (`wargames = "wargames.cli:main"`)
- **Lazy imports**: CLI uses lazy imports per command for faster startup
- **Async patterns**: Proper `async`/`await` usage throughout engine
- **Config**: TOML files with `$ENV_VAR` references (never plaintext secrets)

## ANTI-PATTERNS (THIS PROJECT)
- **Missing `py.typed`**: PEP 561 marker absent despite strict mypy
- **Duplicate crawlers**: `cve.py` and `nvd.py` both fetch NVD CVEs (consider consolidation)
- **`__pycache__` in source**: Cache directories committed (should be gitignored)
- **Empty `__init__.py`**: `wargames/engine/__init__.py` is empty (0 lines)
- **Redundant packages**: `wargames/crew/` and `wargames/crewai/` overlap in purpose
- **Unrelated directory**: `antigravity-bridge/` appears detached from main package

## UNIQUE STYLES
- **Phase progression**: Automatic advancement when round scores exceed threshold
- **Evolutionary learning**: Strategy extraction/storage/pruning after each round
- **Sandbox mode**: Single-round quick test (`wargames sandbox`)
- **Cost tracking**: Per-model token usage tracking in `[costs]` section
- **Vault integration**: Optional OpenClaw Vault integration via `[output.vault]`

## COMMANDS
```bash
# Install in editable mode with dev deps
pip install -e ".[dev]"

# Start a new season (runs in foreground)
wargames start --config config/default.toml

# Attach live TUI dashboard
wargames attach

# Check season status
wargames status

# Pause/resume running season
wargames pause
wargames resume

# Run single-round sandbox (quick iteration)
wargames sandbox --config config/default.toml
wargames sandbox --config config/default.toml --loadout red=aggressive,blue=defensive

# Run Swiss tournament across multiple models
wargames tournament --roster config/roster-example.toml

# Crawl CVEs from NVD/ExploitDB
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

## NOTES
- **Do not commit**: `state.db` (runtime game state), `litellm.pid` (worker PID file)
- **Python version**: Requires 3.12+ (uses modern type syntax like `list[str] | None`)
- **Container**: Designed to run in `wargames-dev` distrobox container (Fedora Toolbox 43)
- **API keys**: Must use env var refs in TOML (`$LITELLM_MASTER_KEY`), never plaintext
- **Directory depth**: Max 3 levels in source (excluding tests)
- **Code ratio**: ~76% Python files in source tree (high signal-to-noise)