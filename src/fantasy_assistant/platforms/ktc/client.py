"""Scrapes KeepTradeCut dynasty/devy trade values — they have no public API.

**UNVERIFIED**: this environment's egress policy blocks keeptradecut.com, so
none of the parsing logic here has been tested against the real page. The
strategies below are a best-effort guess based on common patterns for this
kind of site (a JSON blob embedded in the page for client-side rendering,
falling back to plain HTML table scraping). Run `fantasy-assistant sync-ktc`
locally — if it raises KTCParseError, the real page structure differs from
what's assumed here. Paste the error (it includes a snippet of what was
found) or the page's view-source back and the parser can be fixed quickly.

Respectful-scraping choices: a real User-Agent identifying this tool, one
request per format per sync call, and callers are expected to cache results
(see sync.py's 12h TTL) rather than re-fetching on every run.
"""

from __future__ import annotations

import json
import re

import requests

TIMEOUT_SECONDS = 20
USER_AGENT = "FantasyAssistant/0.1 (personal dynasty tool; contact via GitHub repo)"

PAGE_URLS = {
    "dynasty": "https://keeptradecut.com/dynasty-rankings",
    "devy": "https://keeptradecut.com/devy-rankings",
}


class KTCFetchError(RuntimeError):
    """Network/HTTP-level failure fetching a KTC page."""


class KTCParseError(RuntimeError):
    """The page loaded but didn't match any known parsing strategy — the
    site's structure has likely changed from what's assumed here."""


class KTCClient:
    def __init__(self, session: requests.Session | None = None):
        self._session = session or requests.Session()

    def _fetch_html(self, format_: str) -> str:
        if format_ not in PAGE_URLS:
            raise ValueError(f"Unknown KTC format '{format_}', expected one of {list(PAGE_URLS)}")
        url = PAGE_URLS[format_]
        try:
            resp = self._session.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise KTCFetchError(f"Request to {url} failed: {exc}") from exc
        if not resp.ok:
            raise KTCFetchError(f"KTC returned {resp.status_code} for {url}")
        return resp.text

    def get_values(self, format_: str) -> list[dict]:
        """Returns [{full_name, position, team, value, rank}, ...] for the
        given format ('dynasty' or 'devy')."""
        html = self._fetch_html(format_)
        players = _parse_next_data(html) or _parse_embedded_array(html) or _parse_html_table(html)
        if players is None:
            raise KTCParseError(
                f"Could not find player data in the {format_} rankings page using any known "
                "strategy (Next.js data blob, embedded JS array, HTML table). Page length was "
                f"{len(html)} chars. The site's structure likely changed — needs a live look."
            )
        return players


def _parse_next_data(html: str) -> list[dict] | None:
    """Strategy 1: Next.js apps embed page data as JSON in
    <script id="__NEXT_DATA__" type="application/json">...</script>."""
    match = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL
    )
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None

    players = _find_player_list(data)
    if not players:
        return None
    return [_normalize_ktc_record(p) for p in players if _normalize_ktc_record(p)]


def _parse_embedded_array(html: str) -> list[dict] | None:
    """Strategy 2: a plain `var playersArray = [...]` (or similar) assignment
    embedded directly in a <script> tag."""
    match = re.search(r"(?:playersArray|var\s+players)\s*=\s*(\[.*?\])\s*;", html, re.DOTALL)
    if not match:
        return None
    try:
        raw = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return [_normalize_ktc_record(p) for p in raw if _normalize_ktc_record(p)]


def _parse_html_table(html: str) -> list[dict] | None:
    """Strategy 3: plain server-rendered HTML table/list. Requires bs4."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None

    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("[class*='player-name']")
    if not rows:
        return None

    players = []
    for name_el in rows:
        container = name_el.find_parent(["tr", "div", "li"]) or name_el
        value_el = container.select_one("[class*='value']")
        rank_el = container.select_one("[class*='rank']")
        pos_el = container.select_one("[class*='position']")
        players.append(
            {
                "full_name": name_el.get_text(strip=True),
                "value": _to_int(value_el.get_text(strip=True)) if value_el else None,
                "rank": _to_int(rank_el.get_text(strip=True)) if rank_el else None,
                "position": pos_el.get_text(strip=True) if pos_el else None,
            }
        )
    return players or None


def _find_player_list(data, depth: int = 0) -> list[dict] | None:
    """Recursively hunts a parsed JSON blob for a list of dict entries that
    look like player records (has a name-ish and value-ish key)."""
    if depth > 8:
        return None
    if isinstance(data, list) and data and isinstance(data[0], dict):
        keys = {k.lower() for k in data[0].keys()}
        if keys & {"playername", "full_name", "name"} and keys & {"value", "rank", "tier"}:
            return data
    if isinstance(data, dict):
        for value in data.values():
            found = _find_player_list(value, depth + 1)
            if found:
                return found
    if isinstance(data, list):
        for item in data:
            found = _find_player_list(item, depth + 1)
            if found:
                return found
    return None


def _normalize_ktc_record(p: dict) -> dict | None:
    name = p.get("playerName") or p.get("full_name") or p.get("name")
    if not name:
        return None
    return {
        "full_name": name,
        "position": p.get("position") or p.get("position1"),
        "team": p.get("team") or p.get("teamName"),
        "value": _to_int(p.get("value") or p.get("Value") or p.get("value1")),
        "rank": _to_int(p.get("rank") or p.get("Rank") or p.get("overallRank")),
    }


def _to_int(x) -> int | None:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return int(x)
    digits = re.sub(r"[^\d-]", "", str(x))
    return int(digits) if digits else None
