# War Games Expansion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expand war-games from a working prototype into a full competitive LLM security simulation with evolutionary learning, real CVE integration, structured bug reports/patches, and a live TUI dashboard.

**Architecture:** Layered additions — strategy persistence (DB+vault), structured agent output (bug reports/patches), CVE draft pool injection with scenario generation, async event bridge for TUI, then end-to-end validation. Each layer builds on the previous.

**Tech Stack:** Python 3.12+, Pydantic, aiosqlite, httpx, Textual, asyncio, Ollama/qwen3:4b

**Design doc:** `docs/plans/2026-03-06-war-games-expansion-design.md`

---

### Task 1: Strategy DB Table and StrategyStore

**Files:**
- Modify: `wargames/output/db.py:83-90` (add table DDL to ALL_TABLES)
- Modify: `wargames/models.py` (add Strategy model)
- Create: `wargames/engine/strategy.py`
- Test: `tests/engine/test_strategy.py`

**Step 1: Add Strategy model to models.py**

Add after `Patch` model (line 153):

```python
class Strategy(BaseModel):
    team: str
    phase: int
    strategy_type: str  # "attack", "defense", "draft"
    content: str
    win_rate: float = 0.0
    usage_count: int = 0
    created_round: int = 0
```

**Step 2: Add strategies table DDL to db.py**

Add before `ALL_TABLES` (line 83):

```python
CREATE_STRATEGIES = """
CREATE TABLE IF NOT EXISTS strategies (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    team           TEXT,
    phase          INTEGER,
    strategy_type  TEXT,
    content        TEXT,
    win_rate       REAL DEFAULT 0.0,
    usage_count    INTEGER DEFAULT 0,
    created_round  INTEGER
)
"""
```

Add `CREATE_STRATEGIES` to `ALL_TABLES` list.

**Step 3: Write failing test**

```python
# tests/engine/test_strategy.py
import pytest
from unittest.mock import AsyncMock
from wargames.engine.strategy import StrategyStore
from wargames.models import (
    Strategy, Phase, MatchOutcome, RoundResult,
    AttackResult, DefenseResult, Severity,
)


@pytest.fixture
def sample_result():
    return RoundResult(
        round_number=1,
        phase=Phase.PROMPT_INJECTION,
        outcome=MatchOutcome.RED_WIN,
        red_score=8,
        blue_threshold=10,
        red_draft=[], blue_draft=[],
        attacks=[AttackResult(turn=1, description="SQLi on login", success=True,
                              severity=Severity.HIGH, points=5)],
        defenses=[DefenseResult(turn=1, description="WAF blocked attempt", blocked=True,
                                 points_deducted=2)],
        red_debrief="Key insight: SQL injection via login form was effective. "
                    "Recommendation: Try union-based SQLi next time.",
        blue_debrief="Lesson learned: WAF rules caught the basic SQLi but missed "
                     "the second attempt. Need better input validation.",
    )


@pytest.mark.asyncio
async def test_extract_strategies(sample_result):
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = (
        '[{"strategy_type": "attack", "content": "Use union-based SQLi on login forms"},'
        ' {"strategy_type": "defense", "content": "Add parameterized queries to all endpoints"}]'
    )
    store = StrategyStore(llm=mock_llm)
    strategies = await store.extract_strategies(sample_result, team="red")
    assert len(strategies) == 2
    assert strategies[0].strategy_type == "attack"
    assert strategies[0].phase == 1
    assert strategies[0].created_round == 1


@pytest.mark.asyncio
async def test_save_and_load_strategies(tmp_path):
    from wargames.output.db import Database
    db = Database(tmp_path / "test.db")
    await db.init()
    store = StrategyStore(llm=AsyncMock(), db=db)

    strategy = Strategy(
        team="red", phase=1, strategy_type="attack",
        content="Use SQLi on login", win_rate=0.8,
        usage_count=3, created_round=1,
    )
    await store.save_strategies([strategy])
    loaded = await store.get_top_strategies("red", phase=1, limit=5)
    assert len(loaded) == 1
    assert loaded[0].content == "Use SQLi on login"
    assert loaded[0].win_rate == 0.8
    await db.close()


@pytest.mark.asyncio
async def test_update_win_rates(tmp_path):
    from wargames.output.db import Database
    db = Database(tmp_path / "test.db")
    await db.init()
    store = StrategyStore(llm=AsyncMock(), db=db)

    strategy = Strategy(
        team="red", phase=1, strategy_type="attack",
        content="Use SQLi on login", win_rate=0.5,
        usage_count=2, created_round=1,
    )
    await store.save_strategies([strategy])
    await store.update_win_rates(
        team="red", phase=1, round_won=True
    )
    loaded = await store.get_top_strategies("red", phase=1, limit=5)
    # (0.5*2 + 1) / 3 = 0.667
    assert loaded[0].win_rate == pytest.approx(0.667, abs=0.01)
    assert loaded[0].usage_count == 3
    await db.close()
```

