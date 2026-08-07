"""Tests the KTC parser strategies against synthetic HTML matching each
assumed structure. These do NOT prove the parser matches the real live
site (unverified, see client.py) — they prove the parsing logic is
internally correct for each structure it claims to handle, and that a
truly unrecognized structure raises KTCParseError instead of failing silently.
"""

import responses

from fantasy_assistant.platforms.ktc.client import KTCClient, KTCParseError, _normalize_ktc_record, _page_url

URL = "https://keeptradecut.com/dynasty-rankings"
URL_SUPERFLEX = "https://keeptradecut.com/dynasty-rankings?format=2"


@responses.activate
def test_parses_next_data_json():
    html = """
    <html><body>
    <script id="__NEXT_DATA__" type="application/json">
    {"props": {"pageProps": {"playersArray": [
        {"playerName": "Ja'Marr Chase", "position": "WR", "team": "CIN", "value": 9500, "rank": 1},
        {"playerName": "Bijan Robinson", "position": "RB", "team": "ATL", "value": 8900, "rank": 2}
    ]}}}
    </script>
    </body></html>
    """
    responses.add(responses.GET, URL, body=html)

    client = KTCClient()
    players = client.get_values("dynasty")
    assert len(players) == 2
    assert players[0]["full_name"] == "Ja'Marr Chase"
    assert players[0]["value"] == 9500


@responses.activate
def test_parses_embedded_js_array():
    html = """
    <html><body><script>
    var playersArray = [{"full_name": "Puka Nacua", "position": "WR", "team": "LAR", "value": 7200, "rank": 5}];
    </script></body></html>
    """
    responses.add(responses.GET, URL, body=html)

    client = KTCClient()
    players = client.get_values("dynasty")
    assert len(players) == 1
    assert players[0]["full_name"] == "Puka Nacua"


@responses.activate
def test_parses_html_table_fallback():
    html = """
    <html><body>
    <div class="player-row">
      <span class="player-name">Marvin Harrison Jr.</span>
      <span class="player-position">WR</span>
      <span class="player-value">8100</span>
      <span class="player-rank">3</span>
    </div>
    </body></html>
    """
    responses.add(responses.GET, URL, body=html)

    client = KTCClient()
    players = client.get_values("dynasty")
    assert len(players) == 1
    assert players[0]["full_name"] == "Marvin Harrison Jr."
    assert players[0]["value"] == 8100


@responses.activate
def test_unrecognized_structure_raises_parse_error_not_silent_empty():
    responses.add(responses.GET, URL, body="<html><body><p>Totally different page</p></body></html>")

    client = KTCClient()
    try:
        client.get_values("dynasty")
        assert False, "expected KTCParseError"
    except KTCParseError as exc:
        assert "dynasty" in str(exc)


# ---- qb_mode ----


def test_page_url_1qb_has_no_query_param():
    assert _page_url("dynasty", "1qb") == "https://keeptradecut.com/dynasty-rankings"


def test_page_url_superflex_adds_query_param():
    assert _page_url("dynasty", "superflex") == "https://keeptradecut.com/dynasty-rankings?format=2"


def test_page_url_rejects_unknown_qb_mode():
    try:
        _page_url("dynasty", "3qb")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_normalize_record_prefers_dual_superflex_field_when_present():
    record = {"playerName": "Josh Allen", "position": "QB", "value": 6000, "rank": 10, "superflexValue": 9800, "superflexRank": 1}
    normal = _normalize_ktc_record(record, "1qb")
    sf = _normalize_ktc_record(record, "superflex")
    assert normal["value"] == 6000
    assert sf["value"] == 9800
    assert sf["rank"] == 1


def test_normalize_record_falls_back_to_generic_value_when_no_dual_field():
    # Simulates a page that only has one format's data (fetched via qb_mode-specific URL).
    record = {"playerName": "Josh Allen", "position": "QB", "value": 9800, "rank": 1}
    sf = _normalize_ktc_record(record, "superflex")
    assert sf["value"] == 9800


@responses.activate
def test_get_values_requests_superflex_url():
    html = """
    <script>var playersArray = [{"full_name": "Josh Allen", "position": "QB", "value": 9800, "rank": 1}];</script>
    """
    responses.add(responses.GET, URL_SUPERFLEX, body=html)

    client = KTCClient()
    players = client.get_values("dynasty", qb_mode="superflex")
    assert len(players) == 1
    assert players[0]["value"] == 9800
