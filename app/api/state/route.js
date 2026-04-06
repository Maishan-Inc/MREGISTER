import { withErrorBoundary, jsonOk } from "@/src/server/api";
import { requireAuth } from "@/src/server/auth";
import { buildStatePayload } from "@/src/server/tasks";

export async function GET(request) {
  return withErrorBoundary(async () => {
    requireAuth(request);
    return jsonOk(buildStatePayload());
  });
}
