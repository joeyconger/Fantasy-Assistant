"""Small FastAPI dashboard for deployment (e.g. Railway) so people without a
terminal can view standings and trigger a sync. Gated by HTTP Basic Auth —
this is a single shared login, not per-user accounts. Fine for "me and a few
friends I trust with the URL"; not a substitute for real auth if this ever
needs to isolate different people's data from each other.

Navigation is league-first, not tool-first: each league gets its own hub
(`/league/{id}`) that only links to the tools that make sense for its actual
rules — a dynasty league has no Draft Board (there's no startup draft to
prep for), only the devy league shows the devy watchlist, and every value
lookup (KTC vs FantasyPros, 1QB vs Superflex) is anchored to that league's
own detected format instead of asking you to pick it by hand.
"""

from __future__ import annotations

import html
import os
import secrets as secrets_module

from urllib.parse import quote, unquote

from fastapi import Depends, FastAPI, Form, HTTPException, Query, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from . import db as db_module
from . import devy as devy_module
from . import league_sources
from .analysis.buy_low_sell_high import find_buy_low_sell_high
from .analysis.draft_board import find_rank_inefficiencies
from .analysis.roster_format import detect_qb_mode
from .analysis.trade_analyzer import TradeAnalyzerError, analyze_trade
from .analysis.waiver_targets import top_trade_targets, top_waiver_adds
from .platforms.espn.client import ESPNAPIError, ESPNAuthRequired, ESPNClient
from .platforms.espn.rankings import sync_player_pool as espn_sync_player_pool
from .platforms.espn.sync import sync_league as espn_sync_league
from .platforms.sleeper.client import SleeperAPIError, SleeperClient
from .platforms.sleeper.sync import sync_league as sleeper_sync_league
from .platforms.sleeper.sync import sync_players
from .web_components import FORMAT_COLORS, PAGE_STYLE, collapsible, format_badge, gradient, player_cell, stat_tile, table_wrap

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


def _my_owner_id_for(conn, league_id: str) -> str | None:
    """Looks up my_owner_id for a league from league_sources, if set."""
    app_config = league_sources.load_config(conn)
    for league_cfg in app_config.sleeper_leagues:
        if league_cfg.league_id == league_id:
            return league_cfg.my_owner_id
    if app_config.espn_league and app_config.espn_league.league_id == league_id:
        return app_config.espn_league.my_owner_id
    return None


def _qb_mode_for_league(conn, league_id: str) -> str:
    row = conn.execute("SELECT roster_positions FROM leagues WHERE league_id = ?", (league_id,)).fetchone()
    return detect_qb_mode(row["roster_positions"] if row else None)


def _get_league_or_404(conn, league_id: str):
    league = conn.execute("SELECT * FROM leagues WHERE league_id = ?", (league_id,)).fetchone()
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    return league


def _nav_html(conn, current_league_id: str | None = None) -> str:
    """Top-level nav: Home + one tab per synced league, color-coded by
    format. Replaces the old flat tool-list nav — the league you're in is
    now the primary axis of navigation, not the tool."""
    leagues = conn.execute("SELECT league_id, name, format FROM leagues ORDER BY platform, name").fetchall()
    links = [f'<a class="{"active" if current_league_id is None else ""}" href="/">Home</a>']
    for l in leagues:
        active = l["league_id"] == current_league_id
        color = FORMAT_COLORS.get(l["format"], "#94a3b8")
        style = f'style="background:{gradient(color)}; border-color:transparent;"' if active else ""
        links.append(
            f'<a class="{"active" if active else ""}" {style} '
            f'href="/league/{quote(l["league_id"])}">{html.escape(l["name"] or l["league_id"])}</a>'
        )
    links.append(f'<a class="{"active" if current_league_id == "__settings__" else ""}" href="/settings">⚙ Settings</a>')
    return "".join(links)


