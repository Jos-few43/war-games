# Evolution Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix strategy evolution to have proper attribution, pruning with graveyard, and time decay so winning strategies are reinforced and losing ones are retired.

**Architecture:** Three surgical changes to `strategy.py`: (1) track which strategy IDs were injected and only update those win rates, (2) soft-delete underperformers into a graveyard and dedup new strategies against it, (3) rank strategies by a composite score combining win rate and recency. Game engine passes the needed context (loaded IDs, current round) through the existing call chain.

**Tech Stack:** Python 3.14, Pydantic, aiosqlite, pytest

---

### Task 1: Add `id` field to Strategy model and `active` column to DB schema

**Files:**
- Modify: `wargames/models.py:236-243`
- Modify: `wargames/output/db.py:86-97`
- Test: `tests/engine/test_strategy.py`

**Step 1: Write the failing test**

Add to `tests/engine/test_strategy.py`:

```python
@pytest.mark.asyncio
async def test_strategy_has_id_after_load(tmp_path: Path):
    """Strategies loaded from DB have their integer id set."""
    db = Database(tmp_path / "test.db")
    await db.init()

    strategy = Strategy(
        team="red", phase=1, strategy_type="attack",
        content="Test strategy with id", win_rate=0.5, usage_count=1, created_round=1,
    )
    await save_strategies([strategy], db)

    loaded = await get_top_strategies(team="red", phase=1, db=db)
    assert len(loaded) == 1
    assert loaded[0].id is not None
    assert isinstance(loaded[0].id, int)

    await db.close()


@pytest.mark.asyncio
async def test_inactive_strategies_not_returned(tmp_path: Path):
    """Strategies with active=0 are excluded from get_top_strategies."""
    db = Database(tmp_path / "test.db")
    await db.init()

    strategies = [
        Strategy(team="red", phase=1, strategy_type="attack", content="Active one", win_rate=0.8, usage_count=3, created_round=1),
        Strategy(team="red", phase=1, strategy_type="attack", content="Inactive one", win_rate=0.9, usage_count=3, created_round=1),
    ]
    await save_strategies(strategies, db)

    # Manually deactivate the second strategy
    await db._conn.execute("UPDATE strategies SET active = 0 WHERE content = 'Inactive one'")
    await db._conn.commit()

    loaded = await get_top_strategies(team="red", phase=1, db=db)
    assert len(loaded) == 1
    assert loaded[0].content == "Active one"

    await db.close()
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/PROJECTz/war-games && python -m pytest tests/engine/test_strategy.py::test_strategy_has_id_after_load tests/engine/test_strategy.py::test_inactive_strategies_not_returned -v`
Expected: FAIL — `id` field doesn't exist on Strategy, `active` column doesn't exist

**Step 3: Implement the changes**

In `wargames/models.py`, update the Strategy model (around line 236):

```python
class Strategy(BaseModel):
    id: int | None = None
    team: str
    phase: int
    strategy_type: str  # "attack", "defense", "draft"
    content: str
    win_rate: float = 0.0
    usage_count: int = 0
    created_round: int = 0
```

In `wargames/output/db.py`, update the CREATE_STRATEGIES SQL (around line 86):

```sql
CREATE TABLE IF NOT EXISTS strategies (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    team           TEXT,
    phase          INTEGER,
    strategy_type  TEXT,
    content        TEXT,
    win_rate       REAL DEFAULT 0.0,
    usage_count    INTEGER DEFAULT 0,
    created_round  INTEGER,
    active         INTEGER DEFAULT 1
)
```

In `wargames/engine/strategy.py`, update `get_top_strategies` (around line 87) to include `id` and filter by `active`:

```python
async def get_top_strategies(
    team: str, phase: int, db, limit: int = 5
) -> list[Strategy]:
    """Query DB for top active strategies ordered by win_rate DESC."""
    cursor = await db._conn.execute(
        """
        SELECT id, team, phase, strategy_type, content, win_rate, usage_count, created_round
        FROM strategies
        WHERE team = ? AND phase = ? AND active = 1
        ORDER BY win_rate DESC
        LIMIT ?
        """,
        (team, phase, limit),
    )
    rows = await cursor.fetchall()
    return [
        Strategy(
            id=row["id"],
            team=row["team"],
            phase=row["phase"],
            strategy_type=row["strategy_type"],
            content=row["content"],
            win_rate=row["win_rate"],
            usage_count=row["usage_count"],
            created_round=row["created_round"],
        )
        for row in rows
    ]
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/PROJECTz/war-games && python -m pytest tests/engine/test_strategy.py -v`
Expected: ALL PASS (new tests + existing tests)

