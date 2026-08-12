import sqlite3
from datetime import datetime, timedelta, timezone

from fantasy_assistant.db import init_db
from fantasy_assistant.platforms.ffc.sync import sync_adp


class _FakeFFCClient:
    def __init__(self, players):
        self._players = players
        self.calls = []

    def get_adp(self, qb_mode, teams=12, year=None):
        self.calls.append(qb_mode)
        return self._players


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_db(c)
    return c


def test_sync_adp_derives_rank_from_sort_order():
    conn = _conn()
    players = [
        {"name": "Ja'Marr Chase", "position": "WR", "team": "CIN", "adp": 1.2},
        {"name": "Bijan Robinson", "position": "RB", "team": "ATL", "adp": 2.4},
    ]
    count = sync_adp(conn, _FakeFFCClient(players), qb_mode="1qb")
    assert count == 2

    chase = conn.execute(
        "SELECT * FROM draft_adp WHERE source = 'ffc' AND qb_mode = '1qb' AND normalized_name = ?",
        ("jamarr chase",),
    ).fetchone()
    assert chase["overall_rank"] == 1
    assert chase["adp"] == 1.2

    bijan = conn.execute(
        "SELECT * FROM draft_adp WHERE source = 'ffc' AND qb_mode = '1qb' AND normalized_name = 'bijan robinson'"
    ).fetchone()
    assert bijan["overall_rank"] == 2


def test_sync_adp_skips_players_with_no_name():
    conn = _conn()
    players = [{"position": "WR", "adp": 5.0}, {"name": "Real Player", "position": "RB", "adp": 6.0}]
    count = sync_adp(conn, _FakeFFCClient(players), qb_mode="1qb")
    assert count == 1


def test_sync_adp_qb_modes_stored_separately():
    conn = _conn()
    players = [{"name": "Josh Allen", "position": "QB", "adp": 3.0}]
    sync_adp(conn, _FakeFFCClient(players), qb_mode="1qb")
    sync_adp(conn, _FakeFFCClient(players), qb_mode="superflex")

    rows = conn.execute("SELECT qb_mode FROM draft_adp WHERE normalized_name = 'josh allen'").fetchall()
    assert {r["qb_mode"] for r in rows} == {"1qb", "superflex"}


def test_sync_adp_skips_when_cache_fresh():
    conn = _conn()
    client = _FakeFFCClient([{"name": "Player A", "position": "WR", "adp": 1.0}])
    sync_adp(conn, client, qb_mode="1qb")
    count = sync_adp(conn, client, qb_mode="1qb")
    assert count == 0
    assert client.calls == ["1qb"]  # second call skipped entirely, never hit get_adp again


def test_sync_adp_force_refetches_even_if_fresh():
    conn = _conn()
    client = _FakeFFCClient([{"name": "Player A", "position": "WR", "adp": 1.0}])
    sync_adp(conn, client, qb_mode="1qb")
    count = sync_adp(conn, client, qb_mode="1qb", force=True)
    assert count == 1
    assert client.calls == ["1qb", "1qb"]


def test_sync_adp_refetches_when_cache_stale():
    conn = _conn()
    stale = (datetime.now(timezone.utc) - timedelta(hours=13)).isoformat()
    conn.execute(
        "INSERT INTO draft_adp_cache_meta (source, qb_mode, fetched_at) VALUES ('ffc', '1qb', ?)", (stale,)
    )
    conn.commit()

    client = _FakeFFCClient([{"name": "Player A", "position": "WR", "adp": 1.0}])
    count = sync_adp(conn, client, qb_mode="1qb")
    assert count == 1


def test_sync_adp_overwrites_prior_values_on_resync():
    conn = _conn()
    client = _FakeFFCClient([{"name": "Player A", "position": "WR", "adp": 1.0}])
    sync_adp(conn, client, qb_mode="1qb")

    client2 = _FakeFFCClient([{"name": "Player A", "position": "WR", "adp": 1.0}, {"name": "Player B", "position": "RB", "adp": 2.0}])
    sync_adp(conn, client2, qb_mode="1qb", force=True)

    rows = conn.execute("SELECT normalized_name FROM draft_adp WHERE qb_mode = '1qb'").fetchall()
    assert {r["normalized_name"] for r in rows} == {"player a", "player b"}
