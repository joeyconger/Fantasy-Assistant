"""Tests the /settings web page: rendering, add/update/remove leagues, and
that it can't be used without auth."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from fantasy_assistant import league_sources
from fantasy_assistant.db import init_db

from test_web import _auth_header, web_app  # noqa: F401


def _conn(tmp_path):
    conn = sqlite3.connect(tmp_path / "test.db")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_settings_requires_auth(web_app):
    client = TestClient(web_app.app)
    resp = client.get("/settings")
    assert resp.status_code == 401


def test_settings_page_empty_state(web_app):
    client = TestClient(web_app.app)
    resp = client.get("/settings", headers=_auth_header("testuser", "testpass"))
    assert resp.status_code == 200
    assert "No leagues configured yet" in resp.text
    assert "Add League" in resp.text


def test_settings_page_lists_sources_and_escapes_names(web_app, tmp_path):
    conn = _conn(tmp_path)
    league_sources.add_source(conn, "L1", "sleeper", format_override="dynasty", my_owner_id="u1")
    conn.execute(
        "INSERT INTO leagues (league_id, platform, name) VALUES ('L1', 'sleeper', ?)",
        ("<script>alert(1)</script>",),
    )
    conn.commit()
    conn.close()

    client = TestClient(web_app.app)
    resp = client.get("/settings", headers=_auth_header("testuser", "testpass"))
    assert resp.status_code == 200
    assert "<script>alert(1)</script>" not in resp.text
    assert "&lt;script&gt;" in resp.text
    assert "L1" in resp.text


def test_settings_page_shows_owner_dropdown_when_synced(web_app, tmp_path):
    conn = _conn(tmp_path)
    league_sources.add_source(conn, "L1", "sleeper")
    conn.execute("INSERT INTO leagues (league_id, platform, name) VALUES ('L1', 'sleeper', 'Test League')")
    conn.execute("INSERT INTO owners (league_id, owner_id, display_name, team_name) VALUES ('L1', 'u1', 'joeyc', 'Team Joey')")
    conn.commit()
    conn.close()

    client = TestClient(web_app.app)
    resp = client.get("/settings", headers=_auth_header("testuser", "testpass"))
    assert resp.status_code == 200
    assert "<select name=\"my_owner_id\">" in resp.text
    assert "joeyc" in resp.text


def test_settings_add_league(web_app):
    client = TestClient(web_app.app, follow_redirects=False)
    resp = client.post(
        "/settings/add",
        headers=_auth_header("testuser", "testpass"),
        data={"league_id": "L1", "platform": "sleeper", "format_override": "", "my_owner_id": "", "espn_season": ""},
    )
    assert resp.status_code == 303
    assert "/settings?success=" in resp.headers["location"]

    follow = client.get(resp.headers["location"], headers=_auth_header("testuser", "testpass"))
    assert "L1" in follow.text


def test_settings_add_league_duplicate_shows_error(web_app):
    client = TestClient(web_app.app, follow_redirects=False)
    data = {"league_id": "L1", "platform": "sleeper", "format_override": "", "my_owner_id": "", "espn_season": ""}
    client.post("/settings/add", headers=_auth_header("testuser", "testpass"), data=data)
    resp = client.post("/settings/add", headers=_auth_header("testuser", "testpass"), data=data)
    assert resp.status_code == 303
    assert "/settings?error=" in resp.headers["location"]


def test_settings_add_league_bad_espn_season_shows_error(web_app):
    client = TestClient(web_app.app, follow_redirects=False)
    resp = client.post(
        "/settings/add",
        headers=_auth_header("testuser", "testpass"),
        data={"league_id": "E1", "platform": "espn", "format_override": "", "my_owner_id": "", "espn_season": "notanumber"},
    )
    assert resp.status_code == 303
    assert "/settings?error=" in resp.headers["location"]


def test_settings_update_league(web_app, tmp_path):
    conn = _conn(tmp_path)
    league_sources.add_source(conn, "L1", "sleeper")
    conn.close()

    client = TestClient(web_app.app, follow_redirects=False)
    resp = client.post(
        "/settings/update/L1",
        headers=_auth_header("testuser", "testpass"),
        data={"format_override": "dynasty", "my_owner_id": "u9", "espn_season": ""},
    )
    assert resp.status_code == 303
    assert "/settings?success=" in resp.headers["location"]

    conn = sqlite3.connect(tmp_path / "test.db")
    conn.row_factory = sqlite3.Row
    row = league_sources.get_source(conn, "L1")
    assert row["format_override"] == "dynasty"
    assert row["my_owner_id"] == "u9"


def test_settings_remove_league(web_app, tmp_path):
    conn = _conn(tmp_path)
    league_sources.add_source(conn, "L1", "sleeper")
    conn.close()

    client = TestClient(web_app.app, follow_redirects=False)
    resp = client.post("/settings/remove/L1", headers=_auth_header("testuser", "testpass"))
    assert resp.status_code == 303
    assert "/settings?success=" in resp.headers["location"]

    conn = sqlite3.connect(tmp_path / "test.db")
    conn.row_factory = sqlite3.Row
    assert league_sources.get_source(conn, "L1") is None


def test_settings_nav_link_present_on_dashboard(web_app, tmp_path):
    client = TestClient(web_app.app)
    resp = client.get("/", headers=_auth_header("testuser", "testpass"))
    assert resp.status_code == 200
    assert 'href="/settings"' in resp.text
