import { paramsForSport } from "../ratings/config.js";
import { predictSpread } from "../ratings/elo.js";
import type { RatingParams } from "../ratings/elo.js";
import { determinePickSide, computeCovered, computeClv } from "./clv.js";
import {
  getFinalGamesForBacktest,
  getTeamRatingBeforeWeek,
  getGamesPlayedCount,
  createBacktestRun,
  insertBacktestResult,
} from "../db/repo.js";
import type { Sport } from "../db/repo.js";

export interface BacktestParams {
  sport: Sport;
  seasonStart: number;
  seasonEnd: number;
  name: string;
  /**
   * Only affects prediction-time params (homeFieldAdvantage,
   * marketShrinkageK, baseErrorPoints) — team_ratings itself must already
   * have been computed with matching sosWeight/performanceWeight/
   * seasonCarryover for a sweep over THOSE params to mean anything (see
   * backtest/sweep.ts). Passing a different value here without
   * recomputing ratings first silently sweeps nothing for those three.
   */
  ratingParams?: RatingParams;
}

export interface RunBacktestResult {
  backtestRunId: number;
  gamesScored: number;
  gamesSkippedNoOdds: number;
}

/**
 * Replays every completed game in [seasonStart, seasonEnd], predicting each
 * one from the rating the team actually had before that week (via
 * getTeamRatingBeforeWeek — same as a live prediction would have seen,
 * team_ratings must already be computed for these seasons) and anchoring
 * to the OPENING line, then scoring the pick against the CLOSING line. A
 * game with no opening or closing line on file is skipped, not zero-filled
 * — silently treating "no odds ingested" as "no edge" would bias the
 * results.
 */
export async function runBacktest(input: BacktestParams): Promise<RunBacktestResult> {
  const params = input.ratingParams ?? paramsForSport(input.sport);
  const backtestRunId = await createBacktestRun({
    name: input.name,
    method: "elo",
    seasonStart: input.seasonStart,
    seasonEnd: input.seasonEnd,
    params: { sport: input.sport, ...params },
  });

  let gamesScored = 0;
  let gamesSkippedNoOdds = 0;

  for (let season = input.seasonStart; season <= input.seasonEnd; season += 1) {
    const games = await getFinalGamesForBacktest(input.sport, season);
    for (const game of games) {
      if (game.openingSpreadHome === null || game.closingSpreadHome === null) {
        gamesSkippedNoOdds += 1;
        continue;
      }

      const [homeRating, awayRating, homeGamesPlayed, awayGamesPlayed] = await Promise.all([
        getTeamRatingBeforeWeek(game.homeTeamId, input.sport, season, game.week),
        getTeamRatingBeforeWeek(game.awayTeamId, input.sport, season, game.week),
        getGamesPlayedCount(game.homeTeamId, input.sport, season, game.week - 1),
        getGamesPlayedCount(game.awayTeamId, input.sport, season, game.week - 1),
      ]);
      const prediction = predictSpread(
        { homeRating, awayRating, homeGamesPlayed, awayGamesPlayed, marketSpreadHome: game.openingSpreadHome },
        params,
      );

      const actualMarginHome = game.homeScore - game.awayScore;
      const pickSide = determinePickSide(prediction.modelSpreadHome, game.openingSpreadHome);
      const covered = pickSide ? computeCovered(pickSide, game.closingSpreadHome, actualMarginHome) : null;
      const clv = pickSide ? computeClv(pickSide, game.openingSpreadHome, game.closingSpreadHome) : null;

      await insertBacktestResult({
        backtestRunId,
        gameId: game.gameId,
        modelSpreadHome: prediction.modelSpreadHome,
        openingSpreadHome: game.openingSpreadHome,
        closingSpreadHome: game.closingSpreadHome,
        actualMarginHome,
        clv,
        covered,
        beatClose: clv === null ? null : clv > 0,
      });
      gamesScored += 1;
    }
  }

  return { backtestRunId, gamesScored, gamesSkippedNoOdds };
}
