import { escapeHtml } from "./layout.js";

export interface CoverRateBar {
  label: string;
  coverRate: number | null; // 0-1, null renders as n/a
  games: number;
}

const CHART_HEIGHT = 160;
const BAR_TOP = 12;
const BAR_BOTTOM = 128;
const BASELINE_Y = BAR_BOTTOM - (BAR_BOTTOM - BAR_TOP) * 0.5; // 50% reference line

/**
 * A row of thin vertical bars showing cover rate against the 50% baseline
 * (the breakeven line after vig — a bar poking above it is the visual
 * "is this doing anything" signal). Per the dataviz mark spec: thin marks,
 * rounded data-ends, a dashed baseline, and selective direct labels
 * (always shown here since bar count stays small).
 */
export function coverRateBarChart(bars: CoverRateBar[]): string {
  const width = Math.max(320, bars.length * 90);
  const barWidth = Math.min(46, (width - 24) / bars.length - 16);
  const step = (width - 24) / bars.length;

  const barsSvg = bars
    .map((b, i) => {
      const cx = 12 + step * i + step / 2;
      const x = cx - barWidth / 2;
      if (b.coverRate === null) {
        return `
          <text x="${cx}" y="${(BAR_TOP + BAR_BOTTOM) / 2}" text-anchor="middle" class="chart-na-label">n/a</text>
          <text x="${cx}" y="${CHART_HEIGHT - 6}" text-anchor="middle" class="chart-axis-label">${escapeHtml(b.label)}</text>
        `;
      }
      const clamped = Math.max(0, Math.min(1, b.coverRate));
      const barTop = BAR_TOP + (BAR_BOTTOM - BAR_TOP) * (1 - clamped);
      const isGood = clamped >= 0.5;
      const barY = isGood ? barTop : BASELINE_Y;
      const barHeight = Math.max(2, Math.abs(BASELINE_Y - barTop));
      const labelY = isGood ? barTop - 6 : barTop + 14;
      return `
        <rect x="${x}" y="${barY}" width="${barWidth}" height="${barHeight}" rx="4"
              class="${isGood ? "chart-bar-good" : "chart-bar-bad"}" />
        <text x="${cx}" y="${labelY}" text-anchor="middle" class="chart-value-label">${(clamped * 100).toFixed(1)}%</text>
        <text x="${cx}" y="${CHART_HEIGHT - 6}" text-anchor="middle" class="chart-axis-label">${escapeHtml(b.label)}</text>
        <text x="${cx}" y="${CHART_HEIGHT + 8}" text-anchor="middle" class="chart-na-label">n=${b.games}</text>
      `;
    })
    .join("");

  return `
    <svg viewBox="0 0 ${width} ${CHART_HEIGHT + 20}" width="100%" role="img" aria-label="Cover rate by segment, 50% baseline">
      <line x1="12" y1="${BASELINE_Y}" x2="${width - 12}" y2="${BASELINE_Y}" class="chart-baseline-line" />
      ${barsSvg}
    </svg>
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
 * direct labels only at the first/last/peak/trough points (this dashboard
 * has no JS, so there's no hover layer to lean on instead — see
 * references/interaction.md's fallback for static output).
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

  // Sparse x-axis labels so they don't collide -- roughly every ~8th point, plus
  // the last (skipping a regular tick that would land too close to it), with
  // anchors flipped at the edges so labels don't clip past the viewBox.
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
    <svg viewBox="0 0 ${width} ${LINE_HEIGHT}" width="100%" role="img" aria-label="Rating trend over time">
      <line x1="12" y1="${zeroY.toFixed(1)}" x2="${width - 12}" y2="${zeroY.toFixed(1)}" class="chart-baseline-line" />
      <path d="${pathD}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
      ${dotsAndLabels}
      ${xLabels}
    </svg>
  `;
}
