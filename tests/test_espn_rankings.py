import sqlite3

import responses

from fantasy_assistant.db import init_db
from fantasy_assistant.platforms.espn.client import ESPNClient
from fantasy_assistant.platforms.espn.rankings import sync_player_pool

SEASON = 2026
URL = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON}/players"

POOL_RESPONSE = [
    {
        "player": {
            "id": 4046,
            "fullName": "Test WR",
            "defaultPositionId": 3,
            "proTeamId": 12,
            "draftRanksByRankType": {"STANDARD": {"rank": 15, "auctionValue": 40}},
            "ownership": {"averageDraftPosition": 14.2, "percentOwned": 99.1},
        }
    },
    {
        "player": {
            "id": 5000,
            "fullName": "No Rank Guy",
            "defaultPositionId": 2,
            "proTeamId": 6,
            "draftRanksByRankType": {},
            "ownership": {},
        }
    },
]


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


@responses.activate
def test_sync_player_pool_upserts_players_and_rankings():
    responses.add(responses.GET, URL, json=POOL_RESPONSE)
    conn = _make_db()
    client = ESPNClient()

    count = sync_player_pool(conn, client, SEASON)
    assert count == 1  # only the player with an actual rank/adp counts

    player = conn.execute("SELECT * FROM players WHERE player_id = '4046' AND platform = 'espn'").fetchone()
    assert player["full_name"] == "Test WR"
    assert player["position"] == "WR"
    assert player["team"] == "KC"

    ranking = conn.execute(
        "SELECT * FROM player_rankings WHERE player_id = '4046' AND platform = 'espn' AND source = 'espn_standard_rank'"
    ).fetchone()
    assert ranking["overall_rank"] == 15
    assert ranking["adp"] == 14.2

    # Player with no rank/adp still gets a players row (for matching purposes)
    # but no player_rankings row.
    no_rank = conn.execute("SELECT * FROM players WHERE player_id = '5000' AND platform = 'espn'").fetchone()
    assert no_rank is not None
    no_rank_ranking = conn.execute(
        "SELECT * FROM player_rankings WHERE player_id = '5000' AND platform = 'espn'"
    ).fetchone()
    assert no_rank_ranking is None
