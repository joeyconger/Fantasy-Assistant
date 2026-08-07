"""Persists Reddit sentiment scores into player_sentiment."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def sync_sentiment(conn: sqlite3.Connection, scored: dict[str, dict]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    for norm, data in scored.items():
        conn.execute(
            """
            INSERT INTO player_sentiment (normalized_name, source, full_name, mention_count, positive_count, negative_count, net_score, fetched_at)
            VALUES (?, 'reddit', ?, ?, ?, ?, ?, ?)
            ON CONFLICT(normalized_name, source) DO UPDATE SET
                full_name=excluded.full_name,
                mention_count=excluded.mention_count,
                positive_count=excluded.positive_count,
                negative_count=excluded.negative_count,
                net_score=excluded.net_score,
                fetched_at=excluded.fetched_at
            """,
            (
                norm,
                data["full_name"],
                data["mention_count"],
                data["positive_count"],
                data["negative_count"],
                data["net_score"],
                now,
            ),
        )
        count += 1
    conn.commit()
    return count


def tracked_player_names(conn: sqlite3.Connection) -> list[str]:
    """Players worth watching for sentiment: anyone rostered in any synced
    league. Scoped this way (rather than the whole ~12k NFL pool) so mention
    matching stays fast and relevant to leagues you're actually in."""
    rows = conn.execute(
        """
        SELECT DISTINCT p.full_name
        FROM roster_players rp
        JOIN leagues l ON l.league_id = rp.league_id
        JOIN players p ON p.player_id = rp.player_id AND p.platform = l.platform
        WHERE p.full_name IS NOT NULL
        """
    ).fetchall()
    return [row["full_name"] for row in rows]
