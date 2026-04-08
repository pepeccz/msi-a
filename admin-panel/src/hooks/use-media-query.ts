"use client";

import { useState, useEffect } from "react";

/**
 * SSR-safe hook that evaluates a CSS media query string.
 *
 * Returns `false` during server-side rendering and on the first render
 * to prevent hydration mismatches. Subscribes to changes via
 * `MediaQueryList.addEventListener` once the component mounts.
 *
 * @param query  CSS media query string, e.g. "(max-width: 1023px)"
 * @returns      `true` when the query matches, `false` otherwise
 *
 * @example
 * const isMobile = useMediaQuery("(max-width: 1023px)");
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(false);

  useEffect(() => {
    // Guard: window is not available in SSR environments
    if (typeof window === "undefined") return;

    const mediaQueryList = window.matchMedia(query);

    // Sync state immediately with current value
    setMatches(mediaQueryList.matches);

    // Listen for future changes
    function handleChange(event: MediaQueryListEvent) {
      setMatches(event.matches);
    }

    mediaQueryList.addEventListener("change", handleChange);

    return () => {
      mediaQueryList.removeEventListener("change", handleChange);
    };
  }, [query]);

  return matches;
}

/**
 * Convenience hook that returns `true` when the viewport is smaller than
 * 1024px (the `lg` Tailwind breakpoint), i.e. when the sidebar should
 * render as a drawer instead of an inline panel.
 *
 * @returns `true` on mobile/tablet (< 1024px), `false` on desktop (≥ 1024px)
 */
export function useIsMobile(): boolean {
  return useMediaQuery("(max-width: 1023px)");
}
