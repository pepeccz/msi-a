/**
 * Tests for DirtyFormContext + DirtyFormProvider + useDirtyForm.
 */

import React from "react";
import { renderHook, act, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { DirtyFormProvider, useDirtyForm } from "../dirty-form-context";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock Radix AlertDialog to control rendering imperatively in tests
jest.mock("@/components/ui/alert-dialog", () => ({
  AlertDialog: ({ children, open }: { children: React.ReactNode; open: boolean }) =>
    open ? <div data-testid="alert-dialog">{children}</div> : null,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => (
    <h2>{children}</h2>
  ),
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => (
    <p>{children}</p>
  ),
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  AlertDialogAction: ({
    children,
    onClick,
    className,
  }: {
    children: React.ReactNode;
    onClick?: () => void;
    className?: string;
  }) => (
    <button onClick={onClick} className={className} data-testid="dialog-confirm">
      {children}
    </button>
  ),
  AlertDialogCancel: ({
    children,
    onClick,
  }: {
    children: React.ReactNode;
    onClick?: () => void;
  }) => (
    <button onClick={onClick} data-testid="dialog-cancel">
      {children}
    </button>
  ),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function wrapper({ children }: { children: React.ReactNode }) {
  return <DirtyFormProvider>{children}</DirtyFormProvider>;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("DirtyFormContext", () => {
  // (a) guardNavigation resolves true immediately when no dirty forms
  it("guardNavigation resolves true immediately when no dirty forms", async () => {
    const { result } = renderHook(() => useDirtyForm(), { wrapper });

    let resolved: boolean | null = null;
    await act(async () => {
      resolved = await result.current.guardNavigation("/some/path");
    });

    expect(resolved).toBe(true);
  });

  // (b) guardNavigation opens AlertDialog when hasAnyDirty
  it("guardNavigation opens AlertDialog when a form is dirty", async () => {
    const { result } = renderHook(() => useDirtyForm(), { wrapper });

    act(() => {
      result.current.registerDirty("form-1");
    });

    let promise: Promise<boolean>;
    act(() => {
      promise = result.current.guardNavigation("/some/path");
    });

    await waitFor(() => {
      expect(screen.queryByTestId("alert-dialog")).toBeInTheDocument();
    });

    // Cancel to resolve the promise and avoid open state leak
    act(() => {
      fireEvent.click(screen.getByTestId("dialog-cancel"));
    });

    await act(async () => { await promise!; });
  });

  // (c) "Descartar y salir" resolves true
  it("confirm button resolves guardNavigation with true", async () => {
    const { result } = renderHook(() => useDirtyForm(), { wrapper });

    act(() => {
      result.current.registerDirty("form-1");
    });

    let resolved: boolean | null = null;
    act(() => {
      result.current.guardNavigation("/path").then((v) => { resolved = v; });
    });

    await waitFor(() => {
      expect(screen.queryByTestId("dialog-confirm")).toBeInTheDocument();
    });

    act(() => {
      fireEvent.click(screen.getByTestId("dialog-confirm"));
    });

    await waitFor(() => expect(resolved).toBe(true));
  });

  // (d) "Cancelar" resolves false
  it("cancel button resolves guardNavigation with false", async () => {
    const { result } = renderHook(() => useDirtyForm(), { wrapper });

    act(() => {
      result.current.registerDirty("form-1");
    });

    let resolved: boolean | null = null;
    act(() => {
      result.current.guardNavigation("/path").then((v) => { resolved = v; });
    });

    await waitFor(() => {
      expect(screen.queryByTestId("dialog-cancel")).toBeInTheDocument();
    });

    act(() => {
      fireEvent.click(screen.getByTestId("dialog-cancel"));
    });

    await waitFor(() => expect(resolved).toBe(false));
  });

  // (e) beforeunload listener attached when any form registers dirty
  it("attaches beforeunload listener when a form is dirty", () => {
    const addSpy = jest.spyOn(window, "addEventListener");
    const { result } = renderHook(() => useDirtyForm(), { wrapper });

    act(() => {
      result.current.registerDirty("form-1");
    });

    expect(addSpy).toHaveBeenCalledWith("beforeunload", expect.any(Function));
    addSpy.mockRestore();
  });

  // (f) listener removed when all forms cleared
  it("detaches beforeunload listener when all forms cleared", () => {
    const removeSpy = jest.spyOn(window, "removeEventListener");
    const { result } = renderHook(() => useDirtyForm(), { wrapper });

    act(() => {
      result.current.registerDirty("form-1");
    });

    act(() => {
      result.current.clearDirty("form-1");
    });

    expect(removeSpy).toHaveBeenCalledWith("beforeunload", expect.any(Function));
    removeSpy.mockRestore();
  });

  // (g) Multiple formIds tracked independently
  it("tracks multiple formIds independently", () => {
    const { result } = renderHook(() => useDirtyForm(), { wrapper });

    act(() => {
      result.current.registerDirty("form-a");
      result.current.registerDirty("form-b");
    });

    expect(result.current.hasAnyDirty).toBe(true);
    expect(result.current.dirtyForms.has("form-a")).toBe(true);
    expect(result.current.dirtyForms.has("form-b")).toBe(true);

    act(() => {
      result.current.clearDirty("form-a");
    });

    // form-b still dirty
    expect(result.current.hasAnyDirty).toBe(true);
    expect(result.current.dirtyForms.has("form-b")).toBe(true);

    act(() => {
      result.current.clearDirty("form-b");
    });

    expect(result.current.hasAnyDirty).toBe(false);
  });

  // useDirtyForm throws outside provider
  it("throws when used outside provider", () => {
    const spy = jest.spyOn(console, "error").mockImplementation(() => {});
    expect(() => renderHook(() => useDirtyForm())).toThrow(
      "useDirtyForm must be used within a DirtyFormProvider"
    );
    spy.mockRestore();
  });
});
