"use client";

import { useEffect, useCallback, useRef } from "react";
import { useDirtyFormSafe } from "@/contexts/dirty-form-context";

interface UseDirtyGuardConfig {
  /** Whether the form currently has unsaved changes */
  isDirty: boolean;
  /** Unique identifier for this form within the provider */
  formId: string;
}

interface UseDirtyGuardResult {
  /**
   * Call this after a successful save to imperatively clear dirty state.
   * Useful when the isDirty value may be stale or take a render cycle to update.
   */
  clearDirty: () => void;
}

/**
 * useDirtyGuard — registers a form's dirty state with DirtyFormProvider.
 *
 * - When isDirty flips true → calls registerDirty(formId)
 * - When isDirty flips false → calls clearDirty(formId)
 * - On unmount → defensively calls clearDirty(formId)
 *
 * beforeunload protection is managed at the provider level (single listener).
 *
 * @example
 * const { clearDirty } = useDirtyGuard({ isDirty: hasChanges, formId: `users:main:${id}` });
 * // On successful save:
 * await api.save(...);
 * clearDirty();
 */
export function useDirtyGuard({
  isDirty,
  formId,
}: UseDirtyGuardConfig): UseDirtyGuardResult {
  const { registerDirty, clearDirty: ctxClearDirty } = useDirtyFormSafe();

  // Track prev isDirty to avoid unnecessary register/clear calls on re-renders
  const prevIsDirtyRef = useRef<boolean>(false);
  // Track whether we've registered dirty to properly clean up on unmount
  const isRegisteredRef = useRef<boolean>(false);

  // Sync dirty state with context
  useEffect(() => {
    if (isDirty === prevIsDirtyRef.current) return;
    prevIsDirtyRef.current = isDirty;

    if (isDirty) {
      registerDirty(formId);
      isRegisteredRef.current = true;
    } else {
      ctxClearDirty(formId);
      isRegisteredRef.current = false;
    }
  }, [isDirty, formId, registerDirty, ctxClearDirty]);

  // Defensive cleanup on unmount
  useEffect(() => {
    return () => {
      if (isRegisteredRef.current) {
        ctxClearDirty(formId);
        isRegisteredRef.current = false;
      }
    };
    // formId and ctxClearDirty are stable — intentionally omitted from deps
    // to avoid re-running the cleanup on every formId change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Stable clearDirty callback for imperative use after save
  const clearDirty = useCallback(() => {
    ctxClearDirty(formId);
    isRegisteredRef.current = false;
    prevIsDirtyRef.current = false;
  }, [formId, ctxClearDirty]);

  return { clearDirty };
}
