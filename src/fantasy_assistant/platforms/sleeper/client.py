"""Thin wrapper around the public Sleeper API (https://docs.sleeper.com/).

No auth required. We rate-limit ourselves lightly via urllib3 retries with
backoff on 429/5xx, per Sleeper's guidance to keep request volume reasonable.
"""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

BASE_URL = "https://api.sleeper.app/v1"
TIMEOUT_SECONDS = 10


class SleeperAPIError(RuntimeError):
    """Raised when the Sleeper API returns an error or unexpected shape."""


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


class SleeperClient:
    def __init__(self, session: requests.Session | None = None):
        self._session = session or _build_session()

    def _get(self, path: str) -> dict | list:
        url = f"{BASE_URL}{path}"
        try:
            resp = self._session.get(url, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise SleeperAPIError(f"Request to {url} failed: {exc}") from exc

        if resp.status_code == 404:
            raise SleeperAPIError(f"Not found: {url} (check the league ID)")
        if not resp.ok:
            raise SleeperAPIError(f"Sleeper API returned {resp.status_code} for {url}: {resp.text[:200]}")

        try:
            return resp.json()
        except ValueError as exc:
            raise SleeperAPIError(f"Non-JSON response from {url}") from exc

    def get_league(self, league_id: str) -> dict:
        data = self._get(f"/league/{league_id}")
        if not data:
            raise SleeperAPIError(f"League {league_id} not found or has no data")
        return data

    def get_rosters(self, league_id: str) -> list[dict]:
        return self._get(f"/league/{league_id}/rosters") or []

    def get_users(self, league_id: str) -> list[dict]:
        return self._get(f"/league/{league_id}/users") or []

    def get_all_players(self, sport: str = "nfl") -> dict:
        """Full NFL player pool, keyed by player_id. This is a multi-MB payload —
        Sleeper asks that it be fetched at most once per day, so callers should
        cache it (see sync.sync_players)."""
        return self._get(f"/players/{sport}") or {}

    def get_nfl_state(self) -> dict:
        """Current NFL week/season — used to figure out which weeks have data."""
        return self._get("/state/nfl") or {}

    def get_matchups(self, league_id: str, week: int) -> list[dict]:
        """Per-roster matchup data for one week, including players_points
        (player_id -> fantasy points scored that week under this league's
        scoring settings)."""
        return self._get(f"/league/{league_id}/matchups/{week}") or []
