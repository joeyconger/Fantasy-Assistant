"""Pulls league/roster/player data from Sleeper and upserts it into SQLite."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from .client import SleeperClient

PLAYERS_CACHE_TTL = timedelta(hours=24)


def _detect_format(sleeper_type: int) -> str:
    # Sleeper settings.type: 0 = redraft, 1 = keeper, 2 = dynasty.
    # Devy isn't a Sleeper concept — that's a manual override in config/leagues.yaml.
    return "redraft" if sleeper_type == 0 else "dynasty"


def sync_league(conn: sqlite3.Connection, client: SleeperClient, league_id: str, format_override: str | None = None) -> dict:
    """Fetch league settings, rosters, and users from Sleeper; upsert into the DB.

    Returns the detected/effective format so the caller can report it back
    (useful since devy leagues need a manual config override).
    """
    league = client.get_league(league_id)
    rosters = client.get_rosters(league_id)
    users = client.get_users(league_id)

    sleeper_type = int((league.get("settings") or {}).get("type", 0))
    effective_format = format_override or _detect_format(sleeper_type)

    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """
        INSERT INTO leagues (
            league_id, platform, name, season, format, sleeper_type,
            scoring_settings, roster_positions, total_rosters, last_synced_at
        ) VALUES (?, 'sleeper', ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(league_id) DO UPDATE SET
            name=excluded.name,
            season=excluded.season,
            format=excluded.format,
            sleeper_type=excluded.sleeper_type,
            scoring_settings=excluded.scoring_settings,
            roster_positions=excluded.roster_positions,
            total_rosters=excluded.total_rosters,
            last_synced_at=excluded.last_synced_at
        """,
        (
            league_id,
            league.get("name"),
            league.get("season"),
            effective_format,
            sleeper_type,
            json.dumps(league.get("scoring_settings") or {}),
            json.dumps(league.get("roster_positions") or []),
            league.get("total_rosters"),
            now,
        ),
    )

    for user in users:
        metadata = user.get("metadata") or {}
        conn.execute(
            """
            INSERT INTO owners (league_id, owner_id, display_name, team_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(league_id, owner_id) DO UPDATE SET
                display_name=excluded.display_name,
                team_name=excluded.team_name
            """,
            (league_id, user["user_id"], user.get("display_name"), metadata.get("team_name")),
        )

    conn.execute("DELETE FROM roster_players WHERE league_id = ?", (league_id,))
    for roster in rosters:
        roster_id = str(roster["roster_id"])
        settings = roster.get("settings") or {}
        fpts = float(settings.get("fpts", 0)) + float(settings.get("fpts_decimal", 0)) / 100
        fpts_against = float(settings.get("fpts_against", 0)) + float(settings.get("fpts_against_decimal", 0)) / 100

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
                roster.get("owner_id"),
                settings.get("wins", 0),
                settings.get("losses", 0),
                settings.get("ties", 0),
                fpts,
                fpts_against,
                settings.get("waiver_position"),
            ),
        )

        starters = set(roster.get("starters") or [])
        taxi = set(roster.get("taxi") or [])
        reserve = set(roster.get("reserve") or [])
        for player_id in roster.get("players") or []:
            conn.execute(
                """
                INSERT INTO roster_players (league_id, roster_id, player_id, is_starter, is_taxi, is_ir)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(league_id, roster_id, player_id) DO UPDATE SET
                    is_starter=excluded.is_starter,
                    is_taxi=excluded.is_taxi,
                    is_ir=excluded.is_ir
                """,
                (
                    league_id,
                    roster_id,
                    player_id,
                    1 if player_id in starters else 0,
                    1 if player_id in taxi else 0,
                    1 if player_id in reserve else 0,
                ),
            )

    conn.commit()
    return {"league_id": league_id, "name": league.get("name"), "format": effective_format, "sleeper_type": sleeper_type}


def sync_players(conn: sqlite3.Connection, client: SleeperClient, force: bool = False) -> int:
    """Refresh the full NFL player pool, but only if the cache is stale (>24h)
    or force=True — this payload is multi-MB and Sleeper asks it be pulled sparingly.

    Returns the number of players upserted, or 0 if the cache was still fresh.
    """
    row = conn.execute("SELECT fetched_at FROM players_cache_meta WHERE id = 1").fetchone()
    if row and not force:
        fetched_at = datetime.fromisoformat(row["fetched_at"])
        if datetime.now(timezone.utc) - fetched_at < PLAYERS_CACHE_TTL:
            return 0

    players = client.get_all_players()
    now = datetime.now(timezone.utc).isoformat()

    for player_id, p in players.items():
        conn.execute(
            """
            INSERT INTO players (player_id, platform, full_name, position, team, status, age, years_exp, updated_at)
            VALUES (?, 'sleeper', ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id, platform) DO UPDATE SET
                full_name=excluded.full_name,
                position=excluded.position,
                team=excluded.team,
                status=excluded.status,
                age=excluded.age,
                years_exp=excluded.years_exp,
                updated_at=excluded.updated_at
            """,
            (
                player_id,
                p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
                p.get("position"),
                p.get("team"),
                p.get("status"),
                p.get("age"),
                p.get("years_exp"),
                now,
            ),
        )

        # search_rank is Sleeper's own overall-relevance ordering (used to
        # power their player search) — not literally "average draft
        # position," but a usable ADP-like proxy for the same purpose.
        search_rank = p.get("search_rank")
        if search_rank is not None:
            conn.execute(
                """
                INSERT INTO player_rankings (player_id, platform, source, overall_rank, position_rank, adp, fetched_at)
                VALUES (?, 'sleeper', 'sleeper_search_rank', ?, NULL, NULL, ?)
                ON CONFLICT(player_id, platform, source) DO UPDATE SET
                    overall_rank=excluded.overall_rank,
                    fetched_at=excluded.fetched_at
                """,
                (player_id, search_rank, now),
            )

    conn.execute(
        """
        INSERT INTO players_cache_meta (id, fetched_at) VALUES (1, ?)
        ON CONFLICT(id) DO UPDATE SET fetched_at=excluded.fetched_at
        """,
        (now,),
    )
    conn.commit()
    return len(players)
