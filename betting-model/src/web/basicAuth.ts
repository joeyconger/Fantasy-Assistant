import type { ServerResponse } from "node:http";
import { config } from "../config.js";

export function isBasicAuthorized(authHeader: string | undefined): boolean {
  if (!config.dashboardUser || !config.dashboardPassword) return false;
  if (!authHeader?.startsWith("Basic ")) return false;
  const decoded = Buffer.from(authHeader.slice("Basic ".length), "base64").toString("utf8");
  const separatorIndex = decoded.indexOf(":");
  if (separatorIndex === -1) return false;
  const user = decoded.slice(0, separatorIndex);
  const password = decoded.slice(separatorIndex + 1);
  return user === config.dashboardUser && password === config.dashboardPassword;
}

export function requireBasicAuth(res: ServerResponse): void {
  res.writeHead(401, { "WWW-Authenticate": 'Basic realm="betting-model"', "Content-Type": "text/plain" });
  res.end("unauthorized");
}
