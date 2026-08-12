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


def _add_league(conn, league_id="L1", format_="redraft", roster_positions=None, platform="sleeper"):
    import json

    conn.execute(
        "INSERT INTO leagues (league_id, platform, name, season, format, total_rosters, roster_positions) VALUES (?, ?, 'Test', '2026', ?, 1, ?)",
        (league_id, platform, format_, json.dumps(roster_positions) if roster_positions else None),
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


def test_find_rank_inefficiencies_qb_mode_uses_correct_espn_source(conn):
    from fantasy_assistant.analysis.draft_board import find_rank_inefficiencies

    _add_player(conn, "1", "sleeper", "Player QB", "QB")
    _add_player(conn, "9", "espn", "Player QB", "QB")
    conn.execute("INSERT INTO player_rankings (player_id, platform, source, overall_rank, fetched_at) VALUES ('1','sleeper','sleeper_search_rank',20,?)", (NOW,))
    conn.execute("INSERT INTO player_rankings (player_id, platform, source, overall_rank, fetched_at) VALUES ('9','espn','espn_standard_rank',60,?)", (NOW,))
    conn.execute("INSERT INTO player_rankings (player_id, platform, source, overall_rank, fetched_at) VALUES ('9','espn','espn_superflex_rank',22,?)", (NOW,))
    conn.commit()

    one_qb = find_rank_inefficiencies(conn, qb_mode="1qb")
    sf = find_rank_inefficiencies(conn, qb_mode="superflex")

    assert one_qb[0]["espn_rank"] == 60
    assert sf[0]["espn_rank"] == 22
    # Sleeper side is qb-agnostic and identical either way.
    assert one_qb[0]["sleeper_rank"] == sf[0]["sleeper_rank"] == 20


def test_find_rank_inefficiencies_superflex_empty_when_no_espn_superflex_data(conn):
    from fantasy_assistant.analysis.draft_board import find_rank_inefficiencies

    _add_player(conn, "1", "sleeper", "Player A", "WR")
    _add_player(conn, "9", "espn", "Player A", "WR")
    conn.execute("INSERT INTO player_rankings (player_id, platform, source, overall_rank, fetched_at) VALUES ('1','sleeper','sleeper_search_rank',5,?)", (NOW,))
    conn.execute("INSERT INTO player_rankings (player_id, platform, source, overall_rank, fetched_at) VALUES ('9','espn','espn_standard_rank',80,?)", (NOW,))
    conn.commit()

    # No espn_superflex_rank row exists at all (honest absence, not a fabricated mirror).
    assert find_rank_inefficiencies(conn, qb_mode="superflex") == []
    assert len(find_rank_inefficiencies(conn, qb_mode="1qb")) == 1


def test_find_rank_inefficiencies_excludes_defensive_positions(conn):
    from fantasy_assistant.analysis.draft_board import find_rank_inefficiencies

    _add_player(conn, "1", "sleeper", "Some Defense", "D/ST")
    _add_player(conn, "9", "espn", "Some Defense", "D/ST")
    conn.execute("INSERT INTO player_rankings (player_id, platform, source, overall_rank, fetched_at) VALUES ('1','sleeper','sleeper_search_rank',50,?)", (NOW,))
    conn.execute("INSERT INTO player_rankings (player_id, platform, source, overall_rank, fetched_at) VALUES ('9','espn','espn_standard_rank',200,?)", (NOW,))
    conn.commit()

    assert find_rank_inefficiencies(conn) == []


def test_find_rank_inefficiencies_superflex_uses_position_rank_for_non_qb(conn):
    """Sleeper's search_rank has no Superflex-aware ordering, but ESPN's
    Superflex rank type genuinely crowds QBs to the top — comparing raw
    overall rank for a RB in that situation would produce a huge fake delta
    driven entirely by how many QBs ESPN now ranks above him, not a real
    disagreement. Set up a pool where that crowding is obvious and confirm
    the RB's delta reflects position rank, not the crushed overall rank."""
    from fantasy_assistant.analysis.draft_board import find_rank_inefficiencies

    _add_player(conn, "rb_a", "sleeper", "Value RB", "RB")
    _add_player(conn, "rb_b", "espn", "Value RB", "RB")
    # Sleeper: this RB is the best RB in its pool (overall rank 10, position rank 1).
    conn.execute("INSERT INTO player_rankings (player_id, platform, source, overall_rank, fetched_at) VALUES ('rb_a','sleeper','sleeper_search_rank',10,?)", (NOW,))
    # ESPN Superflex: same RB is still the best RB (position rank 1), but a
    # wave of QBs crowded above it drags its overall rank down to 90.
    conn.execute("INSERT INTO player_rankings (player_id, platform, source, overall_rank, fetched_at) VALUES ('rb_b','espn','espn_superflex_rank',90,?)", (NOW,))
    for i in range(5):
        qb_sleeper_id, qb_espn_id = f"qb_s{i}", f"qb_e{i}"
        _add_player(conn, qb_sleeper_id, "sleeper", f"Filler QB {i}", "QB")
        _add_player(conn, qb_espn_id, "espn", f"Filler QB {i}", "QB")
        conn.execute(
            "INSERT INTO player_rankings (player_id, platform, source, overall_rank, fetched_at) VALUES (?,'sleeper','sleeper_search_rank',?,?)",
            (qb_sleeper_id, 200 + i, NOW),
        )
        conn.execute(
            "INSERT INTO player_rankings (player_id, platform, source, overall_rank, fetched_at) VALUES (?,'espn','espn_superflex_rank',?,?)",
            (qb_espn_id, i + 1, NOW),
        )
    conn.commit()

    results = find_rank_inefficiencies(conn, qb_mode="superflex")
    rb_result = next(r for r in results if r["position"] == "RB")
    assert rb_result["position_relative"] is True
    # Both sides rank this RB #1 at its position — position-rank delta is 0,
    # not the huge fake delta raw overall rank (10 - 90 = -80) would show.
    assert rb_result["sleeper_rank"] == 1
    assert rb_result["espn_rank"] == 1
    assert rb_result["delta"] == 0


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


# ---- platform-awareness (waiver/trade/buy-sell must work for ESPN leagues too, not just Sleeper) ----


def test_waiver_and_trade_targets_work_for_espn_league():
    """Regression test: these functions used to hardcode platform='sleeper'
    in their SQL joins, which meant an ESPN league would silently return
    zero candidates (looking identical to 'no data yet') instead of
    actually working. This proves an all-ESPN dataset produces results."""
    from fantasy_assistant.analysis.waiver_targets import top_trade_targets, top_waiver_adds

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)

    _add_league(conn, platform="espn")
    _add_player(conn, "e-rostered", "espn", "Rostered ESPN Guy", "WR")
    _add_player(conn, "e-free", "espn", "Free ESPN Guy", "RB")
    conn.execute("INSERT INTO roster_players (league_id, roster_id, player_id) VALUES ('L1', '1', 'e-rostered')")
    conn.execute(
        "INSERT INTO player_rankings (player_id, platform, source, overall_rank, fetched_at) VALUES ('e-rostered', 'espn', 'espn_standard_rank', 12, ?)",
        (NOW,),
    )
    for week, pts in [(1, 5.0), (2, 5.0), (3, 20.0), (4, 20.0)]:
        conn.execute(
            "INSERT INTO player_weekly_points (league_id, player_id, week, points, fetched_at) VALUES ('L1', 'e-rostered', ?, ?, ?)",
            (week, pts, NOW),
        )
        conn.execute(
            "INSERT INTO player_weekly_points (league_id, player_id, week, points, fetched_at) VALUES ('L1', 'e-free', ?, ?, ?)",
            (week, pts, NOW),
        )
    conn.commit()

    adds = top_waiver_adds(conn, "L1")
    assert [a["player_id"] for a in adds] == ["e-free"]

    targets = top_trade_targets(conn, "L1", min_trend=2.0)
    assert len(targets) == 1
    assert targets[0]["player_id"] == "e-rostered"
    assert targets[0]["rank"] == 12  # confirms the ESPN-specific rank source was used, not Sleeper's


