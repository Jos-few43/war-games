# Expansion v3: Tournament + Gameplay + Observability — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add MVP tournament system (ELO ratings, leaderboards), richer gameplay (sandbox mode, team loadouts), and observability (token tracking, cost metrics, stats command).

**Architecture:** Three independent pillars built sequentially. Each adds new modules, DB tables, and CLI commands without modifying existing gameplay logic. Pillar 1 = Tournament (ELO + leaderboard + seasons). Pillar 2 = Gameplay (loadouts + sandbox). Pillar 3 = Observability (token tracking + costs + TUI widget + stats CLI).

**Tech Stack:** Python 3.14, Pydantic v2, aiosqlite, httpx, Textual (TUI), tomli, pytest + pytest-asyncio

---

## Context for the Implementer

This is the `war-games` project at `~/PROJECTz/war-games/`. It's an LLM red-team vs blue-team competition engine. Key architecture:

- **Config:** TOML files in `config/`, loaded by `wargames/config.py` → `GameConfig` (Pydantic model in `wargames/models.py`)
- **Engine:** `wargames/engine/game.py` (`GameEngine`) orchestrates seasons, calls `RoundEngine` per round
- **LLM:** `wargames/llm/client.py` (`LLMClient`) — httpx async client with primary + fallback retry chain
- **DB:** `wargames/output/db.py` (`Database`) — aiosqlite, 8 tables, stores rounds/attacks/defenses/strategies
- **CLI:** `wargames/cli.py` — argparse, 9 commands (start, attach, status, pause, resume, crawl, report, export)
- **TUI:** `wargames/tui/app.py` (`WarGamesTUI`) — Textual app with TeamPanel, LiveFeed, SeasonStats, RecentReports
- **Draft:** `wargames/engine/draft.py` — `DraftPool` (resource inventory) + `DraftEngine` (snake/linear draft)
- **Tests:** `tests/` with pytest + pytest-asyncio, mock LLM responses with `unittest.mock`

Run tests with: `cd ~/PROJECTz/war-games && python -m pytest tests/ -v`

Design doc: `docs/plans/2026-03-07-expansion-v3-design.md`

---

## PILLAR 1: TOURNAMENT SYSTEM

### Task 1: ELO Rating Engine

**Files:**
- Create: `wargames/engine/elo.py`
- Create: `tests/engine/test_elo.py`

**Step 1: Write the failing tests**

Create `tests/engine/test_elo.py`:

```python
import pytest
from wargames.engine.elo import calculate_elo, ModelRating


def test_calculate_elo_winner_gains_points():
    new_winner, new_loser = calculate_elo(1500.0, 1500.0)
    assert new_winner > 1500.0
    assert new_loser < 1500.0


def test_calculate_elo_symmetric_at_equal_ratings():
    new_winner, new_loser = calculate_elo(1500.0, 1500.0)
    gain = new_winner - 1500.0
    loss = 1500.0 - new_loser
    assert abs(gain - loss) < 0.01


def test_calculate_elo_underdog_gains_more():
    """Lower-rated winner gains more than higher-rated winner would."""
    gain_underdog, _ = calculate_elo(1300.0, 1700.0)
    gain_favorite, _ = calculate_elo(1700.0, 1300.0)
    assert (gain_underdog - 1300.0) > (gain_favorite - 1700.0)


def test_calculate_elo_draw():
    new_a, new_b = calculate_elo(1500.0, 1500.0, draw=True)
    # Equal ratings + draw = no change
    assert abs(new_a - 1500.0) < 0.01
    assert abs(new_b - 1500.0) < 0.01


def test_calculate_elo_draw_favors_underdog():
    new_low, new_high = calculate_elo(1300.0, 1700.0, draw=True)
    assert new_low > 1300.0  # underdog gains from draw
    assert new_high < 1700.0  # favorite loses from draw


def test_model_rating_defaults():
    r = ModelRating(model_name="test-model")
    assert r.rating == 1500.0
    assert r.wins == 0
    assert r.losses == 0
    assert r.draws == 0


def test_model_rating_record_win():
    r = ModelRating(model_name="test")
    r.record_win(new_rating=1516.0)
    assert r.wins == 1
    assert r.rating == 1516.0


def test_model_rating_record_loss():
    r = ModelRating(model_name="test")
    r.record_loss(new_rating=1484.0)
    assert r.losses == 1
    assert r.rating == 1484.0


def test_model_rating_record_draw():
    r = ModelRating(model_name="test")
    r.record_draw(new_rating=1500.0)
    assert r.draws == 1
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/engine/test_elo.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wargames.engine.elo'`

**Step 3: Write minimal implementation**

Create `wargames/engine/elo.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

K_FACTOR = 32
DEFAULT_RATING = 1500.0


def _expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def calculate_elo(
    winner_rating: float, loser_rating: float, *, draw: bool = False,
) -> tuple[float, float]:
    """Calculate new ELO ratings after a match.

    Returns (new_rating_a, new_rating_b).
    If draw=True, both players are treated as having scored 0.5.
    If draw=False, first player is the winner (score=1) and second is loser (score=0).
    """
    expected_a = _expected_score(winner_rating, loser_rating)
    expected_b = 1.0 - expected_a

    if draw:
        score_a, score_b = 0.5, 0.5
    else:
        score_a, score_b = 1.0, 0.0

    new_a = winner_rating + K_FACTOR * (score_a - expected_a)
    new_b = loser_rating + K_FACTOR * (score_b - expected_b)
    return new_a, new_b


@dataclass
class ModelRating:
    model_name: str
    rating: float = DEFAULT_RATING
    wins: int = 0
    losses: int = 0
    draws: int = 0
    last_played: str = ""

    def record_win(self, new_rating: float) -> None:
        self.rating = new_rating
        self.wins += 1
        self.last_played = datetime.now(timezone.utc).isoformat()

    def record_loss(self, new_rating: float) -> None:
        self.rating = new_rating
        self.losses += 1
        self.last_played = datetime.now(timezone.utc).isoformat()

    def record_draw(self, new_rating: float) -> None:
        self.rating = new_rating
        self.draws += 1
        self.last_played = datetime.now(timezone.utc).isoformat()
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/engine/test_elo.py -v`
Expected: All 9 tests PASS

**Step 5: Commit**

```bash
git add wargames/engine/elo.py tests/engine/test_elo.py
git commit -m "feat(engine): add ELO rating calculation engine"
```

---

### Task 2: Tournament DB Tables + Methods

**Files:**
- Modify: `wargames/output/db.py`
- Create: `tests/output/test_tournament_db.py`

**Step 1: Write the failing tests**

Create `tests/output/test_tournament_db.py`:

