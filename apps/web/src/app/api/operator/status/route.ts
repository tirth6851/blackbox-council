import { NextRequest, NextResponse } from "next/server";
import { OPERATOR_SESSION_COOKIE, verifySessionToken } from "@/lib/operator-session";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const credential = process.env.OPERATOR_CREDENTIAL;
  const configured = Boolean(credential);
  const token = request.cookies.get(OPERATOR_SESSION_COOKIE)?.value;
  // Unset credential means there is nothing to authenticate against — the
  // local/demo default — so every caller is treated as already authorized,
  // matching the proxy route's own behavior in that case.
  const authenticated = configured ? verifySessionToken(token, credential!) : true;
  return NextResponse.json({ configured, authenticated });
}
