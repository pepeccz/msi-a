/**
 * Unit tests for Edge Middleware auth guard.
 *
 * Tests cover REQ-3 (spec): cookie-presence gate for protected routes.
 * The middleware does NOT verify the JWT signature — that is a backend invariant.
 *
 * Mocking strategy: minimal mocks for NextRequest / NextResponse that preserve
 * the exact surface the middleware uses (cookies.has, redirect, next).
 */

import { middleware } from "../middleware";
import { NextRequest, NextResponse } from "next/server";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// next/server is an Edge-Runtime module — jest (jsdom) cannot import it natively.
// We replace it with a thin, type-faithful stub.
jest.mock("next/server", () => {
  const redirect = jest.fn((url: URL, init?: { status?: number }) => ({
    _type: "redirect",
    url: url.toString(),
    status: init?.status ?? 307,
  }));

  const next = jest.fn(() => ({
    _type: "next",
  }));

  const NextResponseMock = { redirect, next };

  // NextRequest factory — builds a minimal object matching the middleware API
  class NextRequestMock {
    public nextUrl: URL;
    public cookies: { has: (name: string) => boolean };

    constructor(url: string, options?: { cookies?: Record<string, string> }) {
      this.nextUrl = new URL(url, "http://localhost");
      const jar: Record<string, string> = options?.cookies ?? {};
      this.cookies = {
        has: (name: string) => Object.prototype.hasOwnProperty.call(jar, name),
      };
    }
  }

  return {
    NextResponse: NextResponseMock,
    NextRequest: NextRequestMock,
  };
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeRequest(
  path: string,
  options?: { cookie?: boolean }
): NextRequest {
  const cookies: Record<string, string> =
    options?.cookie ? { admin_token: "some-value" } : {};
  return new NextRequest(`http://localhost${path}`, { cookies }) as NextRequest;
}

// ---------------------------------------------------------------------------
// B1 — scaffold (implicit: if this file loads without error, scaffold is OK)
// B2 — no cookie → 307 with returnTo
// ---------------------------------------------------------------------------

describe("middleware — anonymous request", () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  it("B2: redirects to /login with returnTo when admin_token cookie is absent", () => {
    const req = makeRequest("/tariffs");
    const res = middleware(req);

    expect(NextResponse.redirect).toHaveBeenCalledTimes(1);

    const [redirectUrl, init] = (NextResponse.redirect as jest.Mock).mock.calls[0];
    expect(redirectUrl).toBeInstanceOf(URL);
    expect(redirectUrl.pathname).toBe("/login");
    expect(redirectUrl.searchParams.get("returnTo")).toBe("/tariffs");

    expect((res as { status: number }).status).toBe(307);
  });

  it("B2: returnTo encodes the full pathname for nested routes", () => {
    const req = makeRequest("/settings/system");
    middleware(req);

    const [redirectUrl] = (NextResponse.redirect as jest.Mock).mock.calls[0];
    expect(redirectUrl.searchParams.get("returnTo")).toBe("/settings/system");
  });
});

// ---------------------------------------------------------------------------
// B3 — cookie present → passes through
// ---------------------------------------------------------------------------

describe("middleware — authenticated request", () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  it("B3: calls NextResponse.next() when admin_token cookie is present", () => {
    const req = makeRequest("/tariffs", { cookie: true });
    const res = middleware(req);

    expect(NextResponse.redirect).not.toHaveBeenCalled();
    expect(NextResponse.next).toHaveBeenCalledTimes(1);
    expect((res as { _type: string })._type).toBe("next");
  });
});

// ---------------------------------------------------------------------------
// B4 — /login excluded
// ---------------------------------------------------------------------------

describe("middleware — /login excluded", () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  it("B4: does NOT redirect when path is /login (no cookie)", () => {
    const req = makeRequest("/login");
    middleware(req);

    expect(NextResponse.redirect).not.toHaveBeenCalled();
    expect(NextResponse.next).toHaveBeenCalledTimes(1);
  });

  it("B4: does NOT redirect when path is /login (with cookie)", () => {
    const req = makeRequest("/login", { cookie: true });
    middleware(req);

    expect(NextResponse.redirect).not.toHaveBeenCalled();
    expect(NextResponse.next).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// B5 — /api/* not redirected
// ---------------------------------------------------------------------------

describe("middleware — /api/* excluded", () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  it("B5: does NOT redirect /api/* routes even without cookie", () => {
    const req = makeRequest("/api/admin/tariffs");
    middleware(req);

    expect(NextResponse.redirect).not.toHaveBeenCalled();
    expect(NextResponse.next).toHaveBeenCalledTimes(1);
  });

  it("B5: does NOT redirect nested /api/* paths", () => {
    const req = makeRequest("/api/admin/system/agent/logs");
    middleware(req);

    expect(NextResponse.redirect).not.toHaveBeenCalled();
    expect(NextResponse.next).toHaveBeenCalledTimes(1);
  });
});
