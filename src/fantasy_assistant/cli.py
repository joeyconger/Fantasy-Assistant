from __future__ import annotations

import click

from . import config as config_module
from . import db as db_module
from .analysis.buy_low_sell_high import find_buy_low_sell_high
from .analysis.draft_board import find_rank_inefficiencies
from .analysis.trade_analyzer import TradeAnalyzerError, analyze_trade
from .analysis.waiver_targets import top_trade_targets, top_waiver_adds
from . import devy as devy_module
from .platforms.espn.client import ESPNAPIError, ESPNAuthRequired, ESPNClient
from .platforms.espn.rankings import sync_player_pool as espn_sync_player_pool
from .platforms.espn.sync import sync_league as espn_sync_league
from .platforms.fantasypros.client import FantasyProsClient, FantasyProsFetchError, FantasyProsParseError
from .platforms.fantasypros.sync import sync_rankings as fantasypros_sync_rankings
from .platforms.ffc.client import FFCClient, FFCFetchError, FFCParseError
from .platforms.ffc.sync import sync_adp as ffc_sync_adp
from .platforms.ktc.client import KTCClient, KTCFetchError, KTCParseError
from .platforms.ktc.sync import sync_values as ktc_sync_values
from .analysis.sentiment import score_player_mentions
from .platforms.reddit.client import ApifyFetchError, ApifyNotConfigured, fetch_recent_posts
from .platforms.reddit.sync import sync_sentiment, tracked_player_names
from .platforms.sleeper.client import SleeperAPIError, SleeperClient
from .platforms.sleeper.sync import sync_league, sync_players
from .platforms.sleeper.weekly_points import current_completed_weeks, sync_weekly_points


def _my_owner_id_for(league_id: str) -> str | None:
    """Looks up my_owner_id for a league from config/leagues.yaml, if configured."""
    try:
        app_config = config_module.load_config()
    except FileNotFoundError:
        return None
    for league_cfg in app_config.sleeper_leagues:
        if league_cfg.league_id == league_id:
            return league_cfg.my_owner_id
    if app_config.espn_league and app_config.espn_league.league_id == league_id:
        return app_config.espn_league.my_owner_id
    return None


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

            try:
                count = espn_sync_player_pool(conn, espn_client, espn_cfg.season)
                click.echo(f"ESPN rankings: synced {count} players")
            except (ESPNAuthRequired, ESPNAPIError) as exc:
                click.echo(f"ESPN rankings: skipped — {exc}")


@cli.command("sync-rankings")
def sync_rankings_cmd():
    """Sync overall-rank/ADP data: Sleeper search_rank (from sync-players) + ESPN's full player pool."""
    conn = db_module.get_connection()
    db_module.init_db(conn)

    client = SleeperClient()
    try:
        count = sync_players(conn, client)
        click.echo(f"Sleeper rankings: refreshed with player sync ({count} players)" if count else "Sleeper rankings: player cache fresh, skipped")
    except SleeperAPIError as exc:
        raise click.ClickException(str(exc))

    try:
        app_config = config_module.load_config()
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc))

    if not app_config.espn_league or not app_config.espn_league.season:
        click.echo("ESPN rankings: no ESPN league/season configured — skipped.")
        return

    espn_cfg = app_config.espn_league
    espn_client = ESPNClient(swid=espn_cfg.swid, espn_s2=espn_cfg.espn_s2)
    try:
        count = espn_sync_player_pool(conn, espn_client, espn_cfg.season)
        click.echo(f"ESPN rankings: synced {count} players")
    except (ESPNAuthRequired, ESPNAPIError) as exc:
        click.echo(f"ESPN rankings: failed — {exc}")


