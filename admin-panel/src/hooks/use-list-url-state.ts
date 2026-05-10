"use client";

import { useCallback, useMemo } from "react";
import { useRouter, useSearchParams, usePathname } from "next/navigation";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ListParamValue = string | number | boolean | null;

export type Serializer<V> = {
  /** Parse a raw URL string (or null when absent) into the typed value */
  parse: (raw: string | null) => V;
  /** Serialize the typed value to a URL string, or null to omit from URL */
  serialize: (value: V) => string | null;
};

export type Serializers<T> = {
  [K in keyof T]: Serializer<T[K]>;
};

export interface UseListUrlStateConfig<
  T extends Record<string, ListParamValue>,
> {
  /** Default values for every param. TypeScript infers T from this object. */
  defaults: T;
  /** Override serializer per key. Falls back to built-in string/number/boolean. */
  serializers?: Partial<Serializers<T>>;
  /**
   * Keys whose change automatically resets the page key to its default.
   * The page reset is skipped when the patch already includes the pageKey.
   */
  resetPageOn?: ReadonlyArray<keyof T>;
  /**
   * Which key represents the page number/index.
   * Defaults to "page" if that key exists in defaults.
   */
  pageKey?: keyof T;
}

// ---------------------------------------------------------------------------
// Built-in serializers
// ---------------------------------------------------------------------------

function builtinSerializer<V extends ListParamValue>(
  defaultValue: V
): Serializer<V> {
  const type = typeof defaultValue;

  if (type === "number") {
    return {
      parse: (raw) => {
        if (raw === null) return defaultValue;
        const n = Number(raw);
        return (isNaN(n) ? defaultValue : n) as V;
      },
      serialize: (value) => {
        if (value === null || value === defaultValue) return null;
        return String(value);
      },
    };
  }

  if (type === "boolean") {
    return {
      parse: (raw) => {
        if (raw === null) return defaultValue;
        return (raw === "true") as V;
      },
      serialize: (value) => {
        if (value === null || value === defaultValue) return null;
        return String(value);
      },
    };
  }

  // string (including null default)
  return {
    parse: (raw) => {
      if (raw === null) return defaultValue;
      return raw as V;
    },
    serialize: (value) => {
      if (value === null || value === defaultValue) return null;
      return String(value);
    },
  };
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * useListUrlState — Synchronize list-page filter/sort/pagination state with
 * the URL via query parameters. Uses router.replace() (no history entries).
 *
 * @example
 * const [params, setParams] = useListUrlState({
 *   defaults: { q: '', status: 'all' as Status, page: 0 },
 *   resetPageOn: ['q', 'status'],
 * });
 */
export function useListUrlState<T extends Record<string, ListParamValue>>(
  config: UseListUrlStateConfig<T>
): readonly [T, (patch: Partial<T>) => void] {
  const {
    defaults,
    serializers: customSerializers,
    resetPageOn,
    pageKey: explicitPageKey,
  } = config;

  const router = useRouter();
  const pathname = usePathname();
  // useSearchParams() may be null during SSR — guard defensively
  const searchParams = useSearchParams();

  // Resolve the page key
  const pageKey = useMemo<keyof T | undefined>(() => {
    if (explicitPageKey !== undefined) return explicitPageKey;
    if ("page" in defaults) return "page" as keyof T;
    return undefined;
  }, [explicitPageKey, defaults]);

  // Build serializer map (custom overrides built-in)
  const serializerMap = useMemo<Serializers<T>>(() => {
    const map = {} as Serializers<T>;
    for (const key in defaults) {
      const k = key as keyof T;
      map[k] =
        (customSerializers?.[k] as Serializer<T[typeof k]>) ??
        (builtinSerializer(defaults[k]) as Serializer<T[typeof k]>);
    }
    return map;
  }, [defaults, customSerializers]);

  // Derive current state from URL — memoized on searchParams string repr
  const state = useMemo<T>(() => {
    const result = { ...defaults };
    for (const key in defaults) {
      const k = key as keyof T;
      const raw = searchParams ? searchParams.get(key) : null;
      result[k] = serializerMap[k].parse(raw) as T[typeof k];
    }
    return result;
    // searchParams object identity changes on every navigation — use toString()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams?.toString(), serializerMap, defaults]);

  // Stable setParams callback
  const setParams = useCallback(
    (patch: Partial<T>) => {
      // Start from current URL params (preserve keys not managed by this hook)
      const current = new URLSearchParams(
        searchParams ? searchParams.toString() : ""
      );

      // Determine if we need to reset the page key
      const patchKeys = Object.keys(patch) as Array<keyof T>;
      const shouldResetPage =
        pageKey !== undefined &&
        !(pageKey in patch) &&
        resetPageOn !== undefined &&
        patchKeys.some((k) => resetPageOn.includes(k));

      // Apply the patch
      const fullPatch: Partial<T> = { ...patch };
      if (shouldResetPage) {
        fullPatch[pageKey as keyof T] = defaults[pageKey as keyof T];
      }

      for (const key in fullPatch) {
        const k = key as keyof T;
        const serialized = serializerMap[k]?.serialize(fullPatch[k] as T[typeof k]);
        if (serialized === null || serialized === undefined) {
          current.delete(key);
        } else {
          current.set(key, serialized);
        }
      }

      const qs = current.toString();
      const url = qs ? `${pathname}?${qs}` : pathname;
      router.replace(url, { scroll: false });
    },
    [searchParams, pathname, router, pageKey, resetPageOn, defaults, serializerMap]
  );

  return [state, setParams] as const;
}
