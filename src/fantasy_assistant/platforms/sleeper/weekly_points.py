"""Syncs per-player weekly fantasy points for a league, from Sleeper's
matchups endpoint. Powers the performance-trend signal used by waiver
targeting and the buy-low/sell-high engine.

Note: snap share, target share, and red zone usage — also named in the
original spec as trend signals — are NOT available from Sleeper or ESPN's
public APIs. This module only covers fantasy points scored. Snap/target/RZ
data would need an additional stats source (e.g. nflverse/nflfastR) that
isn't wired in yet.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .client import SleeperClient


def sync_weekly_points(conn: sqlite3.Connection, client: SleeperClient, league_id: str, weeks: list[int]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    for week in weeks:
        matchups = client.get_matchups(league_id, week)
        for roster in matchups:
            players_points = roster.get("players_points") or {}
            for player_id, points in players_points.items():
                conn.execute(
                    """
                    INSERT INTO player_weekly_points (league_id, player_id, week, points, fetched_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(league_id, player_id, week) DO UPDATE SET
                        points=excluded.points,
                        fetched_at=excluded.fetched_at
                    """,
                    (league_id, player_id, week, points, now),
                )
                count += 1

    conn.commit()
    return count


def current_completed_weeks(client: SleeperClient, lookback: int = 4) -> list[int]:
    """Returns up to `lookback` most recent NFL weeks that should have data,
    based on Sleeper's current-state endpoint. Empty during preseason/week 1."""
    state = client.get_nfl_state()
    current_week = state.get("week") or 0
    last_completed = current_week - 1 if state.get("season_type") == "regular" else 0
    if last_completed < 1:
        return []
    start = max(1, last_completed - lookback + 1)
    return list(range(start, last_completed + 1))
