"""Fetches Reddit posts (via Apify), scores sentiment, and persists into
player_sentiment — cached 24h so casual re-runs don't hit Apify repeatedly.
Every call costs against the free $5/month Apify budget, and sentiment
doesn't need to refresh faster than daily for this app's actual use.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from ...analysis.sentiment import score_player_mentions
from .client import fetch_recent_posts

CACHE_TTL = timedelta(hours=24)


def sync_sentiment(conn: sqlite3.Connection, scored: dict[str, dict]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    for norm, data in scored.items():
        conn.execute(
            """
            INSERT INTO player_sentiment (normalized_name, source, full_name, mention_count, positive_count, negative_count, net_score, fetched_at)
            VALUES (?, 'reddit', ?, ?, ?, ?, ?, ?)
            ON CONFLICT(normalized_name, source) DO UPDATE SET
                full_name=excluded.full_name,
                mention_count=excluded.mention_count,
                positive_count=excluded.positive_count,
                negative_count=excluded.negative_count,
                net_score=excluded.net_score,
                fetched_at=excluded.fetched_at
            """,
            (
                norm,
                data["full_name"],
                data["mention_count"],
                data["positive_count"],
                data["negative_count"],
                data["net_score"],
                now,
            ),
        )
        count += 1
    conn.commit()
    return count


def tracked_player_names(conn: sqlite3.Connection) -> list[str]:
    """Players worth watching for sentiment: anyone rostered in any synced
    league. Scoped this way (rather than the whole ~12k NFL pool) so mention
    matching stays fast and relevant to leagues you're actually in."""
    rows = conn.execute(
        """
        SELECT DISTINCT p.full_name
        FROM roster_players rp
        JOIN leagues l ON l.league_id = rp.league_id
        JOIN players p ON p.player_id = rp.player_id AND p.platform = l.platform
        WHERE p.full_name IS NOT NULL
        """
    ).fetchall()
    return [row["full_name"] for row in rows]


def sync_reddit_sentiment(
    conn: sqlite3.Connection,
    player_names: list[str],
    subreddit_flairs: dict[str, list[str] | None] | None = None,
    limit: int = 100,
    force: bool = False,
) -> tuple[int, int] | None:
    """Fetches recent posts, scores them against player_names, and persists
    the result. Returns (posts_scanned, players_scored), or None if skipped
    because the cache is still fresh (<24h) — pass force=True to bypass.
    """
    row = conn.execute("SELECT fetched_at FROM reddit_sentiment_cache_meta WHERE id = 1").fetchone()
    if row and not force:
        fetched_at = datetime.fromisoformat(row["fetched_at"])
        if datetime.now(timezone.utc) - fetched_at < CACHE_TTL:
            return None

    posts = fetch_recent_posts(subreddit_flairs=subreddit_flairs, limit=limit)
    scored = score_player_mentions(posts, player_names)
    count = sync_sentiment(conn, scored)

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO reddit_sentiment_cache_meta (id, fetched_at) VALUES (1, ?)
        ON CONFLICT(id) DO UPDATE SET fetched_at=excluded.fetched_at
        """,
        (now,),
    )
    conn.commit()
    return len(posts), count
