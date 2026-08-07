"""SQLite connection + schema init. Kept dependency-free (stdlib sqlite3)."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# DATABASE_PATH lets a deployment (e.g. Railway, with a mounted volume) point
# the DB at persistent storage instead of the repo-relative local default.
DEFAULT_DB_PATH = Path(os.environ["DATABASE_PATH"]) if os.environ.get("DATABASE_PATH") else REPO_ROOT / "data" / "fantasy_assistant.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()
