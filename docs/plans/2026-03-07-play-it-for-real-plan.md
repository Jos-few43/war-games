# Play It For Real — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make war-games playable end-to-end with cloud+local fallback, working CLI commands, and a successful first real game run.

**Architecture:** Add fallback model support to LLMClient (retry primary → fallback chain), wire three stubbed CLI commands to existing crawlers/DB, create a cloud-with-fallback config preset.

**Tech Stack:** Python 3.12+, httpx, aiosqlite, pydantic, pytest, pytest-asyncio

---

### Task 1: Add fallback fields to TeamSettings

**Files:**
- Modify: `wargames/models.py:59-70` (TeamSettings class)
- Test: `tests/test_config.py`

**Step 1: Write the failing test**

In `tests/test_config.py`, add:

```python
def test_team_settings_fallback_fields():
    ts = TeamSettings(
        name="Test",
        model="http://cloud:4002",
        model_name="openrouter/auto",
        temperature=0.7,
        fallback_model="http://localhost:11434",
        fallback_model_name="qwen3:4b",
        fallback_api_key="",
    )
    assert ts.fallback_model == "http://localhost:11434"
    assert ts.fallback_model_name == "qwen3:4b"
    assert ts.fallback_api_key == ""


def test_team_settings_fallback_defaults():
    ts = TeamSettings(
        name="Test",
        model="http://cloud:4002",
        model_name="openrouter/auto",
        temperature=0.7,
    )
    assert ts.fallback_model == ""
    assert ts.fallback_model_name == ""


def test_team_settings_fallback_env_var_resolution():
    import os
    os.environ["TEST_FALLBACK_KEY"] = "fb-secret"
    ts = TeamSettings(
        name="Test",
        model="http://cloud:4002",
        model_name="openrouter/auto",
        temperature=0.7,
        fallback_api_key="$TEST_FALLBACK_KEY",
    )
    assert ts.fallback_api_key == "fb-secret"
    del os.environ["TEST_FALLBACK_KEY"]
```

**Step 2: Run test to verify it fails**

Run: `cd ~/PROJECTz/war-games && python -m pytest tests/test_config.py::test_team_settings_fallback_fields -v`
Expected: FAIL — `TeamSettings` doesn't accept `fallback_model`

**Step 3: Write minimal implementation**

In `wargames/models.py`, add three fields to `TeamSettings` (after `api_key`):

```python
class TeamSettings(BaseModel):
    name: str
    model: str
    model_name: str
    temperature: float = Field(ge=0.0, le=2.0)
    timeout: float = Field(default=120.0, description="HTTP timeout per LLM call in seconds")
    api_key: str = Field(default="", description="API key or env var ref like $LITELLM_MASTER_KEY")
    fallback_model: str = Field(default="", description="Fallback base URL")
    fallback_model_name: str = Field(default="", description="Fallback model name")
    fallback_api_key: str = Field(default="", description="Fallback API key or env var ref")

    @model_validator(mode="after")
    def resolve_env_vars(self):
        if self.api_key.startswith("$"):
            self.api_key = os.environ.get(self.api_key[1:], "")
        if self.fallback_api_key.startswith("$"):
            self.fallback_api_key = os.environ.get(self.fallback_api_key[1:], "")
        return self
```

**Step 4: Run test to verify it passes**

Run: `cd ~/PROJECTz/war-games && python -m pytest tests/test_config.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add wargames/models.py tests/test_config.py
git commit -m "feat(models): add fallback model fields to TeamSettings"
```

---

### Task 2: Add fallback retry logic to LLMClient

**Files:**
- Modify: `wargames/llm/client.py`
- Test: `tests/llm/test_client.py`

**Step 1: Write the failing tests**

Add to `tests/llm/test_client.py`:

