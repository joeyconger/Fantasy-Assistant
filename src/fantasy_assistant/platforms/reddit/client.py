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

Each subreddit gets its own flair allowlist (DEFAULT_SUBREDDIT_FLAIRS) — by
request, since r/DynastyFF's "Player Discussion"/"News" posts and
r/fantasyfootball's "Player Discussion" posts are the relevant signal, not
every post in either subreddit. Flair filtering happens client-side after
one combined fetch (not passed as an actor input param, since actor-level
flair filter support isn't confirmed either — safer to filter on data we
can actually see). The flair match is a case-insensitive substring check
rather than exact equality, since real Reddit flairs are often decorated
with emoji/extra text (e.g. "🏈 News") that would break an exact match. A
post whose subreddit or flair can't be determined at all is excluded —
silently including it would mean applying no rule at all, which defeats
the point of asking for specific subreddits/flairs.
"""

from __future__ import annotations

import os

import requests

TIMEOUT_SECONDS = 60
DEFAULT_ACTOR = "trudax~reddit-scraper-lite"

# subreddit -> allowed flairs (None means "no flair filter for this sub").
# Matched against the extracted subreddit case-insensitively.
DEFAULT_SUBREDDIT_FLAIRS: dict[str, list[str] | None] = {
    "DynastyFF": ["Player Discussion", "News"],
    "fantasyfootball": ["Player Discussion"],
}

# Candidate field names per attribute, tried in order — not confirmed live.
TITLE_KEYS = ("title",)
BODY_KEYS = ("body", "selftext", "text", "description")
SUBREDDIT_KEYS = ("communityName", "subredditName", "subreddit", "community")
SCORE_KEYS = ("score", "upVotes", "numberOfUpvotes", "upvotes")
CREATED_KEYS = ("createdAt", "created_utc", "date", "createdAtFormatted")
FLAIR_KEYS = ("flair", "linkFlairText", "flairText", "link_flair_text")

_NO_RULE = object()  # sentinel: subreddit isn't in the ruleset at all


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
    subreddit_flairs: dict[str, list[str] | None] | None = None,
    limit: int = 100,
    actor: str = DEFAULT_ACTOR,
    session: requests.Session | None = None,
) -> list[dict]:
    """Runs the Apify Reddit Scraper actor synchronously (one call covering
    every subreddit in subreddit_flairs) and returns posts normalized to
    {subreddit, title, selftext, score, created_utc} — the shape
    analysis/sentiment.py's score_player_mentions() expects.

    subreddit_flairs: {subreddit_name: [allowed flairs] | None}. A `None`
    value means no flair filter for that subreddit. Defaults to
    DEFAULT_SUBREDDIT_FLAIRS. A post from a subreddit not present in this
    dict (or whose subreddit can't be determined) is dropped.
    """
    token = _api_token()
    subreddit_flairs = subreddit_flairs or DEFAULT_SUBREDDIT_FLAIRS
    rules_by_lower_sub = {sub.lower(): flairs for sub, flairs in subreddit_flairs.items()}
    session = session or requests.Session()

    url = f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
    payload = {"subreddits": list(subreddit_flairs.keys()), "sort": "new", "maxItems": limit}

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

        subreddit = _first_present(item, SUBREDDIT_KEYS)
        rule = rules_by_lower_sub.get((subreddit or "").lower(), _NO_RULE)
        if rule is _NO_RULE:
            continue
        if rule and not _flair_matches(_first_present(item, FLAIR_KEYS), rule):
            continue

        posts.append(
            {
                "subreddit": subreddit or "",
                "title": title,
                "selftext": _first_present(item, BODY_KEYS) or "",
                "score": _first_present(item, SCORE_KEYS) or 0,
                "created_utc": _first_present(item, CREATED_KEYS),
            }
        )
    return posts
