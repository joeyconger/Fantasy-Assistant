"""Tests the FFC client against synthetic JSON matching the assumed
response shape. Does NOT prove this matches the real live API (unverified,
see client.py) — proves the parsing logic is internally correct, and that
an unrecognized shape raises FFCParseError instead of failing silently.
"""

import responses

from fantasy_assistant.platforms.ffc.client import FFCClient, FFCParseError

PPR_URL = "https://fantasyfootballcalculator.com/api/v1/adp/ppr"
TWO_QB_URL = "https://fantasyfootballcalculator.com/api/v1/adp/2qb"


@responses.activate
def test_get_adp_1qb_hits_ppr_endpoint_and_parses_players():
    responses.add(
        responses.GET,
        PPR_URL,
        json={"players": [{"name": "Ja'Marr Chase", "position": "WR", "team": "CIN", "adp": 1.2}]},
    )

    client = FFCClient()
    players = client.get_adp("1qb")
    assert len(players) == 1
    assert players[0]["name"] == "Ja'Marr Chase"
    assert responses.calls[0].request.url.startswith(PPR_URL)


@responses.activate
def test_get_adp_superflex_hits_2qb_endpoint():
    responses.add(
        responses.GET,
        TWO_QB_URL,
        json={"players": [{"name": "Josh Allen", "position": "QB", "team": "BUF", "adp": 3.5}]},
    )

    client = FFCClient()
    players = client.get_adp("superflex")
    assert players[0]["name"] == "Josh Allen"
    assert responses.calls[0].request.url.startswith(TWO_QB_URL)


def test_get_adp_rejects_unknown_qb_mode():
    client = FFCClient()
    try:
        client.get_adp("2qb")
        assert False, "expected ValueError"
    except ValueError:
        pass


@responses.activate
def test_get_adp_passes_teams_param():
    responses.add(responses.GET, PPR_URL, json={"players": []})

    client = FFCClient()
    client.get_adp("1qb", teams=10)
    assert "teams=10" in responses.calls[0].request.url


@responses.activate
def test_missing_players_list_raises_parse_error_not_silent_empty():
    responses.add(responses.GET, PPR_URL, json={"meta": {}})

    client = FFCClient()
    try:
        client.get_adp("1qb")
        assert False, "expected FFCParseError"
    except FFCParseError:
        pass


@responses.activate
def test_non_json_response_raises_parse_error():
    responses.add(responses.GET, PPR_URL, body="<html>not json</html>")

    client = FFCClient()
    try:
        client.get_adp("1qb")
        assert False, "expected FFCParseError"
    except FFCParseError:
        pass
