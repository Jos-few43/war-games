# Contributing to War Games

Thank you for your interest in contributing to War Games! This guide will help you get started with development, testing, and submitting contributions.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Commit Messages](#commit-messages)
- [Issue Types](#issue-types)

---

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md). Please read it before contributing.

---

## Getting Started

### Prerequisites

- Python 3.12+
- Git
- (Recommended) Distrobox container: `wargames-dev`

### Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/Jos-few43/war-games.git
cd war-games

# Enter the development container (recommended)
distrobox enter wargames-dev

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pip install pre-commit
pre-commit install
```

### Verify Installation

```bash
# Run tests
pytest

# Check version
wargames --version
```

---

## Development Workflow

### 1. Create a Branch

```bash
# Update your fork
git fetch origin
git checkout main
git pull origin main

# Create a new feature branch
git checkout -b feature/my-new-feature

# Or for bug fixes
git checkout -b fix/description-of-fix
```

### 2. Make Changes

```bash
# Make your code changes
# ... edit files ...

# Run tests to verify
pytest

# Run type checking
mypy wargames/

# Run linting
ruff check wargames/
```

### 3. Commit Changes

```bash
# Stage changes
git add .

# Commit with conventional commit format
git commit -m "feat(engine): add new strategy type"
```

### 4. Submit a Pull Request

```bash
# Push to your fork
git push origin feature/my-new-feature

# Create PR via GitHub CLI
gh pr create --title "feat(engine): add new strategy type" \
  --body "## Summary
- Added new strategy type for phase 2

## Test Plan
- [x] pytest passes
- [x] mypy type checking passes
- [x] Manual sandbox test"
```

---

## Coding Standards

### Language & Style

- **Python version**: 3.12+
- **Formatter**: Ruff (configured in `pyproject.toml`)
- **Type checker**: mypy with strict mode

### Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Modules | `snake_case` | `game_engine.py` |
| Classes | `PascalCase` | `GameEngine` |
| Functions | `snake_case` | `calculate_elo()` |
| Constants | `UPPER_SNAKE_CASE` | `DEFAULT_TIMEOUT` |
| Private methods | `_snake_case` | `_internal_method()` |

### Import Order (enforced by Ruff)

```python
# Standard library
import asyncio
from pathlib import Path

# Third-party packages
from textual.app import App
import pydantic

# Local imports (relative)
from wargames import models
from wargames.engine import game
```

### Type Hints

Always use type hints for function signatures:

```python
# Good
def calculate_elo(rating: int, opponent_rating: int, k: int, score: float) -> int:
    """Calculate new ELO rating after a match."""
    ...

# Avoid
def calculate_elo(rating, opponent_rating, k, score):
    ...
```

### Docstrings

Use Google-style docstrings for public APIs:

```python
def calculate_elo(rating: int, opponent_rating: int, k: int, score: float) -> int:
    """Calculate new ELO rating after a match.

    Args:
        rating: Current ELO rating.
        opponent_rating: Opponent's ELO rating.
        k: K-factor for the calculation.
        score: Match result (1.0 for win, 0.5 for draw, 0.0 for loss).

    Returns:
        New ELO rating after the match.

    Raises:
        ValueError: If score is not in [0.0, 1.0].
    """
    ...
```

### Error Handling

- Use try/except blocks for operations that can fail
- Never silently catch exceptions
- Log errors with appropriate context
- Raise specific exceptions rather than generic ones

```python
# Good
try:
    result = await client.chat_completion(messages)
except httpx.TimeoutException as e:
    logger.error(f"Request timed out after {timeout}s: {e}")
    raise TimeoutError(f"LLM request timed out after {timeout}s") from e

# Avoid
try:
    result = await client.chat_completion(messages)
except:
    pass  # Never do this
```

---

## Testing

### Test Requirements

- All new features must include tests
- Bug fixes must include regression tests
- Maintain >80% code coverage in engine modules

### Running Tests

```bash
# Run all tests
pytest

# Run specific module
pytest tests/engine/

# Run with coverage
pytest --cov=wargames --cov-report=term-missing

# Run in watch mode
pytest --watch
```

### Test File Structure

Tests should mirror the source structure:

```
wargames/
  engine/
    game.py
    round.py
    elo.py

tests/
  engine/
    test_game.py
    test_round.py
    test_elo.py
```

### Test Naming

```python
def test_calculate_elo_win():
    """Test ELO calculation for a win."""
    ...

def test_calculate_elo_draw():
    """Test ELO calculation for a draw."""
    ...

def test_phase_advance_threshold():
    """Test phase advancement when average score exceeds threshold."""
    ...
```

### Async Tests

Use `pytest-asyncio` with strict mode:

```python
import pytest

@pytest.mark.asyncio
async def test_game_engine_run():
    """Test the game engine season loop."""
    engine = GameEngine(config)
    results = [result async for result in engine.run()]
    assert len(results) == config.game.rounds
```

---

## Pull Request Process

### Before Submitting

1. **Run all tests**: `pytest`
2. **Run type checking**: `mypy wargames/`
3. **Run linter**: `ruff check wargames/`
4. **Update documentation** if needed
5. **Check your branch is up to date** with main

### PR Template

```markdown
## Summary
<!-- Brief description of changes -->

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update
- [ ] Refactoring

## Test Plan
<!-- How did you test your changes? -->
- [ ] Unit tests added/updated
- [ ] Manual testing performed
- [ ] Integration tests pass

## Checklist
- [ ] Code follows style guidelines
- [ ] Type hints added
- [ ] Documentation updated
- [ ] Tests pass
- [ ] No new mypy/ruff errors
```

### Review Process

1. **Automated checks** run (CI pipeline)
2. **Maintainer review** within 48 hours
3. **Address feedback** if requested
4. **Merge** after approval

---

## Commit Messages

We use [Conventional Commits](https://www.conventionalcommits.org/) for clear changelog generation.

### Format

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Types

| Type | Description |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation changes |
| `style` | Code style (formatting, no logic change) |
| `refactor` | Code refactoring |
| `perf` | Performance improvement |
| `test` | Test updates |
| `chore` | Maintenance, tooling |

### Examples

```bash
# Feature
git commit -m "feat(engine): add Swiss tournament mode"

# Bug fix
git commit -m "fix(elo): calculate correct K-factor for new players"

# Documentation
git commit -m "docs(readme): add architecture diagram"

# Refactoring
git commit -m "refactor(teams): extract common agent logic"
```

---

## Issue Types

### Bug Reports

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md):

- **Expected behavior**: What should happen
- **Actual behavior**: What actually happened
- **Steps to reproduce**: How to trigger the issue
- **Environment**: Python version, OS, dependencies
- **Logs**: Relevant error output

### Feature Requests

Use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md):

- **Problem**: What problem does this solve?
- **Proposed solution**: How should it work?
- **Alternatives considered**: What else was tried?
- **Urgency**: How important is this?

### Questions

For general questions, use [GitHub Discussions](https://github.com/Jos-few43/war-games/discussions) instead of issues.

---

## Resources

- [CLAUDE.md](CLAUDE.md) - Detailed architecture reference
- [Wiki](https://github.com/Jos-few43/war-games/wiki) - Additional documentation
- [Discord](https://discord.gg/wargames) - Community discussion

---

## Getting Help

- **Slack**: #war-games-dev on [AI Coding Community](https://discord.gg/ai-coding)
- **GitHub Issues**: For bugs and feature requests
- **Discussions**: For questions and ideas

---

Thank you for contributing to War Games!