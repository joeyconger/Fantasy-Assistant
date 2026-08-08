"""Loads config/leagues.yaml and (optionally) config/secrets.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "leagues.yaml"
DEFAULT_SECRETS_PATH = REPO_ROOT / "config" / "secrets.yaml"


@dataclass
class SleeperLeagueConfig:
    league_id: str
    format: str | None = None  # redraft | dynasty | devy | None (auto-detect)
    my_owner_id: str | None = None  # your owner_id in this league — run `fantasy-assistant owners LEAGUE_ID` to find it


@dataclass
class EspnLeagueConfig:
    league_id: str
    season: int | None = None
    private: bool | None = None
    format: str | None = None  # redraft | dynasty | devy — ESPN gives no auto-detect signal
    swid: str | None = None
    espn_s2: str | None = None
    my_owner_id: str | None = None


@dataclass
class AppConfig:
    sleeper_leagues: list[SleeperLeagueConfig]
    espn_league: EspnLeagueConfig | None


def load_config(path: Path = DEFAULT_CONFIG_PATH, secrets_path: Path = DEFAULT_SECRETS_PATH) -> AppConfig:
    if not path.exists():
        raise FileNotFoundError(
            f"No config file at {path}. Copy config/leagues.yaml and fill in your league IDs."
        )

    raw = yaml.safe_load(path.read_text()) or {}

    sleeper_leagues = [
        SleeperLeagueConfig(
            league_id=str(entry["league_id"]),
            format=entry.get("format"),
            my_owner_id=str(entry["my_owner_id"]) if entry.get("my_owner_id") else None,
        )
        for entry in raw.get("sleeper", []) or []
    ]

    espn_raw = raw.get("espn") or {}
    espn_league = None
    if espn_raw.get("league_id"):
        secrets = {}
        if secrets_path.exists():
            secrets = yaml.safe_load(secrets_path.read_text()) or {}
        espn_secrets = secrets.get("espn", {})
        # ESPN_SWID/ESPN_S2 env vars (set on a host like Railway, which has no
        # local secrets.yaml) take priority over the gitignored local file.
        swid = os.environ.get("ESPN_SWID") or espn_secrets.get("swid")
        espn_s2 = os.environ.get("ESPN_S2") or espn_secrets.get("espn_s2")
        espn_league = EspnLeagueConfig(
            league_id=str(espn_raw["league_id"]),
            season=espn_raw.get("season"),
            private=espn_raw.get("private"),
            format=espn_raw.get("format"),
            swid=swid,
            espn_s2=espn_s2,
            my_owner_id=str(espn_raw["my_owner_id"]) if espn_raw.get("my_owner_id") else None,
        )

    return AppConfig(sleeper_leagues=sleeper_leagues, espn_league=espn_league)
