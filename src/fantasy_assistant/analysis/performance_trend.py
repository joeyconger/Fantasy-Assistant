"""Computes recent-vs-season points trend per player, from player_weekly_points."""

from __future__ import annotations

import sqlite3


def compute_trends(conn: sqlite3.Connection, league_id: str, recent_weeks: int = 3) -> dict[str, dict]:
    """Returns {player_id: {season_avg, recent_avg, trend, weeks_played}} for
    every player with any recorded points in this league.

    trend = recent_avg - season_avg (positive = trending up recently).
    Players with fewer than `recent_weeks` total weeks played are still
    included (recent_avg then covers however many weeks exist), since a
    fresh waiver pickup shouldn't be excluded just for lacking history.
    """
    rows = conn.execute(
        "SELECT player_id, week, points FROM player_weekly_points WHERE league_id = ? ORDER BY player_id, week",
        (league_id,),
    ).fetchall()

    by_player: dict[str, list[tuple[int, float]]] = {}
    for row in rows:
        by_player.setdefault(row["player_id"], []).append((row["week"], row["points"] or 0.0))

    trends = {}
    for player_id, weeks in by_player.items():
        weeks.sort()
        points = [p for _, p in weeks]
        season_avg = sum(points) / len(points)
        recent = points[-recent_weeks:]
        recent_avg = sum(recent) / len(recent)
        trends[player_id] = {
            "season_avg": round(season_avg, 2),
            "recent_avg": round(recent_avg, 2),
            "trend": round(recent_avg - season_avg, 2),
            "weeks_played": len(points),
        }
    return trends
