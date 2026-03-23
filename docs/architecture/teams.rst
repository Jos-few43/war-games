# Teams & Agents

Documentation for team agents and loadouts.

## Red Team Agent (`wargames/teams/red.py`)

The red team generates attacks across phases:

- **Phase 1**: Prompt injection attempts
- **Phase 2**: Code vulnerability exploitation
- **Phase 3**: Real CVE exploitation (from NVD/ExploitDB)
- **Phase 4**: Open-ended attacks

### Attack Types

- Prompt injection (role reversal, ignored instructions)
- Code injection (SQLi, XSS, command injection)
- Denial of service
- Privilege escalation

## Blue Team Agent (`wargames/teams/blue.py`)

The blue team generates defenses:

- Input validation and sanitization
- Output filtering
- Sandbox execution
- Rate limiting

## Loadout System

Loadouts define resource allocation:

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

### Built-in Loadouts

| Loadout | Red Strategy | Blue Strategy |
|---------|-------------|---------------|
| `default` | Balanced | Balanced |
| `aggressive` | High attack focus | Moderate defense |
| `defensive` | Moderate attack | High defense |
| `experimental` | Random mix | Adaptive |
