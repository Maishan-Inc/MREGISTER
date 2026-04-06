import fs from "node:fs";
import path from "node:path";

const ROOT_DIR = process.cwd();
export const RUNTIME_DIR = path.join(ROOT_DIR, "runtime");
export const TASKS_DIR = path.join(RUNTIME_DIR, "tasks");
export const DB_PATH = path.join(RUNTIME_DIR, "app.db");
export const COOKIE_NAME = "mregister_session";
export const SESSION_TTL_HOURS = Number(process.env.MREGISTER_SESSION_TTL_HOURS || 24);

export function ensureRuntimeDirs() {
  fs.mkdirSync(RUNTIME_DIR, { recursive: true });
  fs.mkdirSync(TASKS_DIR, { recursive: true });
}

export function resolveTaskDir(taskId) {
  const value = String(taskId).padStart(6, "0");
  return path.join(TASKS_DIR, value);
}

export function tailText(filePath, maxLines = 160) {
  if (!fs.existsSync(filePath)) {
    return "";
  }
  const text = fs.readFileSync(filePath, "utf8");
  const lines = text.split(/\r?\n/);
  return lines.slice(-maxLines).join("\n");
}
