"""Tests get_snap_counts against synthetic CSV matching the assumed
snap_counts column shape (PFR-scraped, uses "player" not
"player_display_name" for the name column). Doesn't prove this matches the
real file — see client.py's UNVERIFIED note.
"""

import responses

from fantasy_assistant.platforms.nflverse.client import SNAP_COUNTS_CSV_URL, NflverseClient, NflverseParseError

HEADER = "player,position,team,season,week,offense_snaps,offense_pct"


def _csv(*rows: str) -> str:
    return "\n".join([HEADER, *rows])


@responses.activate
def test_get_snap_counts_parses_matching_rows():
    responses.add(
        responses.GET,
        SNAP_COUNTS_CSV_URL,
        body=_csv("Ja'Marr Chase,WR,CIN,2026,1,55,0.92"),
    )

    client = NflverseClient()
    rows = client.get_snap_counts(2026)
    assert len(rows) == 1
    r = rows[0]
    assert r["full_name"] == "Ja'Marr Chase"
    assert r["team"] == "CIN"
    assert r["week"] == 1
    assert r["offense_snaps"] == 55
    assert r["offense_pct"] == 0.92


@responses.activate
def test_get_snap_counts_filters_out_other_seasons():
    responses.add(
        responses.GET,
        SNAP_COUNTS_CSV_URL,
        body=_csv(
            "Ja'Marr Chase,WR,CIN,2025,1,50,0.85",
            "Ja'Marr Chase,WR,CIN,2026,1,55,0.92",
        ),
    )

    client = NflverseClient()
    rows = client.get_snap_counts(2026)
    assert len(rows) == 1
    assert rows[0]["offense_snaps"] == 55


@responses.activate
def test_get_snap_counts_skips_rows_with_no_name():
    responses.add(responses.GET, SNAP_COUNTS_CSV_URL, body=_csv(",WR,CIN,2026,1,55,0.92"))

    client = NflverseClient()
    assert client.get_snap_counts(2026) == []


@responses.activate
def test_get_snap_counts_raises_on_empty_response():
    responses.add(responses.GET, SNAP_COUNTS_CSV_URL, body="")

    client = NflverseClient()
    try:
        client.get_snap_counts(2026)
        assert False, "expected NflverseParseError"
    except NflverseParseError:
        pass
