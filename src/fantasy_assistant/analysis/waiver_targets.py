"""Surfaces waiver-wire pickups (available, trending up) and trade targets
(rostered elsewhere, trending up) using performance trend + rank.

NOT YET BUILT: personalizing this to "my roster" specifically (auto-detecting
which team is yours and its positional needs) — that needs a `my_owner_id`
config value per league and a needs-gap calculation this doesn't do yet.
Right now this surfaces trending players league-wide; you still apply your
own judgment about whether they fill a hole on your specific team.
"""

from __future__ import annotations

import sqlite3

from .performance_trend import compute_trends

FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}


def _rostered_player_ids(conn: sqlite3.Connection, league_id: str) -> set[str]:
    rows = conn.execute("SELECT DISTINCT player_id FROM roster_players WHERE league_id = ?", (league_id,)).fetchall()
    return {row["player_id"] for row in rows}


def _rank_lookup(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT player_id, overall_rank FROM player_rankings WHERE platform = 'sleeper' AND source = 'sleeper_search_rank'"
    ).fetchall()
    return {row["player_id"]: row["overall_rank"] for row in rows}


def top_waiver_adds(conn: sqlite3.Connection, league_id: str, limit: int = 15) -> list[dict]:
    rostered = _rostered_player_ids(conn, league_id)
    trends = compute_trends(conn, league_id)
    ranks = _rank_lookup(conn)

    players = conn.execute(
        "SELECT player_id, full_name, position, team FROM players WHERE platform = 'sleeper' AND position IN (%s)"
        % ",".join("?" * len(FANTASY_POSITIONS)),
        tuple(FANTASY_POSITIONS),
    ).fetchall()

    candidates = []
    for p in players:
        if p["player_id"] in rostered:
            continue
        trend = trends.get(p["player_id"])
        if not trend or trend["recent_avg"] <= 0:
            continue
        candidates.append(
            {
                "player_id": p["player_id"],
                "name": p["full_name"],
                "position": p["position"],
                "team": p["team"],
                "recent_avg": trend["recent_avg"],
                "season_avg": trend["season_avg"],
                "trend": trend["trend"],
                "rank": ranks.get(p["player_id"]),
            }
        )

    candidates.sort(key=lambda c: c["recent_avg"], reverse=True)
    return candidates[:limit]


def top_trade_targets(conn: sqlite3.Connection, league_id: str, limit: int = 15, min_trend: float = 2.0) -> list[dict]:
    trends = compute_trends(conn, league_id)
    ranks = _rank_lookup(conn)

    rows = conn.execute(
        """
        SELECT rp.player_id, p.full_name, p.position, p.team,
               COALESCE(o.team_name, o.display_name, 'Roster ' || rp.roster_id) AS owned_by
        FROM roster_players rp
        JOIN players p ON p.player_id = rp.player_id AND p.platform = 'sleeper'
        LEFT JOIN rosters r ON r.league_id = rp.league_id AND r.roster_id = rp.roster_id
        LEFT JOIN owners o ON o.league_id = r.league_id AND o.owner_id = r.owner_id
        WHERE rp.league_id = ?
        """,
        (league_id,),
    ).fetchall()

    candidates = []
    for row in rows:
        trend = trends.get(row["player_id"])
        if not trend or trend["trend"] < min_trend:
            continue
        candidates.append(
            {
                "player_id": row["player_id"],
                "name": row["full_name"],
                "position": row["position"],
                "team": row["team"],
                "owned_by": row["owned_by"],
                "recent_avg": trend["recent_avg"],
                "season_avg": trend["season_avg"],
                "trend": trend["trend"],
                "rank": ranks.get(row["player_id"]),
            }
        )

    candidates.sort(key=lambda c: c["trend"], reverse=True)
    return candidates[:limit]
