from __future__ import annotations

import click

from . import config as config_module
from . import db as db_module
from .platforms.espn.client import ESPNAPIError, ESPNAuthRequired, ESPNClient
from .platforms.espn.sync import sync_league as espn_sync_league
from .platforms.sleeper.client import SleeperAPIError, SleeperClient
from .platforms.sleeper.sync import sync_league, sync_players


@click.group()
def cli():
    """Local fantasy football decision-support tool."""


@cli.command("init-db")
def init_db_cmd():
    """Create the SQLite database and tables if they don't exist yet."""
    conn = db_module.get_connection()
    db_module.init_db(conn)
    click.echo(f"Initialized DB at {db_module.DEFAULT_DB_PATH}")


@cli.command("sync-players")
@click.option("--force", is_flag=True, help="Refetch even if the cache is <24h old.")
def sync_players_cmd(force: bool):
    """Refresh the full Sleeper NFL player pool (cached for 24h)."""
    conn = db_module.get_connection()
    db_module.init_db(conn)
    client = SleeperClient()
    try:
        count = sync_players(conn, client, force=force)
    except SleeperAPIError as exc:
        raise click.ClickException(str(exc))
    if count:
        click.echo(f"Synced {count} players.")
    else:
        click.echo("Player cache is still fresh (<24h old) — skipped. Use --force to refetch.")


@cli.command("sync-league")
@click.argument("league_id")
@click.option("--format", "format_override", type=click.Choice(["redraft", "dynasty", "devy"]), default=None)
def sync_league_cmd(league_id: str, format_override: str | None):
    """Sync one Sleeper league's settings, rosters, and standings."""
    conn = db_module.get_connection()
    db_module.init_db(conn)
    client = SleeperClient()
    try:
        result = sync_league(conn, client, league_id, format_override=format_override)
    except SleeperAPIError as exc:
        raise click.ClickException(str(exc))
    click.echo(f"Synced '{result['name']}' ({result['league_id']}) — format: {result['format']}")


@cli.command("sync-espn")
def sync_espn_cmd():
    """Sync the ESPN league's settings, rosters, and standings."""
    conn = db_module.get_connection()
    db_module.init_db(conn)

    try:
        app_config = config_module.load_config()
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc))

    if not app_config.espn_league:
        raise click.ClickException("No ESPN league configured in config/leagues.yaml.")
    espn_cfg = app_config.espn_league
    if not espn_cfg.season:
        raise click.ClickException("Set espn.season in config/leagues.yaml before syncing.")

    client = ESPNClient(swid=espn_cfg.swid, espn_s2=espn_cfg.espn_s2)
    try:
        result = espn_sync_league(conn, client, espn_cfg.league_id, espn_cfg.season, format_override=espn_cfg.format)
    except ESPNAuthRequired as exc:
        raise click.ClickException(str(exc))
    except ESPNAPIError as exc:
        raise click.ClickException(str(exc))
    click.echo(f"Synced '{result['name']}' ({result['league_id']}) — format: {result['format']}")


@cli.command("sync-all")
def sync_all_cmd():
    """Sync players plus every Sleeper league listed in config/leagues.yaml, and ESPN if configured."""
    conn = db_module.get_connection()
    db_module.init_db(conn)
    client = SleeperClient()

    try:
        app_config = config_module.load_config()
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc))

    try:
        count = sync_players(conn, client)
        click.echo(f"Players: synced {count}" if count else "Players: cache fresh, skipped")

        for league_cfg in app_config.sleeper_leagues:
            result = sync_league(conn, client, league_cfg.league_id, format_override=league_cfg.format)
            note = "" if league_cfg.format else "  (auto-detected — set format: in config/leagues.yaml to override, e.g. for devy)"
            click.echo(f"League: synced '{result['name']}' ({result['league_id']}) — format: {result['format']}{note}")
    except SleeperAPIError as exc:
        raise click.ClickException(str(exc))

    if app_config.espn_league:
        espn_cfg = app_config.espn_league
        if not espn_cfg.season:
            click.echo("ESPN league configured but no season set in config/leagues.yaml — skipped.")
        else:
            espn_client = ESPNClient(swid=espn_cfg.swid, espn_s2=espn_cfg.espn_s2)
            try:
                result = espn_sync_league(conn, espn_client, espn_cfg.league_id, espn_cfg.season, format_override=espn_cfg.format)
                click.echo(f"ESPN league: synced '{result['name']}' ({result['league_id']}) — format: {result['format']}")
            except ESPNAuthRequired as exc:
                click.echo(f"ESPN league: skipped — {exc}")
            except ESPNAPIError as exc:
                click.echo(f"ESPN league: skipped — {exc}")


@cli.command("standings")
@click.argument("league_id")
def standings_cmd(league_id: str):
    """Print current standings for a synced league."""
    conn = db_module.get_connection()
    league = conn.execute("SELECT * FROM leagues WHERE league_id = ?", (league_id,)).fetchone()
    if not league:
        raise click.ClickException(f"League {league_id} hasn't been synced yet. Run sync-league first.")

    rows = conn.execute(
        """
        SELECT r.wins, r.losses, r.ties, r.fpts, r.fpts_against,
               COALESCE(o.team_name, o.display_name, 'Roster ' || r.roster_id) AS team
        FROM rosters r
        LEFT JOIN owners o ON o.league_id = r.league_id AND o.owner_id = r.owner_id
        WHERE r.league_id = ?
        ORDER BY r.wins DESC, r.fpts DESC
        """,
        (league_id,),
    ).fetchall()

    click.echo(f"{league['name']} ({league['format']}, {league['season']})")
    click.echo(f"{'Team':<25} {'W':>3} {'L':>3} {'T':>3} {'PF':>8} {'PA':>8}")
    for row in rows:
        click.echo(
            f"{row['team']:<25} {row['wins']:>3} {row['losses']:>3} {row['ties']:>3} "
            f"{row['fpts']:>8.2f} {row['fpts_against']:>8.2f}"
        )


if __name__ == "__main__":
    cli()
