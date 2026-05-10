"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import {
  useListUrlState,
  type UseListUrlStateConfig,
  type ListParamValue,
} from "@/hooks/use-list-url-state";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UseDebouncedListUrlStateConfig<
  T extends Record<string, ListParamValue>,
> extends UseListUrlStateConfig<T> {
  /**
   * Keys in T whose changes are debounced before being written to the URL.
   * All other keys are written to the URL immediately (same as useListUrlState).
   */
  debounceFields: ReadonlyArray<keyof T>;
  /**
   * Debounce delay in milliseconds. Defaults to 300ms.
   */
  delayMs?: number;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * useDebouncedListUrlState — Extends useListUrlState with per-field debouncing.
 *
 * Useful for pages where certain fields (e.g. free-text search) should not
 * update the URL on every keystroke — which would trigger rapid API calls and
 * reset timers (like a 30s auto-refresh interval).
 *
 * Non-debounced fields are written to the URL immediately as usual.
 * Debounced fields are held in local state and only written to the URL after
 * `delayMs` ms of inactivity.
 *
 * The returned [params, setParams] tuple has the same shape as useListUrlState:
 * - `params` reflects the URL for non-debounced keys; for debounced keys, it
 *   reflects the local (unsettled) value so the search input stays responsive.
 * - `setParams` accepts a patch with any mix of debounced and non-debounced keys.
 *
 * @example
 * const [params, setParams] = useDebouncedListUrlState({
 *   defaults: { q: "", status: "all", page: 0 },
 *   resetPageOn: ["q", "status"],
 *   debounceFields: ["q"],
 *   delayMs: 300,
 * });
 *
 * // Search input stays responsive (reflects local state, not URL):
 * <input value={params.q} onChange={(e) => setParams({ q: e.target.value })} />
 */
export function useDebouncedListUrlState<
  T extends Record<string, ListParamValue>,
>(
  config: UseDebouncedListUrlStateConfig<T>
): readonly [T, (patch: Partial<T>) => void] {
  const { debounceFields, delayMs = 300, ...urlStateConfig } = config;

  // Ground truth: URL-synced state
  const [urlParams, setUrlParams] = useListUrlState(urlStateConfig);

  // Local "pending" state for debounced fields only
  // Initialised from the URL so the input shows the correct value on mount.
  const [localDebounced, setLocalDebounced] = useState<Partial<T>>(() => {
    const initial: Partial<T> = {};
    for (const key of debounceFields) {
      initial[key] = urlParams[key];
    }
    return initial;
  });

  // Timer ref per debounced key
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  // Merged params: URL for non-debounced keys, local for debounced keys
  const params = useMemo<T>(() => {
    return { ...urlParams, ...localDebounced } as T;
  }, [urlParams, localDebounced]);

  // Stable setter
  const setParams = useCallback(
    (patch: Partial<T>) => {
      const immediatePatch: Partial<T> = {};
      const debouncedPatch: Partial<T> = {};

      for (const key in patch) {
        const k = key as keyof T;
        if (debounceFields.includes(k)) {
          debouncedPatch[k] = patch[k];
        } else {
          immediatePatch[k] = patch[k];
        }
      }

      // Apply non-debounced keys immediately to URL
      if (Object.keys(immediatePatch).length > 0) {
        setUrlParams(immediatePatch);
      }

      // Apply debounced keys: update local state immediately (keeps input
      // responsive), then schedule URL write after delayMs
      if (Object.keys(debouncedPatch).length > 0) {
        setLocalDebounced((prev) => ({ ...prev, ...debouncedPatch }));

        for (const key in debouncedPatch) {
          // Clear any existing timer for this key
          if (timers.current[key]) {
            clearTimeout(timers.current[key]);
          }
          timers.current[key] = setTimeout(() => {
            setUrlParams({ [key]: debouncedPatch[key as keyof T] } as Partial<T>);
          }, delayMs);
        }
      }
    },
    [debounceFields, delayMs, setUrlParams]
  );

  // Cleanup timers on unmount
  useEffect(() => {
    return () => {
      for (const t of Object.values(timers.current)) {
        clearTimeout(t);
      }
    };
  }, []);

  return [params, setParams] as const;
}