**Step 4: Run test to verify it fails**

Run: `python -m pytest tests/engine/test_strategy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wargames.engine.strategy'`

**Step 5: Implement StrategyStore**

```python
# wargames/engine/strategy.py
from __future__ import annotations

import json
from wargames.models import Strategy, RoundResult


EXTRACT_SYSTEM = """You are analyzing a post-match debrief from a cybersecurity war game.
Extract actionable strategies as a JSON array. Each element:
{"strategy_type": "attack"|"defense"|"draft", "content": "concise strategy description"}

Return ONLY the JSON array. No markdown, no explanation."""


class StrategyStore:
    def __init__(self, llm=None, db=None):
        self.llm = llm
        self.db = db

    async def extract_strategies(
        self, result: RoundResult, team: str,
    ) -> list[Strategy]:
        debrief = result.red_debrief if team == "red" else result.blue_debrief
        if not debrief:
            return []

        try:
            raw = await self.llm.chat(
                [{"role": "user", "content": f"Debrief:\n{debrief}"}],
                system=EXTRACT_SYSTEM,
            )
            items = json.loads(raw)
        except (json.JSONDecodeError, Exception):
            return []

        strategies = []
        for item in items:
            strategies.append(Strategy(
                team=team,
                phase=result.phase.value,
                strategy_type=item.get("strategy_type", "attack"),
                content=item.get("content", ""),
                created_round=result.round_number,
            ))
        return strategies

    async def save_strategies(self, strategies: list[Strategy]) -> None:
        for s in strategies:
            await self.db._conn.execute(
                "INSERT INTO strategies (team, phase, strategy_type, content, "
                "win_rate, usage_count, created_round) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (s.team, s.phase, s.strategy_type, s.content,
                 s.win_rate, s.usage_count, s.created_round),
            )
        await self.db._conn.commit()

    async def get_top_strategies(
        self, team: str, phase: int, limit: int = 5,
    ) -> list[Strategy]:
        cursor = await self.db._conn.execute(
            "SELECT * FROM strategies WHERE team = ? AND phase = ? "
            "ORDER BY win_rate DESC LIMIT ?",
            (team, phase, limit),
        )
        rows = await cursor.fetchall()
        return [
            Strategy(
                team=r["team"], phase=r["phase"],
                strategy_type=r["strategy_type"], content=r["content"],
                win_rate=r["win_rate"], usage_count=r["usage_count"],
                created_round=r["created_round"],
            )
            for r in rows
        ]

    async def update_win_rates(
        self, team: str, phase: int, round_won: bool,
    ) -> None:
        cursor = await self.db._conn.execute(
            "SELECT id, win_rate, usage_count FROM strategies "
            "WHERE team = ? AND phase = ?",
            (team, phase),
        )
        rows = await cursor.fetchall()
        win_val = 1.0 if round_won else 0.0
        for row in rows:
            new_count = row["usage_count"] + 1
            new_rate = (row["win_rate"] * row["usage_count"] + win_val) / new_count
            await self.db._conn.execute(
                "UPDATE strategies SET win_rate = ?, usage_count = ? WHERE id = ?",
                (new_rate, new_count, row["id"]),
            )
        await self.db._conn.commit()
```

**Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/engine/test_strategy.py -v`
Expected: 3 passed

**Step 7: Commit**

```bash
git add wargames/models.py wargames/output/db.py wargames/engine/strategy.py tests/engine/test_strategy.py
git commit -m "feat(strategy): add strategy extraction, persistence, and win rate tracking"
```

---

### Task 2: Wire Strategy Store into Game Engine

**Files:**
- Modify: `wargames/engine/game.py:28-89`
- Modify: `wargames/engine/round.py:36-141`
- Modify: `wargames/teams/red.py:5-19`
- Modify: `wargames/teams/blue.py:5-22`
- Test: `tests/engine/test_game.py` (add test)

**Step 1: Add strategy context to agent system prompts**

In `wargames/teams/red.py`, modify `attack()` to accept `strategies: list[str] = None` parameter and inject them:

```python
async def attack(self, target: str, tools: list[str], past_lessons: list[str],
                 strategies: list[str] = None) -> str:
    lessons_text = "\n".join(f"- {l}" for l in past_lessons) if past_lessons else "None yet."
    strat_text = "\n".join(f"- {s}" for s in (strategies or []))
    system = (
        "You are a red team security researcher. Your job is to find vulnerabilities "
        "and craft exploits against the target system. Be creative, thorough, and realistic.\n\n"
        "Scoring: Low=1pt, Medium=3pts, High=5pts, Critical=8pts. "
        "Full privilege escalation or zero-day = automatic win.\n\n"
        f"Your available tools: {', '.join(tools)}\n\n"
        f"Proven tactics from past seasons:\n{strat_text or 'None yet.'}\n\n"
        f"Lessons from recent rounds:\n{lessons_text}"
    )
    return await self.llm.chat(
        [{"role": "user", "content": f"Target system: {target}\n\nDescribe your attack in detail."}],
        system=system,
    )
