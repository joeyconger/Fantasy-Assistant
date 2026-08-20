import { createServer } from "node:http";
import { pool } from "./db/pool.js";
import { isBasicAuthorized, requireBasicAuth } from "./web/basicAuth.js";
import { renderHome } from "./web/pages/home.js";
import { renderBacktestReport } from "./web/pages/backtestReport.js";
import { renderRatingsPage, renderPredictionsPage } from "./web/pages/ratings.js";
import { listBacktestRuns, getTeamRatingsForWeek, getPredictionsForWeek } from "./db/repo.js";
import type { Sport } from "./db/repo.js";
import { getOverallReport, getOpeningCoverRate, getThresholdReport, getSeasonReport } from "./backtest/report.js";
import { listJobs, getJob, JOB_STARTERS } from "./adminJobs.js";
import { config } from "./config.js";

// A read-only diagnostics surface: backtest reports, team ratings, and raw
// model predictions vs. market lines. NOT a live-picks app — nothing here
// is framed as a recommendation. HTML routes require HTTP Basic auth
// (DASHBOARD_USER/DASHBOARD_PASSWORD); /query and /admin/jobs use their
// own bearer-token auth (ADMIN_TOKEN) for API-style access.
const PORT = process.env.PORT ?? "3000";

function isAdminAuthorized(authHeader: string | undefined): boolean {
  if (!config.adminToken) return false;
  return authHeader === `Bearer ${config.adminToken}`;
}

function readBody(req: import("node:http").IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => resolve(body));
    req.on("error", reject);
  });
}

function html(res: import("node:http").ServerResponse, body: string): void {
  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
  res.end(body);
}

function isSport(value: string): value is Sport {
  return value === "nfl" || value === "cfb";
}

const server = createServer((req, res) => {
  handleRequest(req, res).catch((err) => {
    console.error("unhandled request error:", err);
    if (!res.headersSent) {
      res.writeHead(500, { "Content-Type": "text/plain" });
    }
    res.end("internal error");
  });
});

async function handleRequest(
  req: import("node:http").IncomingMessage,
  res: import("node:http").ServerResponse,
): Promise<void> {
  let url: URL;
  try {
    url = new URL(req.url ?? "/", `http://localhost:${PORT}`);
  } catch {
    res.writeHead(400, { "Content-Type": "text/plain" });
    res.end("bad request");
    return;
  }

  if (req.method === "GET" && url.pathname === "/health") {
    res.writeHead(200, { "Content-Type": "text/plain" });
    res.end("ok");
    return;
  }

  if (req.method === "POST" && url.pathname === "/query") {
    if (!isAdminAuthorized(req.headers.authorization)) {
      res.writeHead(401, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "unauthorized" }));
      return;
    }
    try {
      const body = JSON.parse(await readBody(req)) as { sql?: string; params?: unknown[] };
      const sql = (body.sql ?? "").trim();
      if (!/^select\b/i.test(sql)) {
        res.writeHead(400, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "only SELECT queries are allowed" }));
        return;
      }
      const result = await pool.query(sql, body.params ?? []);
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ rows: result.rows, rowCount: result.rowCount }));
    } catch (err) {
      res.writeHead(400, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: (err as Error).message }));
    }
    return;
  }

  // Background job triggers — for anything too slow to run inside a
  // request without risking a platform healthcheck timeout (ingestion,
  // rating computation, backtests). Pass params as a JSON body.
  if (req.method === "POST" && /^\/admin\/jobs\/[\w-]+$/.test(url.pathname)) {
    if (!isAdminAuthorized(req.headers.authorization)) {
      res.writeHead(401, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "unauthorized" }));
      return;
    }
    const name = url.pathname.split("/")[3]!;
    const starter = JOB_STARTERS[name];
    if (!starter) {
      res.writeHead(404, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: `unknown job: ${name}`, available: Object.keys(JOB_STARTERS) }));
      return;
    }
    let params: Record<string, unknown> = {};
    try {
      const raw = await readBody(req);
      params = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
    } catch {
      res.writeHead(400, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "invalid JSON body" }));
      return;
    }
    try {
      const job = starter(params);
      res.writeHead(202, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ started: job.id }));
    } catch (err) {
      res.writeHead(400, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: (err as Error).message }));
    }
    return;
  }

  if (req.method === "GET" && url.pathname === "/admin/jobs") {
    if (!isAdminAuthorized(req.headers.authorization)) {
      res.writeHead(401, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "unauthorized" }));
      return;
    }
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify(listJobs()));
    return;
  }

  if (req.method === "GET" && /^\/admin\/jobs\/[\w-]+$/.test(url.pathname)) {
    if (!isAdminAuthorized(req.headers.authorization)) {
      res.writeHead(401, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "unauthorized" }));
      return;
    }
    const job = getJob(url.pathname.split("/")[3]!);
    if (!job) {
      res.writeHead(404, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "job not found" }));
      return;
    }
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify(job));
    return;
  }

  // Everything below is the HTML dashboard — Basic-auth gated.
  if (!isBasicAuthorized(req.headers.authorization)) {
    requireBasicAuth(res);
    return;
  }

  if (req.method === "GET" && url.pathname === "/") {
    const runs = await listBacktestRuns();
    const statsByRun = new Map(await Promise.all(runs.map(async (r) => [r.id, await getOverallReport(r.id)] as const)));
    html(res, renderHome(runs, statsByRun));
    return;
  }

  if (req.method === "GET" && /^\/backtest\/\d+$/.test(url.pathname)) {
    const runId = Number(url.pathname.split("/")[2]);
    const runs = await listBacktestRuns();
    const run = runs.find((r) => r.id === runId);
    if (!run) {
      res.writeHead(404, { "Content-Type": "text/plain" });
      res.end("backtest run not found");
      return;
    }
    const [overall, openingCover, thresholds, seasons] = await Promise.all([
      getOverallReport(runId),
      getOpeningCoverRate(runId),
      getThresholdReport(runId),
      getSeasonReport(runId),
    ]);
    html(res, renderBacktestReport(run, overall, openingCover, thresholds, seasons));
    return;
  }

  if (req.method === "GET" && url.pathname === "/ratings") {
    const sport = url.searchParams.get("sport") ?? "";
    const season = url.searchParams.get("season") ?? "";
    const week = url.searchParams.get("week") ?? "";
    const ratings =
      isSport(sport) && season && week ? await getTeamRatingsForWeek(sport, Number(season), Number(week)) : null;
    html(res, renderRatingsPage(sport || "nfl", season, week, ratings));
    return;
  }

  if (req.method === "GET" && url.pathname === "/predictions") {
    const sport = url.searchParams.get("sport") ?? "";
    const season = url.searchParams.get("season") ?? "";
    const week = url.searchParams.get("week") ?? "";
    const predictions =
      isSport(sport) && season && week ? await getPredictionsForWeek(sport, Number(season), Number(week)) : null;
    html(res, renderPredictionsPage(sport || "nfl", season, week, predictions));
    return;
  }

  res.writeHead(404, { "Content-Type": "text/plain" });
  res.end("not found");
}

server.listen(Number(PORT), () => {
  console.log(`server listening on ${PORT}`);
});