@cli.command("draft-board")
@click.option("--limit", default=25, help="How many top inefficiencies to show.")
@click.option("--qb-mode", type=click.Choice(["1qb", "superflex"]), default="1qb")
def draft_board_cmd(limit: int, qb_mode: str):
    """Show players where market ADP (Fantasy Football Calculator) and ESPN rank disagree most — possible draft value."""
    conn = db_module.get_connection()
    results = find_rank_inefficiencies(conn, limit=limit, qb_mode=qb_mode)
    if not results:
        msg = "No matched players with both market ADP and ESPN ranks yet. Run sync-ffc-adp and sync-rankings first."
        if qb_mode == "superflex":
            msg += " (Also possible: ESPN or FFC don't have Superflex-specific data — try --qb-mode 1qb.)"
        click.echo(msg)
        return

    if qb_mode == "superflex" and any(r["position_relative"] for r in results):
        click.echo(
            "Note: RB/WR/TE/K ranks below are position rank (e.g. RB12), not overall rank — "
            "Superflex crowds QBs to the top of each source's overall list, which would otherwise make "
            "every other position look artificially crushed. QB still shows overall rank.\n"
        )

    click.echo(f"{'Player':<25} {'Pos':<5} {'ADP':>8} {'ESPN':>8} {'Delta':>7}  Note")
    for r in results:
        adp_col = f"{r['position']}{r['adp_rank']}" if r["position_relative"] else str(r["adp_rank"])
        espn_col = f"{r['position']}{r['espn_rank']}" if r["position_relative"] else str(r["espn_rank"])
        click.echo(
            f"{r['name']:<25} {r['position']:<5} {adp_col:>8} {espn_col:>8} "
            f"{r['delta']:>7}  {r['note']}"
        )


@cli.command("sync-weekly-points")
@click.argument("league_id")
@click.option("--weeks", default=4, help="How many recent completed weeks to pull.")
def sync_weekly_points_cmd(league_id: str, weeks: int):
    """Pull recent weekly fantasy points for a Sleeper league (performance trend data)."""
    conn = db_module.get_connection()
    db_module.init_db(conn)
    client = SleeperClient()
    try:
        week_list = current_completed_weeks(client, lookback=weeks)
        if not week_list:
            click.echo("No completed weeks yet this season (preseason or week 1) — nothing to sync.")
            return
        count = sync_weekly_points(conn, client, league_id, week_list)
        click.echo(f"Synced {count} player-week point entries for weeks {week_list}.")
    except SleeperAPIError as exc:
        raise click.ClickException(str(exc))


@cli.command("waiver-targets")
@click.argument("league_id")
@click.option("--limit", default=15)
def waiver_targets_cmd(league_id: str, limit: int):
    """Show available (unrostered) players trending up recently."""
    conn = db_module.get_connection()
    my_owner_id = _my_owner_id_for(league_id)
    try:
        results = top_waiver_adds(conn, league_id, limit=limit, my_owner_id=my_owner_id)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    if not results:
        click.echo("No candidates found. Run sync-weekly-points and sync-rankings first.")
        return
    if not my_owner_id:
        click.echo("(Set my_owner_id in config/leagues.yaml to see which candidates fill your roster's needs.)")
    click.echo(f"{'Player':<25} {'Pos':<5} {'Team':<5} {'Recent':>7} {'Season':>7} {'Trend':>7} {'Rank':>6}  Need")
    for r in results:
        need = "FILLS NEED" if r.get("fills_need") else ""
        click.echo(
            f"{r['name']:<25} {r['position']:<5} {(r['team'] or ''):<5} {r['recent_avg']:>7} "
            f"{r['season_avg']:>7} {r['trend']:>7} {r['rank'] or '-':>6}  {need}"
        )


