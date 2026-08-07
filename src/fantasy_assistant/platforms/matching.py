"""Matches the same real player across platforms/sources that each assign
their own independent IDs (Sleeper, ESPN, and later KTC/FantasyPros).

Matching is name+position based since there's no shared ID. A duplicate
normalized name within the same position is left unmatched rather than
guessed — a wrong pairing would silently corrupt every downstream feature
(draft board, buy-low/sell-high), which is worse than just not comparing
that player yet.
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
_PUNCTUATION = re.compile(r"[.'’\-]")


def normalize_name(name: str) -> str:
    name = _PUNCTUATION.sub("", name.lower())
    parts = [p for p in name.split() if p not in _SUFFIXES]
    return " ".join(parts).strip()


def _players_by_key(conn: sqlite3.Connection, platform: str) -> dict[tuple[str, str], list[str]]:
    rows = conn.execute(
        "SELECT player_id, full_name, position FROM players WHERE platform = ? AND full_name IS NOT NULL",
        (platform,),
    ).fetchall()
    index: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        key = (normalize_name(row["full_name"]), row["position"] or "")
        index[key].append(row["player_id"])
    return index


def match_players(conn: sqlite3.Connection, platform_a: str, platform_b: str) -> list[dict]:
    """Returns [{a_player_id, b_player_id, name, position}] for players that
    match unambiguously by normalized name + position between the two platforms.
    """
    index_a = _players_by_key(conn, platform_a)
    index_b = _players_by_key(conn, platform_b)

    matches = []
    for key, a_ids in index_a.items():
        b_ids = index_b.get(key)
        if not b_ids:
            continue
        if len(a_ids) != 1 or len(b_ids) != 1:
            continue  # ambiguous (duplicate name+position on one side) — skip rather than guess
        name, position = key
        matches.append({"a_player_id": a_ids[0], "b_player_id": b_ids[0], "name": name, "position": position})
    return matches
