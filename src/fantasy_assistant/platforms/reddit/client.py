"""Fetches recent Reddit posts via Apify's Reddit Scraper actor, instead of
a direct Reddit API client. Reddit closed self-service API app registration
in November 2025 and blocked the unauthenticated `.json` fallback in May
2026, so a Reddit "script" app (client_id/client_secret) is no longer
obtainable for a new project — see the conversation that decided this.
Apify runs the actual scraping on their infrastructure (this is a real ToS
gray area — using it is a deliberate choice, not a compliant workaround)
and returns structured JSON over a plain REST API, which this module calls.

Requires APIFY_API_TOKEN — a free Apify account (no card needed; the free
plan grants $5/month of usage, which comfortably covers this app's volume)
gets you one from https://console.apify.com/settings/integrations.

**UNVERIFIED**: this sandbox can't reach apify.com. Uses the
`trudax/reddit-scraper-lite` actor (one of the more established, actively
maintained Reddit scrapers on Apify) via its `run-sync-get-dataset-items`
endpoint, which runs the actor and returns its output dataset in one HTTP
call (capped at 300s server-side per Apify's own docs). Neither the input
parameter names nor the output field names are confirmed against a live
run — Apify Reddit actors aren't standardized across authors, so field
extraction here tries several plausible candidate keys per attribute
(same defensive pattern as espn/rankings.py's rank-type guessing) rather
than betting on one exact schema. Run `fantasy-assistant sync-reddit`
locally; if it errors or mention counts come back at zero despite real
matching posts existing, dump one raw dataset item's keys and this needs a
real look.
"""

from __future__ import annotations

import os

import requests

TIMEOUT_SECONDS = 60
DEFAULT_ACTOR = "trudax~reddit-scraper-lite"
DEFAULT_SUBREDDITS = ["fantasyfootball", "DynastyFF"]

# Candidate field names per attribute, tried in order — not confirmed live.
TITLE_KEYS = ("title",)
BODY_KEYS = ("body", "selftext", "text", "description")
SUBREDDIT_KEYS = ("communityName", "subredditName", "subreddit", "community")
SCORE_KEYS = ("score", "upVotes", "numberOfUpvotes", "upvotes")
CREATED_KEYS = ("createdAt", "created_utc", "date", "createdAtFormatted")


class ApifyNotConfigured(RuntimeError):
    pass


class ApifyFetchError(RuntimeError):
    pass


def _first_present(item: dict, keys: tuple[str, ...]):
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _api_token() -> str:
    token = os.environ.get("APIFY_API_TOKEN")
    if not token:
        raise ApifyNotConfigured(
            "APIFY_API_TOKEN isn't set. Create a free account at https://apify.com (no card "
            "needed, $5/month free usage) and set this env var from "
            "https://console.apify.com/settings/integrations before Reddit sentiment can run."
        )
    return token


def fetch_recent_posts(
    subreddits: list[str] | None = None,
    limit: int = 100,
    actor: str = DEFAULT_ACTOR,
    session: requests.Session | None = None,
) -> list[dict]:
    """Runs the Apify Reddit Scraper actor synchronously and returns posts
    normalized to {subreddit, title, selftext, score, created_utc} — the
    shape analysis/sentiment.py's score_player_mentions() expects.
    """
    token = _api_token()
    subreddits = subreddits or DEFAULT_SUBREDDITS
    session = session or requests.Session()

    url = f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
    payload = {"subreddits": subreddits, "sort": "new", "maxItems": limit}

    try:
        resp = session.post(url, params={"token": token}, json=payload, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise ApifyFetchError(f"Request to Apify failed: {exc}") from exc
    if not resp.ok:
        raise ApifyFetchError(f"Apify returned {resp.status_code}: {resp.text[:300]}")

    try:
        items = resp.json()
    except ValueError as exc:
        raise ApifyFetchError(f"Apify response wasn't JSON: {exc}") from exc
    if not isinstance(items, list):
        raise ApifyFetchError("Apify response wasn't a list of dataset items — actor output shape may have changed.")

    posts = []
    for item in items:
        title = _first_present(item, TITLE_KEYS)
        if not title:
            continue
        posts.append(
            {
                "subreddit": _first_present(item, SUBREDDIT_KEYS) or "",
                "title": title,
                "selftext": _first_present(item, BODY_KEYS) or "",
                "score": _first_present(item, SCORE_KEYS) or 0,
                "created_utc": _first_present(item, CREATED_KEYS),
            }
        )
    return posts
