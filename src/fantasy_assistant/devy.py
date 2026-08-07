"""Devy prospect watchlist — college players not yet NFL-draft-eligible, so
they won't appear in Sleeper/ESPN's NFL player pools by definition. This is
a manual watchlist (you add prospects yourself) rather than pulled from a
data source, since there's no clean public feed of devy-specific rankings
beyond KTC's devy page (already covered by sync-ktc --format devy) — this
module cross-references your watchlist against those cached values by name.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .platforms.matching import normalize_name


def add_prospect(conn: sqlite3.Connection, full_name: str, position: str | None = None, college: str | None = None, notes: str | None = None) -> int:
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "INSERT INTO devy_prospects (full_name, position, college, notes, added_at) VALUES (?, ?, ?, ?, ?)",
        (full_name, position, college, notes, now),
    )
    conn.commit()
    return cursor.lastrowid


def remove_prospect(conn: sqlite3.Connection, prospect_id: int) -> bool:
    cursor = conn.execute("DELETE FROM devy_prospects WHERE id = ?", (prospect_id,))
    conn.commit()
    return cursor.rowcount > 0


def list_prospects(conn: sqlite3.Connection) -> list[dict]:
    """Watchlist entries, cross-referenced against cached KTC devy values by
    normalized name when available (run sync-ktc --format devy first)."""
    devy_values = {
        (row["normalized_name"], row["position"] or ""): row
        for row in conn.execute(
            "SELECT normalized_name, position, value, rank FROM market_values WHERE source = 'ktc' AND format = 'devy'"
        ).fetchall()
    }

    prospects = conn.execute("SELECT * FROM devy_prospects ORDER BY added_at DESC").fetchall()
    results = []
    for p in prospects:
        key = (normalize_name(p["full_name"]), p["position"] or "")
        ktc = devy_values.get(key)
        results.append(
            {
                "id": p["id"],
                "full_name": p["full_name"],
                "position": p["position"],
                "college": p["college"],
                "notes": p["notes"],
                "ktc_value": ktc["value"] if ktc else None,
                "ktc_rank": ktc["rank"] if ktc else None,
            }
        )
    return results
