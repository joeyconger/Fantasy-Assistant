import { renderPage, statTiles, badge, escapeHtml } from "../layout.js";
import type { TeamRatingRow, PredictionRow } from "../../db/repo.js";

function form(action: string, label: string, sport: string, season: string, week: string): string {
  return `
    <form method="get" action="${action}">
      <select name="sport">
        <option value="nfl" ${sport === "nfl" ? "selected" : ""}>NFL</option>
        <option value="cfb" ${sport === "cfb" ? "selected" : ""}>CFB</option>
      </select>
      <input type="number" name="season" placeholder="Season, e.g. 2025" value="${escapeHtml(season)}" required>
      <input type="number" name="week" placeholder="Through week" value="${escapeHtml(week)}" required>
      <button type="submit">${escapeHtml(label)}</button>
    </form>
  `;
}

function powerBar(rating: number, maxAbs: number): string {
  const pct = maxAbs === 0 ? 0 : Math.min(100, (Math.abs(rating) / maxAbs) * 50);
  const fill =
    rating === 0
      ? ""
      : rating > 0
        ? `<div class="power-bar-fill pos" style="width:${pct.toFixed(1)}%"></div>`
        : `<div class="power-bar-fill neg" style="width:${pct.toFixed(1)}%"></div>`;
  return `<div class="power-bar-cell">
    <div class="power-bar-track">
      <div class="power-bar-center"></div>
      ${fill}
    </div>
  </div>`;
}

export function renderRatingsPage(
  sport: string,
  season: string,
  week: string,
  ratings: TeamRatingRow[] | null,
): string {
  const maxAbs = ratings ? Math.max(1e-9, ...ratings.map((r) => Math.abs(r.rating))) : 0;
  const headline =
    ratings && ratings.length > 0
      ? statTiles([
          { label: "Teams rated", value: String(ratings.length) },
          {
            label: "Top team",
            value: escapeHtml(ratings[0]!.teamName),
            tone: "good",
            sub: `${ratings[0]!.rating >= 0 ? "+" : ""}${ratings[0]!.rating.toFixed(2)} pts`,
          },
          {
            label: "Bottom team",
            value: escapeHtml(ratings[ratings.length - 1]!.teamName),
            tone: "bad",
            sub: `${ratings[ratings.length - 1]!.rating >= 0 ? "+" : ""}${ratings[ratings.length - 1]!.rating.toFixed(2)} pts`,
          },
        ])
      : "";

  const table =
    ratings === null
      ? ""
      : ratings.length === 0
        ? `<p class="muted">No ratings computed for ${escapeHtml(sport)} ${escapeHtml(season)} through week ${escapeHtml(week)} yet — run <code>npm run ratings:compute -- --sport ${escapeHtml(sport)} --season ${escapeHtml(season)}</code> first.</p>`
        : `<table>
            <thead><tr><th>#</th><th>Team</th><th class="num">Rating</th><th>Power rating</th><th class="num">± error</th></tr></thead>
            <tbody>${ratings
              .map(
                (r, i) => `<tr>
                  <td class="muted">${i + 1}</td>
                  <td>${escapeHtml(r.teamName)}</td>
                  <td class="num">${r.rating >= 0 ? "+" : ""}${r.rating.toFixed(2)}</td>
                  <td>${powerBar(r.rating, maxAbs)}</td>
                  <td class="num muted">${r.ratingError === null ? "—" : r.ratingError.toFixed(2)}</td>
                </tr>`,
              )
              .join("")}</tbody>
          </table>
          <p class="subtitle" style="margin-top:1rem;">
            <a class="run-link" href="/predictions?sport=${escapeHtml(sport)}&season=${escapeHtml(season)}&week=${Number(week) + 1}">
              See week ${Number(week) + 1} predictions using these ratings →
            </a>
          </p>`;

  const body = `
    <h1>Team ratings</h1>
    <p class="subtitle">EPA-driven Elo ratings, in points (positive = above league average). Bars are relative to the widest spread in this list, not an absolute scale.</p>
    ${form("/ratings", "Show ratings", sport, season, week)}
    ${headline}
    ${table}
  `;
  return renderPage("Ratings", body, "/ratings");
}

export function renderPredictionsPage(
  sport: string,
  season: string,
  week: string,
  predictions: PredictionRow[] | null,
): string {
  const withDeviation =
    predictions?.map((p) => ({
      ...p,
      deviation: p.marketSpreadHome === null ? null : p.modelSpreadHome - p.marketSpreadHome,
    })) ?? null;

  const bigDeviations = withDeviation?.filter((p) => p.deviation !== null && Math.abs(p.deviation) >= 3).length ?? 0;

  const headline =
    withDeviation && withDeviation.length > 0
      ? statTiles([
          { label: "Games", value: String(withDeviation.length) },
          {
            label: "Model vs. market, 3+ pts apart",
            value: String(bigDeviations),
            sub: bigDeviations > 0 ? "worth a second look, not a signal" : undefined,
          },
        ])
      : "";

  const table =
    withDeviation === null
      ? ""
      : withDeviation.length === 0
        ? `<p class="muted">No predictions generated for ${escapeHtml(sport)} ${escapeHtml(season)} week ${escapeHtml(week)} yet — run <code>npm run ratings:predict -- --sport ${escapeHtml(sport)} --season ${escapeHtml(season)} --week ${escapeHtml(week)}</code> first.</p>`
        : `<table>
            <thead><tr><th>Matchup</th><th class="num">Model line (home)</th><th class="num">Market line (home)</th><th class="num">Deviation</th><th class="num">Confidence (±pts)</th></tr></thead>
            <tbody>${withDeviation
              .map((p) => {
                const devBadge =
                  p.deviation === null
                    ? '<span class="muted">—</span>'
                    : badge(`${p.deviation >= 0 ? "+" : ""}${p.deviation.toFixed(1)}`, "neutral");
                return `<tr>
                  <td>${escapeHtml(p.awayTeam)} @ ${escapeHtml(p.homeTeam)}</td>
                  <td class="num">${p.modelSpreadHome.toFixed(1)}</td>
                  <td class="num">${p.marketSpreadHome === null ? "—" : p.marketSpreadHome.toFixed(1)}</td>
                  <td class="num">${devBadge}</td>
                  <td class="num muted">${p.confidence === null ? "—" : p.confidence.toFixed(1)}</td>
                </tr>`;
              })
              .join("")}</tbody>
          </table>`;

  const body = `
    <h1>Model predictions</h1>
    <p class="subtitle">Raw model output vs. market — diagnostic only, not a picks feature.</p>
    <div class="banner">
      See the backtest report for whether this model's picks beat the closing line —
      these numbers are not validated for betting either way.
    </div>
    ${form("/predictions", "Show predictions", sport, season, week)}
    ${headline}
    ${table}
  `;
  return renderPage("Predictions", body, "/predictions");
}
