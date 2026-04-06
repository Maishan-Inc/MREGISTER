import crypto from "node:crypto";
import { COOKIE_NAME, SESSION_TTL_HOURS } from "@/src/server/runtime";
import { getDb, getSetting, nowIso, run, setSetting, one } from "@/src/server/db";

function hashValue(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

export function authConfigured() {
  return Boolean(getSetting("admin_password_hash"));
}

export function hashPassword(password) {
  const salt = crypto.randomBytes(16).toString("hex");
  const derived = crypto.scryptSync(password, salt, 64).toString("hex");
  return `${salt}:${derived}`;
}

export function verifyPassword(password, storedHash) {
  if (!storedHash || !storedHash.includes(":")) {
    return false;
  }
  const [salt, original] = storedHash.split(":");
  const candidate = crypto.scryptSync(password, salt, 64).toString("hex");
  return crypto.timingSafeEqual(Buffer.from(candidate), Buffer.from(original));
}

export function saveAdminPassword(password) {
  setSetting("admin_password_hash", hashPassword(password));
}

export function createSession() {
  const rawToken = crypto.randomBytes(32).toString("hex");
  const sessionId = crypto.randomUUID();
  const expiresAt = new Date(Date.now() + SESSION_TTL_HOURS * 3600 * 1000).toISOString();
  run(
    "INSERT INTO sessions (id, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?)",
    [sessionId, hashValue(rawToken), expiresAt, nowIso()],
  );
  return { rawToken, expiresAt };
}

export function clearSession(rawToken) {
  if (!rawToken) {
    return;
  }
  run("DELETE FROM sessions WHERE token_hash = ?", [hashValue(rawToken)]);
}

export function getAuthenticatedSession(rawToken) {
  if (!rawToken) {
    return null;
  }
  getDb().prepare("DELETE FROM sessions WHERE expires_at < ?").run(nowIso());
  const row = one("SELECT * FROM sessions WHERE token_hash = ?", [hashValue(rawToken)]);
  return row || null;
}

export function requireAuth(request) {
  const session = getAuthenticatedSession(request.cookies.get(COOKIE_NAME)?.value);
  if (!session) {
    const error = new Error("未登录");
    error.status = 401;
    throw error;
  }
  return session;
}

export function getAuthViewFromToken(rawToken) {
  if (!authConfigured()) {
    return "setup";
  }
  return getAuthenticatedSession(rawToken) ? "app" : "login";
}

export function getAuthView(request) {
  return getAuthViewFromToken(request.cookies.get(COOKIE_NAME)?.value);
}

export function issueSessionCookie(response, rawToken, expiresAt) {
  response.cookies.set({
    name: COOKIE_NAME,
    value: rawToken,
    httpOnly: true,
    sameSite: "lax",
    secure: false,
    expires: new Date(expiresAt),
    path: "/",
  });
  return response;
}

export function getApiKeyHash(rawKey) {
  return hashValue(rawKey);
}

export function createApiKeySecret() {
  const rawKey = `mreg_${crypto.randomBytes(24).toString("hex")}`;
  return {
    rawKey,
    keyHash: getApiKeyHash(rawKey),
    keyPrefix: rawKey.slice(0, 12),
  };
}

export function requireApiKey(request) {
  const authHeader = request.headers.get("authorization") || "";
  const bearer = authHeader.startsWith("Bearer ") ? authHeader.slice(7).trim() : "";
  if (!bearer) {
    const error = new Error("缺少 API Key");
    error.status = 401;
    throw error;
  }
  const row = one("SELECT * FROM api_keys WHERE key_hash = ? AND is_active = 1", [getApiKeyHash(bearer)]);
  if (!row) {
    const error = new Error("API Key 无效");
    error.status = 401;
    throw error;
  }
  run("UPDATE api_keys SET last_used_at = ? WHERE id = ?", [nowIso(), row.id]);
  return row;
}
