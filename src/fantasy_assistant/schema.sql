-- Core schema for Phase 1 (league sync). Later phases add tables for
-- market values, sentiment, devy prospects, etc. as those features land.

CREATE TABLE IF NOT EXISTS leagues (
    league_id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,          -- 'sleeper' | 'espn'
    name TEXT,
    season TEXT,
    format TEXT,                     -- 'redraft' | 'dynasty' | 'devy'
    sleeper_type INTEGER,            -- raw Sleeper settings.type (0=redraft,1=keeper,2=dynasty)
    scoring_settings TEXT,           -- JSON blob, platform-native shape
    roster_positions TEXT,           -- JSON array
    total_rosters INTEGER,
    last_synced_at TEXT
);

CREATE TABLE IF NOT EXISTS owners (
    league_id TEXT NOT NULL REFERENCES leagues(league_id),
    owner_id TEXT NOT NULL,
    display_name TEXT,
    team_name TEXT,
    PRIMARY KEY (league_id, owner_id)
);

CREATE TABLE IF NOT EXISTS rosters (
    league_id TEXT NOT NULL REFERENCES leagues(league_id),
    roster_id TEXT NOT NULL,
    owner_id TEXT,
    wins INTEGER,
    losses INTEGER,
    ties INTEGER,
    fpts REAL,
    fpts_against REAL,
    waiver_position INTEGER,
    PRIMARY KEY (league_id, roster_id)
);

CREATE TABLE IF NOT EXISTS roster_players (
    league_id TEXT NOT NULL REFERENCES leagues(league_id),
    roster_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    is_starter INTEGER NOT NULL DEFAULT 0,
    is_taxi INTEGER NOT NULL DEFAULT 0,
    is_ir INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (league_id, roster_id, player_id)
);

-- player_id alone isn't unique across platforms — Sleeper and ESPN each
-- assign their own independent numeric IDs, so the same ID can refer to two
-- different real players. roster_players.player_id is disambiguated by
-- joining through leagues.platform (a roster only ever holds players from
-- its own platform).
CREATE TABLE IF NOT EXISTS players (
    player_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    full_name TEXT,
    position TEXT,
    team TEXT,
    status TEXT,
    age INTEGER,
    years_exp INTEGER,
    updated_at TEXT,
    PRIMARY KEY (player_id, platform)
);

-- Single-row table tracking when the full Sleeper player blob was last pulled,
-- so we don't re-fetch a multi-MB payload on every sync.
CREATE TABLE IF NOT EXISTS players_cache_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    fetched_at TEXT NOT NULL
);