```python
@pytest.fixture
def fallback_settings():
    return TeamSettings(
        name="Fallback Team",
        model="http://cloud:4002/v1",
        model_name="cloud-model",
        temperature=0.7,
        fallback_model="http://localhost:11434/v1",
        fallback_model_name="qwen3:4b",
    )


@pytest.mark.asyncio
async def test_chat_falls_back_on_primary_exhaustion(fallback_settings):
    """After primary retries exhausted, should try fallback model."""
    client = LLMClient(fallback_settings)
    mock_success = _ok_response("fallback response")

    # Primary always fails (5 ReadTimeout = exhaust MAX_RETRIES)
    primary_fails = [httpx.ReadTimeout("timeout")] * 5

    call_count = 0
    original_post = client._http.post

    async def mock_post(url, **kwargs):
        nonlocal call_count
        call_count += 1
        body = kwargs.get("json", {})
        if body.get("model") == "cloud-model":
            exc = primary_fails.pop(0) if primary_fails else None
            if exc:
                raise exc
        return mock_success

    with patch.object(client._http, "post", side_effect=mock_post):
        with patch.object(client, "_fallback_http") as fb_http:
            fb_http.post = AsyncMock(return_value=mock_success)
            result = await client.chat([{"role": "user", "content": "Hi"}])
            assert result == "fallback response"
            fb_http.post.assert_called_once()

    await client.close()


@pytest.mark.asyncio
async def test_chat_no_fallback_when_primary_succeeds(fallback_settings):
    """Fallback should NOT be used if primary succeeds."""
    client = LLMClient(fallback_settings)
    mock_success = _ok_response("primary response")
    with patch.object(client._http, "post", return_value=mock_success):
        result = await client.chat([{"role": "user", "content": "Hi"}])
        assert result == "primary response"
    await client.close()


@pytest.mark.asyncio
async def test_chat_no_fallback_configured(team_settings):
    """Without fallback configured, should raise after primary fails."""
    client = LLMClient(team_settings)
    with patch.object(
        client._http, "post",
        side_effect=httpx.ReadTimeout("timeout"),
    ):
        with pytest.raises(httpx.ReadTimeout):
            await client.chat([{"role": "user", "content": "Hi"}])
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/PROJECTz/war-games && python -m pytest tests/llm/test_client.py::test_chat_falls_back_on_primary_exhaustion -v`
Expected: FAIL — `_fallback_http` doesn't exist

**Step 3: Write minimal implementation**

Replace `wargames/llm/client.py` with:

```python
import asyncio
import logging
import httpx
from wargames.models import TeamSettings

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class LLMClient:
    MAX_RETRIES = 5
    RETRY_BACKOFF = 2.0
    FALLBACK_RETRIES = 2

    def __init__(self, settings: TeamSettings):
        self.settings = settings
        headers = {}
        if settings.api_key:
            headers["Authorization"] = f"Bearer {settings.api_key}"
        self._http = httpx.AsyncClient(
            base_url=settings.model, timeout=settings.timeout, headers=headers,
        )

        # Set up fallback client if configured
        self._fallback_http: httpx.AsyncClient | None = None
        if settings.fallback_model:
            fb_headers = {}
            if settings.fallback_api_key:
                fb_headers["Authorization"] = f"Bearer {settings.fallback_api_key}"
            self._fallback_http = httpx.AsyncClient(
                base_url=settings.fallback_model,
                timeout=settings.timeout,
                headers=fb_headers,
            )

    async def _attempt(
        self, http: httpx.AsyncClient, model_name: str,
        messages: list[dict], max_retries: int,
    ) -> str:
        """Try a model with retries. Raises on exhaustion."""
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": self.settings.temperature,
        }
        last_exc = None
        for attempt in range(max_retries):
            try:
                response = await http.post("/chat/completions", json=payload)
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code not in RETRYABLE_STATUS:
                    raise
                retry_after = exc.response.headers.get("retry-after")
                delay = float(retry_after) if retry_after else self.RETRY_BACKOFF * (2 ** attempt)
                logger.warning("HTTP %d on attempt %d, retrying in %.1fs", exc.response.status_code, attempt + 1, delay)
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
            except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadTimeout) as exc:
                last_exc = exc
                if attempt < max_retries - 1:
                    await asyncio.sleep(self.RETRY_BACKOFF * (attempt + 1))
        raise last_exc

    async def chat(self, messages: list[dict], system: str | None = None) -> str:
        if system:
            messages = [{"role": "system", "content": system}, *messages]

        try:
            return await self._attempt(
                self._http, self.settings.model_name, messages, self.MAX_RETRIES,
            )
        except (httpx.HTTPStatusError, httpx.RemoteProtocolError,
                httpx.ConnectError, httpx.ReadTimeout) as exc:
            if not self._fallback_http:
                raise
            logger.warning(
                "Primary model %s failed after %d retries, falling back to %s",
                self.settings.model_name, self.MAX_RETRIES,
                self.settings.fallback_model_name,
            )
            return await self._attempt(
                self._fallback_http, self.settings.fallback_model_name,
                messages, self.FALLBACK_RETRIES,
            )

    async def close(self):
        await self._http.aclose()
        if self._fallback_http:
            await self._fallback_http.aclose()
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/PROJECTz/war-games && python -m pytest tests/llm/test_client.py -v`
Expected: ALL PASS (existing + new tests)

