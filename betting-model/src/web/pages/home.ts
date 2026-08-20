import { renderPage, statTiles, badge, sportChip, escapeHtml } from "../layout.js";
import type { BacktestRunSummary } from "../../db/repo.js";
import type { AggregateStats } from "../../backtest/report.js";

function fmtPct(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function coverTone(value: number | null): "good" | "bad" | "neutral" {
  if (value === null) return "neutral";
  return value >= 0.5 ? "good" : "bad";
}

export function renderHome(runs: BacktestRunSummary[], statsByRun: Map<number, AggregateStats>): string {
  const scored = runs.filter((r) => (statsByRun.get(r.id)?.games ?? 0) > 0);
  const best = scored.reduce<{ run: BacktestRunSummary; stats: AggregateStats } | null>((acc, run) => {
    const stats = statsByRun.get(run.id);
    if (!stats || stats.coverRate === null) return acc;
    if (!acc || (acc.stats.coverRate ?? 0) < stats.coverRate) return { run, stats };
    return acc;
  }, null);
  const totalGames = scored.reduce((sum, r) => sum + (statsByRun.get(r.id)?.games ?? 0), 0);

  const headline = statTiles([
    { label: "Backtest runs", value: String(runs.length) },
    { label: "Total games scored", value: totalGames.toLocaleString() },
    best
      ? {
          label: "Best cover rate",
          value: fmtPct(best.stats.coverRate),
          tone: coverTone(best.stats.coverRate),
          sub: `run #${best.run.id} · ${escapeHtml(best.run.name)}`,
        }
      : { label: "Best cover rate", value: "—" },
  ]);

  const rows = runs
    .map((run) => {
      const stats = statsByRun.get(run.id);
      const cover = stats?.coverRate ?? null;
      return `<tr>
        <td><a class="run-link" href="/backtest/${run.id}">#${run.id}</a></td>
        <td>${escapeHtml(run.name)}</td>
        <td>${sportChip(run.sport ?? "?")}</td>
        <td class="num">${run.seasonStart}–${run.seasonEnd}</td>
        <td class="num">${(stats?.games ?? 0).toLocaleString()}</td>
        <td class="num">${cover === null ? '<span class="muted">—</span>' : badge(fmtPct(cover), coverTone(cover))}</td>
        <td class="muted">${new Date(run.createdAt).toISOString().slice(0, 16).replace("T", " ")}</td>
      </tr>`;
    })
    .join("");

  const body = `
    <h1>Backtest runs</h1>
    <p class="subtitle">Every model run, replayed against real closing lines. Read-only diagnostics — not a picks feed.</p>
    <div class="banner">
      This is a diagnostics dashboard, not the live-picks app — Phase 4 (live picks) is
      still gated until the backtest shows real signal. <strong>Nothing here is a betting
      recommendation.</strong>
    </div>
    ${headline}
    ${
      runs.length === 0
        ? `<p class="muted">No backtest runs yet.</p>`
        : `<table>
            <thead><tr><th>Run</th><th>Name</th><th>Sport</th><th>Seasons</th><th>Games</th><th>Cover rate</th><th>Run at</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>`
    }
  `;
  return renderPage("Backtest runs", body, "/");
}
