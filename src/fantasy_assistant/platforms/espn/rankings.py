"""Syncs ESPN's full player pool (standard draft rank + ADP) into player_rankings.

Separate from sync.py's league/roster sync, which only ever sees players
rostered in one league. This is meant to cover the whole draftable pool.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .client import ESPNClient
from .constants import POSITION_MAP, PRO_TEAM_MAP


def sync_player_pool(conn: sqlite3.Connection, client: ESPNClient, season: int) -> int:
    entries = client.get_player_pool(season)
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    for entry in entries:
        player = entry.get("player") or entry  # some ESPN shapes nest under "player", some don't
        player_id = player.get("id") or entry.get("id")
        if player_id is None:
            continue
        player_id = str(player_id)

        full_name = player.get("fullName")
        position = POSITION_MAP.get(player.get("defaultPositionId"))
        team = PRO_TEAM_MAP.get(player.get("proTeamId"))

        conn.execute(
            """
            INSERT INTO players (player_id, platform, full_name, position, team, status, age, years_exp, updated_at)
            VALUES (?, 'espn', ?, ?, ?, ?, NULL, NULL, ?)
            ON CONFLICT(player_id, platform) DO UPDATE SET
                full_name=COALESCE(excluded.full_name, players.full_name),
                position=COALESCE(excluded.position, players.position),
                team=COALESCE(excluded.team, players.team),
                updated_at=excluded.updated_at
            """,
            (player_id, full_name, position, team, player.get("injuryStatus"), now),
        )

        rank_types = player.get("draftRanksByRankType") or {}
        standard = rank_types.get("STANDARD") or {}
        overall_rank = standard.get("rank")
        adp = (player.get("ownership") or {}).get("averageDraftPosition")

        if overall_rank is not None or adp is not None:
            conn.execute(
                """
                INSERT INTO player_rankings (player_id, platform, source, overall_rank, position_rank, adp, fetched_at)
                VALUES (?, 'espn', 'espn_standard_rank', ?, NULL, ?, ?)
                ON CONFLICT(player_id, platform, source) DO UPDATE SET
                    overall_rank=excluded.overall_rank,
                    adp=excluded.adp,
                    fetched_at=excluded.fetched_at
                """,
                (player_id, overall_rank, adp, now),
            )
            count += 1

    conn.commit()
    return count
