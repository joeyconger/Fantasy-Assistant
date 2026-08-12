import sqlite3
from datetime import datetime, timedelta, timezone

import fantasy_assistant.platforms.reddit.sync as reddit_sync
from fantasy_assistant.db import init_db
from fantasy_assistant.platforms.reddit.sync import sync_reddit_sentiment


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_db(c)
    return c


def _fake_fetch(posts, calls):
    def _fetch(subreddit_flairs=None, limit=100):
        calls.append((subreddit_flairs, limit))
        return posts

    return _fetch


def test_sync_reddit_sentiment_scores_and_persists(monkeypatch):
    conn = _conn()
    calls = []
    posts = [{"title": "Bijan Robinson is a stud", "selftext": ""}]
    monkeypatch.setattr(reddit_sync, "fetch_recent_posts", _fake_fetch(posts, calls))

    result = sync_reddit_sentiment(conn, ["Bijan Robinson"])
    assert result == (1, 1)

    row = conn.execute("SELECT * FROM player_sentiment WHERE normalized_name = 'bijan robinson'").fetchone()
    assert row["mention_count"] == 1
    assert row["net_score"] > 0


def test_sync_reddit_sentiment_skips_when_cache_fresh(monkeypatch):
    conn = _conn()
    calls = []
    monkeypatch.setattr(reddit_sync, "fetch_recent_posts", _fake_fetch([], calls))

    sync_reddit_sentiment(conn, ["Bijan Robinson"])
    result = sync_reddit_sentiment(conn, ["Bijan Robinson"])

    assert result is None
    assert len(calls) == 1  # second call never hit fetch_recent_posts


def test_sync_reddit_sentiment_force_refetches_even_if_fresh(monkeypatch):
    conn = _conn()
    calls = []
    monkeypatch.setattr(reddit_sync, "fetch_recent_posts", _fake_fetch([], calls))

    sync_reddit_sentiment(conn, ["Bijan Robinson"])
    result = sync_reddit_sentiment(conn, ["Bijan Robinson"], force=True)

    assert result == (0, 0)
    assert len(calls) == 2


def test_sync_reddit_sentiment_refetches_when_cache_stale(monkeypatch):
    conn = _conn()
    stale = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    conn.execute("INSERT INTO reddit_sentiment_cache_meta (id, fetched_at) VALUES (1, ?)", (stale,))
    conn.commit()

    calls = []
    monkeypatch.setattr(reddit_sync, "fetch_recent_posts", _fake_fetch([], calls))

    result = sync_reddit_sentiment(conn, ["Bijan Robinson"])
    assert result == (0, 0)
    assert len(calls) == 1


def test_sync_reddit_sentiment_within_24h_is_still_fresh(monkeypatch):
    conn = _conn()
    recent = (datetime.now(timezone.utc) - timedelta(hours=23)).isoformat()
    conn.execute("INSERT INTO reddit_sentiment_cache_meta (id, fetched_at) VALUES (1, ?)", (recent,))
    conn.commit()

    calls = []
    monkeypatch.setattr(reddit_sync, "fetch_recent_posts", _fake_fetch([], calls))

    result = sync_reddit_sentiment(conn, ["Bijan Robinson"])
    assert result is None
    assert calls == []


def test_sync_reddit_sentiment_passes_subreddit_flairs_and_limit_through(monkeypatch):
    conn = _conn()
    calls = []
    monkeypatch.setattr(reddit_sync, "fetch_recent_posts", _fake_fetch([], calls))

    sync_reddit_sentiment(conn, ["Bijan Robinson"], subreddit_flairs={"nfl": None}, limit=50)

    assert calls == [({"nfl": None}, 50)]
