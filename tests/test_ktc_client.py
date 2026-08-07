"""Tests the KTC parser strategies against synthetic HTML matching each
assumed structure. These do NOT prove the parser matches the real live
site (unverified, see client.py) — they prove the parsing logic is
internally correct for each structure it claims to handle, and that a
truly unrecognized structure raises KTCParseError instead of failing silently.
"""

import responses

from fantasy_assistant.platforms.ktc.client import KTCClient, KTCParseError, _normalize_ktc_record, _page_url

URL = "https://keeptradecut.com/dynasty-rankings"


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
#
# Confirmed live (2026-08): KTC embeds BOTH qb_modes in one page load, nested
# under oneQBValues/superflexValues on every record — there's no separate
# URL per format. These tests lock in that real shape, plus a fallback path
# for flat value/rank fields in case a differently-shaped page is ever hit
# (e.g. the still-unverified devy-rankings page).


def test_page_url_takes_no_qb_mode_argument():
    # Real finding: a qb_mode-specific URL doesn't exist — one page has both.
    assert _page_url("dynasty") == "https://keeptradecut.com/dynasty-rankings"


def test_page_url_rejects_unknown_format():
    try:
        _page_url("redraft")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_normalize_record_reads_nested_qb_mode_values():
    record = {
        "playerName": "Bijan Robinson",
        "position": "RB",
        "team": "ATL",
        "oneQBValues": {"value": 9998, "rank": 3, "positionalRank": 2},
        "superflexValues": {"value": 9999, "rank": 1, "positionalRank": 1},
    }
    one_qb = _normalize_ktc_record(record, "1qb")
    sf = _normalize_ktc_record(record, "superflex")
    assert one_qb["value"] == 9998
    assert one_qb["rank"] == 3
    assert sf["value"] == 9999
    assert sf["rank"] == 1


def test_normalize_record_falls_back_to_flat_fields_when_not_nested():
    # In case a page shape doesn't nest like dynasty's does (e.g. devy, unverified).
    record = {"playerName": "Some Prospect", "position": "QB", "value": 4200, "rank": 7}
    one_qb = _normalize_ktc_record(record, "1qb")
    assert one_qb["value"] == 4200
    assert one_qb["rank"] == 7


@responses.activate
def test_get_values_extracts_correct_qb_mode_from_one_fetch():
    html = """
    <script>var playersArray = [{
        "playerName": "Josh Allen", "position": "QB", "team": "BUF",
        "oneQBValues": {"value": 6500, "rank": 10},
        "superflexValues": {"value": 9800, "rank": 1}
    }];</script>
    """
    responses.add(responses.GET, URL, body=html)

    client = KTCClient()
    one_qb = client.get_values("dynasty", qb_mode="1qb")
    assert one_qb[0]["value"] == 6500

    sf = client.get_values("dynasty", qb_mode="superflex")
    assert sf[0]["value"] == 9800

    # Both calls hit the same URL — no ?format=2 or similar query param.
    assert all(call.request.url == URL for call in responses.calls)
