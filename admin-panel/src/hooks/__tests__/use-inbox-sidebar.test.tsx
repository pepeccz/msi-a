/**
 * Tests for useInboxSidebar hook.
 *
 * Coverage:
 * - Optimistic note add: note appears immediately, replaced by server response on success
 * - Add error: optimistic note removed after error, error re-thrown
 * - Optimistic note delete: note disappears immediately
 * - Delete error: note reappears after error, error re-thrown
 * - Refetch triggered on conversationHistoryId change
 *
 * Tests are written only — execution happens on the testing server.
 */

import { renderHook, act, waitFor } from "@testing-library/react";
import { useInboxSidebar } from "../use-inbox-sidebar";
import type { InboxSidebarResponse, InboxNote } from "@/lib/types";

// ---------------------------------------------------------------------------
// Mock api module
// ---------------------------------------------------------------------------

const mockGetInboxSidebar = jest.fn();
const mockCreateInboxNote = jest.fn();
const mockDeleteInboxNote = jest.fn();

jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: {
    getInboxSidebar: (...args: unknown[]) => mockGetInboxSidebar(...args),
    createInboxNote: (...args: unknown[]) => mockCreateInboxNote(...args),
    deleteInboxNote: (...args: unknown[]) => mockDeleteInboxNote(...args),
  },
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const NOTE_1: InboxNote = {
  id: "note-1",
  author_name: "Admin A",
  content: "Primera nota",
  created_at: "2026-05-01T10:00:00Z",
  can_delete: true,
};

const NOTE_2: InboxNote = {
  id: "note-2",
  author_name: "Admin B",
  content: "Segunda nota",
  created_at: "2026-05-02T10:00:00Z",
  can_delete: false,
};

const SIDEBAR_RESPONSE: InboxSidebarResponse = {
  client: {
    user_id: "user-1",
    name: "Cliente Test",
    phone: "+34600000001",
    created_at: "2025-01-01T00:00:00Z",
    cases_count: 3,
    billed_total_eur: 450.0,
    last_activity_at: "2026-04-30T08:00:00Z",
  },
  active_case: null,
  notes: [NOTE_1, NOTE_2],
};

