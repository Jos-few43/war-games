# Engine Components

Detailed documentation for game engine components.

## Game Engine (`wargames/engine/game.py`)

The `GameEngine` is the main orchestrator for running seasons.

### Key Methods

```python
async def run(self) -> AsyncGenerator[RoundResult, None]:
    """Run the season, yielding round results."""
    
async def start_season(self) -> None:
    """Initialize a new season."""
    
async def advance_phase(self) -> None:
    """Advance to next competition phase."""
```

## Round Engine (`wargames/engine/round.py`)

The `RoundEngine` executes individual rounds.

### Phase Flow

1. **Draft**: Assign loadout resources to each team
2. **Combat**: Execute turns where red attacks and blue defends
3. **Debrief**: Teams reflect on outcomes
4. **Strategy Extract**: Judge distills reusable strategies

## Draft Engine (`wargames/engine/draft.py`)

Handles team loadout selection. Supports:
- **Snake draft**: Alternating picks with value reversal
- **Linear draft**: Sequential picks per team

## Judge (`wargames/engine/judge.py`)

The judge scores attacks and defenses, extracts strategies.

### Scoring

- **Attack severity**: LOW=1, MEDIUM=3, HIGH=5, CRITICAL=8
- **Defense effectiveness**: Full block (2pts), partial block (1pt), miss (0pts)

## ELO System (`wargames/engine/elo.py`)

Standard Elo rating with dynamic K-factor based on games played.

## Tournament (`wargames/engine/swiss.py`)

Swiss-system pairing and standings management.
