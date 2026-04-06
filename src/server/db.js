import { DatabaseSync } from "node:sqlite";
import { DB_PATH, ensureRuntimeDirs } from "@/src/server/runtime";

let database;

function createDatabase() {
  ensureRuntimeDirs();
  const db = new DatabaseSync(DB_PATH);
  db.exec("PRAGMA journal_mode = WAL;");
  db.exec(`
    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY,
      value TEXT
    );

    CREATE TABLE IF NOT EXISTS sessions (
      id TEXT PRIMARY KEY,
      token_hash TEXT NOT NULL,
      expires_at TEXT NOT NULL,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS credentials (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      kind TEXT NOT NULL,
      api_key TEXT NOT NULL,
      base_url TEXT NOT NULL,
      category_key TEXT,
      tag_key TEXT,
      notes TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS tasks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      platform TEXT NOT NULL,
      quantity INTEGER NOT NULL,
      results_count INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL,
      source TEXT NOT NULL,
      credential_id INTEGER NOT NULL,
      console_path TEXT NOT NULL,
      output_dir TEXT NOT NULL,
      archive_path TEXT NOT NULL,
      config_json TEXT NOT NULL,
      error_message TEXT,
      pid INTEGER,
      auto_delete_at TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      completed_at TEXT
    );

    CREATE TABLE IF NOT EXISTS api_keys (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      key_hash TEXT NOT NULL,
      key_prefix TEXT NOT NULL,
      is_active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,
      last_used_at TEXT
    );
  `);
  db.exec(`
    UPDATE tasks
    SET status = 'interrupted',
        updated_at = datetime('now'),
        error_message = COALESCE(error_message, 'Server restarted before task finished')
    WHERE status IN ('queued', 'running');
  `);
  return db;
}

export function getDb() {
  if (!database) {
    database = createDatabase();
  }
  return database;
}

export function nowIso() {
  return new Date().toISOString();
}

export function getSetting(key, fallback = null) {
  const row = getDb().prepare("SELECT value FROM settings WHERE key = ?").get(key);
  return row ? row.value : fallback;
}

export function setSetting(key, value) {
  getDb()
    .prepare(`
      INSERT INTO settings (key, value)
      VALUES (?, ?)
      ON CONFLICT(key) DO UPDATE SET value = excluded.value
    `)
    .run(key, value);
}

export function all(sql, params = []) {
  return getDb().prepare(sql).all(...params);
}

export function one(sql, params = []) {
  return getDb().prepare(sql).get(...params);
}

export function run(sql, params = []) {
  return getDb().prepare(sql).run(...params);
}
