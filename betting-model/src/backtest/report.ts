import { pool } from "../db/pool.js";

export interface AggregateStats {
  games: number;
  decidedGames: number; // games where the model actually disagreed with the opening line (a pick was made)
  coverRate: number | null; // vs. CLOSING line — a diagnostic, not a real-money answer (see getOpeningCoverRate)
  avgClv: number | null;
  beatCloseRate: number | null;
}

const AGGREGATE_SELECT = `
  count(*)::int AS games,
  count(*) FILTER (WHERE covered IS NOT NULL)::int AS decided_games,
  count(*) FILTER (WHERE covered = true)::int AS covers,
  avg(clv) AS avg_clv,
  count(*) FILTER (WHERE beat_close IS NOT NULL)::int AS beat_close_decided,
  count(*) FILTER (WHERE beat_close = true)::int AS beat_close_games
`;

interface AggregateRow {
  games: number;
  decided_games: number;
  covers: number;
  avg_clv: number | null;
  beat_close_decided: number;
  beat_close_games: number;
}

function toAggregateStats(row: AggregateRow): AggregateStats {
  return {
    games: row.games,
    decidedGames: row.decided_games,
    coverRate: row.decided_games > 0 ? row.covers / row.decided_games : null,
    avgClv: row.avg_clv,
    beatCloseRate: row.beat_close_decided > 0 ? row.beat_close_games / row.beat_close_decided : null,
  };
}

export async function getOverallReport(backtestRunId: number): Promise<AggregateStats> {
  const result = await pool.query<AggregateRow>(
    `SELECT ${AGGREGATE_SELECT} FROM backtest_results WHERE backtest_run_id = $1`,
    [backtestRunId],
  );
  return toAggregateStats(result.rows[0]!);
}

export interface OpeningCoverStats {
  decidedGames: number;
  coverRate: number | null;
}

/**
 * The real "would this have made money" answer: cover rate against the
 * OPENING line (the price actually available at bet time), not the
 * closing line. Deliberately kept separate from getOverallReport's
 * coverRate — conflating the two double-counts market movement as if it
 * were model skill. See backtest/clv.ts for why pick side is always
 * determined against the opening line.
 */
export async function getOpeningCoverRate(backtestRunId: number): Promise<OpeningCoverStats> {
  const result = await pool.query<{ decided_games: number; covers: number }>(
    `SELECT
       count(*) FILTER (WHERE pick_side IS NOT NULL)::int AS decided_games,
       count(*) FILTER (WHERE covered_opening = true)::int AS covers
     FROM (
       SELECT
         CASE WHEN model_spread_home = opening_spread_home THEN NULL
              WHEN model_spread_home < opening_spread_home THEN 'home' ELSE 'away' END AS pick_side,
         CASE
           WHEN model_spread_home = opening_spread_home THEN NULL
           WHEN (actual_margin_home + opening_spread_home) = 0 THEN NULL
           WHEN model_spread_home < opening_spread_home THEN (actual_margin_home + opening_spread_home) > 0
           ELSE (actual_margin_home + opening_spread_home) < 0
         END AS covered_opening
       FROM backtest_results
       WHERE backtest_run_id = $1 AND opening_spread_home IS NOT NULL
     ) t`,
    [backtestRunId],
  );
  const row = result.rows[0]!;
  return { decidedGames: row.decided_games, coverRate: row.decided_games > 0 ? row.covers / row.decided_games : null };
}

export interface ThresholdStats extends AggregateStats {
  minDeviation: number;
}

const DEVIATION_THRESHOLDS = [0, 1, 2, 3, 5];

/** Cover rate/CLV filtered to games where the model disagreed with the opening line by at least N points — do bigger disagreements carry more signal, or just more noise? */
export async function getThresholdReport(backtestRunId: number): Promise<ThresholdStats[]> {
  const rows = await Promise.all(
    DEVIATION_THRESHOLDS.map(async (minDeviation) => {
      const result = await pool.query<AggregateRow>(
        `SELECT ${AGGREGATE_SELECT} FROM backtest_results
         WHERE backtest_run_id = $1 AND abs(model_spread_home - opening_spread_home) >= $2`,
        [backtestRunId, minDeviation],
      );
      return { minDeviation, ...toAggregateStats(result.rows[0]!) };
    }),
  );
  return rows;
}

export interface SeasonStats extends AggregateStats {
  season: number;
}

export async function getSeasonReport(backtestRunId: number): Promise<SeasonStats[]> {
  const result = await pool.query<AggregateRow & { season: number }>(
    `SELECT g.season, ${AGGREGATE_SELECT}
     FROM backtest_results br JOIN games g ON g.id = br.game_id
     WHERE br.backtest_run_id = $1
     GROUP BY g.season
     ORDER BY g.season ASC`,
    [backtestRunId],
  );
  return result.rows.map((row) => ({ season: row.season, ...toAggregateStats(row) }));
}
