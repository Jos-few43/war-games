# Expansion v2: Play It For Real

**Date:** 2026-03-07
**Status:** Approved

## Overview

Finish stubbed CLI commands, add cloud-with-local-fallback support, and run the first real end-to-end game. Goal: make war-games playable, not just testable.

## 1. LLM Client Fallback

Add optional fallback model support to `TeamSettings` and `LLMClient`.

### Model Changes (`models.py`)

New optional fields on `TeamSettings`:
- `fallback_model: str = ""` — fallback base URL (e.g., Ollama endpoint)
- `fallback_model_name: str = ""` — fallback model name
- `fallback_api_key: str = ""` — fallback API key (same env var resolution)

### Client Changes (`llm/client.py`)

After exhausting primary retries (3 attempts), if fallback is configured:
1. Log warning: "Primary model failed, falling back to {fallback_model_name}"
2. Attempt fallback with 2 retries, same exponential backoff
3. If fallback also fails, raise as normal

Response gets `model_used: str` field so logs/TUI show which model answered.

### Fallback triggers

Same as existing retry triggers: `ReadTimeout`, `RemoteProtocolError`, `ConnectError`, HTTP 5xx, HTTP 429.

## 2. CLI Command: `crawl`

Wire existing `CveNvdCrawler` and `ExploitDbCrawler` to the CLI stub.

- Parse `--sources` flag (default: `nvd,exploitdb`)
- Initialize DB, run selected crawlers
- Print summary: counts per source
- Uses existing `Database.save_cves()` for persistence

## 3. CLI Command: `report`

Query DB for a specific round, print formatted summary.

- Add `get_round_result(round_number) -> RoundResult | None` to `Database` if needed
- Output: phase, outcome, red/blue scores, draft picks, attacks (severity + success), defenses (blocked + effectiveness), bug reports (title + severity), patches (title + addressed)

## 4. CLI Command: `export`

Export full season as markdown or JSON.

- **Markdown:** Season summary table (round, phase, outcome, scores) + per-round details
- **JSON:** List of all `RoundResult` objects + strategy stats

Output to stdout by default, `--output <path>` for file.

## 5. Config: `fallback-cloud.toml`

Cloud primary (OpenRouter via LiteLLM green, port 4002) with Ollama local fallback.

```toml
[game]
name = "season-fallback"
rounds = 3
turn_limit = 4
score_threshold = 10
phase_advance_score = 7.5

[draft]
picks_per_team = 3
style = "snake"

[teams.red]
name = "Red Team"
model = "http://localhost:4002"
model_name = "openrouter/auto"
fallback_model = "http://localhost:11434"
fallback_model_name = "qwen3:4b"
temperature = 0.8
timeout = 60.0
api_key = "$LITELLM_MASTER_KEY"

[teams.blue]
name = "Blue Team"
model = "http://localhost:4002"
model_name = "openrouter/auto"
fallback_model = "http://localhost:11434"
fallback_model_name = "qwen3:4b"
temperature = 0.4
timeout = 60.0
api_key = "$LITELLM_MASTER_KEY"

[teams.judge]
name = "Judge"
model = "http://localhost:4002"
model_name = "openrouter/auto"
fallback_model = "http://localhost:11434"
fallback_model_name = "qwen3:4b"
temperature = 0.2
timeout = 90.0
api_key = "$LITELLM_MASTER_KEY"

[crawler]
enabled = true
sources = ["nvd", "exploitdb"]
refresh_interval = "24h"

[output.vault]
enabled = true
path = "~/OpenClaw-Vault/WarGames"

[output.database]
path = "~/.local/share/wargames/state.db"
```

## 6. Live Run & Validation

Run full pipeline after implementation:

1. `wargames crawl --config config/fallback-cloud.toml`
2. `wargames start --config config/fallback-cloud.toml`
3. `wargames attach` — observe TUI
4. Fix bugs encountered during run
5. `wargames report 1` — verify CLI report
6. `wargames export --format markdown` — verify export

### Success criteria

- 3 rounds complete without crashes
- Fallback triggers at least once (can test by pointing primary at invalid URL)
- `crawl` populates CVE database
- `report` prints readable round summary
- `export` produces valid markdown/JSON
- Vault output contains round files, bug reports, patches, strategy notes

## Files Changed

| File | Change |
|---|---|
| `wargames/models.py` | Add fallback fields to TeamSettings |
| `wargames/llm/client.py` | Add fallback retry logic |
| `wargames/cli.py` | Wire crawl, report, export commands |
| `wargames/output/db.py` | Add get_round_result query (if needed) |
| `config/fallback-cloud.toml` | New preset |
| `tests/llm/test_client.py` | Fallback retry tests |
| `tests/test_cli.py` | CLI command tests |
