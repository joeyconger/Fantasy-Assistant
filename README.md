# Fantasy Assistant

Decision-support tool for Sleeper and ESPN fantasy football leagues — league
sync, a draft-value inefficiency finder, waiver/trade targeting personalized
to your roster's actual needs, a buy-low/sell-high engine, a trade analyzer,
and devy prospect tracking. Usable as a local CLI, or deployed (e.g. on
Railway) as a small shared web dashboard with a Sleeper/ESPN-app-style design
(position/format color coding, player cards, a priority-flagged home view).

## Status at a glance

| Piece | Status |
|---|---|
| Sleeper sync (leagues, rosters, standings, players) | ✅ **Verified live** — all 3 leagues sync correctly |
| ESPN league sync (rosters, standings) | ✅ **Verified live** — private league, cookies working |
| Web dashboard + Railway deploy | ✅ **Deployed and live**, shared login |
| Sleeper rank data (`search_rank`) | ✅ Verified live (part of the already-proven player sync). Still used by waiver-targets/roster-needs — but no longer by the draft board, see below. |
| ESPN full player-pool rankings/ADP | ✅ **Verified live** — 2918 players synced, correct rank/ADP order (Gibbs #1, Bijan #2, Puka #3 — matches real ADP). |
| — 1QB vs Superflex split | ✅ **Verified live** — ESPN's payload genuinely has a distinct Superflex rank type (unconfirmed until tested; turned out to exist). Confirmed meaningful, not noise: nearly every top-25 Superflex divergence is a QB valued much higher by ESPN in that mode, exactly the expected real-world pattern. |
| Fantasy Football Calculator (FFC) real ADP | ✅ **Verified live** — `platforms/ffc/`. Replaces Sleeper's `search_rank` on the draft board specifically, since search_rank turned out to be an interest/search-volume metric, not real ADP (a hyped rookie QB was ranking above an established veteran on search_rank alone). `sync-ffc-adp` confirmed working against the real API. |
| Draft board (rank inefficiency finder) | ✅ **Verified live** — re-anchored to FFC market ADP vs ESPN rank; also confirmed the defensive-position filter is real (not dead code) — IDP players like LBs were leaking into results pre-fix since Sleeper and ESPN happen to label that position identically. |
| Weekly performance trend (Sleeper matchups) | ⚠️ Built + tested; no real games played yet this season to sync (it's August) |
| Waiver/trade target identifier | ✅ Platform-awareness bug fixed and verified (Sleeper and ESPN both); still needs real weekly-points data to say anything — no games played yet this season |
| KeepTradeCut (KTC) scraper | ✅ **Verified live** — dynasty and devy, both 1QB and Superflex confirmed with real player data (Ja'Marr Chase, Bijan Robinson, Jeremiah Smith, Arch Manning, etc., sane values). Fixed a real bug found during verification: KTC nests both qb_modes per-record (`oneQBValues`/`superflexValues`), not flat top-level fields — the original `?format=2` URL guess was wrong and unnecessary, one page load has both. |
| — 1QB vs Superflex split | ✅ Verified — auto-detected from each league's roster settings (2+ QB slots or a Superflex/OP slot → superflex) for buy-sell; explicit `--qb-mode` flag for `sync-ktc`/`devy-list` since those aren't tied to one league. |
| FantasyPros scraper | ✅ **Verified live** — 511 redraft consensus rankings, correct order (Gibbs #1, Bijan #2, Chase #3 — matches actual current consensus), real names/positions/teams. Worked on the first real run, no fix needed. |
| Reddit sentiment | ⚠️ **UNVERIFIED** — re-enabled via Apify's Reddit Scraper actor (`platforms/reddit/`) after Reddit closed self-service API registration. See "Reddit sentiment via Apify" below for the full story, including the ToS tradeoff. Needs `APIFY_API_TOKEN` + a live `sync-reddit` run to confirm. Buy-low/sell-high already treats sentiment as optional, so nothing else depends on this working. |
| X/Twitter | 🚫 **Skipped, deliberately.** See "Why X/Twitter was skipped" below. |
| Buy-low/sell-high engine | ⚠️ Combines the above signals correctly (verified via synthetic data + now real KTC + FantasyPros data). Still needs weekly-points data to say anything for a given league — no games played yet this season. |
| Devy watchlist | ✅ Fully built and tested (it's just a manual list — no external dependency), and now cross-references real KTC devy values |

**Bottom line**: every data source except X/Twitter (skipped) and Reddit
(re-enabled via Apify, not yet live-verified) is verified live — Sleeper,
ESPN (league sync + player-pool rankings, both qb_modes), KTC, FantasyPros,
and FFC. Phase A (functional gaps) is complete. Phase B (design polish +
personalization + trade analyzer) is also complete. What's left is real
weekly-points data (just needs the season to start) and live-verifying
`sync-reddit`.

## Phase B: design polish + features — complete

Everything from the "make it feel like a real app, not bare-bones" pass:

- **Design system** (`web_components.py`): CSS custom properties for a
  light/dark (`prefers-color-scheme`) theme, a shared color scale for
  positions (QB/RB/WR/TE/K/DEF) and a separate one for league formats
  (redraft/dynasty/devy) so the two are never visually confused, plus small
  HTML-generating helpers (`player_cell`, `avatar`, `position_badge`,
  `format_badge`, `stat_tile`, `table_wrap`) reused across every page. All
  user-controlled strings (names, notes, etc.) are HTML-escaped —
  covered by `tests/test_web_components.py`.
- **Hand-rolled CSS, not a component library**: considered shadcn/ui, but
  that implies a React/Node SPA rewrite of an app that's otherwise a simple
  Python server-rendered tool with no complex client state — not worth the
  migration risk or the departure from "small deployable chunks." See the
  docstring at the top of `web_components.py`.
- **Home dashboard rebuilt as a priority view**: instead of just standings,
  `/` now leads with a cross-league "This Week's Priorities" digest (top
  buy/sell flags + waiver adds across every synced league) via
  `_priority_items`, with stat tiles up top and standings below.
- **League switcher**: color-coded tabs by format (redraft/dynasty/devy)
  instead of a plain `<select>` dropdown, so it's obvious at a glance which
  league context you're in.
- **Mobile responsive**: nav and league-tabs wrap/scroll horizontally on
  narrow viewports, tables scroll inside their own container instead of
  blowing out the page width, and a `@media (max-width: 640px)` block
  shrinks font sizes/padding.
- **Personalization** (`my_owner_id` in `config/leagues.yaml`): waiver
  adds and buy-sell flags now tag whether a candidate fills one of your
  roster's actual weak positions (`analysis/roster_needs.py`), and trade
  targets exclude your own roster.
- **Trade analyzer** (`analysis/trade_analyzer.py`, `/trade-analyzer`):
  evaluate a proposed trade by KTC value (dynasty/devy) or FantasyPros rank
  (redraft), reporting unresolved player names explicitly rather than
  silently dropping them.

No new environment variables or schema changes for any of this — it's all
additive on top of the existing tables, so it's safe to deploy straight to
the live Railway instance.

## Phase C: league-first navigation — complete

Restructured navigation around leagues instead of tools: each league now
gets its own hub page (`/league/{league_id}`) that only shows the tools its
actual rules support, instead of one flat tool list with a league picker
bolted onto each page.

- **BMFS** (redraft, Sleeper, 1QB) and **Lads** (redraft, ESPN, confirmed
  Superflex): Draft Board, Waivers/Trades, Buy/Sell (FantasyPros-anchored),
  Trade Analyzer — same tool set, each locked to its own qb_mode.
- **Weekend Warriors** (dynasty, Sleeper): Waivers/Trades, Buy/Sell
  (KTC-anchored), Trade Analyzer — no Draft Board, since there's no startup
  draft to prep for in an ongoing dynasty league.
- **Dollars for Devys** (devy, Sleeper, Superflex): Waivers/Trades, Buy/Sell,
  Trade Analyzer, plus the **Devy Watchlist** — the only league that gets it,
  since it's the only one that's actually devy.

Every tool auto-locks to its league's real settings instead of asking you to
pick: `qb_mode` (1QB vs Superflex) is read live from that league's synced
`roster_positions` (`analysis/roster_format.detect_qb_mode`) rather than a
manual toggle, and KTC vs FantasyPros anchoring already followed from
format. The old flat routes (`/draft-board`, `/waivers`, `/buy-sell`,
`/trade-analyzer`, `/devy`) are gone — everything lives under
`/league/{league_id}/...` now. Top nav is Home + one tab per league;
each league hub has its own sub-nav for just its applicable tools.

Also fixed while touching this: standings would 500 if `fpts`/`fpts_against`
were still NULL (a freshly-synced league before any games are played) —
`_standings_table_html` now treats NULL as 0.0 instead of crashing.

No new environment variables or schema changes.

## Draft Board fixes: defensive players + Superflex QB-crowding

Found from a real live run on the "Lads" (ESPN, Superflex) league: RBs like
James Conner and Tyler Allgeier were showing enormous fake deltas (Sleeper
rank ~90 vs ESPN Superflex rank ~290, a "-199" swing) that didn't reflect
any real disagreement.

- **Root cause**: Sleeper's `search_rank` has no Superflex-aware ordering
  (it's one list regardless of qb_mode — see `roster_format.py`), but
  ESPN's Superflex rank type genuinely re-sorts its whole pool around
  Superflex QB scarcity, so every QB jumps toward the top of the overall
  list. That mechanically drags every RB/WR/TE/K down in *overall* rank
  even when their value relative to other players at their own position
  barely moved — comparing raw overall rank in that situation was mostly
  measuring "how many QBs ESPN now ranks above this guy," not a real market
  gap.
- **Fix**: in Superflex mode, RB/WR/TE/K deltas now compare **within-position
  rank** (RB vs RB, WR vs WR, ...) instead of overall rank — stable across
  formats since Superflex reshuffles QBs against everyone else, not RBs
  against other RBs. QB deliberately keeps using overall rank: that jump
  *is* the real Superflex signal this tool exists to surface. The web table
  labels these rows "RB12"-style instead of a bare number so it's obvious
  which metric is being compared, with a note explaining why.
- **Also**: team defenses and any IDP positions (none of these leagues play
  IDP) are now excluded from the draft board outright — D/ST valuation
  doesn't belong in a skill-position market-inefficiency tool.

`analysis/draft_board.py` and `tests/test_analysis.py` — see
`test_find_rank_inefficiencies_superflex_uses_position_rank_for_non_qb` and
`test_find_rank_inefficiencies_excludes_defensive_positions`.

## Draft Board: real ADP (FFC) instead of Sleeper's search_rank

Found from another real live run: the draft board showed a hyped rookie QB
(Fernando Mendoza) ranked well above an established veteran (Baker Mayfield)
on the "Sleeper" side — 39 vs 64. That wasn't a bug in the matching logic;
it's genuinely what Sleeper's `search_rank` says. The problem is what
`search_rank` actually measures: it's Sleeper's own interest/search-volume
ranking (how much people are searching/interacting with a player on
Sleeper), not a real average draft position. A hyped rookie can spike that
metric from pure attention, especially on Sleeper's dynasty-heavy userbase,
without reflecting real redraft startable value.

**Fix**: swapped the "market" side of the draft board from Sleeper's
`search_rank` to real ADP from Fantasy Football Calculator's free public
API (`platforms/ffc/`) — actual aggregated draft-pick data, not an interest
metric. `sync-ffc-adp --qb-mode 1qb` hits FFC's `ppr` ADP list, `--qb-mode
superflex` hits their `2qb` list. Values are matched into the draft board
by normalized name+position (FFC has no shared player ID with Sleeper/ESPN
either), the same way KTC/FantasyPros are — see the new `draft_adp` table.
Dynasty startup ADP is explicitly out of scope (disregarded by decision);
this only covers redraft.

The web/CLI column previously labeled "Sleeper Rank" is now "Market ADP" /
"ADP" — an honest label, since this isn't Sleeper-specific data anymore.

**Verified live**: `sync-ffc-adp` confirmed working against the real API
for both qb_modes. Re-ran `draft-board` afterward and confirmed it now
compares real market ADP against ESPN — and confirmed the defensive-position
filter (added in the previous fix) is genuinely necessary, not dead code:
before pulling this fix, the board was showing LB players (TJ Watt, Micah
Parsons, Nik Bonitto, Byron Young) mixed in with skill positions, since
Sleeper and ESPN happen to label individual defensive positions identically
even though team defenses (DEF vs D/ST) never collide.

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

122 tests, all passing as of this writing. Covers: Sleeper/ESPN sync upserts,
the private-league auth path, the players table's platform-scoped primary
key (prevents Sleeper/ESPN ID collisions), cross-platform name matching
(suffixes, punctuation, ambiguous-duplicate handling), the rank-inefficiency
engine (including the Superflex QB-crowding position-relative fix and FFC
ADP integration), performance trend math, waiver/trade filtering, the
buy-low/sell-high flag logic, KTC/FantasyPros/FFC parser strategies against
synthetic HTML/JSON, the Apify-based Reddit client's defensive field
extraction, lexicon-based sentiment scoring, the devy watchlist,
roster-needs gap analysis, the trade analyzer, the design-system component
helpers (XSS-escaping), and the web dashboard (auth gating, XSS-escaping,
missing-env-var fail-fast).

What tests can't cover: whether the *real* KTC/FantasyPros pages, FFC's ADP
API, or Apify's Reddit Scraper actor match the shapes the parsers assume.
Only a live run answers that.

## Everyday commands

```powershell
fantasy-assistant sync-all          # Sleeper leagues + players + ESPN league + ESPN rankings
fantasy-assistant sync-rankings     # just the rank/ADP data (Sleeper + ESPN)
fantasy-assistant sync-weekly-points 1389373095143284736   # this week's + recent points (needs games played)
fantasy-assistant sync-ktc --format dynasty --qb-mode 1qb   # or --format devy, --qb-mode superflex
fantasy-assistant sync-fantasypros
fantasy-assistant sync-ffc-adp --qb-mode 1qb        # or --qb-mode superflex; real ADP for the draft board
fantasy-assistant sync-reddit       # needs APIFY_API_TOKEN; defaults to r/DynastyFF, Player Discussion/News flairs

fantasy-assistant standings 1389373095143284736
fantasy-assistant owners 1389373095143284736                      # find your owner_id for personalization
fantasy-assistant draft-board                                    # market ADP (FFC) vs ESPN rank divergence
fantasy-assistant waiver-targets 1389373095143284736              # available players trending up
fantasy-assistant trade-targets 1389373095143284736               # rostered players trending up
fantasy-assistant buy-sell 1389373095143284736                    # the composite engine (auto-detects 1QB/Superflex)
fantasy-assistant trade-analyze 1315737573154390016 --side-a "Player One" --side-b "Player Two" --side-b "Player Three"

fantasy-assistant devy-add "Some College QB" --position QB --college "Ohio State" --notes "watch him"
fantasy-assistant devy-list --qb-mode 1qb    # or --qb-mode superflex
fantasy-assistant devy-remove 1
```

Full command list: `fantasy-assistant --help`.

**Personalization**: waiver-targets/trade-targets/buy-sell are league-wide
by default (useful, but you have to judge fit yourself). Run
`fantasy-assistant owners LEAGUE_ID` to find your `owner_id`, set it as
`my_owner_id` in `config/leagues.yaml` for that league, and: trade-targets
excludes players you already own, both commands tag candidates that fill
one of your roster's actual weak positions (`analysis/roster_needs.py` —
compares your average rank per position against the league average), and
buy-sell tags whether each flagged player is on your roster (an actual
sell-high decision) or someone else's (a trade-for target). Leave it unset
and everything still works exactly as before, unpersonalized.

**Trade analyzer**: evaluates a proposed trade using KTC value (dynasty/devy,
auto-detects 1QB/Superflex from the league) or FantasyPros rank (redraft).
Player names not found in the synced data are reported as unresolved, not
silently dropped or valued at zero.

**1QB vs Superflex**: `buy-sell` auto-detects which one your league actually
is from its synced roster settings (2+ QB slots, or a Superflex/OP slot) —
no flag needed. `sync-ktc` and `devy-list` need `--qb-mode` explicitly since
they're not tied to one specific league. Run `sync-ktc` once for each mode
you actually need (e.g. `1qb` for Weekend Warriors, `superflex` only if
Dollars for Devys turns out to be superflex — check by running `buy-sell`
on it and seeing which mode it reports).

## Phase A: functional gaps — complete

All done and verified live: waiver/trade/buy-sell platform-awareness bug
fixed, KTC (dynasty + devy, both qb_modes), FantasyPros, and ESPN
player-pool rankings (both qb_modes, including confirming ESPN genuinely
has distinct Superflex data). Reddit sentiment was originally out of scope
by decision, then re-enabled via Apify once a cheap third-party option was
found — see "Reddit sentiment via Apify" below.

**What's left, and it's just waiting on the season:**

Once weekly games start, run `sync-weekly-points` for each league —
`waiver-targets`/`trade-targets`/`buy-sell` all need real weekly points
data to say anything useful; right now they'll just report "no candidates"
because there's no games yet. Nothing to fix, just nothing to show until
then.

## Why X/Twitter was skipped

Per the original scope: X's API is paid and priced for commercial use, not
a personal side project — not cost-effective here. The documented fallback
(RSS/Nitter mirrors of beat reporters) was also skipped: Nitter instances
are unreliable and frequently down, which would make that data source
flaky in a way that's worse than just not having it. Reddit (via Apify, see
below) is the sentiment source; if X becomes a real gap in practice, revisit
then rather than building against infrastructure likely to break on its own.

## Reddit sentiment via Apify

Originally out of scope: Reddit sentiment needed a "script" app
(client_id/client_secret) that only the account owner could create. By the
time this was revisited, Reddit had closed that door entirely — self-service
API registration closed November 2025, and the old free workaround
(unauthenticated `.json` URLs, no key needed) got blocked in May 2026 too.
There's no compliant free path left for a new project.

**What's used instead**: Apify's Reddit Scraper actor (`platforms/reddit/`),
called over Apify's plain REST API (`run-sync-get-dataset-items`) — no
Reddit credentials needed, just a free Apify account. This is explicitly a
ToS gray area: Apify is scraping Reddit on your behalf, which Reddit's own
terms don't permit, even though enforcement against small third-party
scrapers has been looser than, say, X's. Going ahead with it was a deliberate
call, not a "this is definitely fine" one.

**Cost**: Apify's free plan grants $5/month usage forever, no card required.
The Reddit Scraper actor runs ~$3.40 per 1,000 results; at this app's volume
(periodic sentiment checks across a couple dozen rostered players) that free
allowance should comfortably cover it indefinitely, though that's not a
guarantee if Apify changes pricing or the free tier later.

**UNVERIFIED**: same situation as KTC/FantasyPros/FFC when they were first
built — this sandbox can't reach apify.com, so neither the Reddit Scraper
actor's exact input parameters nor its output field names are confirmed
live. `platforms/reddit/client.py` tries several plausible field names per
attribute defensively rather than betting on one exact schema (same pattern
as `espn/rankings.py`'s rank-type guessing). Set `APIFY_API_TOKEN` and run
`fantasy-assistant sync-reddit` locally to verify; an `ApifyFetchError` or
a run that scans posts but scores zero players despite real matches
existing both point at the assumptions in `client.py` needing a real look.

**Scoped to dynasty use, by request**: defaults to r/DynastyFF only (not
r/fantasyfootball), filtered to posts flaired "Player Discussion" or "News"
— this app's actual sentiment use case is dynasty buy-low/sell-high, not
general redraft chatter. Flair matching is case-insensitive substring, not
exact equality, since real flairs are often decorated (e.g. "🏈 News"); a
post with no determinable flair is dropped rather than let through, since
silently including unknown-flair posts would defeat the point of asking for
specific ones. Both are overridable per-run:

```powershell
fantasy-assistant sync-reddit --subreddit DynastyFF --subreddit fantasyfootball
fantasy-assistant sync-reddit --flair "Trade" --flair "Rookie Draft"
fantasy-assistant sync-reddit --flair ''   # disables flair filtering entirely
```

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
   `ESPN_SWID`, `ESPN_S2`, and (once you set it up) `APIFY_API_TOKEN`.
4. **Networking → Generate Domain**.

Web dashboard pages: `/` (priorities + standings + Sync Now), then
`/league/{league_id}` for each league's hub, with `/league/{league_id}/draft-board`,
`/waivers`, `/buy-sell`, `/trade-analyzer`, and (devy league only) `/devy`
underneath it — see "Phase C" above. All behind the shared login. The devy
watchlist is view-only on the web — add/remove prospects via the CLI
(`devy-add`/`devy-remove`) since that's a
local/one-time action, not something that needed a web form yet.

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
  web_components.py            # design system: CSS tokens + HTML component helpers
  devy.py                       # devy watchlist CRUD
  config.py                   # config/leagues.yaml + secrets.yaml/env loading
  db.py                        # SQLite connection/init
  schema.sql                    # all table definitions, heavily commented
  analysis/                   # cross-cutting logic (not platform-specific)
    draft_board.py             # market ADP (FFC) vs ESPN rank inefficiency
    performance_trend.py        # recent vs season points
    waiver_targets.py            # available/rostered players trending up
    buy_low_sell_high.py          # the composite engine
    trade_analyzer.py              # two-sided trade value comparison
    roster_needs.py                 # positional need-gap vs league average
    roster_format.py                 # 1QB vs Superflex detection (shared)
    sentiment.py                      # lexicon-based Reddit scoring
  platforms/
    matching.py                 # cross-platform name matching (shared)
    sleeper/                    # client, sync, weekly_points
    espn/                       # client, sync, rankings, constants
    ktc/                        # client (verified live), sync
    fantasypros/                # client (verified live), sync
    ffc/                        # client (UNVERIFIED), sync — real ADP for the draft board
    reddit/                     # client (Apify-based, UNVERIFIED), sync
tests/                        # 122 tests, see "Run the tests" above
```
