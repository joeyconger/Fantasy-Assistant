"""Tests the nflverse client against synthetic CSV matching the assumed
column shape. Does NOT prove this matches the real live file (unverified,
see client.py) — proves the parsing logic is internally correct, and that
an unrecognized shape raises NflverseParseError instead of failing silently.
"""

import responses

from fantasy_assistant.platforms.nflverse.client import CSV_URL, NflverseClient, NflverseParseError

HEADER = "player_display_name,position,recent_team,season,week,targets,target_share,air_yards_share,wopr,racr"


def _csv(*rows: str) -> str:
    return "\n".join([HEADER, *rows])


@responses.activate
def test_get_weekly_stats_parses_matching_rows():
    responses.add(
        responses.GET,
        CSV_URL,
        body=_csv("Ja'Marr Chase,WR,CIN,2026,1,10,0.28,0.35,0.55,1.1"),
    )

    client = NflverseClient()
    rows = client.get_weekly_stats(2026)
    assert len(rows) == 1
    r = rows[0]
    assert r["full_name"] == "Ja'Marr Chase"
    assert r["position"] == "WR"
    assert r["team"] == "CIN"
    assert r["season"] == 2026
    assert r["week"] == 1
    assert r["targets"] == 10
    assert r["target_share"] == 0.28
    assert r["air_yards_share"] == 0.35
    assert r["wopr"] == 0.55
    assert r["racr"] == 1.1


@responses.activate
def test_get_weekly_stats_filters_out_other_seasons():
    responses.add(
        responses.GET,
        CSV_URL,
        body=_csv(
            "Ja'Marr Chase,WR,CIN,2025,1,10,0.28,0.35,0.55,1.1",
            "Ja'Marr Chase,WR,CIN,2026,1,11,0.30,0.36,0.56,1.2",
        ),
    )

    client = NflverseClient()
    rows = client.get_weekly_stats(2026)
    assert len(rows) == 1
    assert rows[0]["season"] == 2026
    assert rows[0]["targets"] == 11


@responses.activate
def test_get_weekly_stats_skips_rows_with_no_name():
    responses.add(
        responses.GET,
        CSV_URL,
        body=_csv(",WR,CIN,2026,1,10,0.28,0.35,0.55,1.1"),
    )

    client = NflverseClient()
    rows = client.get_weekly_stats(2026)
    assert rows == []


@responses.activate
def test_get_weekly_stats_raises_on_empty_response():
    responses.add(responses.GET, CSV_URL, body="")

    client = NflverseClient()
    try:
        client.get_weekly_stats(2026)
        assert False, "expected NflverseParseError"
    except NflverseParseError:
        pass


@responses.activate
def test_get_weekly_stats_handles_missing_optional_fields_gracefully():
    responses.add(
        responses.GET,
        CSV_URL,
        body=_csv("Some Guy,RB,KC,2026,3,,,,,"),
    )

    client = NflverseClient()
    rows = client.get_weekly_stats(2026)
    assert len(rows) == 1
    assert rows[0]["targets"] is None
    assert rows[0]["target_share"] is None
