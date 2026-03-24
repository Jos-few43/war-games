# WARGAMES TESTS Package Knowledge Base

**Generated:** Tue Mar 24 2026
**Commit:** 0977a81
**Branch:** main

## OVERVIEW
Test suite mirroring the wargames package structure. Contains unit, integration, and functional tests for all components.

## STRUCTURE
```
tests/
├── engine/        # Tests for scoring, ELO, Swiss, worker, strategy
├── teams/         # Tests for red/blue team behaviors
├── llm/           # Tests for LLM providers and tool abstractions
├── crawler/       # Tests for CVE/NVD/ExploitDB scraping
├── output/        # Tests for database persistence layer
├── tui/           # Tests for Textual-based user interface
├── crew/          # Tests for maintenance crew manager
├── crewai/        # Tests for CrewAI task definitions (optional)
└── ...            # Supporting test modules
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Engine tests | `tests/engine/` | Tests for judge, elo, swiss, strategy, worker |
| Team tests | `tests/teams/` | Tests for red team attacks and blue team defenses |
| LLM tests | `tests/llm/` | Tests for Gemini provider and tool interfaces |
| Crawler tests | `tests/crawler/` | Tests for CVE and exploit data scraping |
| Output tests | `tests/output/` | Tests for database models and queries |
| TUI tests | `tests/tui/` | Tests for Textual dashboard and screens |
| Crew tests | `tests/crew/` | Tests for maintenance crew manager |
| CrewAI tests | `tests/crewai/` | Tests for CrewAI task definitions |
| Fixtures | `tests/fixtures/` | Shared test data and mocks (if any) |
| Conftest | `tests/conftest.py` | Pytest configuration and shared fixtures |

## CONVENTIONS
- **Test mirroring**: Package structure mirrors `wargames/` for direct correspondence
- **Async testing**: Uses `pytest.mark.asyncio` for async test functions
- **Test timeout**: 10s timeout via `pytest-timeout` plugin
- **Strict mode**: `asyncio_mode = "strict"` in pyproject.toml
- **Mocking**: Uses `unittest.mock` or `pytest-mock` for isolation
- **Assertions**: Prefers pytest assertions over unittest style
- **Fixtures**: Uses `@pytest.fixture` for reusable test setup
- **Markers**: Uses `@pytest.mark` for test categorization (if defined)

## ANTI-PATTERNS (THIS PACKAGE)
- **Empty `__init__.py`**: Some test subpackages have empty `__init__.py` (consider removing if not needed for package structure)
- **Direct file assertions**: Avoid asserting on exact file paths; use temporary directories
- **Hardcoded test data**: Consider using factories or fixtures for complex test data
- **Slow tests in suite**: Long-running tests should be marked appropriately (e.g., `@pytest.mark.slow`)
- **Missing teardown**: Ensure proper cleanup of resources (db connections, files, etc.)

## UNIQUE STYLES
- **Async-first**: Most tests are async due to engine's I/O-bound nature
- **Integration focus**: Tests often verify end-to-end flows (e.g., crawl → store → retrieve)
- **Snapshot testing**: May use snapshot assertions for complex outputs (JSON, reports)
- **Property-based testing**: Potential use of hypothesis for property-based tests (if adopted)
- **Test data isolation**: Uses temporary directories and unique identifiers to avoid conflicts

## COMMANDS
```bash
# Full test suite
pytest                                      # Runs all tests with 10s timeout
pytest -v                                   # Verbose output
pytest --tb=short                           # Short traceback format

# Subset testing
pytest tests/engine/                        # Engine-specific tests
pytest tests/teams/                         # Team behavior tests
pytest tests/crawler/                       # Crawler utility tests
pytest -k "test_scoring"                    # Scoring-related tests only
pytest -k "red" or -k "blue"                # Team-specific tests
pytest -m "not slow"                        # Exclude slow tests

# Coverage and reporting
pytest --cov=wargames --cov-report=html     # Generate HTML coverage report
pytest --cov-report=term-missing            # Show missing lines in terminal
pytest --durations=10                       # Show 10 slowest tests
```

## NOTES
- **Python version**: Requires 3.12+ (uses `list[str] | None` syntax in tests)
- **API keys**: Tests must use mocked LLM responses or test keys; never real keys
- **Test isolation**: Each test should clean up after itself (tmp files, db state)
- **CI/CD**: Configured to run in GitHub Actions or similar with timeout limits
- **Updating mirrors**: When adding new wargames subpackage, mirror it in tests/
- **Test data location**: Keep test data close to tests or in fixtures/ directory