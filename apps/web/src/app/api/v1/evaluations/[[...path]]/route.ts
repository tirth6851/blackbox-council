import { NextRequest, NextResponse } from "next/server";
import { OPERATOR_SESSION_COOKIE, verifySessionToken } from "@/lib/operator-session";

// Same-origin BFF proxy: the browser calls /api/v1/evaluations/* on this
// Next.js server exactly like it always did, but this route now sits in
// front of the real FastAPI backend and is the only place that ever holds
// OPERATOR_CREDENTIAL. That variable is intentionally NOT prefixed
// NEXT_PUBLIC_ — a NEXT_PUBLIC_* value gets inlined into the client
// bundle and would hand the shared operator secret to every visitor's
// browser, defeating the entire point of gating approval/execute/rollback
// and live-run creation behind it.
//
// Hiding the secret from the browser is not the same as authorizing the
// browser to use it: without a check here, this proxy is a confused
// deputy — any anonymous visitor could POST to it and have it silently
// upgrade their request with the operator credential. So when
// OPERATOR_CREDENTIAL is configured, every protected path additionally
// requires a valid signed operator-session cookie (see
// app/api/operator/{login,logout,status}/route.ts) and a same-origin
// check, and is refused — never forwarded with the credential — without
// both. Public paths (mock evaluation creation, reading a report) are
// unaffected, matching the plan's "synthetic mock demo stays public".
const BACKEND_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const OPERATOR_CREDENTIAL = process.env.OPERATOR_CREDENTIAL;

export const dynamic = "force-dynamic";

function isProtectedRequest(method: string, path: string[] | undefined, bodyText: string): boolean {
  const suffix = path && path.length > 0 ? path[path.length - 1] : null;
  if (suffix === "approvals" || suffix === "execute" || suffix === "rollback") return true;
  // The root POST /api/v1/evaluations is only protected when it's actually
  // requesting a live model run; mode="mock" (or omitted) stays public.
  if ((!path || path.length === 0) && method === "POST") {
    try {
      const parsed = JSON.parse(bodyText || "{}");
      return parsed?.mode === "live";
    } catch {
      return false;
    }
  }
  return false;
}

/** Cheap CSRF defense-in-depth on top of the session cookie's own
 * SameSite=Strict (which is the primary defense — a browser simply won't
 * attach that cookie to a cross-site request in the first place). Only
 * refuses a request that explicitly carries a *different* Origin; a
 * missing Origin (e.g. a same-origin navigation, or a non-browser caller
 * that can't have the cookie anyway) is not blocked here. */
function isSameOriginOrNoOrigin(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return true;
  // Compare against the literal incoming Host header rather than
  // request.nextUrl.host: in some dev/proxy setups the latter can differ
  // from what the browser actually addressed, which would otherwise make
  // this reject same-origin requests.
  const host = request.headers.get("host");
  try {
    return host !== null && new URL(origin).host === host;
  } catch {
    return false;
  }
}

async function forward(request: NextRequest, path: string[] | undefined): Promise<NextResponse> {
  const suffix = path && path.length > 0 ? `/${path.join("/")}` : "";
  const target = `${BACKEND_BASE_URL}/api/v1/evaluations${suffix}${request.nextUrl.search}`;

  const bodyText =
    request.method !== "GET" && request.method !== "HEAD" ? await request.text() : undefined;
  const protectedRequest = isProtectedRequest(request.method, path, bodyText ?? "");

  if (protectedRequest && OPERATOR_CREDENTIAL) {
    if (!isSameOriginOrNoOrigin(request)) {
      return NextResponse.json(
        {
          error: {
            code: "cross_origin_forbidden",
            message: "Cross-origin requests to protected operator actions are refused.",
          },
        },
        { status: 403 },
      );
    }
    const sessionToken = request.cookies.get(OPERATOR_SESSION_COOKIE)?.value;
    if (!verifySessionToken(sessionToken, OPERATOR_CREDENTIAL)) {
      return NextResponse.json(
        {
          error: {
            code: "operator_session_required",
            message: "Sign in as operator before approving, executing, rolling back, or starting a live run.",
          },
        },
        { status: 401 },
      );
    }
  }

  const headers = new Headers();
  const incomingContentType = request.headers.get("content-type");
  if (incomingContentType) headers.set("Content-Type", incomingContentType);
  // Only ever attached once the checks above have actually authorized this
  // specific request — never attached "just in case" for every call.
  if (protectedRequest && OPERATOR_CREDENTIAL) headers.set("X-Operator-Credential", OPERATOR_CREDENTIAL);

  const init: RequestInit = { method: request.method, headers };
  if (bodyText !== undefined) init.body = bodyText;

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch {
    return NextResponse.json(
      { error: { code: "network_error", message: "Could not reach the BlackBox Council API." } },
      { status: 502 },
    );
  }

  const body = await upstream.arrayBuffer();
  const responseHeaders = new Headers();
  const contentType = upstream.headers.get("content-type");
  if (contentType) responseHeaders.set("Content-Type", contentType);
  const contentDisposition = upstream.headers.get("content-disposition");
  if (contentDisposition) responseHeaders.set("Content-Disposition", contentDisposition);

  return new NextResponse(body, { status: upstream.status, headers: responseHeaders });
}

export async function GET(request: NextRequest, { params }: { params: { path?: string[] } }) {
  return forward(request, params.path);
}

export async function POST(request: NextRequest, { params }: { params: { path?: string[] } }) {
  return forward(request, params.path);
}
