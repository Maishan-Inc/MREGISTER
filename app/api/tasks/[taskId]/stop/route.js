import { withErrorBoundary, jsonOk } from "@/src/server/api";
import { requireAuth } from "@/src/server/auth";
import { taskRunner } from "@/src/server/task-runner";

export async function POST(request, { params }) {
  return withErrorBoundary(async () => {
    requireAuth(request);
    taskRunner.stop(Number(params.taskId));
    return jsonOk({ ok: true });
  });
}