**Step 5: Commit**

```bash
git add wargames/llm/client.py tests/llm/test_client.py
git commit -m "feat(llm): add fallback model retry chain to LLMClient"
```

---

### Task 3: Wire `crawl` CLI command

**Files:**
- Modify: `wargames/cli.py:98-100`
- Test: `tests/test_cli.py`

**Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock


def test_crawl_calls_crawlers(tmp_path):
    """crawl command should invoke NVD and ExploitDB crawlers."""
    mock_nvd = MagicMock()
    mock_nvd.fetch = AsyncMock(return_value=[{"cve_id": "CVE-2024-0001", "source": "nvd"}])
    mock_nvd.store = AsyncMock()

    mock_edb = MagicMock()
    mock_edb.fetch = AsyncMock(return_value=[{"cve_id": "EDB-1234", "source": "exploitdb"}])
    mock_edb.store = AsyncMock()

    mock_db = MagicMock()
    mock_db.init = AsyncMock()
    mock_db.close = AsyncMock()

    with patch("wargames.cli.NVDCrawler", return_value=mock_nvd), \
         patch("wargames.cli.ExploitDBCrawler", return_value=mock_edb), \
         patch("wargames.cli.Database", return_value=mock_db), \
         patch("wargames.cli._default_db_path", return_value=tmp_path / "test.db"):
        from wargames.cli import main
        main(["crawl", "--sources", "nvd,exploitdb"])
        mock_nvd.fetch.assert_called_once()
        mock_edb.fetch.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `cd ~/PROJECTz/war-games && python -m pytest tests/test_cli.py::test_crawl_calls_crawlers -v`
Expected: FAIL — `crawl` is a stub

**Step 3: Write minimal implementation**

In `wargames/cli.py`, replace the crawl TODO block. Add imports at top:

```python
# Add these imports at top of cli.py
from wargames.crawler.cve import NVDCrawler
from wargames.crawler.exploitdb import ExploitDBCrawler
from wargames.output.db import Database


def _default_db_path() -> Path:
    return Path("~/.local/share/wargames/state.db").expanduser()
```

Replace the crawl handler (lines 98-100):

```python
    elif args.command == "crawl":
        sources = [s.strip() for s in args.sources.split(",")]
        db_path = _default_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)

        async def _crawl():
            db = Database(db_path)
            await db.init()
            total = 0
            if "nvd" in sources:
                crawler = NVDCrawler()
                results = await crawler.fetch()
                await crawler.store(db, results)
                print(f"NVD: {len(results)} CVEs")
                total += len(results)
            if "exploitdb" in sources:
                crawler = ExploitDBCrawler()
                results = await crawler.fetch()
                await crawler.store(db, results)
                print(f"ExploitDB: {len(results)} CVEs")
                total += len(results)
            await db.close()
            print(f"Total: {total} CVEs crawled → {db_path}")

        asyncio.run(_crawl())
```

**Step 4: Run test to verify it passes**

Run: `cd ~/PROJECTz/war-games && python -m pytest tests/test_cli.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add wargames/cli.py tests/test_cli.py
git commit -m "feat(cli): wire crawl command to NVD and ExploitDB crawlers"
```

---

### Task 4: Wire `report` CLI command

**Files:**
- Modify: `wargames/cli.py:102-104` (report stub)
- Modify: `wargames/output/db.py` (add `get_round_with_reports` if needed)
- Test: `tests/test_cli.py`

**Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
def test_report_prints_round_summary(tmp_path, capsys):
    """report command should print a formatted round summary."""
    from wargames.models import RoundResult, Phase, MatchOutcome, AttackResult, DefenseResult, Severity

    mock_result = RoundResult(
        round_number=1,
        phase=Phase.PROMPT_INJECTION,
        outcome=MatchOutcome.RED_WIN,
        red_score=12,
        blue_score=3,
        blue_threshold=10,
        red_draft=[],
        blue_draft=[],
        attacks=[AttackResult(turn=1, description="SQL injection", severity=Severity.HIGH, points=5, success=True)],
        defenses=[DefenseResult(turn=1, description="WAF block", blocked=True, points_deducted=3)],
    )

    mock_db = MagicMock()
    mock_db.init = AsyncMock()
    mock_db.get_round = AsyncMock(return_value=mock_result)
    mock_db.close = AsyncMock()

    with patch("wargames.cli.Database", return_value=mock_db), \
         patch("wargames.cli._default_db_path", return_value=tmp_path / "test.db"):
        from wargames.cli import main
        main(["report", "1"])

    output = capsys.readouterr().out
    assert "Round 1" in output
    assert "RED_WIN" in output or "red_win" in output
    assert "SQL injection" in output
```

**Step 2: Run test to verify it fails**

Run: `cd ~/PROJECTz/war-games && python -m pytest tests/test_cli.py::test_report_prints_round_summary -v`
Expected: FAIL — report is a stub

**Step 3: Write minimal implementation**

Replace the report handler in `wargames/cli.py`:

```python
    elif args.command == "report":
        db_path = _default_db_path()

        async def _report():
            db = Database(db_path)
            await db.init()
            try:
                result = await db.get_round(args.round_number)
            except KeyError:
                print(f"Round {args.round_number} not found.")
                await db.close()
                return
            await db.close()

            print(f"═══ Round {result.round_number} ═══")
            print(f"Phase: {result.phase.name}  |  Outcome: {result.outcome.value}")
            print(f"Score: Red {result.red_score} — Blue {result.blue_score} (threshold {result.blue_threshold})")
            print()

            if result.red_draft or result.blue_draft:
                print("── Draft ──")
                for pick in result.red_draft:
                    print(f"  🔴 {pick.resource_name} ({pick.resource_category})")
                for pick in result.blue_draft:
                    print(f"  🔵 {pick.resource_name} ({pick.resource_category})")
                print()

            print("── Attacks ──")
            for a in result.attacks:
                status = "HIT" if a.success else "MISS"
                sev = f" [{a.severity.value}]" if a.severity else ""
                print(f"  T{a.turn}: {status}{sev} +{a.points}pts — {a.description[:80]}")
            print()

            print("── Defenses ──")
            for d in result.defenses:
                status = "BLOCKED" if d.blocked else "MISSED"
                print(f"  T{d.turn}: {status} -{d.points_deducted}pts — {d.description[:80]}")
            print()

            if result.bug_reports:
                print("── Bug Reports ──")
                for b in result.bug_reports:
                    print(f"  [{b.severity.value}] {b.title}")
                print()

            if result.patches:
                print("── Patches ──")
                for p in result.patches:
                    print(f"  {p.title} — fixes: {p.fixes[:60]}")

        asyncio.run(_report())
```

**Step 4: Run test to verify it passes**

Run: `cd ~/PROJECTz/war-games && python -m pytest tests/test_cli.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add wargames/cli.py tests/test_cli.py
git commit -m "feat(cli): wire report command with formatted round summary"
```

---

### Task 5: Wire `export` CLI command

**Files:**
- Modify: `wargames/cli.py:106-108` (export stub)
- Modify: `wargames/output/db.py` (add `get_all_rounds`)
- Test: `tests/test_cli.py`

**Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
import json


def test_export_json(tmp_path, capsys):
    """export --format json should print valid JSON."""
    from wargames.models import RoundResult, Phase, MatchOutcome

    mock_results = [
        RoundResult(
            round_number=1, phase=Phase.PROMPT_INJECTION,
            outcome=MatchOutcome.RED_WIN, red_score=12, blue_score=3,
            blue_threshold=10, red_draft=[], blue_draft=[],
            attacks=[], defenses=[],
        ),
    ]

    mock_db = MagicMock()
    mock_db.init = AsyncMock()
    mock_db.get_all_rounds = AsyncMock(return_value=mock_results)
    mock_db.close = AsyncMock()

    with patch("wargames.cli.Database", return_value=mock_db), \
         patch("wargames.cli._default_db_path", return_value=tmp_path / "test.db"):
        from wargames.cli import main
        main(["export", "--format", "json"])

    output = capsys.readouterr().out
    data = json.loads(output)
    assert len(data["rounds"]) == 1
    assert data["rounds"][0]["outcome"] == "red_win"


def test_export_markdown(tmp_path, capsys):
    """export --format markdown should print a markdown table."""
    from wargames.models import RoundResult, Phase, MatchOutcome

    mock_results = [
        RoundResult(
            round_number=1, phase=Phase.PROMPT_INJECTION,
            outcome=MatchOutcome.RED_WIN, red_score=12, blue_score=3,
            blue_threshold=10, red_draft=[], blue_draft=[],
            attacks=[], defenses=[],
        ),
    ]

    mock_db = MagicMock()
    mock_db.init = AsyncMock()
    mock_db.get_all_rounds = AsyncMock(return_value=mock_results)
    mock_db.close = AsyncMock()

    with patch("wargames.cli.Database", return_value=mock_db), \
         patch("wargames.cli._default_db_path", return_value=tmp_path / "test.db"):
        from wargames.cli import main
        main(["export", "--format", "markdown"])

    output = capsys.readouterr().out
    assert "| Round |" in output
    assert "| 1 |" in output
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/PROJECTz/war-games && python -m pytest tests/test_cli.py::test_export_json -v`
Expected: FAIL — `export` is a stub, `get_all_rounds` doesn't exist

