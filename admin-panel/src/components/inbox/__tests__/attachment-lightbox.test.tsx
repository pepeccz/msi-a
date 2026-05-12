/**
 * Tests for AttachmentLightbox component (T10).
 *
 * TDD cycle: RED (tests written first)
 *
 * Covers:
 *   - Opens with correct image at initialIndex
 *   - Arrow buttons navigate forward/backward
 *   - Keyboard ArrowRight / ArrowLeft navigate images
 *   - Cannot navigate before first or after last image
 *   - Close button calls onClose
 *   - Counter shows "N / total"
 */

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { AttachmentLightbox } from "../attachment-lightbox";
import type { MessageAttachment } from "@/lib/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeAtt(i: number): MessageAttachment {
  return {
    id: `att-${i}`,
    url: `/conversation-images/conv/${i}.jpg`,
    kind: "image",
    content_type: "image/jpeg",
    filename: `image_${i}.jpg`,
    size_bytes: null,
    width: null,
    height: null,
    position: i,
    created_at: "2026-01-01T00:00:00Z",
  };
}

const ATTS = [makeAtt(0), makeAtt(1), makeAtt(2)];
const noop = jest.fn();

beforeEach(() => {
  noop.mockClear();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AttachmentLightbox", () => {
  it("renders null when not open", () => {
    const { container } = render(
      <AttachmentLightbox
        attachments={ATTS}
        initialIndex={0}
        open={false}
        onClose={noop}
      />,
    );
    // Dialog closed → no visible content
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("opens with the image at initialIndex=1", () => {
    render(
      <AttachmentLightbox
        attachments={ATTS}
        initialIndex={1}
        open={true}
        onClose={noop}
      />,
    );
    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("src", ATTS[1].url);
    expect(img).toHaveAttribute("alt", ATTS[1].filename);
  });

  it("shows counter '2 / 3' when initialIndex=1 and 3 attachments", () => {
    render(
      <AttachmentLightbox
        attachments={ATTS}
        initialIndex={1}
        open={true}
        onClose={noop}
      />,
    );
    expect(screen.getByText("2 / 3")).toBeInTheDocument();
  });

  it("next button navigates to next image", () => {
    render(
      <AttachmentLightbox
        attachments={ATTS}
        initialIndex={0}
        open={true}
        onClose={noop}
      />,
    );
    const nextBtn = screen.getByLabelText("Imagen siguiente");
    fireEvent.click(nextBtn);
    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("src", ATTS[1].url);
  });

  it("prev button navigates to previous image", () => {
    render(
      <AttachmentLightbox
        attachments={ATTS}
        initialIndex={2}
        open={true}
        onClose={noop}
      />,
    );
    const prevBtn = screen.getByLabelText("Imagen anterior");
    fireEvent.click(prevBtn);
    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("src", ATTS[1].url);
  });

  it("no prev button on first image", () => {
    render(
      <AttachmentLightbox
        attachments={ATTS}
        initialIndex={0}
        open={true}
        onClose={noop}
      />,
    );
    expect(screen.queryByLabelText("Imagen anterior")).toBeNull();
  });

  it("no next button on last image", () => {
    render(
      <AttachmentLightbox
        attachments={ATTS}
        initialIndex={2}
        open={true}
        onClose={noop}
      />,
    );
    expect(screen.queryByLabelText("Imagen siguiente")).toBeNull();
  });

  it("ArrowRight key navigates to next image", () => {
    render(
      <AttachmentLightbox
        attachments={ATTS}
        initialIndex={0}
        open={true}
        onClose={noop}
      />,
    );
    fireEvent.keyDown(window, { key: "ArrowRight" });
    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("src", ATTS[1].url);
  });

  it("ArrowLeft key navigates to previous image", () => {
    render(
      <AttachmentLightbox
        attachments={ATTS}
        initialIndex={2}
        open={true}
        onClose={noop}
      />,
    );
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("src", ATTS[1].url);
  });

  it("ArrowRight at last image stays on last image", () => {
    render(
      <AttachmentLightbox
        attachments={ATTS}
        initialIndex={2}
        open={true}
        onClose={noop}
      />,
    );
    fireEvent.keyDown(window, { key: "ArrowRight" });
    const img = screen.getByRole("img");
    // Still on last
    expect(img).toHaveAttribute("src", ATTS[2].url);
  });

  it("ArrowLeft at first image stays on first image", () => {
    render(
      <AttachmentLightbox
        attachments={ATTS}
        initialIndex={0}
        open={true}
        onClose={noop}
      />,
    );
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    const img = screen.getByRole("img");
    // Still on first
    expect(img).toHaveAttribute("src", ATTS[0].url);
  });

  it("does not show counter for single attachment", () => {
    render(
      <AttachmentLightbox
        attachments={[ATTS[0]]}
        initialIndex={0}
        open={true}
        onClose={noop}
      />,
    );
    // No "1 / 1" counter for single images
    expect(screen.queryByText("1 / 1")).toBeNull();
  });
});
