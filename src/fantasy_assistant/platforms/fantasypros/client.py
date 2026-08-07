"""Scrapes FantasyPros' free consensus rankings pages.

FantasyPros has a paid API (checked as part of scoping this — pricing tiers
exist but weren't purchased, so this uses the free public rankings pages
instead, same as the original spec allowed for).

**UNVERIFIED**: same situation as KTC — this environment can't reach
fantasypros.com, so this is unverified against the live page. Known (as of
general public knowledge, not confirmed live) FantasyPros rankings pages
embed their data as a `var ecrData = {...}` JS object in a <script> tag,
containing a `players` array with fields like player_name, player_position_id,
player_team_id, rank_ecr. Run `fantasy-assistant sync-fantasypros` locally;
a FantasyProsParseError means that assumption is wrong and needs a real look.
"""

from __future__ import annotations

import json
import re

import requests

TIMEOUT_SECONDS = 20
USER_AGENT = "FantasyAssistant/0.1 (personal dynasty tool; contact via GitHub repo)"

RANKINGS_URL = "https://www.fantasypros.com/nfl/rankings/consensus-cheatsheets.php"


class FantasyProsFetchError(RuntimeError):
    pass


class FantasyProsParseError(RuntimeError):
    pass


class FantasyProsClient:
    def __init__(self, session: requests.Session | None = None):
        self._session = session or requests.Session()

    def get_consensus_rankings(self) -> list[dict]:
        try:
            resp = self._session.get(RANKINGS_URL, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise FantasyProsFetchError(f"Request to {RANKINGS_URL} failed: {exc}") from exc
        if not resp.ok:
            raise FantasyProsFetchError(f"FantasyPros returned {resp.status_code}")

        html = resp.text
        match = re.search(r"var\s+ecrData\s*=\s*(\{.*?\});", html, re.DOTALL)
        if not match:
            raise FantasyProsParseError(
                f"Could not find the expected 'ecrData' JS object in the rankings page "
                f"(page length {len(html)} chars). The site's structure likely changed."
            )
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            raise FantasyProsParseError(f"Found ecrData but it wasn't valid JSON: {exc}") from exc

        players = data.get("players")
        if not isinstance(players, list):
            raise FantasyProsParseError("ecrData found but had no 'players' list — shape has changed.")

        results = []
        for p in players:
            name = p.get("player_name")
            if not name:
                continue
            results.append(
                {
                    "full_name": name,
                    "position": (p.get("player_position_id") or "").rstrip("0123456789"),
                    "team": p.get("player_team_id"),
                    "overall_rank": p.get("rank_ecr"),
                }
            )
        return results
