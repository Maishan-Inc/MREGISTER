import { authConfigured, getAuthenticatedSession } from "@/src/server/auth";
import { COOKIE_NAME } from "@/src/server/runtime";
import { jsonOk, withErrorBoundary } from "@/src/server/api";

export async function GET(request) {
  return withErrorBoundary(async () => {
    const token = request.cookies.get(COOKIE_NAME)?.value;
    return jsonOk({
      configured: authConfigured(),
      authenticated: Boolean(getAuthenticatedSession(token)),
    });
  });
}
