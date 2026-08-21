from fantasy_assistant.analysis.sentiment import score_player_mentions, score_text


def test_score_text_counts_positive_and_negative_words():
    assert score_text("This guy is a stud breakout candidate") > 0
    assert score_text("Total bust, drop him, injury concern") < 0
    assert score_text("The weather was nice today") == 0


def test_score_player_mentions_matches_by_last_name():
    posts = [
        {"title": "Chase is a stud this year", "selftext": "smash play every week"},
        {"title": "Unrelated post about waivers", "selftext": ""},
    ]
    results = score_player_mentions(posts, ["Ja'Marr Chase"])
    key = list(results.keys())[0]
    assert results[key]["mention_count"] == 1
    assert results[key]["positive_count"] == 1


def test_score_player_mentions_excludes_players_with_no_mentions():
    posts = [{"title": "Nothing relevant here", "selftext": ""}]
    results = score_player_mentions(posts, ["Ja'Marr Chase"])
    assert results == {}


def test_score_player_mentions_tracks_negative_sentiment():
    posts = [{"title": "Chase is a bust, fade him, sell now", "selftext": ""}]
    results = score_player_mentions(posts, ["Ja'Marr Chase"])
    key = list(results.keys())[0]
    assert results[key]["negative_count"] == 1
    assert results[key]["net_score"] < 0


def test_score_player_mentions_requires_full_name_for_shared_last_names():
    """"Allen is a must-start" shouldn't score both Josh Allen and Cyrus
    Allen off a bare last-name match — that's a real, different player
    each time, and attributing one post's sentiment to both would be wrong."""
    posts = [{"title": "Allen is a must-start this week", "selftext": ""}]
    results = score_player_mentions(posts, ["Josh Allen", "Cyrus Allen"])
    assert results == {}


def test_score_player_mentions_matches_full_name_when_last_name_is_ambiguous():
    posts = [{"title": "Josh Allen is a must-start this week", "selftext": ""}]
    results = score_player_mentions(posts, ["Josh Allen", "Cyrus Allen"])
    assert len(results) == 1
    entry = list(results.values())[0]
    assert entry["full_name"] == "Josh Allen"
    assert entry["mention_count"] == 1


def test_score_player_mentions_last_name_matching_unaffected_when_unique():
    """A player whose last name isn't shared by anyone else being tracked
    should still match on the bare last name, same as before."""
    posts = [{"title": "Chase is a stud this year", "selftext": ""}]
    results = score_player_mentions(posts, ["Ja'Marr Chase", "Josh Allen"])
    assert len(results) == 1
    assert list(results.values())[0]["full_name"] == "Ja'Marr Chase"
