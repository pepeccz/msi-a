/**
 * Tests for MessageAttachments grid component (T10).
 *
 * TDD cycle: RED (tests written first)
 *
 * Covers design A7 layout rules:
 *   1  → single image max-w-320
 *   2  → grid-cols-2
 *   3  → 1 large left + 2 stacked right
 *   4  → 2×2 grid
 *   5  → 2×3 grid, 5 cells, last cell of row empty
 *   6  → 2×3 full grid, no overlay
 *   7+ → 2×3 grid, 5 shown + overlay on 6th cell showing "+N"
 *
 * Additional scenarios:
 *   - Broken URL → placeholder shown (not red flash)
 *   - Click fires onOpen callback with correct index
 */

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { MessageAttachments } from "../message-attachments";
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
    size_bytes: 12345,
    width: 800,
    height: 600,
    position: i,
    created_at: "2026-01-01T00:00:00Z",
  };
}

function makeAtts(n: number): MessageAttachment[] {
  return Array.from({ length: n }, (_, i) => makeAtt(i));
}

const noop = jest.fn();

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("MessageAttachments", () => {
  beforeEach(() => {
    noop.mockClear();
  });

  it("returns null when attachments is empty", () => {
    const { container } = render(
      <MessageAttachments attachments={[]} onOpen={noop} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("1 image: renders single img without grid, max-width class applied", () => {
    render(<MessageAttachments attachments={makeAtts(1)} onOpen={noop} />);
    const imgs = screen.getAllByRole("img");
    expect(imgs).toHaveLength(1);
    // The wrapper should have max-w-[320px] class
    const btn = imgs[0].closest("button");
    const wrapper = btn?.parentElement;
    expect(wrapper?.className).toContain("max-w-[320px]");
  });

  it("2 images: renders grid with 2 images", () => {
    render(<MessageAttachments attachments={makeAtts(2)} onOpen={noop} />);
    const imgs = screen.getAllByRole("img");
    expect(imgs).toHaveLength(2);
    // Grid container has grid-cols-2
    const container = imgs[0].closest("div[class*='grid']");
    expect(container?.className).toContain("grid-cols-2");
  });

  it("3 images: renders 3 images", () => {
    render(<MessageAttachments attachments={makeAtts(3)} onOpen={noop} />);
    const imgs = screen.getAllByRole("img");
    expect(imgs).toHaveLength(3);
  });

  it("4 images: renders 2×2 grid with 4 images", () => {
    render(<MessageAttachments attachments={makeAtts(4)} onOpen={noop} />);
    const imgs = screen.getAllByRole("img");
    expect(imgs).toHaveLength(4);
    const container = imgs[0].closest("div[class*='grid']");
    expect(container?.className).toContain("grid-cols-2");
  });

  it("5 images: renders 5 visible images without overlay", () => {
    render(<MessageAttachments attachments={makeAtts(5)} onOpen={noop} />);
    const imgs = screen.getAllByRole("img");
    expect(imgs).toHaveLength(5);
    // No overlay text for 5 images
    expect(screen.queryByText(/^\+/)).toBeNull();
  });

  it("6 images: renders 6 images in 2×3 grid, no overlay", () => {
    render(<MessageAttachments attachments={makeAtts(6)} onOpen={noop} />);
    const imgs = screen.getAllByRole("img");
    expect(imgs).toHaveLength(6);
    expect(screen.queryByText(/^\+/)).toBeNull();
  });

  it("7 images: renders 6 images (5 + overlay on 6th) with +1 text", () => {
    render(<MessageAttachments attachments={makeAtts(7)} onOpen={noop} />);
    const imgs = screen.getAllByRole("img");
    expect(imgs).toHaveLength(6); // only 6 img elements rendered
    // Overlay text shows "+1" (7 - 6 = 1)
    expect(screen.getByText("+1")).toBeInTheDocument();
  });

  it("10 images: renders overlay with +4", () => {
    render(<MessageAttachments attachments={makeAtts(10)} onOpen={noop} />);
    const imgs = screen.getAllByRole("img");
    expect(imgs).toHaveLength(6);
    // 10 - 6 = 4
    expect(screen.getByText("+4")).toBeInTheDocument();
  });

  it("click on image fires onOpen with correct index", () => {
    render(<MessageAttachments attachments={makeAtts(3)} onOpen={noop} />);
    const buttons = screen.getAllByRole("button");
    // Click second image (index 1)
    fireEvent.click(buttons[1]);
    expect(noop).toHaveBeenCalledWith(expect.any(Array), 1);
  });

  it("click on first image fires onOpen with index 0", () => {
    render(<MessageAttachments attachments={makeAtts(2)} onOpen={noop} />);
    const buttons = screen.getAllByRole("button");
    fireEvent.click(buttons[0]);
    expect(noop).toHaveBeenCalledWith(expect.any(Array), 0);
  });

  it("broken image URL: onError sets fallback src (no red flash)", () => {
    const atts = makeAtts(1);
    render(<MessageAttachments attachments={atts} onOpen={noop} />);
    const img = screen.getByRole("img");
    // Simulate image load error
    fireEvent.error(img);
    // After error the src should be a data URI (not the original broken URL)
    expect((img as HTMLImageElement).src).toContain("data:");
  });

  it("images have loading=lazy attribute", () => {
    render(<MessageAttachments attachments={makeAtts(4)} onOpen={noop} />);
    const imgs = screen.getAllByRole("img");
    imgs.forEach((img) => {
      expect(img).toHaveAttribute("loading", "lazy");
    });
  });

  it("images have alt text from filename", () => {
    const atts = makeAtts(1);
    render(<MessageAttachments attachments={atts} onOpen={noop} />);
    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("alt", "image_0.jpg");
  });

  it("images with null filename get alt='imagen'", () => {
    const att: MessageAttachment = {
      ...makeAtt(0),
      filename: null,
    };
    render(<MessageAttachments attachments={[att]} onOpen={noop} />);
    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("alt", "imagen");
  });
});
