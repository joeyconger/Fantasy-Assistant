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

Defaults to r/DynastyFF only, filtered to the "Player Discussion" and
"News" flairs — by request, since this app's Reddit sentiment use case is
specifically dynasty-league buy-low/sell-high, not general redraft chatter.
Flair filtering happens client-side after fetching (not passed as an actor
input param), since actor-level flair filter support isn't confirmed
either — safer to filter on data we can actually see. The flair match is a
case-insensitive substring check rather than exact equality, since real
Reddit flairs are often decorated with emoji/extra text (e.g. "🏈 News")
that would break an exact match. A post whose flair can't be determined at
all is excluded when a flair filter is active — silently including
unknown-flair posts would defeat the point of asking for only certain
flairs.
"""

from __future__ import annotations

import os

import requests

TIMEOUT_SECONDS = 60
DEFAULT_ACTOR = "trudax~reddit-scraper-lite"
DEFAULT_SUBREDDITS = ["DynastyFF"]
DEFAULT_FLAIRS = ["Player Discussion", "News"]

# Candidate field names per attribute, tried in order — not confirmed live.
TITLE_KEYS = ("title",)
BODY_KEYS = ("body", "selftext", "text", "description")
SUBREDDIT_KEYS = ("communityName", "subredditName", "subreddit", "community")
SCORE_KEYS = ("score", "upVotes", "numberOfUpvotes", "upvotes")
CREATED_KEYS = ("createdAt", "created_utc", "date", "createdAtFormatted")
FLAIR_KEYS = ("flair", "linkFlairText", "flairText", "link_flair_text")


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


def _flair_matches(flair: str | None, wanted: list[str]) -> bool:
    if not flair:
        return False
    flair_lower = flair.lower()
    return any(w.lower() in flair_lower for w in wanted)


def fetch_recent_posts(
    subreddits: list[str] | None = None,
    limit: int = 100,
    flairs: list[str] | None = DEFAULT_FLAIRS,
    actor: str = DEFAULT_ACTOR,
    session: requests.Session | None = None,
) -> list[dict]:
    """Runs the Apify Reddit Scraper actor synchronously and returns posts
    normalized to {subreddit, title, selftext, score, created_utc} — the
    shape analysis/sentiment.py's score_player_mentions() expects.

    flairs: only posts whose flair contains one of these (case-insensitive)
    are kept; a post with no determinable flair is dropped whenever a
    filter is active. Pass flairs=None to disable flair filtering entirely.
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
        if flairs and not _flair_matches(_first_present(item, FLAIR_KEYS), flairs):
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
