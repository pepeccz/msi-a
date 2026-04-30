/**
 * C1 — api.ts: verify that no localStorage reads or writes occur for admin_token.
 *
 * REQ-2: api.ts MUST NOT read or write localStorage for any token key.
 * All auth is conveyed via httpOnly cookie (credentials: "include").
 */

// ---------------------------------------------------------------------------
// Mocks — must be hoisted before imports
// ---------------------------------------------------------------------------

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => "/",
}));

// Mock jose (ESM, not transformable in jsdom)
jest.mock("jose", () => ({
  decodeJwt: jest.fn(() => ({ exp: 9999999999 })),
  jwtVerify: jest.fn(),
  importSPKI: jest.fn(),
}));

// ---------------------------------------------------------------------------
// Imports
// ---------------------------------------------------------------------------

import { api } from "@/lib/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockFetch(status: number, body: unknown): jest.SpyInstance {
  const mockFn = jest.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => null },
    json: async () => body,
  } as unknown as Response);
  global.fetch = mockFn;
  return mockFn;
}

// ---------------------------------------------------------------------------
// C1 — localStorage never touched
// ---------------------------------------------------------------------------

describe("api.ts — no localStorage access for admin_token", () => {
  let getItemSpy: jest.SpyInstance;
  let setItemSpy: jest.SpyInstance;
  let removeItemSpy: jest.SpyInstance;

  beforeEach(() => {
    getItemSpy = jest.spyOn(Storage.prototype, "getItem");
    setItemSpy = jest.spyOn(Storage.prototype, "setItem");
    removeItemSpy = jest.spyOn(Storage.prototype, "removeItem");
  });

  afterEach(() => {
    jest.restoreAllMocks();
    // Restore fetch
    global.fetch = undefined as unknown as typeof fetch;
  });

  it("C1a: api.getMe() does not read localStorage", async () => {
    mockFetch(200, {
      id: "1",
      username: "admin",
      display_name: "Admin",
      role: "admin",
    });

    await api.getMe();

    const adminTokenReads = getItemSpy.mock.calls.filter(
      ([key]) => key === "admin_token"
    );
    expect(adminTokenReads).toHaveLength(0);
    // fetchSpy cleanup handled in afterEach
  });

  it("C1b: api.login() does not write localStorage", async () => {
    mockFetch(200, {
      access_token: "tok.123.abc",
      token_type: "bearer",
      expires_in: 3600,
    });

    await api.login("admin", "password");

    const adminTokenWrites = setItemSpy.mock.calls.filter(
      ([key]) => key === "admin_token"
    );
    expect(adminTokenWrites).toHaveLength(0);
    // fetchSpy cleanup handled in afterEach
  });

  it("C1c: api.logout() does not remove from localStorage", async () => {
    mockFetch(200, undefined);

    await api.logout();

    const adminTokenRemovals = removeItemSpy.mock.calls.filter(
      ([key]) => key === "admin_token"
    );
    expect(adminTokenRemovals).toHaveLength(0);
    // fetchSpy cleanup handled in afterEach
  });

  it("C1d: api.getMe() 401 does not touch localStorage", async () => {
    // Mock window.location to prevent jsdom navigation errors
    Object.defineProperty(window, "location", {
      value: { href: "", pathname: "/dashboard", search: "" },
      writable: true,
    });

    mockFetch(401, { detail: "Token expired or invalid" });

    await api.getMe().catch(() => {});

    const adminTokenOps = [
      ...getItemSpy.mock.calls,
      ...setItemSpy.mock.calls,
      ...removeItemSpy.mock.calls,
    ].filter(([key]) => key === "admin_token");

    expect(adminTokenOps).toHaveLength(0);
    // fetchSpy cleanup handled in afterEach
  });
});