**Step 5: Commit**

```bash
cd ~/PROJECTz/war-games
git add wargames/models.py wargames/output/db.py wargames/engine/strategy.py tests/engine/test_strategy.py
git commit -m "feat(evolution): add strategy id field and active column for soft-delete"
```

---

### Task 2: Per-strategy attribution in win rate updates

**Files:**
- Modify: `wargames/engine/strategy.py:116-137`
- Modify: `wargames/engine/game.py:94-136`
- Test: `tests/engine/test_strategy.py`

**Step 1: Write the failing test**

Add to `tests/engine/test_strategy.py`:

```python
@pytest.mark.asyncio
async def test_update_win_rates_by_id(tmp_path: Path):
    """Only strategies with specified IDs get their win rates updated."""
    db = Database(tmp_path / "test.db")
    await db.init()

    strategies = [
        Strategy(team="red", phase=1, strategy_type="attack", content="Used strategy", win_rate=0.5, usage_count=2, created_round=1),
        Strategy(team="red", phase=1, strategy_type="attack", content="Not used strategy", win_rate=0.5, usage_count=2, created_round=1),
    ]
    await save_strategies(strategies, db)

    # Load to get IDs
    loaded = await get_top_strategies(team="red", phase=1, db=db)
    used_id = next(s.id for s in loaded if s.content == "Used strategy")

    # Only update the used strategy
    await update_win_rates(strategy_ids=[used_id], round_won=True, db=db)

    reloaded = await get_top_strategies(team="red", phase=1, db=db)
    used = next(s for s in reloaded if s.content == "Used strategy")
    not_used = next(s for s in reloaded if s.content == "Not used strategy")

    # Used: (0.5*2 + 1.0) / 3 = 0.667
    assert used.win_rate == pytest.approx(2.0 / 3, rel=1e-4)
    assert used.usage_count == 3

    # Not used: unchanged
    assert not_used.win_rate == pytest.approx(0.5)
    assert not_used.usage_count == 2

    await db.close()


@pytest.mark.asyncio
async def test_update_win_rates_empty_ids(tmp_path: Path):
    """Empty ID list is a no-op."""
    db = Database(tmp_path / "test.db")
    await db.init()

    strategy = Strategy(team="red", phase=1, strategy_type="attack", content="Some strat", win_rate=0.5, usage_count=2, created_round=1)
    await save_strategies([strategy], db)

    await update_win_rates(strategy_ids=[], round_won=True, db=db)

    loaded = await get_top_strategies(team="red", phase=1, db=db)
    assert loaded[0].win_rate == pytest.approx(0.5)
    assert loaded[0].usage_count == 2

    await db.close()
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/PROJECTz/war-games && python -m pytest tests/engine/test_strategy.py::test_update_win_rates_by_id tests/engine/test_strategy.py::test_update_win_rates_empty_ids -v`
Expected: FAIL — `update_win_rates` doesn't accept `strategy_ids` parameter

**Step 3: Implement the changes**

Replace `update_win_rates` in `wargames/engine/strategy.py` (lines 116-137):

```python
async def update_win_rates(*, strategy_ids: list[int], round_won: bool, db) -> None:
    """Update win_rate only for strategies that were actually used this round."""
    if not strategy_ids:
        return

    win_val = 1.0 if round_won else 0.0

    placeholders = ",".join("?" for _ in strategy_ids)
    cursor = await db._conn.execute(
        f"SELECT id, win_rate, usage_count FROM strategies WHERE id IN ({placeholders})",
        strategy_ids,
    )
    rows = await cursor.fetchall()

    for row in rows:
        old_rate = row["win_rate"]
        old_count = row["usage_count"]
        new_count = old_count + 1
        new_rate = (old_rate * old_count + win_val) / new_count

        await db._conn.execute(
            "UPDATE strategies SET win_rate = ?, usage_count = ? WHERE id = ?",
            (new_rate, new_count, row["id"]),
        )

    await db._conn.commit()
```

