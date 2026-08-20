import type { RatingParams } from "./elo.js";
import type { Sport } from "../db/repo.js";

// Starting defaults — chosen for plausibility (home-field advantage in the
// range consensus market data typically shows, SOS bounds tight enough to
// not blow up on an outlier opponent, shrinkage that lets the market
// dominate early season and the model earn weight as games accumulate).
// NOT backtested: this repo has no ingested historical odds/results yet, so
// none of these numbers have been calibrated or walk-forward validated.
// Re-run a calibration sweep against real data (see backtest/sweep.ts once
// Phase 3 exists) before trusting these for anything beyond diagnostics.
export const NFL_PARAMS: RatingParams = {
  homeFieldAdvantage: 1.5,
  performanceWeight: 0.2,
  pointsPerEpa: 25,
  sosWeight: 0.25,
  minSosMultiplier: 0.7,
  maxSosMultiplier: 1.5,
  ratingScaleRef: 10,
  seasonCarryover: 0.6,
  marketShrinkageK: 8,
  baseErrorPoints: 10,
};

// CFB gets a heavier SOS weight than NFL (wider talent gaps top to bottom
// of FBS than across the NFL), a lower market-shrinkage K (fewer games per
// season means less time to earn weight away from the market), and a
// bigger home-field number (documented as generally larger in CFB).
export const CFB_PARAMS: RatingParams = {
  ...NFL_PARAMS,
  homeFieldAdvantage: 2.5,
  sosWeight: 0.4,
  marketShrinkageK: 6,
  ratingScaleRef: 15,
};

export function paramsForSport(sport: Sport): RatingParams {
  return sport === "cfb" ? CFB_PARAMS : NFL_PARAMS;
}
