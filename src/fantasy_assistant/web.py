"""Small FastAPI dashboard for deployment (e.g. Railway) so people without a
terminal can view standings and trigger a sync. Gated by HTTP Basic Auth —
this is a single shared login, not per-user accounts. Fine for "me and a few
friends I trust with the URL"; not a substitute for real auth if this ever
needs to isolate different people's data from each other.
"""

from __future__ import annotations

import html
import os
import secrets as secrets_module

from urllib.parse import quote, unquote

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from . import config as config_module
from . import db as db_module
from . import devy as devy_module
from .analysis.buy_low_sell_high import find_buy_low_sell_high
from .analysis.draft_board import find_rank_inefficiencies
from .analysis.waiver_targets import top_trade_targets, top_waiver_adds
from .platforms.espn.client import ESPNAPIError, ESPNAuthRequired, ESPNClient
from .platforms.espn.rankings import sync_player_pool as espn_sync_player_pool
from .platforms.espn.sync import sync_league as espn_sync_league
from .platforms.sleeper.client import SleeperAPIError, SleeperClient
from .platforms.sleeper.sync import sync_league as sleeper_sync_league
from .platforms.sleeper.sync import sync_players

DASHBOARD_USER = os.environ.get("DASHBOARD_USER")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD")
if not DASHBOARD_USER or not DASHBOARD_PASSWORD:
    raise RuntimeError(
        "DASHBOARD_USER and DASHBOARD_PASSWORD must both be set before the web dashboard "
        "will start — it would otherwise be exposed with no login to whoever finds the URL."
    )

app = FastAPI(title="Fantasy Assistant")
security = HTTPBasic()


def require_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    user_ok = secrets_module.compare_digest(credentials.username, DASHBOARD_USER)
    pass_ok = secrets_module.compare_digest(credentials.password, DASHBOARD_PASSWORD)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@app.get("/health")
def health():
    return {"status": "ok"}


