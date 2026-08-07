import sqlite3
from datetime import datetime, timezone

from fantasy_assistant.db import init_db
from fantasy_assistant.devy import add_prospect, list_prospects, remove_prospect

NOW = datetime.now(timezone.utc).isoformat()


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_add_and_list_prospect():
    conn = _make_db()
    pid = add_prospect(conn, "Future Star", "QB", "Ohio State", "keep an eye on him")
    results = list_prospects(conn)
    assert len(results) == 1
    assert results[0]["id"] == pid
    assert results[0]["full_name"] == "Future Star"
    assert results[0]["ktc_value"] is None


def test_list_prospects_joins_ktc_devy_value_by_name():
    conn = _make_db()
    add_prospect(conn, "Future Star", "QB", "Ohio State")
    conn.execute(
        "INSERT INTO market_values (source, format, normalized_name, full_name, position, value, rank, fetched_at) "
        "VALUES ('ktc', 'devy', 'future star', 'Future Star', 'QB', 4200, 7, ?)",
        (NOW,),
    )
    conn.commit()

    results = list_prospects(conn)
    assert results[0]["ktc_value"] == 4200
    assert results[0]["ktc_rank"] == 7


def test_remove_prospect():
    conn = _make_db()
    pid = add_prospect(conn, "Future Star", "QB")
    assert remove_prospect(conn, pid) is True
    assert list_prospects(conn) == []
    assert remove_prospect(conn, pid) is False
