"""Scrapes KeepTradeCut dynasty trade values — they have no public API.

**VERIFIED against the live dynasty-rankings page** (2026-08). The page
embeds a `var playersArray = [...]` JS array (matched by the
`_parse_embedded_array` strategy below) where each record carries BOTH 1QB
and Superflex values at once, nested under `oneQBValues` / `superflexValues`
(each with its own `value`/`rank`/`positionalRank`/`adp`) — there is no
separate URL or query param per format; that was an earlier wrong guess,
now removed. One request covers both qb_modes.

**devy-rankings page is NOT yet verified** — same parsing code is used
(the two pages share KTC's site framework) but the devy page hasn't been
checked directly. Run `fantasy-assistant sync-ktc --format devy` to confirm;
if it raises KTCParseError, the real page structure differs from what's
assumed here — paste the error back (it includes a length/snippet) and it
can be fixed the same way the dynasty page was.

Respectful-scraping choices: a real User-Agent identifying this tool, and
callers are expected to cache results (see sync.py's 12h TTL) rather than
re-fetching on every run.
"""

from __future__ import annotations

import json
import re

import requests

TIMEOUT_SECONDS = 20
USER_AGENT = "FantasyAssistant/0.1 (personal dynasty tool; contact via GitHub repo)"

BASE_URLS = {
    "dynasty": "https://keeptradecut.com/dynasty-rankings",
    "devy": "https://keeptradecut.com/devy-rankings",
}


class KTCFetchError(RuntimeError):
    """Network/HTTP-level failure fetching a KTC page."""


class KTCParseError(RuntimeError):
    """The page loaded but didn't match any known parsing strategy — the
    site's structure has likely changed from what's assumed here."""


def _page_url(format_: str) -> str:
    if format_ not in BASE_URLS:
        raise ValueError(f"Unknown KTC format '{format_}', expected one of {list(BASE_URLS)}")
    return BASE_URLS[format_]


class KTCClient:
    def __init__(self, session: requests.Session | None = None):
        self._session = session or requests.Session()

    def _fetch_html(self, format_: str) -> str:
        url = _page_url(format_)
        try:
            resp = self._session.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise KTCFetchError(f"Request to {url} failed: {exc}") from exc
        if not resp.ok:
            raise KTCFetchError(f"KTC returned {resp.status_code} for {url}")
        return resp.text

    def get_values(self, format_: str, qb_mode: str = "1qb") -> list[dict]:
        """Returns [{full_name, position, team, value, rank}, ...] for the
        given format ('dynasty' or 'devy') and qb_mode ('1qb' or 'superflex').

        One page load carries both qb_modes (see module docstring), so this
        doesn't make a second request for a different qb_mode of the same
        format — the same fetch is just re-normalized for whichever one is
        asked for. Callers doing both 1qb and superflex syncs back-to-back
        will still issue two HTTP requests today since caching is keyed by
        (format, qb_mode) in sync.py, not by format alone — a reasonable
        future optimization, not fixed now.
        """
        if qb_mode not in ("1qb", "superflex"):
            raise ValueError(f"Unknown qb_mode '{qb_mode}', expected '1qb' or 'superflex'")
        html = self._fetch_html(format_)
        raw = _parse_next_data(html) or _parse_embedded_array(html) or _parse_html_table(html)
        if raw is None:
            raise KTCParseError(
                f"Could not find player data in the {format_} rankings page using any "
                "known strategy (Next.js data blob, embedded JS array, HTML table). Page length "
                f"was {len(html)} chars. The site's structure likely changed — needs a live look."
            )
        return [_normalize_ktc_record(p, qb_mode) for p in raw if _normalize_ktc_record(p, qb_mode)]


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
    return _find_player_list(data)


def _parse_embedded_array(html: str) -> list[dict] | None:
    """Strategy 2: a plain `var playersArray = [...]` (or similar) assignment
    embedded directly in a <script> tag."""
    match = re.search(r"(?:playersArray|var\s+players)\s*=\s*(\[.*?\])\s*;", html, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


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
                "playerName": name_el.get_text(strip=True),
                "value": value_el.get_text(strip=True) if value_el else None,
                "rank": rank_el.get_text(strip=True) if rank_el else None,
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
        if keys & {"playername", "full_name", "name"} and keys & {
            "value", "rank", "tier", "oneqbvalues", "superflexvalues"
        }:
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


def _normalize_ktc_record(p: dict, qb_mode: str) -> dict | None:
    name = p.get("playerName") or p.get("full_name") or p.get("name")
    if not name:
        return None

    # Confirmed live structure: each record nests both formats under
    # oneQBValues / superflexValues, each its own {value, rank, ...} dict.
    values_key = "superflexValues" if qb_mode == "superflex" else "oneQBValues"
    values = p.get(values_key) or {}
    value = values.get("value")
    rank = values.get("rank")

    if value is None and rank is None:
        # Fallback for a shape that doesn't nest this way (e.g. if the
        # devy page or a future site change differs from dynasty's).
        if qb_mode == "superflex":
            value = p.get("superflexValue") or p.get("sfValue") or p.get("value")
            rank = p.get("superflexRank") or p.get("sfRank") or p.get("rank")
        else:
            value = p.get("value") or p.get("oneQBValue")
            rank = p.get("rank") or p.get("oneQBRank")

    return {
        "full_name": name,
        "position": p.get("position") or p.get("position1"),
        "team": p.get("team") or p.get("teamName"),
        "value": _to_int(value),
        "rank": _to_int(rank),
    }


def _to_int(x) -> int | None:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return int(x)
    digits = re.sub(r"[^\d-]", "", str(x))
    return int(digits) if digits else None
