# Evolutionary Learning Improvements — Design

## Goal

Fix three structural problems in the strategy evolution system that prevent meaningful selective pressure: lack of attribution, no pruning, and no time decay.

## Problems Observed

1. **No attribution**: `update_win_rates()` updates ALL strategies for a team/phase, even ones not loaded that round. Strategies get credit/blame for rounds they didn't influence.
2. **No pruning**: Strategies accumulate indefinitely. Losing strategies (win_rate=0.0) persist and get recommended.
3. **No time decay**: Old high-win-rate strategies dominate over newer, potentially better ones.

## Design

### 1. Per-Strategy Attribution

- Add `id: int | None` to `Strategy` model
- `get_top_strategies()` returns strategies with DB IDs
- `game.py` tracks which strategy IDs were loaded per round
- `update_win_rates()` signature changes from `(team, phase, round_won, db)` to `(strategy_ids, round_won, db)` — only updates the specific strategies that were injected into prompts

### 2. Strategy Pruning with Graveyard

- Add `active INTEGER DEFAULT 1` column to strategies table
- Pruning soft-deletes by setting `active = 0` (graveyard)
- `get_top_strategies()` filters `WHERE active = 1`
- New `prune_strategies(team, phase, db)` function:
  - Deactivate strategies with `usage_count >= 3 AND win_rate < 0.2`
  - Cap pool at 20 active strategies per team/phase (deactivate lowest-rated excess)
- Dedup on insert: before saving a new strategy, check word overlap against all strategies (active + inactive). Skip if >70% overlap with any existing strategy.

### 3. Time Decay

- `get_top_strategies()` takes `current_round` parameter
- Selection uses composite score: `win_rate * 0.7 + recency_bonus * 0.3`
- Recency bonus: `1.0 / (1 + (current_round - created_round))`
- Recent winners beat old winners. Old winners still beat recent losers.

### 4. Cross-Game Pool (Deferred)

Deferred to PostgreSQL migration (V5 Step 3). Config model (`EvolutionSettings`) will be added now as a placeholder with `pool_enabled = false`.

## Files Changed

| File | Changes |
|------|---------|
| `wargames/models.py` | Add `id` to Strategy, add `EvolutionSettings` |
| `wargames/engine/strategy.py` | Attribution, pruning, decay, dedup |
| `wargames/engine/game.py` | Pass strategy IDs, call prune, pass current_round |
| `wargames/output/db.py` | Add `active` column to strategies schema |
| `tests/engine/test_strategy.py` | Tests for all new behavior |

## Not Changing

- Agent prompts (red.py, blue.py) — strategy injection format stays the same
- Config loading — no new TOML sections needed yet
- Database backend — stays SQLite, PostgreSQL migration is separate
