import { NextResponse } from "next/server";
import { createSession, issueSessionCookie, verifyPassword } from "@/src/server/auth";
import { getSetting } from "@/src/server/db";
import { withErrorBoundary } from "@/src/server/api";

export async function POST(request) {
  return withErrorBoundary(async () => {
    const payload = await request.json();
    const password = String(payload?.password || "");
    const ok = verifyPassword(password, getSetting("admin_password_hash"));
    if (!ok) {
      const error = new Error("密码错误");
      error.status = 401;
      throw error;
    }
    const session = createSession();
    return issueSessionCookie(NextResponse.json({ ok: true }), session.rawToken, session.expiresAt);
  });
}
