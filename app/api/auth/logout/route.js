import { NextResponse } from "next/server";
import { clearSession } from "@/src/server/auth";
import { COOKIE_NAME } from "@/src/server/runtime";
import { withErrorBoundary } from "@/src/server/api";

export async function POST(request) {
  return withErrorBoundary(async () => {
    clearSession(request.cookies.get(COOKIE_NAME)?.value);
    const response = NextResponse.json({ ok: true });
    response.cookies.delete(COOKIE_NAME);
    return response;
  });
}