Update `wargames/engine/game.py` (around lines 94-136). Change the strategy loading to capture IDs, and the update call to pass them:

In the round loop (around line 94), change:
```python
            # Load top strategies for current phase before each round
            red_top = await get_top_strategies("red", self._current_phase.value, self.db)
            blue_top = await get_top_strategies("blue", self._current_phase.value, self.db)
            red_strat_texts = [s.content for s in red_top]
            blue_strat_texts = [s.content for s in blue_top]
```
to:
```python
            # Load top strategies for current phase before each round
            red_top = await get_top_strategies("red", self._current_phase.value, self.db)
            blue_top = await get_top_strategies("blue", self._current_phase.value, self.db)
            red_strat_texts = [s.content for s in red_top]
            blue_strat_texts = [s.content for s in blue_top]
            red_used_ids = [s.id for s in red_top if s.id is not None]
            blue_used_ids = [s.id for s in blue_top if s.id is not None]
```

And change the win rate update calls (around line 135):
```python
                await update_win_rates("red", self._current_phase.value, won_red, self.db)
                await update_win_rates("blue", self._current_phase.value, not won_red, self.db)
```
to:
```python
                await update_win_rates(strategy_ids=red_used_ids, round_won=won_red, db=self.db)
                await update_win_rates(strategy_ids=blue_used_ids, round_won=not won_red, db=self.db)
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/PROJECTz/war-games && python -m pytest tests/engine/test_strategy.py -v`
Expected: ALL PASS

Note: The existing `test_update_win_rates` and `test_update_win_rates_loss` tests will fail because they use the old signature `update_win_rates(team=..., phase=..., round_won=..., db=...)`. Update them to use the new signature:

For `test_update_win_rates`: load the strategy to get its ID first, then call `update_win_rates(strategy_ids=[loaded[0].id], round_won=True, db=db)`.

For `test_update_win_rates_loss`: same pattern — load to get ID, then call with `strategy_ids=[loaded[0].id]`.

**Step 5: Run full test suite**

Run: `cd ~/PROJECTz/war-games && python -m pytest -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
cd ~/PROJECTz/war-games
git add wargames/engine/strategy.py wargames/engine/game.py tests/engine/test_strategy.py
git commit -m "feat(evolution): per-strategy attribution — only update win rates for used strategies"
```

---

### Task 3: Strategy pruning with graveyard

**Files:**
- Modify: `wargames/engine/strategy.py` (add `prune_strategies` function)
- Modify: `wargames/engine/game.py` (call prune after win rate update)
- Test: `tests/engine/test_strategy.py`

**Step 1: Write the failing tests**

Add to `tests/engine/test_strategy.py`:

```python
from wargames.engine.strategy import prune_strategies


@pytest.mark.asyncio
async def test_prune_underperformers(tmp_path: Path):
    """Strategies with usage >= 3 and win_rate < 0.2 get deactivated."""
    db = Database(tmp_path / "test.db")
    await db.init()

    strategies = [
        Strategy(team="red", phase=1, strategy_type="attack", content="Winner", win_rate=0.8, usage_count=5, created_round=1),
        Strategy(team="red", phase=1, strategy_type="attack", content="Loser", win_rate=0.1, usage_count=4, created_round=1),
        Strategy(team="red", phase=1, strategy_type="attack", content="New loser", win_rate=0.0, usage_count=1, created_round=3),
    ]
    await save_strategies(strategies, db)

    await prune_strategies(team="red", phase=1, db=db)

    loaded = await get_top_strategies(team="red", phase=1, db=db)
    contents = [s.content for s in loaded]
    assert "Winner" in contents
    assert "New loser" in contents  # kept — not enough usage to judge
    assert "Loser" not in contents  # pruned — low win rate with enough data

    await db.close()


@pytest.mark.asyncio
async def test_prune_caps_pool_size(tmp_path: Path):
    """Pool is capped at 20 active strategies per team/phase."""
    db = Database(tmp_path / "test.db")
    await db.init()

    strategies = [
        Strategy(team="blue", phase=1, strategy_type="defense", content=f"Strategy {i}",
                 win_rate=float(i) / 25, usage_count=1, created_round=1)
        for i in range(25)
    ]
    await save_strategies(strategies, db)

    await prune_strategies(team="blue", phase=1, db=db)

    loaded = await get_top_strategies(team="blue", phase=1, db=db, limit=50)
    assert len(loaded) == 20

    # Verify the top-rated ones survived
    assert loaded[0].content == "Strategy 24"  # highest win_rate

    await db.close()


@pytest.mark.asyncio
async def test_pruned_strategies_remain_in_graveyard(tmp_path: Path):
    """Pruned strategies are soft-deleted (active=0), not hard-deleted."""
    db = Database(tmp_path / "test.db")
    await db.init()

    strategy = Strategy(team="red", phase=1, strategy_type="attack", content="Bad strat",
                        win_rate=0.05, usage_count=5, created_round=1)
    await save_strategies([strategy], db)

    await prune_strategies(team="red", phase=1, db=db)

    # Not in active results
    loaded = await get_top_strategies(team="red", phase=1, db=db)
    assert len(loaded) == 0

    # But still in DB
    cursor = await db._conn.execute("SELECT active FROM strategies WHERE content = 'Bad strat'")
    row = await cursor.fetchone()
    assert row is not None
    assert row["active"] == 0

    await db.close()
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/PROJECTz/war-games && python -m pytest tests/engine/test_strategy.py::test_prune_underperformers tests/engine/test_strategy.py::test_prune_caps_pool_size tests/engine/test_strategy.py::test_pruned_strategies_remain_in_graveyard -v`
Expected: FAIL — `prune_strategies` doesn't exist

