from __future__ import annotations

import click

from . import config as config_module
from . import db as db_module
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


@cli.command("sync-all")
def sync_all_cmd():
    """Sync players plus every Sleeper league listed in config/leagues.yaml."""
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
        click.echo("ESPN league configured but ESPN sync isn't built yet (Phase 2) — skipped.")


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
