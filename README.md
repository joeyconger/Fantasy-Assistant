# Fantasy Assistant

Decision-support tool for Sleeper and ESPN fantasy football leagues — league
sync, draft assistant, waiver/trade targeting, a buy-low/sell-high engine,
and devy prospect tracking. Usable as a local CLI, or deployed (e.g. on
Railway) as a small shared web dashboard.

## Status

**Phase 1 (league sync) is done and confirmed working against the live
Sleeper API** — all three Sleeper leagues sync correctly:

| League | Format |
|---|---|
| BMFS (`1389373095143284736`) | redraft |
| Weekend Warriors (`1315737573154390016`) | dynasty |
| Dollars for Devys (`1313961246109761536`) | devy |

**ESPN sync is built but not yet verified against the live API** — same
situation Sleeper was in before you tested it: unit tested against mocked
responses shaped like ESPN's real payloads, but the ESPN API is unofficial
(no public docs, field names reverse-engineered), so it needs a real run to
confirm. See "Verify ESPN sync" below.

**Web dashboard is built and smoke-tested locally** (auth gating, HTML
rendering, the sync trigger all pass automated tests + a manual server run)
but **not yet deployed to Railway** — that requires your Railway account, so
it's the next thing for you to do. See "Deploy to Railway" below.

Not built yet: draft assistant, waiver/trade targeting, buy-low/sell-high
engine, devy tracking module, per-user accounts (the web dashboard is one
shared login for now — fine for you + a few trusted friends, not real
multi-user isolation).

## Setup

Requires Python 3.10+.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

(macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate`)

## Run the tests (no network required)

```powershell
pytest tests/ -v
```

Mocks every Sleeper and ESPN HTTP call — verifies upserts, format handling,
starter/taxi/IR flags, the 24h player-cache TTL, the 401→"private league"
error path, and that Sleeper/ESPN player IDs can't collide in the DB.

## Sync your leagues

```powershell
fantasy-assistant sync-all
```

Pulls the Sleeper player pool (cached 24h) + all three Sleeper leagues, then
attempts the ESPN league if `config/leagues.yaml` has a season set.

## Verify ESPN sync

Your ESPN league (`509682142`, season 2026) hasn't been tried against the
live API yet. Run:

```powershell
fantasy-assistant sync-espn
```

Two outcomes:

- **It works** — prints `Synced '<league name>' (509682142) — format: redraft`.
  Paste that back to me, and if the "Dollars for Devys"-style situation
  applies here too (i.e. this ESPN league is actually dynasty/devy), tell me
  and I'll set `format:` in `config/leagues.yaml` like we did for Sleeper.
- **It fails with an auth error** — the league is private. Do this:
  1. Copy `config/secrets.yaml.example` to `config/secrets.yaml`
  2. Log into fantasy.espn.com in your browser
  3. Open DevTools (F12) → Application tab (Chrome/Edge) or Storage tab
     (Firefox) → Cookies → `https://fantasy.espn.com`
  4. Copy the `SWID` cookie value (looks like `{ABC123-...}`) and the
     `espn_s2` cookie value (a long string) into `config/secrets.yaml`
  5. Run `fantasy-assistant sync-espn` again

`config/secrets.yaml` is gitignored — cookies never get committed.

## Check standings

```powershell
fantasy-assistant standings 1389373095143284736
```

Works for any synced league — Sleeper or ESPN — by league ID.

## CLI reference

| Command | What it does |
|---|---|
| `fantasy-assistant init-db` | Create the SQLite DB and tables |
| `fantasy-assistant sync-players [--force]` | Refresh the cached Sleeper NFL player pool |
| `fantasy-assistant sync-league LEAGUE_ID [--format redraft\|dynasty\|devy]` | Sync one Sleeper league |
| `fantasy-assistant sync-espn` | Sync the ESPN league from config |
| `fantasy-assistant sync-all` | Sync players + every Sleeper league + ESPN (if configured) |
| `fantasy-assistant standings LEAGUE_ID` | Print standings for a synced league |

Web dashboard (also runnable locally): `DASHBOARD_USER=x DASHBOARD_PASSWORD=y uvicorn fantasy_assistant.web:app --reload`

## Deploy to Railway

This gives you (and whoever you share the URL with) a web dashboard —
standings for every league plus a "Sync Now" button — instead of a terminal.
I can't do this part for you (it needs your Railway account), but it's a
handful of clicks:

1. **Go to [railway.app](https://railway.app)** and sign in (GitHub login is
   easiest since the repo's already there).
2. **New Project → Deploy from GitHub repo** → pick `joeyconger/Fantasy-Assistant`
   → select the `claude/fantasy-football-tool-xaf7ux` branch (or `main`,
   once this is merged). Railway will detect `railway.json` and use its
   build/start commands automatically — no config needed there.
3. **Add a Volume** (Railway dashboard → your service → Settings → Volumes →
   New Volume). Mount path: `/data`. This is what makes your synced data
   survive redeploys instead of resetting every time.
4. **Set environment variables** (Settings → Variables):
   | Variable | Value |
   |---|---|
   | `DASHBOARD_USER` | pick a username |
   | `DASHBOARD_PASSWORD` | pick a real password — this is the only thing stopping strangers from seeing your league data |
   | `DATABASE_PATH` | `/data/fantasy_assistant.db` |
   | `ESPN_SWID` | only if your ESPN league turned out to be private (see above) |
   | `ESPN_S2` | same |
5. **Generate a public URL**: Settings → Networking → Generate Domain.
6. Deploy should kick off automatically after step 2 (and again any time you
   push to that branch). Once it's up, visit the URL, log in with the
   username/password from step 4, and click **Sync Now**.

Paste back the deploy logs if anything fails, or the URL once it's working
and I'll sanity-check it.

## Data

Everything is cached in SQLite. Locally that's `data/fantasy_assistant.db`
(gitignored). Delete it any time to start fresh; `init-db` recreates the
schema. On Railway, set `DATABASE_PATH` to a path inside your mounted Volume
so it isn't wiped on redeploy (see above).

## Project layout

```
railway.json               # Railway build/start command config
.env.example                # env vars the web dashboard needs (copy to .env for local testing)
config/
  leagues.yaml             # your league IDs, formats, ESPN season
  secrets.yaml.example      # template for ESPN cookies (copy to secrets.yaml) — local use only
src/fantasy_assistant/
  cli.py                    # command-line entrypoints
  web.py                     # FastAPI dashboard (auth, standings view, sync trigger)
  config.py                 # loads config/leagues.yaml (+ secrets.yaml / env var overrides)
  db.py                     # SQLite connection/init (DATABASE_PATH env var override)
  schema.sql                 # table definitions (players keyed by player_id+platform,
                              # since Sleeper and ESPN assign independent IDs)
  platforms/
    sleeper/
      client.py             # thin Sleeper API wrapper
      sync.py                # fetch + upsert logic
    espn/
      client.py              # thin ESPN API wrapper (public + cookie auth)
      constants.py           # ESPN's proTeamId/positionId/lineupSlotId maps
      sync.py                 # fetch + upsert logic
tests/
  test_sleeper_sync.py      # sync logic tested against mocked API responses
  test_espn_sync.py          # same, for ESPN, incl. private-league auth path
  test_web.py                 # dashboard auth gating + HTML-escaping tests
```
