import { randomUUID } from "node:crypto";
import { syncCfbdTeams } from "./ingest/cfbd/syncTeams.js";
import { syncCfbdGames } from "./ingest/cfbd/syncGames.js";
import { syncCfbdGameStats } from "./ingest/cfbd/syncStats.js";
import { syncNflSchedules } from "./ingest/nflverse/syncSchedules.js";
import { syncNflPbpStats } from "./ingest/nflverse/syncPbpStats.js";
import { syncCurrentOdds } from "./ingest/odds/syncCurrentOdds.js";
import { syncCurrentInjuries } from "./ingest/injuries/syncInjuries.js";
import { syncNflWeather } from "./ingest/weather/syncWeather.js";
import { computeRatingsForSeason, computeRatingsForAllSeasons } from "./ratings/computeRatings.js";
import { predictWeek } from "./ratings/predict.js";
import { runBacktest } from "./backtest/run.js";
import { runParamSweep } from "./backtest/sweep.js";
import { paramsForSport } from "./ratings/config.js";
import type { RatingParams } from "./ratings/elo.js";
import type { Sport } from "./db/repo.js";

// Background job pattern for Railway: a long-running ingest/compute/backtest
// job triggered inline inside an HTTP request risks the platform's
// healthcheck timing it out, so every admin action here returns
// immediately (202 + job id) and runs to completion in the background —
// poll GET /admin/jobs/:id for status and log lines.

export interface Job {
  id: string;
  name: string;
  status: "running" | "done" | "failed";
  startedAt: string;
  finishedAt: string | null;
  log: string[];
  error: string | null;
}

const jobs = new Map<string, Job>();

export function listJobs(): Job[] {
  return [...jobs.values()].sort((a, b) => b.startedAt.localeCompare(a.startedAt));
}

export function getJob(id: string): Job | undefined {
  return jobs.get(id);
}

export function log(job: Job, message: string): void {
  const line = `[${new Date().toISOString()}] ${message}`;
  job.log.push(line);
  console.log(`[job ${job.name} ${job.id}] ${message}`);
}

function runJob(name: string, fn: (job: Job) => Promise<void>): Job {
  const job: Job = {
    id: randomUUID(),
    name,
    status: "running",
    startedAt: new Date().toISOString(),
    finishedAt: null,
    log: [],
    error: null,
  };
  jobs.set(job.id, job);
  fn(job)
    .then(() => {
      job.status = "done";
      job.finishedAt = new Date().toISOString();
    })
    .catch((err) => {
      job.status = "failed";
      job.error = (err as Error).message;
      job.finishedAt = new Date().toISOString();
      log(job, `ERROR: ${(err as Error).message}`);
    });
  return job;
}

function requireSport(params: Record<string, unknown>): Sport {
  const sport = params.sport;
  if (sport !== "nfl" && sport !== "cfb") throw new Error(`params.sport must be 'nfl' or 'cfb', got '${String(sport)}'`);
  return sport;
}

function requireNumber(params: Record<string, unknown>, key: string): number {
  const value = Number(params[key]);
  if (Number.isNaN(value)) throw new Error(`params.${key} must be a number`);
  return value;
}

export type JobStarter = (params: Record<string, unknown>) => Job;

