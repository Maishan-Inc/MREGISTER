import { withErrorBoundary, jsonOk } from "@/src/server/api";
import { requireAuth } from "@/src/server/auth";
import { run } from "@/src/server/db";

export async function DELETE(request, { params }) {
  return withErrorBoundary(async () => {
    requireAuth(request);
    run("DELETE FROM api_keys WHERE id = ?", [Number(params.keyId)]);
    return jsonOk({ ok: true });
  });
}
