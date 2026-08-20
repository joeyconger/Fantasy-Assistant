import type { RatingParams } from "../ratings/elo.js";
import { computeRatingsForSeason } from "../ratings/computeRatings.js";
import { runBacktest } from "./run.js";
import { getOverallReport, getOpeningCoverRate } from "./report.js";
import type { AggregateStats, OpeningCoverStats } from "./report.js";
import type { Sport } from "../db/repo.js";

export interface ParamVariant {
  label: string;
  params: RatingParams;
}

export interface SweepResult {
  label: string;
  backtestRunId: number;
  gamesScored: number;
  overall: AggregateStats;
  openingCover: OpeningCoverStats;
}

/**
 * Compares full RatingParams variants against each other on the same
 * season range. IMPORTANT and easy to get wrong (see backtest/run.ts's
 * BacktestParams.ratingParams doc): a variant's sosWeight,
 * performanceWeight, and seasonCarryover only take effect if ratings are
 * actually recomputed with that variant's params — predictSpread alone
 * can't retroactively change how team_ratings was built. So this sweep
 * recomputes team_ratings for [seasonStart, seasonEnd] with each variant's
 * params before backtesting it. It deliberately does NOT recompute
 * seasonStart-1 (the season carryover reads from) for every variant — that
 * would cascade into recomputing all of history — so every variant shares
 * the same seasonStart-1 anchor already on file. That keeps variants
 * comparable to each other, but means the very first season in the range
 * only partially reflects the swept params (its carryover input doesn't).
 * Include a season before the one you actually care about if that matters.
 *
 * Side effect: after this runs, team_ratings for [seasonStart, seasonEnd]
 * holds whichever variant ran LAST, not the "canonical" params — re-run
 * `ratings:compute` for those seasons once you've picked a winner.
 */
export async function runParamSweep(
  sport: Sport,
  seasonStart: number,
  seasonEnd: number,
  variants: ParamVariant[],
): Promise<SweepResult[]> {
  const results: SweepResult[] = [];
  for (const variant of variants) {
    for (let season = seasonStart; season <= seasonEnd; season += 1) {
      await computeRatingsForSeason(sport, season, variant.params);
    }
    const backtest = await runBacktest({
      sport,
      seasonStart,
      seasonEnd,
      name: `sweep: ${variant.label}`,
      ratingParams: variant.params,
    });
    const [overall, openingCover] = await Promise.all([
      getOverallReport(backtest.backtestRunId),
      getOpeningCoverRate(backtest.backtestRunId),
    ]);
    results.push({
      label: variant.label,
      backtestRunId: backtest.backtestRunId,
      gamesScored: backtest.gamesScored,
      overall,
      openingCover,
    });
  }
  return results;
}
