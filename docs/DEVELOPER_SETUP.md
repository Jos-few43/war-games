# Developer Setup Guide

This guide covers setting up a complete development environment for War Games, including IDE integration, debugging, and advanced tooling.

## Container Setup

### Recommended: Distrobox

```bash
# Create the development container
distrobox create --name wargames-dev --image fedora:43

# Enter the container
distrobox enter wargames-dev

# Install system dependencies
sudo dnf install -y python3.12 python3.12-pip git vim

# Set up Python 3.12 as default
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1
```

### Quick Access

```bash
# Using the container router (if configured)
ctr wargames
```

## Python Environment

### Virtual Environment (Alternative to Distrobox)

```bash
# Create virtual environment
python3 -m venv venv

# Activate
source venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Install additional dev tools
pip install pytest-watch pytest-cov mypy ruff
```

### Dependency Management

```bash
# Install production dependencies
pip install -e .

# Install with all dev dependencies
pip install -e ".[dev]"

# Install specific extras
pip install -e ".[test]"    # Testing only
pip install -e ".[lint]"    # Linting only
```

## IDE Setup

### VS Code

Create `.vscode/settings.json`:

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
  "python.analysis.typeCheckingMode": "strict",
  "python.analysis.autoImportCompletions": true,
  "ruff.lint.args": ["--config=${workspaceFolder}/pyproject.toml"],
  "ruff.format.args": ["--config=${workspaceFolder}/pyproject.toml"],
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.fixAll": "explicit",
    "source.organizeImports": "explicit"
  },
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.tabSize": 4
  },
  "files.exclude": {
    "**/__pycache__": true,
    "**/*.pyc": true,
    "**/.pytest_cache": true,
    "**/state.db": true
  }
}
```

### PyCharm

1. **Project Structure**: Mark `wargames/` as Sources
2. **Python Version**: Set to Python 3.12
3. **Interpreter**: Use virtual environment or container
4. **Formatter**: Enable Ruff plugin
5. **Type Checking**: Enable mypy plugin

### Neovim

```lua
-- lua/config/init.lua
require("config.lsp").setup()

-- lua/config/lsp.lua
local lsp = require("lspconfig")

lsp.ruff.setup({
  init_options = {
    settings = {
      ruff = {
        args = { "--config=${workspaceFolder}/pyproject.toml" },
      },
    },
  },
})

lsp.mypy.setup({
  settings = {
    mypy = {
      python_version = "3.12",
      strict = true,
    },
  },
})
```

## Debugging

### VS Code Debug Configuration

Create `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Debug: Sandbox",
      "type": "python",
      "request": "launch",
      "module": "wargames",
      "args": ["sandbox", "--config", "config/default.toml"],
      "console": "integratedTerminal"
    },
    {
      "name": "Debug: Tests",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": ["tests/", "-v", "-k", "test_elo"],
      "console": "integratedTerminal"
    }
  ]
}
```

### Python Debugging

```bash
# Using PDB
python -m pdb -m wargames sandbox --config config/default.toml

# Using debugpy (for VS Code remote debug)
python -m debugpy --listen 0.0.0.0:5678 -m wargames start --config config/default.toml

# Breakpoint in code
import debugpy
debugpy.breakpoint()
```

### Logging

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("wargames.engine")
logger.debug("Starting round %d", round_num)
```

Environment variable for verbose logging:

```bash
export WARGAMES_DEBUG=1
wargames start --config config/default.toml
```

## Testing

### Run Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=wargames --cov-report=term-missing

# Specific module
pytest tests/engine/

# With verbose output
pytest -v -s

# Watch mode (reruns on changes)
pytest --watch

# Stop on first failure
pytest -x
```

### Write Tests

```python
# tests/engine/test_elo.py
import pytest

@pytest.mark.asyncio
async def test_calculate_elo_win():
    """Test ELO calculation for a win."""
    from wargames.engine.elo import calculate_elo
    
    new_rating = calculate_elo(
        rating=1500,
        opponent_rating=1500,
        k=32,
        score=1.0
    )
    
    assert new_rating == 1516

