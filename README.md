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
| Settings page (add/edit/remove leagues, DB-backed config) | ✅ **Verified live** — full add/update/remove flow smoke-tested against a real running server, owner dropdown confirmed populated from synced data |

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

## Design refresh: Sleeper-app-flavored visual pass

A second design pass on top of Phase B's system, aimed at "sleek modern
fantasy app" specifically rather than "clean utilitarian dashboard":

- **Color/gradient**: swapped the flat single-color accent for a
  teal→violet gradient (`--accent`/`--accent-2`), Sleeper's actual brand
  palette flavor. Badges, avatars, active nav/tab pills, buttons, and stat
  tile top-accents all use it. Position/format badges and avatars now use a
  computed two-stop gradient (flat color → a darker shade of itself, via
  `web_components.gradient()`/`_darken()`) instead of a flat fill, computed
  in Python rather than CSS `color-mix()` so it doesn't depend on
  per-element custom properties.
- **Depth**: cards, tables, buttons, and nav pills all get a soft shadow
  plus a hover-lift transition (`translateY` + a stronger shadow) — nothing
  sits totally flat against the background anymore.
- **App-shell feel**: the header (logo + nav) is now a `position: sticky`,
  backdrop-blurred bar (`.app-bar`) that stays pinned while scrolling,
  instead of static page content you scroll away from.
- **Collapsible sections**: the home dashboard's per-league standings are
  now native `<details>/<summary>` widgets (`web_components.collapsible()`)
  — a real expand/collapse interaction with zero JS, styled to match the
  rest of the system (custom chevron, card styling). Open by default.
- **Small motion touches**: a subtle page fade-in on load, a pulsing
  opacity animation on the disabled Sync button (was static "Syncing…"
  text only), and a small colored dot before each buy/sell flag.
- **Darker dark mode**: dark surfaces moved closer to true near-black navy
  (previously a lighter slate) for more contrast against the brighter
  accent gradient.

Verified visually with Playwright screenshots (light + dark, mobile +
desktop viewports) against seeded synthetic data — not just "tests pass,"
actually rendered and looked at. `tests/test_web_components.py` covers the
new `gradient()`/`_darken()`/`collapsible()` helpers. No routes, nav
structure, or page content changed — this is a CSS/markup-only pass on top
of the existing pages.

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

173 tests, all passing as of this writing. Covers: Sleeper/ESPN sync upserts,
the private-league auth path, the players table's platform-scoped primary
key (prevents Sleeper/ESPN ID collisions), cross-platform name matching
(suffixes, punctuation, ambiguous-duplicate handling), the rank-inefficiency
engine (including the Superflex QB-crowding position-relative fix and FFC
ADP integration), performance trend math, waiver/trade filtering, the
buy-low/sell-high flag logic, KTC/FantasyPros/FFC parser strategies against
synthetic HTML/JSON, the Apify-based Reddit client's defensive field
extraction, lexicon-based sentiment scoring, the devy watchlist,
roster-needs gap analysis, the trade analyzer, the design-system component
helpers (XSS-escaping), the web dashboard (auth gating, XSS-escaping,
missing-env-var fail-fast), the `league_sources` DB-backed config store
plus the web Settings page (CRUD, YAML migration, owner dropdown, form
error handling), and the in-process daily sync scheduler's time math
(`auto_sync.py`, including that it never spawns a real thread under
pytest).

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
fantasy-assistant sync-draft-data                   # sync-rankings + FFC ADP (both qb_modes) in one call — see "Auto-syncing draft/market data"
fantasy-assistant sync-market-values                # KTC (dynasty+devy, both qb_modes) + FantasyPros in one call — feeds buy-sell/devy
fantasy-assistant sync-reddit       # needs APIFY_API_TOKEN; see "Reddit sentiment via Apify" for subreddit/flair defaults

fantasy-assistant list-leagues                                    # leagues currently configured to sync
fantasy-assistant add-league LEAGUE_ID --platform sleeper --format dynasty --my-owner-id u1
fantasy-assistant remove-league LEAGUE_ID                          # stops syncing it; keeps already-synced data
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
by default (useful, but you have to judge fit yourself). Set your
`owner_id` for a league from the web Settings page (`/settings` — pick your
team from a dropdown once that league has been synced at least once), or via
`fantasy-assistant owners LEAGUE_ID` to find it and `fantasy-assistant
add-league --my-owner-id` when first adding a league (see "Settings" below)
— and: trade-targets excludes players you already own, both commands tag
candidates that fill one of your roster's actual weak positions
(`analysis/roster_needs.py` — compares your average rank per position
against the league average), and buy-sell tags whether each flagged player
is on your roster (an actual sell-high decision) or someone else's (a
trade-for target). Leave it unset and everything still works exactly as
before, unpersonalized.

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

