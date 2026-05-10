/**
 * Tests for useListUrlState hook.
 *
 * We mock next/navigation to control searchParams and capture router.replace calls.
 */

import { renderHook, act } from "@testing-library/react";
import { useListUrlState } from "../use-list-url-state";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockReplace = jest.fn();
let mockSearchParamsString = "";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
  usePathname: () => "/test",
  useSearchParams: () => {
    // Return a URLSearchParams-compatible object or null to simulate SSR
    if (mockSearchParamsString === "__null__") return null;
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
  mockReplace.mockClear();
  mockSearchParamsString = "";
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useListUrlState", () => {
  // (a) Hydrate from URL on mount
  it("hydrates state from URL on mount", () => {
    setUrl("status=open&page=3");

    const { result } = renderHook(() =>
      useListUrlState({
        defaults: { q: "", status: "all", page: 0 },
      })
    );

    expect(result.current[0].status).toBe("open");
    expect(result.current[0].page).toBe(3);
  });

  // (b) Default suppression — defaults produce clean URL
  it("returns defaults when URL has no params", () => {
    setUrl("");

    const { result } = renderHook(() =>
      useListUrlState({
        defaults: { q: "", status: "all", page: 0 },
      })
    );

    const [state] = result.current;
    expect(state.q).toBe("");
    expect(state.status).toBe("all");
    expect(state.page).toBe(0);
  });

  // (c) setParams writes to URL via replace
  it("setParams calls router.replace with the new URL", () => {
    setUrl("");

    const { result } = renderHook(() =>
      useListUrlState({
        defaults: { q: "", status: "all", page: 0 },
      })
    );

    act(() => {
      result.current[1]({ status: "open" });
    });

    expect(mockReplace).toHaveBeenCalledTimes(1);
    const [url] = mockReplace.mock.calls[0];
    expect(url).toContain("status=open");
  });

  // Default suppression — setting a param to default removes it from URL
  it("omits default values from URL when set via setParams", () => {
    setUrl("status=open");

    const { result } = renderHook(() =>
      useListUrlState({
        defaults: { q: "", status: "all", page: 0 },
      })
    );

    act(() => {
      result.current[1]({ status: "all" }); // reset to default
    });

    const [url] = mockReplace.mock.calls[0];
    expect(url).not.toContain("status");
  });

  // (d) resetPageOn resets page key when other keys change
  it("resets page to default when a resetPageOn key changes", () => {
    setUrl("page=5&status=open");

    const { result } = renderHook(() =>
      useListUrlState({
        defaults: { q: "", status: "all", page: 0 },
        resetPageOn: ["q", "status"],
      })
    );

    act(() => {
      result.current[1]({ status: "closed" });
    });

    const [url] = mockReplace.mock.calls[0];
    // page should be reset to 0 (default), which is omitted from URL
    expect(url).not.toContain("page=");
    expect(url).toContain("status=closed");
  });

  // resetPageOn does NOT reset page when patch already includes pageKey
  it("does not double-reset page when patch explicitly sets page", () => {
    setUrl("page=5&status=open");

    const { result } = renderHook(() =>
      useListUrlState({
        defaults: { q: "", status: "all", page: 0 },
        resetPageOn: ["q", "status"],
      })
    );

    act(() => {
      result.current[1]({ status: "closed", page: 2 });
    });

    const [url] = mockReplace.mock.calls[0];
    expect(url).toContain("page=2");
  });

  // (e) Custom serializer round-trips
  it("uses custom serializer for parse and serialize", () => {
    // Use string values (valid ListParamValue) with a custom serializer
    // that reverses the string on serialize and parse.
    setUrl("tag=olleh"); // "hello" reversed

    const { result } = renderHook(() =>
      useListUrlState({
        defaults: { tag: "world" },
        serializers: {
          tag: {
            // Custom: store reversed string in URL
            parse: (raw) => {
              if (raw === null) return "world";
              return raw.split("").reverse().join("");
            },
            serialize: (value) => {
              if (value === "world") return null; // default → suppress
              return (value as string).split("").reverse().join("");
            },
          },
        },
      })
    );

    // "olleh" parsed with reverse → "hello"
    expect(result.current[0].tag).toBe("hello");

    act(() => {
      result.current[1]({ tag: "test" });
    });

    const [url] = mockReplace.mock.calls[0];
    // "test" reversed → "tset"
    expect(url).toContain("tag=tset");
  });

  // (f) Multi-key patch batched into single replace call
  it("batches multi-key patch into a single router.replace call", () => {
    setUrl("");

    const { result } = renderHook(() =>
      useListUrlState({
        defaults: { q: "", status: "all", page: 0 },
      })
    );

    act(() => {
      result.current[1]({ q: "honda", status: "open", page: 2 });
    });

    // Only ONE replace call, not three
    expect(mockReplace).toHaveBeenCalledTimes(1);
    const [url] = mockReplace.mock.calls[0];
    expect(url).toContain("q=honda");
    expect(url).toContain("status=open");
    expect(url).toContain("page=2");
  });

  // (g) SSR/Suspense: hook renders without crashing when searchParams is null
  it("renders without crashing when searchParams is null (SSR)", () => {
    mockSearchParamsString = "__null__";

    expect(() => {
      renderHook(() =>
        useListUrlState({
          defaults: { q: "", status: "all", page: 0 },
        })
      );
    }).not.toThrow();
  });

  it("returns defaults when searchParams is null (SSR)", () => {
    mockSearchParamsString = "__null__";

    const { result } = renderHook(() =>
      useListUrlState({
        defaults: { q: "", status: "all", page: 0 },
      })
    );

    const [state] = result.current;
    expect(state.q).toBe("");
    expect(state.status).toBe("all");
    expect(state.page).toBe(0);
  });

  // Boolean param handling
  it("parses boolean params correctly", () => {
    setUrl("active=true");

    const { result } = renderHook(() =>
      useListUrlState({
        defaults: { active: false },
      })
    );

    expect(result.current[0].active).toBe(true);
  });

  it("serializes boolean defaults as absent from URL", () => {
    setUrl("");

    const { result } = renderHook(() =>
      useListUrlState({
        defaults: { active: false },
      })
    );

    act(() => {
      result.current[1]({ active: false });
    });

    const [url] = mockReplace.mock.calls[0];
    expect(url).not.toContain("active");
  });
});
