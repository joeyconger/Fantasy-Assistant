"""Thin wrapper around the unofficial ESPN Fantasy Football API.

There's no public documentation for this — endpoint and field names are
reverse-engineered (consistent with what the wider ESPN fantasy tooling
community has documented). Public leagues need no auth; private leagues
require the SWID and espn_s2 cookies from a logged-in browser session.
"""

from __future__ import annotations

import json

import requests

LEAGUE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league_id}"
PLAYERS_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/players"
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

    def _cookies(self) -> dict:
        if self._swid and self._espn_s2:
            return {"SWID": self._swid, "espn_s2": self._espn_s2}
        return {}

    def _request(self, url: str, params: list[tuple[str, str]], headers: dict | None = None):
        try:
            resp = self._session.get(url, params=params, cookies=self._cookies(), headers=headers, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise ESPNAPIError(f"Request to {url} failed: {exc}") from exc

        if resp.status_code in (401, 403):
            raise ESPNAuthRequired(
                f"ESPN rejected the request (status {resp.status_code}) — this league is almost "
                "certainly private. Add SWID and espn_s2 cookies (config/secrets.yaml locally, or "
                "ESPN_SWID/ESPN_S2 env vars when deployed)."
            )
        if resp.status_code == 404:
            raise ESPNAPIError(f"Not found: {url} — check the league ID and season.")
        if not resp.ok:
            raise ESPNAPIError(f"ESPN API returned {resp.status_code} for {url}: {resp.text[:200]}")

        try:
            return resp.json()
        except ValueError as exc:
            raise ESPNAPIError(f"Non-JSON response from {url}") from exc

    def get_league(self, league_id: str, season: int, views: tuple[str, ...] = DEFAULT_VIEWS) -> dict:
        url = LEAGUE_URL.format(season=season, league_id=league_id)
        params = [("view", v) for v in views]
        return self._request(url, params)

    def get_player_pool(self, season: int, limit: int = 2000) -> list[dict]:
        """Full NFL player pool with ESPN's standard draft rank and ADP —
        distinct from get_league's roster data, which only covers players
        actually rostered in one league.

        UNVERIFIED: this endpoint/header shape (kona_player_info view +
        x-fantasy-filter) is reverse-engineered from community ESPN API
        tooling, not tested against the live API from this environment
        (blocked here). The general `player` object fields (fullName,
        defaultPositionId, proTeamId) match what get_league already proved
        live; draftRanksByRankType/ownership are the less-certain part.
        """
        url = PLAYERS_URL.format(season=season)
        params = [("view", "kona_player_info"), ("scoringPeriodId", "0")]
        headers = {
            "x-fantasy-filter": json.dumps(
                {
                    "players": {
                        "limit": limit,
                        "sortDraftRanks": {"sortPriority": 1, "sortAsc": True, "value": "STANDARD"},
                    }
                }
            )
        }
        data = self._request(url, params, headers=headers)
        if isinstance(data, dict):
            data = data.get("players") or []
        return data or []