**Step 3: Implement prune_strategies**

Add to `wargames/engine/strategy.py`:

```python
async def prune_strategies(team: str, phase: int, db, *, min_uses: int = 3, min_win_rate: float = 0.2, max_pool: int = 20) -> None:
    """Soft-delete underperforming strategies and cap pool size."""
    # 1. Deactivate underperformers with enough data
    await db._conn.execute(
        """
        UPDATE strategies SET active = 0
        WHERE team = ? AND phase = ? AND active = 1
          AND usage_count >= ? AND win_rate < ?
        """,
        (team, phase, min_uses, min_win_rate),
    )

    # 2. Cap pool size — deactivate lowest-rated excess
    cursor = await db._conn.execute(
        """
        SELECT id FROM strategies
        WHERE team = ? AND phase = ? AND active = 1
        ORDER BY win_rate DESC
        LIMIT -1 OFFSET ?
        """,
        (team, phase, max_pool),
    )
    excess_rows = await cursor.fetchall()
    if excess_rows:
        excess_ids = [row["id"] for row in excess_rows]
        placeholders = ",".join("?" for _ in excess_ids)
        await db._conn.execute(
            f"UPDATE strategies SET active = 0 WHERE id IN ({placeholders})",
            excess_ids,
        )

    await db._conn.commit()
```

Update the import in `wargames/engine/game.py` (line 15) to include `prune_strategies`:

```python
from wargames.engine.strategy import extract_strategies, save_strategies, get_top_strategies, update_win_rates, prune_strategies
```

Add prune calls after the win rate updates in `game.py` (after the `update_win_rates` calls, inside the same try block around line 136):

```python
                await prune_strategies("red", self._current_phase.value, self.db)
                await prune_strategies("blue", self._current_phase.value, self.db)
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/PROJECTz/war-games && python -m pytest tests/engine/test_strategy.py -v`
Expected: ALL PASS

**Step 5: Run full test suite**

Run: `cd ~/PROJECTz/war-games && python -m pytest -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
cd ~/PROJECTz/war-games
git add wargames/engine/strategy.py wargames/engine/game.py tests/engine/test_strategy.py
git commit -m "feat(evolution): strategy pruning with graveyard soft-delete"
```

---

### Task 4: Strategy deduplication against graveyard

**Files:**
- Modify: `wargames/engine/strategy.py` (add dedup logic to `save_strategies`)
- Test: `tests/engine/test_strategy.py`

**Step 1: Write the failing tests**

Add to `tests/engine/test_strategy.py`:

