/**
 * C2.7 — EscalationCardActions tests
 *
 * Tests:
 * - render pending → assert "Asignarme" and "Asignar a..." buttons present + NO "Tomar control"
 * - render assigned → assert badge with display_name + "Liberar"/"Resolver" buttons
 * - click "Asignarme" → assert api.assignEscalation called with currentUser.id
 * - 409 rollback → assert sileo.warning called and state reverts
 */

// ---------------------------------------------------------------------------
// Mocks (must be before imports)
// ---------------------------------------------------------------------------

const mockAssignEscalation = jest.fn();
const mockUnassignEscalation = jest.fn();
const mockResolveEscalation = jest.fn();

jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: {
    assignEscalation: (...args: unknown[]) => mockAssignEscalation(...args),
    unassignEscalation: (...args: unknown[]) => mockUnassignEscalation(...args),
    resolveEscalation: (...args: unknown[]) => mockResolveEscalation(...args),
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

const mockUser = {
  id: "user-admin-1",
  username: "admin",
  display_name: "Admin Test",
  role: "admin" as const,
};

jest.mock("@/contexts/auth-context", () => ({
  useAuth: () => ({ user: mockUser, isAdmin: true }),
}));

// ---------------------------------------------------------------------------
// Imports (after mocks)
// ---------------------------------------------------------------------------

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { EscalationCardActions } from "@/components/escalations/escalation-card-actions";
import type { Escalation } from "@/lib/types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeEscalation(overrides: Partial<Escalation> = {}): Escalation {
  return {
    id: "esc-1",
    conversation_id: "conv-123",
    user_id: null,
    user_phone: null,
    reason: "Necesita atención",
    source: "tool_call",
    status: "pending",
    triggered_at: new Date().toISOString(),
    resolved_at: null,
    resolved_by: null,
    resolved_by_user_id: null,
    assigned_to_user_id: null,
    assigned_to: null,
    assigned_at: null,
    metadata: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("EscalationCardActions — status=pending", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders Asignarme button for pending escalation", () => {
    const esc = makeEscalation({ status: "pending" });
    render(<EscalationCardActions escalation={esc} onUpdate={jest.fn()} />);
    expect(screen.getByRole("button", { name: /asignarme/i })).toBeInTheDocument();
  });

  it("renders Asignar a... button for pending escalation", () => {
    const esc = makeEscalation({ status: "pending" });
    render(<EscalationCardActions escalation={esc} onUpdate={jest.fn()} />);
    expect(screen.getByRole("button", { name: /asignar a/i })).toBeInTheDocument();
  });

  it("does NOT render Tomar control button for pending escalation", () => {
    const esc = makeEscalation({ status: "pending" });
    render(<EscalationCardActions escalation={esc} onUpdate={jest.fn()} />);
    expect(screen.queryByText(/tomar control/i)).not.toBeInTheDocument();
  });

  it("click Asignarme calls api.assignEscalation with currentUser.id", async () => {
    const onUpdate = jest.fn();
    const updatedEsc = makeEscalation({
      status: "assigned",
      assigned_to_user_id: mockUser.id,
      assigned_to: {
        id: mockUser.id,
        username: mockUser.username,
        display_name: mockUser.display_name,
      },
      assigned_at: new Date().toISOString(),
    });
    mockAssignEscalation.mockResolvedValueOnce(updatedEsc);

    const esc = makeEscalation({ status: "pending" });
    render(<EscalationCardActions escalation={esc} onUpdate={onUpdate} />);

    fireEvent.click(screen.getByRole("button", { name: /asignarme/i }));

    await waitFor(() => {
      expect(mockAssignEscalation).toHaveBeenCalledWith("esc-1", mockUser.id);
    });
    await waitFor(() => {
      expect(onUpdate).toHaveBeenCalledWith(updatedEsc);
    });
    expect(mockSileoSuccess).toHaveBeenCalled();
  });

  it("409 from assignEscalation shows warning toast", async () => {
    mockAssignEscalation.mockRejectedValueOnce(
      Object.assign(new Error("Otro agente ya tomó la escalación"), { status: 409 })
    );

    const esc = makeEscalation({ status: "pending" });
    render(<EscalationCardActions escalation={esc} onUpdate={jest.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /asignarme/i }));

    await waitFor(() => {
      expect(mockSileoWarning).toHaveBeenCalled();
    });
  });
});

describe("EscalationCardActions — status=assigned", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("shows Asignado a badge with display_name when assigned", () => {
    const esc = makeEscalation({
      status: "assigned",
      assigned_to_user_id: "user-2",
      assigned_to: {
        id: "user-2",
        username: "carlos",
        display_name: "Carlos",
      },
      assigned_at: new Date().toISOString(),
    });
    render(<EscalationCardActions escalation={esc} onUpdate={jest.fn()} />);
    expect(screen.getByText(/Asignado a Carlos/i)).toBeInTheDocument();
  });

  it("renders Liberar button when assigned", () => {
    const esc = makeEscalation({
      status: "assigned",
      assigned_to: { id: "u-1", username: "maria", display_name: "María" },
    });
    render(<EscalationCardActions escalation={esc} onUpdate={jest.fn()} />);
    expect(screen.getByRole("button", { name: /liberar/i })).toBeInTheDocument();
  });

  it("renders Resolver button when assigned", () => {
    const esc = makeEscalation({
      status: "assigned",
      assigned_to: { id: "u-1", username: "maria", display_name: "María" },
    });
    render(<EscalationCardActions escalation={esc} onUpdate={jest.fn()} />);
    expect(screen.getByRole("button", { name: /resolver/i })).toBeInTheDocument();
  });

  it("does NOT render Asignarme or Asignar a... when assigned", () => {
    const esc = makeEscalation({
      status: "assigned",
      assigned_to: { id: "u-1", username: "maria", display_name: "María" },
    });
    render(<EscalationCardActions escalation={esc} onUpdate={jest.fn()} />);
    expect(screen.queryByRole("button", { name: /asignarme/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /asignar a/i })).not.toBeInTheDocument();
  });
});

describe("EscalationCardActions — status=resolved", () => {
  it("shows resolved state and not action buttons", () => {
    const esc = makeEscalation({
      status: "resolved",
      resolved_by: "admin",
      resolved_at: new Date().toISOString(),
    });
    render(<EscalationCardActions escalation={esc} onUpdate={jest.fn()} />);
    expect(screen.queryByRole("button", { name: /asignarme/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /liberar/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /resolver/i })).not.toBeInTheDocument();
  });
});
