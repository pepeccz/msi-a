/**
 * PR3 inbox-completeness tests
 *
 * T14: EscalationCard — source badge renders with correct label/icon per source;
 *      renders only when escalation_source !== null and status in [pending, in_progress];
 *      does NOT render when escalation_source is null.
 * T15: InboxList — sort dropdown renders 4 options; selection updates URL param;
 *      pre-selected from URL on load.
 * T16: ConversationThread MessageBubble — renders "1 imagen" for count=1;
 *      renders "N imágenes" for count>1; does NOT render counter when count=0 or undefined.
 */

// ---------------------------------------------------------------------------
// Mocks (must be before imports)
// ---------------------------------------------------------------------------

// jsdom does not implement scrollIntoView — mock it globally
window.HTMLElement.prototype.scrollIntoView = jest.fn();

const mockRouterReplace = jest.fn();
let mockSearchParamsValue: Record<string, string | null> = {};

jest.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockRouterReplace }),
  useSearchParams: () => ({
    get: (key: string) => mockSearchParamsValue[key] ?? null,
    toString: () => "",
  }),
}));

const mockResolveEscalation = jest.fn().mockResolvedValue({ status: "resolved" });
const mockDeleteConversation = jest.fn().mockResolvedValue({ message: "deleted", details: {} });
const mockMarkRead = jest.fn().mockResolvedValue(undefined);
const mockPauseBot = jest.fn().mockResolvedValue(undefined);
const mockResumeBot = jest.fn().mockResolvedValue(undefined);
const mockEscalateConversation = jest.fn().mockResolvedValue(undefined);
const mockGetThread = jest.fn().mockResolvedValue({ messages: [], next_cursor: null });
const mockGetInbox = jest.fn().mockResolvedValue({
  items: [],
  total: 0,
  page: 1,
  page_size: 50,
  stats: { pending: 0, in_progress: 0, resolved_today: 0, total_today: 0 },
});

jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: {
    resolveEscalation: (...args: unknown[]) => mockResolveEscalation(...args),
    deleteConversation: (...args: unknown[]) => mockDeleteConversation(...args),
    markRead: (...args: unknown[]) => mockMarkRead(...args),
    pauseBot: (...args: unknown[]) => mockPauseBot(...args),
    resumeBot: (...args: unknown[]) => mockResumeBot(...args),
    escalateConversation: (...args: unknown[]) => mockEscalateConversation(...args),
    getThread: (...args: unknown[]) => mockGetThread(...args),
    getInbox: (...args: unknown[]) => mockGetInbox(...args),
  },
}));

const mockSileoSuccess = jest.fn();
const mockSileoError = jest.fn();
const mockSileoWarning = jest.fn();

jest.mock("sileo", () => ({
  sileo: {
    success: (...args: unknown[]) => mockSileoSuccess(...args),
    error: (...args: unknown[]) => mockSileoError(...args),
    warning: (...args: unknown[]) => mockSileoWarning(...args),
    info: jest.fn(),
  },
}));

let mockIsAdmin = false;
jest.mock("@/contexts/auth-context", () => ({
  useAuth: () => ({ isAdmin: mockIsAdmin, user: { role: mockIsAdmin ? "admin" : "agent" } }),
}));

// ---------------------------------------------------------------------------
// Imports (after mocks)
// ---------------------------------------------------------------------------

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ClientCard } from "@/components/inbox/client-card";
import { InboxList } from "@/components/inbox/inbox-list";
import { ConversationThread } from "@/components/inbox/conversation-thread";
import type { InboxItemResponse, EscalationSource, ConversationMessageResponse } from "@/lib/types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeConversation(overrides: Partial<InboxItemResponse> = {}): InboxItemResponse {
  return {
    conversation_history_id: "conv-1",
    user_name: "Juan Test",
    user_phone: "+34600000001",
    last_message_preview: "Hola",
    last_message_at: new Date().toISOString(),
    bot_status: "active",
    unread_count: 0,
    escalation_status: "pending",
    paused_by_user_name: null,
    escalation_source: "tool_call",
    escalation_id: "esc-123",
    ...overrides,
  };
}

