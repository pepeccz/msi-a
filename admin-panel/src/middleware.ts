import { NextRequest, NextResponse } from "next/server";

/**
 * Edge Middleware — cookie-presence auth gate.
 *
 * Design invariants (ADR-D3):
 * - Cookie PRESENCE is the only check here. JWT signature verification is
 *   ALWAYS done on the backend (trust boundary invariant).
 * - Excluded paths: /login, /api/*, /_next/*, /favicon.ico, public static assets.
 * - Anonymous requests to protected routes → 307 to /login?returnTo=<path>.
 */
export function middleware(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;

  // Pass through excluded paths — no redirect regardless of cookie state.
  if (isExcluded(pathname)) {
    return NextResponse.next();
  }

  // Cookie-presence check only. Do NOT decode or verify the JWT here.
  const hasCookie = request.cookies.has("admin_token");
  if (hasCookie) {
    return NextResponse.next();
  }

  // Anonymous request to a protected route → redirect to /login with returnTo.
  const loginUrl = new URL("/login", request.nextUrl.origin);
  loginUrl.searchParams.set("returnTo", pathname);
  return NextResponse.redirect(loginUrl, { status: 307 });
}

/**
 * Returns true for paths that the middleware must NOT intercept.
 */
function isExcluded(pathname: string): boolean {
  return (
    pathname === "/login" ||
    pathname.startsWith("/api/") ||
    pathname.startsWith("/_next/") ||
    pathname === "/favicon.ico"
  );
}

/**
 * Next.js matcher config — limits Edge invocation to routes that matter.
 * Static assets under /_next/static and /_next/image are excluded via the
 * matcher pattern directly; the isExcluded() guard above handles any that
 * slip through (belt-and-suspenders).
 */
export const config = {
  matcher: [
    /*
     * Match all paths except:
     * - _next/static (static files)
     * - _next/image  (image optimisation)
     * - favicon.ico
     */
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
