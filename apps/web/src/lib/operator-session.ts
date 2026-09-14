import { createHmac, timingSafeEqual } from "node:crypto";

// A tiny signed-cookie session, not a general auth system: this exists
// only to answer "did a browser that knows OPERATOR_CREDENTIAL sign in
// recently", so the BFF proxy (app/api/v1/evaluations/[[...path]]/route.ts)
// has something to check before it forwards a request with the shared
// operator secret attached. Without this, the proxy is a confused deputy:
// hiding the secret from the browser is not the same as authorizing the
// browser to use it.
export const OPERATOR_SESSION_COOKIE = "operator_session";
const SESSION_TTL_MS = 12 * 60 * 60 * 1000; // 12 hours

function sign(payload: string, secret: string): string {
  return createHmac("sha256", secret).update(payload).digest("hex");
}

export function constantTimeEquals(a: string, b: string): boolean {
  const bufA = Buffer.from(a, "utf8");
  const bufB = Buffer.from(b, "utf8");
  if (bufA.length !== bufB.length) return false;
  return timingSafeEqual(bufA, bufB);
}

export function createSessionToken(secret: string): string {
  const expiresAt = Date.now() + SESSION_TTL_MS;
  const payload = String(expiresAt);
  return `${payload}.${sign(payload, secret)}`;
}

export function verifySessionToken(token: string | undefined, secret: string): boolean {
  if (!token) return false;
  const parts = token.split(".");
  if (parts.length !== 2) return false;
  const [payload, signature] = parts;
  const expected = sign(payload, secret);
  if (signature.length !== expected.length) return false;
  if (!timingSafeEqual(Buffer.from(signature, "utf8"), Buffer.from(expected, "utf8"))) return false;
  const expiresAt = Number(payload);
  if (!Number.isFinite(expiresAt) || Date.now() > expiresAt) return false;
  return true;
}
