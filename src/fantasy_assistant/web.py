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
from .platforms.espn.client import ESPNAPIError, ESPNAuthRequired, ESPNClient
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

    body = "".join(sections) or "<p>No leagues synced yet. Click Sync Now.</p>"

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Fantasy Assistant</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 1.5rem; }}
  th, td {{ text-align: left; padding: 0.4rem 0.8rem; border-bottom: 1px solid #ddd; }}
  .tag {{ font-size: 0.75rem; font-weight: normal; color: #666; }}
  button {{ padding: 0.5rem 1rem; cursor: pointer; }}
  .errors {{ background: #fdecea; border: 1px solid #f5c2c0; padding: 0.75rem 1rem; border-radius: 4px; margin-bottom: 1rem; }}
</style>
</head>
<body>
  <h1>Fantasy Assistant</h1>
  <form method="post" action="/sync">
    <button type="submit">Sync Now</button>
  </form>
  {error_html}
  {body}
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def dashboard(_user: str = Depends(require_auth), errors: str = Query(default="")):
    conn = db_module.get_connection()
    db_module.init_db(conn)
    try:
        error_list = [unquote(e) for e in errors.split("\x1f") if e]
        return _render_dashboard(conn, errors=error_list)
    finally:
        conn.close()


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
    finally:
        conn.close()

    if errors:
        error_param = "\x1f".join(quote(e) for e in errors)
        return RedirectResponse(url=f"/?errors={error_param}", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
