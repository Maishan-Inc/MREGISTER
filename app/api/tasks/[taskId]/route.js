import { withErrorBoundary, jsonOk } from "@/src/server/api";
import { requireAuth } from "@/src/server/auth";
import { deleteTask, getTaskPayload } from "@/src/server/tasks";

export async function GET(request, { params }) {
  return withErrorBoundary(async () => {
    requireAuth(request);
    return jsonOk({ task: getTaskPayload(Number(params.taskId)) });
  });
}

export async function DELETE(request, { params }) {
  return withErrorBoundary(async () => {
    requireAuth(request);
    deleteTask(Number(params.taskId));
    return jsonOk({ ok: true });
  });
}
