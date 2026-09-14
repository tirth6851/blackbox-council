import { NextRequest, NextResponse } from "next/server";
import { OPERATOR_SESSION_COOKIE, constantTimeEquals, createSessionToken } from "@/lib/operator-session";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const credential = process.env.OPERATOR_CREDENTIAL;
  if (!credential) {
    return NextResponse.json(
      { error: { code: "operator_not_configured", message: "No operator credential is configured on this server." } },
      { status: 404 },
    );
  }

  let body: { credential?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { error: { code: "invalid_request", message: "Expected a JSON body with a credential field." } },
      { status: 400 },
    );
  }

  if (typeof body.credential !== "string" || !constantTimeEquals(body.credential, credential)) {
    return NextResponse.json(
      { error: { code: "invalid_credential", message: "Incorrect operator credential." } },
      { status: 401 },
    );
  }

  const response = NextResponse.json({ authenticated: true });
  response.cookies.set(OPERATOR_SESSION_COOKIE, createSessionToken(credential), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: 60 * 60 * 12,
  });
  return response;
}