@cli.command("trade-targets")
@click.argument("league_id")
@click.option("--limit", default=15)
def trade_targets_cmd(league_id: str, limit: int):
    """Show rostered players trending up — possible buy-before-price-catches-up trade targets."""
    conn = db_module.get_connection()
    my_owner_id = _my_owner_id_for(league_id)
    try:
        results = top_trade_targets(conn, league_id, limit=limit, my_owner_id=my_owner_id)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    if not results:
        click.echo("No candidates found. Run sync-weekly-points and sync-rankings first.")
        return
    if not my_owner_id:
        click.echo("(Set my_owner_id in config/leagues.yaml to exclude your own roster and see need-fits.)")
    click.echo(f"{'Player':<25} {'Pos':<5} {'Owned By':<20} {'Recent':>7} {'Trend':>7} {'Rank':>6}  Need")
    for r in results:
        need = "FILLS NEED" if r.get("fills_need") else ""
        click.echo(
            f"{r['name']:<25} {r['position']:<5} {r['owned_by']:<20} {r['recent_avg']:>7} "
            f"{r['trend']:>7} {r['rank'] or '-':>6}  {need}"
        )


@cli.command("sync-ktc")
@click.option("--format", "format_", type=click.Choice(["dynasty", "devy"]), default="dynasty")
@click.option("--qb-mode", type=click.Choice(["1qb", "superflex"]), default="1qb", help="Also UNVERIFIED — see client.py.")
@click.option("--force", is_flag=True)
def sync_ktc_cmd(format_: str, qb_mode: str, force: bool):
    """Sync KeepTradeCut dynasty/devy trade values (UNVERIFIED — see platforms/ktc/client.py)."""
    conn = db_module.get_connection()
    db_module.init_db(conn)
    client = KTCClient()
    try:
        count = ktc_sync_values(conn, client, format_, qb_mode=qb_mode, force=force)
    except KTCFetchError as exc:
        raise click.ClickException(f"Couldn't reach KTC: {exc}")
    except KTCParseError as exc:
        raise click.ClickException(
            f"{exc}\n\nThis was never tested against the live site — the parser needs a real look "
            "at the page structure. Paste this error back and it can be fixed."
        )
    click.echo(
        f"Synced {count} {format_}/{qb_mode} values from KTC."
        if count
        else "KTC cache fresh (<12h) — skipped. Use --force."
    )


@cli.command("sync-fantasypros")
@click.option("--force", is_flag=True)
def sync_fantasypros_cmd(force: bool):
    """Sync FantasyPros consensus redraft rankings (UNVERIFIED — see platforms/fantasypros/client.py)."""
    conn = db_module.get_connection()
    db_module.init_db(conn)
    client = FantasyProsClient()
    try:
        count = fantasypros_sync_rankings(conn, client, force=force)
    except FantasyProsFetchError as exc:
        raise click.ClickException(f"Couldn't reach FantasyPros: {exc}")
    except FantasyProsParseError as exc:
        raise click.ClickException(
            f"{exc}\n\nThis was never tested against the live site — the parser needs a real look "
            "at the page structure. Paste this error back and it can be fixed."
        )
    click.echo(f"Synced {count} FantasyPros rankings." if count else "FantasyPros cache fresh (<12h) — skipped. Use --force.")


@cli.command("sync-ffc-adp")
@click.option("--qb-mode", type=click.Choice(["1qb", "superflex"]), default="1qb")
@click.option("--teams", default=12, help="League size FFC's ADP is drawn from.")
@click.option("--force", is_flag=True)
def sync_ffc_adp_cmd(qb_mode: str, teams: int, force: bool):
    """Sync real redraft ADP from Fantasy Football Calculator (UNVERIFIED — see platforms/ffc/client.py). Used by draft-board in place of Sleeper's search_rank."""
    conn = db_module.get_connection()
    db_module.init_db(conn)
    client = FFCClient()
    try:
        count = ffc_sync_adp(conn, client, qb_mode=qb_mode, teams=teams, force=force)
    except FFCFetchError as exc:
        raise click.ClickException(f"Couldn't reach Fantasy Football Calculator: {exc}")
    except FFCParseError as exc:
        raise click.ClickException(
            f"{exc}\n\nThis was never tested against the live API — the parser needs a real look "
            "at the response shape. Paste this error back and it can be fixed."
        )
    click.echo(f"Synced {count} {qb_mode} ADP entries from FFC." if count else "FFC ADP cache fresh (<12h) — skipped. Use --force.")


