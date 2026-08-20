import { parseArgs, requireFlag } from "../ingest/cliArgs.js";
import { runBacktest } from "./run.js";
import { runParamSweep } from "./sweep.js";
import { paramsForSport } from "../ratings/config.js";
import type { RatingParams } from "../ratings/elo.js";
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
    case "sweep": {
      const sport = requireSport(flags);
      const seasonStart = Number(requireFlag(flags, "seasonStart"));
      const seasonEnd = Number(requireFlag(flags, "seasonEnd"));
      const param = requireFlag(flags, "param") as keyof RatingParams;
      const base = paramsForSport(sport);
      if (!(param in base)) {
        throw new Error(`--param must be one of: ${Object.keys(base).join(", ")}`);
      }
      const values = requireFlag(flags, "values").split(",").map(Number);
      const variants = values.map((value) => ({
        label: `${param}=${value}`,
        params: { ...base, [param]: value },
      }));
      const results = await runParamSweep(sport, seasonStart, seasonEnd, variants);
      for (const r of results) {
        console.log(
          `${r.label}: run #${r.backtestRunId}, ${r.gamesScored} games, cover(close)=${r.overall.coverRate?.toFixed(3) ?? "n/a"}, cover(open)=${r.openingCover.coverRate?.toFixed(3) ?? "n/a"}, avgClv=${r.overall.avgClv?.toFixed(3) ?? "n/a"}`,
        );
      }
      console.log(
        `NOTE: team_ratings for ${sport} ${seasonStart}-${seasonEnd} now reflects the LAST variant (${variants[variants.length - 1]!.label}) — re-run 'ratings:compute' with your chosen final params before using this data outside the sweep.`,
      );
      break;
    }
    default:
      console.error(
        "usage: tsx src/backtest/index.ts <run|sweep> --sport nfl|cfb --seasonStart 2022 --seasonEnd 2024\n" +
          "  run   [--name 'my run']            requires team_ratings already computed (npm run ratings:compute first).\n" +
          "  sweep --param <RatingParams key> --values 1,2,3   recomputes team_ratings per value -- see sweep.ts's doc comment\n" +
          "        for what this does and does not sweep correctly.",
      );
      process.exitCode = 1;
  }

  await pool.end();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
