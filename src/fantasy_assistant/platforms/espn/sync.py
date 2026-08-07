"""Pulls league/roster/standings data from ESPN and upserts it into SQLite,
into the same tables Sleeper sync uses (leagues/owners/rosters/roster_players/players),
tagged with platform='espn'.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from .client import ESPNClient
from .constants import BENCH_SLOT_IDS, IR_SLOT_ID, LINEUP_SLOT_MAP, POSITION_MAP, PRO_TEAM_MAP


def _decode_roster_positions(lineup_slot_counts: dict) -> list[str]:
    positions: list[str] = []
    for slot_id_str, count in lineup_slot_counts.items():
        slot_name = LINEUP_SLOT_MAP.get(int(slot_id_str), f"SLOT{slot_id_str}")
        positions.extend([slot_name] * int(count))
    return positions


def sync_league(
    conn: sqlite3.Connection,
    client: ESPNClient,
    league_id: str,
    season: int,
    format_override: str | None = None,
) -> dict:
    """Fetch league settings, teams, rosters, and members from ESPN; upsert into the DB.

    ESPN gives us no reliable signal for redraft vs. dynasty vs. devy (unlike
    Sleeper's settings.type), so format defaults to 'redraft' unless overridden
    in config/leagues.yaml.
    """
    data = client.get_league(league_id, season)

    settings = data.get("settings") or {}
    effective_format = format_override or "redraft"
    roster_positions = _decode_roster_positions((settings.get("rosterSettings") or {}).get("lineupSlotCounts") or {})
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """
        INSERT INTO leagues (
            league_id, platform, name, season, format, sleeper_type,
            scoring_settings, roster_positions, total_rosters, last_synced_at
        ) VALUES (?, 'espn', ?, ?, ?, NULL, ?, ?, ?, ?)
        ON CONFLICT(league_id) DO UPDATE SET
            name=excluded.name,
            season=excluded.season,
            format=excluded.format,
            scoring_settings=excluded.scoring_settings,
            roster_positions=excluded.roster_positions,
            total_rosters=excluded.total_rosters,
            last_synced_at=excluded.last_synced_at
        """,
        (
            league_id,
            settings.get("name"),
            str(season),
            effective_format,
            json.dumps(settings.get("scoringSettings") or {}),
            json.dumps(roster_positions),
            len(data.get("teams") or []),
            now,
        ),
    )

    member_lookup = {m["id"]: m for m in data.get("members") or []}
    teams = data.get("teams") or []

    for team in teams:
        owner_ids = team.get("owners") or []
        owner_id = owner_ids[0] if owner_ids else None
        team_name = f"{team.get('location', '')} {team.get('nickname', '')}".strip() or team.get("name") or f"Team {team['id']}"

        if owner_id and owner_id in member_lookup:
            m = member_lookup[owner_id]
            display_name = f"{m.get('firstName', '')} {m.get('lastName', '')}".strip() or m.get("displayName")
            conn.execute(
                """
                INSERT INTO owners (league_id, owner_id, display_name, team_name)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(league_id, owner_id) DO UPDATE SET
                    display_name=excluded.display_name,
                    team_name=excluded.team_name
                """,
                (league_id, owner_id, display_name, team_name),
            )

        record = (team.get("record") or {}).get("overall") or {}
        roster_id = str(team["id"])
        conn.execute(
            """
            INSERT INTO rosters (
                league_id, roster_id, owner_id, wins, losses, ties, fpts, fpts_against, waiver_position
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(league_id, roster_id) DO UPDATE SET
                owner_id=excluded.owner_id,
                wins=excluded.wins,
                losses=excluded.losses,
                ties=excluded.ties,
                fpts=excluded.fpts,
                fpts_against=excluded.fpts_against,
                waiver_position=excluded.waiver_position
            """,
            (
                league_id,
                roster_id,
                owner_id,
                record.get("wins", 0),
                record.get("losses", 0),
                record.get("ties", 0),
                record.get("pointsFor", 0.0),
                record.get("pointsAgainst", 0.0),
                team.get("waiverRank"),
            ),
        )

        entries = ((team.get("roster") or {}).get("entries")) or []
        conn.execute("DELETE FROM roster_players WHERE league_id = ? AND roster_id = ?", (league_id, roster_id))
        for entry in entries:
            player_id = str(entry["playerId"])
            lineup_slot = entry.get("lineupSlotId")
            is_starter = 0 if lineup_slot in BENCH_SLOT_IDS or lineup_slot == IR_SLOT_ID else 1
            is_ir = 1 if lineup_slot == IR_SLOT_ID else 0

            conn.execute(
                """
                INSERT INTO roster_players (league_id, roster_id, player_id, is_starter, is_taxi, is_ir)
                VALUES (?, ?, ?, ?, 0, ?)
                ON CONFLICT(league_id, roster_id, player_id) DO UPDATE SET
                    is_starter=excluded.is_starter,
                    is_ir=excluded.is_ir
                """,
                (league_id, roster_id, player_id, is_starter, is_ir),
            )

            player_info = ((entry.get("playerPoolEntry") or {}).get("player")) or {}
            conn.execute(
                """
                INSERT INTO players (player_id, platform, full_name, position, team, status, age, years_exp, updated_at)
                VALUES (?, 'espn', ?, ?, ?, ?, NULL, NULL, ?)
                ON CONFLICT(player_id, platform) DO UPDATE SET
                    full_name=excluded.full_name,
                    position=excluded.position,
                    team=excluded.team,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (
                    player_id,
                    player_info.get("fullName"),
                    POSITION_MAP.get(player_info.get("defaultPositionId")),
                    PRO_TEAM_MAP.get(player_info.get("proTeamId")),
                    player_info.get("injuryStatus"),
                    now,
                ),
            )

    conn.commit()
    return {"league_id": league_id, "name": settings.get("name"), "format": effective_format}
