/**
 * C2 — auth-context: verify no localStorage reads on mount.
 *
 * REQ-2: auth-context MUST NOT call localStorage.getItem("admin_token") or
 * decode a JWT in the browser. Auth state derives exclusively from /admin/me.
 */

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => "/",
}));

jest.mock("jose", () => ({
  decodeJwt: jest.fn(() => ({ exp: 9999999999 })),
  jwtVerify: jest.fn(),
  importSPKI: jest.fn(),
}));

// ---------------------------------------------------------------------------
// Imports
// ---------------------------------------------------------------------------

import React from "react";
import { render, waitFor } from "@testing-library/react";
import { AuthProvider } from "@/contexts/auth-context";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockFetch(status: number, body: unknown): jest.Mock {
  const fn = jest.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => null },
    json: async () => body,
  } as unknown as Response);
  global.fetch = fn;
  return fn;
}

// ---------------------------------------------------------------------------
// C2 — no localStorage on mount
// ---------------------------------------------------------------------------

describe("AuthProvider — no localStorage on mount", () => {
  let getItemSpy: jest.SpyInstance;

  beforeEach(() => {
    getItemSpy = jest.spyOn(Storage.prototype, "getItem");
  });

  afterEach(() => {
    jest.restoreAllMocks();
    global.fetch = undefined as unknown as typeof fetch;
  });

  it("C2a: does not call localStorage.getItem('admin_token') on mount", async () => {
    const fetchSpy = mockFetch(200, {
      id: "1",
      username: "admin",
      display_name: "Admin",
      role: "admin",
    });

    render(
      <AuthProvider>
        <div>child</div>
      </AuthProvider>
    );

    // Wait for the async checkAuth to complete
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled();
    });

    const adminTokenReads = getItemSpy.mock.calls.filter(
      ([key]) => key === "admin_token"
    );
    expect(adminTokenReads).toHaveLength(0);
  });

  it("C2b: calls /admin/me on mount (relies on cookie, not localStorage)", async () => {
    const fetchSpy = mockFetch(401, { detail: "Unauthorized" });

    // Suppress the location redirect side-effect from api.ts 401 handler
    Object.defineProperty(window, "location", {
      value: { href: "", pathname: "/dashboard", search: "" },
      writable: true,
    });

    render(
      <AuthProvider>
        <div>child</div>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringContaining("/admin/auth/me"),
        expect.objectContaining({ credentials: "include" })
      );
    });

  });
});