```python
import pytest
import tempfile
from pathlib import Path
from wargames.output.db import Database


@pytest.fixture
async def db():
    with tempfile.TemporaryDirectory() as tmp:
        database = Database(Path(tmp) / "test.db")
        await database.init()
        yield database
        await database.close()


@pytest.mark.asyncio
async def test_model_ratings_table_exists(db):
    tables = await db.list_tables()
    assert "model_ratings" in tables


@pytest.mark.asyncio
async def test_seasons_table_exists(db):
    tables = await db.list_tables()
    assert "seasons" in tables


@pytest.mark.asyncio
async def test_token_usage_table_exists(db):
    tables = await db.list_tables()
    assert "token_usage" in tables


@pytest.mark.asyncio
async def test_save_and_get_model_rating(db):
    await db.save_model_rating("llama-3-70b", 1516.0, wins=1, losses=0, draws=0)
    rating = await db.get_model_rating("llama-3-70b")
    assert rating is not None
    assert rating["model_name"] == "llama-3-70b"
    assert rating["rating"] == 1516.0
    assert rating["wins"] == 1


@pytest.mark.asyncio
async def test_get_model_rating_not_found(db):
    rating = await db.get_model_rating("nonexistent")
    assert rating is None


@pytest.mark.asyncio
async def test_get_all_ratings_sorted(db):
    await db.save_model_rating("model-a", 1600.0, wins=3, losses=1, draws=0)
    await db.save_model_rating("model-b", 1400.0, wins=1, losses=3, draws=0)
    await db.save_model_rating("model-c", 1500.0, wins=2, losses=2, draws=0)
    ratings = await db.get_all_ratings()
    assert len(ratings) == 3
    assert ratings[0]["model_name"] == "model-a"  # highest first
    assert ratings[2]["model_name"] == "model-b"  # lowest last


@pytest.mark.asyncio
async def test_save_and_get_season(db):
    await db.save_season("s1", config_name="test.toml", started_at="2026-03-07T00:00:00Z")
    season = await db.get_season("s1")
    assert season is not None
    assert season["config_name"] == "test.toml"
    assert season["ended_at"] is None


@pytest.mark.asyncio
async def test_end_season(db):
    await db.save_season("s1", config_name="test.toml", started_at="2026-03-07T00:00:00Z")
    await db.end_season("s1", ended_at="2026-03-07T01:00:00Z", winner="blue")
    season = await db.get_season("s1")
    assert season["ended_at"] == "2026-03-07T01:00:00Z"
    assert season["winner"] == "blue"


@pytest.mark.asyncio
async def test_save_and_get_token_usage(db):
    await db.save_token_usage(
        round_number=1, team="red", prompt_tokens=100,
        completion_tokens=50, model_used="llama-3-70b", cost=0.0885,
    )
    usage = await db.get_token_usage()
    assert len(usage) == 1
    assert usage[0]["prompt_tokens"] == 100
    assert usage[0]["model_used"] == "llama-3-70b"


@pytest.mark.asyncio
async def test_get_token_usage_totals(db):
    await db.save_token_usage(1, "red", 100, 50, "llama-3-70b", 0.05)
    await db.save_token_usage(1, "blue", 200, 80, "llama-3-70b", 0.10)
    await db.save_token_usage(2, "red", 150, 60, "qwen3:4b", 0.0)
    totals = await db.get_token_totals()
    assert totals["total_prompt_tokens"] == 450
    assert totals["total_completion_tokens"] == 190
    assert abs(totals["total_cost"] - 0.15) < 0.001
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/output/test_tournament_db.py -v`
Expected: FAIL with `AttributeError: 'Database' object has no attribute 'save_model_rating'`

**Step 3: Write minimal implementation**

Add to `wargames/output/db.py` — three new CREATE TABLE statements and six new methods.

After the existing `CREATE_PATCHES` constant (line ~123), add:

```python
CREATE_MODEL_RATINGS = """
CREATE TABLE IF NOT EXISTS model_ratings (
    model_name  TEXT PRIMARY KEY,
    rating      REAL DEFAULT 1500.0,
    wins        INTEGER DEFAULT 0,
    losses      INTEGER DEFAULT 0,
    draws       INTEGER DEFAULT 0,
    last_played TEXT
)
"""

CREATE_SEASONS = """
CREATE TABLE IF NOT EXISTS seasons (
    season_id   TEXT PRIMARY KEY,
    config_name TEXT,
    started_at  TEXT,
    ended_at    TEXT,
    winner      TEXT
)
"""

CREATE_TOKEN_USAGE = """
CREATE TABLE IF NOT EXISTS token_usage (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    round_number      INTEGER,
    team              TEXT,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    model_used        TEXT,
    cost              REAL
)
"""
```

Add these three to the `ALL_TABLES` list:

```python
ALL_TABLES = [
    CREATE_ROUNDS,
    CREATE_ATTACKS,
    CREATE_DEFENSES,
    CREATE_DRAFT_PICKS,
    CREATE_CRAWLED_CVES,
    CREATE_GAME_STATE,
    CREATE_STRATEGIES,
    CREATE_BUG_REPORTS,
    CREATE_PATCHES,
    CREATE_MODEL_RATINGS,
    CREATE_SEASONS,
    CREATE_TOKEN_USAGE,
]
```

Add these methods to the `Database` class (after `save_cve`):

```python
    # --- Model Ratings ---

    async def save_model_rating(
        self, model_name: str, rating: float,
        wins: int = 0, losses: int = 0, draws: int = 0,
    ) -> None:
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO model_ratings
                (model_name, rating, wins, losses, draws, last_played)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            """,
            (model_name, rating, wins, losses, draws),
        )
        await self._conn.commit()

    async def get_model_rating(self, model_name: str) -> dict | None:
        cursor = await self._conn.execute(
            "SELECT * FROM model_ratings WHERE model_name = ?", (model_name,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_all_ratings(self) -> list[dict]:
        cursor = await self._conn.execute(
            "SELECT * FROM model_ratings ORDER BY rating DESC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # --- Seasons ---

    async def save_season(
        self, season_id: str, config_name: str, started_at: str,
    ) -> None:
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO seasons
                (season_id, config_name, started_at)
            VALUES (?, ?, ?)
            """,
            (season_id, config_name, started_at),
        )
        await self._conn.commit()

    async def get_season(self, season_id: str) -> dict | None:
        cursor = await self._conn.execute(
            "SELECT * FROM seasons WHERE season_id = ?", (season_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def end_season(
        self, season_id: str, ended_at: str, winner: str,
    ) -> None:
        await self._conn.execute(
            "UPDATE seasons SET ended_at = ?, winner = ? WHERE season_id = ?",
            (ended_at, winner, season_id),
        )
        await self._conn.commit()

    # --- Token Usage ---

    async def save_token_usage(
        self, round_number: int, team: str, prompt_tokens: int,
        completion_tokens: int, model_used: str, cost: float,
    ) -> None:
        await self._conn.execute(
            """
            INSERT INTO token_usage
                (round_number, team, prompt_tokens, completion_tokens, model_used, cost)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (round_number, team, prompt_tokens, completion_tokens, model_used, cost),
        )
        await self._conn.commit()

    async def get_token_usage(self) -> list[dict]:
        cursor = await self._conn.execute(
            "SELECT * FROM token_usage ORDER BY id"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_token_totals(self) -> dict:
        cursor = await self._conn.execute(
            """
            SELECT
                COALESCE(SUM(prompt_tokens), 0) AS total_prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS total_completion_tokens,
                COALESCE(SUM(cost), 0.0) AS total_cost
            FROM token_usage
            """
        )
        row = await cursor.fetchone()
        return dict(row)
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/output/test_tournament_db.py -v`
Expected: All 10 tests PASS

