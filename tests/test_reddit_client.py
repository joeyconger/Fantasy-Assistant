"""Tests the Apify-based Reddit client's defensive field extraction,
per-subreddit flair filtering, and error handling against synthetic
dataset-item JSON. Does NOT prove this matches the real live Apify actor
(unverified, see client.py) — proves the extraction/filtering logic is
internally correct for each variant it claims to handle, and that a
genuinely unrecognized response raises ApifyFetchError instead of failing
silently.
"""

import json as json_module

import responses

from fantasy_assistant.platforms.reddit.client import (
    ApifyFetchError,
    ApifyNotConfigured,
    DEFAULT_ACTOR,
    fetch_recent_posts,
)

URL = f"https://api.apify.com/v2/acts/{DEFAULT_ACTOR}/run-sync-get-dataset-items"


@responses.activate
def test_fetch_recent_posts_requires_api_token(monkeypatch):
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    try:
        fetch_recent_posts()
        assert False, "expected ApifyNotConfigured"
    except ApifyNotConfigured:
        pass


@responses.activate
def test_fetch_recent_posts_extracts_primary_field_names(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    responses.add(
        responses.POST,
        URL,
        json=[
            {
                "title": "Bijan Robinson is a stud this year",
                "body": "Full breakdown here",
                "communityName": "DynastyFF",
                "score": 42,
                "createdAt": "2026-08-01T00:00:00Z",
                "flair": "Player Discussion",
            }
        ],
    )

    posts = fetch_recent_posts()
    assert len(posts) == 1
    assert posts[0]["title"] == "Bijan Robinson is a stud this year"
    assert posts[0]["selftext"] == "Full breakdown here"
    assert posts[0]["subreddit"] == "DynastyFF"
    assert posts[0]["score"] == 42
    assert posts[0]["created_utc"] == "2026-08-01T00:00:00Z"


@responses.activate
def test_fetch_recent_posts_falls_back_to_alternate_field_names(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    responses.add(
        responses.POST,
        URL,
        json=[
            {
                "title": "Baker Mayfield sleeper pick",
                "selftext": "he's cooked before",
                "subredditName": "DynastyFF",
                "upVotes": 10,
                "created_utc": 1735689600,
                "linkFlairText": "News",
            }
        ],
    )

    posts = fetch_recent_posts()
    assert posts[0]["selftext"] == "he's cooked before"
    assert posts[0]["subreddit"] == "DynastyFF"
    assert posts[0]["score"] == 10
    assert posts[0]["created_utc"] == 1735689600


@responses.activate
def test_fetch_recent_posts_skips_items_with_no_title(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    responses.add(
        responses.POST,
        URL,
        json=[{"body": "no title here", "communityName": "DynastyFF", "flair": "News"}, {"title": "Has a title", "communityName": "DynastyFF", "flair": "News"}],
    )

    posts = fetch_recent_posts()
    assert len(posts) == 1
    assert posts[0]["title"] == "Has a title"


@responses.activate
def test_fetch_recent_posts_sends_all_requested_subreddits_and_limit(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    responses.add(responses.POST, URL, json=[])

    fetch_recent_posts(subreddit_flairs={"nfl": None}, limit=25)

    payload = json_module.loads(responses.calls[0].request.body)
    assert payload["subreddits"] == ["nfl"]
    assert payload["maxItems"] == 25


@responses.activate
def test_fetch_recent_posts_raises_on_non_list_response(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    responses.add(responses.POST, URL, json={"error": "actor output shape changed"})

    try:
        fetch_recent_posts()
        assert False, "expected ApifyFetchError"
    except ApifyFetchError:
        pass


@responses.activate
def test_fetch_recent_posts_raises_on_http_error(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    responses.add(responses.POST, URL, status=402, body="Payment required")

    try:
        fetch_recent_posts()
        assert False, "expected ApifyFetchError"
    except ApifyFetchError as exc:
        assert "402" in str(exc)


# ---- per-subreddit flair filtering ----


@responses.activate
def test_default_requests_both_dynastyff_and_fantasyfootball(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    responses.add(responses.POST, URL, json=[])

    fetch_recent_posts()

    payload = json_module.loads(responses.calls[0].request.body)
    assert set(payload["subreddits"]) == {"DynastyFF", "fantasyfootball"}


@responses.activate
def test_dynastyff_allows_player_discussion_and_news_by_default(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    responses.add(
        responses.POST,
        URL,
        json=[
            {"title": "Keep A", "communityName": "DynastyFF", "flair": "Player Discussion"},
            {"title": "Keep B", "communityName": "DynastyFF", "flair": "News"},
            {"title": "Drop trade post", "communityName": "DynastyFF", "flair": "Trade"},
        ],
    )

    posts = fetch_recent_posts()
    assert {p["title"] for p in posts} == {"Keep A", "Keep B"}


@responses.activate
def test_fantasyfootball_only_allows_player_discussion_by_default(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    responses.add(
        responses.POST,
        URL,
        json=[
            {"title": "Keep me", "communityName": "fantasyfootball", "flair": "Player Discussion"},
            {"title": "Drop news post", "communityName": "fantasyfootball", "flair": "News"},
        ],
    )

    posts = fetch_recent_posts()
    assert [p["title"] for p in posts] == ["Keep me"]


@responses.activate
def test_post_from_unrequested_subreddit_is_dropped(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    responses.add(
        responses.POST,
        URL,
        json=[{"title": "Off-target sub", "communityName": "nfl", "flair": "Player Discussion"}],
    )

    posts = fetch_recent_posts()
    assert posts == []


@responses.activate
def test_post_with_no_determinable_subreddit_is_dropped(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    responses.add(responses.POST, URL, json=[{"title": "No subreddit field", "flair": "News"}])

    posts = fetch_recent_posts()
    assert posts == []


@responses.activate
def test_flair_match_is_case_insensitive_substring(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    responses.add(
        responses.POST,
        URL,
        json=[{"title": "Emoji decorated flair", "communityName": "DynastyFF", "flair": "\U0001f4f0 NEWS"}],
    )

    posts = fetch_recent_posts()
    assert len(posts) == 1


@responses.activate
def test_subreddit_with_none_flair_rule_gets_no_filter(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    responses.add(
        responses.POST,
        URL,
        json=[{"title": "Off-topic post", "communityName": "nfl", "flair": "Shitpost"}],
    )

    posts = fetch_recent_posts(subreddit_flairs={"nfl": None})
    assert len(posts) == 1


@responses.activate
def test_custom_subreddit_flairs_override_default(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    responses.add(
        responses.POST,
        URL,
        json=[
            {"title": "Trade post", "communityName": "DynastyFF", "flair": "Trade"},
            {"title": "Discussion post", "communityName": "DynastyFF", "flair": "Player Discussion"},
        ],
    )

    posts = fetch_recent_posts(subreddit_flairs={"DynastyFF": ["Trade"]})
    assert [p["title"] for p in posts] == ["Trade post"]
