import { renderPage, statTiles, badge, sportChip, tabs, escapeHtml } from "../layout.js";
import { coverRateBarChart } from "../charts.js";
import type { BacktestRunSummary } from "../../db/repo.js";
import type { AggregateStats, OpeningCoverStats, ThresholdStats, SeasonStats } from "../../backtest/report.js";

function fmtPct(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function fmtClv(value: number | null): string {
  return value === null ? "—" : `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
}

function coverTone(value: number | null): "good" | "bad" | "neutral" {
  if (value === null) return "neutral";
  return value >= 0.5 ? "good" : "bad";
}

function table(headers: string[], rows: string[][]): string {
  return `<table>
    <thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody>
  </table>`;
}

export function renderBacktestReport(
  run: BacktestRunSummary,
  overall: AggregateStats,
  openingCover: OpeningCoverStats,
  thresholds: ThresholdStats[],
  seasons: SeasonStats[],
): string {
  const overviewTab = `
    ${statTiles([
      { label: "Games scored", value: overall.games.toLocaleString() },
      {
        label: "Cover rate (vs. close)",
        value: fmtPct(overall.coverRate),
        tone: coverTone(overall.coverRate),
        sub: `${overall.decidedGames} decided (model disagreed with opening)`,
      },
      {
        label: "Cover rate (vs. open — real answer)",
        value: fmtPct(openingCover.coverRate),
        tone: coverTone(openingCover.coverRate),
        sub: "would this have made money, betting the opening price",
      },
      { label: "Avg CLV", value: fmtClv(overall.avgClv), sub: "price movement only, independent of outcome" },
    ])}
    <div class="banner">
      <strong>Three different questions, don't conflate them:</strong> cover rate vs. the
      closing line is a diagnostic (did the model's disagreement with the market look
      right in hindsight); average CLV is pure price movement and says nothing about who
      won; cover rate vs. the <em>opening</em> line is the only one of the three that
      answers "would betting this have made money."
    </div>
  `;

  const deviationRows = thresholds.map((t) => [
    `≥ ${t.minDeviation} pts`,
    t.games.toLocaleString(),
    t.coverRate === null ? '<span class="muted">—</span>' : badge(fmtPct(t.coverRate), coverTone(t.coverRate)),
    fmtClv(t.avgClv),
  ]);
  const deviationTab = `
    <p class="subtitle">Filtered to games where the model's spread disagreed with the opening line by at least N points — do bigger disagreements carry more signal, or just more noise?</p>
    <div class="chart-card">
      ${coverRateBarChart(thresholds.map((t) => ({ label: `≥${t.minDeviation}`, coverRate: t.coverRate, games: t.games })))}
    </div>
    ${table(["Min. deviation", "Games", "Cover rate (vs. close)", "Avg CLV"], deviationRows)}
  `;

  const seasonRows = seasons.map((s) => [
    String(s.season),
    s.games.toLocaleString(),
    s.coverRate === null ? '<span class="muted">—</span>' : badge(fmtPct(s.coverRate), coverTone(s.coverRate)),
    fmtClv(s.avgClv),
  ]);
  const historyTab = `
    <p class="subtitle">Season-by-season breakdown of this run — the model shouldn't need a specific season to look good; consistency across seasons matters more than any single year's number.</p>
    ${
      seasons.length > 0
        ? `<div class="chart-card">${coverRateBarChart(seasons.map((s) => ({ label: String(s.season), coverRate: s.coverRate, games: s.games })))}</div>`
        : ""
    }
    ${
      seasonRows.length > 0
        ? table(["Season", "Games", "Cover rate (vs. close)", "Avg CLV"], seasonRows)
        : `<p class="muted">No seasons scored yet.</p>`
    }
  `;

  const body = `
    <p class="subtitle"><a class="run-link" href="/">← All runs</a></p>
    <h1>${escapeHtml(run.name)}</h1>
    <p class="subtitle">
      Run #${run.id} · ${run.sport ? sportChip(run.sport) : ""} · ${run.seasonStart}–${run.seasonEnd} ·
      method <code>${escapeHtml(run.method)}</code>
    </p>
    ${tabs("bt", [
      { label: "Overview", html: overviewTab },
      { label: "Deviation from market", html: deviationTab },
      { label: "Historical (by season)", html: historyTab },
    ])}
  `;
  return renderPage(run.name, body, "/");
}
