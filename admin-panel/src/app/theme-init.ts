/**
 * Inline theme-initialisation script injected via dangerouslySetInnerHTML in layout.tsx.
 * Keeping it here as a named constant ensures:
 *  1. The CSP sha256 hash in next.config.ts can be computed deterministically.
 *  2. A sentinel jest test (csp-hash.test.ts) fails immediately when the script drifts.
 *
 * ⚠️  Do NOT modify this string without also regenerating the hash in next.config.ts.
 *     The csp-hash test will catch drift automatically.
 */
export const THEME_INIT_SCRIPT = `(function(){var t=localStorage.getItem("msi-admin-theme");if(t==="dark"||(t==="system"&&matchMedia("(prefers-color-scheme:dark)").matches)){document.documentElement.classList.add("dark")}})()`;