```

Same pattern for `BlueTeamAgent.defend()`.

**Step 2: Pass strategies through RoundEngine.play()**

Add `red_strategies` and `blue_strategies` parameters to `play()`. Pass them to `self.red.attack()` and `self.blue.defend()`.

**Step 3: Wire StrategyStore in GameEngine.run()**

After `await engine.init()`, create `StrategyStore(llm=self._judge_client, db=self.db)`.

Before each round: load top strategies for current phase.
After each round: extract strategies from debriefs, save them, update win rates.

```python
# In GameEngine.run(), after round_engine.play():
red_strats = await strategy_store.extract_strategies(result, "red")
blue_strats = await strategy_store.extract_strategies(result, "blue")
await strategy_store.save_strategies(red_strats + blue_strats)
won_red = result.outcome in (MatchOutcome.RED_WIN, MatchOutcome.RED_AUTO_WIN)
await strategy_store.update_win_rates("red", self._current_phase.value, won_red)
await strategy_store.update_win_rates("blue", self._current_phase.value, not won_red)
```

**Step 4: Add test for strategy integration**

```python
# In tests/engine/test_game.py
@pytest.mark.asyncio
async def test_game_engine_extracts_strategies(config):
    mock_round_result = RoundResult(
        round_number=1, phase=Phase.PROMPT_INJECTION,
        outcome=MatchOutcome.RED_WIN, red_score=8, blue_threshold=10,
        red_draft=[], blue_draft=[], attacks=[], defenses=[],
        red_debrief="SQLi on login was effective",
        blue_debrief="WAF rules were insufficient",
    )
    with patch("wargames.engine.game.RoundEngine") as MockRound:
        MockRound.return_value.play = AsyncMock(return_value=mock_round_result)
        with patch("wargames.engine.game.LLMClient") as MockLLMClient:
            mock_llm = MagicMock()
            mock_llm.close = AsyncMock()
            mock_llm.chat = AsyncMock(return_value='[]')
            MockLLMClient.return_value = mock_llm
            engine = GameEngine(config)
            await engine.init()
            results = []
            async for result in engine.run():
                results.append(result)
            await engine.cleanup()
            assert len(results) == 3
```

**Step 5: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All pass (existing + new)

**Step 6: Commit**

```bash
git add wargames/teams/red.py wargames/teams/blue.py wargames/engine/round.py wargames/engine/game.py tests/engine/test_game.py
git commit -m "feat(strategy): wire strategy store into game loop with agent prompt injection"
```

---

### Task 3: Vault Strategy Output

**Files:**
- Modify: `wargames/output/vault.py` (add `write_strategy_update` method)
- Modify: `wargames/worker.py` (call vault strategy writer after round)
- Test: `tests/output/test_vault.py` (add test)

**Step 1: Write failing test**

```python
# In tests/output/test_vault.py
def test_write_strategy_update(writer):
    from wargames.models import Strategy
    strategies = [
        Strategy(team="red", phase=1, strategy_type="attack",
                 content="Use union-based SQLi", win_rate=0.8,
                 usage_count=3, created_round=1),
    ]
    writer.write_strategy_update(round_number=1, phase_name="prompt-injection", strategies=strategies)
    path = writer.base_path / "strategies" / "phase-1-prompt-injection.md"
    assert path.exists()
    content = path.read_text()
    assert "union-based SQLi" in content
    assert "Round 1" in content
```

**Step 2: Run test, verify fail**

Run: `python -m pytest tests/output/test_vault.py::test_write_strategy_update -v`
Expected: FAIL — `AttributeError: 'VaultWriter' has no attribute 'write_strategy_update'`

**Step 3: Implement write_strategy_update**

Add to `VaultWriter` class in `wargames/output/vault.py`:

```python
def write_strategy_update(self, round_number: int, phase_name: str, strategies: list):
    strat_dir = self.base_path / "strategies"
    strat_dir.mkdir(parents=True, exist_ok=True)
    path = strat_dir / f"phase-{phase_name}.md"

    if not path.exists():
        header = (
            f"---\n"
            f"type: strategy-evolution\n"
            f"phase: {phase_name}\n"
            f"tags: [wargames, strategy]\n"
            f"---\n\n"
            f"# Strategy Evolution: {phase_name.replace('-', ' ').title()}\n\n"
        )
        path.write_text(header)

    entries = []
    for s in strategies:
        entries.append(
            f"- **[{s.strategy_type}]** {s.content} "
            f"(win rate: {s.win_rate:.0%}, used {s.usage_count}x)"
        )
    if entries:
        with open(path, "a") as f:
            f.write(f"\n## Round {round_number}\n\n")
            f.write("\n".join(entries) + "\n")
