import sqlite3

import pytest

from fantasy_assistant.analysis.roster_needs import RosterNeedsError, compute_roster_needs
from fantasy_assistant.db import init_db


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_db(c)
    return c


def _setup_league(conn):
    conn.execute("INSERT INTO leagues (league_id, platform, name, season, format, total_rosters) VALUES ('L1', 'sleeper', 'Test', '2026', 'redraft', 3)")
    conn.execute("INSERT INTO rosters (league_id, roster_id, owner_id) VALUES ('L1', '1', 'me')")
    conn.execute("INSERT INTO rosters (league_id, roster_id, owner_id) VALUES ('L1', '2', 'rival1')")
    conn.execute("INSERT INTO rosters (league_id, roster_id, owner_id) VALUES ('L1', '3', 'rival2')")


def _add_player(conn, pid, name, position, rank):
    conn.execute("INSERT INTO players (player_id, platform, full_name, position) VALUES (?, 'sleeper', ?, ?)", (pid, name, position))
    conn.execute(
        "INSERT INTO player_rankings (player_id, platform, source, overall_rank, fetched_at) VALUES (?, 'sleeper', 'sleeper_search_rank', ?, '2026-01-01')",
        (pid, rank),
    )


def test_flags_weak_position_when_my_players_rank_worse_than_league(conn):
    _setup_league(conn)
    # My RB is much worse-ranked than the league's other RBs.
    _add_player(conn, "my_rb", "My RB", "RB", 150)
    _add_player(conn, "rival_rb1", "Rival RB 1", "RB", 10)
    _add_player(conn, "rival_rb2", "Rival RB 2", "RB", 12)
    conn.execute("INSERT INTO roster_players (league_id, roster_id, player_id) VALUES ('L1', '1', 'my_rb')")
    conn.execute("INSERT INTO roster_players (league_id, roster_id, player_id) VALUES ('L1', '2', 'rival_rb1')")
    conn.execute("INSERT INTO roster_players (league_id, roster_id, player_id) VALUES ('L1', '3', 'rival_rb2')")
    conn.commit()

    results = compute_roster_needs(conn, "L1", "me")
    rb = next(r for r in results if r["position"] == "RB")
    assert rb["need_level"] == "weak"
    assert rb["need_score"] > 0


def test_flags_strong_position_when_my_players_rank_better(conn):
    _setup_league(conn)
    _add_player(conn, "my_wr", "My WR", "WR", 5)
    _add_player(conn, "rival_wr1", "Rival WR 1", "WR", 100)
    _add_player(conn, "rival_wr2", "Rival WR 2", "WR", 110)
    conn.execute("INSERT INTO roster_players (league_id, roster_id, player_id) VALUES ('L1', '1', 'my_wr')")
    conn.execute("INSERT INTO roster_players (league_id, roster_id, player_id) VALUES ('L1', '2', 'rival_wr1')")
    conn.execute("INSERT INTO roster_players (league_id, roster_id, player_id) VALUES ('L1', '3', 'rival_wr2')")
    conn.commit()

    results = compute_roster_needs(conn, "L1", "me")
    wr = next(r for r in results if r["position"] == "WR")
    assert wr["need_level"] == "strong"
    assert wr["need_score"] < 0


def test_position_with_zero_rostered_players_is_most_urgent_need(conn):
    _setup_league(conn)
    _add_player(conn, "my_rb", "My RB", "RB", 50)
    _add_player(conn, "rival_te", "Rival TE", "TE", 30)
    conn.execute("INSERT INTO roster_players (league_id, roster_id, player_id) VALUES ('L1', '1', 'my_rb')")
    conn.execute("INSERT INTO roster_players (league_id, roster_id, player_id) VALUES ('L1', '2', 'rival_te')")
    conn.commit()

    results = compute_roster_needs(conn, "L1", "me")
    # I have zero TEs at all (league has one, rostered by someone else) — that
    # should be the first/most urgent result, need_score None (can't average zero).
    assert results[0]["position"] == "TE"
    assert results[0]["need_score"] is None
    assert results[0]["my_player_count"] == 0


def test_unknown_league_raises_clear_error(conn):
    with pytest.raises(RosterNeedsError, match="hasn't been synced"):
        compute_roster_needs(conn, "NOPE", "me")


def test_unknown_owner_raises_clear_error(conn):
    _setup_league(conn)
    conn.commit()
    with pytest.raises(RosterNeedsError, match="No roster found"):
        compute_roster_needs(conn, "L1", "not-a-real-owner")