export const JOB_STARTERS: Record<string, JobStarter> = {
  "ingest-cfbd-teams": (params) =>
    runJob("ingest-cfbd-teams", async (job) => {
      const year = requireNumber(params, "year");
      const count = await syncCfbdTeams(year);
      log(job, `synced ${count} CFB teams for ${year}`);
    }),
  "ingest-cfbd-games": (params) =>
    runJob("ingest-cfbd-games", async (job) => {
      const year = requireNumber(params, "year");
      const seasonType = (params.seasonType as "regular" | "postseason") ?? "regular";
      const { synced, skipped } = await syncCfbdGames(year, seasonType);
      log(job, `synced ${synced} CFB games for ${year} (${seasonType}), skipped ${skipped}`);
    }),
  "ingest-cfbd-stats": (params) =>
    runJob("ingest-cfbd-stats", async (job) => {
      const year = requireNumber(params, "year");
      const seasonType = (params.seasonType as "regular" | "postseason") ?? "regular";
      const { synced, skipped } = await syncCfbdGameStats(year, seasonType);
      log(job, `synced ${synced} CFB team-game stat rows for ${year} (${seasonType}), skipped ${skipped}`);
    }),
  "ingest-nfl-schedules": (params) =>
    runJob("ingest-nfl-schedules", async (job) => {
      const season = requireNumber(params, "season");
      const { synced } = await syncNflSchedules(season);
      log(job, `synced ${synced} NFL games for ${season}`);
    }),
  "ingest-nfl-stats": (params) =>
    runJob("ingest-nfl-stats", async (job) => {
      const season = requireNumber(params, "season");
      const { synced, skipped } = await syncNflPbpStats(season);
      log(job, `synced ${synced} NFL team-game stat rows for ${season}, skipped ${skipped}`);
    }),
  "ingest-odds-current": (params) =>
    runJob("ingest-odds-current", async (job) => {
      const sport = requireSport(params);
      const { synced, skipped } = await syncCurrentOdds(sport);
      log(job, `synced ${synced} current-odds snapshots for ${sport}, skipped ${skipped}`);
    }),
  "ingest-injuries-current": (params) =>
    runJob("ingest-injuries-current", async (job) => {
      const sport = requireSport(params);
      const { synced, skipped } = await syncCurrentInjuries(sport);
      log(job, `synced ${synced} injury reports for ${sport}, skipped ${skipped}`);
    }),
  "ingest-weather": () =>
    runJob("ingest-weather", async (job) => {
      const { synced, skipped } = await syncNflWeather();
      log(job, `synced ${synced} NFL weather forecasts, skipped ${skipped}`);
    }),
  "ratings-compute": (params) =>
    runJob("ratings-compute", async (job) => {
      const sport = requireSport(params);
      if (params.season !== undefined) {
        const season = requireNumber(params, "season");
        const result = await computeRatingsForSeason(sport, season);
        log(
          job,
          `${sport} ${result.season}: ${result.gamesProcessed} games rated, ${result.gamesSkippedMissingStats} skipped, ${result.teamsRated} teams`,
        );
      } else {
        const results = await computeRatingsForAllSeasons(sport);
        for (const result of results) {
          log(
            job,
            `${sport} ${result.season}: ${result.gamesProcessed} games rated, ${result.gamesSkippedMissingStats} skipped, ${result.teamsRated} teams`,
          );
        }
      }
    }),
  "ratings-predict": (params) =>
    runJob("ratings-predict", async (job) => {
      const sport = requireSport(params);
      const season = requireNumber(params, "season");
      const week = requireNumber(params, "week");
      const result = await predictWeek(sport, season, week);
      log(job, `${sport} ${season} week ${week}: ${result.gamesPredicted} predictions generated`);
    }),
  "backtest-run": (params) =>
    runJob("backtest-run", async (job) => {
      const sport = requireSport(params);
      const seasonStart = requireNumber(params, "seasonStart");
      const seasonEnd = requireNumber(params, "seasonEnd");
      const name = typeof params.name === "string" ? params.name : `${sport} ${seasonStart}-${seasonEnd}`;
      const result = await runBacktest({ sport, seasonStart, seasonEnd, name });
      log(job, `run #${result.backtestRunId}: ${result.gamesScored} games scored, ${result.gamesSkippedNoOdds} skipped (no odds)`);
    }),
  "backtest-sweep": (params) =>
    runJob("backtest-sweep", async (job) => {
      const sport = requireSport(params);
      const seasonStart = requireNumber(params, "seasonStart");
      const seasonEnd = requireNumber(params, "seasonEnd");
      const param = params.param as keyof RatingParams;
      const base = paramsForSport(sport);
      if (!(param in base)) throw new Error(`params.param must be one of: ${Object.keys(base).join(", ")}`);
      const values = params.values;
      if (!Array.isArray(values)) throw new Error("params.values must be an array of numbers");
      const variants = values.map((value) => ({ label: `${param}=${value}`, params: { ...base, [param]: Number(value) } }));
      log(job, `sweeping ${param} over [${values.join(", ")}] for ${sport} ${seasonStart}-${seasonEnd}`);
      const results = await runParamSweep(sport, seasonStart, seasonEnd, variants);
      for (const r of results) {
        log(
          job,
          `${r.label}: run #${r.backtestRunId}, ${r.gamesScored} games, cover(close)=${r.overall.coverRate?.toFixed(3) ?? "n/a"}, cover(open)=${r.openingCover.coverRate?.toFixed(3) ?? "n/a"}, avgClv=${r.overall.avgClv?.toFixed(3) ?? "n/a"}`,
        );
      }
      log(
        job,
        `NOTE: team_ratings for ${sport} ${seasonStart}-${seasonEnd} now reflects the LAST variant tried — re-run ratings-compute with your chosen params before trusting that data outside this sweep.`,
      );
    }),
};
