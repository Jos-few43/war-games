# War Games

<p align="center">
  <img src="docs/images/wargames-banner.png" alt="War Games Banner" width="600">
</p>

<p align="center">
  <a href="https://pypi.org/project/wargames/">
    <img src="https://img.shields.io/pypi/v/wargames?color=blue&label=PyPI" alt="PyPI Version">
  </a>
  <a href="https://github.com/Jos-few43/war-games/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/Jos-few43/war-games?color=green" alt="License">
  </a>
  <a href="https://github.com/Jos-few43/war-games/actions">
    <img src="https://img.shields.io/github/actions/status/Jos-few43/war-games/main?label=CI" alt="CI Status">
  </a>
  <a href="https://github.com/Jos-few43/war-games/releases">
    <img src="https://img.shields.io/github/v/release/Jos-few43/war-games?color=orange&label=Latest" alt="Latest Release">
  </a>
</p>

## Overview

**War Games** is a red team / blue team LLM competition framework with evolutionary learning. Two AI agents compete across structured phases—the red team launches attacks (prompt injection, code vulnerabilities, real CVEs, open-ended exploits) while the blue team defends. A third LLM acts as judge, scoring each round and extracting reusable strategies that improve future performance.

### Key Features

- **Multi-Phase Competition**: Progress through prompt injection → code vulnerabilities → real CVEs → open-ended attacks
- **Evolutionary Learning**: Strategies are extracted, stored, and refined based on win rates
- **Swiss Tournament Mode**: Rank multiple models against each other with ELO ratings
- **Live TUI Dashboard**: Watch matches in real-time with a terminal interface
- **CVE Integration**: Automatic fetching from NVD, ExploitDB, and GitHub Advisories
- **OpenClaw Vault Export**: Persist results to your personal knowledge base

### Use Cases

- Evaluate LLM security robustness across different attack vectors
- Benchmark models against each other in structured competitions
- Generate training data for security-focused fine-tuning
- Research adversarial AI behavior in controlled environments

---

## Quick Start

### Prerequisites

