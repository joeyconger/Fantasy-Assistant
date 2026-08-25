import sqlite3
from datetime import datetime, timedelta, timezone

from fantasy_assistant.db import init_db
from fantasy_assistant.platforms.nflverse.snap_sync import get_player_snap_counts, sync_snap_counts


class _FakeSnapClient:
    def __init__(self, rows):
        self._rows = rows
        self.calls = []

    def get_snap_counts(self, season, url=None):
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
        "offense_snaps": 55,
        "offense_pct": 0.92,
    }
    base.update(overrides)
    return base


def test_sync_snap_counts_inserts_rows():
    conn = _conn()
    count = sync_snap_counts(conn, _FakeSnapClient([_row()]), season=2026)
    assert count == 1

    row = conn.execute(
        "SELECT * FROM snap_counts WHERE source = 'nflverse' AND season = 2026 AND normalized_name = ?",
        ("jamarr chase",),
    ).fetchone()
    assert row["offense_snaps"] == 55
    assert row["offense_pct"] == 0.92


def test_sync_snap_counts_skips_rows_with_no_week():
    conn = _conn()
    count = sync_snap_counts(conn, _FakeSnapClient([_row(week=None)]), season=2026)
    assert count == 0


def test_sync_snap_counts_skips_when_cache_fresh():
    conn = _conn()
    client = _FakeSnapClient([_row()])
    sync_snap_counts(conn, client, season=2026)
    count = sync_snap_counts(conn, client, season=2026)
    assert count == 0
    assert client.calls == [2026]


def test_sync_snap_counts_force_refetches_even_if_fresh():
    conn = _conn()
    client = _FakeSnapClient([_row()])
    sync_snap_counts(conn, client, season=2026)
    count = sync_snap_counts(conn, client, season=2026, force=True)
    assert count == 1
    assert client.calls == [2026, 2026]


def test_sync_snap_counts_doesnt_clobber_advanced_stats_same_season():
    """The whole reason snap_counts is a separate table from advanced_stats
    — syncing one must never wipe the other's rows for the same season."""
    from fantasy_assistant.platforms.nflverse.sync import sync_weekly_stats

    conn = _conn()

    class _FakeStatsClient:
        def get_weekly_stats(self, season, url=None):
            return [
                {
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
            ]

    sync_weekly_stats(conn, _FakeStatsClient(), season=2026)
    sync_snap_counts(conn, _FakeSnapClient([_row()]), season=2026)

    advanced_row = conn.execute(
        "SELECT * FROM advanced_stats WHERE season = 2026 AND normalized_name = 'jamarr chase'"
    ).fetchone()
    assert advanced_row is not None
    assert advanced_row["target_share"] == 0.28

    snap_row = conn.execute(
        "SELECT * FROM snap_counts WHERE season = 2026 AND normalized_name = 'jamarr chase'"
    ).fetchone()
    assert snap_row is not None
    assert snap_row["offense_pct"] == 0.92


def test_get_player_snap_counts_orders_most_recent_week_first():
    conn = _conn()
    client = _FakeSnapClient([_row(week=1, offense_snaps=50), _row(week=3, offense_snaps=60)])
    sync_snap_counts(conn, client, season=2026)

    rows = get_player_snap_counts(conn, "Ja'Marr Chase", 2026)
    assert [r["week"] for r in rows] == [3, 1]


def test_get_player_snap_counts_empty_for_unknown_player():
    conn = _conn()
    assert get_player_snap_counts(conn, "Nobody Real", 2026) == []
