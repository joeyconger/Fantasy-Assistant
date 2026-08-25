"""Runs the daily draft/market-data sync in a background thread inside the
web process, instead of a separate Railway cron service.

Why in-process: Railway Volumes can only be mounted to one service at a
time — a separate cron service can't share this app's SQLite file no
matter how it's configured (this was tried and confirmed broken: the web
service's data silently stopped being the same file the cron service wrote
to). Running the sync here means there's only ever one service and one
database connection path to reason about.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from . import cli as cli_module
from . import db as db_module

logger = logging.getLogger(__name__)

SYNC_HOUR_UTC = 13  # was "0 13 * * *" back when this ran as a Railway cron service


def _seconds_until_next_run(now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    target = now.replace(hour=SYNC_HOUR_UTC, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _current_nfl_season(now: datetime | None = None) -> int:
    """The NFL season is named for the year it starts in (a January/
    February game is still part of the *previous* year's season — e.g. the
    2026 season runs Sept 2026 through Feb 2027). March is used as the
    rollover cutoff since no NFL season activity (games or a following
    season's stats) happens that early."""
    now = now or datetime.now(timezone.utc)
    return now.year if now.month >= 3 else now.year - 1


def run_once() -> None:
    """Runs the full daily sync (draft rank/ADP, market values, nflverse
    advanced stats/snap counts). Logs failures instead of raising — a bad
    sync shouldn't take the web app down with it."""
    conn = db_module.get_connection()
    try:
        db_module.init_db(conn)
        cli_module._sync_rank_data(conn)
        cli_module._sync_market_data(conn)
        cli_module._sync_nflverse_data(conn, _current_nfl_season())
    except Exception:
        logger.exception("Daily auto-sync failed")
    finally:
        conn.close()


def _loop() -> None:
    while True:
        time.sleep(_seconds_until_next_run())
        run_once()


def start() -> None:
    """Starts the daily sync loop in a daemon background thread. Safe to
    call once at app startup — skipped automatically under pytest so test
    runs don't spawn a real background thread every time the app module is
    (re)imported."""
    if "PYTEST_CURRENT_TEST" in os.environ:
        return
    thread = threading.Thread(target=_loop, name="daily-sync", daemon=True)
    thread.start()
