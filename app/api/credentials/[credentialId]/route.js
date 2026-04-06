import { withErrorBoundary, jsonOk } from "@/src/server/api";
import { requireAuth } from "@/src/server/auth";
import { getDefaults, setDefaultCredentialId } from "@/src/server/tasks";
import { run } from "@/src/server/db";

export async function DELETE(request, { params }) {
  return withErrorBoundary(async () => {
    requireAuth(request);
    const credentialId = Number(params.credentialId);
    run("DELETE FROM credentials WHERE id = ?", [credentialId]);
    if (getDefaults().default_outlook_credential_id === credentialId) {
      setDefaultCredentialId(null);
    }
    return jsonOk({ ok: true });
  });
}
