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

-- Per-source rankings, keyed so multiple sources can coexist per player
-- (e.g. Sleeper's search_rank alongside ESPN's standard draft rank) without
-- overwriting each other. overall_rank/position_rank/adp are each nullable
-- since not every source provides all three.
-- Per-week fantasy points, scoped to the league they were scored in (a
-- player's points depend on that league's scoring settings, so this isn't
-- shareable across leagues the way players/rankings are).
CREATE TABLE IF NOT EXISTS player_weekly_points (
    league_id TEXT NOT NULL REFERENCES leagues(league_id),
    player_id TEXT NOT NULL,
    week INTEGER NOT NULL,
    points REAL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (league_id, player_id, week)
);

-- Dynasty/devy market values from KeepTradeCut. Keyed by normalized name +
-- position rather than a player_id, since KTC has no shared ID with
-- Sleeper/ESPN — matched against them at query time the same way Sleeper
-- and ESPN are matched to each other (see platforms/matching.py).
--
-- qb_mode ('1qb' | 'superflex') is part of the key because QB value swings
-- dramatically between the two and KTC publishes separate rankings for
-- each — comparing a Superflex roster against 1QB-priced values (or vice
-- versa) would badly skew buy-low/sell-high. See analysis/roster_format.py.
CREATE TABLE IF NOT EXISTS market_values (
    source TEXT NOT NULL,            -- 'ktc'
    format TEXT NOT NULL,            -- 'dynasty' | 'devy'
    qb_mode TEXT NOT NULL DEFAULT '1qb',  -- '1qb' | 'superflex'
    normalized_name TEXT NOT NULL,
    full_name TEXT,
    position TEXT,
    team TEXT,
    value INTEGER,
    rank INTEGER,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (source, format, qb_mode, normalized_name, position)
);

-- Value on a *previous* sync, kept so we can compute "value delta over
-- time" as the spec asks for, without needing a full history table.
CREATE TABLE IF NOT EXISTS market_values_prior (
    source TEXT NOT NULL,
    format TEXT NOT NULL,
    qb_mode TEXT NOT NULL DEFAULT '1qb',
    normalized_name TEXT NOT NULL,
    position TEXT NOT NULL,
    value INTEGER,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (source, format, qb_mode, normalized_name, position)
);

CREATE TABLE IF NOT EXISTS market_values_cache_meta (
    source TEXT NOT NULL,
    format TEXT NOT NULL,
    qb_mode TEXT NOT NULL DEFAULT '1qb',
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (source, format, qb_mode)
);

-- Expert consensus rankings from a source with no shared player ID (same
-- name-keyed pattern as market_values). FantasyPros' free pages are redraft
-- consensus rankings only.
CREATE TABLE IF NOT EXISTS expert_rankings (
    source TEXT NOT NULL,            -- 'fantasypros'
    format TEXT NOT NULL,            -- 'redraft'
    normalized_name TEXT NOT NULL,
    full_name TEXT,
    position TEXT,
    team TEXT,
    overall_rank INTEGER,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (source, format, normalized_name, position)
);

-- Same "as of last sync" prior-snapshot pattern as market_values_prior, so
-- redraft leagues (which use FantasyPros rank movement instead of KTC value
-- movement) can compute a delta too.
CREATE TABLE IF NOT EXISTS expert_rankings_prior (
    source TEXT NOT NULL,
    format TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    position TEXT NOT NULL,
    overall_rank INTEGER,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (source, format, normalized_name, position)
);

CREATE TABLE IF NOT EXISTS expert_rankings_cache_meta (
    source TEXT NOT NULL,
    format TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (source, format)
);

-- Real average draft position from Fantasy Football Calculator's public
-- API — actual draft-pick data, unlike Sleeper's search_rank (an interest/
-- search-volume metric, not a true ADP). Used by the redraft draft board
-- in place of sleeper_search_rank. Keyed by normalized_name+position like
-- expert_rankings/market_values, since FFC has no shared player ID with
-- Sleeper/ESPN either. qb_mode splits 1QB vs Superflex ADP, same as
-- market_values, since FFC publishes separate lists for each.
CREATE TABLE IF NOT EXISTS draft_adp (
    source TEXT NOT NULL,            -- 'ffc'
    qb_mode TEXT NOT NULL,           -- '1qb' | 'superflex'
    normalized_name TEXT NOT NULL,
    full_name TEXT,
    position TEXT,
    team TEXT,
    overall_rank INTEGER,            -- 1-indexed rank derived from FFC's ADP sort order
    adp REAL,                        -- raw average draft position (e.g. 12.3)
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (source, qb_mode, normalized_name, position)
);

CREATE TABLE IF NOT EXISTS draft_adp_cache_meta (
    source TEXT NOT NULL,
    qb_mode TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (source, qb_mode)
);

-- Basic mention/sentiment counts from Reddit (see analysis/sentiment.py for
-- the scoring method — lexicon-based, not NLP).
CREATE TABLE IF NOT EXISTS player_sentiment (
    normalized_name TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'reddit',
    full_name TEXT,
    mention_count INTEGER,
    positive_count INTEGER,
    negative_count INTEGER,
    net_score REAL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (normalized_name, source)
);

-- Single-row cache guard for sync-reddit, same shape as players_cache_meta
-- (one global sync, not scoped per format/qb_mode like KTC/FantasyPros/FFC).
-- 24h TTL: sentiment doesn't need to refresh faster than that, and every
-- call costs against the free Apify budget.
CREATE TABLE IF NOT EXISTS reddit_sentiment_cache_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    fetched_at TEXT NOT NULL
);

-- Manual devy watchlist — college prospects not yet in any NFL data source.
CREATE TABLE IF NOT EXISTS devy_prospects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    position TEXT,
    college TEXT,
    notes TEXT,
    added_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS player_rankings (
    player_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    source TEXT NOT NULL,       -- 'sleeper_search_rank' | 'espn_standard_rank' | ...
    overall_rank INTEGER,
    position_rank INTEGER,
    adp REAL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (player_id, platform, source)
);
