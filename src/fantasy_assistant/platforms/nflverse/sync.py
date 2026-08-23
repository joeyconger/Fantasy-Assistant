"""Caches nflverse's advanced weekly stats into SQLite. Cached per-season
(12h TTL, same cadence as KTC/FFC/FantasyPros) since the source file is a
combined all-seasons CSV re-fetched each time — cheap to skip on a cache
hit, since it means downloading nothing."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from ..matching import normalize_name
from .client import NflverseClient

CACHE_TTL = timedelta(hours=12)


def sync_weekly_stats(conn: sqlite3.Connection, client: NflverseClient, season: int, force: bool = False) -> int:
    row = conn.execute(
        "SELECT fetched_at FROM advanced_stats_cache_meta WHERE source = 'nflverse' AND season = ?", (season,)
    ).fetchone()
    if row and not force:
        fetched_at = datetime.fromisoformat(row["fetched_at"])
        if datetime.now(timezone.utc) - fetched_at < CACHE_TTL:
            return 0

    rows = client.get_weekly_stats(season)
    now = datetime.now(timezone.utc).isoformat()

    conn.execute("DELETE FROM advanced_stats WHERE source = 'nflverse' AND season = ?", (season,))

    count = 0
    for r in rows:
        if r["week"] is None:
            continue
        conn.execute(
            """
            INSERT INTO advanced_stats (
                source, season, week, normalized_name, full_name, position, team,
                targets, target_share, air_yards_share, wopr, racr, fetched_at
            ) VALUES ('nflverse', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, season, week, normalized_name, position) DO UPDATE SET
                full_name=excluded.full_name,
                team=excluded.team,
                targets=excluded.targets,
                target_share=excluded.target_share,
                air_yards_share=excluded.air_yards_share,
                wopr=excluded.wopr,
                racr=excluded.racr,
                fetched_at=excluded.fetched_at
            """,
            (
                season,
                r["week"],
                normalize_name(r["full_name"]),
                r["full_name"],
                r["position"],
                r["team"],
                r["targets"],
                r["target_share"],
                r["air_yards_share"],
                r["wopr"],
                r["racr"],
                now,
            ),
        )
        count += 1

    conn.execute(
        """
        INSERT INTO advanced_stats_cache_meta (source, season, fetched_at) VALUES ('nflverse', ?, ?)
        ON CONFLICT(source, season) DO UPDATE SET fetched_at=excluded.fetched_at
        """,
        (season, now),
    )
    conn.commit()
    return count


def get_player_advanced_stats(conn: sqlite3.Connection, full_name: str, season: int) -> list[sqlite3.Row]:
    """Every synced week's advanced stats for one player this season, most
    recent week first."""
    return conn.execute(
        "SELECT * FROM advanced_stats WHERE source = 'nflverse' AND season = ? AND normalized_name = ? ORDER BY week DESC",
        (season, normalize_name(full_name)),
    ).fetchall()