@pytest.mark.asyncio
async def test_elo_different_ratings():
    """Test ELO when ratings differ significantly."""
    new_rating = calculate_elo(
        rating=1600,
        opponent_rating=1400,
        k=32,
        score=0.5  # Draw
    )
    
    # Expected: small change due to rating difference
    assert 1598 <= new_rating <= 1602
```

### Fixtures

```python
# conftest.py
import pytest
from wargames.config import load_config

@pytest.fixture
def test_config():
    """Load test configuration."""
    return load_config("config/test-local.toml")

@pytest.fixture
def sample_strategy():
    """Create a sample strategy for testing."""
    from wargames.models import Strategy
    return Strategy(
        name="test_strategy",
        phase="PROMPT_INJECTION",
        team="red",
        content="Test attack content",
        win_rate=0.65,
        usage_count=10,
    )
```

## Type Checking

### mypy Configuration

```toml
# pyproject.toml additions
[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
check_untyped_defs = true
disallow_incomplete_defs = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true

[[tool.mypy.overrides]]
module = "tests.*"
ignore_errors = true
```

### Run Type Checking

```bash
# Full type check
mypy wargames/

# With verbose output
mypy wargames/ -v

#特定模块
mypy wargames/engine/

#快速检查（跳过导入）
mypy wargames/ --ignore-missing-imports
```

## Linting

### Ruff Configuration

```toml
# pyproject.toml additions
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "N",   # pep8-naming
    "UP",  # pyupgrade
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "FA",  # flake8-future-annotations
]
ignore = [
    "E501",  # line too long (handled by formatter)
    "B008",  # do not perform function call in argument defaults
]

[tool.ruff.format]
quote-style = "single"
indent-style = "space"
```

### Run Linting

```bash
# Check and fix
ruff check wargames/ --fix

# Format code
ruff format wargames/

# Check specific files
ruff check wargames/engine/game.py
```

## Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        args: [--config-file=pyproject.toml]
        additional_dependencies:
          - types-all

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
```

Install and run:

```bash
pip install pre-commit
pre-commit install

# Run manually
pre-commit run --all-files
```

## Database Management

### View Database

```bash
# Using sqlite3
sqlite3 ~/.local/share/wargames/state.db

# List tables
sqlite3 ~/.local/share/wargames/state.db ".tables"

# Query rounds
sqlite3 ~/.local/share/wargames/state.db "SELECT * FROM rounds LIMIT 5;"

# View ELO ratings
sqlite3 ~/.local/share/wargames/state.db "SELECT * FROM model_ratings;"
```

### Backup/Restore

```bash
# Backup
cp ~/.local/share/wargames/state.db backup-$(date +%Y%m%d).db

# Restore
cp backup-20240315.db ~/.local/share/wargames/state.db
```

### Clear State

```bash
# Remove database and start fresh
rm ~/.local/share/wargames/state.db

# Also remove PID file if stale
rm ~/.local/share/wargames/wargames.pid
```

## Common Development Tasks

### Add a New Engine Module

```bash
# Create module structure
touch wargames/engine/new_module.py
touch tests/engine/test_new_module.py

# Add to __init__.py
# wargames/engine/__init__.py
from wargames.engine.new_module import NewClass
```

### Add a New CLI Command

```bash
# Edit cli.py
# Add new function with @click.command() decorator
@click.command()
@click.option("--option", help="Description")
def new_command(option):
    """New command description."""
    pass
```

### Update Configuration

```bash
# Add new config section
# config/default.toml
[new_section]
option = "value"
```

## Troubleshooting

### Import Errors

```bash
# Reinstall in editable mode
pip install -e .

# Check Python path
python -c "import wargames; print(wargames.__file__)"
```

### Test Failures

```bash
# Clear cache
rm -rf .pytest_cache __pycache__ wargames/__pycache__

# Run with more info
pytest -vv --tb=long
```

### Database Locked

```bash
# Check for running process
ps aux | grep wargames

# Remove lock file
rm ~/.local/share/wargames/wargames.lock
```