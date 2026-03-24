# WARGAMES ENGINE Package Knowledge Base

**Generated:** Tue Mar 24 2026
**Commit:** 0977a81
**Branch:** main

## OVERVIEW
Core game mechanics: judgment, scoring, ELO rating, Swiss tournament, worker processes, and strategy extraction.

## STRUCTURE
```
wargames/engine/
├── judge.py        # LLM-based scoring of attacks/defenses
├── elo.py          # ELO rating calculation with dynamic K-factor
├── swiss.py        # Swiss tournament pairing and persistence
├── strategy.py     # Win-rate extraction, storage, pruning
├── worker.py       # Background worker process (runs seasons)
├── __init__.py     # Package initializer (currently empty)
└── ...             # Supporting modules (loadout, output, etc.)
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Judge scoring | `judge.py` | Scores attacks/defenses via LLM |
| ELO calculation | `elo.py` | Standard ELO with dynamic K-factor |
| Swiss tournament | `swiss.py` | Pairing, standings, ELO persistence |
| Strategy extraction | `strategy.py` | Extracts, stores, updates win-rates |
| Worker process | `worker.py` | Background worker; entry: `wargames start` |
| Loadout handling | `loadout.py` | Named team configurations |
| Database interface | `output/db.py` | Persistence layer (see output/) |

## CONVENTIONS
- **Type hints**: Strict mypy (`strict = true`) with Python 3.12+ syntax
- **Async patterns**: Proper `async`/`await` throughout (engine is I/O bound)
- **Error handling**: Specific exceptions caught; avoids bare `except:`
- **Imports**: Explicit imports (no lazy loading here - used in core paths)
- **Constants**: UPPER_CASE named constants at module top
- **Docstrings**: Google style for public functions/classes

## ANTI-PATTERNS (THIS PACKAGE)
- **Empty `__init__.py`**: Currently 0 lines; should export key symbols
- **Missing `py.typed`**: Despite strict mypy in root, no PEP 561 marker
- **Direct file paths**: Some modules use relative paths; consider config-driven
- **Tight LLM coupling**: Judge couples to specific LLM provider; consider abstraction

## UNIQUE STYLES
- **Dynamic K-factor**: ELO uses volatility-based adjustment (see `elo.py`)
- **Score threshold progression**: Auto-advance when scores exceed threshold
- **Strategy pruning**: Low win-rate strategies discarded after N rounds
- **Cost tracking**: Per-model token usage in worker (`[costs]` section)
- **Vault integration**: Optional encrypted storage via `[output.vault]`

## COMMANDS
```bash
# Engine-specific operations (via CLI)
wargames start --config config/default.toml   # Uses worker.py internally
wargames tournament --roster config/roster-example.toml  # Uses swiss.py
wargames report <round_number>                # Reads from output.db
wargames ladder                               # ELO leaderboard (from elo.py)
wargames stats                                # Tournament statistics
wargames export --format json --output results.json  # Exports from output.db
```

## NOTES
- **Python version**: Requires 3.12+ (uses `list[str] | None` syntax)
- **API keys**: Must use `$ENV_VAR` in TOML; never plaintext in engine/
- **Worker vs CLI**: `worker.py` runs seasons; CLI (`wargames start`) launches it
- **Test correspondence**: `tests/engine/` mirrors this package structure
- **Future abstraction**: Consider LLM provider interface for judge.py