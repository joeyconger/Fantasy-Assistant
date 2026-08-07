import sqlite3
from datetime import datetime, timezone

import pytest

from fantasy_assistant.db import init_db

NOW = datetime.now(timezone.utc).isoformat()


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_db(c)
    return c


def _add_league(conn, league_id="L1", format_="redraft", roster_positions=None):
    import json

    conn.execute(
        "INSERT INTO leagues (league_id, platform, name, season, format, total_rosters, roster_positions) VALUES (?, 'sleeper', 'Test', '2026', ?, 1, ?)",
        (league_id, format_, json.dumps(roster_positions) if roster_positions else None),
    )


def _add_player(conn, player_id, platform, name, position, team="CIN"):
    conn.execute(
        "INSERT INTO players (player_id, platform, full_name, position, team) VALUES (?, ?, ?, ?, ?)",
        (player_id, platform, name, position, team),
    )


# ---- draft_board ----


def test_find_rank_inefficiencies_flags_big_divergence(conn):
    from fantasy_assistant.analysis.draft_board import find_rank_inefficiencies

    _add_player(conn, "1", "sleeper", "Player A", "WR")
    _add_player(conn, "9", "espn", "Player A", "WR")
    conn.execute("INSERT INTO player_rankings (player_id, platform, source, overall_rank, fetched_at) VALUES ('1','sleeper','sleeper_search_rank',5,?)", (NOW,))
    conn.execute("INSERT INTO player_rankings (player_id, platform, source, overall_rank, fetched_at) VALUES ('9','espn','espn_standard_rank',80,?)", (NOW,))
    conn.commit()

    results = find_rank_inefficiencies(conn)
    assert len(results) == 1
    assert results[0]["delta"] == 5 - 80
    # Sleeper rank 5 vs ESPN rank 80: Sleeper values this player far higher,
    # so an ESPN-league drafter could get him later than his "true" value.
    assert "ESPN drafters may get value" in results[0]["note"]


def test_find_rank_inefficiencies_excludes_players_past_rank_cap(conn):
    from fantasy_assistant.analysis.draft_board import find_rank_inefficiencies

    _add_player(conn, "1", "sleeper", "Deep Bench Guy", "WR")
    _add_player(conn, "9", "espn", "Deep Bench Guy", "WR")
    conn.execute("INSERT INTO player_rankings (player_id, platform, source, overall_rank, fetched_at) VALUES ('1','sleeper','sleeper_search_rank',5000,?)", (NOW,))
    conn.execute("INSERT INTO player_rankings (player_id, platform, source, overall_rank, fetched_at) VALUES ('9','espn','espn_standard_rank',10,?)", (NOW,))
    conn.commit()

    assert find_rank_inefficiencies(conn, rank_cap=300) == []


# ---- performance_trend ----


def test_compute_trends_recent_vs_season(conn):
    from fantasy_assistant.analysis.performance_trend import compute_trends

    _add_league(conn)
    for week, pts in [(1, 5.0), (2, 5.0), (3, 20.0), (4, 20.0)]:
        conn.execute(
            "INSERT INTO player_weekly_points (league_id, player_id, week, points, fetched_at) VALUES ('L1', 'p1', ?, ?, ?)",
            (week, pts, NOW),
        )
    conn.commit()

    trends = compute_trends(conn, "L1", recent_weeks=2)
    t = trends["p1"]
    assert t["season_avg"] == 12.5
    assert t["recent_avg"] == 20.0
    assert t["trend"] == pytest.approx(7.5)


def test_compute_trends_handles_short_history(conn):
    from fantasy_assistant.analysis.performance_trend import compute_trends

    _add_league(conn)
    conn.execute(
        "INSERT INTO player_weekly_points (league_id, player_id, week, points, fetched_at) VALUES ('L1', 'p1', 1, 8.0, ?)",
        (NOW,),
    )
    conn.commit()

    trends = compute_trends(conn, "L1", recent_weeks=3)
    assert trends["p1"]["weeks_played"] == 1
    assert trends["p1"]["trend"] == 0


# ---- waiver_targets ----


