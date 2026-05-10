"use client";

import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  useRef,
  useEffect,
} from "react";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogAction,
  AlertDialogCancel,
} from "@/components/ui/alert-dialog";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DirtyFormContextType {
  /** Ids of forms currently in a dirty state */
  dirtyForms: ReadonlySet<string>;
  /** True if any form is dirty */
  hasAnyDirty: boolean;
  /** Register a formId as dirty */
  registerDirty: (formId: string) => void;
  /** Unregister a formId (it was saved or discarded) */
  clearDirty: (formId: string) => void;
  /**
   * Gate navigation. Returns a promise that resolves to:
   * - true  → proceed with navigation
   * - false → user cancelled
   *
   * When !hasAnyDirty, resolves true immediately.
   * When hasAnyDirty, opens the imperative AlertDialog and resolves on user action.
   */
  guardNavigation: (intendedHref: string) => Promise<boolean>;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const DirtyFormContext = createContext<DirtyFormContextType | undefined>(
  undefined
);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function DirtyFormProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [dirtyForms, setDirtyForms] = useState<ReadonlySet<string>>(
    new Set<string>()
  );
  // Whether the imperative AlertDialog is open
  const [dialogOpen, setDialogOpen] = useState(false);
  // Pending promise resolver — set when guardNavigation opens the dialog
  const resolverRef = useRef<((value: boolean) => void) | null>(null);

  const hasAnyDirty = dirtyForms.size > 0;

  // beforeunload listener — attached when hasAnyDirty, detached when clean
  useEffect(() => {
    if (!hasAnyDirty) return;

    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      // Modern browsers require returnValue to be set
      e.returnValue = "";
    };

    window.addEventListener("beforeunload", handler);
    return () => {
      window.removeEventListener("beforeunload", handler);
    };
  }, [hasAnyDirty]);

  const registerDirty = useCallback((formId: string) => {
    setDirtyForms((prev) => {
      if (prev.has(formId)) return prev;
      const next = new Set(prev);
      next.add(formId);
      return next;
    });
  }, []);

  const clearDirty = useCallback((formId: string) => {
    setDirtyForms((prev) => {
      if (!prev.has(formId)) return prev;
      const next = new Set(prev);
      next.delete(formId);
      return next;
    });
  }, []);

  const guardNavigation = useCallback(
    (intendedHref: string): Promise<boolean> => {
      // Suppress unused parameter warning — kept for future use (e.g. navigating after confirm)
      void intendedHref;

      if (!hasAnyDirty) {
        return Promise.resolve(true);
      }

      // Open the dialog and return a promise that resolves on user action
      setDialogOpen(true);
      return new Promise<boolean>((resolve) => {
        resolverRef.current = resolve;
      });
    },
    [hasAnyDirty]
  );

  // Called when user clicks "Descartar y salir"
  const handleConfirm = useCallback(() => {
    setDialogOpen(false);
    resolverRef.current?.(true);
    resolverRef.current = null;
  }, []);

  // Called when user clicks "Cancelar"
  const handleCancel = useCallback(() => {
    setDialogOpen(false);
    resolverRef.current?.(false);
    resolverRef.current = null;
  }, []);

  return (
    <DirtyFormContext.Provider
      value={{
        dirtyForms,
        hasAnyDirty,
        registerDirty,
        clearDirty,
        guardNavigation,
      }}
    >
      {children}

      {/* Imperative AlertDialog — rendered at provider level, one instance */}
      <AlertDialog open={dialogOpen} onOpenChange={(open) => {
        if (!open) handleCancel();
      }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Salir sin guardar?</AlertDialogTitle>
            <AlertDialogDescription>
              Tienes cambios sin guardar que se perderán.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={handleCancel}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirm}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Descartar y salir
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </DirtyFormContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useDirtyForm(): DirtyFormContextType {
  const context = useContext(DirtyFormContext);
  if (context === undefined) {
    throw new Error(
      "useDirtyForm must be used within a DirtyFormProvider"
    );
  }
  return context;
}

/**
 * Defensive version — returns a no-op context when provider is absent.
 * Use in components (like Sidebar) that may render outside the provider tree.
 */
export function useDirtyFormSafe(): DirtyFormContextType {
  const context = useContext(DirtyFormContext);
  if (context === undefined) {
    return {
      dirtyForms: new Set<string>(),
      hasAnyDirty: false,
      registerDirty: () => {},
      clearDirty: () => {},
      guardNavigation: () => Promise.resolve(true),
    };
  }
  return context;
}
