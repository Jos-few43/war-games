import pytest
import json
from unittest.mock import AsyncMock
from wargames.engine.judge import Judge, ATTACK_SYSTEM_PROMPT
from wargames.models import Severity, AttackResult, BugReport, Patch, Domain


@pytest.mark.asyncio
async def test_judge_evaluates_attack():
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = json.dumps({
        "valid": True,
        "severity": "high",
        "points": 5,
        "auto_win": False,
        "reasoning": "SQL injection successfully extracted data",
        "summary": "An injection attack targeted a database endpoint.",
    })
    judge = Judge(mock_llm)
    result, summary = await judge.evaluate_attack(
        attack_description="SQL injection on /api/users with ' OR 1=1--",
        target_description="REST API with user database",
        available_tools=["sqli_kit", "fuzzer"],
    )
    assert isinstance(result, AttackResult)
    assert result.success is True
    assert result.severity == Severity.HIGH
    assert result.points == 5
    assert result.auto_win is False
    assert isinstance(summary, str)


@pytest.mark.asyncio
async def test_judge_rejects_invalid_attack():
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = json.dumps({
        "valid": False,
        "severity": None,
        "points": 0,
        "auto_win": False,
        "reasoning": "The described attack would not work against this target",
        "summary": "An ineffective attack was attempted.",
    })
    judge = Judge(mock_llm)
    result, summary = await judge.evaluate_attack(
        attack_description="Tried to use buffer overflow on a Python web app",
        target_description="Flask REST API",
        available_tools=["fuzzer"],
    )
    assert result.success is False
    assert result.points == 0


@pytest.mark.asyncio
async def test_judge_detects_auto_win():
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = json.dumps({
        "valid": True,
        "severity": "critical",
        "points": 0,
        "auto_win": True,
        "reasoning": "Full privilege escalation achieved via kernel exploit",
        "summary": "A critical system-level compromise was achieved.",
    })
    judge = Judge(mock_llm)
    result, summary = await judge.evaluate_attack(
        attack_description="Kernel exploit CVE-2024-XXXX for root access",
        target_description="Linux server with outdated kernel",
        available_tools=["priv_esc_toolkit", "cve_database"],
    )
    assert result.auto_win is True


@pytest.mark.asyncio
async def test_judge_evaluates_defense_with_effectiveness():
    """Defense evaluation returns (blocked, effectiveness, reasoning) tuple."""
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = json.dumps({
        "blocked": True,
        "effectiveness": 0.85,
        "reasoning": "WAF rule correctly identified and blocked SQLi pattern",
    })
    judge = Judge(mock_llm)
    blocked, effectiveness, reasoning = await judge.evaluate_defense(
        attack_description="SQL injection on /api/users",
        defense_description="Deployed WAF rule blocking SQL metacharacters",
        available_tools=["waf_rules", "input_sanitizer"],
    )
    assert blocked is True
    assert effectiveness == 0.85
    assert "WAF" in reasoning


@pytest.mark.asyncio
async def test_judge_partial_defense():
    """Effectiveness between 0.3 and 0.7 — partial mitigation, blocked=False."""
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = json.dumps({
        "blocked": False,
        "effectiveness": 0.5,
        "reasoning": "Defense slowed the attack but didn't fully prevent it",
    })
    judge = Judge(mock_llm)
    blocked, effectiveness, reasoning = await judge.evaluate_defense(
        attack_description="Privilege escalation via misconfigured sudo",
        defense_description="Tightened some file permissions",
        available_tools=["hardening_scripts"],
    )
    assert blocked is False  # effectiveness < 0.7
    assert effectiveness == 0.5


@pytest.mark.asyncio
async def test_judge_effectiveness_clamped():
    """Effectiveness values outside 0.0-1.0 are clamped."""
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = json.dumps({
        "blocked": True,
        "effectiveness": 1.5,  # Out of range
        "reasoning": "Excellent defense",
    })
    judge = Judge(mock_llm)
    blocked, effectiveness, reasoning = await judge.evaluate_defense(
        attack_description="XSS attack",
        defense_description="CSP headers deployed",
        available_tools=["csp_toolkit"],
    )
    assert effectiveness == 1.0  # Clamped to max


@pytest.mark.asyncio
async def test_judge_evaluates_patch():
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = json.dumps({
        "addressed": True,
        "completeness": 0.85,
        "reasoning": "Patch addresses the root cause",
    })
    judge = Judge(mock_llm)
    bug = BugReport(round_number=1, title="SQLi", severity=Severity.HIGH,
                    domain=Domain.CODE_VULN, target="/api",
                    steps_to_reproduce="payload", proof_of_concept="",
                    impact="DB access")
    patch = Patch(round_number=1, title="Fix", fixes="parameterized queries",
                  strategy="input validation", changes="login.py", verification="sqlmap")
    result = await judge.evaluate_patch(bug, patch)
    assert result["addressed"] is True
    assert result["completeness"] == 0.85


# --- New calibration and summary tests ---


@pytest.mark.asyncio
async def test_judge_attack_response_includes_summary():
    """When LLM returns JSON with summary field, evaluate_attack returns it in the tuple."""
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = json.dumps({
        "valid": True,
        "severity": "medium",
        "points": 3,
        "auto_win": False,
        "reasoning": "IDOR allows reading other users' data",
        "summary": "An access control vulnerability was exploited.",
    })
    judge = Judge(mock_llm)
    result, summary = await judge.evaluate_attack(
        attack_description="IDOR on /api/users/123 changed to /api/users/456",
        target_description="REST API with user profiles",
        available_tools=["burp_suite"],
    )
    assert isinstance(result, AttackResult)
    assert result.success is True
    assert result.severity == Severity.MEDIUM
    assert summary == "An access control vulnerability was exploited."


@pytest.mark.asyncio
async def test_judge_attack_prompt_contains_calibration():
    """System prompt sent to LLM contains calibration examples for all severity levels."""
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = json.dumps({
        "valid": True,
        "severity": "low",
        "points": 1,
        "auto_win": False,
        "reasoning": "Minor info leak",
        "summary": "A reconnaissance attempt was made.",
    })
    judge = Judge(mock_llm)
    await judge.evaluate_attack(
        attack_description="Version enumeration",
        target_description="Web server",
        available_tools=[],
    )
    # Check the system prompt passed to the LLM
    call_kwargs = mock_llm.chat.call_args
    system_prompt = call_kwargs.kwargs.get("system") or call_kwargs[1].get("system", "")
    assert "Calibration Examples" in system_prompt
    assert "LOW (1 pt)" in system_prompt
    assert "MEDIUM (3 pts)" in system_prompt
    assert "HIGH (5 pts)" in system_prompt
    assert "CRITICAL (8 pts)" in system_prompt


@pytest.mark.asyncio
async def test_judge_attack_fallback_summary_on_missing():
    """When LLM returns JSON without summary field, fallback to truncated description."""
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = json.dumps({
        "valid": True,
        "severity": "high",
        "points": 5,
        "auto_win": False,
        "reasoning": "Successful SSRF",
    })
    judge = Judge(mock_llm)
    attack_desc = "SSRF targeting internal metadata endpoint to steal IAM credentials"
    result, summary = await judge.evaluate_attack(
        attack_description=attack_desc,
        target_description="Cloud-hosted API",
        available_tools=["ssrf_tool"],
    )
    assert isinstance(result, AttackResult)
    assert result.success is True
    # Summary should be the fallback: first 100 chars of attack_description
    assert summary == attack_desc  # Under 100 chars, no truncation
