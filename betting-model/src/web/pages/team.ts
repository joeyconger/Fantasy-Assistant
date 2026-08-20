import { renderPage, statTiles, escapeHtml } from "../layout.js";
import { ratingTrendChart } from "../charts.js";
import type { TeamInfo, RatingHistoryPoint } from "../../db/repo.js";

export function renderTeamPage(team: TeamInfo, history: RatingHistoryPoint[]): string {
  const current = history[history.length - 1] ?? null;
  const peak = history.reduce<RatingHistoryPoint | null>((acc, p) => (!acc || p.rating > acc.rating ? p : acc), null);

  const headline = statTiles([
    {
      label: "Current rating",
      value: current ? `${current.rating >= 0 ? "+" : ""}${current.rating.toFixed(2)}` : "—",
      tone: current ? (current.rating >= 0 ? "good" : "bad") : "neutral",
      sub: current ? `as of ${current.season} wk ${current.throughWeek}` : undefined,
    },
    {
      label: "Peak rating",
      value: peak ? `${peak.rating >= 0 ? "+" : ""}${peak.rating.toFixed(2)}` : "—",
      sub: peak ? `${peak.season} wk ${peak.throughWeek}` : undefined,
    },
    { label: "Weeks rated", value: String(history.length) },
  ]);

  const chart =
    history.length > 0
      ? `<div class="chart-card">${ratingTrendChart(history.map((p) => ({ label: `${p.season} wk${p.throughWeek}`, rating: p.rating })))}</div>`
      : `<p class="muted">No rating history yet — run <code>npm run ratings:compute -- --sport ${escapeHtml(team.sport)}</code> first.</p>`;

  const body = `
    <p class="subtitle"><a class="run-link" href="/ratings?sport=${escapeHtml(team.sport)}">← All ratings</a></p>
    <h1>${escapeHtml(team.name)}</h1>
    <p class="subtitle">${team.conference ? escapeHtml(team.conference) : "No conference on file"} · ${team.sport.toUpperCase()}</p>
    ${headline}
    <h2>Rating over time</h2>
    ${chart}
  `;
  return renderPage(team.name, body, "/ratings");
}
