import { NextRequest, NextResponse } from "next/server";

// Same-origin BFF proxy: the browser calls /api/v1/evaluations/* on this
// Next.js server exactly like it always did, but this route now sits in
// front of the real FastAPI backend and is the only place that ever holds
// OPERATOR_CREDENTIAL. That variable is intentionally NOT prefixed
// NEXT_PUBLIC_ — a NEXT_PUBLIC_* value gets inlined into the client
// bundle and would hand the shared operator secret to every visitor's
// browser, defeating the entire point of gating approval/execute/rollback
// and live-run creation behind it. Reading it here, server-side only,
// keeps it out of the bundle and out of the browser entirely.
const BACKEND_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const OPERATOR_CREDENTIAL = process.env.OPERATOR_CREDENTIAL;

export const dynamic = "force-dynamic";

async function forward(request: NextRequest, path: string[] | undefined): Promise<NextResponse> {
  const suffix = path && path.length > 0 ? `/${path.join("/")}` : "";
  const target = `${BACKEND_BASE_URL}/api/v1/evaluations${suffix}${request.nextUrl.search}`;

  const headers = new Headers();
  const incomingContentType = request.headers.get("content-type");
  if (incomingContentType) headers.set("Content-Type", incomingContentType);
  // Attached here, server-side, only if the operator configured one — the
  // browser never sees or sends this value.
  if (OPERATOR_CREDENTIAL) headers.set("X-Operator-Credential", OPERATOR_CREDENTIAL);

  const init: RequestInit = { method: request.method, headers };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.text();
  }

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
