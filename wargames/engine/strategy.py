from __future__ import annotations

import json

from wargames.models import RoundResult, Strategy

EXTRACT_SYSTEM_PROMPT = """You are an analyst extracting reusable strategies from a cybersecurity war games debrief.

Parse the debrief text and extract distinct strategies the team used. Categorize each as:
- "attack": offensive techniques used by the red team
- "defense": defensive countermeasures used by the blue team
- "draft": resource selection or draft strategies

Respond ONLY with a valid JSON array of objects in this exact format:
[{"strategy_type": str, "content": str}, ...]

Extract 1-5 strategies. If nothing useful can be extracted, return an empty array []."""


async def extract_strategies(result: RoundResult, team: str, llm) -> list[Strategy]:
    """Use LLM to parse debrief text into structured Strategy objects."""
    debrief = result.red_debrief if team == "red" else result.blue_debrief
    if not debrief or not debrief.strip():
        return []

    user_message = (
        f"Team: {team}\n"
        f"Round: {result.round_number}\n"
        f"Phase: {result.phase.value}\n\n"
        f"Debrief:\n{debrief}"
    )

    raw = await llm.chat(
        messages=[{"role": "user", "content": user_message}],
        system=EXTRACT_SYSTEM_PROMPT,
    )

    try:
        items = json.loads(raw)
        if not isinstance(items, list):
            return []
    except (json.JSONDecodeError, ValueError):
        return []

    strategies = []
    for item in items:
        if not isinstance(item, dict):
            continue
        strategy_type = item.get("strategy_type", "")
        content = item.get("content", "")
        if strategy_type and content:
            strategies.append(
                Strategy(
                    team=team,
                    phase=result.phase.value,
                    strategy_type=strategy_type,
                    content=content,
                    created_round=result.round_number,
                )
            )

    return strategies


async def save_strategies(strategies: list[Strategy], db) -> None:
    """Insert Strategy objects into the strategies table."""
    for s in strategies:
        await db._conn.execute(
            """
            INSERT INTO strategies
                (team, phase, strategy_type, content, win_rate, usage_count, created_round)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                s.team,
                s.phase,
                s.strategy_type,
                s.content,
                s.win_rate,
                s.usage_count,
                s.created_round,
            ),
        )
    await db._conn.commit()


async def get_top_strategies(
    team: str, phase: int, db, limit: int = 5
) -> list[Strategy]:
    """Query DB for top strategies ordered by win_rate DESC."""
    cursor = await db._conn.execute(
        """
        SELECT team, phase, strategy_type, content, win_rate, usage_count, created_round
        FROM strategies
        WHERE team = ? AND phase = ?
        ORDER BY win_rate DESC
        LIMIT ?
        """,
        (team, phase, limit),
    )
    rows = await cursor.fetchall()
    return [
        Strategy(
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


async def update_win_rates(team: str, phase: int, round_won: bool, db) -> None:
    """Update win_rate for all strategies of a team/phase using running average."""
    win_val = 1.0 if round_won else 0.0

    cursor = await db._conn.execute(
        "SELECT id, win_rate, usage_count FROM strategies WHERE team = ? AND phase = ?",
        (team, phase),
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
