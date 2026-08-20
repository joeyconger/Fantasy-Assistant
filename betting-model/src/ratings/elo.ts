// EPA-driven, market-anchored Elo-like rating system.
//
// Each team has a rating in points (comparable to a spread). After each
// game, both teams' ratings move toward what their EPA/play performance
// actually implied about the margin, scaled by a strength-of-schedule
// multiplier — the same mechanism as classic Elo's "surprise factor," but
// driven by EPA differential instead of win/loss.

export interface RatingParams {
  homeFieldAdvantage: number; // points added to the home team's expected margin
  performanceWeight: number; // fraction of a game's "surprise" absorbed into rating (Elo K-factor analog)
  pointsPerEpa: number; // scales EPA/play differential into point-equivalent margin
  sosWeight: number; // how strongly opponent rating scales a game's update weight
  minSosMultiplier: number; // floor on the SOS multiplier — a weak opponent still counts for something
  maxSosMultiplier: number; // ceiling on the SOS multiplier — an elite opponent can't blow up a single update
  ratingScaleRef: number; // reference rating magnitude the SOS multiplier normalizes against
  seasonCarryover: number; // fraction of a team's final rating carried into the next season (rest regresses to 0)
  marketShrinkageK: number; // shrinkage constant for market-anchored blending in predictSpread
  baseErrorPoints: number; // model confidence at 0 games played, shrinking as sqrt(gamesPlayed)
}

export interface TeamGamePerformance {
  offEpaPlay: number; // this team's offensive EPA/play in the game
  defEpaPlay: number; // this team's defensive EPA/play allowed in the game (lower/more negative = better defense)
}

export function netPerformance(perf: TeamGamePerformance): number {
  return perf.offEpaPlay - perf.defEpaPlay;
}

export function sosMultiplier(opponentRating: number, params: RatingParams): number {
  return Math.min(
    params.maxSosMultiplier,
    Math.max(params.minSosMultiplier, 1 + params.sosWeight * (opponentRating / params.ratingScaleRef)),
  );
}

export interface RatingUpdateInput {
  homeRating: number;
  awayRating: number;
  homePerf: TeamGamePerformance;
  awayPerf: TeamGamePerformance;
}

export interface RatingUpdateResult {
  homeRating: number;
  awayRating: number;
}

export function updateRatingsForGame(input: RatingUpdateInput, params: RatingParams): RatingUpdateResult {
  const perfMarginHome = params.pointsPerEpa * (netPerformance(input.homePerf) - netPerformance(input.awayPerf));
  const expectedMarginHome = input.homeRating - input.awayRating + params.homeFieldAdvantage;
  const surprise = perfMarginHome - expectedMarginHome;
  const homeMult = sosMultiplier(input.awayRating, params);
  const awayMult = sosMultiplier(input.homeRating, params);
  return {
    homeRating: input.homeRating + params.performanceWeight * homeMult * surprise,
    awayRating: input.awayRating - params.performanceWeight * awayMult * surprise,
  };
}

export function carryoverRating(priorFinalRating: number, params: RatingParams): number {
  return priorFinalRating * params.seasonCarryover;
}

export interface PredictionInput {
  homeRating: number;
  awayRating: number;
  homeGamesPlayed: number;
  awayGamesPlayed: number;
  marketSpreadHome: number | null; // negative = home favored, matching odds_snapshots.spread_home convention
}

export interface Prediction {
  eloSpreadHome: number; // this model's spread with no market anchoring at all
  modelSpreadHome: number; // market-anchored final number
  modelWeight: number; // how much of modelSpreadHome came from the Elo side (1 = pure Elo, no market line available)
  confidence: number; // model's own error estimate in points — smaller is more confident
}

export function predictSpread(input: PredictionInput, params: RatingParams): Prediction {
  const predictedMargin = input.homeRating - input.awayRating + params.homeFieldAdvantage;
  const eloSpreadHome = -predictedMargin;
  const combinedGames = input.homeGamesPlayed + input.awayGamesPlayed;
  const confidence = params.baseErrorPoints / Math.sqrt(combinedGames + 1);

  if (input.marketSpreadHome === null) {
    return { eloSpreadHome, modelSpreadHome: eloSpreadHome, modelWeight: 1, confidence };
  }
  const modelWeight = combinedGames / (combinedGames + params.marketShrinkageK);
  const modelSpreadHome = modelWeight * eloSpreadHome + (1 - modelWeight) * input.marketSpreadHome;
  return { eloSpreadHome, modelSpreadHome, modelWeight, confidence };
}