Then verify existing tests still pass:

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add wargames/output/db.py tests/output/test_tournament_db.py
git commit -m "feat(db): add model_ratings, seasons, and token_usage tables"
```

---

### Task 3: Ladder CLI Command + ELO Integration in GameEngine

**Files:**
- Modify: `wargames/cli.py`
- Modify: `wargames/engine/game.py`
- Create: `tests/test_ladder_cli.py`

**Step 1: Write the failing tests**

Create `tests/test_ladder_cli.py`:

```python
import pytest
from wargames.cli import parse_args


def test_parse_ladder_command():
    args = parse_args(["ladder"])
    assert args.command == "ladder"
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ladder_cli.py -v`
Expected: FAIL with `SystemExit` (argparse doesn't know "ladder" yet)

**Step 3: Write minimal implementation**

In `wargames/cli.py`, add the `ladder` subcommand to `parse_args()` (after the `export` parser, around line 43):

```python
    # ladder
    sub.add_parser("ladder", help="Show model ELO leaderboard")
```

Add the `ladder` command handler in the `main()` function (after the `export` elif block, before `if __name__`):

```python
    elif args.command == "ladder":
        db_path = _default_db_path()

        async def _ladder():
            db = Database(db_path)
            await db.init()
            ratings = await db.get_all_ratings()
            await db.close()

            if not ratings:
                print("No ratings yet. Run a season first.")
                return

            print(f"{'Rank':<6}{'Model':<30}{'Rating':<10}{'W':<5}{'L':<5}{'D':<5}{'Last Played'}")
            print("-" * 66)
            for i, r in enumerate(ratings, 1):
                print(
                    f"{i:<6}{r['model_name']:<30}{r['rating']:<10.1f}"
                    f"{r['wins']:<5}{r['losses']:<5}{r['draws']:<5}"
                    f"{r['last_played'] or 'never'}"
                )

        asyncio.run(_ladder())
```

In `wargames/engine/game.py`, add ELO updates after each round. Add the import at the top:

```python
from wargames.engine.elo import calculate_elo
```

Inside the `run()` method, after the strategy extraction block (after `await update_win_rates(...)` around line 119), add:

```python
            # Update ELO ratings
            red_model = self.config.teams.red.model_name
            blue_model = self.config.teams.blue.model_name
            try:
                red_row = await self.db.get_model_rating(red_model)
                blue_row = await self.db.get_model_rating(blue_model)
                red_rating = red_row["rating"] if red_row else 1500.0
                blue_rating = blue_row["rating"] if blue_row else 1500.0
                red_wins_count = red_row["wins"] if red_row else 0
                red_losses_count = red_row["losses"] if red_row else 0
                red_draws_count = red_row["draws"] if red_row else 0
                blue_wins_count = blue_row["wins"] if blue_row else 0
                blue_losses_count = blue_row["losses"] if blue_row else 0
                blue_draws_count = blue_row["draws"] if blue_row else 0

                is_draw = result.outcome == MatchOutcome.TIMEOUT
                if is_draw:
                    new_red, new_blue = calculate_elo(red_rating, blue_rating, draw=True)
                    red_draws_count += 1
                    blue_draws_count += 1
                elif won_red:
                    new_red, new_blue = calculate_elo(red_rating, blue_rating)
                    red_wins_count += 1
                    blue_losses_count += 1
                else:
                    new_blue, new_red = calculate_elo(blue_rating, red_rating)
                    blue_wins_count += 1
                    red_losses_count += 1

                await self.db.save_model_rating(red_model, new_red, red_wins_count, red_losses_count, red_draws_count)
                await self.db.save_model_rating(blue_model, new_blue, blue_wins_count, blue_losses_count, blue_draws_count)
            except Exception as exc:
                logger.warning("ELO update failed for round %d: %s", round_num, exc)
