# Fantasy Assistant

Local decision-support tool for Sleeper (and eventually ESPN) fantasy football
leagues — league sync, draft assistant, waiver/trade targeting, a buy-low/
sell-high engine, and devy prospect tracking. Runs entirely on your machine;
nothing is deployed anywhere.

## Status

**Phase 1 (league sync) is built for Sleeper.** Draft assistant, waiver/trade
targeting, buy-low/sell-high, devy tracking, and ESPN sync are not built yet —
see the task list in the repo for what's next.

> **Note on how this was built:** development happened in a sandboxed remote
> session with no outbound network access to `api.sleeper.app` (or ESPN,
> KeepTradeCut, FantasyPros, Reddit). The Sleeper sync logic is fully unit
> tested against mocked API responses shaped like Sleeper's real payloads, but
> it has **not been run against the live API yet**. Run the "Verify against
> the real Sleeper API" steps below on your machine before trusting the data.

## Setup

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Configure your leagues

Your league IDs are already filled in at `config/leagues.yaml`:

```yaml
sleeper:
  - league_id: "1389373095143284736"
    format: null
  - league_id: "1315737573154390016"
    format: null
  - league_id: "1313961246109761536"
    format: null

espn:
  league_id: "509682142"
  season: null
  private: null
```

Sleeper tells us redraft vs. dynasty automatically (`settings.type` in the
league object), so `format: null` is fine for those two — `sync-league` will
detect it and print what it found. **Devy isn't something Sleeper knows
about** — if one of your three leagues is the one where you stash college
prospects, edit its `format:` to `devy` in this file so later features (the
buy-low/sell-high engine, devy tracking) treat it correctly.

ESPN sync isn't built yet (Phase 2). When we get there, fill in `season`,
and if the league is private, `private: true` plus your `SWID`/`espn_s2`
cookies in a new `config/secrets.yaml` (gitignored) — I'll walk you through
grabbing those from your browser at that point.

## Run the tests (no network required)

```bash
pytest tests/ -v
```

These mock every Sleeper HTTP call, so they verify the sync logic (upserts,
format detection, taxi/starter/IR flags, the 24h player-cache TTL) without
hitting the real API.

## Verify against the real Sleeper API

This is the step that needs to happen on your machine, not in the sandbox
that built this:

```bash
fantasy-assistant sync-all
```

This will:
1. Pull the full Sleeper NFL player pool (cached 24h — a multi-MB one-time pull)
2. Sync each league in `config/leagues.yaml`: settings, rosters, owners, standings
3. Print the detected format for each league, so you can confirm and fill in `devy`

Then check standings for a specific league:

```bash
fantasy-assistant standings 1389373095143284736
```

If anything looks wrong (missing team names, wrong format detected, etc.),
let me know what you see and I'll fix it before we move to Phase 2.

## CLI reference

| Command | What it does |
|---|---|
| `fantasy-assistant init-db` | Create the SQLite DB and tables |
| `fantasy-assistant sync-players [--force]` | Refresh the cached NFL player pool |
| `fantasy-assistant sync-league LEAGUE_ID [--format redraft\|dynasty\|devy]` | Sync one league |
| `fantasy-assistant sync-all` | Sync players + every league in `config/leagues.yaml` |
| `fantasy-assistant standings LEAGUE_ID` | Print standings for a synced league |

## Data

Everything is cached locally in SQLite at `data/fantasy_assistant.db`
(gitignored — it's your data, not something to commit). Delete it any time
to start fresh; `init-db` will recreate the schema.

## Project layout

```
src/fantasy_assistant/
  cli.py              # command-line entrypoints
  config.py           # loads config/leagues.yaml (+ secrets.yaml)
  db.py                # SQLite connection/init
  schema.sql           # table definitions
  platforms/
    sleeper/
      client.py        # thin Sleeper API wrapper
      sync.py           # fetch + upsert logic
tests/
  test_sleeper_sync.py # sync logic tested against mocked API responses
```
