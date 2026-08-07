"""Caches KTC values into SQLite, and rolls the previous sync's values into
market_values_prior so callers can compute a value delta over time.

Note "prior" here means "value as of the last successful sync," not a fixed
7/30-day window — sync however often you want and the delta reflects that
gap. Cached for 12h by default so casual re-runs don't hit KTC repeatedly.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from ..matching import normalize_name
from .client import KTCClient

CACHE_TTL = timedelta(hours=12)


def sync_values(conn: sqlite3.Connection, client: KTCClient, format_: str, force: bool = False) -> int:
    row = conn.execute(
        "SELECT fetched_at FROM market_values_cache_meta WHERE source = 'ktc' AND format = ?", (format_,)
    ).fetchone()
    if row and not force:
        fetched_at = datetime.fromisoformat(row["fetched_at"])
        if datetime.now(timezone.utc) - fetched_at < CACHE_TTL:
            return 0

    players = client.get_values(format_)
    now = datetime.now(timezone.utc).isoformat()

    # Roll current values into "prior" before overwriting, so a delta is computable.
    conn.execute("DELETE FROM market_values_prior WHERE source = 'ktc' AND format = ?", (format_,))
    conn.execute(
        """
        INSERT INTO market_values_prior (source, format, normalized_name, position, value, fetched_at)
        SELECT source, format, normalized_name, position, value, fetched_at
        FROM market_values WHERE source = 'ktc' AND format = ?
        """,
        (format_,),
    )

    conn.execute("DELETE FROM market_values WHERE source = 'ktc' AND format = ?", (format_,))
    count = 0
    for p in players:
        if not p.get("full_name"):
            continue
        conn.execute(
            """
            INSERT INTO market_values (source, format, normalized_name, full_name, position, team, value, rank, fetched_at)
            VALUES ('ktc', ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, format, normalized_name, position) DO UPDATE SET
                full_name=excluded.full_name,
                team=excluded.team,
                value=excluded.value,
                rank=excluded.rank,
                fetched_at=excluded.fetched_at
            """,
            (
                format_,
                normalize_name(p["full_name"]),
                p["full_name"],
                p.get("position") or "",
                p.get("team"),
                p.get("value"),
                p.get("rank"),
                now,
            ),
        )
        count += 1

    conn.execute(
        """
        INSERT INTO market_values_cache_meta (source, format, fetched_at) VALUES ('ktc', ?, ?)
        ON CONFLICT(source, format) DO UPDATE SET fetched_at=excluded.fetched_at
        """,
        (format_, now),
    )
    conn.commit()
    return count