**Step 3a: Add `get_all_rounds` to Database**

In `wargames/output/db.py`, add method to `Database` class:

```python
    async def get_all_rounds(self) -> list[RoundResult]:
        cursor = await self._conn.execute(
            "SELECT round_number FROM rounds ORDER BY round_number"
        )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            results.append(await self.get_round(row["round_number"]))
        return results
```

**Step 3b: Implement export handler in cli.py**

Add `--output` argument to export parser (after `--format`):

```python
    export_p.add_argument("--output", default=None, help="Output file path (default: stdout)")
```

Replace the export handler:

```python
    elif args.command == "export":
        db_path = _default_db_path()

        async def _export():
            db = Database(db_path)
            await db.init()
            results = await db.get_all_rounds()
            await db.close()

            if not results:
                print("No rounds found.")
                return

            if args.format == "json":
                import json
                data = {
                    "rounds": [r.model_dump(mode="json") for r in results],
                    "summary": {
                        "total_rounds": len(results),
                        "red_wins": sum(1 for r in results if r.outcome in (MatchOutcome.RED_WIN, MatchOutcome.RED_AUTO_WIN, MatchOutcome.RED_CRITICAL_WIN)),
                        "blue_wins": sum(1 for r in results if r.outcome in (MatchOutcome.BLUE_WIN, MatchOutcome.BLUE_DECISIVE_WIN)),
                    },
                }
                output = json.dumps(data, indent=2)
            else:
                lines = ["# Season Report", ""]
                lines.append("| Round | Phase | Outcome | Red | Blue |")
                lines.append("|-------|-------|---------|-----|------|")
                for r in results:
                    lines.append(f"| {r.round_number} | {r.phase.name} | {r.outcome.value} | {r.red_score} | {r.blue_score} |")
                lines.append("")
                red_w = sum(1 for r in results if r.outcome in (MatchOutcome.RED_WIN, MatchOutcome.RED_AUTO_WIN, MatchOutcome.RED_CRITICAL_WIN))
                blue_w = sum(1 for r in results if r.outcome in (MatchOutcome.BLUE_WIN, MatchOutcome.BLUE_DECISIVE_WIN))
                lines.append(f"**Red wins:** {red_w}  |  **Blue wins:** {blue_w}  |  **Total:** {len(results)}")
                output = "\n".join(lines)

            if args.output:
                Path(args.output).write_text(output)
                print(f"Exported to {args.output}")
            else:
                print(output)

        asyncio.run(_export())
```

Add `MatchOutcome` import at top of cli.py:

```python
from wargames.models import MatchOutcome
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/PROJECTz/war-games && python -m pytest tests/test_cli.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add wargames/cli.py wargames/output/db.py tests/test_cli.py
git commit -m "feat(cli): wire export command with JSON and markdown output"
```

---

### Task 6: Create fallback-cloud.toml config preset

**Files:**
- Create: `config/fallback-cloud.toml`

**Step 1: No test needed** (config file, validated by existing config parser tests)