def _tool_subnav(league_id: str, format_: str | None, current: str) -> str:
    """Tool tabs scoped to one league, filtered to what that league's format
    actually supports — a dynasty/devy league has no startup draft to prep
    for, so no Draft Board; only the devy league gets the watchlist."""
    format_ = format_ or "redraft"
    items = []
    if format_ == "redraft":
        items.append(("draft-board", "Draft Board"))
    items.append(("waivers", "Waivers/Trades"))
    items.append(("buy-sell", "Buy/Sell"))
    items.append(("trade-analyzer", "Trade Analyzer"))
    if format_ == "devy":
        items.append(("devy", "Devy Watchlist"))

    links = []
    for slug, label in items:
        active = slug == current
        style = 'style="background:linear-gradient(135deg, var(--accent), var(--accent-2)); border-color:transparent;"' if active else ""
        links.append(f'<a class="{"active" if active else ""}" {style} href="/league/{quote(league_id)}/{slug}">{label}</a>')
    return f'<div class="tabs">{"".join(links)}</div>'


def _page(title: str, body: str, nav_html: str | None = None) -> str:
    nav_html = nav_html if nav_html is not None else '<a class="active" href="/">Home</a>'
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fantasy Assistant — {html.escape(title)}</title>
<style>{PAGE_STYLE}</style>
</head>
<body>
  <header class="app-bar">
    <h1>🏈 Fantasy Assistant</h1>
    <nav>
      {nav_html}
    </nav>
  </header>
  {body}
