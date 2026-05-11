/**
 * Security headers builder — shared between next.config.ts and jest tests.
 *
 * Exported separately so jest (CommonJS) can import it without having to
 * parse the full next.config.ts ESM module.
 */
import * as crypto from "crypto";
import { THEME_INIT_SCRIPT } from "./theme-init";

export interface HeaderEntry {
  key: string;
  value: string;
}

/**
 * Compute the CSP-formatted sha256 hash of THEME_INIT_SCRIPT.
 * Format: 'sha256-<base64>'
 */
export function computeThemeScriptHash(): string {
  const base64 = crypto
    .createHash("sha256")
    .update(THEME_INIT_SCRIPT)
    .digest("base64");
  return `'sha256-${base64}'`;
}

/**
 * Return the array of security headers to be used in next.config.ts headers().
 * This function is pure and synchronous — safe to call from both Next.js and jest.
 */
export function buildSecurityHeaders(): HeaderEntry[] {
  const themeHash = computeThemeScriptHash();

  // Chatwoot connect-src: allow the configured domain or fall back to 'self'.
  const chatwootUrl = process.env.NEXT_PUBLIC_CHATWOOT_URL ?? "";
  let chatwootOrigin = "'self'";
  try {
    if (chatwootUrl) {
      const { origin } = new URL(chatwootUrl);
      chatwootOrigin = origin;
    }
  } catch {
    // Malformed URL — keep 'self'
  }

  // Next.js dev mode (Turbopack/Webpack HMR) injects inline scripts and uses
  // eval() at runtime. The strict CSP blocks them, preventing React hydration
  // entirely — forms submit natively, no client interaction works. Relax in
  // dev only; production builds (`next start`) do not need these allowances.
  //
  // CSP spec: if a hash OR nonce is present in script-src, the browser ignores
  // 'unsafe-inline'. So in dev we drop the theme hash and rely on
  // 'unsafe-inline' instead. Tests run with NODE_ENV=test (not "development")
  // so the hash sentinel test continues to validate production CSP unchanged.
  const isDev = process.env.NODE_ENV === "development";
  const scriptSrc = isDev
    ? `script-src 'self' 'unsafe-inline' 'unsafe-eval'`
    : `script-src 'self' ${themeHash}`;
  const connectSrc = isDev
    ? `connect-src 'self' ${chatwootOrigin} ws: wss:`
    : `connect-src 'self' ${chatwootOrigin}`;

  const csp = [
    "default-src 'self'",
    scriptSrc,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: https:",
    connectSrc,
    "font-src 'self' data:",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join("; ");

  return [
    {
      key: "Content-Security-Policy",
      value: csp,
    },
    {
      key: "X-Frame-Options",
      value: "DENY",
    },
    {
      key: "X-Content-Type-Options",
      value: "nosniff",
    },
    {
      key: "Referrer-Policy",
      value: "strict-origin-when-cross-origin",
    },
    {
      key: "Permissions-Policy",
      value: "camera=(), microphone=(), geolocation=(), payment=()",
    },
  ];
}
