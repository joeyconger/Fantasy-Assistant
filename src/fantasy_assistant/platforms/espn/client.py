"""Thin wrapper around the unofficial ESPN Fantasy Football API.

There's no public documentation for this — endpoint and field names are
reverse-engineered (consistent with what the wider ESPN fantasy tooling
community has documented). Public leagues need no auth; private leagues
require the SWID and espn_s2 cookies from a logged-in browser session.
"""

from __future__ import annotations

import requests

BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league_id}"
TIMEOUT_SECONDS = 15
DEFAULT_VIEWS = ("mTeam", "mRoster", "mSettings", "mStandings")


class ESPNAPIError(RuntimeError):
    """Raised for unexpected ESPN API errors (bad league/season, network, etc.)."""


class ESPNAuthRequired(RuntimeError):
    """Raised when ESPN rejects the request — the league is almost certainly private."""


class ESPNClient:
    def __init__(self, swid: str | None = None, espn_s2: str | None = None, session: requests.Session | None = None):
        self._swid = swid
        self._espn_s2 = espn_s2
        self._session = session or requests.Session()

    def get_league(self, league_id: str, season: int, views: tuple[str, ...] = DEFAULT_VIEWS) -> dict:
        url = BASE_URL.format(season=season, league_id=league_id)
        params = [("view", v) for v in views]
        cookies = {}
        if self._swid and self._espn_s2:
            cookies["SWID"] = self._swid
            cookies["espn_s2"] = self._espn_s2

        try:
            resp = self._session.get(url, params=params, cookies=cookies, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise ESPNAPIError(f"Request to {url} failed: {exc}") from exc

        if resp.status_code in (401, 403):
            raise ESPNAuthRequired(
                f"ESPN rejected the request for league {league_id} (status {resp.status_code}) — "
                "this league is almost certainly private. Add SWID and espn_s2 cookies to "
                "config/secrets.yaml (see README for how to grab them from your browser)."
            )
        if resp.status_code == 404:
            raise ESPNAPIError(f"League {league_id} not found for season {season} — check the league ID and season.")
        if not resp.ok:
            raise ESPNAPIError(f"ESPN API returned {resp.status_code} for {url}: {resp.text[:200]}")

        try:
            return resp.json()
        except ValueError as exc:
            raise ESPNAPIError(f"Non-JSON response from {url}") from exc
