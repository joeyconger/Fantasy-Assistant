"""Finds "inefficiencies" — players where real market ADP (Fantasy Football
Calculator) and ESPN disagree sharply on overall rank. A big gap means
ESPN's draft rank has this player priced very differently than the broader
market does, which is a real signal for value picks in an ESPN draft.

The market-ADP side deliberately isn't Sleeper's own `search_rank`: that
field is Sleeper's interest/search-volume ranking, not a real draft
position — a hyped rookie can rank far above his actual redraft value
there just from search traffic. Fantasy Football Calculator aggregates
real draft picks instead (see platforms/ffc/), which is what "ADP" is
supposed to mean. Dynasty startup ADP is out of scope here by decision —
this tool only covers redraft.

Both sources' raw ranks are clipped to a shared top-N before comparing —
comparing raw ordinals past the draftable range would produce meaningless
deltas, so we only compare players both sources consider draft-relevant.

Defensive players are excluded outright — none of these leagues play IDP,
and defense valuation logic doesn't belong in a skill-position
market-inefficiency tool. In practice, team defenses (Sleeper labels them
"DEF", ESPN "D/ST") can never appear here anyway: match_players() only
pairs players whose position string is identical on both platforms, so
that label mismatch already keeps them from matching. This filter is real
protection only for individual defensive positions (DT/LB/CB/...), where
both platforms may use the same abbreviation.

Superflex QB-crowding: both ESPN's Superflex rank type and FFC's "2qb" ADP
type independently re-sort their pools around Superflex QB scarcity, and
there's no guarantee they crowd QBs to the same degree — comparing raw
overall rank could still produce deltas that are really just measuring "how
many QBs each source ranks above this guy" rather than a real disagreement.
QB is the one position where that overall-rank shift *is* the real
Superflex signal, so QB keeps using overall rank; every other position
switches to within-position rank (RB vs RB, WR vs WR, ...) in Superflex
mode, which stays comparable across sources regardless of how aggressively
each one reprices QBs.
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


def _adp_rank_map(conn: sqlite3.Connection, qb_mode: str) -> dict[tuple[str, str], int]:
    """FFC's ADP, keyed by (normalized_name, position) since FFC has no
    shared player ID with Sleeper/ESPN — matched at query time the same way
    KTC/FantasyPros are, by reusing the already-normalized name from
    match_players()'s key."""
    rows = conn.execute(
        "SELECT normalized_name, position, overall_rank FROM draft_adp "
        "WHERE source = 'ffc' AND qb_mode = ? AND overall_rank IS NOT NULL",
        (qb_mode,),
    ).fetchall()
    return {(row["normalized_name"], row["position"] or ""): row["overall_rank"] for row in rows}


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


def _position_rank_map_by_key(rank_map: dict[tuple[str, str], int]) -> dict[tuple[str, str], int]:
    """Same idea as _position_rank_map, but for (normalized_name, position)
    keyed sources like FFC's ADP table, where position is already part of
    the key — no extra query needed to look positions up."""
    buckets: dict[str, list[tuple[int, tuple[str, str]]]] = {}
    for key, rank in rank_map.items():
        _, position = key
        buckets.setdefault(position, []).append((rank, key))

    result: dict[tuple[str, str], int] = {}
    for position_ranks in buckets.values():
        position_ranks.sort()
        for position_rank, (_, key) in enumerate(position_ranks, start=1):
            result[key] = position_rank
    return result


def find_rank_inefficiencies(
    conn: sqlite3.Connection, limit: int = 25, rank_cap: int = DEFAULT_RANK_CAP, qb_mode: str = "1qb"
) -> list[dict]:
    """qb_mode='superflex' compares against ESPN's Superflex-specific rank
    (espn_superflex_rank) and FFC's "2qb" ADP type, if either was found
    during sync — see espn/rankings.py and platforms/ffc/ for why neither
    is guaranteed to exist. See the module docstring for the QB-crowding
    handling on non-QB positions."""
    espn_source = "espn_superflex_rank" if qb_mode == "superflex" else "espn_standard_rank"
    espn_ranks = _rank_map(conn, "espn", espn_source)
    adp_ranks = _adp_rank_map(conn, qb_mode)

    espn_position_ranks = _position_rank_map(conn, "espn", espn_ranks) if qb_mode == "superflex" else {}
    adp_position_ranks = _position_rank_map_by_key(adp_ranks) if qb_mode == "superflex" else {}

    matches = match_players(conn, "sleeper", "espn")

    results = []
    for m in matches:
        if m["position"] in DEFENSIVE_POSITIONS:
            continue

        name_key = (m["name"], m["position"])
        adp_overall = adp_ranks.get(name_key)
        espn_overall = espn_ranks.get(m["b_player_id"])
        if adp_overall is None or espn_overall is None:
            continue
        if adp_overall > rank_cap or espn_overall > rank_cap:
            continue

        position_relative = qb_mode == "superflex" and m["position"] in POSITION_RELATIVE_IN_SUPERFLEX
        if position_relative:
            adp_rank = adp_position_ranks.get(name_key, adp_overall)
            espn_rank = espn_position_ranks.get(m["b_player_id"], espn_overall)
        else:
            adp_rank = adp_overall
            espn_rank = espn_overall

        delta = adp_rank - espn_rank
        if position_relative:
            note = (
                f"ESPN ranks this {m['position']} higher among {m['position']}s than market ADP does (Superflex-adjusted)"
                if delta > 0
                else f"Market ADP ranks this {m['position']} higher among {m['position']}s than ESPN does (Superflex-adjusted)"
                if delta < 0
                else f"Ranked evenly among {m['position']}s"
            )
        else:
            note = (
                "ESPN ranks him well above market ADP (likely to go earlier in an ESPN draft than the market expects)"
                if delta > 0
                else "Market ADP ranks him well above ESPN (possible value pick in an ESPN draft)"
                if delta < 0
                else "Ranked evenly with market ADP"
            )

        results.append(
            {
                "name": m["name"].title(),
                "position": m["position"],
                "sleeper_player_id": m["a_player_id"],
                "espn_player_id": m["b_player_id"],
                "adp_rank": adp_rank,
                "espn_rank": espn_rank,
                "position_relative": position_relative,
                "delta": delta,
                "note": note,
            }
        )

    results.sort(key=lambda r: abs(r["delta"]), reverse=True)
    return results[:limit]
