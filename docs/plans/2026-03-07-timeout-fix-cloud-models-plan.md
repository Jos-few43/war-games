# Timeout Fix & Cloud Model Support — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the httpx.ReadTimeout crash, harden crawler HTTP calls, and add cloud model config presets via LiteLLM.

**Architecture:** Three independent changes: (1) add ReadTimeout to LLM client retry list, (2) wrap crawler HTTP calls with retry/catch, (3) create new TOML config presets for cloud models.

**Tech Stack:** Python 3.14, httpx, pytest, pytest-asyncio

---

### Task 1: Add ReadTimeout retry to LLM client

**Files:**
- Modify: `wargames/llm/client.py:32`
- Test: `tests/llm/test_client.py`

**Context:** The LLM client retries on `RemoteProtocolError` and `ConnectError` but NOT on `ReadTimeout`. When a local model takes too long, the game crashes. We need to add `ReadTimeout` to the retry list.

**Step 1: Write the failing test**

Add to `tests/llm/test_client.py`:

```python
@pytest.mark.asyncio
async def test_chat_retries_on_read_timeout(team_settings):
    client = LLMClient(team_settings)
    mock_success = AsyncMock()
    mock_success.status_code = 200
    mock_success.json.return_value = {
        "choices": [{"message": {"content": "recovered"}}]
    }
    mock_success.raise_for_status = lambda: None

    import httpx
    with patch.object(
        client._http, "post",
        side_effect=[httpx.ReadTimeout("timeout"), mock_success],
    ):
        result = await client.chat([{"role": "user", "content": "Hi"}])
        assert result == "recovered"
```

**Step 2: Run test to verify it fails**

Run inside wargames-dev container:
```bash
distrobox enter wargames-dev -- bash -c "cd ~/PROJECTz/war-games && python -m pytest tests/llm/test_client.py::test_chat_retries_on_read_timeout -v"
```
Expected: FAIL — `httpx.ReadTimeout` is not caught, so it raises instead of retrying.

**Step 3: Implement the fix**

In `wargames/llm/client.py`, change line 32 from:
```python
            except (httpx.RemoteProtocolError, httpx.ConnectError) as exc:
```
to:
```python
            except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadTimeout) as exc:
```

**Step 4: Run tests to verify they pass**

```bash
distrobox enter wargames-dev -- bash -c "cd ~/PROJECTz/war-games && python -m pytest tests/llm/test_client.py -v"
```
Expected: ALL PASS (4 tests including new one)

**Step 5: Commit**

```bash
cd ~/PROJECTz/war-games
git add wargames/llm/client.py tests/llm/test_client.py
git commit -m "fix(llm): retry on ReadTimeout to survive slow local models"
```

---

### Task 2: Add retry/resilience to NVD crawler

**Files:**
- Modify: `wargames/crawler/cve.py:10-16`
- Test: `tests/crawler/test_crawler.py`

**Context:** The NVD crawler calls `response.raise_for_status()` without any retry or error handling. A network blip crashes the entire game. We need to add retry logic and graceful failure (return empty list instead of crashing).

**Step 1: Write the failing test**

Add to `tests/crawler/test_crawler.py`:

```python
@pytest.mark.asyncio
async def test_nvd_crawler_retries_on_timeout():
    mock_http = AsyncMock()
    import httpx
    mock_success = MagicMock()
    mock_success.status_code = 200
    mock_success.json.return_value = {
        "vulnerabilities": [{
            "cve": {
                "id": "CVE-2024-9999",
                "descriptions": [{"lang": "en", "value": "Test"}],
                "metrics": {},
            }
        }]
    }
    mock_success.raise_for_status = MagicMock()
    mock_http.get.side_effect = [httpx.ReadTimeout("timeout"), mock_success]

    crawler = NVDCrawler(mock_http)
    results = await crawler.fetch(keyword="test", max_results=1)
    assert len(results) == 1
    assert results[0]["cve_id"] == "CVE-2024-9999"

@pytest.mark.asyncio
async def test_nvd_crawler_returns_empty_on_persistent_failure():
    mock_http = AsyncMock()
    import httpx
    mock_http.get.side_effect = httpx.ConnectError("down")

    crawler = NVDCrawler(mock_http)
    results = await crawler.fetch(keyword="test", max_results=1)
    assert results == []
```

**Step 2: Run tests to verify they fail**

```bash
distrobox enter wargames-dev -- bash -c "cd ~/PROJECTz/war-games && python -m pytest tests/crawler/test_crawler.py::test_nvd_crawler_retries_on_timeout tests/crawler/test_crawler.py::test_nvd_crawler_returns_empty_on_persistent_failure -v"
```
Expected: FAIL — no retry logic, raises on timeout.

**Step 3: Implement the fix**

Replace `wargames/crawler/cve.py` `fetch` method:

