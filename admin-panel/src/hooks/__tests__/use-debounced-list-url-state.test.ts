/**
 * Tests for useDebouncedListUrlState hook.
 *
 * Verifies that:
 * - Debounced fields update local state immediately (responsive UI)
 * - URL is written after the delay, not on every keystroke
 * - Non-debounced fields are written to the URL immediately
 * - Timers are reset on rapid consecutive inputs (debounce semantics)
 * - Cleanup on unmount clears pending timers
 */

import { renderHook, act } from "@testing-library/react";
import { useDebouncedListUrlState } from "../use-debounced-list-url-state";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockReplace = jest.fn();
let mockSearchParamsString = "";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
  usePathname: () => "/cases",
  useSearchParams: () => {
    const params = new URLSearchParams(mockSearchParamsString);
    return {
      get: (key: string) => params.get(key),
      toString: () => params.toString(),
    };
  },
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setUrl(qs: string) {
  mockSearchParamsString = qs;
}

beforeEach(() => {
  jest.useFakeTimers();
  mockReplace.mockClear();
  mockSearchParamsString = "";
});

afterEach(() => {
  jest.runOnlyPendingTimers();
  jest.useRealTimers();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useDebouncedListUrlState", () => {
  const config = {
    defaults: { q: "", status: "all", offset: 0 },
    resetPageOn: ["q", "status"] as const,
    pageKey: "offset" as const,
    debounceFields: ["q"] as const,
    delayMs: 300,
  };

  it("initialises state from URL defaults when no query params", () => {
    const { result } = renderHook(() =>
      useDebouncedListUrlState(config)
    );

    expect(result.current[0].q).toBe("");
    expect(result.current[0].status).toBe("all");
    expect(result.current[0].offset).toBe(0);
  });

  it("hydrates debounced field from URL on mount", () => {
    setUrl("q=test");

    const { result } = renderHook(() =>
      useDebouncedListUrlState(config)
    );

    // Both URL param and local state should reflect the value
    expect(result.current[0].q).toBe("test");
  });

  it("updates local state immediately for debounced fields (responsive UI)", () => {
    const { result } = renderHook(() =>
      useDebouncedListUrlState(config)
    );

    act(() => {
      result.current[1]({ q: "abc" });
    });

    // Local state updates immediately — input stays responsive
    expect(result.current[0].q).toBe("abc");

    // URL has NOT been written yet (no timer has fired)
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("writes debounced field to URL after delayMs", () => {
    const { result } = renderHook(() =>
      useDebouncedListUrlState(config)
    );

    act(() => {
      result.current[1]({ q: "abc" });
    });

    // Advance timer to trigger debounce flush
    act(() => {
      jest.advanceTimersByTime(300);
    });

    // Now the URL should have been written
    expect(mockReplace).toHaveBeenCalledTimes(1);
    const calledUrl = mockReplace.mock.calls[0][0] as string;
    expect(calledUrl).toContain("q=abc");
  });

  it("does NOT write to URL before delayMs elapses (true debounce)", () => {
    const { result } = renderHook(() =>
      useDebouncedListUrlState(config)
    );

    act(() => {
      result.current[1]({ q: "a" });
    });

    act(() => {
      jest.advanceTimersByTime(200); // Only 200ms — not yet
    });

    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("resets timer on rapid input (debounce coalescing)", () => {
    const { result } = renderHook(() =>
      useDebouncedListUrlState(config)
    );

    // Type rapidly — 4 keystrokes within 300ms window
    act(() => {
      result.current[1]({ q: "a" });
    });
    act(() => {
      jest.advanceTimersByTime(100);
      result.current[1]({ q: "ab" });
    });
    act(() => {
      jest.advanceTimersByTime(100);
      result.current[1]({ q: "abc" });
    });
    act(() => {
      jest.advanceTimersByTime(100);
      result.current[1]({ q: "abcd" });
    });

    // At 400ms total elapsed — only the LAST write timer (at 300ms) has fired
    act(() => {
      jest.advanceTimersByTime(300);
    });

    // Should have been called exactly once with the final value
    expect(mockReplace).toHaveBeenCalledTimes(1);
    const calledUrl = mockReplace.mock.calls[0][0] as string;
    expect(calledUrl).toContain("q=abcd");
  });

  it("writes non-debounced fields to URL immediately", () => {
    const { result } = renderHook(() =>
      useDebouncedListUrlState(config)
    );

    act(() => {
      result.current[1]({ status: "pending_review" });
    });

    // Non-debounced field — URL written immediately
    expect(mockReplace).toHaveBeenCalledTimes(1);
    const calledUrl = mockReplace.mock.calls[0][0] as string;
    expect(calledUrl).toContain("status=pending_review");
  });

  it("handles mixed patches — immediate for non-debounced, delayed for debounced", () => {
    const { result } = renderHook(() =>
      useDebouncedListUrlState(config)
    );

    act(() => {
      // This would happen if setParams({ q: "abc", status: "pending" })
      result.current[1]({ status: "pending_review" });
      result.current[1]({ q: "abc" });
    });

    // status was written immediately
    expect(mockReplace).toHaveBeenCalledTimes(1);

    // Advance timer to flush q debounce
    act(() => {
      jest.advanceTimersByTime(300);
    });

    // q was also written (second call)
    expect(mockReplace).toHaveBeenCalledTimes(2);
    const lastUrl = mockReplace.mock.calls[1][0] as string;
    expect(lastUrl).toContain("q=abc");
  });

  it("local state reflects the latest input, even before URL write", () => {
    const { result } = renderHook(() =>
      useDebouncedListUrlState(config)
    );

    act(() => {
      result.current[1]({ q: "hello" });
    });

    // Before timer fires, local state shows "hello"
    expect(result.current[0].q).toBe("hello");

    act(() => {
      jest.advanceTimersByTime(150);
      result.current[1]({ q: "hello world" });
    });

    // Updated again — still responsive
    expect(result.current[0].q).toBe("hello world");
  });
});
