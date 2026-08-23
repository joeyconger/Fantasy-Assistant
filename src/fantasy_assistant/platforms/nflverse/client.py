"""Fetches advanced weekly player-usage stats (target share, air yards
share, WOPR, RACR) from nflverse's free, public weekly player-stats CSV
releases — no API key, no auth, no scraping-ToS gray area (unlike Reddit),
since nflverse publishes this as an open dataset specifically for reuse.

**UNVERIFIED**: this sandbox can't reach github.com, so neither the exact
release-asset URL nor the CSV's column names are confirmed against a live
file. Per nflreadr's (the R package this data most commonly gets consumed
through) documented source, nflverse-data publishes a combined
all-seasons weekly CSV under the `player_stats` release tag at the URL
below; if that path 404s or comes back some other shape, dump the raw
response and this needs a real look — same situation KTC/FFC/FantasyPros
were in before their first live run.

Deliberately scoped to columns this integration is reasonably confident
nflverse's `player_stats` weekly file actually has: targets, target_share,
air_yards_share, wopr, racr. Snap counts and true red-zone-touch counts
live in *separate* nflverse datasets (`snap_counts`, derived from
play-by-play) not covered here — rather than guess at those and risk
silently wrong numbers, they're left out of this first pass entirely.
"""

from __future__ import annotations

import csv
import io

import requests

TIMEOUT_SECONDS = 30
USER_AGENT = "FantasyAssistant/0.1 (personal fantasy tool; contact via GitHub repo)"
CSV_URL = "https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats.csv"

# Candidate column names per field, tried in order — nflverse's schema has
# shifted column names across versions (e.g. player_name vs
# player_display_name), so this tries the more common recent name first.
NAME_KEYS = ("player_display_name", "player_name")
POSITION_KEYS = ("position",)
TEAM_KEYS = ("recent_team", "team")
SEASON_KEYS = ("season",)
WEEK_KEYS = ("week",)
TARGETS_KEYS = ("targets",)
TARGET_SHARE_KEYS = ("target_share",)
AIR_YARDS_SHARE_KEYS = ("air_yards_share",)
WOPR_KEYS = ("wopr", "wopr_x")
RACR_KEYS = ("racr",)


class NflverseFetchError(RuntimeError):
    pass


class NflverseParseError(RuntimeError):
    pass


def _first_present(row: dict, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _to_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _to_int(value: str | None) -> int | None:
    as_float = _to_float(value)
    return int(as_float) if as_float is not None else None


class NflverseClient:
    def __init__(self, session: requests.Session | None = None):
        self._session = session or requests.Session()

    def get_weekly_stats(self, season: int, url: str = CSV_URL) -> list[dict]:
        """Fetches the full combined weekly-stats CSV and returns rows for
        `season` only, normalized to {full_name, position, team, season,
        week, targets, target_share, air_yards_share, wopr, racr}. This is
        an all-seasons file, so filtering by season happens here rather
        than via a per-season URL (which may not exist)."""
        try:
            resp = self._session.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise NflverseFetchError(f"Request to {url} failed: {exc}") from exc
        if not resp.ok:
            raise NflverseFetchError(f"nflverse returned {resp.status_code} for {url}")

        try:
            reader = csv.DictReader(io.StringIO(resp.text))
            rows = list(reader)
        except csv.Error as exc:
            raise NflverseParseError(f"Couldn't parse nflverse response as CSV: {exc}") from exc
        if not rows or not reader.fieldnames:
            raise NflverseParseError("nflverse CSV had no rows/header — file shape may have changed.")

        results = []
        for row in rows:
            row_season = _to_int(_first_present(row, SEASON_KEYS))
            if row_season != season:
                continue
            name = _first_present(row, NAME_KEYS)
            if not name:
                continue
            results.append(
                {
                    "full_name": name,
                    "position": _first_present(row, POSITION_KEYS) or "",
                    "team": _first_present(row, TEAM_KEYS),
                    "season": row_season,
                    "week": _to_int(_first_present(row, WEEK_KEYS)),
                    "targets": _to_int(_first_present(row, TARGETS_KEYS)),
                    "target_share": _to_float(_first_present(row, TARGET_SHARE_KEYS)),
                    "air_yards_share": _to_float(_first_present(row, AIR_YARDS_SHARE_KEYS)),
                    "wopr": _to_float(_first_present(row, WOPR_KEYS)),
                    "racr": _to_float(_first_present(row, RACR_KEYS)),
                }
            )
        return results