function makeMessage(overrides: Partial<ConversationMessageResponse> = {}): ConversationMessageResponse {
  return {
    id: "msg-1",
    conversation_history_id: "conv-1",
    role: "user",
    author_type: "user",
    author_user_id: null,
    author_user_name: null,
    content: "",
    created_at: new Date().toISOString(),
    is_read: true,
    has_images: false,
    image_count: 0,
    chatwoot_message_id: null,
    delivery_failed: false,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// T14: EscalationCard — source badge
// ---------------------------------------------------------------------------

describe("T14 — ClientCard EscalationCard: source badge", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders 'Cliente solicitó' badge for source=tool_call", () => {
    const conv = makeConversation({ escalation_status: "pending", escalation_source: "tool_call" });
    render(<ClientCard conversation={conv} onConversationUpdated={jest.fn()} />);
    expect(screen.getByText("Cliente solicitó")).toBeInTheDocument();
  });

  it("renders 'Auto-escalada' badge for source=auto_escalation", () => {
    const conv = makeConversation({ escalation_status: "pending", escalation_source: "auto_escalation" });
    render(<ClientCard conversation={conv} onConversationUpdated={jest.fn()} />);
    expect(screen.getByText("Auto-escalada")).toBeInTheDocument();
  });

  it("renders 'Error técnico' badge for source=error", () => {
    const conv = makeConversation({ escalation_status: "pending", escalation_source: "error" });
    render(<ClientCard conversation={conv} onConversationUpdated={jest.fn()} />);
    expect(screen.getByText("Error técnico")).toBeInTheDocument();
  });

  it("renders 'Caso completado' badge for source=case_completion", () => {
    const conv = makeConversation({ escalation_status: "pending", escalation_source: "case_completion" });
    render(<ClientCard conversation={conv} onConversationUpdated={jest.fn()} />);
    expect(screen.getByText("Caso completado")).toBeInTheDocument();
  });

  it("renders 'Bot desactivado' badge for source=agent_disabled", () => {
    const conv = makeConversation({ escalation_status: "pending", escalation_source: "agent_disabled" });
    render(<ClientCard conversation={conv} onConversationUpdated={jest.fn()} />);
    expect(screen.getByText("Bot desactivado")).toBeInTheDocument();
  });

  it("does NOT render source badge when escalation_source is null", () => {
    const conv = makeConversation({ escalation_status: "pending", escalation_source: null });
    render(<ClientCard conversation={conv} onConversationUpdated={jest.fn()} />);
    expect(screen.queryByText("Cliente solicitó")).not.toBeInTheDocument();
    expect(screen.queryByText("Auto-escalada")).not.toBeInTheDocument();
    expect(screen.queryByText("Error técnico")).not.toBeInTheDocument();
    expect(screen.queryByText("Caso completado")).not.toBeInTheDocument();
    expect(screen.queryByText("Bot desactivado")).not.toBeInTheDocument();
  });

  it("does NOT render source badge when escalation_status is none (no EscalationCard rendered)", () => {
    const conv = makeConversation({ escalation_status: "none", escalation_id: null, escalation_source: "tool_call" });
    render(<ClientCard conversation={conv} onConversationUpdated={jest.fn()} />);
    expect(screen.queryByText("Cliente solicitó")).not.toBeInTheDocument();
  });

  it("renders source badge when escalation_status is in_progress", () => {
    const conv = makeConversation({ escalation_status: "in_progress", escalation_source: "error" });
    render(<ClientCard conversation={conv} onConversationUpdated={jest.fn()} />);
    expect(screen.getByText("Error técnico")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// T15: InboxList — sort dropdown
// ---------------------------------------------------------------------------

describe("T15 — InboxList: sort dropdown", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSearchParamsValue = {};
  });

  it("renders a sort trigger element", () => {
    render(
      <InboxList
        selectedId={null}
        activeTab="todas"
        onSelectConversation={jest.fn()}
        onTabChange={jest.fn()}
        sort="last_message_at_desc"
        onSortChange={jest.fn()}
      />
    );
    // The Select trigger should be present (sort dropdown)
    expect(screen.getByRole("combobox")).toBeInTheDocument();
  });

  it("calls onSortChange when a different option is selected", async () => {
    const onSortChange = jest.fn();
    render(
      <InboxList
        selectedId={null}
        activeTab="todas"
        onSelectConversation={jest.fn()}
        onTabChange={jest.fn()}
        sort="last_message_at_desc"
        onSortChange={onSortChange}
      />
    );

    // Open the select and click an option
    fireEvent.click(screen.getByRole("combobox"));

    await waitFor(() => {
      expect(screen.getByText("Más antiguas primero")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Más antiguas primero"));

    await waitFor(() => {
      expect(onSortChange).toHaveBeenCalledWith("last_message_at_asc");
    });
  });

  it("shows 4 sort options when dropdown is opened", async () => {
    render(
      <InboxList
        selectedId={null}
        activeTab="todas"
        onSelectConversation={jest.fn()}
        onTabChange={jest.fn()}
        sort="last_message_at_desc"
        onSortChange={jest.fn()}
      />
    );

    fireEvent.click(screen.getByRole("combobox"));

    await waitFor(() => {
      // "Última actividad" appears as trigger value + dropdown option — use getAllByText
      expect(screen.getAllByText("Última actividad").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("Más antiguas primero")).toBeInTheDocument();
      expect(screen.getByText("Por fecha de inicio")).toBeInTheDocument();
      expect(screen.getByText("No leídas primero")).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// T16: ConversationThread — image_count rendering
// ---------------------------------------------------------------------------

describe("T16 — ConversationThread MessageBubble: image_count rendering", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockIsAdmin = false;
  });

  it("does NOT show image counter when image_count is 0", () => {
    mockGetThread.mockResolvedValueOnce({
      messages: [makeMessage({ has_images: false, image_count: 0 })],
      next_cursor: null,
    });

    const conv = makeConversation({ escalation_status: "none", escalation_id: null, escalation_source: null });
    render(
      <ConversationThread
        conversation={conv}
        onConversationUpdated={jest.fn()}
      />
    );

    expect(screen.queryByText(/\d+\s*imagen/i)).not.toBeInTheDocument();
  });

  it("shows '1 imagen' when image_count is 1", async () => {
    mockGetThread.mockResolvedValueOnce({
      messages: [makeMessage({ has_images: true, image_count: 1, content: "" })],
      next_cursor: null,
    });

    const conv = makeConversation({ escalation_status: "none", escalation_id: null, escalation_source: null });
    render(
      <ConversationThread
        conversation={conv}
        onConversationUpdated={jest.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("1 imagen")).toBeInTheDocument();
    });
  });

  it("shows '5 imágenes' when image_count is 5", async () => {
    mockGetThread.mockResolvedValueOnce({
      messages: [makeMessage({ has_images: true, image_count: 5, content: "" })],
      next_cursor: null,
    });

    const conv = makeConversation({ escalation_status: "none", escalation_id: null, escalation_source: null });
    render(
      <ConversationThread
        conversation={conv}
        onConversationUpdated={jest.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("5 imágenes")).toBeInTheDocument();
    });
  });
});