```python
import asyncio
import httpx

class NVDCrawler:
    """Crawl NIST NVD API for CVE data."""
    BASE_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
    MAX_RETRIES = 3
    RETRY_BACKOFF = 2.0

    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._http = http_client or httpx.AsyncClient(timeout=30.0)

    async def fetch(self, keyword: str = "", max_results: int = 20) -> list[dict]:
        params = {"resultsPerPage": max_results}
        if keyword:
            params["keywordSearch"] = keyword

        last_exc = None
        for attempt in range(self.MAX_RETRIES):
            try:
                response = await self._http.get(self.BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()
                return self._parse(data)
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_BACKOFF * (attempt + 1))
            except httpx.HTTPStatusError:
                return []
        return []

    def _parse(self, data: dict) -> list[dict]:
        results = []
        for vuln in data.get("vulnerabilities", []):
            cve = vuln.get("cve", {})
            cve_id = cve.get("id", "")
            desc = ""
            for d in cve.get("descriptions", []):
                if d.get("lang") == "en":
                    desc = d.get("value", "")
                    break

            severity = "unknown"
            metrics = cve.get("metrics", {})
            for metric_key in ["cvssMetricV31", "cvssMetricV30", "cvssMetricV2"]:
                metric_list = metrics.get(metric_key, [])
                if metric_list:
                    base_severity = metric_list[0].get("cvssData", {}).get("baseSeverity", "")
                    if base_severity:
                        severity = base_severity.lower()
                    break

            results.append({
                "cve_id": cve_id,
                "source": "nvd",
                "severity": severity,
                "domain": "code-vuln",
                "description": desc,
                "exploit_code": "",
                "fix_hint": "",
            })
        return results

    async def store(self, db, results: list[dict]):
        for r in results:
            await db.save_cve(r)
```

**Step 4: Run tests**

```bash
distrobox enter wargames-dev -- bash -c "cd ~/PROJECTz/war-games && python -m pytest tests/crawler/test_crawler.py -v"
```
Expected: ALL PASS (5 tests)

**Step 5: Commit**

```bash
cd ~/PROJECTz/war-games
git add wargames/crawler/cve.py tests/crawler/test_crawler.py
git commit -m "fix(crawler): add retry and graceful failure to NVD crawler"
```

---

### Task 3: Add retry/resilience to ExploitDB crawler

**Files:**
- Modify: `wargames/crawler/exploitdb.py:12-14`
- Test: `tests/crawler/test_crawler.py`

**Context:** Same pattern as Task 2 but for the ExploitDB CSV crawler.

**Step 1: Write the failing test**

Add to `tests/crawler/test_crawler.py`:

```python
@pytest.mark.asyncio
async def test_exploitdb_crawler_retries_on_timeout():
    mock_http = AsyncMock()
    import httpx
    mock_success = MagicMock()
    mock_success.status_code = 200
    mock_success.text = (
        "id,file,description,date_published,author,platform,type,port\n"
        "99999,exploits/test.txt,Retry Test,2024-01-01,tester,linux,local,0\n"
    )
    mock_success.raise_for_status = MagicMock()
    mock_http.get.side_effect = [httpx.ReadTimeout("timeout"), mock_success]

    crawler = ExploitDBCrawler(mock_http)
    results = await crawler.fetch(max_results=1)
    assert len(results) == 1
    assert results[0]["cve_id"] == "EDB-99999"

@pytest.mark.asyncio
async def test_exploitdb_crawler_returns_empty_on_persistent_failure():
    mock_http = AsyncMock()
    import httpx
    mock_http.get.side_effect = httpx.ConnectError("down")

    crawler = ExploitDBCrawler(mock_http)
    results = await crawler.fetch(max_results=1)
    assert results == []
```

**Step 2: Run tests to verify they fail**

```bash
distrobox enter wargames-dev -- bash -c "cd ~/PROJECTz/war-games && python -m pytest tests/crawler/test_crawler.py::test_exploitdb_crawler_retries_on_timeout tests/crawler/test_crawler.py::test_exploitdb_crawler_returns_empty_on_persistent_failure -v"
```
Expected: FAIL

**Step 3: Implement the fix**

Replace `wargames/crawler/exploitdb.py`:

```python
import asyncio
import csv
import io
import httpx

class ExploitDBCrawler:
    """Crawl ExploitDB via GitHub CSV mirror."""
    CSV_URL = "https://gitlab.com/exploit-database/exploitdb/-/raw/main/files_exploits.csv"
    MAX_RETRIES = 3
    RETRY_BACKOFF = 2.0

    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._http = http_client or httpx.AsyncClient(timeout=30.0)

    async def fetch(self, max_results: int = 20) -> list[dict]:
        last_exc = None
        for attempt in range(self.MAX_RETRIES):
            try:
                response = await self._http.get(self.CSV_URL)
                response.raise_for_status()
                return self._parse(response.text, max_results)
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_BACKOFF * (attempt + 1))
            except httpx.HTTPStatusError:
                return []
        return []

    def _parse(self, text: str, max_results: int) -> list[dict]:
        reader = csv.DictReader(io.StringIO(text))
        results = []
        for i, row in enumerate(reader):
            if i >= max_results:
                break
            results.append({
                "cve_id": f"EDB-{row.get('id', '')}",
                "source": "exploitdb",
                "severity": "unknown",
                "domain": "code-vuln",
                "description": row.get("description", ""),
                "exploit_code": "",
                "fix_hint": "",
            })
        return results

    async def store(self, db, results: list[dict]):
        for r in results:
            await db.save_cve(r)
```

