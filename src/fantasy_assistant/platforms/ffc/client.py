"""Fetches real average draft position (ADP) from Fantasy Football
Calculator's free public REST API — actual draft-pick data aggregated from
real drafts, unlike Sleeper's `search_rank` (an interest/search-volume
metric, not a true ADP). See analysis/draft_board.py for why that
distinction matters.

**UNVERIFIED**: this sandbox can't reach fantasyfootballcalculator.com, so
this is unverified against the live API. Per FFC's own published API docs
(help.fantasyfootballcalculator.com/article/42-adp-rest-api), the endpoint
is `GET /api/v1/adp/{type}?teams={n}&year={year}` returning JSON shaped
roughly like:
{
  "players": [
    {"player_id": ..., "name": "...", "position": "RB", "team": "...",
     "adp": 12.3, "adp_formatted": "2.01", "times_drafted": ..., ...},
    ...
  ]
}
already sorted by ADP ascending (best player first). Run
`fantasy-assistant sync-ffc-adp` locally; an FFCParseError means this
assumption is wrong and needs a real look — in particular, FFC's position
labels for this list aren't confirmed to match Sleeper/ESPN's (e.g. "DEF"
vs "DST") and aren't remapped here; a mismatch just means those specific
players won't match by name+position, not that anything breaks.
"""

from __future__ import annotations

import requests

TIMEOUT_SECONDS = 20
USER_AGENT = "FantasyAssistant/0.1 (personal fantasy tool; contact via GitHub repo)"
BASE_URL = "https://fantasyfootballcalculator.com/api/v1/adp"

# FFC's own "type" path segment per qb_mode. Redraft only, by design — see
# analysis/draft_board.py's module docstring for why dynasty startup ADP is
# out of scope here.
FFC_TYPE_BY_QB_MODE = {"1qb": "ppr", "superflex": "2qb"}


class FFCFetchError(RuntimeError):
    pass


class FFCParseError(RuntimeError):
    pass


class FFCClient:
    def __init__(self, session: requests.Session | None = None):
        self._session = session or requests.Session()

    def get_adp(self, qb_mode: str, teams: int = 12, year: int | None = None) -> list[dict]:
        if qb_mode not in FFC_TYPE_BY_QB_MODE:
            raise ValueError(f"Unknown qb_mode: {qb_mode!r}")
        type_ = FFC_TYPE_BY_QB_MODE[qb_mode]
        url = f"{BASE_URL}/{type_}"
        params = {"teams": teams}
        if year is not None:
            params["year"] = year

        try:
            resp = self._session.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise FFCFetchError(f"Request to {url} failed: {exc}") from exc
        if not resp.ok:
            raise FFCFetchError(f"FFC returned {resp.status_code} for {url}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise FFCParseError(f"FFC ADP response wasn't JSON: {exc}") from exc

        players = data.get("players")
        if not isinstance(players, list):
            raise FFCParseError("FFC ADP response had no 'players' list — API shape may have changed.")
        return players