def test_unsynced_league_raises_clear_error():
    from fantasy_assistant.analysis.waiver_targets import top_waiver_adds

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)

    with pytest.raises(ValueError, match="hasn't been synced"):
        top_waiver_adds(conn, "NONEXISTENT")


# ---- personalization (my_owner_id) ----


def test_top_trade_targets_excludes_my_own_roster_when_owner_id_given(conn):
    from fantasy_assistant.analysis.waiver_targets import top_trade_targets

    _add_league(conn)
    conn.execute("INSERT INTO rosters (league_id, roster_id, owner_id) VALUES ('L1', '1', 'me')")
    conn.execute("INSERT INTO rosters (league_id, roster_id, owner_id) VALUES ('L1', '2', 'rival')")
    _add_player(conn, "mine", "sleeper", "My Guy", "WR")
    _add_player(conn, "theirs", "sleeper", "Rival Guy", "WR")
    conn.execute("INSERT INTO roster_players (league_id, roster_id, player_id) VALUES ('L1', '1', 'mine')")
    conn.execute("INSERT INTO roster_players (league_id, roster_id, player_id) VALUES ('L1', '2', 'theirs')")
    for week, pts in [(1, 5.0), (2, 5.0), (3, 20.0), (4, 20.0), (5, 20.0)]:
        for pid in ("mine", "theirs"):
            conn.execute(
                "INSERT INTO player_weekly_points (league_id, player_id, week, points, fetched_at) VALUES ('L1', ?, ?, ?, ?)",
                (pid, week, pts, NOW),
            )
    conn.commit()

    without_owner = top_trade_targets(conn, "L1", min_trend=2.0)
    with_owner = top_trade_targets(conn, "L1", min_trend=2.0, my_owner_id="me")

    ids_without = {t["player_id"] for t in without_owner}
    ids_with = {t["player_id"] for t in with_owner}
    assert ids_without == {"mine", "theirs"}  # no personalization: both show up
    assert ids_with == {"theirs"}  # personalized: my own player excluded


