"use client";

import { useState, useCallback, useEffect } from "react";
import api from "@/lib/api";
import type { InboxSidebarResponse, InboxNote } from "@/lib/types";

/**
 * Optimistic note shape — extends InboxNote with an internal marker used
 * during the in-flight period (before the server echoes back the real ID).
 */
interface OptimisticNote extends InboxNote {
  _optimistic?: true;
}

/**
 * useInboxSidebar
 *
 * Fetches the aggregated sidebar payload (client summary, active case, notes)
 * whenever `conversationHistoryId` changes. Exposes optimistic add/delete
 * operations that update the UI immediately and roll back on server error.
 *
 * Design: A10 (refetch on convId change only — no SWR), A11 (optimistic UI).
 */
export function useInboxSidebar(conversationHistoryId: string | null) {
  const [data, setData] = useState<InboxSidebarResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!conversationHistoryId) return;
    setIsLoading(true);
    setError(null);
    try {
      const result = await api.getInboxSidebar(conversationHistoryId);
      setData(result);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Error al cargar la ficha";
      setError(msg);
      setData(null);
    } finally {
      setIsLoading(false);
    }
  }, [conversationHistoryId]);

  useEffect(() => {
    if (!conversationHistoryId) {
      setData(null);
      setError(null);
      return;
    }
    refresh();
  }, [conversationHistoryId, refresh]);

  /**
   * Optimistically adds a note to the list, then confirms with the server.
   * If the server call fails, the temporary entry is removed and the error
   * is re-thrown so the caller can show a toast.
   */
  const addNote = useCallback(
    async (content: string) => {
      if (!conversationHistoryId) return;

      const tempId = `temp-${Date.now()}`;
      const optimistic: OptimisticNote = {
        id: tempId,
        author_name: "Vos",
        content,
        created_at: new Date().toISOString(),
        can_delete: true,
        _optimistic: true,
      };

      // Optimistic insert — prepend (newest first)
      setData((prev) =>
        prev ? { ...prev, notes: [optimistic, ...prev.notes] } : prev,
      );

      try {
        const created = await api.createInboxNote(conversationHistoryId, content);
        // Replace the optimistic entry with the server-confirmed one
        setData((prev) =>
          prev
            ? {
                ...prev,
                notes: prev.notes.map((n) =>
                  n.id === tempId ? (created as OptimisticNote) : n,
                ),
              }
            : prev,
        );
      } catch (err) {
        // Rollback
        setData((prev) =>
          prev
            ? { ...prev, notes: prev.notes.filter((n) => n.id !== tempId) }
            : prev,
        );
        throw err;
      }
    },
    [conversationHistoryId],
  );

  /**
   * Optimistically removes a note, then confirms with the server.
   * If the server call fails, the note is restored to its previous position.
   */
  const removeNote = useCallback(async (noteId: string) => {
    let snapshot: OptimisticNote[] | null = null;

    setData((prev) => {
      if (!prev) return prev;
      snapshot = prev.notes as OptimisticNote[];
      return { ...prev, notes: prev.notes.filter((n) => n.id !== noteId) };
    });

    try {
      await api.deleteInboxNote(noteId);
    } catch (err) {
      // Rollback to snapshot
      setData((prev) =>
        prev && snapshot ? { ...prev, notes: snapshot } : prev,
      );
      throw err;
    }
  }, []);

  return { data, isLoading, error, refresh, addNote, removeNote };
}
