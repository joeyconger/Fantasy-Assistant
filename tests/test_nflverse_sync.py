import sqlite3
from datetime import datetime, timedelta, timezone

from fantasy_assistant.db import init_db
from fantasy_assistant.platforms.nflverse.sync import get_player_advanced_stats, sync_weekly_stats


class _FakeNflverseClient:
    def __init__(self, rows):
        self._rows = rows
        self.calls = []

    def get_weekly_stats(self, season, url=None):
        self.calls.append(season)
        return self._rows


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_db(c)
    return c


def _row(**overrides):
    base = {
        "full_name": "Ja'Marr Chase",
        "position": "WR",
        "team": "CIN",
        "season": 2026,
        "week": 1,
        "targets": 10,
        "target_share": 0.28,
        "air_yards_share": 0.35,
        "wopr": 0.55,
        "racr": 1.1,
    }
    base.update(overrides)
    return base


def test_sync_weekly_stats_inserts_rows():
    conn = _conn()
    count = sync_weekly_stats(conn, _FakeNflverseClient([_row()]), season=2026)
    assert count == 1

    row = conn.execute(
        "SELECT * FROM advanced_stats WHERE source = 'nflverse' AND season = 2026 AND normalized_name = ?",
        ("jamarr chase",),
    ).fetchone()
    assert row["week"] == 1
    assert row["target_share"] == 0.28
    assert row["wopr"] == 0.55


def test_sync_weekly_stats_skips_rows_with_no_week():
    conn = _conn()
    count = sync_weekly_stats(conn, _FakeNflverseClient([_row(week=None)]), season=2026)
    assert count == 0


def test_sync_weekly_stats_skips_when_cache_fresh():
    conn = _conn()
    client = _FakeNflverseClient([_row()])
    sync_weekly_stats(conn, client, season=2026)
    count = sync_weekly_stats(conn, client, season=2026)
    assert count == 0
    assert client.calls == [2026]


def test_sync_weekly_stats_force_refetches_even_if_fresh():
    conn = _conn()
    client = _FakeNflverseClient([_row()])
    sync_weekly_stats(conn, client, season=2026)
    count = sync_weekly_stats(conn, client, season=2026, force=True)
    assert count == 1
    assert client.calls == [2026, 2026]


def test_sync_weekly_stats_refetches_when_cache_stale():
    conn = _conn()
    stale = (datetime.now(timezone.utc) - timedelta(hours=13)).isoformat()
    conn.execute(
        "INSERT INTO advanced_stats_cache_meta (source, season, fetched_at) VALUES ('nflverse', 2026, ?)", (stale,)
    )
    conn.commit()

    count = sync_weekly_stats(conn, _FakeNflverseClient([_row()]), season=2026)
    assert count == 1


def test_sync_weekly_stats_separate_seasons_dont_collide():
    conn = _conn()
    sync_weekly_stats(conn, _FakeNflverseClient([_row(season=2025)]), season=2025)
    sync_weekly_stats(conn, _FakeNflverseClient([_row(season=2026)]), season=2026)

    rows = conn.execute("SELECT season FROM advanced_stats WHERE normalized_name = 'jamarr chase'").fetchall()
    assert {r["season"] for r in rows} == {2025, 2026}


def test_get_player_advanced_stats_orders_most_recent_week_first():
    conn = _conn()
    client = _FakeNflverseClient([_row(week=1, targets=5), _row(week=3, targets=9)])
    sync_weekly_stats(conn, client, season=2026)

    rows = get_player_advanced_stats(conn, "Ja'Marr Chase", 2026)
    assert [r["week"] for r in rows] == [3, 1]


def test_get_player_advanced_stats_empty_for_unknown_player():
    conn = _conn()
    assert get_player_advanced_stats(conn, "Nobody Real", 2026) == []