```

**Step 4: Wire into worker.py**

In `Worker.run()`, after `self._vault.write_round(result)`, call strategy extraction and vault write.

**Step 5: Run tests, verify pass**

Run: `python -m pytest tests/output/test_vault.py -v`
Expected: All pass

**Step 6: Commit**

```bash
git add wargames/output/vault.py wargames/worker.py tests/output/test_vault.py
git commit -m "feat(vault): add strategy evolution notes to Obsidian output"
```

---

### Task 4: Structured Bug Reports & Patches

**Files:**
- Modify: `wargames/teams/red.py` (add `generate_bug_report`)
- Modify: `wargames/teams/blue.py` (add `generate_patch`)
- Modify: `wargames/engine/judge.py` (add `evaluate_patch`)
- Modify: `wargames/models.py` (add `PatchScore`, extend `RoundResult`)
- Modify: `wargames/engine/round.py` (wire bug reports/patches into round)
- Modify: `wargames/output/db.py` (add tables)
- Test: `tests/teams/test_agents.py` (add tests)
- Test: `tests/engine/test_judge.py` (add patch eval test)

**Step 1: Add PatchScore model and extend RoundResult**

In `models.py`, add after `Patch`:

```python
class PatchScore(BaseModel):
    addressed: bool = False
    completeness: float = 0.0
    reasoning: str = ""
```

Add to `RoundResult`:

```python
bug_reports: list[BugReport] = []
patches: list[Patch] = []
```

**Step 2: Add bug_reports and patches tables to db.py**

```python
CREATE_BUG_REPORTS = """
CREATE TABLE IF NOT EXISTS bug_reports (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    round_number       INTEGER REFERENCES rounds(round_number),
    title              TEXT,
    severity           TEXT,
    domain             TEXT,
    target             TEXT,
    steps_to_reproduce TEXT,
    proof_of_concept   TEXT,
    impact             TEXT
)
"""

CREATE_PATCHES = """
CREATE TABLE IF NOT EXISTS patches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    round_number INTEGER REFERENCES rounds(round_number),
    title        TEXT,
    fixes        TEXT,
    strategy     TEXT,
    changes      TEXT,
    verification TEXT
)
"""
```

Add both to `ALL_TABLES`. Add `save_round` handling for bug_reports and patches.

**Step 3: Write failing tests for agents**

```python
# In tests/teams/test_agents.py
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
async def test_blue_team_generates_patch():
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = json.dumps({
        "title": "Fix SQL Injection",
        "fixes": "Parameterized queries",
        "strategy": "Input validation + prepared statements",
        "changes": "Modified login handler",
        "verification": "Run SQLMap against endpoint",
    })
    from wargames.models import BugReport
    bug = BugReport(round_number=1, title="SQLi", severity=Severity.HIGH,
                    domain=Domain.CODE_VULN, target="/api/login",
                    steps_to_reproduce="send payload",
                    proof_of_concept="' OR 1=1", impact="DB access")
    agent = BlueTeamAgent(mock_llm)
    patch = await agent.generate_patch(bug, "/api/login", ["input_sanitizer"])
    assert patch.title == "Fix SQL Injection"
```

**Step 4: Implement generate_bug_report on RedTeamAgent**

```python
async def generate_bug_report(self, attack_desc: str, target: str, tools: list[str]) -> BugReport:
    system = (
        "You are a red team researcher writing a structured vulnerability report.\n"
        "Respond ONLY with valid JSON matching this schema:\n"
        '{"title": str, "severity": "low"|"medium"|"high"|"critical", '
        '"domain": "prompt-injection"|"code-vuln"|"config"|"social-engineering"|"mixed", '
        '"target": str, "steps_to_reproduce": str, "proof_of_concept": str, "impact": str}'
    )
    response = await self.llm.chat(
        [{"role": "user", "content": (
            f"Attack: {attack_desc}\nTarget: {target}\n"
            f"Tools: {', '.join(tools)}\n\nWrite the vulnerability report."
        )}],
        system=system,
    )
    try:
        data = json.loads(response)
        return BugReport(round_number=0, **data)
    except (json.JSONDecodeError, Exception):
        return BugReport(
            round_number=0, title="Unstructured Attack",
            severity=Severity.LOW, domain=Domain.MIXED, target=target,
            steps_to_reproduce=attack_desc, proof_of_concept="",
            impact="See attack description",
        )