**On the deployed web dashboard**, there's a **"Sync Reddit Sentiment"**
button next to Sync Now (`POST /sync-reddit`) using the default subreddit/
flair ruleset — the only way to trigger this against production data now
that there's no separate CLI/cron access to that database. Deliberately
kept out of both `/sync` and the automatic daily sync (see "Auto-syncing
draft/market data" below) for the same cost/ToS reasons — it only ever
runs when someone consciously clicks it. Set `APIFY_API_TOKEN` as a
Railway variable on the web service (never commit it to any file) before
using it.

**Scoped per subreddit, by request**: each subreddit gets its own flair
allowlist, since r/DynastyFF's "Player Discussion"/"News" posts and
r/fantasyfootball's "Player Discussion" posts (but not its "News", which is
mostly redraft-irrelevant noise for this app) are the actual signal wanted.
Defaults to `{"DynastyFF": ["Player Discussion", "News"], "fantasyfootball":
["Player Discussion"]}`. Flair matching is case-insensitive substring, not
exact equality, since real flairs are often decorated (e.g. "🏈 News"); a
post whose subreddit or flair can't be determined, or whose subreddit isn't
in the ruleset at all, is dropped rather than let through. Overridable
per-run with repeatable `--sub-flair SUBREDDIT FLAIR` pairs:

```powershell
fantasy-assistant sync-reddit
# uses the default ruleset above

fantasy-assistant sync-reddit --sub-flair DynastyFF "Player Discussion" --sub-flair DynastyFF News --sub-flair fantasyfootball "Player Discussion"
# same thing, spelled out explicitly

fantasy-assistant sync-reddit --sub-flair DynastyFF Trade --sub-flair DynastyFF "Rookie Draft"
# only Trade/Rookie Draft flaired posts from r/DynastyFF, nothing from r/fantasyfootball
```

**Cached 24h**, same idea as KTC/FantasyPros/FFC's cache but a full day
instead of 12h — sentiment doesn't need to be fresher than that, and every
call costs against the free Apify budget. Re-running `sync-reddit` within
24h of the last run just reports "cache fresh — skipped"; `--force`
bypasses it. `reddit_sentiment_cache_meta` is one global row (this is a
single combined sync across both subreddits, not scoped per format like
KTC/FFC), mirroring `players_cache_meta`'s single-row shape.

**How sentiment is scored** (`analysis/sentiment.py`): a cheap, transparent
lexicon match, not NLP. For each fetched post, the title+body text is
checked for a mention of a tracked player by last name (crude but readable
— catches casual references like "Chase is a stud" without needing full
name matches). Any post that mentions a player is scored by counting how
many words from a fixed positive list (`buy`, `breakout`, `stud`, `elite`,
`value`, `bell cow`, ...) versus a fixed negative list (`sell`, `bust`,
`injury`, `avoid`, `fade`, `overrated`, ...) appear in it — net_score =
positive hits minus negative hits for that post, added to the player's
running total across all matching posts. `mention_count` is just how many
posts referenced them; `positive_count`/`negative_count` tally how many of
those individual posts leaned each way. This is intentionally simple: a
signal for "this player is being talked about, and mostly positively or
negatively," not a claim of real sentiment understanding — one optional
input into buy-low/sell-high, not a standalone product.

**Only shown for dynasty/devy leagues**: since the data itself is sourced
from r/DynastyFF (+ r/fantasyfootball's Player Discussion flair), it's
dynasty-community chatter, not a general redraft signal. `buy_low_sell_high.py`
only computes and attaches it for dynasty/devy leagues (Weekend Warriors,
Dollars for Devys) — same `league_format in ("dynasty", "devy")` split KTC
values already use in that function. BMFS and Lads (redraft) never see a
sentiment-driven flag or the "Sentiment: ±N" line, even once real Reddit
data is synced.

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

That's the whole deploy — draft/market data auto-syncs daily from inside
this same service (see "Auto-syncing draft/market data" below). There's no
second service to set up: an earlier version of this app tried a separate
Railway cron service for that, which turned out to be broken by a real
Railway constraint (a Volume can only mount to one service at a time — see
that section for the full story) and was replaced.

Web dashboard pages: `/` (priorities + standings + Sync Now), `/settings`
(add/edit/remove leagues — see "Settings" below), then
`/league/{league_id}` for each league's hub, with `/league/{league_id}/draft-board`,
`/waivers`, `/buy-sell`, `/trade-analyzer`, and (devy league only) `/devy`
underneath it — see "Phase C" above. All behind the shared login. The devy
watchlist is view-only on the web — add/remove prospects via the CLI
(`devy-add`/`devy-remove`) since that's a
local/one-time action, not something that needed a web form yet.

## Settings

`/settings` is the live web page for managing which leagues get synced and
their per-league settings — no more manually editing `config/leagues.yaml`
and redeploying. It replaced that file as the actual source of truth: which
leagues to sync, their format override, `my_owner_id`, and (for the one
ESPN league) its season now all live in a `league_sources` DB table instead.

**Why the DB instead of the YAML file**: Railway re-clones this repo from
git on every deploy, which would silently wipe any hand-edited
`config/leagues.yaml` changes. `league_sources` lives on the same
persistent Volume as everything else already synced, so Settings changes
survive redeploys the same way synced league/roster data does.

**What you can do from `/settings`**:
- Add a league (Sleeper or ESPN — only one ESPN league is supported at a
  time), with an optional format override and `my_owner_id`.
- Edit an existing league's format override, `my_owner_id` (a dropdown once
  that league has been synced at least once, otherwise a plain text field —
  same `owner_id` lookup `fantasy-assistant owners` always did, just without
  the copy-paste round trip), and ESPN season.
