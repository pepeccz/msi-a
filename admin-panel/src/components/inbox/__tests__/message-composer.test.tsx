/**
 * RED tests for MessageComposer extended with paperclip / paste / drag (T13).
 *
 * Spec Cap 8 scenarios:
 *   1. Paperclip button opens hidden file input (accept=image/*, multiple)
 *   2. Drag image onto composer wrapper → preview chip appears
 *   3. Paste image from clipboard → preview chip appears
 *   4. X on chip → chip removed
 *   5. Max 10 chips enforced → 11th triggers sileo.warning
 *   6. Send with chips → calls api.uploadConversationAttachments, clears chips on success
 *   7. Send failure → chips retained, sileo.error called
 *   8. Send disabled when no chips AND no text
 *
 * Tests mock: api, sileo, useWindowStatus hook.
 */

import React from "react";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";

// ── Mocks ──────────────────────────────────────────────────────────────────

jest.mock("sileo", () => ({
  sileo: {
    success: jest.fn(),
    error: jest.fn(),
    warning: jest.fn(),
  },
}));

jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: {
    sendMessage: jest.fn(),
    sendTemplate: jest.fn(),
    uploadConversationAttachments: jest.fn(),
    getWindowStatus: jest.fn(),
  },
}));

jest.mock("@/hooks/use-inbox", () => ({
  useWindowStatus: jest.fn(() => ({
    data: { within_24h: true, seconds_remaining: 3600, expires_at: null, last_inbound_at: null },
    isLoading: false,
    error: null,
  })),
}));

// Mock child components that are not under test here
jest.mock("../takeover-modal", () => ({
  TakeoverModal: ({ open }: { open: boolean }) =>
    open ? <div data-testid="takeover-modal" /> : null,
}));

jest.mock("../template-selector", () => ({
  TemplateSelector: ({ open }: { open: boolean }) =>
    open ? <div data-testid="template-selector" /> : null,
}));

jest.mock("../attachment-chip", () => ({
  AttachmentChip: ({
    file,
    onRemove,
  }: {
    file: File;
    onRemove: () => void;
  }) => (
    <div data-testid="attachment-chip" data-filename={file.name}>
      <button onClick={onRemove} aria-label={`Quitar ${file.name}`}>
        X
      </button>
    </div>
  ),
}));

// Mock URL.createObjectURL
Object.defineProperty(global, "URL", {
  value: { createObjectURL: jest.fn(() => "blob:url"), revokeObjectURL: jest.fn() },
  writable: true,
});

// ── Imports ────────────────────────────────────────────────────────────────

import api from "@/lib/api";
import { sileo } from "sileo";
import { MessageComposer } from "../message-composer";

// ── Helpers ────────────────────────────────────────────────────────────────

function makeImageFile(name = "test.png", type = "image/png"): File {
  return new File([new Uint8Array(10)], name, { type });
}

function makeDataTransfer(files: File[]): Partial<DataTransfer> {
  return {
    files: files as unknown as FileList,
    items: files.map((f) => ({
      kind: "file",
      type: f.type,
      getAsFile: () => f,
    })) as unknown as DataTransferItemList,
  };
}

const defaultProps = {
  conversationHistoryId: "conv-123",
  botStatus: "paused" as const,
  onMessageSent: jest.fn(),
};

function renderComposer(props = {}) {
  return render(<MessageComposer {...defaultProps} {...props} />);
}

// ── Tests ──────────────────────────────────────────────────────────────────

