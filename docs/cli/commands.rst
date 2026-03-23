# CLI Commands

Reference documentation for all War Games command-line interface commands.

## Core Commands

### start

Start a new season of War Games.

```bash
wargames start [--config CONFIG]
```

**Arguments:**
- `--config`: Path to configuration file (default: `config/default.toml`)

### attach

Attach the TUI to a running game.

```bash
wargames attach
```

### status

Show current game status.

```bash
wargames status
```

### pause / resume

Pause or resume a running game.

```bash
wargames pause
wargames resume
```

## Crawling Commands

### crawl

Run vulnerability crawler to fetch CVEs.

```bash
wargames crawl [--sources SOURCES]
```

**Arguments:**
- `--sources`: Comma-separated sources (default: `nvd,exploitdb`)

## Analysis Commands

### report

View a round report.

```bash
wargames report ROUND_NUMBER
```

### ladder

Show model ELO leaderboard.

```bash
wargames ladder
```

### export

Export season results.

```bash
wargames export [--format FORMAT] [--output OUTPUT]
```

**Arguments:**
- `--format`: Output format: `markdown` or `json` (default: `markdown`)
- `--output`: Output file path (default: stdout)

## Tournament Commands

### tournament

Run a Swiss-system tournament.

```bash
wargames tournament --roster ROSTER
```

### sandbox

Run a single-round sandbox test.

```bash
wargames sandbox [--config CONFIG] [--loadout LOADOUT]
```

## CrewAI Commands

### crew

Run CrewAI manager crew.

```bash
wargames crew --task TASK [--inputs JSON]
```

**Arguments:**
- `--task`: Task name (e.g., `run_season`, `update_cves`, `analyze_strategies`, `hunt_bugs`)
- `--inputs`: JSON string of input parameters

**Available Tasks:**
- `run_season`: Run a complete season
- `update_cves`: Fetch latest CVEs
- `analyze_strategies`: Analyze game strategies
- `hunt_bugs`: Hunt for bugs
- `run_full_season_with_analysis`: Run season with analysis
