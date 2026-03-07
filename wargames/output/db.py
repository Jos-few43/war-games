from __future__ import annotations

from pathlib import Path

import aiosqlite

from wargames.models import (
    AttackResult,
    BugReport,
    DefenseResult,
    Domain,
    DraftPick,
    MatchOutcome,
    Patch,
    Phase,
    RoundResult,
    Severity,
)

CREATE_ROUNDS = """
CREATE TABLE IF NOT EXISTS rounds (
    round_number INTEGER PRIMARY KEY,
    phase        INTEGER,
    outcome      TEXT,
    red_score    INTEGER,
    blue_threshold INTEGER,
    red_debrief  TEXT,
    blue_debrief TEXT
)
"""

CREATE_ATTACKS = """
CREATE TABLE IF NOT EXISTS attacks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    round_number INTEGER REFERENCES rounds(round_number),
    turn         INTEGER,
    description  TEXT,
    severity     TEXT,
    points       INTEGER,
    success      INTEGER,
    auto_win     INTEGER
)
"""

CREATE_DEFENSES = """
CREATE TABLE IF NOT EXISTS defenses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    round_number    INTEGER REFERENCES rounds(round_number),
    turn            INTEGER,
    description     TEXT,
    blocked         INTEGER,
    points_deducted INTEGER
)
"""

CREATE_DRAFT_PICKS = """
CREATE TABLE IF NOT EXISTS draft_picks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    round_number      INTEGER,
    team              TEXT,
    resource_name     TEXT,
    resource_category TEXT
)
"""

CREATE_CRAWLED_CVES = """
CREATE TABLE IF NOT EXISTS crawled_cves (
    cve_id       TEXT PRIMARY KEY,
    source       TEXT,
    severity     TEXT,
    domain       TEXT,
    description  TEXT,
    exploit_code TEXT,
    fix_hint     TEXT,
    fetched_at   TEXT
)
"""

CREATE_GAME_STATE = """
CREATE TABLE IF NOT EXISTS game_state (
    key   TEXT PRIMARY KEY,
    value TEXT
)
"""

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
]


