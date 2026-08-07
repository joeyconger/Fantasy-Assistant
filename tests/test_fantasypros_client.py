"""Same caveat as test_ktc_client.py: proves the parser is internally
correct against the assumed 'ecrData' structure, not that it matches the
real live page (unverified, see client.py)."""

import responses

from fantasy_assistant.platforms.fantasypros.client import FantasyProsClient, FantasyProsParseError

URL = "https://www.fantasypros.com/nfl/rankings/consensus-cheatsheets.php"


@responses.activate
def test_parses_ecr_data():
    html = """
    <html><body><script>
    var ecrData = {"players": [
        {"player_name": "Christian McCaffrey", "player_position_id": "RB1", "player_team_id": "SF", "rank_ecr": 1},
        {"player_name": "Tyreek Hill", "player_position_id": "WR1", "player_team_id": "MIA", "rank_ecr": 2}
    ]};
    </script></body></html>
    """
    responses.add(responses.GET, URL, body=html)

    client = FantasyProsClient()
    players = client.get_consensus_rankings()
    assert len(players) == 2
    assert players[0]["full_name"] == "Christian McCaffrey"
    assert players[0]["position"] == "RB"
    assert players[0]["overall_rank"] == 1


@responses.activate
def test_missing_ecr_data_raises_parse_error():
    responses.add(responses.GET, URL, body="<html><body>no data here</body></html>")

    client = FantasyProsClient()
    try:
        client.get_consensus_rankings()
        assert False, "expected FantasyProsParseError"
    except FantasyProsParseError:
        pass
