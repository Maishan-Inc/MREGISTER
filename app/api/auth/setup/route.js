import { NextResponse } from "next/server";
import { authConfigured, createSession, issueSessionCookie, saveAdminPassword } from "@/src/server/auth";
import { withErrorBoundary } from "@/src/server/api";

export async function POST(request) {
  return withErrorBoundary(async () => {
    if (authConfigured()) {
      const error = new Error("管理员密码已设置");
      error.status = 409;
      throw error;
    }
    const payload = await request.json();
    const password = String(payload?.password || "");
    if (password.length < 8) {
      const error = new Error("管理员密码至少 8 位");
      error.status = 400;
      throw error;
    }
    saveAdminPassword(password);
    const session = createSession();
    return issueSessionCookie(NextResponse.json({ ok: true }), session.rawToken, session.expiresAt);
  });
}
