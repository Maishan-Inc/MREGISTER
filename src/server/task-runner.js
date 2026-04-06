import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import { spawn } from "node:child_process";
import { getTask, incrementTaskResult, updateTaskStatus } from "@/src/server/tasks";
import { nowIso } from "@/src/server/db";

function resolvePythonCommand() {
  if (process.env.MREGISTER_PYTHON_BIN) {
    return process.env.MREGISTER_PYTHON_BIN;
  }
  return process.platform === "win32" ? "python" : "python3";
}

class TaskRunner {
  constructor() {
    this.processes = new Map();
  }

  start(taskId) {
    const task = getTask(taskId);
    if (this.processes.has(taskId)) {
      return;
    }
    const taskDir = path.dirname(task.console_path);
    const configPath = path.join(taskDir, "task.json");
    const output = fs.createWriteStream(task.console_path, { flags: "a" });
    output.write(`[${nowIso()}] Task queued\n`);
    const pythonBin = resolvePythonCommand();
    const workerPath = path.join(process.cwd(), "worker", "register_task.py");
    output.write(`[${nowIso()}] Launching worker with ${pythonBin} ${workerPath}\n`);

    const child = spawn(pythonBin, [workerPath, "--config", configPath], {
      cwd: process.cwd(),
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PYTHONUTF8: "1" },
    });
    this.processes.set(taskId, { child, output });
    updateTaskStatus(taskId, "running", { pid: child.pid, error_message: null });

    const handleLine = (line) => {
      output.write(`${line}\n`);
      if (line.startsWith("__RESULT__")) {
        try {
          const payload = JSON.parse(line.slice("__RESULT__".length).trim());
          if (payload.event === "account_success") {
            incrementTaskResult(taskId);
          }
        } catch {}
      }
    };

    readline.createInterface({ input: child.stdout }).on("line", handleLine);
    readline.createInterface({ input: child.stderr }).on("line", handleLine);

    child.on("error", (error) => {
      output.write(`[${nowIso()}] Worker spawn error: ${error.message}\n`);
      output.end();
      this.processes.delete(taskId);
      updateTaskStatus(taskId, "failed", {
        error_message: `Worker spawn error: ${error.message}`,
        completed_at: nowIso(),
        pid: null,
      });
    });

    child.on("close", (code, signal) => {
      output.write(`[${nowIso()}] Task exit code=${code} signal=${signal}\n`);
      output.end();
      this.processes.delete(taskId);
      const current = getTask(taskId);
      const doneCount = current.results_count;
      let nextStatus = "failed";
      let errorMessage = current.error_message || null;
      if (signal || current.status === "stopped") {
        nextStatus = "stopped";
      } else if (code === 0 && doneCount >= current.quantity) {
        nextStatus = "completed";
      } else if (doneCount > 0) {
        nextStatus = "partial";
      } else if (code === 0) {
        nextStatus = "completed";
      }
      if (code && !errorMessage && nextStatus !== "stopped") {
        errorMessage = `Worker exited with code ${code}`;
      }
      updateTaskStatus(taskId, nextStatus, { error_message: errorMessage, completed_at: nowIso(), pid: null });
    });
  }

  stop(taskId) {
    const running = this.processes.get(taskId);
    if (!running) {
      updateTaskStatus(taskId, "stopped", { completed_at: nowIso(), pid: null });
      return;
    }
    updateTaskStatus(taskId, "stopped", { completed_at: nowIso(), pid: null });
    running.child.kill();
  }
}

export const taskRunner = new TaskRunner();
