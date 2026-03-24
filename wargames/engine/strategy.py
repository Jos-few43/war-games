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
    debrief = result.red_debrief if team == 'red' else result.blue_debrief
    if not debrief or not debrief.strip():
        return []

    user_message = (
        f'Team: {team}\n'
        f'Round: {result.round_number}\n'
        f'Phase: {result.phase.value}\n\n'
        f'Debrief:\n{debrief}'
    )

    raw = await llm.chat(
        messages=[{'role': 'user', 'content': user_message}],
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
        strategy_type = item.get('strategy_type', '')
        content = item.get('content', '')
        if strategy_type and content:
            strategies.append(
                Strategy(
                    team=team,
                    phase=result.phase.value,
                    strategy_type=strategy_type,
                    content=content,
                    created_round=result.round_number,
                    # Initialize opponent modeling fields to default values
                    opp_usage_count=0,
                    opp_effectiveness=0.0,
                )
            )

    return strategies


def _word_overlap(a: str, b: str) -> float:
    """Return Jaccard similarity of word sets between two strings."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def _calculate_strategy_diversity(strategies: list[Strategy]) -> float:
    """Calculate diversity score for a list of strategies.

    Returns average pairwise dissimilarity (1 - similarity) between strategies.
    Higher score means more diverse strategies.
    """
    if len(strategies) < 2:
        return 0.0

    total_similarity = 0.0
    comparisons = 0

    for i in range(len(strategies)):
        for j in range(i + 1, len(strategies)):
            similarity = _word_overlap(strategies[i].content, strategies[j].content)
            total_similarity += similarity
            comparisons += 1

    average_similarity = total_similarity / comparisons if comparisons > 0 else 0.0
    # Return dissimilarity as diversity score
    return 1.0 - average_similarity


async def save_strategies(strategies: list[Strategy], db, *, dedup_threshold: float = 0.7) -> None:
    """Insert Strategy objects, skipping duplicates that overlap with existing strategies."""
    for s in strategies:
        # Check for duplicates against ALL strategies (active and inactive)
        cursor = await db._conn.execute(
            'SELECT content FROM strategies WHERE team = ? AND phase = ? AND strategy_type = ?',
            (s.team, s.phase, s.strategy_type),
        )
        existing_rows = await cursor.fetchall()

        is_duplicate = False
        for row in existing_rows:
            if _word_overlap(s.content, row['content']) >= dedup_threshold:
                is_duplicate = True
                break

        if is_duplicate:
            continue

        await db._conn.execute(
            """
            INSERT INTO strategies
                (team, phase, strategy_type, content, win_rate, usage_count, created_round, opp_usage_count, opp_effectiveness)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                s.team,
                s.phase,
                s.strategy_type,
                s.content,
                s.win_rate,
                s.usage_count,
                s.created_round,
                s.opp_usage_count,
                s.opp_effectiveness,
            ),
        )
    await db._conn.commit()


async def get_top_strategies(
    team: str, phase: int, db, limit: int = 5, current_round: int | None = None
) -> list[Strategy]:
    """Query DB for top active strategies, ranked by composite score with time decay."""
    if current_round is not None:
        cursor = await db._conn.execute(
            """
            SELECT id, team, phase, strategy_type, content, win_rate, usage_count, created_round,
                   opp_usage_count, opp_effectiveness,
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
            SELECT id, team, phase, strategy_type, content, win_rate, usage_count, created_round,
                   opp_usage_count, opp_effectiveness
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
            id=row['id'],
            team=row['team'],
            phase=row['phase'],
            strategy_type=row['strategy_type'],
            content=row['content'],
            win_rate=row['win_rate'],
            usage_count=row['usage_count'],
            created_round=row['created_round'],
            opp_usage_count=row['opp_usage_count'],
            opp_effectiveness=row['opp_effectiveness'],
        )
        for row in rows
    ]


async def prune_strategies(
    team: str, phase: int, db, *, min_uses: int = 3, min_win_rate: float = 0.2, max_pool: int = 20
) -> None:
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
        excess_ids = [row['id'] for row in excess_rows]
        placeholders = ','.join('?' for _ in excess_ids)
        await db._conn.execute(
            f'UPDATE strategies SET active = 0 WHERE id IN ({placeholders})',
            excess_ids,
        )
    await db._conn.commit()


async def update_win_rates(
    *, strategy_ids: list[int], round_won: bool, db, learning_rate: float = 0.1
) -> None:
    """Update strategy values using temporal difference learning (TD(0)).

    Uses TD(0) update: V(s) <- V(s) + α * [R + γ * V(s') - V(s)]
    For our case: strategy value <- strategy value + α * [reward - strategy value]
    where reward is 1.0 for win, 0.0 for loss.
    Implements adaptive learning rate equivalent to incremental averaging.
    """
    if not strategy_ids:
        return

    reward = 1.0 if round_won else 0.0
    placeholders = ','.join('?' for _ in strategy_ids)
    cursor = await db._conn.execute(
        f'SELECT id, win_rate, usage_count FROM strategies WHERE id IN ({placeholders})',
        strategy_ids,
    )
    rows = await cursor.fetchall()
    for row in rows:
        old_value = row['win_rate']
        old_count = row['usage_count']
        new_count = old_count + 1

        # TD(0) update with adaptive learning rate (equivalent to incremental averaging)
        # Alpha = 1/(n+1) where n is the usage count
        alpha = 1.0 / (old_count + 1) if old_count >= 0 else learning_rate
        td_error = reward - old_value
        new_value = old_value + alpha * td_error

        await db._conn.execute(
            'UPDATE strategies SET win_rate = ?, usage_count = ? WHERE id = ?',
            (new_value, new_count, row['id']),
        )
    await db._conn.commit()