describe("MessageComposer — paperclip + paste + drag (T13)", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // 1. Paperclip button opens hidden file input
  it("paperclip button triggers hidden file input click", () => {
    renderComposer();
    const fileInput = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    expect(fileInput).toBeTruthy();
    expect(fileInput.accept).toBe("image/*");
    expect(fileInput.multiple).toBe(true);

    const clickSpy = jest.spyOn(fileInput, "click");
    const paperclipBtn = screen.getByRole("button", { name: /adjuntar/i });
    fireEvent.click(paperclipBtn);
    expect(clickSpy).toHaveBeenCalledTimes(1);
  });

  // 2. Adding a file via file input → chip appears
  it("selecting a file via file input shows an attachment chip", () => {
    renderComposer();
    const fileInput = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;

    const file = makeImageFile("photo.png");
    Object.defineProperty(fileInput, "files", {
      value: [file],
      configurable: true,
    });
    fireEvent.change(fileInput);

    expect(screen.getByTestId("attachment-chip")).toBeInTheDocument();
    expect(screen.getByTestId("attachment-chip").dataset.filename).toBe("photo.png");
  });

  // 3. Paste image → chip appears
  it("pasting an image file creates an attachment chip", () => {
    renderComposer();
    const textarea = screen.getByRole("textbox");
    const file = makeImageFile("pasted.png");

    fireEvent.paste(textarea, {
      clipboardData: {
        items: [{ kind: "file", type: "image/png", getAsFile: () => file }],
      },
    });

    expect(screen.getByTestId("attachment-chip")).toBeInTheDocument();
  });

  // Pasting non-image → no chip
  it("pasting a non-image item does not create a chip", () => {
    renderComposer();
    const textarea = screen.getByRole("textbox");

    fireEvent.paste(textarea, {
      clipboardData: {
        items: [{ kind: "string", type: "text/plain", getAsFile: () => null }],
      },
    });

    expect(screen.queryByTestId("attachment-chip")).not.toBeInTheDocument();
  });

  // 4. Drag image → chip appears
  it("dropping an image onto composer wrapper shows attachment chip", () => {
    const { container } = renderComposer();
    const file = makeImageFile("dragged.png");
    const wrapper = container.firstChild as HTMLElement;

    fireEvent.dragOver(wrapper, {
      dataTransfer: makeDataTransfer([file]),
    });
    fireEvent.drop(wrapper, {
      dataTransfer: makeDataTransfer([file]),
    });

    expect(screen.getByTestId("attachment-chip")).toBeInTheDocument();
  });

  // 5. X on chip → chip removed
  it("clicking X on a chip removes it", () => {
    renderComposer();
    const fileInput = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const file = makeImageFile("remove-me.png");
    Object.defineProperty(fileInput, "files", {
      value: [file],
      configurable: true,
    });
    fireEvent.change(fileInput);

    expect(screen.getByTestId("attachment-chip")).toBeInTheDocument();
    const removeBtn = screen.getByRole("button", { name: /quitar remove-me.png/i });
    fireEvent.click(removeBtn);
    expect(screen.queryByTestId("attachment-chip")).not.toBeInTheDocument();
  });

  // 6. Max 10 chips enforced
  it("adding an 11th image triggers sileo.warning and does not add the chip", () => {
    renderComposer();
    const fileInput = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;

    // Add 10 files
    const files10 = Array.from({ length: 10 }, (_, i) =>
      makeImageFile(`img${i}.png`),
    );
    Object.defineProperty(fileInput, "files", {
      value: files10,
      configurable: true,
    });
    fireEvent.change(fileInput);
    expect(screen.getAllByTestId("attachment-chip")).toHaveLength(10);

    // Try to add one more
    const extra = makeImageFile("extra.png");
    Object.defineProperty(fileInput, "files", {
      value: [extra],
      configurable: true,
    });
    fireEvent.change(fileInput);

    expect(screen.getAllByTestId("attachment-chip")).toHaveLength(10);
    expect(sileo.warning).toHaveBeenCalledWith(
      expect.objectContaining({ title: expect.stringContaining("10") }),
    );
  });

  // 7. Send with chips → uploadConversationAttachments called, chips cleared
  it("sending with chips calls uploadConversationAttachments and clears chips on success", async () => {
    (api.uploadConversationAttachments as jest.Mock).mockResolvedValue({
      message: {},
      attachments: [],
    });

    renderComposer();
    const fileInput = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const file = makeImageFile("send-me.png");
    Object.defineProperty(fileInput, "files", {
      value: [file],
      configurable: true,
    });
    fireEvent.change(fileInput);
    expect(screen.getByTestId("attachment-chip")).toBeInTheDocument();

    const sendBtn = screen.getByRole("button", { name: /enviar/i });
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(api.uploadConversationAttachments).toHaveBeenCalledWith(
        "conv-123",
        [file],
        undefined,
      );
    });

    await waitFor(() => {
      expect(screen.queryByTestId("attachment-chip")).not.toBeInTheDocument();
    });
  });

  // 8. Send failure → chips retained, sileo.error called
  it("upload failure retains chips and calls sileo.error", async () => {
    (api.uploadConversationAttachments as jest.Mock).mockRejectedValue(
      new Error("Server error"),
    );

    renderComposer();
    const fileInput = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const file = makeImageFile("retained.png");
    Object.defineProperty(fileInput, "files", {
      value: [file],
      configurable: true,
    });
    fireEvent.change(fileInput);

    const sendBtn = screen.getByRole("button", { name: /enviar/i });
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(sileo.error).toHaveBeenCalled();
    });

    // Chip should still be present
    expect(screen.getByTestId("attachment-chip")).toBeInTheDocument();
  });

  // 9. Send disabled when no chips AND no text
  it("send button is disabled when no chips and no text", () => {
    renderComposer();
    const sendBtn = screen.getByRole("button", { name: /enviar/i });
    expect(sendBtn).toBeDisabled();
  });

  // Send button enabled when there is text
  it("send button is enabled when there is text but no chips", () => {
    renderComposer();
    const textarea = screen.getByRole("textbox");
    fireEvent.change(textarea, { target: { value: "hola" } });
    const sendBtn = screen.getByRole("button", { name: /enviar/i });
    expect(sendBtn).not.toBeDisabled();
  });

  // Send button enabled when there are chips but no text
  it("send button is enabled when there are chips but no text", () => {
    renderComposer();
    const fileInput = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const file = makeImageFile("chip.png");
    Object.defineProperty(fileInput, "files", {
      value: [file],
      configurable: true,
    });
    fireEvent.change(fileInput);

    const sendBtn = screen.getByRole("button", { name: /enviar/i });
    expect(sendBtn).not.toBeDisabled();
  });
});
