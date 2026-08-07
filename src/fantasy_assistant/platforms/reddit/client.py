"""PRAW wrapper for pulling recent posts from fantasy football subreddits.

**NOT TESTED AT ALL**: needs a Reddit "script" app (client_id + client_secret
from https://www.reddit.com/prefs/apps -> create app -> script) which only
you can create, since it's tied to your Reddit account. This environment's
egress policy also blocks reddit.com/oauth.reddit.com outright, so even with
credentials this couldn't be exercised from here. It's standard PRAW
read-only usage (no login needed to read public posts), so it should work
once you supply credentials and run it somewhere with real network access —
but that combination has never actually been tried.
"""

from __future__ import annotations

import os

import praw

DEFAULT_SUBREDDITS = ["fantasyfootball", "DynastyFF"]
DEFAULT_USER_AGENT = "fantasy-assistant/0.1 (personal use)"


class RedditNotConfigured(RuntimeError):
    pass


def build_reddit_client() -> praw.Reddit:
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RedditNotConfigured(
            "REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET aren't set. Create a 'script' app at "
            "https://www.reddit.com/prefs/apps and set those two env vars (REDDIT_USER_AGENT "
            "optional) before Reddit sentiment can run."
        )
    user_agent = os.environ.get("REDDIT_USER_AGENT", DEFAULT_USER_AGENT)
    return praw.Reddit(client_id=client_id, client_secret=client_secret, user_agent=user_agent)


def fetch_recent_posts(reddit: praw.Reddit, subreddits: list[str] | None = None, limit: int = 100) -> list[dict]:
    subreddits = subreddits or DEFAULT_SUBREDDITS
    posts = []
    for sub_name in subreddits:
        subreddit = reddit.subreddit(sub_name)
        for post in subreddit.new(limit=limit):
            posts.append(
                {
                    "subreddit": sub_name,
                    "title": post.title,
                    "selftext": post.selftext or "",
                    "score": post.score,
                    "created_utc": post.created_utc,
                }
            )
    return posts
