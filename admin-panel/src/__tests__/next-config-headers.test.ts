/**
 * Headers shape test — D4
 *
 * Validates that buildSecurityHeaders() returns all 5 required security
 * headers with the correct shape and key values.
 */
import { buildSecurityHeaders } from "@/app/next.config.headers";

describe("next.config security headers", () => {
  const headers = buildSecurityHeaders();

  function findHeader(key: string) {
    return headers.find((h) => h.key === key);
  }

  it("returns exactly 5 headers", () => {
    expect(headers).toHaveLength(5);
  });

  it("Content-Security-Policy is present and contains sha256-", () => {
    const h = findHeader("Content-Security-Policy");
    expect(h).toBeDefined();
    expect(h!.value).toContain("sha256-");
  });

  it("Content-Security-Policy contains all required directives", () => {
    const value = findHeader("Content-Security-Policy")!.value;
    expect(value).toContain("default-src 'self'");
    expect(value).toContain("script-src 'self'");
    expect(value).toContain("style-src 'self'");
    expect(value).toContain("img-src 'self'");
    expect(value).toContain("connect-src");
    expect(value).toContain("font-src 'self'");
    expect(value).toContain("frame-ancestors 'none'");
    expect(value).toContain("base-uri 'self'");
    expect(value).toContain("form-action 'self'");
  });

  it("X-Frame-Options is DENY", () => {
    const h = findHeader("X-Frame-Options");
    expect(h).toBeDefined();
    expect(h!.value).toBe("DENY");
  });

  it("X-Content-Type-Options is nosniff", () => {
    const h = findHeader("X-Content-Type-Options");
    expect(h).toBeDefined();
    expect(h!.value).toBe("nosniff");
  });

  it("Referrer-Policy is strict-origin-when-cross-origin", () => {
    const h = findHeader("Referrer-Policy");
    expect(h).toBeDefined();
    expect(h!.value).toBe("strict-origin-when-cross-origin");
  });

  it("Permissions-Policy covers camera, microphone, geolocation, payment", () => {
    const h = findHeader("Permissions-Policy");
    expect(h).toBeDefined();
    const value = h!.value;
    expect(value).toContain("camera=()");
    expect(value).toContain("microphone=()");
    expect(value).toContain("geolocation=()");
    expect(value).toContain("payment=()");
  });
});
