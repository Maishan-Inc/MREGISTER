import { NextResponse } from "next/server";

export function jsonOk(payload = {}) {
  return NextResponse.json(payload);
}

export function jsonError(error) {
  const status = Number(error?.status || 500);
  const detail = error?.message || "请求失败";
  return NextResponse.json({ detail }, { status });
}

export async function withErrorBoundary(handler) {
  try {
    return await handler();
  } catch (error) {
    return jsonError(error);
  }
}
