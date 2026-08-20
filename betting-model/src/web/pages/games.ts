import { renderPage, statTiles, badge, escapeHtml } from "../layout.js";
import type { GameHistoryRow } from "../../db/repo.js";

function form(sport: string, season: string): string {
  return `
    <form method="get" action="/games">
      <select name="sport">
        <option value="nfl" ${sport === "nfl" ? "selected" : ""}>NFL</option>
        <option value="cfb" ${sport === "cfb" ? "selected" : ""}>CFB</option>
      </select>
      <input type="number" name="season" placeholder="Season, e.g. 2023" value="${escapeHtml(season)}" required>
      <button type="submit">Show games</button>
    </form>
  `;
}

function fmtSpread(value: number | null): string {
  return value === null ? "—" : value >= 0 ? `+${value.toFixed(1)}` : value.toFixed(1);
}

function resultBadge(g: GameHistoryRow): string {
  if (g.homeScore === null || g.awayScore === null || g.closingSpreadHome === null) {
    return '<span class="muted">—</span>';
  }
  const margin = g.homeScore - g.awayScore + g.closingSpreadHome;
  if (margin === 0) return badge("push", "neutral");
  return margin > 0 ? badge("home covered", "good") : badge("away covered", "bad");
}

export function renderGamesPage(sport: string, season: string, games: GameHistoryRow[] | null): string {
  const finalGames = games?.filter((g) => g.status === "final") ?? [];
  const withLines = finalGames.filter((g) => g.closingSpreadHome !== null);
  const homeCovers = withLines.filter((g) => g.homeScore! - g.awayScore! + g.closingSpreadHome! > 0).length;
  const pushes = withLines.filter((g) => g.homeScore! - g.awayScore! + g.closingSpreadHome! === 0).length;
  const decided = withLines.length - pushes;

  const headline =
    games && games.length > 0
      ? statTiles([
          { label: "Games", value: String(games.length) },
          { label: "Final", value: String(finalGames.length) },
          {
            label: "Home covered (vs. close)",
            value: decided > 0 ? `${((homeCovers / decided) * 100).toFixed(1)}%` : "—",
            sub: `${homeCovers}/${decided} decided, ${pushes} push${pushes === 1 ? "" : "es"}`,
          },
        ])
      : "";

  const table =
    games === null
      ? ""
      : games.length === 0
        ? `<p class="muted">No games found for ${escapeHtml(sport)} ${escapeHtml(season)} — try ingesting this season first.</p>`
        : `<table>
            <thead><tr><th>Wk</th><th>Matchup</th><th class="num">Score</th><th class="num">Open</th><th class="num">Close</th><th>Result</th></tr></thead>
            <tbody>${games
              .map(
                (g) => `<tr>
                  <td class="muted">${g.week}</td>
                  <td>${escapeHtml(g.awayTeam)} @ ${escapeHtml(g.homeTeam)}</td>
                  <td class="num">${g.homeScore === null || g.awayScore === null ? '<span class="muted">—</span>' : `${g.awayScore}–${g.homeScore}`}</td>
                  <td class="num muted">${fmtSpread(g.openingSpreadHome)}</td>
                  <td class="num muted">${fmtSpread(g.closingSpreadHome)}</td>
                  <td>${resultBadge(g)}</td>
                </tr>`,
              )
              .join("")}</tbody>
          </table>`;

  const body = `
    <h1>Game history</h1>
    <p class="subtitle">Every ingested game for a season, with opening/closing home spreads and whether home covered the close. Raw data, not model output.</p>
    ${form(sport, season)}
    ${headline}
    ${table}
  `;
  return renderPage("Game history", body, "/games");
}
