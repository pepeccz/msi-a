/**
 * Tests for useDirtyGuard hook.
 */

import { renderHook, act } from "@testing-library/react";
import { useDirtyGuard } from "../use-dirty-guard";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockRegisterDirty = jest.fn();
const mockClearDirty = jest.fn();

jest.mock("@/contexts/dirty-form-context", () => ({
  useDirtyFormSafe: () => ({
    registerDirty: mockRegisterDirty,
    clearDirty: mockClearDirty,
  }),
}));

// ---------------------------------------------------------------------------

beforeEach(() => {
  mockRegisterDirty.mockClear();
  mockClearDirty.mockClear();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useDirtyGuard", () => {
  // (a) Registers dirty when isDirty becomes true
  it("calls registerDirty when isDirty becomes true", () => {
    const { rerender } = renderHook(
      ({ isDirty }: { isDirty: boolean }) =>
        useDirtyGuard({ isDirty, formId: "test-form" }),
      { initialProps: { isDirty: false } }
    );

    expect(mockRegisterDirty).not.toHaveBeenCalled();

    rerender({ isDirty: true });

    expect(mockRegisterDirty).toHaveBeenCalledWith("test-form");
    expect(mockRegisterDirty).toHaveBeenCalledTimes(1);
  });

  // (b) Clears dirty when isDirty becomes false
  it("calls clearDirty when isDirty becomes false", () => {
    const { rerender } = renderHook(
      ({ isDirty }: { isDirty: boolean }) =>
        useDirtyGuard({ isDirty, formId: "test-form" }),
      { initialProps: { isDirty: true } }
    );

    // Initial mount with isDirty=true
    expect(mockRegisterDirty).toHaveBeenCalledWith("test-form");

    mockRegisterDirty.mockClear();

    rerender({ isDirty: false });

    expect(mockClearDirty).toHaveBeenCalledWith("test-form");
  });

  // (c) Clears dirty on unmount even if still isDirty=true
  it("calls clearDirty on unmount when isDirty is true", () => {
    const { unmount } = renderHook(() =>
      useDirtyGuard({ isDirty: true, formId: "test-form" })
    );

    mockClearDirty.mockClear();

    unmount();

    expect(mockClearDirty).toHaveBeenCalledWith("test-form");
  });

  // (c) Does not call clearDirty on unmount when not dirty
  it("does not call clearDirty on unmount when never registered dirty", () => {
    const { unmount } = renderHook(() =>
      useDirtyGuard({ isDirty: false, formId: "test-form" })
    );

    mockClearDirty.mockClear();

    unmount();

    expect(mockClearDirty).not.toHaveBeenCalled();
  });

  // (d) Returned clearDirty is stable reference across renders
  it("returned clearDirty is a stable reference across renders", () => {
    const { result, rerender } = renderHook(
      ({ isDirty }: { isDirty: boolean }) =>
        useDirtyGuard({ isDirty, formId: "test-form" }),
      { initialProps: { isDirty: false } }
    );

    const firstRef = result.current.clearDirty;

    rerender({ isDirty: false });

    expect(result.current.clearDirty).toBe(firstRef);
  });

  // (d) clearDirty returned by hook calls context clearDirty
  it("returned clearDirty calls ctxClearDirty imperatively", () => {
    const { result } = renderHook(() =>
      useDirtyGuard({ isDirty: true, formId: "test-form" })
    );

    mockClearDirty.mockClear();

    act(() => {
      result.current.clearDirty();
    });

    expect(mockClearDirty).toHaveBeenCalledWith("test-form");
  });

  // (e) No double-register on re-render with unchanged isDirty=true
  it("does not double-register on re-render when isDirty remains true", () => {
    const { rerender } = renderHook(
      ({ isDirty }: { isDirty: boolean }) =>
        useDirtyGuard({ isDirty, formId: "test-form" }),
      { initialProps: { isDirty: true } }
    );

    // Should have registered once on initial render
    expect(mockRegisterDirty).toHaveBeenCalledTimes(1);

    // Re-render with same isDirty=true — no additional register
    rerender({ isDirty: true });

    expect(mockRegisterDirty).toHaveBeenCalledTimes(1);
  });
});
