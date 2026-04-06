import { withErrorBoundary, jsonOk } from "@/src/server/api";
import { requireAuth } from "@/src/server/auth";
import { getTask } from "@/src/server/tasks";
import { tailText } from "@/src/server/runtime";

export async function GET(request, { params }) {
  return withErrorBoundary(async () => {
    requireAuth(request);
    const task = getTask(Number(params.taskId));
    return jsonOk({ task_id: Number(params.taskId), console: tailText(task.console_path) });
  });
}