```

**Step 5: Implement generate_patch on BlueTeamAgent**

```python
async def generate_patch(self, bug_report, target: str, tools: list[str]) -> Patch:
    system = (
        "You are a blue team engineer writing a patch for a vulnerability.\n"
        "Respond ONLY with valid JSON matching this schema:\n"
        '{"title": str, "fixes": str, "strategy": str, "changes": str, "verification": str}'
    )
    response = await self.llm.chat(
        [{"role": "user", "content": (
            f"Vulnerability: {bug_report.title}\n"
            f"Severity: {bug_report.severity.value}\n"
            f"Steps: {bug_report.steps_to_reproduce}\n"
            f"Target: {target}\nTools: {', '.join(tools)}\n\nWrite the patch."
        )}],
        system=system,
    )
    try:
        data = json.loads(response)
        return Patch(round_number=0, **data)
    except (json.JSONDecodeError, Exception):
        return Patch(
            round_number=0, title=f"Patch for {bug_report.title}",
            fixes="See defense description", strategy="reactive",
            changes="", verification="manual review",
        )
```

**Step 6: Add evaluate_patch to Judge**

```python
PATCH_SYSTEM_PROMPT = """You are an impartial judge evaluating a security patch against a vulnerability report.

Respond ONLY with valid JSON:
{"addressed": bool, "completeness": float, "reasoning": str}

completeness is 0.0-1.0: 0=useless, 0.5=partial, 1.0=complete fix."""


async def evaluate_patch(self, bug_report, patch) -> dict:
    user_message = (
        f"Vulnerability: {bug_report.title} ({bug_report.severity.value})\n"
        f"Steps to reproduce: {bug_report.steps_to_reproduce}\n"
        f"Patch title: {patch.title}\n"
        f"Patch strategy: {patch.strategy}\n"
        f"Patch changes: {patch.changes}\n\n"
        "Does this patch adequately address the vulnerability?"
    )
    try:
        response = await self.llm.chat(
            [{"role": "user", "content": user_message}],
            system=PATCH_SYSTEM_PROMPT,
        )
        return json.loads(response)
    except (json.JSONDecodeError, Exception):
        return {"addressed": False, "completeness": 0.0, "reasoning": "Parse error"}
```

**Step 7: Wire into RoundEngine.play()**

After each successful attack in the turn loop, generate bug report and patch:

```python
if attack_result.success:
    red_score += attack_result.points
    bug_report = await self.red.generate_bug_report(attack_desc, target, red_tools)
    bug_report.round_number = round_number
    bug_reports.append(bug_report)

    patch = await self.blue.generate_patch(bug_report, target, blue_tools)
    patch.round_number = round_number
    patches.append(patch)
```

Add `bug_reports` and `patches` to the RoundResult construction.

**Step 8: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All pass

**Step 9: Commit**

```bash
git add wargames/models.py wargames/teams/red.py wargames/teams/blue.py wargames/engine/judge.py wargames/engine/round.py wargames/output/db.py tests/teams/test_agents.py tests/engine/test_judge.py
git commit -m "feat(reports): add structured bug reports, patches, and patch scoring"
```

---

### Task 5: CVE Draft Pool Injection

**Files:**
- Modify: `wargames/engine/draft.py:15-58` (add `from_cves` classmethod)
- Modify: `wargames/engine/round.py:42-53` (use CVE pool for phase 3+)
- Modify: `wargames/output/db.py` (add `get_cves` method)
- Test: `tests/engine/test_draft.py` (add CVE pool tests)

**Step 1: Write failing test**

```python
# In tests/engine/test_draft.py
@pytest.mark.asyncio
async def test_draft_pool_from_cves():
    from wargames.output.db import Database
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        await db.init()
        await db.save_cve({
            "cve_id": "CVE-2021-44228",
            "source": "nvd",
            "severity": "critical",
            "domain": "code-vuln",
            "description": "Log4Shell RCE via JNDI lookup",
            "exploit_code": "",
            "fix_hint": "Upgrade log4j",
            "fetched_at": "2026-03-06",
        })
        pool = await DraftPool.from_cves(db)
        assert len(pool.resources) > 0
        cve_resources = [r for r in pool.resources if r.category == "cve"]
        assert len(cve_resources) == 1
        assert "Log4Shell" in cve_resources[0].description
        await db.close()


