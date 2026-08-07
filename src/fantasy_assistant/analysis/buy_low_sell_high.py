"""The core feature: combines on-field performance trend with market value
movement (KTC for dynasty/devy, FantasyPros rank for redraft) and Reddit
sentiment to flag divergences.

- buy-low: performance trending up, but market/sentiment hasn't caught up yet
- sell-high: market value or sentiment is high, but performance is declining

This is a transparent, explainable heuristic (fixed thresholds, plain
if/else), not a statistical model — every flag comes with the specific
reason it fired, deliberately, so you can judge it rather than trust it
blindly. All three inputs (KTC, FantasyPros, Reddit) are themselves
unverified-against-live-site as noted in their own modules; this engine
degrades gracefully when any of them has no data yet (it just uses whatever
signals are actually populated).
"""

from __future__ import annotations

import sqlite3

from ..platforms.matching import normalize_name
from .performance_trend import compute_trends

PERF_TREND_THRESHOLD = 2.0  # points/game swing to count as a meaningful trend
SENTIMENT_THRESHOLD = 3  # net mention score to count as notably positive/negative


def _market_value_delta_map(conn: sqlite3.Connection, format_: str) -> dict[tuple[str, str], int | None]:
    current = {
        (row["normalized_name"], row["position"] or ""): row["value"]
        for row in conn.execute(
            "SELECT normalized_name, position, value FROM market_values WHERE source = 'ktc' AND format = ?",
            (format_,),
        ).fetchall()
    }
    prior = {
        (row["normalized_name"], row["position"] or ""): row["value"]
        for row in conn.execute(
            "SELECT normalized_name, position, value FROM market_values_prior WHERE source = 'ktc' AND format = ?",
            (format_,),
        ).fetchall()
    }
    deltas = {}
    for key, cur_val in current.items():
        prior_val = prior.get(key)
        if cur_val is not None and prior_val is not None:
            deltas[key] = cur_val - prior_val
    return deltas


def _expert_rank_delta_map(conn: sqlite3.Connection) -> dict[tuple[str, str], int | None]:
    current = {
        (row["normalized_name"], row["position"] or ""): row["overall_rank"]
        for row in conn.execute(
            "SELECT normalized_name, position, overall_rank FROM expert_rankings WHERE source = 'fantasypros' AND format = 'redraft'"
        ).fetchall()
    }
    prior = {
        (row["normalized_name"], row["position"] or ""): row["overall_rank"]
        for row in conn.execute(
            "SELECT normalized_name, position, overall_rank FROM expert_rankings_prior WHERE source = 'fantasypros' AND format = 'redraft'"
        ).fetchall()
    }
    deltas = {}
    for key, cur_rank in current.items():
        prior_rank = prior.get(key)
        if cur_rank is not None and prior_rank is not None:
            # rank going down (smaller number) is a positive move — flip sign
            # so positive delta means "market moved up on this player" like the KTC case.
            deltas[key] = prior_rank - cur_rank
    return deltas


def _sentiment_map(conn: sqlite3.Connection) -> dict[str, float]:
    rows = conn.execute("SELECT normalized_name, net_score FROM player_sentiment WHERE source = 'reddit'").fetchall()
    return {row["normalized_name"]: row["net_score"] for row in rows}


def find_buy_low_sell_high(conn: sqlite3.Connection, league_id: str, league_format: str, limit: int = 25) -> list[dict]:
    trends = compute_trends(conn, league_id)
    sentiment = _sentiment_map(conn)

    market_format = league_format if league_format in ("dynasty", "devy") else None
    value_deltas = _market_value_delta_map(conn, market_format) if market_format else {}
    rank_deltas = {} if market_format else _expert_rank_delta_map(conn)

    rows = conn.execute(
        """
        SELECT DISTINCT rp.player_id, p.full_name, p.position, p.team
        FROM roster_players rp
        JOIN players p ON p.player_id = rp.player_id AND p.platform = 'sleeper'
        WHERE rp.league_id = ?
        """,
        (league_id,),
    ).fetchall()

    results = []
    for row in rows:
        trend = trends.get(row["player_id"])
        if not trend:
            continue

        norm = normalize_name(row["full_name"])
        key = (norm, row["position"] or "")
        market_delta = value_deltas.get(key) if market_format else rank_deltas.get(key)
        net_sentiment = sentiment.get(norm)
        perf_trend = trend["trend"]

        flags = []
        if perf_trend > PERF_TREND_THRESHOLD and (market_delta is None or market_delta <= 0):
            flags.append(("buy_low", "Performance trending up, market value hasn't caught up yet"))
        if perf_trend < -PERF_TREND_THRESHOLD and market_delta is not None and market_delta > 0:
            flags.append(("sell_high", "Market value still up while performance is declining"))
        if net_sentiment is not None:
            if net_sentiment >= SENTIMENT_THRESHOLD and perf_trend < 0:
                flags.append(("sell_high", "Reddit sentiment high but usage/performance is declining"))
            if net_sentiment <= -SENTIMENT_THRESHOLD and perf_trend > PERF_TREND_THRESHOLD:
                flags.append(("buy_low", "Performance trending up but Reddit sentiment still lags"))

        if not flags:
            continue

        results.append(
            {
                "player_id": row["player_id"],
                "name": row["full_name"],
                "position": row["position"],
                "team": row["team"],
                "recent_avg": trend["recent_avg"],
                "season_avg": trend["season_avg"],
                "perf_trend": perf_trend,
                "market_delta": market_delta,
                "sentiment": net_sentiment,
                "flags": flags,
            }
        )

    results.sort(key=lambda r: abs(r["perf_trend"]), reverse=True)
    return results[:limit]