- Python 3.12+
- [LiteLLM](https://docs.litellm.ai/) proxy (or any OpenAI-compatible API)
- (Recommended) [Distrobox](https://distrobox.privatedns.org/) container environment

### Installation

```bash
# Clone the repository
git clone https://github.com/Jos-few43/war-games.git
cd war-games

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Verify installation
wargames --version
```

### Run Your First Season

```bash
# Start a new season (runs in foreground)
wargames start --config config/default.toml

# Or run in background with nohup/tmux
nohup wargames start --config config/default.toml > season.log 2>&1 &

# Attach to the live TUI dashboard
wargames attach
```

### Quick Sandbox Test

```bash
# Run a single round without persistent state
wargames sandbox --config config/default.toml
```

---

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              War Games Framework                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐     ┌──────────────────┐     ┌──────────────────────┐  │
│  │   CLI Input   │────▶│   Game Engine    │────▶│   Results Output     │  │
│  │  (Commands)   │     │  (Orchestrator)  │     │  (DB / Vault / TUI)  │  │
│  └──────────────┘     └──────────────────┘     └──────────────────────┘  │
│         │                      │                        ▲                  │
│         │                      ▼                        │                  │
│         │              ┌──────────────────┐            │                  │
│         │              │   Round Engine   │────────────┘                  │
│         │              │   (per-round)     │                               │
│         │              └──────────────────┘                               │
│         │                      │                                            │
│         ▼                      ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                        Season Loop                                   │  │
│  │  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐          │  │
│  │  │ Draft   │───▶│ Combat  │───▶│ Debrief │───▶│ Strategy│          │  │
│  │  │ Phase   │    │ Phase   │    │ Phase   │    │ Extract │          │  │
│  │  └─────────┘    └─────────┘    └─────────┘    └─────────┘          │  │
│  │       │              │              │              │                  │  │
│  │       │              ▼              │              ▼                  │  │
│  │       │        ┌───────────┐       │        ┌───────────┐          │  │
│  │       │        │   Judge   │       │        │  ELO      │          │  │
│  │       │        │  (LLM)    │       │        │  Update   │          │  │
│  │       │        └───────────┘       │        └───────────┘          │  │
│  │       │              │              │              │                  │  │
│  │       │              ▼              │              ▼                  │  │
│  │       │        ┌─────────────────────────────────────────────┐     │  │
│  │       │        │              Agent Teams                      │     │  │
│  │       │        │  ┌─────────────┐       ┌─────────────┐       │     │  │
│  │       │        │  │  Red Team  │       │  Blue Team  │       │     │  │
│  │       │        │  │  (Attack)  │       │  (Defense)  │       │     │  │
│  │       │        │  └─────────────┘       └─────────────┘       │     │  │
│  │       │        └─────────────────────────────────────────────┘     │  │
│  │       │                                                       │     │  │
│  └───────┴───────────────────────────────────────────────────────┴─────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Game Loop Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Season Execution Flow                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Start Season                                                              │
│       │                                                                    │
│       ▼                                                                    │
│   ┌─────────────────────────────────────────────────────────────────┐     │
│   │  For Each Round (1 → N):                                        │     │
│   │                                                                   │     │
│   │  ┌─────────────┐                                                 │     │
│   │  │ 1. DRAFT    │  Assign loadout resources to each team        │     │
│   │  │   Phase     │  (snake or linear draft style)                │     │
│   │  └─────────────┘                                                 │     │
│   │        │                                                         │     │
│   │        ▼                                                         │     │
│   │  ┌───────────────────────────────────────────────────────────┐   │     │
│   │  │ 2. COMBAT PHASE (repeat for turn_limit):                  │   │     │
│   │  │                                                            │   │     │
│   │  │    Red Team ──▶ Generate Attack ──▶ Blue Team           │   │     │
│   │  │        │                              │                  │   │     │
│   │  │        │                              ▼                  │   │     │
│   │  │        │                    Generate Defense            │   │     │
│   │  │        │                              │                  │   │     │
│   │  │        │                              ▼                  │   │     │
│   │  │        │                    Judge ──▶ Score              │   │     │
│   │  │        │                              │                  │   │     │
│   │  └───────────────────────────────────────────────────────────┘   │     │
│   │        │                                                         │     │
│   │        ▼                                                         │     │
│   │  ┌─────────────┐                                                 │     │
│   │  │ 3. DEBRIEF  │  Each team reflects on the round outcome      │     │
│   │  │   Phase     │                                                 │     │
│   │  └─────────────┘                                                 │     │
│   │        │                                                         │     │
│   │        ▼                                                         │     │
│   │  ┌─────────────┐                                                 │     │
│   │  │ 4. STRATEGY │  Judge extracts reusable strategies           │     │
│   │  │  Extract    │  Win rates updated; low-rate pruned           │     │
│   │  └─────────────┘                                                 │     │
│   │        │                                                         │     │
│   │        ▼                                                         │     │
│   │  ┌─────────────┐                                                 │     │
│   │  │ 5. ELO      │  Model ratings adjusted based on outcome      │     │
│   │  │  Update     │                                                 │     │
│   │  └─────────────┘                                                 │     │
│   │        │                                                         │     │
│   │        ▼                                                         │     │
│   │  ┌─────────────┐                                                 │     │
│   │  │ 6. PHASE    │  Check if threshold met to advance phase      │     │
│   │  │  Check      │                                                 │     │
│   │  └─────────────┘                                                 │     │
│   │                                                                   │     │
│   └─────────────────────────────────────────────────────────────────┘     │
│       │                                                                    │
│       ▼                                                                    │
│   End Season                                                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Phase Progression

| Phase | Domain | Description |
|-------|--------|-------------|
| 1 | **PROMPT_INJECTION** | Prompt injection attacks, jailbreaks, role manipulation |
| 2 | **CODE_VULNS** | Code vulnerability exploitation, SQL injection, XSS |
| 3 | **REAL_CVES** | Real CVEs from NVD/ExploitDB/GHSA |
| 4 | **OPEN_ENDED** | Unconstrained red team attacks |

Phases advance automatically when the average score over `min_rounds` consecutive rounds exceeds `phase_advance.min_avg_score`.

---

## Configuration

### Configuration File Structure

```toml
[game]
name = "season-01"           # Season identifier
rounds = 50                  # Total rounds per season
turn_limit = 12              # Max turns per round
score_threshold = 10         # Points before blue loses
phase_advance_score = 7.5    # Avg score needed to advance phase

[draft]
picks_per_team = 5           # Loadout items per team
style = "snake"              # "snake" or "linear"

[teams.red]
name = "Red Team"            # Display name
model = "http://localhost:4000/v1"  # LLM endpoint
model_name = "qwen3-8b"       # Model identifier
temperature = 0.8            # Sampling temperature
timeout = 30.0               # Request timeout (seconds)

[teams.blue]
name = "Blue Team"
model = "http://localhost:4000/v1"
model_name = "llama3.2-3b"
temperature = 0.4
timeout = 30.0

[teams.judge]
name = "Judge"
model = "http://localhost:4002/v1"
model_name = "claude-sonnet-4-5"
temperature = 0.2
timeout = 90.0

[crawler]
enabled = true
sources = ["nvd", "exploitdb", "ghsa"]
refresh_interval = "24h"

[output.vault]
enabled = true
path = "~/OpenClaw-Vault/WarGames"

[output.database]
path = "~/.local/share/wargames/state.db"

[scoring]
profile = "balanced"
```

### Environment Variable Resolution

Use `$VAR_NAME` syntax for sensitive values (never hardcode API keys):

```toml
[teams.red]
model = "http://localhost:4000/v1"
model_name = "qwen3-8b"
# Use env vars instead of hardcoding keys
api_key = "$LITELLM_MASTER_KEY"
```

### Loadout Presets

Named loadout presets define team capabilities:

| Loadout | Red Focus | Blue Focus |
|---------|-----------|------------|
| `aggressive` | High attack power | Minimal defense |
| `defensive` | Test defenses | Heavy defense |
| `balanced` | Mix | Mix |
| `stealth` | Hidden payloads | Detection-focused |

---

## Commands Reference

### Core Commands

| Command | Description |
|---------|-------------|
| `wargames start --config <path>` | Start a new season |
| `wargames attach` | Attach to running TUI dashboard |
| `wargames status` | Check current season status |
| `wargames pause` | Pause running season |
| `wargames resume` | Resume paused season |

### Testing & Development

| Command | Description |
|---------|-------------|
| `wargames sandbox --config <path>` | Run single-round sandbox |
| `wargames sandbox --loadout red=aggressive,blue=defensive` | Test specific loadouts |

### Tournament Mode

| Command | Description |
|---------|-------------|
| `wargames tournament --roster <path>` | Run Swiss-system tournament |

### Data & Reporting

| Command | Description |
|---------|-------------|
| `wargames report <round>` | View round details |
| `wargames ladder` | View ELO ratings |
| `wargames stats` | View overall statistics |
| `wargames export --format markdown` | Export results |
| `wargames export --format json --output results.json` | Export to JSON |

### Utilities

| Command | Description |
|---------|-------------|
| `wargames crawl --sources nvd,exploitdb` | Fetch latest CVEs |
| `wargames --version` | Show version |
| `wargames --help` | Show help |

---

## Examples

### Running a Local Season

```bash
# Start with default configuration
wargames start --config config/default.toml

# In another terminal, attach to watch live
wargames attach
```

### Tournament Across Multiple Models

```bash
# Create a roster file (see config/roster-example.toml)
# Run the tournament
wargames tournament --roster config/roster-cloud.toml
```

### Sandbox Testing

```bash
# Quick test with default settings
wargames sandbox --config config/test-local.toml

# Test specific loadout combinations
wargames sandbox --config config/default.toml --loadout red=aggressive,blue=defensive

# Use cloud models
wargames sandbox --config config/full-cloud.toml
```

---

## Troubleshooting

### Common Issues

#### "No module named 'wargames'"

```bash
# Ensure you're in the right environment
pip install -e .

# Or activate your virtual environment
source venv/bin/activate
```

#### "Connection refused" to LiteLLM

```bash
# Check if LiteLLM is running
curl http://localhost:4000/health

# Start LiteLLM if needed
litellm --config path/to/config.yaml
```

#### "Database locked" errors

```bash
# Ensure no other season is running
wargames status

# Or delete stale lock file
rm ~/.local/share/wargames/wargames.lock
```

#### TUI not updating

```bash
# Check the bridge is connected
wargames attach

# Verify worker is running
ps aux | grep wargames
```

### Debug Mode

Enable verbose logging:

```bash
# Set debug environment variable
export WARGAMES_DEBUG=1
wargames start --config config/default.toml
```

### Getting Help

- **Issues**: [GitHub Issues](https://github.com/Jos-few43/war-games/issues)
- **Discussions**: [GitHub Discussions](https://github.com/Jos-few43/war-games/discussions)
- **Documentation**: [Wiki](https://github.com/Jos-few43/war-games/wiki)

---

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run specific test directory
pytest tests/engine/

# Run tests matching pattern
pytest -k "test_scoring"

# With coverage
pytest --cov=wargames --cov-report=term-missing
```

### Code Quality

```bash
# Type checking
mypy wargames/

# Linting
ruff check wargames/

# Format code
ruff format wargames/
```

### Pre-commit Hooks

```bash
# Install pre-commit hooks
pip install pre-commit
pre-commit install
```

---

## Roadmap

### v1.x Series

- [ ] **v1.1**: Enhanced strategy extraction with semantic similarity matching
- [ ] **v1.2**: WebUI dashboard (TUI → web-based)
- [ ] **v1.3**: Multi-agent team composition (multiple red/blue agents per team)
- [ ] **v1.4**: Custom scenario designer (define your own attack/defense rules)
- [ ] **v1.5**: Real-time streaming responses in TUI

### Future Features

- [ ] **v2.0**: CrewAI integration for autonomous task execution
- [ ] **v2.1**: Reinforcement learning from human feedback (RLHF) for strategy evolution
- [ ] **v2.2**: Plugin system for custom judges/agents
- [ ] **v2.3**: Distributed season execution across multiple machines

### CrewAI Integration (Phase 1)

The initial CrewAI integration will focus on **basic maintenance tasks**:

```python
# Example: CrewAI task definition for War Games
wargames_crew_tasks = [
    {
        "name": "fix_test_failure",
        "description": "Auto-fix failing tests by analyzing error and applying corrections",
        "agent_type": "maintenance",
        "tools": ["read", "edit", "bash"],
    },
    {
        "name": "lint_fixes",
        "description": "Fix lint errors and apply code style corrections",
        "agent_type": "maintenance",
        "tools": ["read", "edit"],
    },
    {
        "name": "update_docs",
        "description": "Update documentation for changed code",
        "agent_type": "documentation",
        "tools": ["read", "write"],
    },
]
```

---

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Quick Contribution Flow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make changes and test: `pytest`
4. Commit with conventional commits: `git commit -m "feat(engine): add new strategy type"`
5. Push and create PR

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Related Projects

- [LiteLLM](https://github.com/BerriAI/litellm) - Unified LLM proxy
- [OpenClaw](https://github.com/Jos-few43/OpenClaw-Vault) - AI agent system
- [OpenCode Manager](https://github.com/Jos-few43/opencode-manager) - AI coding assistant management