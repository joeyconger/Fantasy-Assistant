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
