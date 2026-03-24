# WARGames Package Knowledge Base

**Generated:** Tue Mar 24 2026
**Commit:** 0977a81
**Branch:** main

## OVERVIEW
Main package containing core game logic: engine, teams, CLI, loadouts, and supporting modules.

## STRUCTURE
```
wargames/
├── engine/        # Judge, scoring, ELO, Swiss, worker, strategy
├── teams/         # Red/blue team implementations
├── llm/           # LLM providers and tool abstractions
├── crawler/       # CVE/NVD/ExploitDB scraping utilities
├── output/        # Database persistence layer
├── tui/           # Textual-based terminal user interface
├── crew/          # Maintenance crew manager
├── crewai/        # CrewAI task definitions (optional)
├── loadouts.py    # Named configurations for teams
├── cli.py         # Command-line interface
└── config.py      # TOML configuration loading
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Game engine | `wargames/engine/` | Core scoring, judgment, ELO, Swiss tournament |
| Team behaviors | `wargames/teams/` | Red team (attacks) and blue team (defenses) |
| LLM integration | `wargames/llm/` | Gemini provider abstraction and tool interfaces |
| Data acquisition | `wargames/crawler/` | CVE and exploit data scraping pipelines |
| Data storage | `wargames/output/` | Database models, queries, and persistence |
| User interface | `wargames/tui/` | Textual-based dashboard and screens |
| Automation | `wargames/worker.py` | Background worker process (see engine/) |
| Team presets | `wargames/loadouts.py` | YAML-defined team configurations |
| CLI commands | `wargames/cli.py` | All subcommands: start, attach, status, etc. |
| Config handling | `wargames/config.py` | TOML parsing with env var resolution ($VAR) |

## CONVENTIONS
- **Error handling**: Explicit exception handling; avoids bare `except:` clauses
- **Imports**: Lazy imports in CLI for faster startup; explicit in engine/modules

## ANTI-PATTERNS (THIS PACKAGE)
- **Inconsistent test `__init__.py`**: Some test subpackages have empty `__init__.py` (consider removing if not needed for package structure)

## UNIQUE STYLES
- **Lazy CLI**: Command modules imported only when invoked (fast startup)

## COMMANDS
```bash
# Core gameplay
wargames start --config config/default.toml        # Start a season
wargames attach                                    # Attach live TUI
wargames status                                    # Check season status
wargames pause                                     # Pause running season
wargames resume                                    # Resume paused season

# Utility & development
wargames sandbox --config config/default.toml      # Single-round test
wargames sandbox --config config/default.toml --loadout red=aggressive,blue=defensive  # With loadouts
wargames tournament --roster config/roster-example.toml  # Swiss tournament across models
wargames crawl --sources nvd,exploitdb             # Crawl CVEs from NVD/ExploitDB
wargames report <round_number>                     # View round results
wargames ladder                                    # ELO leaderboard
wargames stats                                     # Tournament statistics
wargames export --format json --output results.json # Export results

# Testing
pytest                                             # Full test suite
pytest tests/engine/                               # Engine-specific tests
pytest -k "test_scoring"                           # Scoring-related tests only
```

## NOTES
- **Python version**: Requires 3.12+ (uses modern type syntax like `list[str] | None`)
- **API keys**: Must use env var refs in TOML (`$LITELLM_MASTER_KEY`), never plaintext
- **Directory depth**: Max 3 levels in source (excluding tests)
- **Worker process**: `wargames/worker.py` is the background service entry point
- **Test mirroring**: `tests/` package structure mirrors `wargames/` for direct correspondence
- **Optional deps**: `[crewai]` and `[crew]` in pyproject.toml for optional enhancements