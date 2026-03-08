import pytest
from pathlib import Path
from wargames.output.vault import VaultWriter
from wargames.models import (
    RoundResult, Phase, MatchOutcome, Severity, Domain,
    AttackResult, DefenseResult, DraftPick, BugReport, Patch,
)


@pytest.fixture
def vault_dir(tmp_path):
    return tmp_path / "WarGames"


@pytest.fixture
def writer(vault_dir):
    return VaultWriter(vault_dir)


@pytest.fixture
def sample_round():
    return RoundResult(
        round_number=1, phase=Phase.PROMPT_INJECTION,
        outcome=MatchOutcome.RED_WIN, red_score=12, blue_threshold=10,
        red_draft=[DraftPick(round=1, team="red", resource_name="fuzzer", resource_category="offensive")],
        blue_draft=[DraftPick(round=1, team="blue", resource_name="waf_rules", resource_category="defensive")],
        attacks=[AttackResult(turn=1, description="SQLi on /users", severity=Severity.HIGH, points=5, success=True)],
        defenses=[DefenseResult(turn=2, description="WAF blocked", blocked=True, points_deducted=2)],
        red_debrief="# Red Debrief\nSQLi worked.",
        blue_debrief="# Blue Debrief\nNeed better input validation.",
    )


def test_write_round_creates_files(writer, sample_round):
    writer.write_round(sample_round)
    assert (writer.base_path / "rounds" / "round-001.md").exists()
    assert (writer.base_path / "debriefs" / "R001-red-debrief.md").exists()
    assert (writer.base_path / "debriefs" / "R001-blue-debrief.md").exists()


def test_round_file_has_frontmatter(writer, sample_round):
    writer.write_round(sample_round)
    content = (writer.base_path / "rounds" / "round-001.md").read_text()
    assert "---" in content
    assert "round: 1" in content
    assert "phase: prompt-injection" in content
    assert "outcome: red_win" in content


def test_write_bug_report(writer):
    report = BugReport(
        round_number=1, title="SQLi on users endpoint",
        severity=Severity.HIGH, domain=Domain.CODE_VULN,
        target="/api/users", steps_to_reproduce="1. Send payload",
        proof_of_concept="' OR 1=1--", impact="Data exfiltration",
    )
    writer.write_bug_report(report)
    path = writer.base_path / "bug-reports" / "R001-sqli-on-users-endpoint.md"
    assert path.exists()
    content = path.read_text()
    assert "severity: high" in content
    assert "Proof of Concept" in content


def test_write_patch(writer):
    p = Patch(
        round_number=1, title="Parameterized queries fix",
        fixes="R001-sqli-on-users-endpoint",
        strategy="Replace string concatenation with parameterized queries",
        changes="Updated all db calls", verification="Run SQLi payload, verify blocked",
    )
    writer.write_patch(p)
    path = writer.base_path / "patches" / "R001-parameterized-queries-fix.md"
    assert path.exists()


def test_append_knowledge(writer):
    writer.append_knowledge("attack-patterns", "## Round 1\n- SQLi works on unvalidated inputs")
    path = writer.base_path / "knowledge" / "attack-patterns.md"
    assert path.exists()
    assert "SQLi works" in path.read_text()
    writer.append_knowledge("attack-patterns", "## Round 2\n- Try SSRF next")
    content = path.read_text()
    assert "Round 1" in content
    assert "Round 2" in content


def test_write_strategy_update(writer):
    from wargames.models import Strategy
    strategies = [
        Strategy(team="red", phase=1, strategy_type="attack",
                 content="Use union-based SQLi", win_rate=0.8,
                 usage_count=3, created_round=1),
    ]
    writer.write_strategy_update(round_number=1, phase_name="prompt-injection", strategies=strategies)
    path = writer.base_path / "strategies" / "phase-prompt-injection.md"
    assert path.exists()
    content = path.read_text()
    assert "union-based SQLi" in content
    assert "Round 1" in content
    assert "80%" in content


def test_write_strategy_update_appends(writer):
    from wargames.models import Strategy
    s1 = Strategy(team="red", phase=1, strategy_type="attack", content="First tactic",
                  win_rate=0.5, usage_count=1, created_round=1)
    s2 = Strategy(team="blue", phase=1, strategy_type="defense", content="Second tactic",
                  win_rate=0.9, usage_count=5, created_round=2)
    writer.write_strategy_update(1, "prompt-injection", [s1])
    writer.write_strategy_update(2, "prompt-injection", [s2])
    content = (writer.base_path / "strategies" / "phase-prompt-injection.md").read_text()
    assert "Round 1" in content
    assert "Round 2" in content
    assert "First tactic" in content
    assert "Second tactic" in content
