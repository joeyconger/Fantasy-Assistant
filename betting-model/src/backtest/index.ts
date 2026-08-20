import { parseArgs, requireFlag } from "../ingest/cliArgs.js";
import { runBacktest } from "./run.js";
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

  switch (command) {
    case "run": {
      const sport = requireSport(flags);
      const seasonStart = Number(requireFlag(flags, "seasonStart"));
      const seasonEnd = Number(requireFlag(flags, "seasonEnd"));
      const name = flags.name ?? `${sport} ${seasonStart}-${seasonEnd}`;
      const result = await runBacktest({ sport, seasonStart, seasonEnd, name });
      console.log(
        `backtest run #${result.backtestRunId}: ${result.gamesScored} games scored, ${result.gamesSkippedNoOdds} skipped (no opening/closing line)`,
      );
      break;
    }
    default:
      console.error(
        "usage: tsx src/backtest/index.ts run --sport nfl|cfb --seasonStart 2022 --seasonEnd 2024 [--name 'my run']\n" +
          "  requires team_ratings already computed for these seasons (npm run ratings:compute first).",
      );
      process.exitCode = 1;
  }

  await pool.end();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
