"""Finds "inefficiencies" — players where Sleeper and ESPN disagree sharply
on overall rank. A big gap means one platform's ADP/rank has this player
priced very differently than the other's, which is a real signal for value
picks in whichever draft uses the lower-ranking source.

Both platforms' raw ranks are clipped to a shared top-N before comparing.
Sleeper's search_rank spans its entire ~12,000-player pool while ESPN's pool
here is filtered to ~2,000 — comparing raw ordinals across mismatched-size
universes would produce meaningless deltas out past the draftable range, so
we only compare players both sources consider draft-relevant.

Defensive players are excluded outright — none of these leagues play IDP,
and defense valuation logic doesn't belong in a skill-position
market-inefficiency tool. In practice, team defenses (Sleeper labels them
"DEF", ESPN "D/ST") can never appear here anyway: match_players() only
pairs players whose position string is identical on both platforms, so
that label mismatch already keeps them from matching. This filter is real
protection only for individual defensive positions (DT/LB/CB/...), where
both platforms may use the same abbreviation.

Superflex QB-crowding confound: Sleeper's search_rank has no Superflex-aware
ordering (see roster_format.py), but ESPN's Superflex rank type genuinely
re-sorts its whole pool around Superflex QB scarcity — every QB jumps way up
the overall list, which mechanically pushes every RB/WR/TE/K down in overall
rank even though their value *relative to their own position* barely moved.
Comparing raw overall rank in that situation produces huge, fake deltas for
non-QB players that are really just measuring "how many QBs ESPN now ranks
above this guy," not a real market disagreement. QB is the one position
where that overall-rank shift *is* the real Superflex signal, so QB keeps
using overall rank; every other position switches to within-position rank
(RB vs RB, WR vs WR, ...) in Superflex mode, which stays stable across
formats since Superflex doesn't reshuffle RBs against other RBs.
"""

from __future__ import annotations

import sqlite3

from ..platforms.matching import match_players

DEFAULT_RANK_CAP = 300

# Team defense + individual defensive positions — excluded outright, not one
# of these leagues plays IDP, and D/ST doesn't fit a skill-position value tool.
DEFENSIVE_POSITIONS = {"D/ST", "DEF", "DT", "DE", "LB", "DL", "CB", "S", "DB"}

# Positions whose overall rank gets distorted by Superflex QB-crowding —
# QB is deliberately excluded, its overall-rank shift in Superflex mode is
# the real signal this tool exists to surface.
POSITION_RELATIVE_IN_SUPERFLEX = {"RB", "WR", "TE", "K"}


def _rank_map(conn: sqlite3.Connection, platform: str, source: str) -> dict[str, int]:
    rows = conn.execute(
        "SELECT player_id, overall_rank FROM player_rankings WHERE platform = ? AND source = ? AND overall_rank IS NOT NULL",
        (platform, source),
    ).fetchall()
    return {row["player_id"]: row["overall_rank"] for row in rows}


def _position_rank_map(conn: sqlite3.Connection, platform: str, rank_map: dict[str, int]) -> dict[str, int]:
    """Within-position rank (1 = best at that position) derived from the
    same overall_rank ordering already fetched — no extra data source
    needed, just re-sorted per position.

    Queries all of the platform's players rather than filtering by an
    IN (...) list of rank_map's keys — Sleeper's pool alone is ~12,000
    players, and binding that many parameters in one query risks exceeding
    SQLITE_MAX_VARIABLE_NUMBER on older sqlite3 builds (default 999 before
    3.32.0). Fetching everything and filtering in Python is cheap at this
    scale and has no such limit.
    """
    if not rank_map:
        return {}
    rows = conn.execute("SELECT player_id, position FROM players WHERE platform = ?", (platform,)).fetchall()
    position_by_id = {row["player_id"]: row["position"] for row in rows}

    buckets: dict[str, list[tuple[int, str]]] = {}
    for player_id, rank in rank_map.items():
        position = position_by_id.get(player_id)
        if not position:
            continue
        buckets.setdefault(position, []).append((rank, player_id))

    result: dict[str, int] = {}
    for position_ranks in buckets.values():
        position_ranks.sort()
        for position_rank, (_, player_id) in enumerate(position_ranks, start=1):
            result[player_id] = position_rank
    return result


def find_rank_inefficiencies(
    conn: sqlite3.Connection, limit: int = 25, rank_cap: int = DEFAULT_RANK_CAP, qb_mode: str = "1qb"
) -> list[dict]:
    """qb_mode='superflex' compares against ESPN's Superflex-specific rank
    (espn_superflex_rank) if any was found during sync — see espn/rankings.py
    for why that's not guaranteed to exist. Sleeper's search_rank doesn't
    differentiate by qb_mode at all, so the Sleeper side is unaffected by
    this parameter either way — see the module docstring for how that's
    handled for non-QB positions."""
    espn_source = "espn_superflex_rank" if qb_mode == "superflex" else "espn_standard_rank"
    sleeper_ranks = _rank_map(conn, "sleeper", "sleeper_search_rank")
    espn_ranks = _rank_map(conn, "espn", espn_source)

    sleeper_position_ranks = _position_rank_map(conn, "sleeper", sleeper_ranks) if qb_mode == "superflex" else {}
    espn_position_ranks = _position_rank_map(conn, "espn", espn_ranks) if qb_mode == "superflex" else {}

    matches = match_players(conn, "sleeper", "espn")

    results = []
    for m in matches:
        if m["position"] in DEFENSIVE_POSITIONS:
            continue

        sleeper_overall = sleeper_ranks.get(m["a_player_id"])
        espn_overall = espn_ranks.get(m["b_player_id"])
        if sleeper_overall is None or espn_overall is None:
            continue
        if sleeper_overall > rank_cap or espn_overall > rank_cap:
            continue

        position_relative = qb_mode == "superflex" and m["position"] in POSITION_RELATIVE_IN_SUPERFLEX
        if position_relative:
            sleeper_rank = sleeper_position_ranks.get(m["a_player_id"], sleeper_overall)
            espn_rank = espn_position_ranks.get(m["b_player_id"], espn_overall)
        else:
            sleeper_rank = sleeper_overall
            espn_rank = espn_overall

        delta = sleeper_rank - espn_rank
        if position_relative:
            note = (
                f"ESPN ranks this {m['position']} higher among {m['position']}s (Superflex-adjusted, QB-crowding removed)"
                if delta > 0
                else f"Sleeper implies a higher {m['position']} rank among {m['position']}s (Superflex-adjusted, QB-crowding removed)"
                if delta < 0
                else f"Ranked evenly among {m['position']}s"
            )
        else:
            note = (
                "ESPN values higher (Sleeper drafters may get value)"
                if delta > 0
                else "Sleeper values higher (ESPN drafters may get value)"
                if delta < 0
                else "Ranked evenly"
            )

        results.append(
            {
                "name": m["name"].title(),
                "position": m["position"],
                "sleeper_player_id": m["a_player_id"],
                "espn_player_id": m["b_player_id"],
                "sleeper_rank": sleeper_rank,
                "espn_rank": espn_rank,
                "position_relative": position_relative,
                "delta": delta,
                "note": note,
            }
        )

    results.sort(key=lambda r: abs(r["delta"]), reverse=True)
    return results[:limit]
