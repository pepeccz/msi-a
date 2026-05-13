/**
 * C2.7 — AssignToDialog tests
 *
 * Tests:
 * - render → listActiveAdminUsers is called on open
 * - only active admins listed (is_active=true filter passed)
 * - submit calls assignEscalation with selected id
 */

// ---------------------------------------------------------------------------
// Mocks (must be before imports)
// ---------------------------------------------------------------------------

const mockAssignEscalation = jest.fn();
const mockGetAdminUsers = jest.fn();

jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: {
    assignEscalation: (...args: unknown[]) => mockAssignEscalation(...args),
    getAdminUsers: (...args: unknown[]) => mockGetAdminUsers(...args),
  },
}));

const mockSileoSuccess = jest.fn();
const mockSileoError = jest.fn();

jest.mock("sileo", () => ({
  sileo: {
    success: (...args: unknown[]) => mockSileoSuccess(...args),
    error: (...args: unknown[]) => mockSileoError(...args),
    warning: jest.fn(),
    info: jest.fn(),
  },
}));

// ---------------------------------------------------------------------------
// Imports (after mocks)
// ---------------------------------------------------------------------------

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AssignToDialog } from "@/components/escalations/assign-to-dialog";
import type { AdminUser, Escalation } from "@/lib/types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeAdmin(overrides: Partial<AdminUser> = {}): AdminUser {
  return {
    id: "admin-1",
    username: "admin",
    display_name: "Admin Uno",
    role: "admin",
    is_active: true,
    email: null,
    chatwoot_agent_id: null,
    chatwoot_user_id: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    created_by: null,
    ...overrides,
  };
}

function makeEscalation(overrides: Partial<Escalation> = {}): Escalation {
  return {
    id: "esc-1",
    conversation_id: "conv-123",
    user_id: null,
    user_phone: null,
    reason: "Test",
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

describe("AssignToDialog", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("calls getAdminUsers with is_active=true when dialog opens", async () => {
    mockGetAdminUsers.mockResolvedValueOnce({
      items: [makeAdmin()],
      total: 1,
      has_more: false,
    });

    const esc = makeEscalation();
    render(
      <AssignToDialog
        escalationId={esc.id}
        onAssigned={jest.fn()}
        trigger={<button>Asignar a...</button>}
      />
    );

    // Open dialog
    fireEvent.click(screen.getByText("Asignar a..."));

    await waitFor(() => {
      expect(mockGetAdminUsers).toHaveBeenCalledWith(
        expect.objectContaining({ is_active: true })
      );
    });
  });

  it("lists active admins from the API response", async () => {
    const admin1 = makeAdmin({ id: "a-1", display_name: "Carlos López" });
    const admin2 = makeAdmin({ id: "a-2", display_name: "María García" });

    mockGetAdminUsers.mockResolvedValueOnce({
      items: [admin1, admin2],
      total: 2,
      has_more: false,
    });

    const esc = makeEscalation();
    render(
      <AssignToDialog
        escalationId={esc.id}
        onAssigned={jest.fn()}
        trigger={<button>Asignar a...</button>}
      />
    );

    fireEvent.click(screen.getByText("Asignar a..."));

    await waitFor(() => {
      expect(screen.getByText("Carlos López")).toBeInTheDocument();
      expect(screen.getByText("María García")).toBeInTheDocument();
    });
  });

  it("calls assignEscalation with selected admin id on confirm", async () => {
    const admin1 = makeAdmin({ id: "a-1", display_name: "Carlos" });
    const updatedEsc = makeEscalation({
      status: "assigned",
      assigned_to_user_id: "a-1",
      assigned_to: { id: "a-1", username: "carlos", display_name: "Carlos" },
    });

    mockGetAdminUsers.mockResolvedValueOnce({
      items: [admin1],
      total: 1,
      has_more: false,
    });
    mockAssignEscalation.mockResolvedValueOnce(updatedEsc);

    const onAssigned = jest.fn();
    render(
      <AssignToDialog
        escalationId="esc-1"
        onAssigned={onAssigned}
        trigger={<button>Asignar a...</button>}
      />
    );

    fireEvent.click(screen.getByText("Asignar a..."));

    // Wait for admins to load and click one
    await waitFor(() => {
      expect(screen.getByText("Carlos")).toBeInTheDocument();
    });

    // Click the admin option to select
    fireEvent.click(screen.getByText("Carlos"));

    // Click confirm
    const confirmButton = screen.getByRole("button", { name: /asignar/i });
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(mockAssignEscalation).toHaveBeenCalledWith("esc-1", "a-1");
    });
    await waitFor(() => {
      expect(onAssigned).toHaveBeenCalledWith(updatedEsc);
    });
  });
});
