# War Games Expansion Design

**Date:** 2026-03-06
**Status:** Approved

## Overview

Six workstreams to evolve the war-games project from a working prototype into a full competitive LLM security simulation with evolutionary learning, real CVE integration, structured reporting, and a live TUI dashboard.

## 1. Commit Current Changes

Uncommitted improvements: LLM client retry logic (3 retries, exponential backoff, 300s timeout), improved vault output (phase names, draft picks section, wikilinks, severity tags, truncated descriptions), vault writer connected to worker loop, models updated to qwen3:4b, new test-multi config.

## 2. Evolutionary Learning (Dual Store)

### DB Strategy Store (for agents)

New `strategies` table:

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| team | TEXT | "red" or "blue" |
| phase | INTEGER | Phase enum value |
| strategy_type | TEXT | "attack", "defense", or "draft" |
| content | TEXT | Strategy description |
| win_rate | REAL | Success rate when used |
| usage_count | INTEGER | Times used |
| created_round | INTEGER | Round that generated it |

New `engine/strategy.py` with `StrategyStore` class:
- `extract_strategies(round_result) -> list[Strategy]` — parse debriefs for actionable strategies
- `get_top_strategies(team, phase, limit=5) -> list[Strategy]` — load best strategies by win_rate
- `update_win_rates(round_result)` — update stats for strategies used in the round

Before each round, top strategies are injected into agent system prompts as "proven tactics from past rounds."

### Vault Knowledge Base (for humans)

New `strategies/` folder in vault output:
- Per-phase strategy files: `strategies/phase-1-prompt-injection.md`
- Appended after each round with new learnings
- Wikilinks back to source rounds

## 3. Structured Bug Reports & Patches

### Agent Changes

**RedTeamAgent** — new `generate_bug_report(attack_desc, target, tools) -> BugReport`:
- LLM outputs JSON matching BugReport schema
- Fields: title, severity, domain, steps_to_reproduce, proof_of_concept, impact

**BlueTeamAgent** — new `generate_patch(bug_report, target, tools) -> Patch`:
- LLM outputs JSON matching Patch schema
- Fields: title, fixes, strategy, changes, verification

### Round Engine Changes

After each successful attack:
1. Red generates BugReport from the attack
2. Blue generates Patch from the BugReport
3. Judge evaluates patch quality via new `evaluate_patch(bug_report, patch) -> PatchScore`

New fields on `RoundResult`:
- `bug_reports: list[BugReport]`
- `patches: list[Patch]`

### Persistence

- New `bug_reports` and `patches` DB tables
- Vault writer calls existing `write_bug_report` and `write_patch` methods

## 4. Crawler to Game Pipeline

### Draft Pool Injection

`DraftPool.from_cves(db) -> DraftPool` — queries `crawled_cves` table, converts to `Resource` objects with category `"cve"`.

Phase behavior:
- Phase 1-2: `DraftPool.default()` (existing tools only)
- Phase 3 (REAL_CVES): mixed pool — default tools + CVE resources
- Phase 4 (OPEN_ENDED): full pool — tools + CVEs + strategy-derived resources

### Scenario Generation

New `engine/scenario.py` with `ScenarioGenerator`:
- `generate_target(cve_resources, phase) -> str` — creates target description from drafted CVE details
- Replaces generic `_default_target()` for phases 3-4
- Judge receives CVE context for more accurate scoring

### Game Mechanic

Red drafting a CVE = offensive knowledge (specific exploit details).
Blue drafting a CVE = defensive forewarning (deny red that knowledge).
Draft becomes a strategic intelligence competition.

## 5. TUI Dashboard

### Event Bridge

New `tui/bridge.py` with `EventBridge`:
- Wraps `asyncio.Queue`
- Worker pushes events via `RoundEngine.on_event()` callback
- TUI drains queue via `set_interval(0.5, consume_events)`

### Live Feed Updates

| Event | TUI Action |
|---|---|
| `draft_complete` | Update team panels, log draft picks |
| `attack` | Color-coded log entry (green=success, red=fail), update score |
| `defense` | Log entry (blue=blocked, yellow=missed) |
| `round_complete` | Update season stats, recent rounds, separator line |

### Controls

- `p` — pause/resume via shared `asyncio.Event` on worker
- `d` — modal with full draft history from DB
- `r` — modal with recent round summaries
- Header shows "PAUSED" state

## 6. Live Game Run

### Pre-flight
- Verify Ollama running, qwen3:4b available
- Use `config/test-multi.toml` (3 rounds x 4 turns)

### Run Sequence
1. `wargames crawl` — populate CVE database
2. `wargames start` — background game
3. `wargames attach` — TUI

### Validation
- 3 rounds complete without crashes
- Vault: round files, bug reports, patches, strategy notes
- DB: rounds, attacks, defenses, draft picks, strategies
- TUI: live event display

## Execution Order

1 → 2 → 3 → 4 → 5 → 6 (dependency chain: each builds on previous)

## New Files

| File | Purpose |
|---|---|
| `wargames/engine/strategy.py` | Strategy extraction, storage, retrieval |
| `wargames/engine/scenario.py` | CVE-based target/scenario generation |
| `wargames/tui/bridge.py` | Async event bridge between worker and TUI |

## Test Coverage

Each workstream gets corresponding tests:
- Strategy store: extraction, retrieval, win rate updates
- Bug reports: structured output parsing, fallback on bad JSON
- CVE draft pool: from_cves, mixed pool construction
- Scenario generator: target description from CVE data
- Event bridge: queue push/drain, TUI widget updates
- Patch scoring: judge evaluation of patch quality
