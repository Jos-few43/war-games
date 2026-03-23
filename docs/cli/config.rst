# Configuration Reference

This document describes all configuration options available in War Games TOML configuration files.

## Game Configuration

### [game] Section

```toml
[game]
name = "Season 1"
rounds = 100
turn_limit = 10
score_threshold = 20
phase_advance_min_avg = 15.0
phase_advance_min_rounds = 5
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `name` | str | - | Season name |
| `rounds` | int | 100 | Total rounds per season |
| `turn_limit` | int | 10 | Max turns per round |
| `score_threshold` | int | 20 | Points for red win |
| `phase_advance_min_avg` | float | 15.0 | Min avg score to advance phase |
| `phase_advance_min_rounds` | int | 5 | Consecutive rounds for phase advance |

## Draft Configuration

### [draft] Section

```toml
[draft]
picks_per_team = 3
style = "snake"  # or "linear"
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `picks_per_team` | int | 3 | Number of loadout picks per team |
| `style` | str | "snake" | Draft style: "snake" or "linear" |

## Team Configuration

### [teams.red] / [teams.blue] / [teams.judge] Sections

```toml
[teams.red]
model = "openai/gpt-4o"
temperature = 0.8
loadout = "aggressive"

[teams.blue]
model = "openai/gpt-4o"
temperature = 0.5
loadout = "defensive"

[teams.judge]
model = "anthropic/claude-sonnet-4-20250514"
temperature = 0.3
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `model` | str | - | LiteLLM model identifier |
| `temperature` | float | 0.7 | Sampling temperature |
| `loadout` | str | "default" | Loadout preset name |

## Loadout Presets

Loadouts define resource allocation for teams:

```toml
[loadouts.red.aggressive]
prompt_injection = 3
code_vuln = 2
real_cve = 1
open_ended = 1

[loadouts.blue.defensive]
input_validation = 3
sandboxing = 2
output_filtering = 2
```

## Scoring Overrides

```toml
[scoring.attacks]
low = 1
medium = 3
high = 5
critical = 8

[scoring.defense]
full_block = 2
partial_block = 1
miss = 0

[scoring.win_conditions]
auto_win_threshold = 25
draw_on_timeout = true
```

## Database Configuration

```toml
[output.database]
path = "$HOME/.local/share/wargames/state.db"
```

## Vault Export (Optional)

```toml
[output.vault]
enabled = false
path = "~/Documents/OpenClaw-Vault/01-RESEARCH/WarGames"
```

## Cost Tracking

```toml
[costs]
openai/gpt-4o = 0.0025
anthropic/claude-sonnet-4-20250514 = 0.003
```

## Environment Variable Substitution

All configuration values support environment variable substitution:

```toml
[teams.red]
api_key = "$OPENAI_API_KEY"

[teams.judge]
api_key = "$ANTHROPIC_API_KEY"
```

Use `$VAR_NAME` or `${VAR_NAME}` syntax. Values are resolved at runtime.
