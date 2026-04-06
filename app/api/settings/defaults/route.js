import { withErrorBoundary, jsonOk } from "@/src/server/api";
import { requireAuth } from "@/src/server/auth";
import { getCredentialById, getDefaults, setDefaultCredentialId } from "@/src/server/tasks";

export async function POST(request) {
  return withErrorBoundary(async () => {
    requireAuth(request);
    const payload = await request.json();
    const credentialId = payload?.default_outlook_credential_id ? Number(payload.default_outlook_credential_id) : null;
    if (credentialId) {
      getCredentialById(credentialId);
    }
    setDefaultCredentialId(credentialId);
    return jsonOk({ ok: true, defaults: getDefaults() });
  });
}
