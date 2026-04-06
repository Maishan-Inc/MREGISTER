import { withErrorBoundary, jsonOk } from "@/src/server/api";
import { requireAuth } from "@/src/server/auth";
import { nowIso, run } from "@/src/server/db";
import { getCredentials } from "@/src/server/tasks";

export async function POST(request) {
  return withErrorBoundary(async () => {
    requireAuth(request);
    const payload = await request.json();
    const timestamp = nowIso();
    const name = String(payload?.name || "").trim();
    const baseUrl = String(payload?.base_url || "").trim();
    const apiKey = String(payload?.api_key || "").trim();
    if (!name || !baseUrl || !apiKey) {
      const error = new Error("名称、Base URL、API Key 都必填");
      error.status = 400;
      throw error;
    }
    run(
      `
        INSERT INTO credentials (name, kind, api_key, base_url, category_key, tag_key, notes, created_at, updated_at)
        VALUES (?, 'outlook-api', ?, ?, ?, ?, ?, ?, ?)
      `,
      [
        name,
        apiKey,
        baseUrl,
        String(payload?.category_key || "mregister").trim().toLowerCase(),
        String(payload?.tag_key || "chatgpt_registered").trim().toLowerCase(),
        String(payload?.notes || "").trim(),
        timestamp,
        timestamp,
      ],
    );
    return jsonOk({ ok: true, credentials: getCredentials() });
  });
}
