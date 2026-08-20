import { paramsForSport } from "./config.js";
import { updateRatingsForGame, carryoverRating } from "./elo.js";
import {
  getSeasonsWithFinalGames,
  getFinalGamesWithStatsForSeason,
  getPriorSeasonFinalRating,
  upsertTeamRating,
  getGamesPlayedCount,
} from "../db/repo.js";
import type { Sport } from "../db/repo.js";

export interface ComputeRatingsResult {
  season: number;
  gamesProcessed: number;
  gamesSkippedMissingStats: number;
  teamsRated: number;
}

/**
 * Replays a season game-by-game in play order, updating each team's rating
 * after every game and snapshotting it into team_ratings at each week
 * boundary — so a backtest or the dashboard can ask "what did the model
 * think as of week N" without recomputing. Only teams that actually played
 * get a snapshot for a given week (a bye week doesn't produce a new row);
 * readers should carry the most recent prior row forward, which
 * getTeamRatingBeforeWeek already does.
 */
export async function computeRatingsForSeason(sport: Sport, season: number): Promise<ComputeRatingsResult> {
  const params = paramsForSport(sport);
  const games = await getFinalGamesWithStatsForSeason(sport, season);

  const ratings = new Map<number, number>();

  async function ratingFor(teamId: number): Promise<number> {
    const existing = ratings.get(teamId);
    if (existing !== undefined) return existing;
    const prior = await getPriorSeasonFinalRating(teamId, sport, season - 1);
    const initial = prior !== undefined ? carryoverRating(prior, params) : 0;
    ratings.set(teamId, initial);
    return initial;
  }

  let gamesProcessed = 0;
  let gamesSkippedMissingStats = 0;
  let currentWeek: number | null = null;
  const teamsSeenThisWeek = new Set<number>();
  const allTeamsSeen = new Set<number>();

  async function flushWeek(week: number): Promise<void> {
    for (const teamId of teamsSeenThisWeek) {
      const rating = ratings.get(teamId)!;
      const gamesPlayed = await getGamesPlayedCount(teamId, sport, season, week);
      const ratingError = params.baseErrorPoints / Math.sqrt(gamesPlayed + 1);
      await upsertTeamRating({ teamId, sport, season, throughWeek: week, rating, ratingError, method: "elo" });
    }
    teamsSeenThisWeek.clear();
  }

  for (const game of games) {
    if (currentWeek !== null && game.week !== currentWeek) {
      await flushWeek(currentWeek);
    }
    currentWeek = game.week;

    if (!game.homeStats || !game.awayStats) {
      gamesSkippedMissingStats += 1;
      continue;
    }

    const homeRating = await ratingFor(game.homeTeamId);
    const awayRating = await ratingFor(game.awayTeamId);
    const updated = updateRatingsForGame(
      { homeRating, awayRating, homePerf: game.homeStats, awayPerf: game.awayStats },
      params,
    );
    ratings.set(game.homeTeamId, updated.homeRating);
    ratings.set(game.awayTeamId, updated.awayRating);
    teamsSeenThisWeek.add(game.homeTeamId);
    teamsSeenThisWeek.add(game.awayTeamId);
    allTeamsSeen.add(game.homeTeamId);
    allTeamsSeen.add(game.awayTeamId);
    gamesProcessed += 1;
  }
  if (currentWeek !== null) {
    await flushWeek(currentWeek);
  }

  return { season, gamesProcessed, gamesSkippedMissingStats, teamsRated: allTeamsSeen.size };
}

export async function computeRatingsForAllSeasons(sport: Sport): Promise<ComputeRatingsResult[]> {
  const seasons = await getSeasonsWithFinalGames(sport);
  const results: ComputeRatingsResult[] = [];
  for (const season of seasons) {
    // Seasons must process in order — each season's carryover reads the
    // previous season's final rating out of team_ratings.
    results.push(await computeRatingsForSeason(sport, season));
  }
  return results;
}
