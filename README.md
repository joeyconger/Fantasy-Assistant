# Fantasy Assistant

Decision-support tool for Sleeper and ESPN fantasy football leagues — league
sync, a draft-value inefficiency finder, waiver/trade targeting, a buy-low/
sell-high engine, and devy prospect tracking. Usable as a local CLI, or
deployed (e.g. on Railway) as a small shared web dashboard.

## Status at a glance

| Piece | Status |
|---|---|
| Sleeper sync (leagues, rosters, standings, players) | ✅ **Verified live** — all 3 leagues sync correctly |
| ESPN league sync (rosters, standings) | ✅ **Verified live** — private league, cookies working |
| Web dashboard + Railway deploy | ✅ **Deployed and live**, shared login |
| Sleeper rank data (`search_rank`) | ✅ Verified live (part of the already-proven player sync) |
| ESPN full player-pool rankings/ADP | ⚠️ **Built, unit-tested, NOT run live** — new endpoint, different from the proven league endpoint |
| Draft board (rank inefficiency finder) | ⚠️ Logic verified correct via synthetic data + unit tests; depends on the ESPN piece above |
| Weekly performance trend (Sleeper matchups) | ⚠️ Built + tested; no real games played yet this season to sync (it's August) |
| Waiver/trade target identifier | ⚠️ Built + tested; same real-data caveat as above |
| KeepTradeCut (KTC) scraper | ❌ **UNVERIFIED — genuinely uncertain.** This environment cannot reach keeptradecut.com at all. The parser is a best-effort guess at their page structure with 3 fallback strategies; each strategy is unit-tested against synthetic HTML matching what it expects, but none of that proves it matches the real site. **Run `fantasy-assistant sync-ktc` first and expect it might fail.** |
| FantasyPros scraper | ❌ **Same caveat as KTC** — untested against the real site. |
| Reddit sentiment | ❌ **Cannot be tested at all yet** — needs a Reddit API app (client ID/secret) that only you can create, and this sandbox can't reach reddit.com anyway. Code is standard PRAW usage, structurally sound, never actually run. |
| X/Twitter | 🚫 **Skipped, deliberately.** See "Why X/Twitter was skipped" below. |
| Buy-low/sell-high engine | ⚠️ Combines the above signals; verified correct via synthetic data. Only as good as whichever of KTC/FantasyPros/Reddit actually works once you test them. |
| Devy watchlist | ✅ Fully built and tested (it's just a manual list — no external dependency) |

**Bottom line**: everything that only depends on Sleeper/ESPN (which this
session proved it can reach once, via your machine) is solid. Everything
that depends on KTC, FantasyPros, or Reddit is code I'm reasonably confident
in structurally, but have zero live confirmation on — this sandbox is
blocked from reaching any of those three sites. Treat those three as "try it
and tell me what breaks," not "should just work."

## Setup

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

47 tests, all passing as of this writing. Covers: Sleeper/ESPN sync upserts,
the private-league auth path, the players table's platform-scoped primary
key (prevents Sleeper/ESPN ID collisions), cross-platform name matching
(suffixes, punctuation, ambiguous-duplicate handling), the rank-inefficiency
engine, performance trend math, waiver/trade filtering, the buy-low/sell-high
flag logic, KTC/FantasyPros parser strategies against synthetic HTML, Reddit
sentiment scoring, the devy watchlist, and the web dashboard (auth gating,
XSS-escaping, missing-env-var fail-fast).

What tests can't cover: whether the *real* KTC/FantasyPros pages match the
HTML/JSON shapes the parsers assume, and whether Reddit's API behaves as
expected with real credentials. Only a live run answers that.

## Everyday commands

```powershell
fantasy-assistant sync-all          # Sleeper leagues + players + ESPN league + ESPN rankings
fantasy-assistant sync-rankings     # just the rank/ADP data (Sleeper + ESPN)
fantasy-assistant sync-weekly-points 1389373095143284736   # this week's + recent points (needs games played)
fantasy-assistant sync-ktc --format dynasty                # or --format devy
fantasy-assistant sync-fantasypros
fantasy-assistant sync-reddit       # needs REDDIT_CLIENT_ID/SECRET env vars first

fantasy-assistant standings 1389373095143284736
fantasy-assistant draft-board                                    # Sleeper vs ESPN rank divergence
fantasy-assistant waiver-targets 1389373095143284736              # available players trending up
fantasy-assistant trade-targets 1389373095143284736               # rostered players trending up
fantasy-assistant buy-sell 1389373095143284736                    # the composite engine

fantasy-assistant devy-add "Some College QB" --position QB --college "Ohio State" --notes "watch him"
fantasy-assistant devy-list
fantasy-assistant devy-remove 1
```

Full command list: `fantasy-assistant --help`.

## What to try first when you're back

1. **`fantasy-assistant sync-rankings`** — pulls Sleeper's rank data (proven
   to work, piggybacks on the already-verified player sync) and ESPN's
   player pool (the new, unverified endpoint). If ESPN's part fails, paste
   the error — it'll likely be a wrong field name I can fix once I see the
   real shape.
2. **`fantasy-assistant draft-board`** — once #1 works, this should show
   players where Sleeper and ESPN disagree on rank.
3. **`fantasy-assistant sync-ktc --format dynasty`** — the riskiest untested
   piece. If it raises `KTCParseError`, that's expected-possible, not a
   crisis — the error message itself explains what to send back (or you can
   view-source the page and paste the relevant `<script>` tag).
4. **`fantasy-assistant sync-fantasypros`** — same idea, `FantasyProsParseError`
   if the page structure differs from what's assumed.
5. **Reddit**: create a script app at https://www.reddit.com/prefs/apps
   (takes 2 minutes, just needs a Reddit account), set `REDDIT_CLIENT_ID`
   and `REDDIT_CLIENT_SECRET`, then `fantasy-assistant sync-reddit`.
6. Once weekly games start (this is being built in the preseason), run
   `sync-weekly-points` for each league — `waiver-targets`/`trade-targets`/
   `buy-sell` all need real weekly points data to say anything useful; right
   now they'll just report "no candidates" because there's no games yet.

## Why X/Twitter was skipped

Per the original scope: X's API is paid and priced for commercial use, not
a personal side project — not cost-effective here. The documented fallback
(RSS/Nitter mirrors of beat reporters) was also skipped: Nitter instances
are unreliable and frequently down, which would make that data source
flaky in a way that's worse than just not having it. Reddit is the sentiment
source; if this becomes a real gap in practice, revisit then rather than
building against infrastructure likely to break on its own.

## ESPN private league

Cookies are set as Railway env vars `ESPN_SWID`/`ESPN_S2` (confirmed
working). For local runs, copy `config/secrets.yaml.example` to
`config/secrets.yaml` and put them there instead — never commit that file
(it's gitignored).

## Deploy to Railway

Already done for the core app — this is for reference if you ever need to
redo it, or want to point a fresh Railway project at this repo.

1. **railway.app** → sign in → **New Project → Deploy from GitHub repo** →
   `joeyconger/Fantasy-Assistant`, the working branch.
2. **Volume** (Settings → Volumes → New Volume), mount path `/data`.
3. **Variables**: `DASHBOARD_USER`, `DASHBOARD_PASSWORD`, `DATABASE_PATH=/data/fantasy_assistant.db`,
   `ESPN_SWID`, `ESPN_S2`, and (once you set them up) `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET`.
4. **Networking → Generate Domain**.

Web dashboard pages: `/` (standings + Sync Now), `/draft-board`,
`/waivers`, `/buy-sell`, `/devy`. All behind the shared login. The devy
watchlist is view-only on the web — add/remove prospects via the CLI
(`devy-add`/`devy-remove`) since that's a local/one-time action, not
something that needed a web form yet.

## Data model notes

- **Cross-platform player identity**: Sleeper, ESPN, KTC, and FantasyPros
  all use their own independent player IDs with no shared key. Matching is
  done by normalized name + position (`platforms/matching.py`) — lowercased,
  punctuation stripped, suffixes like Jr./III removed. An ambiguous match
  (e.g. two same-named players at the same position on one side) is left
  unmatched rather than guessed, since a wrong pairing would silently
  corrupt every downstream feature.
- **KTC/FantasyPros storage**: since they have no player ID at all, their
  values are keyed directly by (normalized name, position) in their own
  tables (`market_values`, `expert_rankings`) rather than joined into the
  `players` table.
- **Value/rank deltas over time**: each sync rolls the previous values into
  a `_prior` table before overwriting, so "value 7 days ago" is really
  "value as of your last sync" — sync however often you want; the delta
  reflects whatever gap that is.
- **Not available from any source used here**: snap share, target share,
  red zone usage. Sleeper and ESPN's public APIs don't expose these. Only
  fantasy points scored (from Sleeper matchups) powers the performance-trend
  signal. Adding snap/target/RZ data would mean integrating an additional
  stats source (e.g. nflverse/nflfastR) — not in the original source list,
  flagged here as a real gap rather than silently ignored.
- **Roster construction needs / scoring-weighted best-player-available**:
  the draft board compares raw rank/ADP, not full season point projections
  weighted by your league's specific scoring settings — that would need a
  real projections data source this doesn't have. What's built is the
  "market inefficiency" half of the draft assistant ask, not the full
  scoring-aware BPA half.

## Project layout

```
railway.json                 # Railway build/start command config
.env.example                  # env vars the web dashboard/CLI can use
config/
  leagues.yaml               # league IDs, formats, ESPN season
  secrets.yaml.example        # template for ESPN cookies (local use only)
src/fantasy_assistant/
  cli.py                      # all CLI commands
  web.py                       # FastAPI dashboard
  devy.py                       # devy watchlist CRUD
  config.py                   # config/leagues.yaml + secrets.yaml/env loading
  db.py                        # SQLite connection/init
  schema.sql                    # all table definitions, heavily commented
  analysis/                   # cross-cutting logic (not platform-specific)
    draft_board.py             # Sleeper vs ESPN rank inefficiency
    performance_trend.py        # recent vs season points
    waiver_targets.py            # available/rostered players trending up
    buy_low_sell_high.py          # the composite engine
    sentiment.py                   # lexicon-based Reddit scoring
  platforms/
    matching.py                 # cross-platform name matching (shared)
    sleeper/                    # client, sync, weekly_points
    espn/                       # client, sync, rankings, constants
    ktc/                        # client (UNVERIFIED), sync
    fantasypros/                # client (UNVERIFIED), sync
    reddit/                     # client (UNTESTED - needs credentials), sync
tests/                        # 47 tests, see "Run the tests" above
```
