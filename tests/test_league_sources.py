import sqlite3

import pytest

from fantasy_assistant import league_sources
from fantasy_assistant.db import init_db


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_db(c)
    return c


def test_add_and_list_source(conn):
    league_sources.add_source(conn, "L1", "sleeper", format_override="dynasty", my_owner_id="u1")
    rows = league_sources.list_sources(conn)
    assert len(rows) == 1
    assert rows[0]["league_id"] == "L1"
    assert rows[0]["platform"] == "sleeper"
    assert rows[0]["format_override"] == "dynasty"
    assert rows[0]["my_owner_id"] == "u1"


def test_add_source_rejects_unknown_platform(conn):
    with pytest.raises(league_sources.LeagueSourceError):
        league_sources.add_source(conn, "L1", "yahoo")


def test_add_source_rejects_unknown_format(conn):
    with pytest.raises(league_sources.LeagueSourceError):
        league_sources.add_source(conn, "L1", "sleeper", format_override="keeper")


def test_add_source_rejects_duplicate_league_id(conn):
    league_sources.add_source(conn, "L1", "sleeper")
    with pytest.raises(league_sources.LeagueSourceError):
        league_sources.add_source(conn, "L1", "sleeper")


def test_add_source_rejects_second_espn_league(conn):
    league_sources.add_source(conn, "E1", "espn", espn_season=2026)
    with pytest.raises(league_sources.LeagueSourceError):
        league_sources.add_source(conn, "E2", "espn", espn_season=2026)


def test_update_source_overwrites_fields(conn):
    league_sources.add_source(conn, "L1", "sleeper", format_override="dynasty", my_owner_id="u1")
    ok = league_sources.update_source(conn, "L1", format_override="devy", my_owner_id="u2")
    assert ok is True
    row = league_sources.get_source(conn, "L1")
    assert row["format_override"] == "devy"
    assert row["my_owner_id"] == "u2"


def test_update_source_can_clear_fields_to_none(conn):
    league_sources.add_source(conn, "L1", "sleeper", format_override="dynasty", my_owner_id="u1")
    league_sources.update_source(conn, "L1", format_override=None, my_owner_id=None)
    row = league_sources.get_source(conn, "L1")
    assert row["format_override"] is None
    assert row["my_owner_id"] is None


def test_update_source_returns_false_for_unknown_league(conn):
    assert league_sources.update_source(conn, "NOPE", format_override="dynasty") is False


def test_update_source_rejects_unknown_format(conn):
    league_sources.add_source(conn, "L1", "sleeper")
    with pytest.raises(league_sources.LeagueSourceError):
        league_sources.update_source(conn, "L1", format_override="keeper")


def test_remove_source(conn):
    league_sources.add_source(conn, "L1", "sleeper")
    assert league_sources.remove_source(conn, "L1") is True
    assert league_sources.list_sources(conn) == []
    assert league_sources.remove_source(conn, "L1") is False


def test_remove_source_does_not_touch_synced_league_data(conn):
    league_sources.add_source(conn, "L1", "sleeper")
    conn.execute("INSERT INTO leagues (league_id, platform, name) VALUES ('L1', 'sleeper', 'Test League')")
    conn.commit()

    league_sources.remove_source(conn, "L1")

    assert conn.execute("SELECT * FROM leagues WHERE league_id = 'L1'").fetchone() is not None


def test_load_config_builds_sleeper_and_espn_leagues(conn):
    league_sources.add_source(conn, "S1", "sleeper", format_override="dynasty", my_owner_id="u1")
    league_sources.add_source(conn, "E1", "espn", format_override="redraft", my_owner_id="e1", espn_season=2026)

    app_config = league_sources.load_config(conn)

    assert len(app_config.sleeper_leagues) == 1
    assert app_config.sleeper_leagues[0].league_id == "S1"
    assert app_config.sleeper_leagues[0].format == "dynasty"
    assert app_config.sleeper_leagues[0].my_owner_id == "u1"

    assert app_config.espn_league is not None
    assert app_config.espn_league.league_id == "E1"
    assert app_config.espn_league.season == 2026
    assert app_config.espn_league.my_owner_id == "e1"


def test_load_config_espn_league_none_when_not_configured(conn):
    league_sources.add_source(conn, "S1", "sleeper")
    app_config = league_sources.load_config(conn)
    assert app_config.espn_league is None


def test_load_config_merges_espn_credentials_from_env(conn, monkeypatch):
    monkeypatch.setenv("ESPN_SWID", "{swid-value}")
    monkeypatch.setenv("ESPN_S2", "s2-value")
    league_sources.add_source(conn, "E1", "espn", espn_season=2026)

    app_config = league_sources.load_config(conn)

    assert app_config.espn_league.swid == "{swid-value}"
    assert app_config.espn_league.espn_s2 == "s2-value"


def test_migrate_yaml_if_needed_is_noop_when_table_already_has_rows(conn):
    league_sources.add_source(conn, "L1", "sleeper")
    count = league_sources.migrate_yaml_if_needed(conn)
    assert count == 0
    assert len(league_sources.list_sources(conn)) == 1


def test_migrate_yaml_if_needed_is_noop_when_no_yaml_file(conn, monkeypatch, tmp_path):
    from fantasy_assistant import config as config_module

    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", tmp_path / "does-not-exist.yaml")
    count = league_sources.migrate_yaml_if_needed(conn)
    assert count == 0
    assert league_sources.list_sources(conn) == []


def test_migrate_yaml_if_needed_imports_existing_yaml_setup(conn, monkeypatch, tmp_path):
    from fantasy_assistant import config as config_module

    yaml_path = tmp_path / "leagues.yaml"
    yaml_path.write_text(
        """
sleeper:
  - league_id: "111"
    format: dynasty
    my_owner_id: "u1"
  - league_id: "222"
espn:
  league_id: "333"
  season: 2026
  format: redraft
  my_owner_id: "e1"
"""
    )
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", yaml_path)

    count = league_sources.migrate_yaml_if_needed(conn)
    assert count == 3

    rows = {r["league_id"]: r for r in league_sources.list_sources(conn)}
    assert rows["111"]["platform"] == "sleeper"
    assert rows["111"]["format_override"] == "dynasty"
    assert rows["111"]["my_owner_id"] == "u1"
    assert rows["222"]["format_override"] is None
    assert rows["333"]["platform"] == "espn"
    assert rows["333"]["espn_season"] == 2026


def test_load_config_triggers_migration_when_table_empty(conn, monkeypatch, tmp_path):
    from fantasy_assistant import config as config_module

    yaml_path = tmp_path / "leagues.yaml"
    yaml_path.write_text('sleeper:\n  - league_id: "111"\n    my_owner_id: "u1"\n')
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", yaml_path)

    app_config = league_sources.load_config(conn)
    assert len(app_config.sleeper_leagues) == 1
    assert app_config.sleeper_leagues[0].league_id == "111"

    # Second call shouldn't re-migrate or duplicate anything.
    league_sources.load_config(conn)
    assert len(league_sources.list_sources(conn)) == 1
