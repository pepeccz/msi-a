/**
 * CSP hash sentinel — D2
 *
 * Ensures THEME_INIT_SCRIPT and the sha256 hash baked into next.config.ts
 * never drift. If you change the theme-init script you MUST regenerate the
 * hash in next.config.ts (and next.config.headers.ts).
 */
import * as crypto from "crypto";
import { THEME_INIT_SCRIPT } from "@/app/theme-init";
import { buildSecurityHeaders } from "@/app/next.config.headers";

describe("CSP hash sentinel", () => {
  it("THEME_INIT_SCRIPT is a non-empty string", () => {
    expect(typeof THEME_INIT_SCRIPT).toBe("string");
    expect(THEME_INIT_SCRIPT.length).toBeGreaterThan(0);
  });

  it("THEME_INIT_SCRIPT starts with IIFE pattern", () => {
    expect(THEME_INIT_SCRIPT).toMatch(/^\(function\(\)/);
  });

  it("computed sha256 of THEME_INIT_SCRIPT matches hash in CSP header", () => {
    const computed = crypto
      .createHash("sha256")
      .update(THEME_INIT_SCRIPT)
      .digest("base64");

    const expectedHash = `sha256-${computed}`;

    const headers = buildSecurityHeaders();
    const cspEntry = headers.find((h) => h.key === "Content-Security-Policy");
    expect(cspEntry).toBeDefined();
    expect(cspEntry!.value).toContain(`'${expectedHash}'`);
  });
});
