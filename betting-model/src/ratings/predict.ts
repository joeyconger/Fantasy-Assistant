import { paramsForSport } from "./config.js";
import { predictSpread } from "./elo.js";
import {
  getGamesForWeek,
  getMarketSpreadHome,
  getGamesPlayedCount,
  getTeamRatingBeforeWeek,
  insertModelPrediction,
} from "../db/repo.js";
import type { Sport } from "../db/repo.js";

export interface PredictWeekResult {
  gamesPredicted: number;
}

/** Generates and stores this model's prediction for every game in a week, anchored to whatever market line exists at call time. */
export async function predictWeek(sport: Sport, season: number, week: number): Promise<PredictWeekResult> {
  const params = paramsForSport(sport);
  const games = await getGamesForWeek(sport, season, week);

  let gamesPredicted = 0;
  for (const game of games) {
    const [homeRating, awayRating, homeGamesPlayed, awayGamesPlayed, marketSpreadHome] = await Promise.all([
      getTeamRatingBeforeWeek(game.homeTeamId, sport, season, week),
      getTeamRatingBeforeWeek(game.awayTeamId, sport, season, week),
      getGamesPlayedCount(game.homeTeamId, sport, season, week - 1),
      getGamesPlayedCount(game.awayTeamId, sport, season, week - 1),
      getMarketSpreadHome(game.gameId),
    ]);
    const prediction = predictSpread(
      { homeRating, awayRating, homeGamesPlayed, awayGamesPlayed, marketSpreadHome },
      params,
    );
    await insertModelPrediction({
      gameId: game.gameId,
      method: "elo",
      modelSpreadHome: prediction.modelSpreadHome,
      modelTotal: null,
      confidence: prediction.confidence,
      marketSpreadHome,
    });
    gamesPredicted += 1;
  }
  return { gamesPredicted };
}
