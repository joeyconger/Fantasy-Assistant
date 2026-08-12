"""Tests the Apify-based Reddit client's defensive field extraction, flair
filtering, and error handling against synthetic dataset-item JSON. Does NOT
prove this matches the real live Apify actor (unverified, see client.py) —
proves the extraction/filtering logic is internally correct for each
variant it claims to handle, and that a genuinely unrecognized response
raises ApifyFetchError instead of failing silently.
"""

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
        json=[{"body": "no title here"}, {"title": "Has a title", "flair": "News"}],
    )

    posts = fetch_recent_posts()
    assert len(posts) == 1
    assert posts[0]["title"] == "Has a title"


@responses.activate
def test_fetch_recent_posts_sends_subreddits_and_limit(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    responses.add(responses.POST, URL, json=[])

    fetch_recent_posts(subreddits=["nfl"], limit=25)

    request_body = responses.calls[0].request.body
    import json as json_module

    payload = json_module.loads(request_body)
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


# ---- flair filtering ----


@responses.activate
def test_fetch_recent_posts_defaults_to_player_discussion_and_news_flairs(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    responses.add(
        responses.POST,
        URL,
        json=[
            {"title": "Keep A", "flair": "Player Discussion"},
            {"title": "Keep B", "flair": "News"},
            {"title": "Drop me", "flair": "Waiver Wire"},
            {"title": "No flair at all"},
        ],
    )

    posts = fetch_recent_posts()
    titles = {p["title"] for p in posts}
    assert titles == {"Keep A", "Keep B"}


@responses.activate
def test_fetch_recent_posts_flair_match_is_case_insensitive_substring(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    responses.add(
        responses.POST,
        URL,
        json=[{"title": "Emoji decorated flair", "flair": "\U0001f4f0 NEWS"}],
    )

    posts = fetch_recent_posts()
    assert len(posts) == 1


@responses.activate
def test_fetch_recent_posts_flairs_none_disables_filtering(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    responses.add(
        responses.POST,
        URL,
        json=[{"title": "Off-topic post", "flair": "Shitpost"}, {"title": "No flair"}],
    )

    posts = fetch_recent_posts(flairs=None)
    assert len(posts) == 2


@responses.activate
def test_fetch_recent_posts_custom_flairs_override_default(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    responses.add(
        responses.POST,
        URL,
        json=[
            {"title": "Trade post", "flair": "Trade"},
            {"title": "News post", "flair": "News"},
        ],
    )

    posts = fetch_recent_posts(flairs=["Trade"])
    assert [p["title"] for p in posts] == ["Trade post"]


@responses.activate
def test_default_subreddit_is_dynastyff_only(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    responses.add(responses.POST, URL, json=[])

    fetch_recent_posts()

    import json as json_module

    payload = json_module.loads(responses.calls[0].request.body)
    assert payload["subreddits"] == ["DynastyFF"]
