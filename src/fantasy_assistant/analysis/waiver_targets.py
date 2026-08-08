"""Surfaces waiver-wire pickups (available, trending up) and trade targets
(rostered elsewhere, trending up) using performance trend + rank.

Personalized when my_owner_id is passed (see config/leagues.yaml — run
`fantasy-assistant owners LEAGUE_ID` to find yours): candidates get a
fills_need tag based on your roster's actual positional weak spots
(analysis/roster_needs.py), and top_trade_targets excludes players already
on your own roster (you can't trade for what you have). Without
my_owner_id, everything still works exactly as before — league-wide
trending players, no personalization, your own judgment on fit.
"""

from __future__ import annotations

import sqlite3

from .performance_trend import compute_trends
from .roster_needs import RosterNeedsError, compute_roster_needs

FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}

# Each platform's overall-rank proxy lives under a different source label
# (see player_rankings). ESPN's is only populated by sync-rankings, which
# hits a separate, unverified endpoint from the roster sync — see README.
_RANK_SOURCE_BY_PLATFORM = {
    "sleeper": "sleeper_search_rank",
    "espn": "espn_standard_rank",
}


def _league_platform(conn: sqlite3.Connection, league_id: str) -> str:
    row = conn.execute("SELECT platform FROM leagues WHERE league_id = ?", (league_id,)).fetchone()
    if not row:
        raise ValueError(f"League {league_id} hasn't been synced yet.")
    return row["platform"]


def _rostered_player_ids(conn: sqlite3.Connection, league_id: str) -> set[str]:
    rows = conn.execute("SELECT DISTINCT player_id FROM roster_players WHERE league_id = ?", (league_id,)).fetchall()
    return {row["player_id"] for row in rows}


def _rank_lookup(conn: sqlite3.Connection, platform: str) -> dict[str, int]:
    source = _RANK_SOURCE_BY_PLATFORM.get(platform)
    if not source:
        return {}
    rows = conn.execute(
        "SELECT player_id, overall_rank FROM player_rankings WHERE platform = ? AND source = ?", (platform, source)
    ).fetchall()
    return {row["player_id"]: row["overall_rank"] for row in rows}


def _needs_by_position(conn: sqlite3.Connection, league_id: str, my_owner_id: str | None) -> dict[str, str]:
    if not my_owner_id:
        return {}
    try:
        needs = compute_roster_needs(conn, league_id, my_owner_id)
    except RosterNeedsError:
        return {}
    return {n["position"]: n["need_level"] for n in needs}


def top_waiver_adds(conn: sqlite3.Connection, league_id: str, limit: int = 15, my_owner_id: str | None = None) -> list[dict]:
    platform = _league_platform(conn, league_id)
    rostered = _rostered_player_ids(conn, league_id)
    trends = compute_trends(conn, league_id)
    ranks = _rank_lookup(conn, platform)
    needs = _needs_by_position(conn, league_id, my_owner_id)

    players = conn.execute(
        "SELECT player_id, full_name, position, team FROM players WHERE platform = ? AND position IN (%s)"
        % ",".join("?" * len(FANTASY_POSITIONS)),
        (platform, *FANTASY_POSITIONS),
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
                "fills_need": (needs.get(p["position"]) == "weak") if needs else None,
            }
        )

    candidates.sort(key=lambda c: c["recent_avg"], reverse=True)
    return candidates[:limit]


def top_trade_targets(
    conn: sqlite3.Connection, league_id: str, limit: int = 15, min_trend: float = 2.0, my_owner_id: str | None = None
) -> list[dict]:
    platform = _league_platform(conn, league_id)
    trends = compute_trends(conn, league_id)
    ranks = _rank_lookup(conn, platform)
    needs = _needs_by_position(conn, league_id, my_owner_id)

    my_roster_id = None
    if my_owner_id:
        my_roster = conn.execute(
            "SELECT roster_id FROM rosters WHERE league_id = ? AND owner_id = ?", (league_id, my_owner_id)
        ).fetchone()
        my_roster_id = my_roster["roster_id"] if my_roster else None

    rows = conn.execute(
        """
        SELECT rp.roster_id, rp.player_id, p.full_name, p.position, p.team,
               COALESCE(o.team_name, o.display_name, 'Roster ' || rp.roster_id) AS owned_by
        FROM roster_players rp
        JOIN players p ON p.player_id = rp.player_id AND p.platform = ?
        LEFT JOIN rosters r ON r.league_id = rp.league_id AND r.roster_id = rp.roster_id
        LEFT JOIN owners o ON o.league_id = r.league_id AND o.owner_id = r.owner_id
        WHERE rp.league_id = ?
        """,
        (platform, league_id),
    ).fetchall()

    candidates = []
    for row in rows:
        if my_roster_id is not None and row["roster_id"] == my_roster_id:
            continue  # can't trade for a player you already own
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
                "fills_need": (needs.get(row["position"]) == "weak") if needs else None,
            }
        )

    candidates.sort(key=lambda c: c["trend"], reverse=True)
    return candidates[:limit]