**Step 4: Run tests**

```bash
distrobox enter wargames-dev -- bash -c "cd ~/PROJECTz/war-games && python -m pytest tests/crawler/test_crawler.py -v"
```
Expected: ALL PASS (7 tests)

**Step 5: Commit**

```bash
cd ~/PROJECTz/war-games
git add wargames/crawler/exploitdb.py tests/crawler/test_crawler.py
git commit -m "fix(crawler): add retry and graceful failure to ExploitDB crawler"
```

---

### Task 4: Create cloud model config presets

**Files:**
- Create: `config/cloud-judge.toml`
- Create: `config/full-cloud.toml`

**Context:** Create two new config presets that route through LiteLLM green (port 4002) for cloud model access. Red/blue teams can use local models via Ollama (port 11434) or LiteLLM blue (port 4000). Judge benefits most from a strong cloud model.

**Step 1: Create cloud-judge config**

Create `config/cloud-judge.toml`:

```toml
# Local teams + cloud judge via LiteLLM
# Red/Blue use Ollama, Judge uses Claude via LiteLLM green (port 4002)

[game]
name = "season-cloud-judge"
rounds = 10
turn_limit = 8
score_threshold = 10
phase_advance_score = 7.5

[draft]
picks_per_team = 5
style = "snake"

[teams.red]
name = "Red Team"
model = "http://localhost:11434/v1"
model_name = "qwen3:8b"
temperature = 0.8

[teams.blue]
name = "Blue Team"
model = "http://localhost:11434/v1"
model_name = "qwen3:8b"
temperature = 0.4

[teams.judge]
name = "Judge"
model = "http://localhost:4002/v1"
model_name = "claude-sonnet-4-5"
temperature = 0.2

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

**Step 2: Create full-cloud config**

Create `config/full-cloud.toml`:

```toml
# All teams use cloud models via LiteLLM green (port 4002)
# Maximum quality, higher API cost

[game]
name = "season-full-cloud"
rounds = 10
turn_limit = 8
score_threshold = 10
phase_advance_score = 7.5

[draft]
picks_per_team = 5
style = "snake"

[teams.red]
name = "Red Team"
model = "http://localhost:4002/v1"
model_name = "claude-sonnet-4-5"
temperature = 0.8

[teams.blue]
name = "Blue Team"
model = "http://localhost:4002/v1"
model_name = "claude-haiku-4-5"
temperature = 0.4

[teams.judge]
name = "Judge"
model = "http://localhost:4002/v1"
model_name = "claude-sonnet-4-5"
temperature = 0.2

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

**Step 3: Verify configs parse correctly**

```bash
distrobox enter wargames-dev -- bash -c "cd ~/PROJECTz/war-games && python -c \"
from wargames.config import load_config
c1 = load_config('config/cloud-judge.toml')
print(f'cloud-judge: red={c1.teams.red.model_name} judge={c1.teams.judge.model_name}')
c2 = load_config('config/full-cloud.toml')
print(f'full-cloud: red={c2.teams.red.model_name} blue={c2.teams.blue.model_name} judge={c2.teams.judge.model_name}')
print('Both configs parse OK')
\""
```
Expected: Both parse without error, correct model names shown.

**Step 4: Commit**

```bash
cd ~/PROJECTz/war-games
git add config/cloud-judge.toml config/full-cloud.toml
git commit -m "feat(config): add cloud-judge and full-cloud model presets"
```

---

### Task 5: Run full test suite and verify

**Files:** None (verification only)

**Step 1: Run all tests**

```bash
distrobox enter wargames-dev -- bash -c "cd ~/PROJECTz/war-games && python -m pytest tests/ -v"
```
Expected: ALL PASS (77+ tests including new ones)

**Step 2: Live smoke test with test-local config**

Start resmgr daemon, then run a 1-round game to verify the timeout fix works end-to-end:

```bash
# Terminal 1: Start resmgr
distrobox enter wargames-dev -- bash -c "cd ~/PROJECTz/resmgr && python -m resmgr.cli start --config config.yaml"

# Terminal 2: Run game in slice
systemd-run --user --slice=simulation-red.slice --unit=wargames-smoke \
    -- distrobox enter wargames-dev -- bash -c \
    "cd ~/PROJECTz/war-games && python -m wargames.cli start --config config/test-local.toml"

# Monitor
journalctl --user -u wargames-smoke -f
```
Expected: Game completes 1 round without crashing on timeout.

**Step 3: Push changes**

```bash
cd ~/PROJECTz/war-games
git push origin feature/expansion-v1
```
