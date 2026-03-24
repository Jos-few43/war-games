# War Games Chores

Immediate tasks to improve code quality, fix anti-patterns, and maintain the project.

## Anti-Patterns to Fix

### Project-wide
- [ ] Add `py.typed` marker for PEP 561 compliance (despite strict mypy)
- [ ] Remove `__pycache__` directories from source and add to `.gitignore`
- [ ] Consolidate duplicate crawlers: `wargames/crawler/cve.py` and `wargames/crawler/nvd.py`
- [ ] Evaluate and remove unrelated directory: `antigravity-bridge/` or integrate into main package

### wargames/ Package
- [ ] Fill or remove empty `__init__.py` in `wargames/engine/`
- [ ] Evaluate redundant packages: `wargames/crew/` and `wargames/crewai/` - consolidate or clarify purpose

### Tests/ Package
- [ ] Remove empty `__init__.py` files in test subpackages where not needed for package structure
- [ ] Replace direct file assertions with temporary directories
- [ ] Refactor hardcoded test data to use factories or fixtures
- [ ] Mark slow tests with `@pytest.mark.slow` and exclude from default runs
- [ ] Ensure proper teardown of resources (db connections, files) in all tests

### Code Quality
- [ ] Fix LSP error in `wargames/crawler/cve.py`: line 17, argument type mismatch (str vs int)
- [ ] Run `ruff check --fix` and `ruff format` to ensure linting compliance
- [ ] Run `mypy` to ensure type checking passes
- [ ] Ensure all TOML config files use environment variable references (never plaintext secrets)

## Maintenance Tasks

### Documentation
- [ ] Update `DEVELOPER_SETUP.md` with any new dependencies or setup steps
- [ ] Expand API documentation for engine modules in `docs/`
- [ ] Create contributor guide with setup instructions
- [ ] Update `README.md` with latest features and usage examples

### Testing
- [ ] Add property-based testing for core algorithms (ELO, strategy extraction)
- [ ] Implement fuzz testing for attack/defense generation
- [ ] Add chaos engineering tests for system resilience
- [ ] Increase test coverage for edge cases in judge and crawler modules

### Performance
- [ ] Profile and optimize database queries in `wargames/output/db.py`
- [ ] Implement caching for frequent LLM prompts in `wargames/llm/`
- [ ] Add connection pooling for HTTP clients in crawlers

### Dependency Management
- [ ] Regularly update dependencies to latest secure versions
- [ ] Audit for unused dependencies and remove them
- [ ] Check for security vulnerabilities in dependencies

## Good First Issues

These are suitable for new contributors:
- [ ] Fix the LSP error in `wargames/crawler/cve.py`
- [ ] Remove `__pycache__` directories and update `.gitignore`
- [ ] Add missing `py.typed` file
- [ ] Consolidate duplicate CVE crawler logic
- [ ] Fill empty `__init__.py` files with appropriate exports or remove them
- [ ] Update documentation strings for public functions and classes
- [ ] Add type hints to functions missing them
- [ ] Write unit tests for uncovered functions

## Definition of Done

A chore is complete when:
- [ ] The specific task is finished
- [ ] Tests pass (if applicable)
- [ ] Linting passes (`ruff check`)
- [ ] Type checking passes (`mypy`)
- [ ] Documentation is updated (if relevant)
- [ ] Changes are committed with a conventional commit message

---
*Last updated: Tue Mar 24 2026*