```python
@pytest.mark.asyncio
async def test_dedup_skips_similar_active(tmp_path: Path):
    """New strategy with >70% word overlap to existing active strategy is skipped."""
    db = Database(tmp_path / "test.db")
    await db.init()

    existing = Strategy(team="red", phase=1, strategy_type="attack",
                        content="Use SQL injection to bypass authentication and access admin panel",
                        win_rate=0.5, usage_count=2, created_round=1)
    await save_strategies([existing], db)

    duplicate = Strategy(team="red", phase=1, strategy_type="attack",
                         content="Use SQL injection to bypass authentication and access the admin panel directly",
                         win_rate=0.0, usage_count=0, created_round=2)
    await save_strategies([duplicate], db)

    loaded = await get_top_strategies(team="red", phase=1, db=db, limit=10)
    assert len(loaded) == 1  # duplicate was skipped

    await db.close()


@pytest.mark.asyncio
async def test_dedup_skips_similar_inactive(tmp_path: Path):
    """New strategy with >70% word overlap to graveyard strategy is also skipped."""
    db = Database(tmp_path / "test.db")
    await db.init()

    graveyard = Strategy(team="blue", phase=1, strategy_type="defense",
                         content="Deploy WAF rules to block SQL injection patterns at the perimeter",
                         win_rate=0.1, usage_count=5, created_round=1)
    await save_strategies([graveyard], db)
    # Deactivate it (move to graveyard)
    await db._conn.execute("UPDATE strategies SET active = 0 WHERE content LIKE '%WAF rules%'")
    await db._conn.commit()

    rehash = Strategy(team="blue", phase=1, strategy_type="defense",
                      content="Deploy WAF rules to block SQL injection patterns at the network perimeter",
                      win_rate=0.0, usage_count=0, created_round=3)
    await save_strategies([rehash], db)

    # Should have 0 active (graveyard one is inactive, rehash was skipped)
    loaded = await get_top_strategies(team="blue", phase=1, db=db, limit=10)
    assert len(loaded) == 0

    await db.close()


@pytest.mark.asyncio
async def test_dedup_allows_different_strategies(tmp_path: Path):
    """Strategies with <70% word overlap are allowed."""
    db = Database(tmp_path / "test.db")
    await db.init()

    existing = Strategy(team="red", phase=1, strategy_type="attack",
                        content="Use SQL injection to bypass authentication",
                        win_rate=0.5, usage_count=2, created_round=1)
    await save_strategies([existing], db)

    different = Strategy(team="red", phase=1, strategy_type="attack",
                         content="Social engineering phishing campaign targeting admin credentials",
                         win_rate=0.0, usage_count=0, created_round=2)
    await save_strategies([different], db)

    loaded = await get_top_strategies(team="red", phase=1, db=db, limit=10)
    assert len(loaded) == 2

    await db.close()
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/PROJECTz/war-games && python -m pytest tests/engine/test_strategy.py::test_dedup_skips_similar_active tests/engine/test_strategy.py::test_dedup_skips_similar_inactive tests/engine/test_strategy.py::test_dedup_allows_different_strategies -v`
Expected: FAIL — no dedup logic yet, duplicates get inserted

**Step 3: Implement dedup**

Add a helper function and modify `save_strategies` in `wargames/engine/strategy.py`:

```python
def _word_overlap(a: str, b: str) -> float:
    """Return fraction of shared words between two strings (Jaccard similarity)."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


async def save_strategies(strategies: list[Strategy], db, *, dedup_threshold: float = 0.7) -> None:
    """Insert Strategy objects, skipping duplicates that overlap with existing strategies."""
    for s in strategies:
        # Check for duplicates against ALL strategies (active and inactive)
        cursor = await db._conn.execute(
            "SELECT content FROM strategies WHERE team = ? AND phase = ? AND strategy_type = ?",
            (s.team, s.phase, s.strategy_type),
        )
        existing_rows = await cursor.fetchall()

        is_duplicate = False
        for row in existing_rows:
            if _word_overlap(s.content, row["content"]) >= dedup_threshold:
                is_duplicate = True
                break

        if is_duplicate:
            continue

        await db._conn.execute(
            """
            INSERT INTO strategies
                (team, phase, strategy_type, content, win_rate, usage_count, created_round)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (s.team, s.phase, s.strategy_type, s.content, s.win_rate, s.usage_count, s.created_round),
        )
    await db._conn.commit()
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/PROJECTz/war-games && python -m pytest tests/engine/test_strategy.py -v`
Expected: ALL PASS

**Step 5: Run full test suite**

