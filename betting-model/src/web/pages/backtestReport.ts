import { renderPage, statTiles, tabs, escapeHtml } from "../layout.js";
import { renderCoverRateChart } from "../charts.js";
import type {
  AggregateStats,
  ThresholdStats,
  ConfidenceStats,
  SportSeasonStats,
  OpeningCoverStats,
  KeyNumberStats,
  WeatherStats,
  ConferenceStats,
  InOutConferenceStats,
  WeekBucketStats,
  HomeRoadSizeStats,
} from "../../backtest/report.js";
import type { BacktestRunSummary } from "../../db/repo.js";

function fmtPct(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function fmtSigned(value: number | null): string {
  if (value === null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}`;
}

function coverClass(value: number | null): string {
  if (value === null) return "muted";
  return value >= 0.5 ? "good" : "bad";
}

function coverTone(value: number | null): "good" | "bad" | "neutral" {
  if (value === null) return "neutral";
  return value >= 0.5 ? "good" : "bad";
}

export interface SegmentData {
  keyNumbers: KeyNumberStats[];
  weather: WeatherStats[];
  precipitation: WeatherStats[];
  conference: ConferenceStats[];
  inOutConference: InOutConferenceStats[];
  weekBucket: WeekBucketStats[];
  homeRoadSpread: HomeRoadSizeStats[];
  homeRoadDeviation: HomeRoadSizeStats[];
}

/** Shared chart+table pattern reused across every segment breakdown in this report — cuts the repetition that would otherwise appear ~8 times. */
function statSection(games: number, chartSvg: string, tableHtml: string): string {
  return games === 0 ? `<p class="muted">No games in this breakdown for this run.</p>` : `${chartSvg}${tableHtml}`;
}

function table(headers: string[], rows: string[]): string {
  return `<table><thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table>`;
}

function statRow(label: string, s: AggregateStats): string {
  return `<tr><td>${escapeHtml(label)}</td><td class="num">${s.games}</td><td class="num ${coverClass(s.coverRate)}">${fmtPct(s.coverRate)}</td><td class="num">${fmtSigned(s.avgClv)}</td></tr>`;
}

export function renderBacktestReport(
  run: BacktestRunSummary,
  overall: AggregateStats,
  openingCover: OpeningCoverStats,
  thresholds: ThresholdStats[],
  confidence: ConfidenceStats[],
  bySeasonSport: SportSeasonStats[],
  segments: SegmentData,
): string {
  const isCfb = run.sport === "cfb";
  const totalGames = thresholds[0]?.games ?? overall.games;

  // --- Overview tab ---
  const headline = statTiles([
    { label: "Games scored", value: totalGames.toLocaleString() },
    { label: "Cover rate (vs. close)", value: fmtPct(overall.coverRate), tone: coverTone(overall.coverRate) },
    {
      label: "Cover rate (vs. open)",
      value: fmtPct(openingCover.coverRateVsOpening),
      tone: coverTone(openingCover.coverRateVsOpening),
      sub: `${openingCover.games.toLocaleString()} games w/ opening line`,
    },
    { label: "Avg CLV", value: fmtSigned(overall.avgClv) },
  ]);

  const seasonChart = renderCoverRateChart(
    bySeasonSport.map((s) => ({ label: `${s.sport} ${s.season}`, coverRate: s.coverRate, games: s.games })),
  );
  const seasonTable = table(
    ["Sport", "Season", "Games", "Cover rate", "Avg CLV"],
    bySeasonSport.map(
      (s) => `<tr>
        <td>${escapeHtml(s.sport)}</td>
        <td class="num">${s.season}</td>
        <td class="num">${s.games}</td>
        <td class="num ${coverClass(s.coverRate)}">${fmtPct(s.coverRate)}</td>
        <td class="num">${fmtSigned(s.avgClv)}</td>
      </tr>`,
    ),
  );

  const overviewTab = `
    ${headline}
    <p class="subtitle">"Cover rate (vs. open)" is whether the pick would have won money bet AT the opening line, using the real result — the actual answer to "would this have been profitable." Different from Avg CLV (price movement only) and from "vs. close" (whether the CLOSING number, not the price you'd have bet, was beaten). See README "Backtest results" for the full three-metrics explanation.</p>
    <h2>By sport/season</h2>
    <p class="subtitle">Is the result stable year to year, or is one season driving it?</p>
    ${statSection(bySeasonSport.reduce((n, s) => n + s.games, 0), seasonChart, seasonTable)}
  `;

  // --- Deviation & confidence tab ---
  const thresholdChart = renderCoverRateChart(
    thresholds.map((t) => ({ label: `${t.threshold}+`, coverRate: t.coverRate, games: t.games })),
  );
  const thresholdTable = table(
    ["Min deviation (pts)", "Games", "Cover rate", "Avg CLV"],
    thresholds.map(
      (t) => `<tr><td class="num">${t.threshold}+</td><td class="num">${t.games}</td><td class="num ${coverClass(t.coverRate)}">${fmtPct(t.coverRate)}</td><td class="num">${fmtSigned(t.avgClv)}</td></tr>`,
    ),
  );

  const confidenceChart = renderCoverRateChart(
    confidence.map((c) => ({ label: `≤${c.maxConfidence}`, coverRate: c.coverRate, games: c.games })),
  );
  const confidenceTable = table(
    ["Max error (±pts)", "Games", "Cover rate", "Avg CLV"],
    confidence.map(
      (c) => `<tr><td class="num">≤${c.maxConfidence}</td><td class="num">${c.games}</td><td class="num ${coverClass(c.coverRate)}">${fmtPct(c.coverRate)}</td><td class="num">${fmtSigned(c.avgClv)}</td></tr>`,
    ),
  );

  const deviationTab = `
    <h2>By deviation threshold</h2>
    <p class="subtitle">Restricting to picks where the model disagreed with the market by at least this much. Dashed line is the 50% no-edge baseline.</p>
    ${statSection(thresholds[0]?.games ?? 0, thresholdChart, thresholdTable)}
    <h2>By confidence</h2>
    <p class="subtitle">Restricting to picks with at least this much certainty (lower = more games observed when predicted) — a different question than deviation size above.</p>
    ${statSection(confidence.reduce((n, c) => n + c.games, 0), confidenceChart, confidenceTable)}
  `;

  // --- Conference tab (CFB only) ---
  let conferenceTab = `<p class="muted">Conference breakdowns only apply to CFB — this run is NFL.</p>`;
  if (isCfb) {
    const conferenceChart = renderCoverRateChart(
      segments.conference.map((c) => ({ label: c.conference, coverRate: c.coverRate, games: c.games })),
    );
    const conferenceTable = table(
      ["Conference (of picked team)", "Games", "Cover rate", "Avg CLV"],
      segments.conference.map(
        (c) => `<tr><td>${escapeHtml(c.conference)}</td><td class="num">${c.games}</td><td class="num ${coverClass(c.coverRate)}">${fmtPct(c.coverRate)}</td><td class="num">${fmtSigned(c.avgClv)}</td></tr>`,
      ),
    );
    const inOutChart = renderCoverRateChart(
      segments.inOutConference.map((c) => ({ label: c.matchupType, coverRate: c.coverRate, games: c.games })),
    );
    const inOutTable = table(
      ["Matchup type", "Games", "Cover rate", "Avg CLV"],
      segments.inOutConference.map(
        (c) => `<tr><td>${escapeHtml(c.matchupType)}</td><td class="num">${c.games}</td><td class="num ${coverClass(c.coverRate)}">${fmtPct(c.coverRate)}</td><td class="num">${fmtSigned(c.avgClv)}</td></tr>`,
      ),
    );
    conferenceTab = `
      <div class="banner">Real risk of overfitting to noise here — many conferences, moderate games per conference each. Treat any standout conference as a hypothesis worth a dedicated holdout test, not a confirmed edge.</div>
      <h2>By conference of the picked team</h2>
      <p class="subtitle">Does the model do better picking teams from some conferences than others?</p>
      ${statSection(segments.conference.reduce((n, c) => n + c.games, 0), conferenceChart, conferenceTable)}
      <h2>In-conference vs. out-of-conference</h2>
      <p class="subtitle">Rivalry-heavy, familiar matchups vs. cross-conference games.</p>
      ${statSection(segments.inOutConference.reduce((n, c) => n + c.games, 0), inOutChart, inOutTable)}
    `;
  }

  // --- Schedule spot tab ---
  let scheduleTab = "";
  if (isCfb) {
    const weekChart = renderCoverRateChart(
      segments.weekBucket.map((w) => ({ label: w.weekBucket, coverRate: w.coverRate, games: w.games })),
    );
    const weekTable = table(
      ["Week range", "Games", "Cover rate", "Avg CLV"],
      segments.weekBucket.map(
        (w) => `<tr><td>${escapeHtml(w.weekBucket)}</td><td class="num">${w.games}</td><td class="num ${coverClass(w.coverRate)}">${fmtPct(w.coverRate)}</td><td class="num">${fmtSigned(w.avgClv)}</td></tr>`,
      ),
    );
    const homeRoadSpreadRows = segments.homeRoadSpread
      .filter((r) => r.games > 0)
      .map(
        (r) => `<tr><td>${escapeHtml(r.pickSide)}</td><td>${escapeHtml(r.sizeBucket)}</td><td class="num">${r.games}</td><td class="num ${coverClass(r.coverRate)}">${fmtPct(r.coverRate)}</td><td class="num">${fmtSigned(r.avgClv)}</td></tr>`,
      );
    const homeRoadDeviationRows = segments.homeRoadDeviation
      .filter((r) => r.games > 0)
      .map(
        (r) => `<tr><td>${escapeHtml(r.pickSide)}</td><td>${escapeHtml(r.sizeBucket)}</td><td class="num">${r.games}</td><td class="num ${coverClass(r.coverRate)}">${fmtPct(r.coverRate)}</td><td class="num">${fmtSigned(r.avgClv)}</td></tr>`,
      );
    scheduleTab = `
      <h2>By week</h2>
      <p class="subtitle">The literal test of "early season, thin data, should be worse."</p>
      ${statSection(segments.weekBucket.reduce((n, w) => n + w.games, 0), weekChart, weekTable)}
      <h2>Home/road × the game's own spread size</h2>
      <p class="subtitle">Favorite/underdog crossed with home/road — the market's own number, not the model's deviation.</p>
      ${statSection(homeRoadSpreadRows.length, "", table(["Pick", "Spread size", "Games", "Cover rate", "Avg CLV"], homeRoadSpreadRows))}
      <h2>Home/road × model deviation size</h2>
      <p class="subtitle">Does the model's edge (when it disagrees a lot) hold up the same for home picks as away picks?</p>
      ${statSection(homeRoadDeviationRows.length, "", table(["Pick", "Deviation size", "Games", "Cover rate", "Avg CLV"], homeRoadDeviationRows))}
    `;
  } else {
    scheduleTab = `<p class="muted">Week/home-road breakdowns are currently only computed for CFB runs.</p>`;
  }

  // --- Key numbers & weather tab ---
  const keyNumberChart = renderCoverRateChart(
    segments.keyNumbers.map((k) => ({ label: k.keyNumberBucket, coverRate: k.coverRate, games: k.games })),
  );
  const keyNumberTable = table(
    ["Distance from key number", "Games", "Cover rate", "Avg CLV"],
    segments.keyNumbers.map((k) => statRow(k.keyNumberBucket, k)),
  );
  const weatherChart = renderCoverRateChart(
    segments.weather.map((w) => ({ label: w.weatherBucket, coverRate: w.coverRate, games: w.games })),
  );
  const weatherTable = table(["Wind", "Games", "Cover rate", "Avg CLV"], segments.weather.map((w) => statRow(w.weatherBucket, w)));
  const precipChart = renderCoverRateChart(
    segments.precipitation.map((w) => ({ label: w.weatherBucket, coverRate: w.coverRate, games: w.games })),
  );
  const precipTable = table(
    ["Precipitation", "Games", "Cover rate", "Avg CLV"],
    segments.precipitation.map((w) => statRow(w.weatherBucket, w)),
  );
  const weatherGames = segments.weather.reduce((n, w) => n + w.games, 0);

  const moreTab = `
    <h2>By distance from a key number</h2>
    <p class="subtitle">3, 4, 6, 7, 10, 13, 14, 17, 20, 21 — where NFL/CFB final margins cluster (field goal, touchdown, common combinations). This is about the market's own number, not the model.</p>
    ${statSection(segments.keyNumbers.reduce((n, k) => n + k.games, 0), keyNumberChart, keyNumberTable)}
    <h2>By wind</h2>
    <p class="subtitle">Historical weather backfill is UNVERIFIED and needs the <code>weather-backfill</code> job run first — this will be empty until then. See README "New scaffolds."</p>
    ${weatherGames === 0 ? `<p class="muted">No weather data for this run yet — run the <code>weather-backfill</code> admin job.</p>` : statSection(weatherGames, weatherChart, weatherTable)}
    <h2>By precipitation</h2>
    ${statSection(segments.precipitation.reduce((n, w) => n + w.games, 0), precipChart, precipTable)}
  `;

  const body = `
    <h1>Backtest #${run.id}: ${escapeHtml(run.name)}</h1>
    <p class="subtitle">${escapeHtml(run.method)} · ${escapeHtml(run.sport ?? "?")} · seasons ${run.seasonStart}–${run.seasonEnd}</p>
    <div class="banner">
      <strong>Cover rate</strong> is ATS win rate against the closing line for whichever side the
      model favored. <strong>Avg CLV</strong> is only computed for games with a real opening line —
      "—" means none of the games in that row had one.
    </div>
    ${tabs(`bt${run.id}`, [
      { label: "Overview", html: overviewTab },
      { label: "Deviation & confidence", html: deviationTab },
      { label: "Conference", html: conferenceTab },
      { label: "Schedule spot", html: scheduleTab },
      { label: "Key numbers & weather", html: moreTab },
    ])}
  `;
  return renderPage(`Backtest #${run.id}`, body, "/");
}
