# Security Policy

## Reporting Security Vulnerabilities

We take security vulnerabilities seriously. If you discover a security issue, please report it responsibly.

### Reporting Process

1. **DO NOT** create a public GitHub issue for security vulnerabilities
2. Email security findings privately or use GitHub's private vulnerability reporting
3. Include as much detail as possible:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Any suggested fixes (optional)

### Scope

The War Games framework handles:
- LLM API calls (keys passed via environment variables)
- CVE data from NVD/ExploitDB
- Local database storage

### Security Principles

- API keys are never stored in code or config files (use env var refs)
- Database operations use parameterized queries
- CVE data is validated before use
- LLM outputs are not executed directly

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Disclosure Policy

- Initial response within 48 hours
- Regular updates on progress
- Public disclosure after fix release
