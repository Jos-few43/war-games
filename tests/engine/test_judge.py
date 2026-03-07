import pytest
import json
from unittest.mock import AsyncMock
from wargames.engine.judge import Judge
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
    })
    judge = Judge(mock_llm)
    result = await judge.evaluate_attack(
        attack_description="SQL injection on /api/users with ' OR 1=1--",
        target_description="REST API with user database",
        available_tools=["sqli_kit", "fuzzer"],
    )
    assert isinstance(result, AttackResult)
    assert result.success is True
    assert result.severity == Severity.HIGH
    assert result.points == 5
    assert result.auto_win is False


@pytest.mark.asyncio
async def test_judge_rejects_invalid_attack():
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = json.dumps({
        "valid": False,
        "severity": None,
        "points": 0,
        "auto_win": False,
        "reasoning": "The described attack would not work against this target",
    })
    judge = Judge(mock_llm)
    result = await judge.evaluate_attack(
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
    })
    judge = Judge(mock_llm)
    result = await judge.evaluate_attack(
        attack_description="Kernel exploit CVE-2024-XXXX for root access",
        target_description="Linux server with outdated kernel",
        available_tools=["priv_esc_toolkit", "cve_database"],
    )
    assert result.auto_win is True


@pytest.mark.asyncio
async def test_judge_evaluates_defense():
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = json.dumps({
        "blocked": True,
        "reasoning": "WAF rule correctly identified and blocked SQLi pattern",
    })
    judge = Judge(mock_llm)
    blocked, reasoning = await judge.evaluate_defense(
        attack_description="SQL injection on /api/users",
        defense_description="Deployed WAF rule blocking SQL metacharacters",
        available_tools=["waf_rules", "input_sanitizer"],
    )
    assert blocked is True


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
