import fs from "node:fs";
import path from "node:path";
import AdmZip from "adm-zip";
import { PLATFORM_SPECS } from "@/src/lib/constants";
import { nowIso, one, all, run, getSetting } from "@/src/server/db";
import { resolveTaskDir, tailText } from "@/src/server/runtime";

function serializeCredential(row) {
  return {
    id: row.id,
    name: row.name,
    kind: row.kind,
    base_url: row.base_url,
    category_key: row.category_key || "mregister",
    tag_key: row.tag_key || "chatgpt_registered",
    notes: row.notes || "",
    created_at: row.created_at,
    updated_at: row.updated_at,
    has_api_key: Boolean(row.api_key),
  };
}

export function getCredentials() {
  return all("SELECT * FROM credentials ORDER BY id DESC").map(serializeCredential);
}

export function getCredentialById(id) {
  const row = one("SELECT * FROM credentials WHERE id = ?", [id]);
  if (!row) {
    const error = new Error("凭据不存在");
    error.status = 404;
    throw error;
  }
  return row;
}

export function getDefaults() {
  const defaultCredentialId = getSetting("default_outlook_credential_id");
  return {
    default_outlook_credential_id: defaultCredentialId ? Number(defaultCredentialId) : null,
  };
}

export function setDefaultCredentialId(id) {
  run(
    `
      INSERT INTO settings (key, value) VALUES ('default_outlook_credential_id', ?)
      ON CONFLICT(key) DO UPDATE SET value = excluded.value
    `,
    [id ? String(id) : null],
  );
}

function serializeTask(row) {
  const config = JSON.parse(row.config_json);
  if (config?.credential?.api_key) {
    config.credential = {
      ...config.credential,
      api_key: undefined,
    };
  }
  return {
    id: row.id,
    name: row.name,
    platform: row.platform,
    quantity: row.quantity,
    results_count: row.results_count,
    status: row.status,
    source: row.source,
    credential_id: row.credential_id,
    created_at: row.created_at,
    updated_at: row.updated_at,
    completed_at: row.completed_at,
    auto_delete_at: row.auto_delete_at,
    error_message: row.error_message || "",
    platform_label: PLATFORM_SPECS[row.platform]?.label || row.platform,
    config,
    console_tail: tailText(row.console_path),
  };
}

export function listTasks() {
  return all("SELECT * FROM tasks ORDER BY id DESC").map(serializeTask);
}

export function getTask(taskId) {
  const row = one("SELECT * FROM tasks WHERE id = ?", [taskId]);
  if (!row) {
    const error = new Error("任务不存在");
    error.status = 404;
    throw error;
  }
  return row;
}

export function getTaskPayload(taskId) {
  return serializeTask(getTask(taskId));
}

export function createTask({
  name,
  platform,
  quantity,
  source = "ui",
  credentialId,
  autoDeleteAt = null,
}) {
  if (!PLATFORM_SPECS[platform]) {
    const error = new Error("不支持的驱动");
    error.status = 400;
    throw error;
  }
  const credential = getCredentialById(credentialId);
  const taskDir = resolveTaskDir(Date.now() + Math.floor(Math.random() * 1000));
  fs.mkdirSync(taskDir, { recursive: true });
  const consolePath = path.join(taskDir, "console.log");
  const archivePath = path.join(taskDir, "result.zip");
  const outputDir = path.join(taskDir, "output");
  fs.mkdirSync(outputDir, { recursive: true });

  const createdAt = nowIso();
  const config = {
    task_name: name,
    platform,
    quantity,
    credential: {
      id: credential.id,
      name: credential.name,
      base_url: credential.base_url,
      api_key: credential.api_key,
      category_key: (credential.category_key || "mregister").toLowerCase(),
      tag_key: (credential.tag_key || "chatgpt_registered").toLowerCase(),
    },
    output_dir: outputDir,
  };
  const result = run(
    `
      INSERT INTO tasks (
        name, platform, quantity, results_count, status, source, credential_id,
        console_path, output_dir, archive_path, config_json, auto_delete_at,
        created_at, updated_at
      ) VALUES (?, ?, ?, 0, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `,
    [
      name,
      platform,
      quantity,
      source,
      credential.id,
      consolePath,
      outputDir,
      archivePath,
      JSON.stringify(config),
      autoDeleteAt,
      createdAt,
      createdAt,
    ],
  );
  const taskId = Number(result.lastInsertRowid);
  const realTaskDir = resolveTaskDir(taskId);
  if (realTaskDir !== taskDir) {
    fs.renameSync(taskDir, realTaskDir);
  }
  const realConsolePath = path.join(realTaskDir, "console.log");
  const realOutputDir = path.join(realTaskDir, "output");
  const realArchivePath = path.join(realTaskDir, "result.zip");
  const realConfig = { ...config, task_id: taskId, output_dir: realOutputDir, console_path: realConsolePath };
  fs.writeFileSync(path.join(realTaskDir, "task.json"), JSON.stringify(realConfig, null, 2), "utf8");
  run(
    "UPDATE tasks SET console_path = ?, output_dir = ?, archive_path = ?, config_json = ?, updated_at = ? WHERE id = ?",
    [realConsolePath, realOutputDir, realArchivePath, JSON.stringify(realConfig), nowIso(), taskId],
  );
  return taskId;
}

export function updateTaskStatus(taskId, status, extra = {}) {
  const task = getTask(taskId);
  run(
    `
      UPDATE tasks
      SET status = ?, results_count = ?, error_message = ?, pid = ?, completed_at = ?, updated_at = ?
      WHERE id = ?
    `,
    [
      status,
      extra.results_count ?? task.results_count,
      extra.error_message ?? task.error_message ?? null,
      extra.pid ?? task.pid ?? null,
      extra.completed_at ?? task.completed_at ?? null,
      nowIso(),
      taskId,
    ],
  );
}

export function incrementTaskResult(taskId) {
  run("UPDATE tasks SET results_count = results_count + 1, updated_at = ? WHERE id = ?", [nowIso(), taskId]);
}

export function createTaskArchive(taskId) {
  const task = getTask(taskId);
  if (fs.existsSync(task.archive_path)) {
    return task.archive_path;
  }
  const zip = new AdmZip();
  const taskDir = path.dirname(task.console_path);
  if (fs.existsSync(task.console_path)) {
    zip.addLocalFile(task.console_path);
  }
  if (fs.existsSync(task.output_dir)) {
    zip.addLocalFolder(task.output_dir, "output");
  }
  zip.writeZip(task.archive_path);
  return task.archive_path;
}

export function deleteTask(taskId) {
  const task = getTask(taskId);
  if (["queued", "running"].includes(task.status)) {
    const error = new Error("请先停止任务");
    error.status = 409;
    throw error;
  }
  const taskDir = path.dirname(task.console_path);
  fs.rmSync(taskDir, { recursive: true, force: true });
  run("DELETE FROM tasks WHERE id = ?", [taskId]);
}

export function dashboardPayload() {
  const tasks = listTasks();
  return {
    total_tasks: tasks.length,
    running_tasks: tasks.filter((item) => item.status === "running").length,
    completed_tasks: tasks.filter((item) => item.status === "completed").length,
    credential_count: getCredentials().length,
  };
}

export function buildStatePayload() {
  return {
    platforms: PLATFORM_SPECS,
    defaults: getDefaults(),
    credentials: getCredentials(),
    tasks: listTasks(),
    api_keys: all("SELECT id, name, key_prefix, created_at, last_used_at FROM api_keys WHERE is_active = 1 ORDER BY id DESC"),
    dashboard: dashboardPayload(),
  };
}
