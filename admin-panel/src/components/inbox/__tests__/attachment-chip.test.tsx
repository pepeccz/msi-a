/**
 * RED tests for AttachmentChip component (T13).
 *
 * Spec scenarios covered:
 *   - Renders a 48×48 thumbnail via object URL
 *   - Truncates filename to 20 chars
 *   - X button calls onRemove
 *   - Object URL is revoked on unmount (memory leak prevention)
 */

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock URL.createObjectURL / revokeObjectURL since jsdom doesn't support them
const mockCreateObjectURL = jest.fn(() => "blob:http://localhost/mock-blob-url");
const mockRevokeObjectURL = jest.fn();
Object.defineProperty(global, "URL", {
  value: {
    createObjectURL: mockCreateObjectURL,
    revokeObjectURL: mockRevokeObjectURL,
  },
  writable: true,
});

// Lazy import to allow URL mock to be set up first
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AttachmentChip } = require("../attachment-chip") as {
  AttachmentChip: React.FC<{ file: File; onRemove: () => void }>;
};

function makeFile(name: string, type = "image/png", size = 100): File {
  const blob = new Blob([new Uint8Array(size)], { type });
  return new File([blob], name, { type });
}

describe("AttachmentChip", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders an img element with object URL as src", () => {
    const file = makeFile("photo.png");
    const onRemove = jest.fn();
    render(<AttachmentChip file={file} onRemove={onRemove} />);

    expect(mockCreateObjectURL).toHaveBeenCalledWith(file);
    const img = screen.getByRole("img");
    expect(img).toBeInTheDocument();
  });

  it("renders alt text with truncated filename (≤ 20 chars)", () => {
    const longName = "a_very_long_filename_that_exceeds_20.png";
    const file = makeFile(longName);
    render(<AttachmentChip file={file} onRemove={jest.fn()} />);

    const img = screen.getByRole("img");
    // alt should be truncated
    expect(img.getAttribute("alt")!.length).toBeLessThanOrEqual(20);
    expect(img.getAttribute("alt")).toContain("...");
  });

  it("short filename is not truncated", () => {
    const file = makeFile("short.png");
    render(<AttachmentChip file={file} onRemove={jest.fn()} />);
    const img = screen.getByRole("img");
    expect(img.getAttribute("alt")).toBe("short.png");
  });

  it("calls onRemove when X button is clicked", () => {
    const file = makeFile("photo.png");
    const onRemove = jest.fn();
    render(<AttachmentChip file={file} onRemove={onRemove} />);

    const removeBtn = screen.getByRole("button", { name: /quitar/i });
    fireEvent.click(removeBtn);
    expect(onRemove).toHaveBeenCalledTimes(1);
  });

  it("revokes object URL on unmount", () => {
    const file = makeFile("photo.png");
    const { unmount } = render(<AttachmentChip file={file} onRemove={jest.fn()} />);

    expect(mockRevokeObjectURL).not.toHaveBeenCalled();
    unmount();
    expect(mockRevokeObjectURL).toHaveBeenCalledWith("blob:http://localhost/mock-blob-url");
  });

  it("has aria-label on remove button referencing filename", () => {
    const file = makeFile("test.jpg");
    render(<AttachmentChip file={file} onRemove={jest.fn()} />);

    const btn = screen.getByRole("button");
    expect(btn.getAttribute("aria-label")).toContain("test.jpg");
  });
});
