"""Compares two sides of a proposed trade: dynasty/devy leagues use KTC
value (qb_mode-aware, auto-detected from the league), redraft leagues use
FantasyPros rank (lower is better).

Players are matched by normalized name against whichever table applies. A
name that can't be found is reported as unresolved rather than silently
dropped or defaulted to zero — a trade evaluation missing a player's value
is misleading, not just incomplete, so the caller needs to know.
"""

from __future__ import annotations

import sqlite3

from ..platforms.matching import normalize_name
from .roster_format import detect_qb_mode


class TradeAnalyzerError(ValueError):
    pass


def _lookup_dynasty_value(conn: sqlite3.Connection, name: str, league_format: str, qb_mode: str) -> dict | None:
    norm = normalize_name(name)
    row = conn.execute(
        "SELECT full_name, position, value FROM market_values WHERE source = 'ktc' AND format = ? AND qb_mode = ? AND normalized_name = ?",
        (league_format, qb_mode, norm),
    ).fetchone()
    if not row or row["value"] is None:
        return None
    return {"full_name": row["full_name"], "position": row["position"], "metric": row["value"]}


def _lookup_redraft_rank(conn: sqlite3.Connection, name: str) -> dict | None:
    norm = normalize_name(name)
    row = conn.execute(
        "SELECT full_name, position, overall_rank FROM expert_rankings WHERE source = 'fantasypros' AND format = 'redraft' AND normalized_name = ?",
        (norm,),
    ).fetchone()
    if not row or row["overall_rank"] is None:
        return None
    return {"full_name": row["full_name"], "position": row["position"], "metric": row["overall_rank"]}


def analyze_trade(conn: sqlite3.Connection, league_id: str, side_a_names: list[str], side_b_names: list[str]) -> dict:
    league = conn.execute("SELECT format, roster_positions FROM leagues WHERE league_id = ?", (league_id,)).fetchone()
    if not league:
        raise TradeAnalyzerError(f"League {league_id} hasn't been synced yet.")

    league_format = league["format"] or "redraft"
    is_dynasty = league_format in ("dynasty", "devy")
    qb_mode = detect_qb_mode(league["roster_positions"]) if is_dynasty else None
    higher_is_better = is_dynasty  # KTC value: higher = better. FantasyPros rank: lower = better.

    def resolve_side(names: list[str]) -> tuple[list[dict], list[str]]:
        players, unresolved = [], []
        for name in names:
            found = (
                _lookup_dynasty_value(conn, name, league_format, qb_mode)
                if is_dynasty
                else _lookup_redraft_rank(conn, name)
            )
            (players if found else unresolved).append(found if found else name)
        return players, unresolved

    side_a, unresolved_a = resolve_side(side_a_names)
    side_b, unresolved_b = resolve_side(side_b_names)

    total_a = sum(p["metric"] for p in side_a)
    total_b = sum(p["metric"] for p in side_b)

    # Positive means side A comes out ahead (receives more value than they send).
    advantage_to_a = (total_b - total_a) if higher_is_better else (total_a - total_b)
    if advantage_to_a > 0:
        winner = "A"
    elif advantage_to_a < 0:
        winner = "B"
    else:
        winner = "even"

    return {
        "league_format": league_format,
        "qb_mode": qb_mode,
        "metric": "value" if is_dynasty else "rank",
        "higher_is_better": higher_is_better,
        "side_a": side_a,
        "side_b": side_b,
        "total_a": total_a,
        "total_b": total_b,
        "winner": winner,
        "margin": abs(advantage_to_a),
        "unresolved": unresolved_a + unresolved_b,
    }