```

Also add season lifecycle. In `init()`, after DB init (around line 42), add:

```python
        from datetime import datetime, timezone
        import uuid
        self._season_id = str(uuid.uuid4())[:8]
        await self.db.save_season(
            self._season_id,
            config_name=self.config.game.name,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
```

In `cleanup()`, before closing DB:

```python
        if self.db and hasattr(self, '_season_id'):
            from datetime import datetime, timezone
            # Determine season winner from DB stats
            stats = await self.db.get_season_stats()
            red_w = stats.get("red_wins", 0)
            blue_w = stats.get("blue_wins", 0)
            winner = "red" if red_w > blue_w else "blue" if blue_w > red_w else "draw"
            await self.db.end_season(
                self._season_id,
                ended_at=datetime.now(timezone.utc).isoformat(),
                winner=winner,
            )
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ladder_cli.py tests/ -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add wargames/cli.py wargames/engine/game.py tests/test_ladder_cli.py
git commit -m "feat(tournament): add ladder CLI command and ELO integration in GameEngine"
```

---

## PILLAR 2: GAMEPLAY

### Task 4: Team Loadouts

**Files:**
- Create: `wargames/engine/loadouts.py`
- Create: `tests/engine/test_loadouts.py`
- Modify: `wargames/models.py` (add loadout fields to `TeamSettings`)
- Modify: `wargames/engine/draft.py` (loadout support in `DraftEngine`)

**Step 1: Write the failing tests**

Create `tests/engine/test_loadouts.py`:

```python
import pytest
from wargames.engine.loadouts import PRESETS, resolve_loadout
from wargames.engine.draft import DraftPool, DraftPick


def test_presets_has_four_entries():
    assert len(PRESETS) == 4
    assert "aggressive" in PRESETS
    assert "defensive" in PRESETS
    assert "balanced" in PRESETS
    assert "recon" in PRESETS


def test_all_preset_resources_exist_in_default_pool():
    pool = DraftPool.default()
    resource_names = {r.name for r in pool.resources}
    for preset_name, resources in PRESETS.items():
        for resource in resources:
            assert resource in resource_names, f"{resource} from preset '{preset_name}' not in default pool"


def test_resolve_loadout_named_preset():
    picks = resolve_loadout("red", loadout="aggressive")
    assert len(picks) == 4
    assert all(p.team == "red" for p in picks)
    assert picks[0].resource_name == "fuzzer"


def test_resolve_loadout_custom_list():
    picks = resolve_loadout("blue", loadout_custom=["waf_rules", "rate_limiter"])
    assert len(picks) == 2
    assert picks[0].resource_name == "waf_rules"
    assert picks[1].resource_name == "rate_limiter"


def test_resolve_loadout_custom_overrides_named():
    picks = resolve_loadout("red", loadout="aggressive", loadout_custom=["waf_rules"])
    assert len(picks) == 1
    assert picks[0].resource_name == "waf_rules"


def test_resolve_loadout_none_returns_empty():
    picks = resolve_loadout("red")
    assert picks == []


def test_resolve_loadout_unknown_preset_returns_empty():
    picks = resolve_loadout("red", loadout="nonexistent")
    assert picks == []
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/engine/test_loadouts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wargames.engine.loadouts'`

**Step 3: Write minimal implementation**

Create `wargames/engine/loadouts.py`:

```python
from __future__ import annotations

from wargames.models import DraftPick


PRESETS: dict[str, list[str]] = {
    "aggressive": ["fuzzer", "sqli_kit", "prompt_injector", "priv_esc_toolkit"],
    "defensive": ["waf_rules", "rate_limiter", "input_sanitizer", "sandboxing"],
    "balanced": ["fuzzer", "waf_rules", "port_scanner", "input_sanitizer"],
    "recon": ["port_scanner", "code_analyzer", "network_mapper", "cve_database"],
}


def resolve_loadout(
    team: str,
    loadout: str = "",
    loadout_custom: list[str] | None = None,
) -> list[DraftPick]:
    """Resolve a team's loadout into draft picks.

    Custom loadout takes priority over named preset.
    Returns empty list if no loadout configured (normal draft).
    """
    if loadout_custom:
        resource_names = loadout_custom
    elif loadout and loadout in PRESETS:
        resource_names = PRESETS[loadout]
    else:
        return []

    return [
        DraftPick(
            round=0,
            team=team,
            resource_name=name,
            resource_category="loadout",
        )
        for name in resource_names
    ]
```

Now add loadout fields to `TeamSettings` in `wargames/models.py`. After the `fallback_api_key` field (line 67), add:

```python
    loadout: str = Field(default="", description="Named loadout preset (aggressive/defensive/balanced/recon)")
    loadout_custom: list[str] = Field(default_factory=list, description="Custom list of resource names")
```

Now modify `DraftEngine.run()` in `wargames/engine/draft.py` to check for loadouts. Add import at top:

```python
from wargames.engine.loadouts import resolve_loadout
```

Modify the `run()` method signature to accept optional team settings, and add loadout check at the beginning of `run()`:

Replace the `run()` method (lines 96-150) with:

```python
    async def run(
        self,
        pool: DraftPool,
        red_llm,
        blue_llm,
        red_settings=None,
        blue_settings=None,
    ) -> tuple[list[DraftPick], list[DraftPick]]:
        # Check for loadout overrides
        if red_settings:
            red_loadout = resolve_loadout(
                "red", loadout=red_settings.loadout,
                loadout_custom=red_settings.loadout_custom if red_settings.loadout_custom else None,
            )
        else:
            red_loadout = []

        if blue_settings:
            blue_loadout = resolve_loadout(
                "blue", loadout=blue_settings.loadout,
                loadout_custom=blue_settings.loadout_custom if blue_settings.loadout_custom else None,
            )
        else:
            blue_loadout = []

        # If both teams have loadouts, skip the LLM draft entirely
        if red_loadout and blue_loadout:
            return red_loadout, blue_loadout

        # If only one team has a loadout, the other drafts normally
        red_picks: list[DraftPick] = red_loadout if red_loadout else []
        blue_picks: list[DraftPick] = blue_loadout if blue_loadout else []

        if red_loadout and not blue_loadout:
            # Only blue drafts
            for _ in range(self.picks_per_team):
                available = pool.available()
                available_names = [r.name for r in available]
                chosen = await blue_llm.chat([{"role": "user", "content":
                    f"You are the blue team. Choose one resource.\nAvailable: {', '.join(available_names)}\nReply with only the resource name."}])
                chosen = chosen.strip()
                if chosen not in available_names:
                    chosen = available_names[0]
                resource = pool.pick(chosen)
                blue_picks.append(DraftPick(round=0, team="blue", resource_name=resource.name, resource_category=resource.category))
            return red_picks, blue_picks

        if blue_loadout and not red_loadout:
            # Only red drafts
            for _ in range(self.picks_per_team):
                available = pool.available()
                available_names = [r.name for r in available]
                chosen = await red_llm.chat([{"role": "user", "content":
                    f"You are the red team. Choose one resource.\nAvailable: {', '.join(available_names)}\nReply with only the resource name."}])
                chosen = chosen.strip()
                if chosen not in available_names:
                    chosen = available_names[0]
                resource = pool.pick(chosen)
                red_picks.append(DraftPick(round=0, team="red", resource_name=resource.name, resource_category=resource.category))
            return red_picks, blue_picks

        # Normal draft — no loadouts
        round_num = 1
        for team in self.draft_order():
            llm = red_llm if team == "red" else blue_llm
            available = pool.available()
            available_names = [r.name for r in available]

            prompt = (
                f"You are the {team} team. Choose one resource to draft.\n"
                f"Available resources: {', '.join(available_names)}\n"
                "Reply with only the resource name, nothing else."
            )

            chosen = await llm.chat([{"role": "user", "content": prompt}])
            chosen = chosen.strip()

            if chosen not in available_names:
                chosen = await llm.chat([{"role": "user", "content": prompt}])
                chosen = chosen.strip()
                if chosen not in available_names:
                    chosen = available_names[0]

            resource = pool.pick(chosen)
            pick = DraftPick(
                round=round_num, team=team,
                resource_name=resource.name, resource_category=resource.category,
            )

            if team == "red":
                red_picks.append(pick)
            else:
                blue_picks.append(pick)

            round_num += 1

        return red_picks, blue_picks
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/engine/test_loadouts.py tests/engine/test_draft.py tests/ -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add wargames/engine/loadouts.py wargames/models.py wargames/engine/draft.py tests/engine/test_loadouts.py
git commit -m "feat(gameplay): add team loadout presets with draft integration"
```

---

### Task 5: Sandbox Mode

**Files:**
- Create: `wargames/engine/sandbox.py`
- Create: `tests/engine/test_sandbox.py`
- Modify: `wargames/cli.py` (add `sandbox` command)

**Step 1: Write the failing tests**

Create `tests/engine/test_sandbox.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from wargames.engine.sandbox import SandboxRunner
from wargames.models import GameConfig, Phase


@pytest.fixture
def mock_config():
    """Minimal GameConfig for sandbox testing."""
    from wargames.models import (
        GameSettings, DraftSettings, TeamSettings, TeamsSettings,
        CrawlerSettings,
    )
    return GameConfig(
        game=GameSettings(name="sandbox-test", rounds=1, turn_limit=4,
                         score_threshold=10, phase_advance_score=7.5),
        draft=DraftSettings(picks_per_team=2, style="snake"),
        teams=TeamsSettings(
            red=TeamSettings(name="Red", model="http://localhost:4000",
                           model_name="test", temperature=0.7),
            blue=TeamSettings(name="Blue", model="http://localhost:4000",
                            model_name="test", temperature=0.5),
            judge=TeamSettings(name="Judge", model="http://localhost:4000",
                             model_name="test", temperature=0.2),
        ),
        crawler=CrawlerSettings(enabled=False),
    )


def test_sandbox_runner_init(mock_config):
    runner = SandboxRunner(mock_config)
    assert runner.config is mock_config


def test_parse_sandbox_command():
    from wargames.cli import parse_args
    args = parse_args(["sandbox", "--config", "config/test.toml"])
    assert args.command == "sandbox"
    assert args.config == "config/test.toml"


def test_parse_sandbox_with_loadout():
    from wargames.cli import parse_args
    args = parse_args(["sandbox", "--config", "config/test.toml",
                       "--loadout", "red=aggressive,blue=defensive"])
    assert args.loadout == "red=aggressive,blue=defensive"
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/engine/test_sandbox.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wargames.engine.sandbox'`

**Step 3: Write minimal implementation**

Create `wargames/engine/sandbox.py`:

```python
from __future__ import annotations

import logging
from wargames.models import GameConfig, Phase, RoundResult
from wargames.llm.client import LLMClient
from wargames.teams.red import RedTeamAgent
from wargames.teams.blue import BlueTeamAgent
from wargames.engine.judge import Judge
from wargames.engine.draft import DraftEngine
from wargames.engine.round import RoundEngine

logger = logging.getLogger(__name__)


class SandboxRunner:
    """Single-round sandbox executor. No DB, no season, no strategies."""

    def __init__(self, config: GameConfig):
        self.config = config

    async def run(self, loadout_overrides: dict[str, str] | None = None) -> RoundResult:
        """Run one round and return the result.

        loadout_overrides: optional dict like {"red": "aggressive", "blue": "defensive"}
        """
        # Apply loadout overrides if provided
        if loadout_overrides:
            if "red" in loadout_overrides:
                self.config.teams.red.loadout = loadout_overrides["red"]
            if "blue" in loadout_overrides:
                self.config.teams.blue.loadout = loadout_overrides["blue"]

        red_client = LLMClient(self.config.teams.red)
        blue_client = LLMClient(self.config.teams.blue)
        judge_client = LLMClient(self.config.teams.judge)

        try:
            red_agent = RedTeamAgent(red_client)
            blue_agent = BlueTeamAgent(blue_client)
            judge = Judge(judge_client)
            draft_engine = DraftEngine(
                picks_per_team=self.config.draft.picks_per_team,
                style=self.config.draft.style.value,
            )

            round_engine = RoundEngine(
                red=red_agent, blue=blue_agent, judge=judge,
                draft_engine=draft_engine, db=None,
                turn_limit=self.config.game.turn_limit,
                score_threshold=self.config.game.score_threshold,
            )

            result = await round_engine.play(
                round_number=1,
                phase=Phase.PROMPT_INJECTION,
                red_settings=self.config.teams.red,
                blue_settings=self.config.teams.blue,
            )
            return result
        finally:
            await red_client.close()
            await blue_client.close()
            await judge_client.close()
```

Add the `sandbox` subcommand to `wargames/cli.py`. In `parse_args()`, after the `ladder` parser:

```python
    # sandbox
    sandbox_p = sub.add_parser("sandbox", help="Run a single-round sandbox game")
    sandbox_p.add_argument("--config", default="config/default.toml", help="Config file path")
    sandbox_p.add_argument("--loadout", default=None, help="Loadout overrides: red=aggressive,blue=defensive")
```

Add the `sandbox` command handler in `main()`, after the `ladder` elif block:

```python
    elif args.command == "sandbox":
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        from wargames.config import load_config
        from wargames.engine.sandbox import SandboxRunner
        config = load_config(Path(args.config))

        loadout_overrides = None
        if args.loadout:
            loadout_overrides = {}
            for pair in args.loadout.split(","):
                team, preset = pair.strip().split("=")
                loadout_overrides[team.strip()] = preset.strip()

        async def _sandbox():
            runner = SandboxRunner(config)
            result = await runner.run(loadout_overrides)
            print(f"=== Sandbox Round ===")
            print(f"Outcome: {result.outcome.value}")
            print(f"Score: Red {result.red_score} — Blue {result.blue_score}")
            print()
            print("-- Attacks --")
            for a in result.attacks:
                status = "HIT" if a.success else "MISS"
                sev = f" [{a.severity.value}]" if a.severity else ""
                print(f"  T{a.turn}: {status}{sev} +{a.points}pts -- {a.description[:80]}")
            print()
            print("-- Defenses --")
            for d in result.defenses:
                status = "BLOCKED" if d.blocked else "MISSED"
                print(f"  T{d.turn}: {status} -{d.points_deducted}pts -- {d.description[:80]}")

        asyncio.run(_sandbox())
```

Note: The `RoundEngine.play()` method needs to accept optional `red_settings` and `blue_settings` for passing to the draft engine. Modify the `play()` method signature in `wargames/engine/round.py` (line 37) to add:

```python
    async def play(self, round_number: int, phase: Phase, target: str = None,
                   red_lessons: list[str] = None, blue_lessons: list[str] = None,
                   red_strategies: list[str] = None, blue_strategies: list[str] = None,
                   red_settings=None, blue_settings=None) -> RoundResult:
```

And pass them to `self.draft_engine.run()` (around line 52-54):

```python
        red_draft_picks, blue_draft_picks = await self.draft_engine.run(
            pool, self.red.llm, self.blue.llm,
            red_settings=red_settings, blue_settings=blue_settings,
        )
```

Also update the call in `wargames/engine/game.py` `run()` method (around line 87) to pass settings:

```python
            try:
                result = await round_engine.play(
                    round_number=round_num,
                    phase=self._current_phase,
                    red_lessons=red_lessons,
                    blue_lessons=blue_lessons,
                    red_strategies=red_strat_texts,
                    blue_strategies=blue_strat_texts,
                    red_settings=self.config.teams.red,
                    blue_settings=self.config.teams.blue,
                )
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/engine/test_sandbox.py tests/ -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add wargames/engine/sandbox.py wargames/cli.py wargames/engine/round.py wargames/engine/game.py tests/engine/test_sandbox.py
git commit -m "feat(gameplay): add sandbox mode for single-round testing"
```

---

## PILLAR 3: OBSERVABILITY

### Task 6: Token Usage Tracking in LLMClient

**Files:**
- Modify: `wargames/llm/client.py`
- Create: `tests/llm/test_token_tracking.py`

**Step 1: Write the failing tests**

Create `tests/llm/test_token_tracking.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
from wargames.llm.client import LLMClient
from wargames.models import TeamSettings


@pytest.fixture
def team_settings():
    return TeamSettings(
        name="Test", model="http://localhost:4000/v1",
        model_name="test-model", temperature=0.7,
    )


def _ok_response_with_usage(content="Hello", prompt_tokens=50, completion_tokens=20):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
    }
    resp.raise_for_status.return_value = None
    return resp


@pytest.mark.asyncio
async def test_token_tracking_initial_state(team_settings):
    client = LLMClient(team_settings)
    usage = client.get_usage()
    assert usage["prompt_tokens"] == 0
    assert usage["completion_tokens"] == 0
    assert usage["model_used"] == "test-model"


@pytest.mark.asyncio
async def test_token_tracking_accumulates(team_settings):
    client = LLMClient(team_settings)
    resp1 = _ok_response_with_usage("a", prompt_tokens=50, completion_tokens=20)
    resp2 = _ok_response_with_usage("b", prompt_tokens=80, completion_tokens=30)
    with patch.object(client._http, "post", side_effect=[resp1, resp2]):
        await client.chat([{"role": "user", "content": "Hi"}])
        await client.chat([{"role": "user", "content": "Again"}])
    usage = client.get_usage()
    assert usage["prompt_tokens"] == 130
    assert usage["completion_tokens"] == 50


@pytest.mark.asyncio
async def test_token_tracking_resets_on_get(team_settings):
    client = LLMClient(team_settings)
    resp = _ok_response_with_usage("a", prompt_tokens=50, completion_tokens=20)
    with patch.object(client._http, "post", return_value=resp):
        await client.chat([{"role": "user", "content": "Hi"}])
    usage = client.get_usage(reset=True)
    assert usage["prompt_tokens"] == 50
    # After reset
    usage2 = client.get_usage()
    assert usage2["prompt_tokens"] == 0


@pytest.mark.asyncio
async def test_token_tracking_no_usage_field(team_settings):
    """Gracefully handle responses without usage field."""
    client = LLMClient(team_settings)
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"choices": [{"message": {"content": "Hi"}}]}
    resp.raise_for_status.return_value = None
    with patch.object(client._http, "post", return_value=resp):
        result = await client.chat([{"role": "user", "content": "Hi"}])
    assert result == "Hi"
    usage = client.get_usage()
    assert usage["prompt_tokens"] == 0  # No crash, just 0


@pytest.mark.asyncio
async def test_token_tracking_with_fallback(team_settings):
    """Fallback model usage should be tracked with fallback model name."""
    settings = TeamSettings(
        name="Test", model="http://cloud:4002", model_name="cloud-model",
        temperature=0.7, fallback_model="http://localhost:11434/v1",
        fallback_model_name="qwen3:4b",
    )
    client = LLMClient(settings)
    fb_resp = _ok_response_with_usage("fallback", prompt_tokens=30, completion_tokens=10)
    import httpx
    with patch.object(client._http, "post", side_effect=httpx.ReadTimeout("timeout")), \
         patch.object(client._fallback_http, "post", return_value=fb_resp):
        await client.chat([{"role": "user", "content": "Hi"}])
    usage = client.get_usage()
    # Should track the fallback usage
    assert usage["prompt_tokens"] == 30
    assert usage["completion_tokens"] == 10
    await client.close()
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/llm/test_token_tracking.py -v`
Expected: FAIL with `AttributeError: 'LLMClient' object has no attribute 'get_usage'`

**Step 3: Write minimal implementation**

Modify `wargames/llm/client.py`. In `__init__()`, add token tracking state (after `self.settings = settings`, line 17):

```python
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._last_model_used = settings.model_name
```

Modify `_attempt()` to return both content and usage data. Change the return type and the data extraction (lines 49-51):

Replace the entire `_attempt()` method:

```python
    async def _attempt(
        self, http: httpx.AsyncClient, model_name: str,
        messages: list[dict], max_retries: int,
    ) -> tuple[str, dict]:
        """Attempt to call the LLM. Returns (content, usage_dict)."""
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
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                return content, usage
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
```

Modify `chat()` to track usage:

```python
    async def chat(self, messages: list[dict], system: str | None = None) -> str:
        if system:
            messages = [{"role": "system", "content": system}, *messages]

        try:
            content, usage = await self._attempt(
                self._http, self.settings.model_name, messages, self.MAX_RETRIES,
            )
            self._prompt_tokens += usage.get("prompt_tokens", 0)
            self._completion_tokens += usage.get("completion_tokens", 0)
            self._last_model_used = self.settings.model_name
            return content
        except (httpx.HTTPStatusError, httpx.RemoteProtocolError,
                httpx.ConnectError, httpx.ReadTimeout) as exc:
            if not self._fallback_http:
                raise
            logger.warning(
                "Primary model %s failed after %d retries, falling back to %s",
                self.settings.model_name, self.MAX_RETRIES,
                self.settings.fallback_model_name,
            )
            content, usage = await self._attempt(
                self._fallback_http, self.settings.fallback_model_name,
                messages, self.FALLBACK_RETRIES,
            )
            self._prompt_tokens += usage.get("prompt_tokens", 0)
            self._completion_tokens += usage.get("completion_tokens", 0)
            self._last_model_used = self.settings.fallback_model_name
            return content

    def get_usage(self, reset: bool = False) -> dict:
        """Return accumulated token usage. Optionally reset counters."""
        usage = {
            "prompt_tokens": self._prompt_tokens,
            "completion_tokens": self._completion_tokens,
            "model_used": self._last_model_used,
        }
        if reset:
            self._prompt_tokens = 0
            self._completion_tokens = 0
        return usage
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/llm/test_token_tracking.py tests/llm/test_client.py tests/ -v`
Expected: All tests PASS

**Important:** The existing `test_client.py` tests mock `_attempt` indirectly by mocking `http.post`. Since `_attempt` now returns `(content, usage)` instead of just `content`, the existing `_ok_response` mock already returns valid JSON with the correct structure, so existing tests should still work — `_attempt` extracts content from `data["choices"][0]["message"]["content"]` which hasn't changed.

**Step 5: Commit**

```bash
git add wargames/llm/client.py tests/llm/test_token_tracking.py
git commit -m "feat(llm): add token usage tracking to LLMClient"
```

---

### Task 7: Cost Configuration + Stats CLI Command

**Files:**
- Modify: `wargames/models.py` (add `CostsSettings`)
- Modify: `wargames/cli.py` (add `stats` command)
- Create: `tests/test_stats_cli.py`

**Step 1: Write the failing tests**

Create `tests/test_stats_cli.py`:

```python
import pytest
from wargames.cli import parse_args
from wargames.models import GameConfig, CostsSettings


def test_parse_stats_command():
    args = parse_args(["stats"])
    assert args.command == "stats"


def test_costs_settings_default():
    cs = CostsSettings()
    assert cs.rates == {}


def test_costs_settings_with_rates():
    cs = CostsSettings(rates={"llama-3-70b": 0.00059, "qwen3:4b": 0.0})
    assert cs.rates["llama-3-70b"] == 0.00059
    assert cs.rates["qwen3:4b"] == 0.0


def test_config_with_costs():
    from wargames.models import (
        GameSettings, DraftSettings, TeamSettings, TeamsSettings, CrawlerSettings,
    )
    config = GameConfig(
        game=GameSettings(name="t", rounds=1, turn_limit=1,
                         score_threshold=10, phase_advance_score=7.5),
        draft=DraftSettings(picks_per_team=3, style="snake"),
        teams=TeamsSettings(
            red=TeamSettings(name="R", model="http://x", model_name="m", temperature=0.5),
            blue=TeamSettings(name="B", model="http://x", model_name="m", temperature=0.5),
            judge=TeamSettings(name="J", model="http://x", model_name="m", temperature=0.2),
        ),
        costs=CostsSettings(rates={"m": 0.001}),
    )
    assert config.costs.rates["m"] == 0.001


def test_config_without_costs():
    from wargames.models import (
        GameSettings, DraftSettings, TeamSettings, TeamsSettings, CrawlerSettings,
    )
    config = GameConfig(
        game=GameSettings(name="t", rounds=1, turn_limit=1,
                         score_threshold=10, phase_advance_score=7.5),
        draft=DraftSettings(picks_per_team=3, style="snake"),
        teams=TeamsSettings(
            red=TeamSettings(name="R", model="http://x", model_name="m", temperature=0.5),
            blue=TeamSettings(name="B", model="http://x", model_name="m", temperature=0.5),
            judge=TeamSettings(name="J", model="http://x", model_name="m", temperature=0.2),
        ),
    )
    assert config.costs.rates == {}
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_stats_cli.py -v`
Expected: FAIL (argparse doesn't know "stats", `CostsSettings` doesn't exist)

**Step 3: Write minimal implementation**

In `wargames/models.py`, add `CostsSettings` class before `GameConfig` (around line 103):

```python
class CostsSettings(BaseModel):
    rates: dict[str, float] = Field(default_factory=dict, description="Model name to $/1K tokens rate")
```

Add `costs` field to `GameConfig`:

```python
class GameConfig(BaseModel):
    game: GameSettings
    draft: DraftSettings
    teams: TeamsSettings
    crawler: CrawlerSettings = CrawlerSettings()
    output: OutputSettings | None = None
    costs: CostsSettings = CostsSettings()
```

In `wargames/cli.py`, add the `stats` subcommand to `parse_args()` (after `sandbox`):

```python
    # stats
    sub.add_parser("stats", help="Show aggregate game statistics")
```

Add the `stats` command handler in `main()` (after `sandbox` elif):

```python
    elif args.command == "stats":
        db_path = _default_db_path()

        async def _stats():
            db = Database(db_path)
            await db.init()

            # Season stats
            season_stats = await db.get_season_stats()
            print("=== Season Stats ===")
            print(f"Total rounds: {season_stats['total_rounds']}")
            print(f"Red wins: {season_stats['red_wins']}")
            print(f"Blue wins: {season_stats['blue_wins']}")
            print(f"Auto wins: {season_stats['auto_wins']}")
            print()

            # ELO ratings
            ratings = await db.get_all_ratings()
            if ratings:
                print("=== Model Ratings ===")
                print(f"{'Model':<30}{'Rating':<10}{'W/L/D'}")
                for r in ratings:
                    print(f"{r['model_name']:<30}{r['rating']:<10.1f}{r['wins']}/{r['losses']}/{r['draws']}")
                print()

            # Token usage
            totals = await db.get_token_totals()
            print("=== Token Usage ===")
            print(f"Total prompt tokens:     {totals['total_prompt_tokens']:,}")
            print(f"Total completion tokens:  {totals['total_completion_tokens']:,}")
            total_tokens = totals['total_prompt_tokens'] + totals['total_completion_tokens']
            print(f"Total tokens:            {total_tokens:,}")
            print(f"Total cost:              ${totals['total_cost']:.4f}")

            if season_stats['total_rounds'] > 0:
                avg_tokens = total_tokens / season_stats['total_rounds']
                avg_cost = totals['total_cost'] / season_stats['total_rounds']
                print(f"Avg tokens/round:        {avg_tokens:,.0f}")
                print(f"Avg cost/round:          ${avg_cost:.4f}")

            await db.close()

        asyncio.run(_stats())
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_stats_cli.py tests/ -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add wargames/models.py wargames/cli.py tests/test_stats_cli.py
git commit -m "feat(observability): add CostsSettings model and stats CLI command"
```

---

### Task 8: Token Usage Saving in GameEngine

**Files:**
- Modify: `wargames/engine/game.py` (save token usage after each round)

**Step 1: Integration — wire token tracking into game loop**

In `wargames/engine/game.py`, in the `run()` method, after saving strategies and ELO (after the ELO update block), add token usage persistence:

```python
            # Save token usage
            try:
                costs = {}
                if hasattr(self.config, 'costs') and self.config.costs:
                    costs = self.config.costs.rates

                for team_name, client in [("red", self._red_client), ("blue", self._blue_client), ("judge", self._judge_client)]:
                    usage = client.get_usage(reset=True)
                    model = usage["model_used"]
                    rate = costs.get(model, 0.0)
                    total_tokens = usage["prompt_tokens"] + usage["completion_tokens"]
                    cost = (total_tokens / 1000.0) * rate

                    await self.db.save_token_usage(
                        round_number=round_num,
                        team=team_name,
                        prompt_tokens=usage["prompt_tokens"],
                        completion_tokens=usage["completion_tokens"],
                        model_used=model,
                        cost=cost,
                    )
            except Exception as exc:
                logger.warning("Token usage tracking failed for round %d: %s", round_num, exc)
```

**Step 2: Run full test suite to verify nothing broke**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add wargames/engine/game.py
git commit -m "feat(observability): save token usage per round in GameEngine"
```

---

### Task 9: TUI Token Panel Widget

**Files:**
- Modify: `wargames/tui/app.py` (add `TokenPanel` widget)

**Step 1: Add TokenPanel widget**

In `wargames/tui/app.py`, add a new widget class after `RecentReports` (around line 43):

```python
class TokenPanel(Static):
    """Live token usage and cost display."""

    def compose(self) -> ComposeResult:
        yield Static("TOKENS & COST", classes="section-title")
        yield Static("Red: -- tokens ($--)", id="red-tokens")
        yield Static("Blue: -- tokens ($--)", id="blue-tokens")
        yield Static("Total cost: $--", id="total-cost")
```

Add CSS for the new widget (inside the CSS string, after the `RecentReports` CSS):

```css
    TokenPanel {
        width: 1fr;
        border: solid $warning;
        padding: 0 1;
    }
```

Change the bottom layout to accommodate 3 panels. Replace the `#bottom` section in `compose()`:

```python
        with Horizontal(id="bottom"):
            yield SeasonStats()
            yield RecentReports()
            yield TokenPanel()
```

In `refresh_data()`, add token usage refresh (after the recent rounds section, before `except`):

```python
                # Token usage
                try:
                    cursor = await db.execute(
                        "SELECT team, SUM(prompt_tokens + completion_tokens) as total_tokens, "
                        "SUM(cost) as total_cost FROM token_usage GROUP BY team"
                    )
                    token_rows = await cursor.fetchall()
                    for tr in token_rows:
                        team = tr["team"]
                        if team in ("red", "blue"):
                            self.query_one(f"#{team}-tokens", Static).update(
                                f"{team.title()}: {tr['total_tokens']:,} tokens (${tr['total_cost']:.4f})"
                            )

                    cursor = await db.execute(
                        "SELECT COALESCE(SUM(cost), 0) as total FROM token_usage"
                    )
                    cost_row = await cursor.fetchone()
                    if cost_row:
                        self.query_one("#total-cost", Static).update(f"Total cost: ${cost_row['total']:.4f}")
                except Exception:
                    pass  # token_usage table may not exist yet
```

Also add token usage events to `consume_events()` (inside the event loop, after the `round_complete` handler):

```python
            elif event_type == "token_usage":
                team = data.get("team", "?")
                tokens = data.get("tokens", 0)
                cost = data.get("cost", 0.0)
                feed.write(f"[dim]TOKENS {team}: {tokens:,} (${cost:.4f})[/]")
```

**Step 2: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add wargames/tui/app.py
git commit -m "feat(tui): add TokenPanel widget for live cost tracking"
```

---

### Task 10: Config Presets Update + Final Verification

**Files:**
- Modify: `config/fallback-cloud.toml` (add costs section)
- Create: `config/tournament.toml` (new tournament preset with loadouts + costs)

**Step 1: Update fallback-cloud.toml**

Add costs section at the end of `config/fallback-cloud.toml`:

```toml
[costs]
"llama-3-70b" = 0.00059
"qwen3:4b" = 0.0
```

**Step 2: Create tournament preset**

Create `config/tournament.toml`:

```toml
# Tournament mode preset with loadouts and cost tracking.

[game]
name = "tournament-01"
rounds = 5
turn_limit = 4
score_threshold = 10
phase_advance_score = 7.5

[draft]
picks_per_team = 3
style = "snake"

[teams.red]
name = "Red Team"
model = "http://localhost:4003"
model_name = "llama-3-70b"
fallback_model = "http://localhost:11434/v1"
fallback_model_name = "qwen3:4b"
temperature = 0.8
timeout = 60.0
api_key = "$LITELLM_MASTER_KEY"
loadout = "aggressive"

[teams.blue]
name = "Blue Team"
model = "http://localhost:4003"
model_name = "llama-3-70b"
fallback_model = "http://localhost:11434/v1"
fallback_model_name = "qwen3:4b"
temperature = 0.4
timeout = 60.0
api_key = "$LITELLM_MASTER_KEY"
loadout = "defensive"

[teams.judge]
name = "Judge"
model = "http://localhost:4003"
model_name = "llama-3-70b"
fallback_model = "http://localhost:11434/v1"
fallback_model_name = "qwen3:4b"
temperature = 0.2
timeout = 90.0
api_key = "$LITELLM_MASTER_KEY"

[crawler]
enabled = true
sources = ["nvd", "exploitdb"]
refresh_interval = "24h"

[costs]
"llama-3-70b" = 0.00059
"qwen3:4b" = 0.0

[output.vault]
enabled = true
path = "~/OpenClaw-Vault/WarGames"

[output.database]
path = "~/.local/share/wargames/state.db"
```

**Step 3: Run full test suite + verify configs load**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

Then verify configs load:

```bash
python -c "from wargames.config import load_config; from pathlib import Path; c = load_config(Path('config/tournament.toml')); print(f'OK: {c.game.name}, loadout={c.teams.red.loadout}, costs={c.costs.rates}')"
```

Expected: `OK: tournament-01, loadout=aggressive, costs={'llama-3-70b': 0.00059, 'qwen3:4b': 0.0}`

**Step 4: Commit**

```bash
git add config/fallback-cloud.toml config/tournament.toml
git commit -m "feat(config): add tournament preset and cost rates to fallback-cloud"
```

---

## Summary of All Tasks

| # | Pillar | Task | New Files | Modified Files |
|---|--------|------|-----------|----------------|
| 1 | Tournament | ELO Rating Engine | `elo.py`, `test_elo.py` | — |
| 2 | Tournament | DB Tables + Methods | `test_tournament_db.py` | `db.py` |
| 3 | Tournament | Ladder CLI + GameEngine ELO | `test_ladder_cli.py` | `cli.py`, `game.py` |
| 4 | Gameplay | Team Loadouts | `loadouts.py`, `test_loadouts.py` | `models.py`, `draft.py` |
| 5 | Gameplay | Sandbox Mode | `sandbox.py`, `test_sandbox.py` | `cli.py`, `round.py`, `game.py` |
| 6 | Observability | Token Tracking | `test_token_tracking.py` | `client.py` |
| 7 | Observability | Cost Config + Stats CLI | `test_stats_cli.py` | `models.py`, `cli.py` |
| 8 | Observability | Token Saving in GameEngine | — | `game.py` |
| 9 | Observability | TUI Token Panel | — | `app.py` |
| 10 | Config | Presets Update | `tournament.toml` | `fallback-cloud.toml` |