def test_mixed_pool_has_defaults_and_cves():
    default_pool = DraftPool.default()
    cve_resource = Resource("CVE-2021-44228", "cve", "Log4Shell RCE")
    mixed = DraftPool(default_pool.resources + [cve_resource])
    assert any(r.category == "cve" for r in mixed.resources)
    assert any(r.category == "offensive" for r in mixed.resources)
```

**Step 2: Add get_cves to Database**

```python
async def get_cves(self, limit: int = 20) -> list[dict]:
    cursor = await self._conn.execute(
        "SELECT * FROM crawled_cves ORDER BY ROWID DESC LIMIT ?", (limit,)
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
```

**Step 3: Add from_cves classmethod to DraftPool**

```python
@classmethod
async def from_cves(cls, db, include_defaults: bool = True) -> "DraftPool":
    cve_rows = await db.get_cves()
    cve_resources = [
        Resource(
            name=row["cve_id"],
            category="cve",
            description=row["description"][:200],
        )
        for row in cve_rows
    ]
    if include_defaults:
        base = cls.default()
        return cls(base.resources + cve_resources)
    return cls(cve_resources)
```

**Step 4: Update RoundEngine to use CVE pool for phase 3+**

In `round.py`, modify the pool selection at the top of `play()`:

```python
if phase in (Phase.REAL_CVES, Phase.OPEN_ENDED) and self.db:
    pool = await DraftPool.from_cves(self.db)
else:
    pool = DraftPool.default()
```

**Step 5: Run tests, verify pass**

Run: `python -m pytest tests/engine/test_draft.py -v`
Expected: All pass

**Step 6: Commit**

```bash
git add wargames/engine/draft.py wargames/engine/round.py wargames/output/db.py tests/engine/test_draft.py
git commit -m "feat(cve): inject crawled CVEs into draft pool for phase 3+"
```

---

### Task 6: Scenario Generator

**Files:**
- Create: `wargames/engine/scenario.py`
- Modify: `wargames/engine/round.py:143-150` (use scenario for CVE phases)
- Test: `tests/engine/test_scenario.py`

**Step 1: Write failing test**

```python
# tests/engine/test_scenario.py
import pytest
from wargames.engine.scenario import ScenarioGenerator
from wargames.engine.draft import Resource


def test_generate_target_from_cve():
    gen = ScenarioGenerator()
    cve_resources = [
        Resource("CVE-2021-44228", "cve", "Log4Shell: RCE via JNDI lookup in log4j"),
    ]
    target = gen.generate_target(cve_resources)
    assert "CVE-2021-44228" in target
    assert "log4j" in target.lower() or "Log4Shell" in target


def test_generate_target_no_cves_returns_default():
    gen = ScenarioGenerator()
    target = gen.generate_target([])
    assert "web application" in target.lower()


def test_generate_target_multiple_cves():
    gen = ScenarioGenerator()
    cves = [
        Resource("CVE-2021-44228", "cve", "Log4Shell RCE"),
        Resource("CVE-2021-41773", "cve", "Apache path traversal"),
    ]
    target = gen.generate_target(cves)
    assert "CVE-2021-44228" in target
    assert "CVE-2021-41773" in target
```

**Step 2: Implement ScenarioGenerator**

```python
# wargames/engine/scenario.py
from __future__ import annotations
from wargames.engine.draft import Resource


class ScenarioGenerator:
    DEFAULT_TARGET = (
        "A full-stack web application with API, database, authentication, "
        "and file storage. Standard security posture with common misconfigurations."
    )

    def generate_target(self, cve_resources: list[Resource]) -> str:
        cves = [r for r in cve_resources if r.category == "cve"]
        if not cves:
            return self.DEFAULT_TARGET

        vuln_list = "\n".join(
            f"- {cve.name}: {cve.description}" for cve in cves
        )
        return (
            f"A web application server with the following known vulnerabilities:\n"
            f"{vuln_list}\n\n"
            f"The server runs outdated software. Exploit the specific CVEs or "
            f"discover additional weaknesses."
        )
```

**Step 3: Wire into RoundEngine**

In `play()`, replace `_default_target()` call for CVE phases:

```python
if not target:
    if phase in (Phase.REAL_CVES, Phase.OPEN_ENDED):
        from wargames.engine.scenario import ScenarioGenerator
        cve_picks = [r for r in (red_tools + blue_tools)
                     if any(p.resource_category == "cve" for p in red_draft_picks + blue_draft_picks
                            if p.resource_name == r)]
        # Build resource list from draft picks
        cve_resources = []
        for pick in red_draft_picks + blue_draft_picks:
            if pick.resource_category == "cve":
                cve_resources.append(Resource(pick.resource_name, "cve", pick.resource_name))
        target = ScenarioGenerator().generate_target(cve_resources)
    else:
        target = self._default_target(phase)
```

**Step 4: Run tests, verify pass**

Run: `python -m pytest tests/engine/test_scenario.py tests/engine/test_round.py -v`
Expected: All pass

**Step 5: Commit**

```bash
git add wargames/engine/scenario.py wargames/engine/round.py tests/engine/test_scenario.py
git commit -m "feat(scenario): generate CVE-based target descriptions for phase 3+"
```

---

### Task 7: TUI Event Bridge

**Files:**
- Create: `wargames/tui/bridge.py`
- Modify: `wargames/worker.py` (create bridge, wire to engine events)
- Modify: `wargames/tui/app.py` (consume bridge events)
- Test: `tests/tui/test_bridge.py`

**Step 1: Write failing test**

```python
# tests/tui/test_bridge.py
import pytest
import asyncio
from wargames.tui.bridge import EventBridge


@pytest.mark.asyncio
async def test_bridge_push_and_drain():
    bridge = EventBridge()
    bridge.push("attack", {"turn": 1, "success": True})
    bridge.push("defense", {"turn": 1, "blocked": False})
    events = bridge.drain()
    assert len(events) == 2
    assert events[0] == ("attack", {"turn": 1, "success": True})


@pytest.mark.asyncio
async def test_bridge_drain_empty():
    bridge = EventBridge()
    events = bridge.drain()
    assert events == []


@pytest.mark.asyncio
async def test_bridge_async_push():
    bridge = EventBridge()
    await bridge.async_push("round_complete", {"outcome": "red_win"})
    events = bridge.drain()
    assert len(events) == 1
```

**Step 2: Implement EventBridge**

```python
# wargames/tui/bridge.py
from __future__ import annotations
import asyncio
from collections import deque


class EventBridge:
    def __init__(self, maxlen: int = 500):
        self._queue: deque[tuple[str, dict]] = deque(maxlen=maxlen)

    def push(self, event_type: str, data: dict) -> None:
        self._queue.append((event_type, data))

    async def async_push(self, event_type: str, data: dict) -> None:
        self._queue.append((event_type, data))

    def drain(self) -> list[tuple[str, dict]]:
        events = list(self._queue)
        self._queue.clear()
        return events
```

**Step 3: Wire bridge into Worker**

In `wargames/worker.py`, add bridge creation and event forwarding:

```python
from wargames.tui.bridge import EventBridge

class Worker:
    def __init__(self, config, pid_file=None):
        # ... existing ...
        self._bridge = EventBridge()

    @property
    def bridge(self) -> EventBridge:
        return self._bridge
```

In `run()`, after creating the engine, set the event callback:

```python
round_engine.on_event(lambda etype, data: self._bridge.push(etype, data))
```

Wait — `on_event` is on `RoundEngine`, not `GameEngine`. The worker creates `GameEngine` which internally creates `RoundEngine`. We need to pass the bridge callback through.

Better approach: add `on_event` to `GameEngine` which forwards to each `RoundEngine` it creates.

In `wargames/engine/game.py`:

```python
def __init__(self, config):
    # ... existing ...
    self._on_event = None

def on_event(self, callback):
    self._on_event = callback
```

In `run()`, after creating `round_engine`:

```python
if self._on_event:
    round_engine.on_event(self._on_event)
```

In `worker.py`, in `run()`:

```python
self._engine = GameEngine(self.config)
await self._engine.init()
self._engine.on_event(lambda etype, data: self._bridge.push(etype, data))
```

**Step 4: Update TUI to consume bridge events**

In `wargames/tui/app.py`, modify `__init__` to accept an optional bridge:

```python
def __init__(self, db_path: str, bridge: EventBridge | None = None, **kwargs):
    super().__init__(**kwargs)
    self.db_path = db_path
    self._bridge = bridge
```

Add `consume_events` method:

```python
def consume_events(self):
    if not self._bridge:
        return
    for event_type, data in self._bridge.drain():
        feed = self.query_one("#feed", LiveFeed)
        if event_type == "draft_complete":
            red_tools = ", ".join(data.get("red", []))
            blue_tools = ", ".join(data.get("blue", []))
            feed.write(f"[bold]DRAFT[/] Red: {red_tools}")
            feed.write(f"[bold]DRAFT[/] Blue: {blue_tools}")
        elif event_type == "attack":
            turn = data.get("turn", "?")
            success = data.get("success", False)
            pts = data.get("points", 0)
            color = "green" if success else "red"
            desc = data.get("description", "")[:80]
            feed.write(f"[{color}]T{turn} ATK[/] {'HIT' if success else 'MISS'} (+{pts}) {desc}")
            if success:
                score_widget = self.query_one("#red-score", Static)
                score_widget.update(f"Score: {data.get('red_score', '?')}")
        elif event_type == "defense":
            turn = data.get("turn", "?")
            blocked = data.get("blocked", False)
            color = "blue" if blocked else "yellow"
            feed.write(f"[{color}]T{turn} DEF[/] {'BLOCKED' if blocked else 'MISSED'}")
        elif event_type == "round_complete":
            outcome = data.get("outcome", "?")
            score = data.get("red_score", "?")
            feed.write(f"[bold]━━━ ROUND COMPLETE: {outcome} (score: {score}) ━━━[/]")
```

In `on_mount`, add: `self.set_interval(0.5, self.consume_events)`

**Step 5: Implement pause toggle**

```python
def action_toggle_pause(self):
    feed = self.query_one("#feed", LiveFeed)
    if hasattr(self, '_paused') and self._paused:
        self._paused = False
        feed.write("[bold green]RESUMED[/]")
        self.sub_title = ""
    else:
        self._paused = True
        feed.write("[bold yellow]PAUSED[/]")
        self.sub_title = "PAUSED"
```

Note: actual pause/resume requires the worker's `GameEngine.pause()`/`resume()` to be called. For now, the TUI displays the state; wiring to the actual worker pause is done via the CLI's existing `wargames pause`/`wargames resume` commands.

**Step 6: Run tests**

Run: `python -m pytest tests/tui/ -v`
Expected: All pass

**Step 7: Commit**

```bash
git add wargames/tui/bridge.py wargames/tui/app.py wargames/engine/game.py wargames/worker.py tests/tui/test_bridge.py
git commit -m "feat(tui): add event bridge for live scoreboard and round log"
```

---

### Task 8: Wire Vault Bug Reports & Patches in Worker

**Files:**
- Modify: `wargames/worker.py` (write bug reports, patches, strategy notes after each round)
- Modify: `wargames/output/vault.py` (import models)
- Test: `tests/test_worker.py` (verify vault calls)

**Step 1: Update worker run loop**

In `wargames/worker.py`, after `self._vault.write_round(result)`:

```python
for bug in result.bug_reports:
    self._vault.write_bug_report(bug)
for patch in result.patches:
    self._vault.write_patch(patch)
```

**Step 2: Add test**

```python
@pytest.mark.asyncio
async def test_worker_writes_vault_bug_reports(tmp_path):
    # Similar to existing worker test but with bug_reports on result
    ...
```

**Step 3: Run tests, verify pass**

Run: `python -m pytest tests/test_worker.py -v`
Expected: All pass

**Step 4: Commit**

```bash
git add wargames/worker.py tests/test_worker.py
git commit -m "feat(worker): write bug reports and patches to vault"
```

---

### Task 9: End-to-End Validation

**Files:**
- Modify: `config/test-multi.toml` (ensure crawler enabled for CVE test)
- Test: `tests/test_integration.py` (extend integration test)

**Step 1: Update integration test**

Add a test that exercises the full pipeline with mocked LLMs, including bug reports, patches, strategies, and vault output:

```python
@pytest.mark.asyncio
async def test_full_pipeline_with_reports_and_strategies(tmp_path):
    # Create config pointing to tmp_path for DB and vault
    # Mock LLMs to return structured JSON
    # Run 2 rounds
    # Assert: bug reports, patches, strategies all populated
    # Assert: vault files created for rounds, bug reports, patches, strategies
```

**Step 2: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All pass

**Step 3: Commit**

```bash
git add tests/test_integration.py config/test-multi.toml
git commit -m "test: add full pipeline integration test with reports and strategies"
```

---

### Task 10: Live Game Run with Ollama

**Files:** No code changes — operational validation.

**Step 1: Pre-flight checks**

```bash
curl -s http://localhost:11434/api/tags | python -m json.tool | grep qwen3
```

**Step 2: Run crawler**

```bash
wargames crawl --config config/test-multi.toml
```

**Step 3: Start game**

```bash
wargames start --config config/test-multi.toml
```

**Step 4: Attach TUI**

```bash
wargames attach
```

**Step 5: Validate outputs**

```bash
# Check vault
ls ~/OpenClaw-Vault/WarGames/rounds/
ls ~/OpenClaw-Vault/WarGames/bug-reports/
ls ~/OpenClaw-Vault/WarGames/patches/
ls ~/OpenClaw-Vault/WarGames/strategies/

# Check DB
sqlite3 ~/.local/share/wargames/state.db "SELECT COUNT(*) FROM rounds; SELECT COUNT(*) FROM strategies; SELECT COUNT(*) FROM bug_reports;"
```

**Step 6: Commit any prompt tuning or config adjustments**

```bash
git add -A
git commit -m "chore: tune prompts and config from live run validation"
```
