import { withErrorBoundary, jsonOk } from "@/src/server/api";
import { requireApiKey } from "@/src/server/auth";
import { createTask, getDefaults } from "@/src/server/tasks";
import { taskRunner } from "@/src/server/task-runner";

export async function POST(request) {
  return withErrorBoundary(async () => {
    requireApiKey(request);
    const payload = await request.json();
    const credentialId = getDefaults().default_outlook_credential_id;
    if (!credentialId) {
      const error = new Error("站点未配置默认 OutlookManager 凭据");
      error.status = 409;
      throw error;
    }
    const autoDeleteAt = new Date(Date.now() + 24 * 3600 * 1000).toISOString();
    const taskId = createTask({
      name: String(payload?.name || "").trim() || `api-${Date.now()}`,
      platform: String(payload?.platform || "chatgpt-register-lib"),
      quantity: Math.max(1, Number(payload?.quantity || 1)),
      source: "api",
      credentialId,
      autoDeleteAt,
    });
    taskRunner.start(taskId);
    return jsonOk({ ok: true, task_id: taskId, auto_delete_at: autoDeleteAt });
  });
}
