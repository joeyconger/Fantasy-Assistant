import sqlite3

from fantasy_assistant.db import init_db
from fantasy_assistant.platforms.matching import match_players, normalize_name


def test_normalize_name_strips_suffixes_and_punctuation():
    assert normalize_name("Michael Pittman Jr.") == "michael pittman"
    assert normalize_name("Odell Beckham III") == "odell beckham"
    assert normalize_name("D'Andre Swift") == "dandre swift"
    assert normalize_name("Amon-Ra St. Brown") == "amonra st brown"


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_match_players_matches_despite_suffix_difference():
    conn = _make_db()
    # Realistic cross-platform mismatch: one source includes the suffix, the other doesn't.
    conn.execute("INSERT INTO players (player_id, platform, full_name, position) VALUES ('1', 'sleeper', 'Michael Pittman Jr.', 'WR')")
    conn.execute("INSERT INTO players (player_id, platform, full_name, position) VALUES ('9', 'espn', 'Michael Pittman', 'WR')")
    conn.commit()

    matches = match_players(conn, "sleeper", "espn")
    assert len(matches) == 1
    assert matches[0]["a_player_id"] == "1"
    assert matches[0]["b_player_id"] == "9"


def test_match_players_skips_ambiguous_duplicates():
    conn = _make_db()
    # Two "Josh Johnson"s at the same position on the sleeper side — ambiguous, should not match.
    conn.execute("INSERT INTO players (player_id, platform, full_name, position) VALUES ('1', 'sleeper', 'Josh Johnson', 'QB')")
    conn.execute("INSERT INTO players (player_id, platform, full_name, position) VALUES ('2', 'sleeper', 'Josh Johnson', 'QB')")
    conn.execute("INSERT INTO players (player_id, platform, full_name, position) VALUES ('9', 'espn', 'Josh Johnson', 'QB')")
    conn.commit()

    matches = match_players(conn, "sleeper", "espn")
    assert matches == []


def test_match_players_no_match_across_positions():
    conn = _make_db()
    conn.execute("INSERT INTO players (player_id, platform, full_name, position) VALUES ('1', 'sleeper', 'Taysom Hill', 'QB')")
    conn.execute("INSERT INTO players (player_id, platform, full_name, position) VALUES ('9', 'espn', 'Taysom Hill', 'TE')")
    conn.commit()

    matches = match_players(conn, "sleeper", "espn")
    assert matches == []