class Database:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        for ddl in ALL_TABLES:
            await self._conn.execute(ddl)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def list_tables(self) -> list[str]:
        cursor = await self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def save_round(self, result: RoundResult) -> None:
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO rounds
                (round_number, phase, outcome, red_score, blue_threshold, red_debrief, blue_debrief)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.round_number,
                result.phase.value,
                result.outcome.value,
                result.red_score,
                result.blue_threshold,
                result.red_debrief,
                result.blue_debrief,
            ),
        )

        # Delete existing child rows so a re-save is idempotent.
        for table in ("attacks", "defenses", "draft_picks", "bug_reports", "patches"):
            await self._conn.execute(
                f"DELETE FROM {table} WHERE round_number = ?",
                (result.round_number,),
            )

        for attack in result.attacks:
            await self._conn.execute(
                """
                INSERT INTO attacks
                    (round_number, turn, description, severity, points, success, auto_win)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.round_number,
                    attack.turn,
                    attack.description,
                    attack.severity.value if attack.severity else None,
                    attack.points,
                    int(attack.success),
                    int(attack.auto_win),
                ),
            )

        for defense in result.defenses:
            await self._conn.execute(
                """
                INSERT INTO defenses
                    (round_number, turn, description, blocked, points_deducted)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    result.round_number,
                    defense.turn,
                    defense.description,
                    int(defense.blocked),
                    defense.points_deducted,
                ),
            )

        for pick in result.red_draft + result.blue_draft:
            await self._conn.execute(
                """
                INSERT INTO draft_picks
                    (round_number, team, resource_name, resource_category)
                VALUES (?, ?, ?, ?)
                """,
                (
                    result.round_number,
                    pick.team,
                    pick.resource_name,
                    pick.resource_category,
                ),
            )

        for bug in result.bug_reports:
            await self._conn.execute(
                """
                INSERT INTO bug_reports
                    (round_number, title, severity, domain, target,
                     steps_to_reproduce, proof_of_concept, impact)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.round_number,
                    bug.title,
                    bug.severity.value,
                    bug.domain.value,
                    bug.target,
                    bug.steps_to_reproduce,
                    bug.proof_of_concept,
                    bug.impact,
                ),
            )

        for patch in result.patches:
            await self._conn.execute(
                """
                INSERT INTO patches
                    (round_number, title, fixes, strategy, changes, verification)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    result.round_number,
                    patch.title,
                    patch.fixes,
                    patch.strategy,
                    patch.changes,
                    patch.verification,
                ),
            )

        await self._conn.commit()

    async def get_round(self, round_number: int) -> RoundResult:
        cursor = await self._conn.execute(
            "SELECT * FROM rounds WHERE round_number = ?", (round_number,)
        )
        row = await cursor.fetchone()
        if row is None:
            raise KeyError(f"Round {round_number} not found")

        # Attacks
        cur_a = await self._conn.execute(
            "SELECT * FROM attacks WHERE round_number = ? ORDER BY id", (round_number,)
        )
        attack_rows = await cur_a.fetchall()
        attacks = [
            AttackResult(
                turn=r["turn"],
                description=r["description"],
                severity=Severity(r["severity"]) if r["severity"] else None,
                points=r["points"],
                success=bool(r["success"]),
                auto_win=bool(r["auto_win"]),
            )
            for r in attack_rows
        ]

        # Defenses
        cur_d = await self._conn.execute(
            "SELECT * FROM defenses WHERE round_number = ? ORDER BY id", (round_number,)
        )
        defense_rows = await cur_d.fetchall()
        defenses = [
            DefenseResult(
                turn=r["turn"],
                description=r["description"],
                blocked=bool(r["blocked"]),
                points_deducted=r["points_deducted"],
            )
            for r in defense_rows
        ]

        # Draft picks
        cur_p = await self._conn.execute(
            "SELECT * FROM draft_picks WHERE round_number = ? ORDER BY id", (round_number,)
        )
        pick_rows = await cur_p.fetchall()
        red_draft = [
            DraftPick(
                round=round_number,
                team=r["team"],
                resource_name=r["resource_name"],
                resource_category=r["resource_category"],
            )
            for r in pick_rows
            if r["team"] == "red"
        ]
        blue_draft = [
            DraftPick(
                round=round_number,
                team=r["team"],
                resource_name=r["resource_name"],
                resource_category=r["resource_category"],
            )
            for r in pick_rows
            if r["team"] == "blue"
        ]

        return RoundResult(
            round_number=row["round_number"],
            phase=Phase(row["phase"]),
            outcome=MatchOutcome(row["outcome"]),
            red_score=row["red_score"],
            blue_threshold=row["blue_threshold"],
            red_draft=red_draft,
            blue_draft=blue_draft,
            attacks=attacks,
            defenses=defenses,
            red_debrief=row["red_debrief"] or "",
            blue_debrief=row["blue_debrief"] or "",
        )

    async def get_season_stats(self) -> dict:
        cursor = await self._conn.execute(
            """
            SELECT
                SUM(outcome = 'red_win')      AS red_wins,
                SUM(outcome = 'blue_win')     AS blue_wins,
                SUM(outcome = 'red_auto_win') AS auto_wins,
                COUNT(*)                      AS total_rounds
            FROM rounds
            """
        )
        row = await cursor.fetchone()
        return {
            "red_wins": row["red_wins"] or 0,
            "blue_wins": row["blue_wins"] or 0,
            "auto_wins": row["auto_wins"] or 0,
            "total_rounds": row["total_rounds"] or 0,
        }

    async def set_game_state(self, key: str, value: str) -> None:
        await self._conn.execute(
            "INSERT OR REPLACE INTO game_state (key, value) VALUES (?, ?)",
            (key, value),
        )
        await self._conn.commit()

    async def get_game_state(self, key: str) -> str | None:
        cursor = await self._conn.execute(
            "SELECT value FROM game_state WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        return row["value"] if row else None

    async def get_cves(self, limit: int = 20) -> list[dict]:
        cursor = await self._conn.execute(
            "SELECT * FROM crawled_cves ORDER BY ROWID DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def save_cve(self, cve: dict) -> None:
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO crawled_cves
                (cve_id, source, severity, domain, description, exploit_code, fix_hint, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cve.get("cve_id"),
                cve.get("source"),
                cve.get("severity"),
                cve.get("domain"),
                cve.get("description"),
                cve.get("exploit_code"),
                cve.get("fix_hint"),
                cve.get("fetched_at"),
            ),
        )
        await self._conn.commit()
