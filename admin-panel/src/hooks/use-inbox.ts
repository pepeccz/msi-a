"use client";

/**
 * Hooks for the unified inbox feature (PR5 — T27).
 *
 * No SWR in the project — uses useState + useEffect + setInterval pattern
 * consistent with the rest of the admin panel.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import api from "@/lib/api";
import type {
  InboxParams,
  InboxListResponse,
  MessagesPageResponse,
  ConversationMessageResponse,
  WindowStatusResponse,
  TemplateResponse,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// useInbox — list of conversations with polling
// ---------------------------------------------------------------------------

export interface UseInboxResult {
  data: InboxListResponse | null;
  isLoading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useInbox(
  params: InboxParams = {},
  refreshIntervalMs = 10_000,
): UseInboxResult {
  const [data, setData] = useState<InboxListResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Serialize params to a stable key so the effect re-runs when they change
  const paramsKey = JSON.stringify(params);

  const fetch = useCallback(async () => {
    try {
      const result = await api.getInbox(params);
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar bandeja");
    } finally {
      setIsLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paramsKey]);

  useEffect(() => {
    setIsLoading(true);
    fetch();
    const interval = setInterval(fetch, refreshIntervalMs);
    return () => clearInterval(interval);
  }, [fetch, refreshIntervalMs]);

  return { data, isLoading, error, refresh: fetch };
}

// ---------------------------------------------------------------------------
// useConversation — thread messages with cursor-based load-more + polling
// ---------------------------------------------------------------------------

export interface UseConversationResult {
  messages: ConversationMessageResponse[];
  isLoading: boolean;
  isLoadingMore: boolean;
  error: string | null;
  hasMore: boolean;
  loadMore: () => Promise<void>;
  refresh: () => void;
}

export function useConversation(
  conversationHistoryId: string | null,
  refreshIntervalMs = 5_000,
): UseConversationResult {
  const [messages, setMessages] = useState<ConversationMessageResponse[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  // Track the oldest cursor for load-more (messages sorted newest-first from backend)
  const oldestCursorRef = useRef<string | null>(null);

  const fetchInitial = useCallback(async () => {
    if (!conversationHistoryId) return;
    setIsLoading(true);
    setError(null);
    try {
      const page = await api.getThread(conversationHistoryId, undefined, 50);
      setMessages(page.messages);
      setNextCursor(page.next_cursor);
      if (page.messages.length > 0) {
        oldestCursorRef.current = page.messages[0].id;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar mensajes");
    } finally {
      setIsLoading(false);
    }
  }, [conversationHistoryId]);

  // Polling: append only genuinely new messages (by id) at the bottom
  const pollForNew = useCallback(async () => {
    if (!conversationHistoryId) return;
    try {
      // Always fetch the first page to get newest messages
      const page = await api.getThread(conversationHistoryId, undefined, 50);
      setMessages((prev) => {
        const existingIds = new Set(prev.map((m) => m.id));
        const newOnes = page.messages.filter((m) => !existingIds.has(m.id));
        if (newOnes.length === 0) return prev;
        return [...prev, ...newOnes];
      });
    } catch {
      // Silently ignore polling errors to not disrupt the UI
    }
  }, [conversationHistoryId]);

  // Load older messages (scroll up)
  const loadMore = useCallback(async () => {
    if (!conversationHistoryId || !oldestCursorRef.current) return;
    setIsLoadingMore(true);
    try {
      const page = await api.getThread(
        conversationHistoryId,
        oldestCursorRef.current,
        50,
      );
      if (page.messages.length > 0) {
        setMessages((prev) => [...page.messages, ...prev]);
        oldestCursorRef.current = page.messages[0].id;
      }
      setNextCursor(page.next_cursor);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Error al cargar más mensajes",
      );
    } finally {
      setIsLoadingMore(false);
    }
  }, [conversationHistoryId]);

  useEffect(() => {
    if (!conversationHistoryId) {
      setMessages([]);
      setNextCursor(null);
      oldestCursorRef.current = null;
      return;
    }
    fetchInitial();
  }, [conversationHistoryId, fetchInitial]);

  // Poll for new messages after initial load
  useEffect(() => {
    if (!conversationHistoryId) return;
    const interval = setInterval(pollForNew, refreshIntervalMs);
    return () => clearInterval(interval);
  }, [conversationHistoryId, pollForNew, refreshIntervalMs]);

  return {
    messages,
    isLoading,
    isLoadingMore,
    error,
    hasMore: nextCursor !== null,
    loadMore,
    refresh: fetchInitial,
  };
}

// ---------------------------------------------------------------------------
// useWindowStatus — 24h window check with polling
// ---------------------------------------------------------------------------

export interface UseWindowStatusResult {
  data: WindowStatusResponse | null;
  isLoading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useWindowStatus(
  conversationHistoryId: string | null,
  refreshIntervalMs = 30_000,
): UseWindowStatusResult {
  const [data, setData] = useState<WindowStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    if (!conversationHistoryId) return;
    setIsLoading(true);
    try {
      const result = await api.getWindowStatus(conversationHistoryId);
      setData(result);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Error al verificar ventana",
      );
    } finally {
      setIsLoading(false);
    }
  }, [conversationHistoryId]);

  useEffect(() => {
    if (!conversationHistoryId) {
      setData(null);
      return;
    }
    fetch();
    const interval = setInterval(fetch, refreshIntervalMs);
    return () => clearInterval(interval);
  }, [conversationHistoryId, fetch, refreshIntervalMs]);

  return { data, isLoading, error, refresh: fetch };
}

// ---------------------------------------------------------------------------
// useTemplates — list of WhatsApp templates (no polling needed)
// ---------------------------------------------------------------------------

export interface UseTemplatesResult {
  templates: TemplateResponse[];
  isLoading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useTemplates(): UseTemplatesResult {
  const [templates, setTemplates] = useState<TemplateResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setIsLoading(true);
    try {
      const result = await api.getTemplates();
      setTemplates(result);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Error al cargar plantillas",
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { templates, isLoading, error, refresh: fetch };
}
