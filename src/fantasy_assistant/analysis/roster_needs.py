"""Compares your roster's strength at each position against the league
average, to flag which positions are actual weak spots — the "roster
construction needs" half of personalizing recommendations, rather than
just showing league-wide trending players and leaving you to guess whether
they'd help your specific team.

Heuristic, not a model: need_score is just (my avg rank - league avg rank)
at a position, using whichever rank source matches the league's platform.
Positive means your players there are worse-ranked than a typical roster's,
i.e. a real gap; negative means it's a relative strength. The 'weak'/'ok'/
'strong' labels use simple fixed thresholds — a starting point to react to,
not a precise measurement.
"""

from __future__ import annotations

import sqlite3

FANTASY_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")
WEAK_THRESHOLD = 20
STRONG_THRESHOLD = -20

_RANK_SOURCE_BY_PLATFORM = {
    "sleeper": "sleeper_search_rank",
    "espn": "espn_standard_rank",
}


class RosterNeedsError(ValueError):
    pass


def compute_roster_needs(conn: sqlite3.Connection, league_id: str, my_owner_id: str) -> list[dict]:
    league = conn.execute("SELECT platform FROM leagues WHERE league_id = ?", (league_id,)).fetchone()
    if not league:
        raise RosterNeedsError(f"League {league_id} hasn't been synced yet.")
    platform = league["platform"]

    my_roster = conn.execute(
        "SELECT roster_id FROM rosters WHERE league_id = ? AND owner_id = ?", (league_id, my_owner_id)
    ).fetchone()
    if not my_roster:
        raise RosterNeedsError(f"No roster found for owner_id {my_owner_id} in league {league_id}.")
    my_roster_id = my_roster["roster_id"]

    source = _RANK_SOURCE_BY_PLATFORM.get(platform)
    ranks = {}
    if source:
        rows = conn.execute(
            "SELECT player_id, overall_rank FROM player_rankings WHERE platform = ? AND source = ?",
            (platform, source),
        ).fetchall()
        ranks = {row["player_id"]: row["overall_rank"] for row in rows}

    rostered = conn.execute(
        """
        SELECT rp.roster_id, rp.player_id, p.position
        FROM roster_players rp
        JOIN players p ON p.player_id = rp.player_id AND p.platform = ?
        WHERE rp.league_id = ? AND p.position IN (%s)
        """
        % ",".join("?" * len(FANTASY_POSITIONS)),
        (platform, league_id, *FANTASY_POSITIONS),
    ).fetchall()

    by_position_league: dict[str, list[float]] = {pos: [] for pos in FANTASY_POSITIONS}
    by_position_mine: dict[str, list[float]] = {pos: [] for pos in FANTASY_POSITIONS}
    my_counts: dict[str, int] = dict.fromkeys(FANTASY_POSITIONS, 0)

    for row in rostered:
        rank = ranks.get(row["player_id"])
        if row["roster_id"] == my_roster_id:
            my_counts[row["position"]] += 1
        if rank is None:
            continue
        by_position_league[row["position"]].append(rank)
        if row["roster_id"] == my_roster_id:
            by_position_mine[row["position"]].append(rank)

    results = []
    for pos in FANTASY_POSITIONS:
        league_ranks = by_position_league[pos]
        my_ranks = by_position_mine[pos]
        if not league_ranks:
            continue  # no ranked players at this position league-wide, nothing to compare
        league_avg = sum(league_ranks) / len(league_ranks)

        if not my_ranks:
            need_score = None  # you have zero ranked players at this position — can't average, but it's a gap
            my_avg = None
            need_level = "weak"
        else:
            my_avg = sum(my_ranks) / len(my_ranks)
            need_score = my_avg - league_avg
            need_level = "weak" if need_score > WEAK_THRESHOLD else "strong" if need_score < STRONG_THRESHOLD else "ok"

        results.append(
            {
                "position": pos,
                "my_avg_rank": round(my_avg, 1) if my_avg is not None else None,
                "my_player_count": my_counts[pos],
                "league_avg_rank": round(league_avg, 1),
                "need_score": round(need_score, 1) if need_score is not None else None,
                "need_level": need_level,
            }
        )

    # Positions with no ranked players at all sort first (most urgent, can't even quantify),
    # then by descending need_score (biggest real gap next).
    results.sort(key=lambda r: (0, 0) if r["need_score"] is None else (1, -r["need_score"]))
    return results
