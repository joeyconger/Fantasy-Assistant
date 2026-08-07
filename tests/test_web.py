"""Tests the FastAPI dashboard: auth gating, rendering, and that team names
from external data can't inject HTML/script into the page.
"""

import base64
import importlib
import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from fantasy_assistant.db import init_db


@pytest.fixture
def web_app(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_USER", "testuser")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "testpass")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))

    import fantasy_assistant.db as db_mod
    import fantasy_assistant.web as web_mod

    importlib.reload(db_mod)
    importlib.reload(web_mod)
    return web_mod


def _auth_header(user: str, password: str) -> dict:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_health_requires_no_auth(web_app):
    client = TestClient(web_app.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_dashboard_requires_auth(web_app):
    client = TestClient(web_app.app)
    resp = client.get("/")
    assert resp.status_code == 401


def test_dashboard_rejects_wrong_credentials(web_app):
    client = TestClient(web_app.app)
    resp = client.get("/", headers=_auth_header("testuser", "wrongpass"))
    assert resp.status_code == 401


def test_dashboard_accepts_correct_credentials(web_app):
    client = TestClient(web_app.app)
    resp = client.get("/", headers=_auth_header("testuser", "testpass"))
    assert resp.status_code == 200
    assert "Fantasy Assistant" in resp.text


def test_dashboard_escapes_team_names(web_app, tmp_path):
    conn = sqlite3.connect(tmp_path / "test.db")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        "INSERT INTO leagues (league_id, platform, name, season, format, total_rosters) "
        "VALUES ('L1', 'sleeper', 'Test League', '2026', 'redraft', 1)"
    )
    conn.execute("INSERT INTO owners (league_id, owner_id, display_name, team_name) VALUES ('L1', 'u1', 'joeyc', ?)", ("<script>alert(1)</script>",))
    conn.execute(
        "INSERT INTO rosters (league_id, roster_id, owner_id, wins, losses, ties, fpts, fpts_against) "
        "VALUES ('L1', '1', 'u1', 3, 2, 0, 400.5, 380.25)"
    )
    conn.commit()
    conn.close()

    client = TestClient(web_app.app)
    resp = client.get("/", headers=_auth_header("testuser", "testpass"))
    assert resp.status_code == 200
    assert "<script>alert(1)</script>" not in resp.text
    assert "&lt;script&gt;" in resp.text
    assert "Test League" in resp.text


def test_missing_dashboard_credentials_raises_on_import(monkeypatch):
    monkeypatch.delenv("DASHBOARD_USER", raising=False)
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    import fantasy_assistant.web as web_mod

    with pytest.raises(RuntimeError):
        importlib.reload(web_mod)
