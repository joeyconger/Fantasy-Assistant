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