**Step 2: Write the config file**

Create `config/fallback-cloud.toml`:

```toml
# Cloud primary (OpenRouter via LiteLLM green) with Ollama local fallback.
# If cloud is down or slow, automatically retries with local qwen3:4b.

[game]
name = "season-fallback"
rounds = 3
turn_limit = 4
score_threshold = 10
phase_advance_score = 7.5

[draft]
picks_per_team = 3
style = "snake"

[teams.red]
name = "Red Team"
model = "http://localhost:4002"
model_name = "openrouter/auto"
fallback_model = "http://localhost:11434"
fallback_model_name = "qwen3:4b"
temperature = 0.8
timeout = 60.0
api_key = "$LITELLM_MASTER_KEY"

[teams.blue]
name = "Blue Team"
model = "http://localhost:4002"
model_name = "openrouter/auto"
fallback_model = "http://localhost:11434"
fallback_model_name = "qwen3:4b"
temperature = 0.4
timeout = 60.0
api_key = "$LITELLM_MASTER_KEY"

[teams.judge]
name = "Judge"
model = "http://localhost:4002"
model_name = "openrouter/auto"
fallback_model = "http://localhost:11434"
fallback_model_name = "qwen3:4b"
temperature = 0.2
timeout = 90.0
api_key = "$LITELLM_MASTER_KEY"

[crawler]
enabled = true
sources = ["nvd", "exploitdb"]
refresh_interval = "24h"

[output.vault]
enabled = true
path = "~/OpenClaw-Vault/WarGames"

[output.database]
path = "~/.local/share/wargames/state.db"
```

**Step 3: Validate it parses**

Run: `cd ~/PROJECTz/war-games && python -c "from wargames.config import load_config; from pathlib import Path; c = load_config(Path('config/fallback-cloud.toml')); print(f'OK: {c.game.name}, fallback={c.teams.red.fallback_model_name}')"`
Expected: `OK: season-fallback, fallback=qwen3:4b`

**Step 4: Commit**

```bash
git add config/fallback-cloud.toml
git commit -m "feat(config): add fallback-cloud preset with cloud+local fallback"
```

---

### Task 7: Run full test suite

**Files:** None (validation only)

**Step 1: Run all tests**

Run: `cd ~/PROJECTz/war-games && python -m pytest -v`
Expected: ALL PASS

**Step 2: Fix any failures**

If tests fail, fix the root cause and re-run. Commit fixes individually.

**Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix: resolve test failures from expansion v2"
```

---

### Task 8: Live end-to-end run

**Files:** None (validation + bug fixing)

**Prerequisites:**
- Ollama running with `qwen3:4b` available (fallback)
- LiteLLM green on port 4002 (primary) OR accept fallback-only for first run

**Step 1: Crawl CVEs**

Run: `cd ~/PROJECTz/war-games && python -m wargames.cli crawl --sources nvd,exploitdb`
Expected: Prints CVE counts, no crashes

**Step 2: Start a game**

Run: `cd ~/PROJECTz/war-games && python -m wargames.cli start --config config/fallback-cloud.toml`
Expected: Game runs 3 rounds, prints logs, completes

**Step 3: Test report command**

Run: `cd ~/PROJECTz/war-games && python -m wargames.cli report 1`
Expected: Formatted round summary

**Step 4: Test export command**

Run: `cd ~/PROJECTz/war-games && python -m wargames.cli export --format json`
Run: `cd ~/PROJECTz/war-games && python -m wargames.cli export --format markdown`
Expected: Valid JSON / markdown output

**Step 5: Fix bugs found during run**

Fix any crashes, bad output, or edge cases. Commit each fix separately.

**Step 6: Final commit**

```bash
git commit -m "fix: resolve issues found during first live run"
```

---

### Summary

| Task | Description | Est. Steps |
|------|-------------|------------|
| 1 | Fallback fields on TeamSettings | 5 |
| 2 | Fallback retry logic in LLMClient | 5 |
| 3 | Wire `crawl` CLI command | 5 |
| 4 | Wire `report` CLI command | 5 |
| 5 | Wire `export` CLI command | 5 |
| 6 | Create fallback-cloud.toml | 4 |
| 7 | Run full test suite | 3 |
| 8 | Live end-to-end run | 6 |

**Total: 8 tasks, ~38 steps**
