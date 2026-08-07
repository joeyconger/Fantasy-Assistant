import sqlite3

import responses

from fantasy_assistant.db import init_db
from fantasy_assistant.platforms.sleeper.client import SleeperClient
from fantasy_assistant.platforms.sleeper.weekly_points import current_completed_weeks, sync_weekly_points

LEAGUE_ID = "L1"


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


@responses.activate
def test_sync_weekly_points_upserts_players_points():
    matchup_week1 = [
        {"roster_id": 1, "players_points": {"1001": 12.5, "1002": 0.0}},
        {"roster_id": 2, "players_points": {"1003": 8.0}},
    ]
    matchup_week2 = [
        {"roster_id": 1, "players_points": {"1001": 20.0}},
    ]
    responses.add(responses.GET, f"https://api.sleeper.app/v1/league/{LEAGUE_ID}/matchups/1", json=matchup_week1)
    responses.add(responses.GET, f"https://api.sleeper.app/v1/league/{LEAGUE_ID}/matchups/2", json=matchup_week2)

    conn = _make_db()
    client = SleeperClient()
    count = sync_weekly_points(conn, client, LEAGUE_ID, [1, 2])
    assert count == 4

    row = conn.execute(
        "SELECT points FROM player_weekly_points WHERE league_id = ? AND player_id = '1001' AND week = 2", (LEAGUE_ID,)
    ).fetchone()
    assert row["points"] == 20.0


@responses.activate
def test_current_completed_weeks_regular_season():
    responses.add(responses.GET, "https://api.sleeper.app/v1/state/nfl", json={"week": 5, "season_type": "regular"})
    client = SleeperClient()
    weeks = current_completed_weeks(client, lookback=4)
    assert weeks == [1, 2, 3, 4]


@responses.activate
def test_current_completed_weeks_preseason_returns_empty():
    responses.add(responses.GET, "https://api.sleeper.app/v1/state/nfl", json={"week": 2, "season_type": "preseason"})
    client = SleeperClient()
    weeks = current_completed_weeks(client, lookback=4)
    assert weeks == []


@responses.activate
def test_current_completed_weeks_week_one_returns_empty():
    responses.add(responses.GET, "https://api.sleeper.app/v1/state/nfl", json={"week": 1, "season_type": "regular"})
    client = SleeperClient()
    weeks = current_completed_weeks(client, lookback=4)
    assert weeks == []
