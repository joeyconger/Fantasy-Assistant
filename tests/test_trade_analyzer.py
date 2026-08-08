import sqlite3
from datetime import datetime, timezone

import pytest

from fantasy_assistant.analysis.trade_analyzer import TradeAnalyzerError, analyze_trade
from fantasy_assistant.db import init_db

NOW = datetime.now(timezone.utc).isoformat()


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_db(c)
    return c


def _add_league(conn, format_, league_id="L1", roster_positions=None):
    import json

    conn.execute(
        "INSERT INTO leagues (league_id, platform, name, season, format, total_rosters, roster_positions) VALUES (?, 'sleeper', 'Test', '2026', ?, 1, ?)",
        (league_id, format_, json.dumps(roster_positions) if roster_positions else None),
    )


def _add_ktc_value(conn, name, position, value, format_="dynasty", qb_mode="1qb"):
    from fantasy_assistant.platforms.matching import normalize_name

    conn.execute(
        "INSERT INTO market_values (source, format, qb_mode, normalized_name, full_name, position, value, fetched_at) VALUES ('ktc', ?, ?, ?, ?, ?, ?, ?)",
        (format_, qb_mode, normalize_name(name), name, position, value, NOW),
    )


def _add_fp_rank(conn, name, position, rank):
    from fantasy_assistant.platforms.matching import normalize_name

    conn.execute(
        "INSERT INTO expert_rankings (source, format, normalized_name, full_name, position, overall_rank, fetched_at) VALUES ('fantasypros', 'redraft', ?, ?, ?, ?, ?)",
        (normalize_name(name), name, position, rank, NOW),
    )


def test_dynasty_trade_higher_value_side_wins(conn):
    _add_league(conn, "dynasty")
    _add_ktc_value(conn, "Star Player", "WR", 9000)
    _add_ktc_value(conn, "Bench Guy", "RB", 1000)
    conn.commit()

    result = analyze_trade(conn, "L1", side_a_names=["Star Player"], side_b_names=["Bench Guy"])
    # Side A sends Star Player (9000), receives Bench Guy (1000) -- A gives more than gets -- B wins.
    assert result["metric"] == "value"
    assert result["winner"] == "B"
    assert result["margin"] == 8000


def test_dynasty_trade_balanced_sides(conn):
    _add_league(conn, "dynasty")
    _add_ktc_value(conn, "Player A", "WR", 5000)
    _add_ktc_value(conn, "Player B", "RB", 5000)
    conn.commit()

    result = analyze_trade(conn, "L1", side_a_names=["Player A"], side_b_names=["Player B"])
    assert result["winner"] == "even"
    assert result["margin"] == 0


def test_redraft_trade_lower_rank_total_wins_for_that_side(conn):
    _add_league(conn, "redraft")
    _add_fp_rank(conn, "Elite Guy", "RB", 2)
    _add_fp_rank(conn, "Depth Guy", "WR", 150)
    conn.commit()

    result = analyze_trade(conn, "L1", side_a_names=["Elite Guy"], side_b_names=["Depth Guy"])
    # A sends the elite (rank 2, very valuable) player, receives the depth (rank 150) player.
    # A is giving up much more than receiving -- B wins.
    assert result["metric"] == "rank"
    assert result["winner"] == "B"


def test_unresolved_players_reported_not_silently_dropped(conn):
    _add_league(conn, "dynasty")
    _add_ktc_value(conn, "Known Player", "WR", 5000)
    conn.commit()

    result = analyze_trade(conn, "L1", side_a_names=["Known Player"], side_b_names=["Totally Unknown Guy"])
    assert result["unresolved"] == ["Totally Unknown Guy"]
    assert len(result["side_b"]) == 0
    # Side A's value still gets reported even though B is incomplete -- caller can see the gap.
    assert result["total_a"] == 5000


def test_dynasty_trade_uses_superflex_values_for_superflex_league(conn):
    _add_league(conn, "dynasty", roster_positions=["QB", "QB", "RB", "WR", "BN"])
    _add_ktc_value(conn, "QB Guy", "QB", 3000, qb_mode="1qb")
    _add_ktc_value(conn, "QB Guy", "QB", 9000, qb_mode="superflex")
    _add_ktc_value(conn, "RB Guy", "RB", 5000, qb_mode="1qb")
    _add_ktc_value(conn, "RB Guy", "RB", 5000, qb_mode="superflex")
    conn.commit()

    result = analyze_trade(conn, "L1", side_a_names=["QB Guy"], side_b_names=["RB Guy"])
    assert result["qb_mode"] == "superflex"
    assert result["total_a"] == 9000  # not the 1qb value of 3000
    # A sends the 9000-value QB, receives the 5000-value RB -- A gives up more than gets, B wins.
    assert result["winner"] == "B"


def test_unsynced_league_raises_clear_error(conn):
    with pytest.raises(TradeAnalyzerError, match="hasn't been synced"):
        analyze_trade(conn, "NOPE", ["Player"], ["Other Player"])
