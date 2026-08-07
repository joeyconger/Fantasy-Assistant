"""Detects whether a league is 1QB or Superflex from its already-synced
roster_positions — this swings dynasty/devy QB value dramatically, and KTC
publishes separate rankings for each, so getting this wrong would compare a
Superflex roster against 1QB-priced values (or vice versa).

No extra API call needed: roster_positions is already stored on the
leagues row from the original league sync.
"""

from __future__ import annotations

import json

# Sleeper uses the literal slot name "SUPER_FLEX". ESPN's lineup slot 7 is
# decoded to "OP" (offensive player) in platforms/espn/constants.py — same
# concept, different label.
SUPERFLEX_MARKERS = {"SUPER_FLEX", "SUPERFLEX", "OP"}


def detect_qb_mode(roster_positions_json: str | None) -> str:
    """Returns '1qb' or 'superflex'."""
    if not roster_positions_json:
        return "1qb"
    try:
        positions = json.loads(roster_positions_json)
    except (json.JSONDecodeError, TypeError):
        return "1qb"
    if not isinstance(positions, list):
        return "1qb"

    if any(p in SUPERFLEX_MARKERS for p in positions):
        return "superflex"
    if positions.count("QB") >= 2:
        return "superflex"
    return "1qb"
