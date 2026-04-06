import { withErrorBoundary, jsonOk } from "@/src/server/api";
import { requireAuth } from "@/src/server/auth";
import { createTask, getDefaults } from "@/src/server/tasks";
import { taskRunner } from "@/src/server/task-runner";

export async function POST(request) {
  return withErrorBoundary(async () => {
    requireAuth(request);
    const payload = await request.json();
    const quantity = Math.max(1, Number(payload?.quantity || 1));
    const credentialId = payload?.credential_id ? Number(payload.credential_id) : getDefaults().default_outlook_credential_id;
    if (!credentialId) {
      const error = new Error("请先选择或设置默认 OutlookManager 凭据");
      error.status = 400;
      throw error;
    }
    const taskId = createTask({
      name: String(payload?.name || "").trim() || `chatgpt-register-${Date.now()}`,
      platform: String(payload?.platform || "chatgpt-register-lib"),
      quantity,
      credentialId,
    });
    taskRunner.start(taskId);
    return jsonOk({ ok: true, id: taskId });
  });
}
