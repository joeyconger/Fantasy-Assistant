"""Caches Fantasy Football Calculator's real ADP into SQLite, 12h TTL —
same cadence as FantasyPros. Used by the redraft draft board in place of
Sleeper's search_rank (see analysis/draft_board.py)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from ..matching import normalize_name
from .client import FFCClient

CACHE_TTL = timedelta(hours=12)


def sync_adp(conn: sqlite3.Connection, client: FFCClient, qb_mode: str = "1qb", teams: int = 12, force: bool = False) -> int:
    row = conn.execute(
        "SELECT fetched_at FROM draft_adp_cache_meta WHERE source = 'ffc' AND qb_mode = ?", (qb_mode,)
    ).fetchone()
    if row and not force:
        fetched_at = datetime.fromisoformat(row["fetched_at"])
        if datetime.now(timezone.utc) - fetched_at < CACHE_TTL:
            return 0

    players = client.get_adp(qb_mode, teams=teams)
    now = datetime.now(timezone.utc).isoformat()

    conn.execute("DELETE FROM draft_adp WHERE source = 'ffc' AND qb_mode = ?", (qb_mode,))

    # FFC's response is already sorted by ADP ascending (best player first);
    # the 1-indexed position in that order becomes overall_rank, since
    # draft_board.py compares ordinal ranks, not raw ADP floats. The raw
    # ADP value is kept too, in case it's useful for display later.
    count = 0
    for i, p in enumerate(players, start=1):
        name = p.get("name")
        if not name:
            continue
        conn.execute(
            """
            INSERT INTO draft_adp (source, qb_mode, normalized_name, full_name, position, team, overall_rank, adp, fetched_at)
            VALUES ('ffc', ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, qb_mode, normalized_name, position) DO UPDATE SET
                full_name=excluded.full_name,
                team=excluded.team,
                overall_rank=excluded.overall_rank,
                adp=excluded.adp,
                fetched_at=excluded.fetched_at
            """,
            (qb_mode, normalize_name(name), name, p.get("position") or "", p.get("team"), i, p.get("adp"), now),
        )
        count += 1

    conn.execute(
        """
        INSERT INTO draft_adp_cache_meta (source, qb_mode, fetched_at) VALUES ('ffc', ?, ?)
        ON CONFLICT(source, qb_mode) DO UPDATE SET fetched_at=excluded.fetched_at
        """,
        (qb_mode, now),
    )
    conn.commit()
    return count
