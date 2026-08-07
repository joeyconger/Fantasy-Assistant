"""Basic lexicon-based sentiment scoring: player name mentions + a
positive/negative word list. Not NLP-grade — it's a cheap, transparent
signal ("this player is being talked about a lot, mostly positively") not a
claim of nuanced sentiment understanding. Good enough as one input into the
buy-low/sell-high engine, not a standalone product.
"""

from __future__ import annotations

from ..platforms.matching import normalize_name

POSITIVE_WORDS = {
    "breakout", "buy", "upside", "great", "explosive", "stud", "elite",
    "smash", "must-start", "hot", "steal", "value", "workhorse", "bell cow", "league winner",
}
NEGATIVE_WORDS = {
    "bust", "sell", "drop", "cut", "injury", "injured", "concern", "worried",
    "avoid", "fade", "cold", "overrated", "risky", "bench him",
}


def score_text(text: str) -> int:
    lowered = text.lower()
    pos = sum(1 for w in POSITIVE_WORDS if w in lowered)
    neg = sum(1 for w in NEGATIVE_WORDS if w in lowered)
    return pos - neg


def score_player_mentions(posts: list[dict], player_names: list[str]) -> dict[str, dict]:
    """player_names: full names to track. Matches on last name (crude but
    transparent) to catch casual references like "Chase is a stud".

    Returns {normalized_name: {full_name, mention_count, positive_count,
    negative_count, net_score}}, only for players with >=1 mention.
    """
    tracked = {normalize_name(n): n for n in player_names}
    last_names = {norm: name.split()[-1].lower() for norm, name in tracked.items()}

    results = {
        norm: {"full_name": name, "mention_count": 0, "positive_count": 0, "negative_count": 0, "net_score": 0}
        for norm, name in tracked.items()
    }

    for post in posts:
        text = f"{post.get('title', '')} {post.get('selftext', '')}"
        lowered = text.lower()
        score = None
        for norm, last_name in last_names.items():
            if last_name not in lowered:
                continue
            if score is None:
                score = score_text(text)
            entry = results[norm]
            entry["mention_count"] += 1
            if score > 0:
                entry["positive_count"] += 1
            elif score < 0:
                entry["negative_count"] += 1
            entry["net_score"] += score

    return {k: v for k, v in results.items() if v["mention_count"] > 0}