@cli.command("sync-reddit")
@click.option("--limit", default=100, help="Posts to scan per subreddit.")
def sync_reddit_cmd(limit: int):
    """Pull recent Reddit posts (via Apify) and score sentiment for players in your synced leagues."""
    conn = db_module.get_connection()
    db_module.init_db(conn)

    player_names = tracked_player_names(conn)
    if not player_names:
        click.echo("No rostered players found — sync a league first.")
        return

    try:
        posts = fetch_recent_posts(limit=limit)
    except ApifyNotConfigured as exc:
        raise click.ClickException(str(exc))
    except ApifyFetchError as exc:
        raise click.ClickException(
            f"{exc}\n\nThis was never tested against the live Apify actor — the field-name "
            "guesses in platforms/reddit/client.py may need a real look. Paste this error back "
            "and it can be fixed."
        )

    scored = score_player_mentions(posts, player_names)
    count = sync_sentiment(conn, scored)
    click.echo(f"Scanned {len(posts)} posts, scored sentiment for {count} mentioned players.")


@cli.command("buy-sell")
@click.argument("league_id")
@click.option("--limit", default=25)
def buy_sell_cmd(league_id: str, limit: int):
    """Flag buy-low/sell-high candidates league-wide (performance vs. market/sentiment divergence).

    With my_owner_id set in config/leagues.yaml, each result is tagged
    whether it's on your roster (an actual sell-high decision) or someone
    else's (a potential trade-for target)."""
    conn = db_module.get_connection()
    league = conn.execute("SELECT format FROM leagues WHERE league_id = ?", (league_id,)).fetchone()
    if not league:
        raise click.ClickException(f"League {league_id} hasn't been synced yet.")

    my_owner_id = _my_owner_id_for(league_id)
    results = find_buy_low_sell_high(conn, league_id, league["format"] or "redraft", limit=limit, my_owner_id=my_owner_id)
    if not results:
        click.echo(
            "No flags yet. This needs sync-weekly-points plus at least one of sync-ktc "
            "(dynasty/devy) / sync-fantasypros (redraft) / sync-reddit populated."
        )
        return

    if results[0].get("qb_mode"):
        click.echo(f"(KTC values: {results[0]['qb_mode']} — auto-detected from league roster settings)")
    if not my_owner_id:
        click.echo("(Set my_owner_id in config/leagues.yaml to see which of these are actually on your roster.)")

    for r in results:
        ownership = ""
        if r.get("owned_by_me") is True:
            ownership = " — ON YOUR ROSTER"
        elif r.get("owned_by_me") is False:
            ownership = " — not yours (trade target)"
        click.echo(f"\n{r['name']} ({r['position']}, {r['team']}){ownership}")
        click.echo(f"  Recent avg: {r['recent_avg']}  Season avg: {r['season_avg']}  Trend: {r['perf_trend']:+}")
        if r["market_delta"] is not None:
            click.echo(f"  Market delta: {r['market_delta']:+}")
        if r["sentiment"] is not None:
            click.echo(f"  Reddit sentiment: {r['sentiment']:+}")
        for flag, reason in r["flags"]:
            click.echo(f"  [{flag.upper().replace('_', '-')}] {reason}")