def test_top_waiver_adds_excludes_rostered_players(conn):
    from fantasy_assistant.analysis.waiver_targets import top_waiver_adds

    _add_league(conn)
    _add_player(conn, "rostered", "sleeper", "Rostered Guy", "WR")
    _add_player(conn, "free", "sleeper", "Free Agent Guy", "RB")
    conn.execute("INSERT INTO roster_players (league_id, roster_id, player_id) VALUES ('L1', '1', 'rostered')")
    for week, pts in [(1, 10.0), (2, 12.0)]:
        conn.execute(
            "INSERT INTO player_weekly_points (league_id, player_id, week, points, fetched_at) VALUES ('L1', ?, ?, ?, ?)",
            ("rostered", week, pts, NOW),
        )
        conn.execute(
            "INSERT INTO player_weekly_points (league_id, player_id, week, points, fetched_at) VALUES ('L1', ?, ?, ?, ?)",
            ("free", week, pts, NOW),
        )
    conn.commit()

    results = top_waiver_adds(conn, "L1")
    ids = [r["player_id"] for r in results]
    assert "free" in ids
    assert "rostered" not in ids


def test_top_trade_targets_filters_by_min_trend(conn):
    from fantasy_assistant.analysis.waiver_targets import top_trade_targets

    _add_league(conn)
    _add_player(conn, "hot", "sleeper", "Hot Guy", "WR")
    _add_player(conn, "flat", "sleeper", "Flat Guy", "RB")
    conn.execute("INSERT INTO roster_players (league_id, roster_id, player_id) VALUES ('L1', '1', 'hot')")
    conn.execute("INSERT INTO roster_players (league_id, roster_id, player_id) VALUES ('L1', '1', 'flat')")
    # 5 weeks so the default recent_weeks=3 window is a genuine subset of the
    # season, not the entire history (which would force trend to 0).
    for week, pts in [(1, 5.0), (2, 5.0), (3, 20.0), (4, 20.0), (5, 20.0)]:
        conn.execute(
            "INSERT INTO player_weekly_points (league_id, player_id, week, points, fetched_at) VALUES ('L1', 'hot', ?, ?, ?)",
            (week, pts, NOW),
        )
    for week, pts in [(1, 8.0), (2, 8.0), (3, 8.0), (4, 8.0), (5, 8.0)]:
        conn.execute(
            "INSERT INTO player_weekly_points (league_id, player_id, week, points, fetched_at) VALUES ('L1', 'flat', ?, ?, ?)",
            (week, pts, NOW),
        )
    conn.commit()

    results = top_trade_targets(conn, "L1", min_trend=2.0)
    ids = [r["player_id"] for r in results]
    assert "hot" in ids
    assert "flat" not in ids


# ---- buy_low_sell_high ----


def test_buy_low_flagged_when_performance_up_and_market_flat(conn):
    from fantasy_assistant.analysis.buy_low_sell_high import find_buy_low_sell_high

    _add_league(conn, format_="dynasty")
    _add_player(conn, "p1", "sleeper", "Trending Guy", "WR")
    conn.execute("INSERT INTO roster_players (league_id, roster_id, player_id) VALUES ('L1', '1', 'p1')")
    for week, pts in [(1, 5.0), (2, 5.0), (3, 20.0), (4, 20.0)]:
        conn.execute(
            "INSERT INTO player_weekly_points (league_id, player_id, week, points, fetched_at) VALUES ('L1', 'p1', ?, ?, ?)",
            (week, pts, NOW),
        )
    conn.execute(
        "INSERT INTO market_values (source, format, normalized_name, full_name, position, value, fetched_at) VALUES ('ktc','dynasty','trending guy','Trending Guy','WR',5000,?)",
        (NOW,),
    )
    conn.execute(
        "INSERT INTO market_values_prior (source, format, normalized_name, position, value, fetched_at) VALUES ('ktc','dynasty','trending guy','WR',5000,?)",
        (NOW,),
    )
    conn.commit()

    results = find_buy_low_sell_high(conn, "L1", "dynasty")
    assert len(results) == 1
    flags = [f for f, _ in results[0]["flags"]]
    assert "buy_low" in flags


