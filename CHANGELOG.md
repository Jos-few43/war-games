# Changelog

All notable changes to War Games will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Sphinx documentation system with Furo theme
- API documentation for engine modules
- Developer setup guide (`docs/DEVELOPER_SETUP.md`)
- Security policy (`SECURITY.md`)
- Dependabot configuration (`.github/dependabot.yml`)
- Documentation build in CI pipeline
- Release workflow for PyPI publishing
- Benchmark tests for performance testing
- Coverage configuration in `pyproject.toml`

### Changed
- Enhanced CI pipeline with separate jobs
- Updated `pyproject.toml` with docs dependencies

### Fixed
- Documentation structure now follows Sphinx best practices

## [0.1.0] - 2024-03-22

### Added
- Initial release
- Red team / blue team LLM competition framework
- Multi-phase progression (prompt injection → code vulns → CVEs → open-ended)
- Evolutionary learning through strategy extraction
- Swiss tournament mode with ELO ratings
- Live TUI dashboard
- CVE integration (NVD, ExploitDB)
- OpenClaw Vault export
- CrewAI integration for automated management
- GitHub Actions CI workflow
- Issue templates (bug report, feature request)
- CONTRIBUTING.md guidelines
- Comprehensive README with architecture diagrams