@cli.command("trade-analyze")
@click.argument("league_id")
@click.option("--side-a", "side_a", multiple=True, required=True, help="Player(s) side A sends. Repeatable.")
@click.option("--side-b", "side_b", multiple=True, required=True, help="Player(s) side B sends. Repeatable.")
def trade_analyze_cmd(league_id: str, side_a: tuple[str, ...], side_b: tuple[str, ...]):
    """Evaluate a proposed trade: KTC value for dynasty/devy, FantasyPros rank for redraft.

    Example: fantasy-assistant trade-analyze 1315737573154390016 --side-a "Player One" --side-b "Player Two" --side-b "Player Three"
    """
    conn = db_module.get_connection()
    try:
        result = analyze_trade(conn, league_id, list(side_a), list(side_b))
    except TradeAnalyzerError as exc:
        raise click.ClickException(str(exc))

    click.echo(f"League format: {result['league_format']}" + (f" ({result['qb_mode']})" if result["qb_mode"] else ""))
    click.echo(f"Metric: {result['metric']} ({'higher is better' if result['higher_is_better'] else 'lower is better'})")
    click.echo()

    def show_side(label, players, total):
        click.echo(f"Side {label} sends:")
        for p in players:
            click.echo(f"  {p['full_name']} ({p['position']}) — {result['metric']}: {p['metric']}")
        click.echo(f"  Total: {total}")
        click.echo()

    show_side("A", result["side_a"], result["total_a"])
    show_side("B", result["side_b"], result["total_b"])

    if result["unresolved"]:
        click.echo(f"Could not find data for: {', '.join(result['unresolved'])} (check spelling, or sync-ktc/sync-fantasypros first)")
        click.echo()

    if result["winner"] == "even":
        click.echo("Verdict: dead even.")
    else:
        click.echo(f"Verdict: Side {result['winner']} comes out ahead by {result['margin']} {result['metric']}.")


@cli.command("devy-add")
@click.argument("full_name")
@click.option("--position", default=None)
@click.option("--college", default=None)
@click.option("--notes", default=None)
def devy_add_cmd(full_name: str, position: str | None, college: str | None, notes: str | None):
    """Add a college prospect to the devy watchlist."""
    conn = db_module.get_connection()
    db_module.init_db(conn)
    prospect_id = devy_module.add_prospect(conn, full_name, position, college, notes)
    click.echo(f"Added #{prospect_id}: {full_name}")


@cli.command("devy-remove")
@click.argument("prospect_id", type=int)
def devy_remove_cmd(prospect_id: int):
    """Remove a prospect from the devy watchlist."""
    conn = db_module.get_connection()
    if devy_module.remove_prospect(conn, prospect_id):
        click.echo(f"Removed #{prospect_id}")
    else:
        click.echo(f"No prospect #{prospect_id} found.")


@cli.command("devy-list")
@click.option("--qb-mode", type=click.Choice(["1qb", "superflex"]), default="1qb", help="Which KTC devy values to show — QB value differs a lot between the two.")
def devy_list_cmd(qb_mode: str):
    """List the devy watchlist, with KTC devy value if synced (sync-ktc --format devy)."""
    conn = db_module.get_connection()
    db_module.init_db(conn)
    prospects = devy_module.list_prospects(conn, qb_mode=qb_mode)
    if not prospects:
        click.echo("Watchlist is empty. Add one with devy-add.")
        return
    click.echo(f"{'#':<4} {'Name':<25} {'Pos':<5} {'College':<20} {'KTC Val':>8} {'KTC Rk':>7}")
    for p in prospects:
        click.echo(
            f"{p['id']:<4} {p['full_name']:<25} {(p['position'] or ''):<5} {(p['college'] or ''):<20} "
            f"{p['ktc_value'] if p['ktc_value'] is not None else '-':>8} {p['ktc_rank'] if p['ktc_rank'] is not None else '-':>7}"
        )


@cli.command("owners")
@click.argument("league_id")
def owners_cmd(league_id: str):
    """List owners in a synced league — find your owner_id to set my_owner_id in config/leagues.yaml."""
    conn = db_module.get_connection()
    league = conn.execute("SELECT * FROM leagues WHERE league_id = ?", (league_id,)).fetchone()
    if not league:
        raise click.ClickException(f"League {league_id} hasn't been synced yet.")

    rows = conn.execute(
        "SELECT owner_id, display_name, team_name FROM owners WHERE league_id = ? ORDER BY display_name",
        (league_id,),
    ).fetchall()
    if not rows:
        click.echo("No owners synced yet.")
        return

    click.echo(f"{'Owner ID':<22} {'Display Name':<20} {'Team Name':<25}")
    for r in rows:
        click.echo(f"{r['owner_id']:<22} {(r['display_name'] or ''):<20} {(r['team_name'] or ''):<25}")


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
