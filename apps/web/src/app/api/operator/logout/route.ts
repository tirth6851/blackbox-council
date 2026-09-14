import { NextResponse } from "next/server";
import { OPERATOR_SESSION_COOKIE } from "@/lib/operator-session";

export async function POST(): Promise<NextResponse> {
  const response = NextResponse.json({ authenticated: false });
  response.cookies.set(OPERATOR_SESSION_COOKIE, "", { httpOnly: true, path: "/", maxAge: 0 });
  return response;
}
