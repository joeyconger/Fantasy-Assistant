import { parseArgs, requireFlag } from "../ingest/cliArgs.js";
import { computeRatingsForSeason, computeRatingsForAllSeasons } from "./computeRatings.js";
import { predictWeek } from "./predict.js";
import { pool } from "../db/pool.js";
import type { Sport } from "../db/repo.js";

function requireSport(flags: Record<string, string>): Sport {
  const sport = requireFlag(flags, "sport");
  if (sport !== "nfl" && sport !== "cfb") {
    throw new Error(`--sport must be 'nfl' or 'cfb', got '${sport}'`);
  }
  return sport;
}

async function main() {
  const { command, flags } = parseArgs(process.argv.slice(2));
  const sport = requireSport(flags);

  switch (command) {
    case "compute": {
      if (flags.season) {
        const result = await computeRatingsForSeason(sport, Number(flags.season));
        console.log(
          `${sport} ${result.season}: ${result.gamesProcessed} games rated, ${result.gamesSkippedMissingStats} skipped (missing stats), ${result.teamsRated} teams rated`,
        );
      } else {
        const results = await computeRatingsForAllSeasons(sport);
        for (const result of results) {
          console.log(
            `${sport} ${result.season}: ${result.gamesProcessed} games rated, ${result.gamesSkippedMissingStats} skipped (missing stats), ${result.teamsRated} teams rated`,
          );
        }
      }
      break;
    }
    case "predict": {
      const season = Number(requireFlag(flags, "season"));
      const week = Number(requireFlag(flags, "week"));
      const result = await predictWeek(sport, season, week);
      console.log(`${sport} ${season} week ${week}: ${result.gamesPredicted} predictions generated`);
      break;
    }
    default:
      console.error(
        "usage: tsx src/ratings/index.ts <compute|predict> --sport nfl|cfb [--season 2024] [--week 5]\n" +
          "  compute --season is optional — omit it to (re)compute every season with final games, oldest first.\n" +
          "  predict requires both --season and --week.",
      );
      process.exitCode = 1;
  }

  await pool.end();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