Run: `cd ~/PROJECTz/war-games && python -m pytest -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
cd ~/PROJECTz/war-games
git add wargames/engine/strategy.py tests/engine/test_strategy.py
git commit -m "feat(evolution): dedup new strategies against active and graveyard pool"
```

---

### Task 5: Time decay in strategy selection

**Files:**
- Modify: `wargames/engine/strategy.py:87-113` (`get_top_strategies`)
- Modify: `wargames/engine/game.py:94-98` (pass current_round)
- Test: `tests/engine/test_strategy.py`

**Step 1: Write the failing tests**

Add to `tests/engine/test_strategy.py`:

```python
@pytest.mark.asyncio
async def test_time_decay_favors_recent(tmp_path: Path):
    """Recent strategy with moderate win rate beats old strategy with high win rate."""
    db = Database(tmp_path / "test.db")
    await db.init()

    strategies = [
        Strategy(team="red", phase=1, strategy_type="attack", content="Old winner",
                 win_rate=0.8, usage_count=10, created_round=1),
        Strategy(team="red", phase=1, strategy_type="attack", content="Recent moderate",
                 win_rate=0.7, usage_count=3, created_round=9),
    ]
    await save_strategies(strategies, db)

    # At round 10, recent strategy should rank higher
    loaded = await get_top_strategies(team="red", phase=1, db=db, current_round=10)
    assert loaded[0].content == "Recent moderate"

    await db.close()


@pytest.mark.asyncio
async def test_time_decay_without_round_falls_back(tmp_path: Path):
    """Without current_round, ordering falls back to pure win_rate DESC."""
    db = Database(tmp_path / "test.db")
    await db.init()

    strategies = [
        Strategy(team="red", phase=1, strategy_type="attack", content="Lower rate",
                 win_rate=0.5, usage_count=5, created_round=1),
        Strategy(team="red", phase=1, strategy_type="attack", content="Higher rate",
                 win_rate=0.9, usage_count=5, created_round=1),
    ]
    await save_strategies(strategies, db)

    loaded = await get_top_strategies(team="red", phase=1, db=db)
    assert loaded[0].content == "Higher rate"

    await db.close()
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/PROJECTz/war-games && python -m pytest tests/engine/test_strategy.py::test_time_decay_favors_recent tests/engine/test_strategy.py::test_time_decay_without_round_falls_back -v`
Expected: FAIL — `get_top_strategies` doesn't accept `current_round`

**Step 3: Implement time decay**

Update `get_top_strategies` in `wargames/engine/strategy.py`:

```python
async def get_top_strategies(
    team: str, phase: int, db, limit: int = 5, current_round: int | None = None
) -> list[Strategy]:
    """Query DB for top active strategies, ranked by composite score with time decay."""
    if current_round is not None:
        cursor = await db._conn.execute(
            """
            SELECT id, team, phase, strategy_type, content, win_rate, usage_count, created_round,
                   (win_rate * 0.7 + (1.0 / (1 + (? - created_round))) * 0.3) AS score
            FROM strategies
            WHERE team = ? AND phase = ? AND active = 1
            ORDER BY score DESC
            LIMIT ?
            """,
            (current_round, team, phase, limit),
        )
    else:
        cursor = await db._conn.execute(
            """
            SELECT id, team, phase, strategy_type, content, win_rate, usage_count, created_round
            FROM strategies
            WHERE team = ? AND phase = ? AND active = 1
            ORDER BY win_rate DESC
            LIMIT ?
            """,
            (team, phase, limit),
        )
    rows = await cursor.fetchall()
    return [
        Strategy(
            id=row["id"],
            team=row["team"],
            phase=row["phase"],
            strategy_type=row["strategy_type"],
            content=row["content"],
            win_rate=row["win_rate"],
            usage_count=row["usage_count"],
            created_round=row["created_round"],
        )
        for row in rows
    ]
```

Update `game.py` to pass `current_round` (around line 94):

```python
            red_top = await get_top_strategies("red", self._current_phase.value, self.db, current_round=round_num)
            blue_top = await get_top_strategies("blue", self._current_phase.value, self.db, current_round=round_num)
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/PROJECTz/war-games && python -m pytest tests/engine/test_strategy.py -v`
Expected: ALL PASS

**Step 5: Run full test suite**