const CREATED_NOTE: InboxNote = {
  id: "note-server-new",
  author_name: "Vos",
  content: "Nota nueva",
  created_at: "2026-05-12T12:00:00Z",
  can_delete: true,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

beforeEach(() => {
  jest.clearAllMocks();
  mockGetInboxSidebar.mockResolvedValue(SIDEBAR_RESPONSE);
});

describe("useInboxSidebar — initial fetch", () => {
  it("fetches sidebar on mount when conversationHistoryId is provided", async () => {
    const { result } = renderHook(() => useInboxSidebar("conv-1"));

    expect(result.current.isLoading).toBe(true);

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(mockGetInboxSidebar).toHaveBeenCalledWith("conv-1");
    expect(result.current.data).toEqual(SIDEBAR_RESPONSE);
    expect(result.current.error).toBeNull();
  });

  it("does not fetch when conversationHistoryId is null", () => {
    renderHook(() => useInboxSidebar(null));
    expect(mockGetInboxSidebar).not.toHaveBeenCalled();
  });

  it("refetches when conversationHistoryId changes", async () => {
    const { result, rerender } = renderHook(
      ({ id }: { id: string | null }) => useInboxSidebar(id),
      { initialProps: { id: "conv-1" } },
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mockGetInboxSidebar).toHaveBeenCalledTimes(1);
    expect(mockGetInboxSidebar).toHaveBeenCalledWith("conv-1");

    const SIDEBAR_2: InboxSidebarResponse = { ...SIDEBAR_RESPONSE, notes: [] };
    mockGetInboxSidebar.mockResolvedValueOnce(SIDEBAR_2);

    rerender({ id: "conv-2" });

    await waitFor(() =>
      expect(mockGetInboxSidebar).toHaveBeenCalledWith("conv-2"),
    );
    await waitFor(() => expect(result.current.data).toEqual(SIDEBAR_2));
  });

  it("clears data when conversationHistoryId becomes null", async () => {
    const { result, rerender } = renderHook(
      ({ id }: { id: string | null }) => useInboxSidebar(id),
      { initialProps: { id: "conv-1" } },
    );

    await waitFor(() => expect(result.current.data).toEqual(SIDEBAR_RESPONSE));

    rerender({ id: null });

    expect(result.current.data).toBeNull();
  });
});

describe("useInboxSidebar — addNote (optimistic)", () => {
  it("shows the note immediately before the server responds", async () => {
    let resolveCreate!: (note: InboxNote) => void;
    mockCreateInboxNote.mockReturnValueOnce(
      new Promise<InboxNote>((res) => {
        resolveCreate = res;
      }),
    );

    const { result } = renderHook(() => useInboxSidebar("conv-1"));
    await waitFor(() => expect(result.current.data).toBeTruthy());

    // Start addNote — do not await
    act(() => {
      result.current.addNote("Nota nueva");
    });

    // Optimistic entry should appear immediately
    await waitFor(() =>
      expect(result.current.data?.notes.some((n) => n.content === "Nota nueva")).toBe(true),
    );

    const optimisticNote = result.current.data?.notes.find(
      (n) => n.content === "Nota nueva",
    );
    expect(optimisticNote?.id).toMatch(/^temp-/);

    // Resolve the server call
    await act(async () => {
      resolveCreate(CREATED_NOTE);
    });

    // The temp entry should now be replaced by the server-confirmed note
    await waitFor(() =>
      expect(result.current.data?.notes.some((n) => n.id === "note-server-new")).toBe(true),
    );
    expect(result.current.data?.notes.some((n) => n.id.startsWith("temp-"))).toBe(false);
  });

  it("removes the optimistic note on server error and re-throws", async () => {
    mockCreateInboxNote.mockRejectedValueOnce(new Error("Server error"));

    const { result } = renderHook(() => useInboxSidebar("conv-1"));
    await waitFor(() => expect(result.current.data).toBeTruthy());

    const initialNoteCount = result.current.data!.notes.length;

    await expect(
      act(async () => {
        await result.current.addNote("Nota fallida");
      }),
    ).rejects.toThrow("Server error");

    // Note count should return to initial (optimistic entry rolled back)
    expect(result.current.data?.notes.length).toBe(initialNoteCount);
    expect(result.current.data?.notes.some((n) => n.content === "Nota fallida")).toBe(false);
  });
});

describe("useInboxSidebar — removeNote (optimistic)", () => {
  it("removes the note from the list immediately", async () => {
    mockDeleteInboxNote.mockResolvedValueOnce(undefined);

    const { result } = renderHook(() => useInboxSidebar("conv-1"));
    await waitFor(() => expect(result.current.data).toBeTruthy());

    expect(result.current.data?.notes.some((n) => n.id === "note-1")).toBe(true);

    await act(async () => {
      await result.current.removeNote("note-1");
    });

    expect(result.current.data?.notes.some((n) => n.id === "note-1")).toBe(false);
    expect(result.current.data?.notes.some((n) => n.id === "note-2")).toBe(true);
  });

  it("restores the note on server error and re-throws", async () => {
    mockDeleteInboxNote.mockRejectedValueOnce(new Error("Delete failed"));

    const { result } = renderHook(() => useInboxSidebar("conv-1"));
    await waitFor(() => expect(result.current.data).toBeTruthy());

    const initialNotes = result.current.data!.notes;

    await expect(
      act(async () => {
        await result.current.removeNote("note-1");
      }),
    ).rejects.toThrow("Delete failed");

    // Snapshot restored — note-1 should be back
    expect(result.current.data?.notes.some((n) => n.id === "note-1")).toBe(true);
    expect(result.current.data?.notes.length).toBe(initialNotes.length);
  });
});
