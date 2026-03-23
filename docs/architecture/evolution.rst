# Evolutionary Learning

How War Games implements evolutionary learning through strategy extraction and refinement.

## Strategy Lifecycle

```
1. Round Execution → Judge evaluates attack/defense
2. Strategy Extraction → Judge distills reusable tactics
3. Storage → Strategies saved to DB with win rate
4. Retrieval → High-win-rate strategies injected into prompts
5. Pruning → Low-win-rate strategies removed
```

## Strategy Types

### Attack Strategies

- Prompt injection patterns
- Code vulnerability exploits
- CVE-specific attacks
- Social engineering techniques

### Defense Strategies

- Input validation rules
- Sandbox configurations
- Output filtering patterns
- Rate limiting policies

### Draft Strategies

- Loadout selection heuristics
- Resource allocation patterns

## Win Rate Tracking

Each strategy tracks:
- **wins**: Number of rounds where strategy contributed to victory
- **total**: Total rounds where strategy was used
- **win_rate**: wins / total

Win rates update after each round.

## Strategy Injection

Before each round, `get_top_strategies()` retrieves highest win-rate strategies:

```python
strategies = strategy_store.get_top_strategies(
    team="red",
    phase=Phase.CODE_VULNS,
    limit=5
)
```

These are injected into the agent's prompt as context.

## Pruning

Strategies with win_rate < 0.3 are pruned to prevent stale advice accumulation.