Run: `cd ~/PROJECTz/war-games && python -m pytest -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
cd ~/PROJECTz/war-games
git add wargames/engine/strategy.py wargames/engine/game.py tests/engine/test_strategy.py
git commit -m "feat(evolution): time decay in strategy selection favoring recent winners"
```

---

### Task 6: Integration test — 3-round evolution with all improvements

**Files:**
- Test: `tests/engine/test_strategy.py`

**Step 1: Write the integration test**

Add to `tests/engine/test_strategy.py`:

```python
@pytest.mark.asyncio
async def test_evolution_full_cycle(tmp_path: Path):
    """Simulate a 3-round evolution cycle: extract, save, select, update, prune."""
    db = Database(tmp_path / "test.db")
    await db.init()

    # Round 1: cold start — no strategies
    r1_top = await get_top_strategies("red", 1, db, current_round=1)
    assert len(r1_top) == 0

    # Simulate: round 1 extracts 3 strategies
    r1_strats = [
        Strategy(team="red", phase=1, strategy_type="attack", content="SQL injection via login form", created_round=1),
        Strategy(team="red", phase=1, strategy_type="attack", content="XSS in comment field", created_round=1),
        Strategy(team="red", phase=1, strategy_type="defense", content="Input validation on all fields", created_round=1),
    ]
    await save_strategies(r1_strats, db)

    # Red won round 1 — but no used IDs (cold start)
    # This is correct — no strategies were loaded so none get credit

    # Round 2: load strategies, use them
    r2_top = await get_top_strategies("red", 1, db, current_round=2)
    assert len(r2_top) == 3  # all 3 from round 1
    r2_used_ids = [s.id for s in r2_top if s.id]

    # Red lost round 2
    await update_win_rates(strategy_ids=r2_used_ids, round_won=False, db=db)

    # Check: all used strategies now have usage=1, win_rate=0.0
    after_r2 = await get_top_strategies("red", 1, db, current_round=2)
    for s in after_r2:
        assert s.usage_count == 1
        assert s.win_rate == pytest.approx(0.0)

    # Round 2 also extracts 2 new strategies
    r2_new = [
        Strategy(team="red", phase=1, strategy_type="attack", content="Phishing with crafted email", created_round=2),
        Strategy(team="red", phase=1, strategy_type="attack", content="SQL injection via login form and API", created_round=2),
        # ^ this should be deduped against "SQL injection via login form"
    ]
    await save_strategies(r2_new, db)

    all_active = await get_top_strategies("red", 1, db, current_round=2, limit=20)
    contents = [s.content for s in all_active]
    assert "Phishing with crafted email" in contents
    # The near-duplicate should NOT be saved
    assert "SQL injection via login form and API" not in contents

    # Round 3: use top 5, win
    r3_top = await get_top_strategies("red", 1, db, current_round=3)
    r3_used_ids = [s.id for s in r3_top if s.id]
    await update_win_rates(strategy_ids=r3_used_ids, round_won=True, db=db)

    # After 2 uses (1 loss, 1 win) the round-1 strategies should have win_rate ≈ 0.5
    r1_reloaded = await get_top_strategies("red", 1, db, current_round=3, limit=20)
    sql_strat = next(s for s in r1_reloaded if "SQL injection" in s.content)
    assert sql_strat.usage_count == 2
    assert sql_strat.win_rate == pytest.approx(0.5)

    # The phishing strat (round 2, 1 use, 1 win) should have win_rate=1.0
    phishing = next(s for s in r1_reloaded if "Phishing" in s.content)
    assert phishing.usage_count == 1
    assert phishing.win_rate == pytest.approx(1.0)

    # With time decay at round 3: phishing (round 2, wr=1.0) should outrank SQL (round 1, wr=0.5)
    assert r3_top[0].content != "SQL injection via login form" or r3_top[0].win_rate >= 0.5

    await db.close()
```

**Step 2: Run the integration test**

Run: `cd ~/PROJECTz/war-games && python -m pytest tests/engine/test_strategy.py::test_evolution_full_cycle -v`
Expected: PASS

**Step 3: Run full test suite**

Run: `cd ~/PROJECTz/war-games && python -m pytest -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
cd ~/PROJECTz/war-games
git add tests/engine/test_strategy.py
git commit -m "test(evolution): integration test for full 3-round evolution cycle"
```
