"""Verifies Sleeper sync logic against mocked API responses (no live network).

These fixtures mirror the real Sleeper API response shapes documented at
https://docs.sleeper.com/ — league/rosters/users/players endpoints.
"""

import sqlite3

import responses

from fantasy_assistant.db import init_db
from fantasy_assistant.platforms.sleeper.client import SleeperClient
from fantasy_assistant.platforms.sleeper.sync import sync_league, sync_players

LEAGUE_ID = "123456789"

LEAGUE_RESPONSE = {
    "league_id": LEAGUE_ID,
    "name": "Test Dynasty League",
    "season": "2026",
    "total_rosters": 2,
    "settings": {"type": 2},
    "scoring_settings": {"rec": 1.0, "pass_td": 4},
    "roster_positions": ["QB", "RB", "WR", "TE", "FLEX", "BN"],
}

ROSTERS_RESPONSE = [
    {
        "roster_id": 1,
        "owner_id": "u1",
        "players": ["1001", "1002"],
        "starters": ["1001"],
        "taxi": [],
        "reserve": [],
        "settings": {
            "wins": 5, "losses": 2, "ties": 0,
            "fpts": 800, "fpts_decimal": 25,
            "fpts_against": 700, "fpts_against_decimal": 50,
            "waiver_position": 3,
        },
    },
    {
        "roster_id": 2,
        "owner_id": "u2",
        "players": ["1003", "1004"],
        "starters": ["1003"],
        "taxi": ["1004"],
        "reserve": [],
        "settings": {
            "wins": 3, "losses": 4, "ties": 0,
            "fpts": 650, "fpts_decimal": 0,
            "fpts_against": 720, "fpts_against_decimal": 0,
            "waiver_position": 1,
        },
    },
]

USERS_RESPONSE = [
    {"user_id": "u1", "display_name": "joeyc", "metadata": {"team_name": "The Algorithm"}},
    {"user_id": "u2", "display_name": "rival", "metadata": {}},
]

PLAYERS_RESPONSE = {
    "1001": {"full_name": "Ja'Marr Chase", "position": "WR", "team": "CIN", "status": "Active", "age": 25, "years_exp": 4},
    "1002": {"full_name": "Some Backup", "position": "RB", "team": "CIN", "status": "Active", "age": 26, "years_exp": 3},
    "1003": {"full_name": "Another Player", "position": "TE", "team": "KC", "status": "Active", "age": 27, "years_exp": 5},
}


def make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


@responses.activate
def test_sync_league_upserts_league_owners_rosters():
    responses.add(responses.GET, f"https://api.sleeper.app/v1/league/{LEAGUE_ID}", json=LEAGUE_RESPONSE)
    responses.add(responses.GET, f"https://api.sleeper.app/v1/league/{LEAGUE_ID}/rosters", json=ROSTERS_RESPONSE)
    responses.add(responses.GET, f"https://api.sleeper.app/v1/league/{LEAGUE_ID}/users", json=USERS_RESPONSE)

    conn = make_db()
    client = SleeperClient()

    result = sync_league(conn, client, LEAGUE_ID)

    assert result["format"] == "dynasty"  # settings.type == 2

    league_row = conn.execute("SELECT * FROM leagues WHERE league_id = ?", (LEAGUE_ID,)).fetchone()
    assert league_row["name"] == "Test Dynasty League"
    assert league_row["total_rosters"] == 2

    owners = conn.execute("SELECT * FROM owners WHERE league_id = ? ORDER BY owner_id", (LEAGUE_ID,)).fetchall()
    assert [o["display_name"] for o in owners] == ["joeyc", "rival"]
    assert owners[0]["team_name"] == "The Algorithm"

    rosters = conn.execute("SELECT * FROM rosters WHERE league_id = ? ORDER BY roster_id", (LEAGUE_ID,)).fetchall()
    assert rosters[0]["wins"] == 5
    assert rosters[0]["fpts"] == 800.25
    assert rosters[1]["fpts_against"] == 720.0

    roster_players = conn.execute(
        "SELECT * FROM roster_players WHERE league_id = ? AND roster_id = '2'", (LEAGUE_ID,)
    ).fetchall()
    taxi_flags = {rp["player_id"]: rp["is_taxi"] for rp in roster_players}
    assert taxi_flags["1004"] == 1
    assert taxi_flags["1003"] == 0


@responses.activate
def test_sync_league_redraft_type_detected():
    redraft_league = {**LEAGUE_RESPONSE, "settings": {"type": 0}}
    responses.add(responses.GET, f"https://api.sleeper.app/v1/league/{LEAGUE_ID}", json=redraft_league)
    responses.add(responses.GET, f"https://api.sleeper.app/v1/league/{LEAGUE_ID}/rosters", json=[])
    responses.add(responses.GET, f"https://api.sleeper.app/v1/league/{LEAGUE_ID}/users", json=[])

    conn = make_db()
    result = sync_league(conn, SleeperClient(), LEAGUE_ID)
    assert result["format"] == "redraft"


@responses.activate
def test_sync_league_format_override_wins_over_detection():
    responses.add(responses.GET, f"https://api.sleeper.app/v1/league/{LEAGUE_ID}", json=LEAGUE_RESPONSE)
    responses.add(responses.GET, f"https://api.sleeper.app/v1/league/{LEAGUE_ID}/rosters", json=[])
    responses.add(responses.GET, f"https://api.sleeper.app/v1/league/{LEAGUE_ID}/users", json=[])

    conn = make_db()
    result = sync_league(conn, SleeperClient(), LEAGUE_ID, format_override="devy")
    assert result["format"] == "devy"


@responses.activate
def test_sync_players_populates_and_caches():
    responses.add(responses.GET, "https://api.sleeper.app/v1/players/nfl", json=PLAYERS_RESPONSE)

    conn = make_db()
    client = SleeperClient()

    count = sync_players(conn, client)
    assert count == 3

    chase = conn.execute("SELECT * FROM players WHERE player_id = '1001'").fetchone()
    assert chase["full_name"] == "Ja'Marr Chase"
    assert chase["position"] == "WR"

    # Second call within TTL should skip the network entirely (no mock registered
    # beyond the one call above — a second HTTP call would raise ConnectionError).
    count_again = sync_players(conn, client)
    assert count_again == 0


@responses.activate
def test_sync_players_force_refetches():
    responses.add(responses.GET, "https://api.sleeper.app/v1/players/nfl", json=PLAYERS_RESPONSE)
    responses.add(responses.GET, "https://api.sleeper.app/v1/players/nfl", json=PLAYERS_RESPONSE)

    conn = make_db()
    client = SleeperClient()

    sync_players(conn, client)
    count = sync_players(conn, client, force=True)
    assert count == 3
