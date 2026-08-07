import json

from fantasy_assistant.analysis.roster_format import detect_qb_mode


def test_detects_sleeper_super_flex_slot():
    positions = json.dumps(["QB", "RB", "RB", "WR", "WR", "TE", "SUPER_FLEX", "BN"])
    assert detect_qb_mode(positions) == "superflex"


def test_detects_two_qb_slots_as_superflex():
    positions = json.dumps(["QB", "QB", "RB", "WR", "TE", "BN"])
    assert detect_qb_mode(positions) == "superflex"


def test_detects_espn_op_slot_as_superflex():
    positions = json.dumps(["QB", "RB", "WR", "TE", "OP", "BE"])
    assert detect_qb_mode(positions) == "superflex"


def test_plain_one_qb_league_is_1qb():
    positions = json.dumps(["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "BN"])
    assert detect_qb_mode(positions) == "1qb"


def test_missing_or_malformed_defaults_to_1qb():
    assert detect_qb_mode(None) == "1qb"
    assert detect_qb_mode("not json") == "1qb"
    assert detect_qb_mode(json.dumps({"not": "a list"})) == "1qb"
