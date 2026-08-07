"""Caches FantasyPros consensus rankings into SQLite, 12h TTL."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from ..matching import normalize_name
from .client import FantasyProsClient

CACHE_TTL = timedelta(hours=12)


def sync_rankings(conn: sqlite3.Connection, client: FantasyProsClient, force: bool = False) -> int:
    row = conn.execute(
        "SELECT fetched_at FROM expert_rankings_cache_meta WHERE source = 'fantasypros' AND format = 'redraft'"
    ).fetchone()
    if row and not force:
        fetched_at = datetime.fromisoformat(row["fetched_at"])
        if datetime.now(timezone.utc) - fetched_at < CACHE_TTL:
            return 0

    players = client.get_consensus_rankings()
    now = datetime.now(timezone.utc).isoformat()

    conn.execute("DELETE FROM expert_rankings_prior WHERE source = 'fantasypros' AND format = 'redraft'")
    conn.execute(
        """
        INSERT INTO expert_rankings_prior (source, format, normalized_name, position, overall_rank, fetched_at)
        SELECT source, format, normalized_name, position, overall_rank, fetched_at
        FROM expert_rankings WHERE source = 'fantasypros' AND format = 'redraft'
        """
    )

    conn.execute("DELETE FROM expert_rankings WHERE source = 'fantasypros' AND format = 'redraft'")
    count = 0
    for p in players:
        if not p.get("full_name"):
            continue
        conn.execute(
            """
            INSERT INTO expert_rankings (source, format, normalized_name, full_name, position, team, overall_rank, fetched_at)
            VALUES ('fantasypros', 'redraft', ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, format, normalized_name, position) DO UPDATE SET
                full_name=excluded.full_name,
                team=excluded.team,
                overall_rank=excluded.overall_rank,
                fetched_at=excluded.fetched_at
            """,
            (
                normalize_name(p["full_name"]),
                p["full_name"],
                p.get("position") or "",
                p.get("team"),
                p.get("overall_rank"),
                now,
            ),
        )
        count += 1

    conn.execute(
        """
        INSERT INTO expert_rankings_cache_meta (source, format, fetched_at) VALUES ('fantasypros', 'redraft', ?)
        ON CONFLICT(source, format) DO UPDATE SET fetched_at=excluded.fetched_at
        """,
        (now,),
    )
    conn.commit()
    return count
