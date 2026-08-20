"""CRUD for `league_sources` — which leagues to sync, plus per-league
settings (my_owner_id, format override, ESPN season). This is the DB-backed
successor to config/leagues.yaml: editable live from the web Settings page,
and — unlike the YAML file — persists across a Railway redeploy, since it
lives on the same DB Volume as everything else rather than in the git
checkout Railway re-clones on every deploy.

`load_config(conn)` is what the rest of the app should call in place of the
old `config.load_config()` — it transparently migrates an existing local
config/leagues.yaml the first time this table is empty (see
migrate_yaml_if_needed), then builds the same AppConfig shape everything
already expects, merging in ESPN cookie credentials from the environment/
secrets.yaml the same way config.py always did (those stay out of the DB —
they're auth credentials, not league settings).
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

from . import config as config_module

VALID_FORMATS = {"redraft", "dynasty", "devy"}
VALID_PLATFORMS = {"sleeper", "espn"}


class LeagueSourceError(ValueError):
    pass


def list_sources(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM league_sources ORDER BY platform, added_at").fetchall()


def get_source(conn: sqlite3.Connection, league_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM league_sources WHERE league_id = ?", (league_id,)).fetchone()


def _validate_format(format_override: str | None) -> None:
    if format_override is not None and format_override not in VALID_FORMATS:
        raise LeagueSourceError(f"Unknown format: {format_override!r} (expected one of {sorted(VALID_FORMATS)})")


def add_source(
    conn: sqlite3.Connection,
    league_id: str,
    platform: str,
    format_override: str | None = None,
    my_owner_id: str | None = None,
    espn_season: int | None = None,
) -> None:
    if platform not in VALID_PLATFORMS:
        raise LeagueSourceError(f"Unknown platform: {platform!r} (expected one of {sorted(VALID_PLATFORMS)})")
    _validate_format(format_override)
    if get_source(conn, league_id):
        raise LeagueSourceError(f"League {league_id} is already tracked.")
    # Only one ESPN league is wired up end-to-end right now (sync-espn,
    # sync-rankings' ESPN half, etc. all assume a single espn_league) —
    # reject a second one explicitly rather than silently only using the
    # first and confusing whoever added the second.
    if platform == "espn" and conn.execute("SELECT 1 FROM league_sources WHERE platform = 'espn'").fetchone():
        raise LeagueSourceError("Only one ESPN league is supported right now — remove the existing one first.")

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO league_sources (league_id, platform, format_override, my_owner_id, espn_season, added_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (league_id, platform, format_override, my_owner_id or None, espn_season, now),
    )
    conn.commit()


def update_source(
    conn: sqlite3.Connection,
    league_id: str,
    format_override: str | None = None,
    my_owner_id: str | None = None,
    espn_season: int | None = None,
) -> bool:
    """Overwrites format_override/my_owner_id/espn_season for an existing
    source. Pass None for any field to clear it — this always sets all
    three, matching a form submission where every field is present (empty
    means "unset"), not a sparse partial-update."""
    _validate_format(format_override)
    if not get_source(conn, league_id):
        return False
    conn.execute(
        "UPDATE league_sources SET format_override = ?, my_owner_id = ?, espn_season = ? WHERE league_id = ?",
        (format_override, my_owner_id or None, espn_season, league_id),
    )
    conn.commit()
    return True


def remove_source(conn: sqlite3.Connection, league_id: str) -> bool:
    """Stops syncing this league. Does NOT delete already-synced data
    (leagues/rosters/etc. rows) — that's harmless to leave behind, and
    deleting it is a separate, more destructive action nobody asked for."""
    cur = conn.execute("DELETE FROM league_sources WHERE league_id = ?", (league_id,))
    conn.commit()
    return cur.rowcount > 0


def migrate_yaml_if_needed(conn: sqlite3.Connection) -> int:
    """One-time import from config/leagues.yaml into league_sources, only
    if the table is currently empty — never overwrites DB-based edits made
    since (so this stays safe to call on every load_config()). Returns how
    many rows were migrated; 0 if there was nothing to do (table already
    has rows, or no YAML file exists — e.g. a fresh Railway deploy with
    Settings as the only way leagues ever get added)."""
    existing = conn.execute("SELECT COUNT(*) AS n FROM league_sources").fetchone()
    if existing["n"] > 0:
        return 0
    try:
        # Passed explicitly (not relying on load_config_from_yaml's default
        # parameter) so this re-reads config_module.DEFAULT_CONFIG_PATH at
        # call time — a default arg is bound once at function-definition
        # time, so relying on it would silently ignore any later change to
        # the module attribute (including tests monkeypatching it).
        app_config = config_module.load_config_from_yaml(
            path=config_module.DEFAULT_CONFIG_PATH, secrets_path=config_module.DEFAULT_SECRETS_PATH
        )
    except FileNotFoundError:
        return 0

    now = datetime.now(timezone.utc).isoformat()
    count = 0
    for league_cfg in app_config.sleeper_leagues:
        conn.execute(
            "INSERT OR IGNORE INTO league_sources (league_id, platform, format_override, my_owner_id, espn_season, added_at) "
            "VALUES (?, 'sleeper', ?, ?, NULL, ?)",
            (league_cfg.league_id, league_cfg.format, league_cfg.my_owner_id, now),
        )
        count += 1
    if app_config.espn_league:
        e = app_config.espn_league
        conn.execute(
            "INSERT OR IGNORE INTO league_sources (league_id, platform, format_override, my_owner_id, espn_season, added_at) "
            "VALUES (?, 'espn', ?, ?, ?, ?)",
            (e.league_id, e.format, e.my_owner_id, e.season, now),
        )
        count += 1
    conn.commit()
    return count


def load_config(conn: sqlite3.Connection) -> config_module.AppConfig:
    """The DB-backed replacement for config.load_config_from_yaml() — reads
    league_sources (migrating an existing YAML setup in first, if needed),
    and merges in ESPN cookie credentials from the environment or
    config/secrets.yaml (those still don't live in the DB)."""
    migrate_yaml_if_needed(conn)
    rows = list_sources(conn)

    sleeper_leagues = [
        config_module.SleeperLeagueConfig(
            league_id=row["league_id"],
            format=row["format_override"],
            my_owner_id=row["my_owner_id"],
        )
        for row in rows
        if row["platform"] == "sleeper"
    ]

    espn_league = None
    espn_row = next((row for row in rows if row["platform"] == "espn"), None)
    if espn_row:
        secrets = {}
        secrets_path = config_module.DEFAULT_SECRETS_PATH
        if secrets_path.exists():
            import yaml

            secrets = yaml.safe_load(secrets_path.read_text()) or {}
        espn_secrets = secrets.get("espn", {})
        swid = os.environ.get("ESPN_SWID") or espn_secrets.get("swid")
        espn_s2 = os.environ.get("ESPN_S2") or espn_secrets.get("espn_s2")
        espn_league = config_module.EspnLeagueConfig(
            league_id=espn_row["league_id"],
            season=espn_row["espn_season"],
            private=None,
            format=espn_row["format_override"],
            swid=swid,
            espn_s2=espn_s2,
            my_owner_id=espn_row["my_owner_id"],
        )

    return config_module.AppConfig(sleeper_leagues=sleeper_leagues, espn_league=espn_league)
