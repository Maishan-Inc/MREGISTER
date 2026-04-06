import { withErrorBoundary, jsonOk } from "@/src/server/api";
import { requireApiKey } from "@/src/server/auth";
import { getTaskPayload } from "@/src/server/tasks";

export async function GET(request, { params }) {
  return withErrorBoundary(async () => {
    requireApiKey(request);
    const task = getTaskPayload(Number(params.taskId));
    return jsonOk({
      task_id: task.id,
      status: task.status,
      completed_count: task.results_count,
      target_quantity: task.quantity,
      auto_delete_at: task.auto_delete_at,
      download_url: ["queued", "running"].includes(task.status) ? null : `/api/external/tasks/${task.id}/download`,
    });
  });
}