def test_sell_high_flagged_when_performance_down_and_market_still_up(conn):
    from fantasy_assistant.analysis.buy_low_sell_high import find_buy_low_sell_high

    _add_league(conn, format_="dynasty")
    _add_player(conn, "p1", "sleeper", "Fading Guy", "WR")
    conn.execute("INSERT INTO roster_players (league_id, roster_id, player_id) VALUES ('L1', '1', 'p1')")
    for week, pts in [(1, 20.0), (2, 20.0), (3, 5.0), (4, 5.0)]:
        conn.execute(
            "INSERT INTO player_weekly_points (league_id, player_id, week, points, fetched_at) VALUES ('L1', 'p1', ?, ?, ?)",
            (week, pts, NOW),
        )
    conn.execute(
        "INSERT INTO market_values (source, format, normalized_name, full_name, position, value, fetched_at) VALUES ('ktc','dynasty','fading guy','Fading Guy','WR',6000,?)",
        (NOW,),
    )
    conn.execute(
        "INSERT INTO market_values_prior (source, format, normalized_name, position, value, fetched_at) VALUES ('ktc','dynasty','fading guy','WR',4000,?)",
        (NOW,),
    )
    conn.commit()

    results = find_buy_low_sell_high(conn, "L1", "dynasty")
    assert len(results) == 1
    flags = [f for f, _ in results[0]["flags"]]
    assert "sell_high" in flags


def test_no_flags_when_performance_and_market_agree(conn):
    from fantasy_assistant.analysis.buy_low_sell_high import find_buy_low_sell_high

    _add_league(conn, format_="dynasty")
    _add_player(conn, "p1", "sleeper", "Steady Guy", "WR")
    conn.execute("INSERT INTO roster_players (league_id, roster_id, player_id) VALUES ('L1', '1', 'p1')")
    for week, pts in [(1, 10.0), (2, 10.0), (3, 10.0)]:
        conn.execute(
            "INSERT INTO player_weekly_points (league_id, player_id, week, points, fetched_at) VALUES ('L1', 'p1', ?, ?, ?)",
            (week, pts, NOW),
        )
    conn.commit()

    results = find_buy_low_sell_high(conn, "L1", "dynasty")
    assert results == []


def test_buy_low_sell_high_uses_superflex_values_for_superflex_league(conn):
    from fantasy_assistant.analysis.buy_low_sell_high import find_buy_low_sell_high

    _add_league(conn, format_="dynasty", roster_positions=["QB", "QB", "RB", "WR", "TE", "BN"])
    _add_player(conn, "p1", "sleeper", "Trending QB", "QB")
    conn.execute("INSERT INTO roster_players (league_id, roster_id, player_id) VALUES ('L1', '1', 'p1')")
    for week, pts in [(1, 15.0), (2, 15.0), (3, 30.0), (4, 30.0)]:
        conn.execute(
            "INSERT INTO player_weekly_points (league_id, player_id, week, points, fetched_at) VALUES ('L1', 'p1', ?, ?, ?)",
            (week, pts, NOW),
        )
    # 1QB value: rose a lot (would suppress a buy_low flag if wrongly used).
    conn.execute(
        "INSERT INTO market_values (source, format, qb_mode, normalized_name, full_name, position, value, fetched_at) VALUES ('ktc','dynasty','1qb','trending qb','Trending QB','QB',9000,?)",
        (NOW,),
    )
    conn.execute(
        "INSERT INTO market_values_prior (source, format, qb_mode, normalized_name, position, value, fetched_at) VALUES ('ktc','dynasty','1qb','trending qb','QB',3000,?)",
        (NOW,),
    )
    # Superflex value: flat (should be what actually drives the flag, since this league is superflex).
    conn.execute(
        "INSERT INTO market_values (source, format, qb_mode, normalized_name, full_name, position, value, fetched_at) VALUES ('ktc','dynasty','superflex','trending qb','Trending QB','QB',9500,?)",
        (NOW,),
    )
    conn.execute(
        "INSERT INTO market_values_prior (source, format, qb_mode, normalized_name, position, value, fetched_at) VALUES ('ktc','dynasty','superflex','trending qb','QB',9500,?)",
        (NOW,),
    )
    conn.commit()

    results = find_buy_low_sell_high(conn, "L1", "dynasty")
    assert len(results) == 1
    assert results[0]["qb_mode"] == "superflex"
    assert results[0]["market_delta"] == 0  # superflex delta, NOT the 1qb delta of +6000
    flags = [f for f, _ in results[0]["flags"]]
    assert "buy_low" in flags
