import { withErrorBoundary, jsonOk } from "@/src/server/api";
import { createApiKeySecret, requireAuth } from "@/src/server/auth";
import { nowIso, run } from "@/src/server/db";

export async function POST(request) {
  return withErrorBoundary(async () => {
    requireAuth(request);
    const payload = await request.json();
    const name = String(payload?.name || "").trim();
    if (!name) {
      const error = new Error("名称不能为空");
      error.status = 400;
      throw error;
    }
    const secret = createApiKeySecret();
    const result = run(
      "INSERT INTO api_keys (name, key_hash, key_prefix, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
      [name, secret.keyHash, secret.keyPrefix, nowIso()],
    );
    return jsonOk({ ok: true, id: Number(result.lastInsertRowid), api_key: secret.rawKey });
  });
}
