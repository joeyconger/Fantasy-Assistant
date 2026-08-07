"""Finds "inefficiencies" — players where Sleeper and ESPN disagree sharply
on overall rank. A big gap means one platform's ADP/rank has this player
priced very differently than the other's, which is a real signal for value
picks in whichever draft uses the lower-ranking source.

Both platforms' raw ranks are clipped to a shared top-N before comparing.
Sleeper's search_rank spans its entire ~12,000-player pool while ESPN's pool
here is filtered to ~2,000 — comparing raw ordinals across mismatched-size
universes would produce meaningless deltas out past the draftable range, so
we only compare players both sources consider draft-relevant.
"""

from __future__ import annotations

import sqlite3

from ..platforms.matching import match_players

DEFAULT_RANK_CAP = 300


def _rank_map(conn: sqlite3.Connection, platform: str, source: str) -> dict[str, int]:
    rows = conn.execute(
        "SELECT player_id, overall_rank FROM player_rankings WHERE platform = ? AND source = ? AND overall_rank IS NOT NULL",
        (platform, source),
    ).fetchall()
    return {row["player_id"]: row["overall_rank"] for row in rows}


def find_rank_inefficiencies(conn: sqlite3.Connection, limit: int = 25, rank_cap: int = DEFAULT_RANK_CAP) -> list[dict]:
    sleeper_ranks = _rank_map(conn, "sleeper", "sleeper_search_rank")
    espn_ranks = _rank_map(conn, "espn", "espn_standard_rank")

    matches = match_players(conn, "sleeper", "espn")

    results = []
    for m in matches:
        sleeper_rank = sleeper_ranks.get(m["a_player_id"])
        espn_rank = espn_ranks.get(m["b_player_id"])
        if sleeper_rank is None or espn_rank is None:
            continue
        if sleeper_rank > rank_cap or espn_rank > rank_cap:
            continue

        delta = sleeper_rank - espn_rank
        results.append(
            {
                "name": m["name"].title(),
                "position": m["position"],
                "sleeper_player_id": m["a_player_id"],
                "espn_player_id": m["b_player_id"],
                "sleeper_rank": sleeper_rank,
                "espn_rank": espn_rank,
                "delta": delta,
                "note": "ESPN values higher (Sleeper drafters may get value)"
                if delta > 0
                else "Sleeper values higher (ESPN drafters may get value)"
                if delta < 0
                else "Ranked evenly",
            }
        )

    results.sort(key=lambda r: abs(r["delta"]), reverse=True)
    return results[:limit]
