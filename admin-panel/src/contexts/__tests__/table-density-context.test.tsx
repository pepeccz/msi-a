/**
 * Tests for TableDensityContext + TableDensityProvider + useTableDensity.
 */

import React from "react";
import { renderHook, act } from "@testing-library/react";
import { TableDensityProvider, useTableDensity } from "../table-density-context";

// ---------------------------------------------------------------------------
// localStorage mock
// ---------------------------------------------------------------------------

const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();

Object.defineProperty(window, "localStorage", { value: localStorageMock });

beforeEach(() => {
  localStorageMock.clear();
});

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------

function wrapper({ children }: { children: React.ReactNode }) {
  return <TableDensityProvider>{children}</TableDensityProvider>;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("TableDensityContext", () => {
  // (a) Default comfortable when no localStorage key
  it("defaults to comfortable when no localStorage key is set", () => {
    const { result } = renderHook(() => useTableDensity(), { wrapper });
    expect(result.current.density).toBe("comfortable");
  });

  // (b) toggleDensity writes to localStorage
  it("toggleDensity persists to localStorage", async () => {
    const { result } = renderHook(() => useTableDensity(), { wrapper });

    act(() => {
      result.current.toggleDensity();
    });

    // Wait for useEffect to fire
    await act(async () => {});

    expect(localStorageMock.getItem("msia-admin:table-density")).toBe("compact");
  });

  // (c) Hydrates from localStorage on mount
  it("hydrates from localStorage on mount", async () => {
    localStorageMock.setItem("msia-admin:table-density", "compact");

    const { result } = renderHook(() => useTableDensity(), { wrapper });

    // After hydration useEffect
    await act(async () => {});

    expect(result.current.density).toBe("compact");
  });

  // (d) Toggle switches value between comfortable/compact
  it("toggle switches between comfortable and compact", () => {
    const { result } = renderHook(() => useTableDensity(), { wrapper });

    expect(result.current.density).toBe("comfortable");

    act(() => {
      result.current.toggleDensity();
    });
    expect(result.current.density).toBe("compact");

    act(() => {
      result.current.toggleDensity();
    });
    expect(result.current.density).toBe("comfortable");
  });

  // (e) SSR-safe: initial state is "comfortable" (no window access during server render)
  // We verify this indirectly: the hook starts as "comfortable" synchronously before
  // the useEffect hydration runs.
  it("starts with comfortable before hydration (SSR-safe initial state)", () => {
    const { result } = renderHook(() => useTableDensity(), { wrapper });
    // Immediately after render, before effects run, should be comfortable
    expect(result.current.density).toBe("comfortable");
  });

  // setDensity works directly
  it("setDensity updates density directly", () => {
    const { result } = renderHook(() => useTableDensity(), { wrapper });

    act(() => {
      result.current.setDensity("compact");
    });

    expect(result.current.density).toBe("compact");
  });

  // useTableDensity throws outside provider
  it("throws when used outside provider", () => {
    // Suppress console.error for this test
    const spy = jest.spyOn(console, "error").mockImplementation(() => {});
    expect(() => renderHook(() => useTableDensity())).toThrow(
      "useTableDensity must be used within a TableDensityProvider"
    );
    spy.mockRestore();
  });
});