</body>
</html>"""


def _standings_table_html(conn, league_id: str) -> str:
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
    row_html = "".join(
        f"<tr><td>{html.escape(str(r['team']))}</td><td>{r['wins']}</td><td>{r['losses']}</td>"
        f"<td>{r['ties']}</td><td>{(r['fpts'] or 0.0):.2f}</td><td>{(r['fpts_against'] or 0.0):.2f}</td></tr>"
        for r in rows
    )
    no_rosters_row = '<tr><td colspan="6">No rosters synced yet.</td></tr>'
    return table_wrap(
        f"<table><thead><tr><th>Team</th><th>W</th><th>L</th><th>T</th><th>PF</th><th>PA</th></tr></thead>"
        f"<tbody>{row_html or no_rosters_row}</tbody></table>"
    )


def _priority_items(conn, leagues) -> str:
    """Cross-league digest: the most actionable buy/sell flags and waiver
    adds, surfaced first — this is what makes '/' a decision-support view
    instead of just a standings page you have to interpret yourself."""
    flags = []
    adds = []
    for league in leagues:
        my_owner_id = _my_owner_id_for(conn, league["league_id"])
        for r in find_buy_low_sell_high(conn, league["league_id"], league["format"] or "redraft", limit=3, my_owner_id=my_owner_id):
            for flag, reason in r["flags"]:
                flags.append((league, r, flag, reason))
        for r in top_waiver_adds(conn, league["league_id"], limit=3, my_owner_id=my_owner_id):
            adds.append((league, r))

    if not flags and not adds:
        return (
            "<p class='empty'>No priorities yet — needs sync-weekly-points once games are being played, "
            "plus sync-ktc/sync-fantasypros for buy-sell flags.</p>"
        )

    cards = []
    for league, r, flag, reason in flags[:6]:
        cards.append(f"""
        <div class="card">
          {player_cell(r['name'], r['position'])}
          <div class="flag-{'buy' if flag == 'buy_low' else 'sell'}">{flag.upper().replace('_', '-')}</div>
          <p class="tag">{html.escape(reason)} · <a href="/league/{quote(league['league_id'])}">{format_badge(league['format'])} {html.escape(league['name'] or '')}</a></p>
        </div>
        """)
    for league, r in adds[:6]:
        cards.append(f"""
        <div class="card">
          {player_cell(r['name'], r['position'])}
          <div class="tag">Waiver add · recent avg {r['recent_avg']}</div>
          <p class="tag"><a href="/league/{quote(league['league_id'])}">{format_badge(league['format'])} {html.escape(league['name'] or '')}</a></p>
        </div>
        """)
    return "".join(cards)


def _render_dashboard(conn, errors: list[str] | None = None) -> str:
    leagues = conn.execute("SELECT * FROM leagues ORDER BY platform, name").fetchall()
    nav_html = _nav_html(conn)

    error_html = ""
    if errors:
        items = "".join(f"<li>{html.escape(e)}</li>" for e in errors)
        error_html = f'<div class="errors"><strong>Sync had problems:</strong><ul>{items}</ul></div>'

    sync_form = '<form method="post" action="/sync" onsubmit="this.querySelector(\'button\').disabled=true; this.querySelector(\'button\').textContent=\'Syncing…\';"><button type="submit">Sync Now</button></form>'

    if not leagues:
        return _page("Dashboard", sync_form + error_html + "<p class='empty'>No leagues synced yet. Click Sync Now.</p>", nav_html=nav_html)

    tiles = "".join(
        [
            stat_tile("Leagues", str(len(leagues))),
            stat_tile(
                "Platforms",
                ", ".join(sorted({l["platform"] for l in leagues})),
            ),
        ]
    )

    priorities = _priority_items(conn, leagues)

    sections = []
    for league in leagues:
        summary = (
            f"<span>{html.escape(str(league['name'] or league['league_id']))} "
            f"{format_badge(league['format'])} <span class='tag'>{html.escape(str(league['platform']))}</span></span>"
        )
        inner = (
            f"<p class='tag' style='margin:0 0 var(--space-2);'>"
            f"<a href='/league/{quote(league['league_id'])}'>Open league tools →</a></p>"
            f"{_standings_table_html(conn, league['league_id'])}"
        )
        sections.append(collapsible(summary, inner))

    body = f"""
    {tiles}
    <h2>This Week's Priorities</h2>
    {priorities}
    <h2>Standings</h2>
    {''.join(sections)}
    """
    return _page("Dashboard", sync_form + error_html + body, nav_html=nav_html)


@app.get("/", response_class=HTMLResponse)
def dashboard(_user: str = Depends(require_auth), errors: str = Query(default="")):
    conn = db_module.get_connection()
    db_module.init_db(conn)
    try:
        error_list = [unquote(e) for e in errors.split("\x1f") if e]
        return _render_dashboard(conn, errors=error_list)
    finally:
        conn.close()


@app.get("/league/{league_id}", response_class=HTMLResponse)
def league_hub_page(league_id: str, _user: str = Depends(require_auth)):
    conn = db_module.get_connection()
    db_module.init_db(conn)
    try:
        league = _get_league_or_404(conn, league_id)
        nav_html = _nav_html(conn, league_id)
        qb_mode = _qb_mode_for_league(conn, league_id)
        standings_html = _standings_table_html(conn, league_id)
    finally:
        conn.close()

    format_ = league["format"] or "redraft"
    subnav = _tool_subnav(league_id, format_, current="")

    body = f"""
    {subnav}
    <h2>{html.escape(str(league['name'] or league_id))}
      {format_badge(format_)} <span class="tag">{qb_mode.upper()}</span>
      <span class="tag">{html.escape(str(league['platform']))}</span>
    </h2>
    {standings_html}
    """
    return _page(str(league["name"] or league_id), body, nav_html=nav_html)


@app.get("/league/{league_id}/draft-board", response_class=HTMLResponse)
def draft_board_page(league_id: str, _user: str = Depends(require_auth), limit: int = Query(default=25)):
    conn = db_module.get_connection()
    db_module.init_db(conn)
    try:
        league = _get_league_or_404(conn, league_id)
        nav_html = _nav_html(conn, league_id)
        qb_mode = _qb_mode_for_league(conn, league_id)
        results = find_rank_inefficiencies(conn, limit=limit, qb_mode=qb_mode)
    finally:
        conn.close()

    subnav = _tool_subnav(league_id, league["format"] or "redraft", current="draft-board")

    if not results:
        note = ""
        if qb_mode == "superflex":
            note = "<p class='empty'>(Also possible: ESPN or FFC don't have Superflex-specific data yet.)</p>"
        body = f"<p class='empty'>No matched players with both market ADP and ESPN ranks yet. Run sync-ffc-adp and sync-rankings.</p>{note}"
    else:
        def _rank_cell(r):
            if r["position_relative"]:
                return f"{html.escape(r['position'])}{r['adp_rank']}", f"{html.escape(r['position'])}{r['espn_rank']}"
            return str(r["adp_rank"]), str(r["espn_rank"])

        def _row_html(r):
            adp_cell, espn_cell = _rank_cell(r)
            return (
                f"<tr><td>{player_cell(r['name'], r['position'])}</td>"
                f"<td>{adp_cell}</td><td>{espn_cell}</td><td>{r['delta']:+}</td>"
                f"<td>{html.escape(r['note'])}</td></tr>"
            )

        rows = "".join(_row_html(r) for r in results)
        rank_note = (
            "<p class='tag'>RB/WR/TE/K ranks shown as position rank (e.g. RB12), not overall — "
            "Superflex crowds QBs to the top of the overall list, which would otherwise make every "
            "other position look artificially crushed. QB still shows overall rank, since QB's overall-rank "
            "jump in Superflex *is* the real signal.</p>"
            if qb_mode == "superflex"
            else ""
        )
        body = rank_note + table_wrap(
            f"""<table><thead><tr><th>Player</th><th>Market ADP</th>
        <th>ESPN Rank ({qb_mode.upper()})</th><th>Delta</th><th>Note</th></tr></thead><tbody>{rows}</tbody></table>"""
        )

    return _page("Draft Board", f"{subnav}<h2>Draft Board — Rank Inefficiencies ({qb_mode.upper()})</h2>{body}", nav_html=nav_html)


@app.get("/league/{league_id}/waivers", response_class=HTMLResponse)
def waivers_page(league_id: str, _user: str = Depends(require_auth)):
    conn = db_module.get_connection()
    db_module.init_db(conn)
    try:
        league = _get_league_or_404(conn, league_id)
        nav_html = _nav_html(conn, league_id)
        my_owner_id = _my_owner_id_for(conn, league_id)
        adds = top_waiver_adds(conn, league_id, my_owner_id=my_owner_id)
        targets = top_trade_targets(conn, league_id, my_owner_id=my_owner_id)
    finally:
        conn.close()

    subnav = _tool_subnav(league_id, league["format"] or "redraft", current="waivers")

    personalization_note = (
        ""
        if my_owner_id
        else "<p class='empty'>Set my_owner_id in config/leagues.yaml to see which candidates fill your roster's needs.</p>"
    )

    def table(items, extra_col=None):
        if not items:
            return "<p class='empty'>No candidates yet — run sync-weekly-points and sync-rankings.</p>"
        header = "<th>Player</th><th>Team</th><th>Recent Avg</th><th>Trend</th><th>Rank</th><th>Need</th>"
        if extra_col:
            header += f"<th>{extra_col}</th>"
        rows = ""
        for r in items:
            need_badge = "<span class='badge' style='background:#16a34a;'>FILLS NEED</span>" if r.get("fills_need") else ""
            trend_class = "flag-buy" if r["trend"] > 0 else "flag-sell" if r["trend"] < 0 else ""
            row = (
                f"<td>{player_cell(r['name'], r['position'])}</td>"
                f"<td>{html.escape(r['team'] or '')}</td><td>{r['recent_avg']}</td>"
                f"<td class='{trend_class}'>{r['trend']:+}</td>"
                f"<td>{r['rank'] if r['rank'] is not None else '-'}</td><td>{need_badge}</td>"
            )
            if extra_col:
                row += f"<td>{html.escape(r.get('owned_by', ''))}</td>"
            rows += f"<tr>{row}</tr>"
        return table_wrap(f"<table><thead><tr>{header}</tr></thead><tbody>{rows}</tbody></table>")

    body = f"""
    {subnav}
    {personalization_note}
    <h2>Waiver Adds (available, trending up)</h2>
    {table(adds)}
    <h2>Trade Targets (rostered, trending up)</h2>
    {table(targets, extra_col="Owned By")}
    """
    return _page("Waivers/Trades", body, nav_html=nav_html)


@app.get("/league/{league_id}/buy-sell", response_class=HTMLResponse)
def buy_sell_page(league_id: str, _user: str = Depends(require_auth)):
    conn = db_module.get_connection()
    db_module.init_db(conn)
    try:
        league = _get_league_or_404(conn, league_id)
        nav_html = _nav_html(conn, league_id)
        my_owner_id = _my_owner_id_for(conn, league_id)
        results = find_buy_low_sell_high(conn, league_id, league["format"] or "redraft", my_owner_id=my_owner_id)
    finally:
        conn.close()

    subnav = _tool_subnav(league_id, league["format"] or "redraft", current="buy-sell")

    personalization_note = (
        ""
        if my_owner_id
        else "<p class='empty'>Set my_owner_id in config/leagues.yaml to see which of these are actually on your roster.</p>"
    )

    if not results:
        body = f"{personalization_note}<p class='empty'>No flags yet — needs sync-weekly-points plus sync-ktc/sync-fantasypros.</p>"
    else:
        cards = []
        for r in results:
            flag_html = "".join(
                f'<div class="flag-{("buy" if f == "buy_low" else "sell")}">'
                f'{f.upper().replace("_", "-")}: {html.escape(reason)}</div>'
                for f, reason in r["flags"]
            )
            ownership = ""
            if r.get("owned_by_me") is True:
                ownership = " <span class='tag'>ON YOUR ROSTER</span>"
            elif r.get("owned_by_me") is False:
                ownership = " <span class='tag'>trade target</span>"
            cards.append(f"""
            <div class="card">
              {player_cell(r['name'], r['position'])}
              <p class="tag">{html.escape(r['team'] or '')}{ownership}</p>
              <p>Recent avg: {r['recent_avg']} · Season avg: {r['season_avg']} · Trend: {r['perf_trend']:+}
              {f" · Market delta: {r['market_delta']:+}" if r['market_delta'] is not None else ""}
              {f" · Sentiment: {r['sentiment']:+}" if r['sentiment'] is not None else ""}</p>
              {flag_html}
            </div>
            """)
        body = personalization_note + "".join(cards)

    return _page("Buy/Sell", f"{subnav}<h2>Buy-Low / Sell-High</h2>{body}", nav_html=nav_html)


@app.get("/league/{league_id}/trade-analyzer", response_class=HTMLResponse)
def trade_analyzer_page(
    league_id: str,
    _user: str = Depends(require_auth),
    side_a: str = Query(default=""),
    side_b: str = Query(default=""),
):
    conn = db_module.get_connection()
    db_module.init_db(conn)
    try:
        league = _get_league_or_404(conn, league_id)
        nav_html = _nav_html(conn, league_id)

        result = None
        error = None
        side_a_names = [n.strip() for n in side_a.split("\n") if n.strip()]
        side_b_names = [n.strip() for n in side_b.split("\n") if n.strip()]
        if side_a_names and side_b_names:
            try:
                result = analyze_trade(conn, league_id, side_a_names, side_b_names)
            except TradeAnalyzerError as exc:
                error = str(exc)
    finally:
        conn.close()

    subnav = _tool_subnav(league_id, league["format"] or "redraft", current="trade-analyzer")

    form = f"""
    <form method="get" action="/league/{quote(league_id)}/trade-analyzer">
      <div style="display:flex; gap:1rem; flex-wrap:wrap;">
        <div style="flex:1; min-width:220px;">
          <label>Side A sends (one player per line)</label><br>
          <textarea name="side_a" rows="5" style="width:100%;">{html.escape(side_a)}</textarea>
        </div>
        <div style="flex:1; min-width:220px;">
          <label>Side B sends (one player per line)</label><br>
          <textarea name="side_b" rows="5" style="width:100%;">{html.escape(side_b)}</textarea>
        </div>
      </div>
      <button type="submit" style="margin-top:0.75rem;">Analyze</button>
    </form>
    """

    result_html = ""
    if error:
        result_html = f"<div class='errors'>{html.escape(error)}</div>"
    elif result:
        metric = result["metric"]

        def side_table(label, players, total):
            if not players:
                return f"<p class='empty'>Side {label}: nothing resolved.</p>"
            rows = "".join(
                f"<tr><td>{player_cell(p['full_name'], p['position'])}</td><td>{p['metric']}</td></tr>"
                for p in players
            )
            table_html = table_wrap(
                f"<table><thead><tr><th>Player</th><th>{metric.title()}</th></tr></thead><tbody>{rows}</tbody></table>"
            )
            return f"<h4>Side {label} sends</h4>{table_html}<p>Total: {total}</p>"

        unresolved_html = ""
        if result["unresolved"]:
            unresolved_html = (
                "<p class='empty'>Couldn't find data for: "
                + html.escape(", ".join(result["unresolved"]))
                + " (check spelling, or sync-ktc/sync-fantasypros first)</p>"
            )

        verdict = (
            "Dead even."
            if result["winner"] == "even"
            else f"Side {result['winner']} comes out ahead by {result['margin']} {metric}."
        )

        result_html = f"""
        <p>League format: {html.escape(result['league_format'])}{f" ({html.escape(result['qb_mode'])})" if result['qb_mode'] else ""}
        · Metric: {metric} ({'higher is better' if result['higher_is_better'] else 'lower is better'})</p>
        <div style="display:flex; gap:2rem; flex-wrap:wrap;">
          <div>{side_table('A', result['side_a'], result['total_a'])}</div>
          <div>{side_table('B', result['side_b'], result['total_b'])}</div>
        </div>
        {unresolved_html}
        <h3>{verdict}</h3>
        """

    return _page("Trade Analyzer", f"{subnav}<h2>Trade Analyzer</h2>{form}{result_html}", nav_html=nav_html)


@app.get("/league/{league_id}/devy", response_class=HTMLResponse)
def devy_page(league_id: str, _user: str = Depends(require_auth)):
    conn = db_module.get_connection()
    db_module.init_db(conn)
    try:
        league = _get_league_or_404(conn, league_id)
        nav_html = _nav_html(conn, league_id)
        qb_mode = _qb_mode_for_league(conn, league_id)
        prospects = devy_module.list_prospects(conn, qb_mode=qb_mode)
    finally:
        conn.close()

    subnav = _tool_subnav(league_id, league["format"] or "redraft", current="devy")

    if not prospects:
        body = "<p class='empty'>Watchlist is empty. Add prospects with the CLI: fantasy-assistant devy-add.</p>"
    else:
        rows = "".join(
            f"<tr><td>{player_cell(p['full_name'], p['position'])}</td>"
            f"<td>{html.escape(p['college'] or '')}</td><td>{html.escape(p['notes'] or '')}</td>"
            f"<td>{p['ktc_value'] if p['ktc_value'] is not None else '-'}</td>"
            f"<td>{p['ktc_rank'] if p['ktc_rank'] is not None else '-'}</td></tr>"
            for p in prospects
        )
        table_html = table_wrap(
            f"""<table><thead><tr><th>Name</th><th>College</th><th>Notes</th>
        <th>KTC Devy Value ({qb_mode.upper()})</th><th>KTC Devy Rank</th></tr></thead><tbody>{rows}</tbody></table>"""
        )
        body = f"""{table_html}
        <p class='empty'>Manage the watchlist via CLI: fantasy-assistant devy-add / devy-remove.</p>"""

    return _page("Devy Watchlist", f"{subnav}<h2>Devy Watchlist ({qb_mode.upper()})</h2>{body}", nav_html=nav_html)


_FORMAT_OPTIONS = [("", "Auto-detect"), ("redraft", "Redraft"), ("dynasty", "Dynasty"), ("devy", "Devy")]


def _format_select_html(name: str, current: str | None) -> str:
    options = "".join(
        f'<option value="{value}"{" selected" if (current or "") == value else ""}>{label}</option>'
        for value, label in _FORMAT_OPTIONS
    )
    return f'<select name="{name}">{options}</select>'


def _owner_field_html(conn, league_id: str, name: str, current: str | None) -> str:
    """A <select> of that league's synced owners if any exist, else a plain
    text input — matches how personalization already worked (run `owners`
    after syncing), just without the copy-paste round trip."""
    owner_rows = conn.execute(
        "SELECT owner_id, display_name, team_name FROM owners WHERE league_id = ? ORDER BY display_name",
        (league_id,),
    ).fetchall()
    if not owner_rows:
        return (
            f'<input type="text" name="{name}" value="{html.escape(current or "")}" placeholder="owner_id (sync this league first for a dropdown)">'
        )
    options = ['<option value="">— none —</option>']
    for row in owner_rows:
        label = row["display_name"] or row["team_name"] or row["owner_id"]
        selected = " selected" if row["owner_id"] == current else ""
        options.append(f'<option value="{html.escape(row["owner_id"])}"{selected}>{html.escape(label)}</option>')
    return f'<select name="{name}">{"".join(options)}</select>'


@app.get("/settings", response_class=HTMLResponse)
def settings_page(_user: str = Depends(require_auth), error: str = Query(default=""), success: str = Query(default="")):
    conn = db_module.get_connection()
    db_module.init_db(conn)
    try:
        nav_html = _nav_html(conn, current_league_id="__settings__")
        sources = league_sources.list_sources(conn)

        rows = []
        for src in sources:
            league_row = conn.execute("SELECT name FROM leagues WHERE league_id = ?", (src["league_id"],)).fetchone()
            league_name = (league_row["name"] if league_row else None) or src["league_id"]
            sync_note = "" if league_row else "<p class='empty' style='margin:0 0 var(--space-2);'>Not synced yet — sync it to unlock the owner dropdown.</p>"

            espn_season_field = (
                f'<label>ESPN season<br><input type="number" name="espn_season" value="{src["espn_season"] or ""}"></label>'
                if src["platform"] == "espn"
                else ""
            )
            rows.append(f"""
            <div class="card">
              <h3>{html.escape(league_name)} {format_badge(src["format_override"] or "auto")}
                <span class="tag">{html.escape(src["platform"])} · {html.escape(src["league_id"])}</span></h3>
              {sync_note}
              <form method="post" action="/settings/update/{quote(src['league_id'])}">
                <div style="display:flex; gap:1rem; flex-wrap:wrap; align-items:flex-end;">
                  <label>Format override<br>{_format_select_html("format_override", src["format_override"])}</label>
                  <label>My owner ID (personalization)<br>{_owner_field_html(conn, src["league_id"], "my_owner_id", src["my_owner_id"])}</label>
                  {espn_season_field}
                  <button type="submit">Save</button>
                </div>
              </form>
              <form method="post" action="/settings/remove/{quote(src['league_id'])}" style="margin-top:var(--space-2);"
                    onsubmit="return confirm('Stop syncing {html.escape(league_name)}? Already-synced data is kept.');">
                <button type="submit" class="btn" style="background:var(--sell);">Remove</button>
              </form>
            </div>
            """)

        add_form = f"""
        <div class="card">
          <h3>Add a league</h3>
          <form method="post" action="/settings/add">
            <div style="display:flex; gap:1rem; flex-wrap:wrap; align-items:flex-end;">
              <label>League ID<br><input type="text" name="league_id" required></label>
              <label>Platform<br>
                <select name="platform" id="add-league-platform" onchange="document.getElementById('add-league-season').style.display = this.value === 'espn' ? '' : 'none';">
                  <option value="sleeper">Sleeper</option>
                  <option value="espn">ESPN</option>
                </select>
              </label>
              <label>Format override<br>{_format_select_html("format_override", None)}</label>
              <label>My owner ID<br><input type="text" name="my_owner_id" placeholder="sync first, then set this below"></label>
              <label id="add-league-season" style="display:none;">ESPN season<br><input type="number" name="espn_season"></label>
              <button type="submit">Add League</button>
            </div>
          </form>
          <p class="tag" style="margin-top:var(--space-2);">Only one ESPN league is supported at a time. After adding,
          run Sync Now (or <code>sync-all</code>/<code>sync-espn</code>) to pull its data.</p>
        </div>
        """

    finally:
        conn.close()

    banner = ""
    if error:
        banner = f"<div class='errors'>{html.escape(unquote(error))}</div>"
    elif success:
        banner = f"<div class='card' style='border-color:var(--buy);'>{html.escape(unquote(success))}</div>"

    body = f"""
    {banner}
    <h2>Leagues</h2>
    {"".join(rows) if rows else "<p class='empty'>No leagues configured yet — add one below.</p>"}
    <h2>Add League</h2>
    {add_form}
    """
    return _page("Settings", body, nav_html=nav_html)


def _parse_optional_season(espn_season: str) -> int | None:
    espn_season = espn_season.strip()
    if not espn_season:
        return None
    try:
        return int(espn_season)
    except ValueError:
        raise league_sources.LeagueSourceError(f"ESPN season must be a number, got {espn_season!r}.")


@app.post("/settings/add")
def settings_add(
    _user: str = Depends(require_auth),
    league_id: str = Form(...),
    platform: str = Form(...),
    format_override: str = Form(default=""),
    my_owner_id: str = Form(default=""),
    espn_season: str = Form(default=""),
):
    conn = db_module.get_connection()
    db_module.init_db(conn)
    try:
        season = _parse_optional_season(espn_season)
        league_sources.add_source(
            conn,
            league_id.strip(),
            platform,
            format_override=format_override or None,
            my_owner_id=my_owner_id.strip() or None,
            espn_season=season,
        )
        redirect_url = f"/settings?success={quote(f'Added {platform} league {league_id.strip()}.')}"
    except league_sources.LeagueSourceError as exc:
        redirect_url = f"/settings?error={quote(str(exc))}"
    finally:
        conn.close()
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@app.post("/settings/update/{league_id}")
def settings_update(
    league_id: str,
    _user: str = Depends(require_auth),
    format_override: str = Form(default=""),
    my_owner_id: str = Form(default=""),
    espn_season: str = Form(default=""),
):
    conn = db_module.get_connection()
    db_module.init_db(conn)
    try:
        season = _parse_optional_season(espn_season)
        league_sources.update_source(
            conn, league_id, format_override=format_override or None, my_owner_id=my_owner_id.strip() or None, espn_season=season
        )
        redirect_url = "/settings?success=" + quote("Saved.")
    except league_sources.LeagueSourceError as exc:
        redirect_url = f"/settings?error={quote(str(exc))}"
    finally:
        conn.close()
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@app.post("/settings/remove/{league_id}")
def settings_remove(league_id: str, _user: str = Depends(require_auth)):
    conn = db_module.get_connection()
    db_module.init_db(conn)
    try:
        removed = league_sources.remove_source(conn, league_id)
    finally:
        conn.close()
    msg = "Removed." if removed else "That league wasn't tracked."
    return RedirectResponse(url=f"/settings?success={quote(msg)}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/sync")
def trigger_sync(_user: str = Depends(require_auth)):
    conn = db_module.get_connection()
    db_module.init_db(conn)
    errors: list[str] = []
    try:
        app_config = league_sources.load_config(conn)

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
