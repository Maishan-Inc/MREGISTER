import { cookies } from "next/headers";
import { ConsoleApp } from "@/components/ConsoleApp";
import { AuthScreen } from "@/components/AuthScreen";
import { getDb } from "@/src/server/db";
import { getAuthViewFromToken } from "@/src/server/auth";
import { COOKIE_NAME } from "@/src/server/runtime";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  getDb();
  const cookieStore = await cookies();
  const authView = getAuthViewFromToken(cookieStore.get(COOKIE_NAME)?.value);
  return authView === "app" ? <ConsoleApp /> : <AuthScreen view={authView} />;
}