def test_top_waiver_adds_flags_fills_need(conn):
    from fantasy_assistant.analysis.waiver_targets import top_waiver_adds

    _add_league(conn)
    conn.execute("INSERT INTO rosters (league_id, roster_id, owner_id) VALUES ('L1', '1', 'me')")
    # My roster has one weak RB; league has strong RBs elsewhere.
    _add_player(conn, "my_rb", "sleeper", "My RB", "RB")
    _add_player(conn, "rival_rb", "sleeper", "Rival RB", "RB")
    conn.execute("INSERT INTO roster_players (league_id, roster_id, player_id) VALUES ('L1', '1', 'my_rb')")
    conn.execute("INSERT INTO roster_players (league_id, roster_id, player_id) VALUES ('L1', '2', 'rival_rb')")
    conn.execute("INSERT INTO player_rankings (player_id, platform, source, overall_rank, fetched_at) VALUES ('my_rb','sleeper','sleeper_search_rank',200,?)", (NOW,))
    conn.execute("INSERT INTO player_rankings (player_id, platform, source, overall_rank, fetched_at) VALUES ('rival_rb','sleeper','sleeper_search_rank',5,?)", (NOW,))

    _add_player(conn, "free_rb", "sleeper", "Free RB", "RB")
    _add_player(conn, "free_wr", "sleeper", "Free WR", "WR")
    for pid in ("free_rb", "free_wr"):
        for week, pts in [(1, 5.0), (2, 10.0)]:
            conn.execute(
                "INSERT INTO player_weekly_points (league_id, player_id, week, points, fetched_at) VALUES ('L1', ?, ?, ?, ?)",
                (pid, week, pts, NOW),
            )
    conn.commit()

    results = top_waiver_adds(conn, "L1", my_owner_id="me")
    rb_result = next(r for r in results if r["player_id"] == "free_rb")
    wr_result = next(r for r in results if r["player_id"] == "free_wr")
    assert rb_result["fills_need"] is True  # RB is my weak position
    assert wr_result["fills_need"] is False  # no WR data at all — not flagged as a need


def test_fills_need_is_none_without_owner_id(conn):
    from fantasy_assistant.analysis.waiver_targets import top_waiver_adds

    _add_league(conn)
    _add_player(conn, "free_rb", "sleeper", "Free RB", "RB")
    for week, pts in [(1, 5.0), (2, 10.0)]:
        conn.execute(
            "INSERT INTO player_weekly_points (league_id, player_id, week, points, fetched_at) VALUES ('L1', 'free_rb', ?, ?, ?)",
            (week, pts, NOW),
        )
    conn.commit()

    results = top_waiver_adds(conn, "L1")
    assert results[0]["fills_need"] is None


def test_buy_low_sell_high_tags_ownership(conn):
    from fantasy_assistant.analysis.buy_low_sell_high import find_buy_low_sell_high

    _add_league(conn, format_="dynasty")
    conn.execute("INSERT INTO rosters (league_id, roster_id, owner_id) VALUES ('L1', '1', 'me')")
    conn.execute("INSERT INTO rosters (league_id, roster_id, owner_id) VALUES ('L1', '2', 'rival')")
    _add_player(conn, "mine", "sleeper", "My Trending Guy", "WR")
    _add_player(conn, "theirs", "sleeper", "Their Trending Guy", "WR")
    conn.execute("INSERT INTO roster_players (league_id, roster_id, player_id) VALUES ('L1', '1', 'mine')")
    conn.execute("INSERT INTO roster_players (league_id, roster_id, player_id) VALUES ('L1', '2', 'theirs')")
    for pid in ("mine", "theirs"):
        for week, pts in [(1, 5.0), (2, 5.0), (3, 20.0), (4, 20.0)]:
            conn.execute(
                "INSERT INTO player_weekly_points (league_id, player_id, week, points, fetched_at) VALUES ('L1', ?, ?, ?, ?)",
                (pid, week, pts, NOW),
            )
    conn.commit()

    results = find_buy_low_sell_high(conn, "L1", "dynasty", my_owner_id="me")
    by_id = {r["player_id"]: r for r in results}
    assert by_id["mine"]["owned_by_me"] is True
    assert by_id["theirs"]["owned_by_me"] is False

    results_no_owner = find_buy_low_sell_high(conn, "L1", "dynasty")
    assert all(r["owned_by_me"] is None for r in results_no_owner)
