"""Verifies ESPN sync logic against mocked API responses (no live network).

Field names mirror what the wider ESPN fantasy tooling community has
reverse-engineered from the unofficial v3 API — there's no official schema
to link to.
"""

import sqlite3

import pytest
import responses

from fantasy_assistant.db import init_db
from fantasy_assistant.platforms.espn.client import ESPNAuthRequired, ESPNClient
from fantasy_assistant.platforms.espn.sync import sync_league

LEAGUE_ID = "509682142"
SEASON = 2026
URL = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON}/segments/0/leagues/{LEAGUE_ID}"

LEAGUE_RESPONSE = {
    "settings": {
        "name": "Test ESPN League",
        "rosterSettings": {
            "lineupSlotCounts": {"0": 1, "2": 2, "4": 2, "6": 1, "23": 1, "20": 6, "21": 1}
        },
        "scoringSettings": {"scoringItems": [{"statId": 53, "points": 1.0}]},
    },
    "members": [
        {"id": "{OWNER-1}", "firstName": "Joey", "lastName": "C", "displayName": "joeyc"},
    ],
    "teams": [
        {
            "id": 1,
            "location": "The",
            "nickname": "Algorithm",
            "owners": ["{OWNER-1}"],
            "waiverRank": 2,
            "record": {"overall": {"wins": 6, "losses": 1, "ties": 0, "pointsFor": 900.5, "pointsAgainst": 750.25}},
            "roster": {
                "entries": [
                    {
                        "playerId": 4046,
                        "lineupSlotId": 0,
                        "playerPoolEntry": {
                            "player": {
                                "fullName": "Test QB",
                                "defaultPositionId": 1,
                                "proTeamId": 12,
                                "injuryStatus": "ACTIVE",
                            }
                        },
                    },
                    {
                        "playerId": 5000,
                        "lineupSlotId": 20,  # bench
                        "playerPoolEntry": {
                            "player": {
                                "fullName": "Bench Guy",
                                "defaultPositionId": 2,
                                "proTeamId": 6,
                                "injuryStatus": "ACTIVE",
                            }
                        },
                    },
                    {
                        "playerId": 6000,
                        "lineupSlotId": 21,  # IR
                        "playerPoolEntry": {
                            "player": {
                                "fullName": "Hurt Guy",
                                "defaultPositionId": 4,
                                "proTeamId": 21,
                                "injuryStatus": "INJURY_RESERVE",
                            }
                        },
                    },
                ]
            },
        }
    ],
}


def make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


@responses.activate
def test_sync_league_public_upserts_everything():
    responses.add(responses.GET, URL, json=LEAGUE_RESPONSE)

    conn = make_db()
    client = ESPNClient()

    result = sync_league(conn, client, LEAGUE_ID, SEASON)
    assert result["format"] == "redraft"  # default when no override

    league_row = conn.execute("SELECT * FROM leagues WHERE league_id = ?", (LEAGUE_ID,)).fetchone()
    assert league_row["name"] == "Test ESPN League"
    assert league_row["platform"] == "espn"
    assert league_row["season"] == "2026"

    owner = conn.execute("SELECT * FROM owners WHERE league_id = ?", (LEAGUE_ID,)).fetchone()
    assert owner["display_name"] == "Joey C"
    assert owner["team_name"] == "The Algorithm"

    roster = conn.execute("SELECT * FROM rosters WHERE league_id = ? AND roster_id = '1'", (LEAGUE_ID,)).fetchone()
    assert roster["wins"] == 6
    assert roster["fpts"] == 900.5

    players = {
        rp["player_id"]: rp
        for rp in conn.execute(
            "SELECT * FROM roster_players WHERE league_id = ? AND roster_id = '1'", (LEAGUE_ID,)
        ).fetchall()
    }
    assert players["4046"]["is_starter"] == 1
    assert players["5000"]["is_starter"] == 0  # bench
    assert players["6000"]["is_ir"] == 1

    qb = conn.execute(
        "SELECT * FROM players WHERE player_id = '4046' AND platform = 'espn'"
    ).fetchone()
    assert qb["full_name"] == "Test QB"
    assert qb["position"] == "QB"
    assert qb["team"] == "KC"


@responses.activate
def test_sync_league_format_override():
    responses.add(responses.GET, URL, json=LEAGUE_RESPONSE)
    conn = make_db()
    result = sync_league(conn, ESPNClient(), LEAGUE_ID, SEASON, format_override="devy")
    assert result["format"] == "devy"


@responses.activate
def test_sync_league_private_raises_auth_required():
    responses.add(responses.GET, URL, status=401, json={"error": "Unauthorized"})
    conn = make_db()
    with pytest.raises(ESPNAuthRequired):
        sync_league(conn, ESPNClient(), LEAGUE_ID, SEASON)


@responses.activate
def test_sync_league_sends_cookies_when_configured():
    responses.add(responses.GET, URL, json=LEAGUE_RESPONSE)
    conn = make_db()
    client = ESPNClient(swid="{ABC}", espn_s2="tokenvalue")

    sync_league(conn, client, LEAGUE_ID, SEASON)

    sent_request = responses.calls[0].request
    assert "SWID={ABC}" in sent_request.headers.get("Cookie", "")
    assert "espn_s2=tokenvalue" in sent_request.headers.get("Cookie", "")


def test_players_pk_scoped_by_platform_no_collision():
    """A Sleeper player and an ESPN player can share the same raw numeric ID
    without clobbering each other, now that players is keyed on (player_id, platform)."""
    conn = make_db()
    conn.execute(
        "INSERT INTO players (player_id, platform, full_name) VALUES ('4046', 'sleeper', 'Sleeper Guy')"
    )
    conn.execute(
        "INSERT INTO players (player_id, platform, full_name) VALUES ('4046', 'espn', 'ESPN Guy')"
    )
    conn.commit()
    rows = conn.execute("SELECT platform, full_name FROM players WHERE player_id = '4046' ORDER BY platform").fetchall()
    assert [(r["platform"], r["full_name"]) for r in rows] == [("espn", "ESPN Guy"), ("sleeper", "Sleeper Guy")]