def _page(title: str, body: str, nav_extra: str = "") -> str:
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Fantasy Assistant — {html.escape(title)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 1.5rem; }}
  th, td {{ text-align: left; padding: 0.4rem 0.8rem; border-bottom: 1px solid #ddd; }}
  .tag {{ font-size: 0.75rem; font-weight: normal; color: #666; }}
  button {{ padding: 0.5rem 1rem; cursor: pointer; }}
  .errors {{ background: #fdecea; border: 1px solid #f5c2c0; padding: 0.75rem 1rem; border-radius: 4px; margin-bottom: 1rem; }}
  nav {{ margin-bottom: 1.5rem; }}
  nav a {{ margin-right: 1rem; }}
  .flag-buy {{ color: #1a7f37; font-weight: bold; }}
  .flag-sell {{ color: #b91c1c; font-weight: bold; }}
  .empty {{ color: #666; font-style: italic; }}
</style>
</head>
<body>
  <h1>Fantasy Assistant</h1>
  <nav>
    <a href="/">Standings</a>
    <a href="/draft-board">Draft Board</a>
    <a href="/waivers">Waivers/Trades</a>
    <a href="/buy-sell">Buy/Sell</a>
    <a href="/devy">Devy Watchlist</a>
  </nav>
  {nav_extra}
  {body}
</body>
</html>"""


def _league_select(conn, current: str | None, action_base: str) -> str:
    leagues = conn.execute("SELECT league_id, name, platform FROM leagues ORDER BY platform, name").fetchall()
    if not leagues:
        return "<p class='empty'>No leagues synced yet.</p>"
    options = "".join(
        f'<option value="{html.escape(l["league_id"])}" {"selected" if l["league_id"] == current else ""}>'
        f'{html.escape(l["name"] or l["league_id"])} ({html.escape(l["platform"])})</option>'
        for l in leagues
    )
    return f"""
    <form method="get" action="{action_base}" style="margin-bottom:1rem;">
      <select name="league_id" onchange="this.form.submit()">{options}</select>
      <noscript><button type="submit">Go</button></noscript>
    </form>
    """


def _render_dashboard(conn, errors: list[str] | None = None) -> str:
    leagues = conn.execute("SELECT * FROM leagues ORDER BY platform, name").fetchall()

    error_html = ""
    if errors:
        items = "".join(f"<li>{html.escape(e)}</li>" for e in errors)
        error_html = f'<div class="errors"><strong>Sync had problems:</strong><ul>{items}</ul></div>'

    sections = []
    for league in leagues:
        rows = conn.execute(
            """
            SELECT r.wins, r.losses, r.ties, r.fpts, r.fpts_against,
                   COALESCE(o.team_name, o.display_name, 'Roster ' || r.roster_id) AS team
            FROM rosters r
            LEFT JOIN owners o ON o.league_id = r.league_id AND o.owner_id = r.owner_id
            WHERE r.league_id = ?
            ORDER BY r.wins DESC, r.fpts DESC
            """,
            (league["league_id"],),
        ).fetchall()

        row_html = "".join(
            f"<tr><td>{html.escape(str(r['team']))}</td><td>{r['wins']}</td><td>{r['losses']}</td>"
            f"<td>{r['ties']}</td><td>{r['fpts']:.2f}</td><td>{r['fpts_against']:.2f}</td></tr>"
            for r in rows
        )
        sections.append(f"""
        <section>
          <h2>{html.escape(str(league['name'] or league['league_id']))}
            <span class="tag">{html.escape(str(league['platform']))} · {html.escape(str(league['format'] or ''))}</span>
          </h2>
          <table>
            <thead><tr><th>Team</th><th>W</th><th>L</th><th>T</th><th>PF</th><th>PA</th></tr></thead>
            <tbody>{row_html or '<tr><td colspan="6">No rosters synced yet.</td></tr>'}</tbody>
          </table>
        </section>
        """)

    body = "".join(sections) or "<p class='empty'>No leagues synced yet. Click Sync Now.</p>"
    sync_form = '<form method="post" action="/sync"><button type="submit">Sync Now</button></form>'
    return _page("Standings", sync_form + error_html + body)


@app.get("/", response_class=HTMLResponse)
def dashboard(_user: str = Depends(require_auth), errors: str = Query(default="")):
    conn = db_module.get_connection()
    db_module.init_db(conn)
    try:
        error_list = [unquote(e) for e in errors.split("\x1f") if e]
        return _render_dashboard(conn, errors=error_list)
    finally:
        conn.close()


@app.get("/draft-board", response_class=HTMLResponse)
def draft_board_page(
    _user: str = Depends(require_auth), limit: int = Query(default=25), qb_mode: str = Query(default="1qb")
):
    if qb_mode not in ("1qb", "superflex"):
        qb_mode = "1qb"
    conn = db_module.get_connection()
    db_module.init_db(conn)
    try:
        results = find_rank_inefficiencies(conn, limit=limit, qb_mode=qb_mode)
    finally:
        conn.close()

    toggle = "".join(
        f'<a href="/draft-board?qb_mode={m}" style="margin-right:1rem;{"font-weight:bold" if m == qb_mode else ""}">{m.upper()}</a>'
        for m in ("1qb", "superflex")
    )

    if not results:
        note = ""
        if qb_mode == "superflex":
            note = "<p class='empty'>(Also possible: ESPN's data doesn't have a confirmed Superflex-specific rank yet.)</p>"
        body = f"<p class='empty'>No matched players with ranks from both platforms yet. Run sync-rankings.</p>{note}"
    else:
        rows = "".join(
            f"<tr><td>{html.escape(r['name'])}</td><td>{html.escape(r['position'])}</td>"
            f"<td>{r['sleeper_rank']}</td><td>{r['espn_rank']}</td><td>{r['delta']:+}</td>"
            f"<td>{html.escape(r['note'])}</td></tr>"
            for r in results
        )
        body = f"""<table><thead><tr><th>Player</th><th>Pos</th><th>Sleeper Rank</th>
        <th>ESPN Rank ({qb_mode.upper()})</th><th>Delta</th><th>Note</th></tr></thead><tbody>{rows}</tbody></table>"""

    return _page("Draft Board", f"{toggle}<h2>Draft Board — Rank Inefficiencies</h2>{body}")


@app.get("/waivers", response_class=HTMLResponse)
def waivers_page(_user: str = Depends(require_auth), league_id: str | None = Query(default=None)):
    conn = db_module.get_connection()
    db_module.init_db(conn)
    try:
        if not league_id:
            row = conn.execute("SELECT league_id FROM leagues ORDER BY platform, name LIMIT 1").fetchone()
            league_id = row["league_id"] if row else None

        selector = _league_select(conn, league_id, "/waivers")
        if not league_id:
            return _page("Waivers/Trades", selector)

        adds = top_waiver_adds(conn, league_id)
        targets = top_trade_targets(conn, league_id)
    finally:
        conn.close()

    def table(items, extra_col=None):
        if not items:
            return "<p class='empty'>No candidates yet — run sync-weekly-points and sync-rankings.</p>"
        header = "<th>Player</th><th>Pos</th><th>Team</th><th>Recent Avg</th><th>Trend</th><th>Rank</th>"
        if extra_col:
            header += f"<th>{extra_col}</th>"
        rows = ""
        for r in items:
            row = (
                f"<td>{html.escape(r['name'])}</td><td>{html.escape(r['position'] or '')}</td>"
                f"<td>{html.escape(r['team'] or '')}</td><td>{r['recent_avg']}</td><td>{r['trend']:+}</td>"
                f"<td>{r['rank'] if r['rank'] is not None else '-'}</td>"
            )
            if extra_col:
                row += f"<td>{html.escape(r.get('owned_by', ''))}</td>"
            rows += f"<tr>{row}</tr>"
        return f"<table><thead><tr>{header}</tr></thead><tbody>{rows}</tbody></table>"

    body = f"""
    {selector}
    <h2>Waiver Adds (available, trending up)</h2>
    {table(adds)}
    <h2>Trade Targets (rostered, trending up)</h2>
    {table(targets, extra_col="Owned By")}
    """
    return _page("Waivers/Trades", body)


@app.get("/buy-sell", response_class=HTMLResponse)
def buy_sell_page(_user: str = Depends(require_auth), league_id: str | None = Query(default=None)):
    conn = db_module.get_connection()
    db_module.init_db(conn)
    try:
        if not league_id:
            row = conn.execute("SELECT league_id FROM leagues ORDER BY platform, name LIMIT 1").fetchone()
            league_id = row["league_id"] if row else None

        selector = _league_select(conn, league_id, "/buy-sell")
        if not league_id:
            return _page("Buy/Sell", selector)

        league = conn.execute("SELECT format FROM leagues WHERE league_id = ?", (league_id,)).fetchone()
        results = find_buy_low_sell_high(conn, league_id, league["format"] if league else "redraft")
    finally:
        conn.close()

    if not results:
        body = "<p class='empty'>No flags yet — needs sync-weekly-points plus sync-ktc/sync-fantasypros/sync-reddit.</p>"
    else:
        cards = []
        for r in results:
            flag_html = "".join(
                f'<div class="flag-{("buy" if f == "buy_low" else "sell")}">'
                f'{f.upper().replace("_", "-")}: {html.escape(reason)}</div>'
                for f, reason in r["flags"]
            )
            cards.append(f"""
            <section>
              <h3>{html.escape(r['name'])} ({html.escape(r['position'] or '')}, {html.escape(r['team'] or '')})</h3>
              <p>Recent avg: {r['recent_avg']} · Season avg: {r['season_avg']} · Trend: {r['perf_trend']:+}
              {f" · Market delta: {r['market_delta']:+}" if r['market_delta'] is not None else ""}
              {f" · Sentiment: {r['sentiment']:+}" if r['sentiment'] is not None else ""}</p>
              {flag_html}
            </section>
            """)
        body = "".join(cards)

    return _page("Buy/Sell", f"{selector}<h2>Buy-Low / Sell-High</h2>{body}")


@app.get("/devy", response_class=HTMLResponse)
def devy_page(_user: str = Depends(require_auth), qb_mode: str = Query(default="1qb")):
    if qb_mode not in ("1qb", "superflex"):
        qb_mode = "1qb"
    conn = db_module.get_connection()
    db_module.init_db(conn)
    try:
        prospects = devy_module.list_prospects(conn, qb_mode=qb_mode)
    finally:
        conn.close()

    toggle = "".join(
        f'<a href="/devy?qb_mode={m}" style="margin-right:1rem;{"font-weight:bold" if m == qb_mode else ""}">{m.upper()}</a>'
        for m in ("1qb", "superflex")
    )

    if not prospects:
        body = f"{toggle}<p class='empty'>Watchlist is empty. Add prospects with the CLI: fantasy-assistant devy-add.</p>"
    else:
        rows = "".join(
            f"<tr><td>{html.escape(p['full_name'])}</td><td>{html.escape(p['position'] or '')}</td>"
            f"<td>{html.escape(p['college'] or '')}</td><td>{html.escape(p['notes'] or '')}</td>"
            f"<td>{p['ktc_value'] if p['ktc_value'] is not None else '-'}</td>"
            f"<td>{p['ktc_rank'] if p['ktc_rank'] is not None else '-'}</td></tr>"
            for p in prospects
        )
        body = f"""{toggle}<table><thead><tr><th>Name</th><th>Pos</th><th>College</th><th>Notes</th>
        <th>KTC Devy Value ({qb_mode.upper()})</th><th>KTC Devy Rank</th></tr></thead><tbody>{rows}</tbody></table>
        <p class='empty'>Manage the watchlist via CLI: fantasy-assistant devy-add / devy-remove.</p>"""

    return _page("Devy Watchlist", f"<h2>Devy Watchlist</h2>{body}")


@app.post("/sync")
def trigger_sync(_user: str = Depends(require_auth)):
    conn = db_module.get_connection()
    db_module.init_db(conn)
    errors: list[str] = []
    try:
        app_config = config_module.load_config()

        sleeper_client = SleeperClient()
        sync_players(conn, sleeper_client)
        for league_cfg in app_config.sleeper_leagues:
            try:
                sleeper_sync_league(conn, sleeper_client, league_cfg.league_id, format_override=league_cfg.format)
            except SleeperAPIError as exc:
                errors.append(f"Sleeper {league_cfg.league_id}: {exc}")

        if app_config.espn_league and app_config.espn_league.season:
            espn_cfg = app_config.espn_league
            espn_client = ESPNClient(swid=espn_cfg.swid, espn_s2=espn_cfg.espn_s2)
            try:
                espn_sync_league(conn, espn_client, espn_cfg.league_id, espn_cfg.season, format_override=espn_cfg.format)
            except (ESPNAuthRequired, ESPNAPIError) as exc:
                errors.append(f"ESPN: {exc}")
            try:
                espn_sync_player_pool(conn, espn_client, espn_cfg.season)
            except (ESPNAuthRequired, ESPNAPIError) as exc:
                errors.append(f"ESPN rankings: {exc}")
    finally:
        conn.close()

    if errors:
        error_param = "\x1f".join(quote(e) for e in errors)
        return RedirectResponse(url=f"/?errors={error_param}", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
