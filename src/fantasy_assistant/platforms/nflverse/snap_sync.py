"""Caches nflverse's weekly snap counts into SQLite. Same per-season 12h
cache pattern as sync.py (get_weekly_stats' cache) — kept in a separate
module/table entirely so this sync's full-season DELETE-then-reinsert
can never clobber the other dataset's rows for that season."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from ..matching import normalize_name
from .client import NflverseClient

CACHE_TTL = timedelta(hours=12)


def sync_snap_counts(conn: sqlite3.Connection, client: NflverseClient, season: int, force: bool = False) -> int:
    row = conn.execute(
        "SELECT fetched_at FROM snap_counts_cache_meta WHERE source = 'nflverse' AND season = ?", (season,)
    ).fetchone()
    if row and not force:
        fetched_at = datetime.fromisoformat(row["fetched_at"])
        if datetime.now(timezone.utc) - fetched_at < CACHE_TTL:
            return 0

    rows = client.get_snap_counts(season)
    now = datetime.now(timezone.utc).isoformat()

    conn.execute("DELETE FROM snap_counts WHERE source = 'nflverse' AND season = ?", (season,))

    count = 0
    for r in rows:
        if r["week"] is None:
            continue
        conn.execute(
            """
            INSERT INTO snap_counts (
                source, season, week, normalized_name, full_name, position, team,
                offense_snaps, offense_pct, fetched_at
            ) VALUES ('nflverse', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, season, week, normalized_name, position) DO UPDATE SET
                full_name=excluded.full_name,
                team=excluded.team,
                offense_snaps=excluded.offense_snaps,
                offense_pct=excluded.offense_pct,
                fetched_at=excluded.fetched_at
            """,
            (
                season,
                r["week"],
                normalize_name(r["full_name"]),
                r["full_name"],
                r["position"],
                r["team"],
                r["offense_snaps"],
                r["offense_pct"],
                now,
            ),
        )
        count += 1

    conn.execute(
        """
        INSERT INTO snap_counts_cache_meta (source, season, fetched_at) VALUES ('nflverse', ?, ?)
        ON CONFLICT(source, season) DO UPDATE SET fetched_at=excluded.fetched_at
        """,
        (season, now),
    )
    conn.commit()
    return count


def get_player_snap_counts(conn: sqlite3.Connection, full_name: str, season: int) -> list[sqlite3.Row]:
    """Every synced week's snap counts for one player this season, most
    recent week first."""
    return conn.execute(
        "SELECT * FROM snap_counts WHERE source = 'nflverse' AND season = ? AND normalized_name = ? ORDER BY week DESC",
        (season, normalize_name(full_name)),
    ).fetchall()