- Remove a league, which stops future syncs but does **not** delete
  already-synced data (rosters/standings/etc.) for it.

**One-time migration**: the first time `league_sources` is empty (e.g. an
existing local setup, or the first deploy after this feature shipped), it's
auto-populated from `config/leagues.yaml` if that file exists. After that,
the YAML file is never read again — Settings (or the `add-league`/
`remove-league` CLI commands) is the only way leagues get added or removed.
ESPN cookies (`ESPN_SWID`/`ESPN_S2`) still come from env vars/
`config/secrets.yaml` only, never the DB — that credential boundary is
unchanged.

## Auto-syncing draft/market data

Two commands cover everything that used to require manual sync calls:

- **`fantasy-assistant sync-draft-data`** — everything the draft board
  depends on: Sleeper `search_rank` + ESPN's full player pool
  (`_sync_rank_data`, the same logic `sync-rankings` uses) plus FFC ADP for
  **both** qb_modes (1qb and superflex — different leagues use different
  modes, so both need refreshing regardless of which league you check the
  draft board from).
- **`fantasy-assistant sync-market-values`** — everything buy-sell/devy
  depend on: KTC dynasty+devy trade values (again, both qb_modes) plus
  FantasyPros redraft consensus rankings.

Each underlying sync still respects its own cache (12h for FFC/ESPN/KTC/
FantasyPros), so running either command more often than data actually
changes is a cheap no-op, not a wasted call. (Reddit sentiment, via
`sync-reddit`, is deliberately **not** included in either — it costs
against a metered Apify budget and sits in a ToS gray area, see "Reddit
sentiment via Apify" below, so it stays a manual, conscious action.)

**On Railway, this runs in-process** — a background thread inside the web
service itself (`auto_sync.py`), started from FastAPI's `lifespan` handler
in `web.py`, that wakes up once a day (13:00 UTC by default — change
`SYNC_HOUR_UTC` in `auto_sync.py` for a different time) and runs both
commands directly against the app's own DB connection.

**Why not a separate Railway cron service** (which is what this looked
like at first): Railway Volumes can only be mounted to **one service at a
time**. A second service running the sync commands against what was
supposed to be "the same" Volume actually just detached it from the web
service — the web dashboard silently fell back to a non-persistent path
inside its own container, while the cron service kept the real data. Every
symptom (draft board empty despite the cron reporting real synced counts,
leagues syncing fine because that data was written and read within the
same container's lifetime) traced back to this. Running the sync
in-process instead means there's only ever one service and one database
connection path — nothing to keep in sync across services, because there's
only one service.

**Locally**, there's no scheduler — just run `fantasy-assistant
sync-draft-data`/`sync-market-values` (or `--force` to bypass the caches)
whenever you want fresh data, same as any other sync command.

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
  leagues.yaml               # one-time migration input only, see league_sources.py
  secrets.yaml.example        # template for ESPN cookies (local use only)
src/fantasy_assistant/
  cli.py                      # all CLI commands
  web.py                       # FastAPI dashboard (incl. /settings)
  auto_sync.py                  # in-process daily background sync (see "Auto-syncing draft/market data")
  web_components.py            # design system: CSS tokens + HTML component helpers
  devy.py                       # devy watchlist CRUD
  config.py                   # config/leagues.yaml + secrets.yaml/env loading (migration-only now)
  league_sources.py            # league_sources DB table CRUD + YAML migration — live config source
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
tests/                        # 139 tests, see "Run the tests" above
```
