import { escapeHtml } from "./layout.js";

export interface CoverRateBar {
  label: string;
  coverRate: number | null;
  games: number;
}

/**
 * Single-series bar chart, cover rate (0-1) against a 50% baseline —
 * built as inline SVG per this project's "no heavy framework" rule (no
 * charting library dependency). One series, so no legend is needed per
 * the dataviz skill's rules; a native <title> element gives each bar a
 * real hover tooltip without any JS.
 */
export function renderCoverRateChart(bars: CoverRateBar[], baseline = 0.5): string {
  const width = 640;
  const height = 200;
  const paddingLeft = 8;
  const paddingRight = 8;
  const paddingTop = 20;
  const paddingBottom = 28;
  const plotWidth = width - paddingLeft - paddingRight;
  const plotHeight = height - paddingTop - paddingBottom;
  const gap = 10;
  const maxBarWidth = 90;
  const barWidth = Math.min(maxBarWidth, (plotWidth - gap * (bars.length - 1)) / bars.length);
  const groupWidth = bars.length * barWidth + (bars.length - 1) * gap;
  const groupLeft = paddingLeft + (plotWidth - groupWidth) / 2;
  const baselineY = paddingTop + plotHeight * (1 - baseline);

  const bars_svg = bars
    .map((bar, i) => {
      const x = groupLeft + i * (barWidth + gap);
      const axisLabel = `<text x="${x + barWidth / 2}" y="${height - 8}" text-anchor="middle" class="chart-axis-label">${escapeHtml(bar.label)}</text>`;

      if (bar.coverRate === null || bar.games === 0) {
        return `${axisLabel}<text x="${x + barWidth / 2}" y="${paddingTop + plotHeight / 2}" text-anchor="middle" class="chart-na-label">n/a</text>`;
      }

      const barHeight = Math.max(plotHeight * bar.coverRate, 1);
      const y = paddingTop + plotHeight - barHeight;
      const fillClass = bar.coverRate >= baseline ? "chart-bar-good" : "chart-bar-bad";
      const pct = (bar.coverRate * 100).toFixed(1);

      return `
        <rect x="${x}" y="${y}" width="${barWidth}" height="${barHeight}" rx="3" class="${fillClass}">
          <title>${escapeHtml(bar.label)}: ${pct}% cover rate (${bar.games} games)</title>
        </rect>
        <text x="${x + barWidth / 2}" y="${y - 5}" text-anchor="middle" class="chart-value-label">${pct}%</text>
        ${axisLabel}
      `;
    })
    .join("");

  return `
    <div class="chart-card">
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="cover rate by bucket, dashed line marks the 50% no-edge baseline" style="width:100%; height:auto; display:block;">
        <line x1="${paddingLeft}" y1="${baselineY}" x2="${width - paddingRight}" y2="${baselineY}" class="chart-baseline-line" />
        <text x="${width - paddingRight}" y="${baselineY - 4}" text-anchor="end" class="chart-axis-label">50%</text>
        ${bars_svg}
      </svg>
    </div>
  `;
}

export interface RatingPoint {
  label: string; // e.g. "2023 wk 4"
  rating: number;
}

const LINE_HEIGHT = 180;
const LINE_TOP = 16;
const LINE_BOTTOM = 140;

/**
 * A single team's rating trajectory over time — a 2px line, thin dots at
 * each point, a dashed zero baseline (the "league average" reference), and
 * direct labels only at the first/last/peak/trough points (no JS hover
 * layer here — see renderCoverRateChart's native <title> tooltip for the
 * bar-chart equivalent; a <title> on every point of a dense line would be
 * noisy, so this uses selective direct labels instead).
 */
export function ratingTrendChart(points: RatingPoint[]): string {
  if (points.length === 0) {
    return `<p class="muted">No rating history yet.</p>`;
  }
  const width = Math.max(360, points.length * 28);
  const values = points.map((p) => p.rating);
  const maxAbs = Math.max(1e-9, ...values.map((v) => Math.abs(v)));
  const yFor = (rating: number) => LINE_TOP + (LINE_BOTTOM - LINE_TOP) * (1 - (rating + maxAbs) / (2 * maxAbs));
  const xStep = points.length > 1 ? (width - 24) / (points.length - 1) : 0;
  const xFor = (i: number) => 12 + xStep * i;
  const zeroY = yFor(0);

  const pathD = points.map((p, i) => `${i === 0 ? "M" : "L"}${xFor(i).toFixed(1)},${yFor(p.rating).toFixed(1)}`).join(" ");

  const maxIdx = values.indexOf(Math.max(...values));
  const minIdx = values.indexOf(Math.min(...values));
  const lastIdx = points.length - 1;
  const labeledIndices = new Set([0, lastIdx, maxIdx, minIdx]);

  const dotsAndLabels = points
    .map((p, i) => {
      const cx = xFor(i);
      const cy = yFor(p.rating);
      const dot = `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="2.5" fill="var(--accent)" />`;
      if (!labeledIndices.has(i)) return dot;
      const labelY = cy < zeroY ? cy - 8 : cy + 14;
      const anchor = i === 0 ? "start" : i === lastIdx ? "end" : "middle";
      return `${dot}<text x="${cx.toFixed(1)}" y="${labelY.toFixed(1)}" text-anchor="${anchor}" class="chart-value-label">${p.rating >= 0 ? "+" : ""}${p.rating.toFixed(1)}</text>`;
    })
    .join("");

  // Sparse x-axis labels so they don't collide -- roughly every ~8th point,
  // plus the last (skipping a regular tick that would land too close to
  // it), with anchors flipped at the edges so labels don't clip past the
  // viewBox.
  const tickEvery = Math.max(1, Math.ceil(points.length / 8));
  const anchorFor = (i: number) => (i === 0 ? "start" : i === lastIdx ? "end" : "middle");
  const xLabels = points
    .map((p, i) => {
      const isRegularTick = i % tickEvery === 0 && lastIdx - i >= tickEvery;
      if (!isRegularTick && i !== lastIdx) return "";
      return `<text x="${xFor(i).toFixed(1)}" y="${LINE_HEIGHT - 4}" text-anchor="${anchorFor(i)}" class="chart-axis-label">${escapeHtml(p.label)}</text>`;
    })
    .join("");

  return `
    <div class="chart-card">
      <svg viewBox="0 0 ${width} ${LINE_HEIGHT}" width="100%" role="img" aria-label="Rating trend over time">
        <line x1="12" y1="${zeroY.toFixed(1)}" x2="${width - 12}" y2="${zeroY.toFixed(1)}" class="chart-baseline-line" />
        <path d="${pathD}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
        ${dotsAndLabels}
        ${xLabels}
      </svg>
    </div>
  `;
}
