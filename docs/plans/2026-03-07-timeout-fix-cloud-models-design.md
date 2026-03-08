# Timeout Fix & Cloud Model Support — Design

## Goal

Fix the httpx.ReadTimeout crash that kills the game mid-season, harden crawler HTTP calls, and add cloud model config presets via LiteLLM green (port 4002).

## Architecture

Three independent changes to the war-games codebase:

1. **LLM client retry hardening** — Add `ReadTimeout` to the retry exception list in `llm/client.py`. Same 3x retry with exponential backoff. No timeout value change (300s is adequate).

2. **Crawler error resilience** — Add retry logic to `crawler/cve.py` and `crawler/exploitdb.py` for transient HTTP errors and timeouts.

3. **Cloud model preset configs** — New TOML files that route through LiteLLM green (port 4002) for cloud model access. Two presets: cloud-judge (local teams, cloud judge) and full-cloud (all cloud).

## Components

### LLM Client (`wargames/llm/client.py`)

Current retry list: `RemoteProtocolError`, `ConnectError`
New retry list: `RemoteProtocolError`, `ConnectError`, `ReadTimeout`

No other changes. The 300s timeout stays. Worst case per call: ~15 min (3 retries × 300s + backoff).

### Crawlers (`wargames/crawler/cve.py`, `exploitdb.py`)

Add try/except around HTTP calls with retry on transient errors. Use 30s timeout (already set). Catch `httpx.TimeoutException`, `httpx.ConnectError`. Log warning and continue on permanent failure (don't crash the game over a failed crawl).

### Config Presets

**`config/cloud-judge.toml`** — Red/blue use Ollama (localhost:11434), judge uses LiteLLM green (localhost:4002) with claude-sonnet-4-5. Best cost/quality tradeoff.

**`config/full-cloud.toml`** — All teams use LiteLLM green. Red gets claude-sonnet-4-5 (creative attacks need strong model), blue gets claude-haiku-4-5 (defensive analysis is more structured), judge gets claude-sonnet-4-5.

## Testing

- Unit test: mock httpx to raise ReadTimeout, verify retry behavior
- Unit test: crawler handles timeout gracefully without crashing
- Integration: run with test-local config, verify game completes
- Manual: run with cloud-judge config against live LiteLLM

## Non-Goals

- Direct API provider support (Anthropic, OpenAI SDKs) — use LiteLLM routing
- resmgr VRAM monitoring fix — separate project, separate PR
- Config profile/preset selector in CLI — just use `--config` flag
