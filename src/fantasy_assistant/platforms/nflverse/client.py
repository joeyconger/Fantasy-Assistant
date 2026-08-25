"""Fetches advanced weekly player-usage stats from nflverse's free, public
CSV releases — no API key, no auth, no scraping-ToS gray area (unlike
Reddit), since nflverse publishes these datasets specifically for reuse.

**UNVERIFIED**: this sandbox can't reach github.com, so neither the exact
release-asset URLs nor either CSV's column names are confirmed against a
live file. Per nflreadr's (the R package this data most commonly gets
consumed through) documented source, nflverse-data publishes combined
all-seasons weekly CSVs under the `player_stats` and `snap_counts` release
tags at the URLs below; if either path 404s or comes back some other
shape, dump the raw response and this needs a real look — same situation
KTC/FFC/FantasyPros were in before their first live run.

Two separate datasets, two separate methods:
- get_weekly_stats(): target_share, air_yards_share, wopr, racr — from
  `player_stats`.
- get_snap_counts(): offense_snaps, offense_pct — from `snap_counts`
  (scraped from Pro-Football-Reference by nflverse; defense/special-teams
  snaps aren't fetched, not fantasy-relevant here).

True red-zone-touch counts live only in nflverse's full play-by-play
dataset, which is a much larger file requiring custom aggregation (filter
by field position, count rush attempts + targets inside the 20) rather
than a simple column read — deliberately not attempted here rather than
guess at a column that likely doesn't exist in either file above.
"""

from __future__ import annotations

import csv
import io

import requests

TIMEOUT_SECONDS = 30
USER_AGENT = "FantasyAssistant/0.1 (personal fantasy tool; contact via GitHub repo)"
CSV_URL = "https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats.csv"
SNAP_COUNTS_CSV_URL = "https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts.csv"

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

# snap_counts is PFR-scraped, so its name/team columns are named
# differently than player_stats' (nflreadr's own docs list "player" as the
# display-name column there).
SNAP_NAME_KEYS = ("player", "player_display_name", "player_name")
SNAP_TEAM_KEYS = ("team", "recent_team")
OFFENSE_SNAPS_KEYS = ("offense_snaps",)
OFFENSE_PCT_KEYS = ("offense_pct",)


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

    def _fetch_csv_rows(self, url: str) -> list[dict]:
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
        return rows

    def get_weekly_stats(self, season: int, url: str = CSV_URL) -> list[dict]:
        """Fetches the full combined weekly-stats CSV and returns rows for
        `season` only, normalized to {full_name, position, team, season,
        week, targets, target_share, air_yards_share, wopr, racr}. This is
        an all-seasons file, so filtering by season happens here rather
        than via a per-season URL (which may not exist)."""
        rows = self._fetch_csv_rows(url)

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

    def get_snap_counts(self, season: int, url: str = SNAP_COUNTS_CSV_URL) -> list[dict]:
        """Fetches the full combined snap-counts CSV and returns rows for
        `season` only, normalized to {full_name, position, team, season,
        week, offense_snaps, offense_pct}."""
        rows = self._fetch_csv_rows(url)

        results = []
        for row in rows:
            row_season = _to_int(_first_present(row, SEASON_KEYS))
            if row_season != season:
                continue
            name = _first_present(row, SNAP_NAME_KEYS)
            if not name:
                continue
            results.append(
                {
                    "full_name": name,
                    "position": _first_present(row, POSITION_KEYS) or "",
                    "team": _first_present(row, SNAP_TEAM_KEYS),
                    "season": row_season,
                    "week": _to_int(_first_present(row, WEEK_KEYS)),
                    "offense_snaps": _to_int(_first_present(row, OFFENSE_SNAPS_KEYS)),
                    "offense_pct": _to_float(_first_present(row, OFFENSE_PCT_KEYS)),
                }
            )
        return results
