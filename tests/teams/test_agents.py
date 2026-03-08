import json
import pytest
from unittest.mock import AsyncMock
from wargames.teams.red import RedTeamAgent
from wargames.teams.blue import BlueTeamAgent
from wargames.models import BugReport, Patch, Severity, Domain

@pytest.mark.asyncio
async def test_red_team_generates_attack():
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = "SQL injection on /api/users endpoint using ' OR 1=1-- in the username field"
    agent = RedTeamAgent(mock_llm)
    attack = await agent.attack(
        target="REST API with user authentication",
        tools=["sqli_kit", "fuzzer"],
        past_lessons=["XSS was blocked by CSP headers last round"],
    )
    assert isinstance(attack, str)
    assert len(attack) > 10
    assert mock_llm.chat.call_count == 1

@pytest.mark.asyncio
async def test_blue_team_generates_defense():
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = "Deploy parameterized queries on all database calls and add WAF rule for SQL metacharacters"
    agent = BlueTeamAgent(mock_llm)
    defense = await agent.defend(
        attack_description="SQL injection on /api/users",
        target="REST API with user authentication",
        tools=["waf_rules", "input_sanitizer"],
        past_lessons=["Failed to catch XSS last round"],
    )
    assert isinstance(defense, str)
    assert len(defense) > 10

@pytest.mark.asyncio
async def test_red_team_writes_debrief():
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = "# Red Team Debrief\n- SQLi worked on turn 3\n- Should try SSRF next"
    agent = RedTeamAgent(mock_llm)
    debrief = await agent.write_debrief(
        attacks_summary="Turn 1: XSS failed. Turn 3: SQLi succeeded (HIGH).",
        draft_picks=["sqli_kit", "fuzzer", "cve_database"],
        outcome="red_win",
    )
    assert "Debrief" in debrief

@pytest.mark.asyncio
async def test_red_team_generates_bug_report():
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = json.dumps({
        "title": "SQL Injection in Login",
        "severity": "high",
        "domain": "code-vuln",
        "target": "/api/login",
        "steps_to_reproduce": "1. Send payload",
        "proof_of_concept": "' OR 1=1 --",
        "impact": "Full database access",
    })
    agent = RedTeamAgent(mock_llm)
    report = await agent.generate_bug_report("SQLi attack", "/api/login", ["sqli_kit"])
    assert report.title == "SQL Injection in Login"
    assert report.severity == Severity.HIGH


@pytest.mark.asyncio
async def test_red_team_bug_report_fallback():
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = "not json"
    agent = RedTeamAgent(mock_llm)
    report = await agent.generate_bug_report("some attack", "/target", [])
    assert report.title == "Unstructured Attack"
    assert report.severity == Severity.LOW


@pytest.mark.asyncio
async def test_blue_team_generates_patch():
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = json.dumps({
        "title": "Fix SQL Injection",
        "fixes": "Parameterized queries",
        "strategy": "Input validation + prepared statements",
        "changes": "Modified login handler",
        "verification": "Run SQLMap against endpoint",
    })
    bug = BugReport(round_number=1, title="SQLi", severity=Severity.HIGH,
                    domain=Domain.CODE_VULN, target="/api/login",
                    steps_to_reproduce="send payload",
                    proof_of_concept="' OR 1=1", impact="DB access")
    agent = BlueTeamAgent(mock_llm)
    patch = await agent.generate_patch(bug, "/api/login", ["input_sanitizer"])
    assert patch.title == "Fix SQL Injection"


@pytest.mark.asyncio
async def test_blue_team_writes_debrief():
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = "# Blue Team Debrief\n- Missed SQLi on turn 3\n- WAF caught XSS"
    agent = BlueTeamAgent(mock_llm)
    debrief = await agent.write_debrief(
        defenses_summary="Turn 1: Blocked XSS. Turn 3: Missed SQLi.",
        draft_picks=["waf_rules", "input_sanitizer", "logging_alerting"],
        outcome="red_win",
    )
    assert "Debrief" in debrief
