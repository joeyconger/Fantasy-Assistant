import { Pool, types } from "pg";
import { config } from "../config.js";

// pg returns NUMERIC columns as strings by default (avoids silent precision
// loss for values too big for a JS number). Every NUMERIC column in this
// schema (ratings, spreads, CLV, EPA) is well within float precision and
// gets used in arithmetic immediately, so parse it as a float at the driver
// level instead of coercing ad hoc at every call site.
types.setTypeParser(types.builtins.NUMERIC, (value: string) => parseFloat(value));

export const pool = new Pool({
  connectionString: config.databaseUrl,
  ssl: config.databaseUrl.includes("railway") ? { rejectUnauthorized: false } : undefined,
});

export async function query<T extends Record<string, unknown> = Record<string, unknown>>(
  text: string,
  params: unknown[] = [],
): Promise<T[]> {
  const result = await pool.query(text, params);
  return result.rows as T[];
}
