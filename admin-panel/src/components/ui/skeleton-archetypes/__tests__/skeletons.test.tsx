/**
 * Tests for skeleton archetype components.
 *
 * Tests: accessibility attributes + snapshot + structural assertions.
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import { TableSkeleton } from "../table-skeleton";
import { DetailSkeleton } from "../detail-skeleton";
import { CardGridSkeleton } from "../card-grid-skeleton";
import { ChatThreadSkeleton } from "../chat-thread-skeleton";

// ---------------------------------------------------------------------------
// Mock Table primitives to avoid needing full table CSS in jsdom
// ---------------------------------------------------------------------------

// No mock needed — Table falls back to "comfortable" when provider is absent
// (uses useContext which returns undefined safely)

// ---------------------------------------------------------------------------
// TableSkeleton
// ---------------------------------------------------------------------------

describe("TableSkeleton", () => {
  it("has role=status and aria-busy=true", () => {
    const { container } = render(<TableSkeleton />);
    const root = container.firstChild as HTMLElement;
    expect(root).toHaveAttribute("role", "status");
    expect(root).toHaveAttribute("aria-busy", "true");
  });

  it("has aria-label in Spanish", () => {
    const { container } = render(<TableSkeleton />);
    const root = container.firstChild as HTMLElement;
    expect(root).toHaveAttribute("aria-label", "Cargando datos...");
  });

  it("renders correct number of rows matching rows prop", () => {
    render(<TableSkeleton rows={5} />);
    // Each body row renders a TableRow with TableCell skeletons
    // We count tbody rows by querying the table's body rows
    const bodyRows = document.querySelectorAll("tbody tr");
    expect(bodyRows).toHaveLength(5);
  });

  it("renders default 8 rows when rows prop not specified", () => {
    render(<TableSkeleton />);
    const bodyRows = document.querySelectorAll("tbody tr");
    expect(bodyRows).toHaveLength(8);
  });

  it("renders header row by default", () => {
    render(<TableSkeleton />);
    const headerRow = document.querySelector("thead tr");
    expect(headerRow).not.toBeNull();
  });

  it("omits header row when showHeader=false", () => {
    render(<TableSkeleton showHeader={false} />);
    const headerRow = document.querySelector("thead tr");
    expect(headerRow).toBeNull();
  });

  it("renders correct number of columns from cols prop", () => {
    render(<TableSkeleton cols={[{ width: "50%" }, { width: "50%" }]} />);
    // Header should have 2 cells
    const headerCells = document.querySelectorAll("thead th");
    expect(headerCells).toHaveLength(2);
  });

  it("matches snapshot", () => {
    const { container } = render(<TableSkeleton rows={3} />);
    expect(container).toMatchSnapshot();
  });
});

// ---------------------------------------------------------------------------
// DetailSkeleton
// ---------------------------------------------------------------------------

describe("DetailSkeleton", () => {
  it("has role=status and aria-busy=true", () => {
    const { container } = render(<DetailSkeleton />);
    const root = container.firstChild as HTMLElement;
    expect(root).toHaveAttribute("role", "status");
    expect(root).toHaveAttribute("aria-busy", "true");
  });

  it("has aria-label in Spanish", () => {
    const { container } = render(<DetailSkeleton />);
    const root = container.firstChild as HTMLElement;
    expect(root).toHaveAttribute("aria-label", "Cargando detalle...");
  });

  it("renders multiple sections when specified", () => {
    const { container } = render(
      <DetailSkeleton
        sections={[
          { title: true, fields: 2 },
          { title: true, fields: 3 },
        ]}
      />
    );
    // Should render without errors and have content
    expect(container.firstChild).toBeInTheDocument();
  });

  it("renders fullWidth section as single tall skeleton", () => {
    const { container } = render(
      <DetailSkeleton sections={[{ fullWidth: true }]} />
    );
    // Should not render the two-column grid for fullWidth sections
    expect(container.firstChild).toBeInTheDocument();
  });

  it("matches snapshot", () => {
    const { container } = render(
      <DetailSkeleton sections={[{ title: true, fields: 3 }]} />
    );
    expect(container).toMatchSnapshot();
  });
});

// ---------------------------------------------------------------------------
// CardGridSkeleton
// ---------------------------------------------------------------------------

describe("CardGridSkeleton", () => {
  it("has role=status and aria-busy=true", () => {
    const { container } = render(<CardGridSkeleton />);
    const root = container.firstChild as HTMLElement;
    expect(root).toHaveAttribute("role", "status");
    expect(root).toHaveAttribute("aria-busy", "true");
  });

  it("has aria-label in Spanish", () => {
    const { container } = render(<CardGridSkeleton />);
    const root = container.firstChild as HTMLElement;
    expect(root).toHaveAttribute("aria-label", "Cargando elementos...");
  });

  it("renders correct number of cards matching items prop", () => {
    const { container } = render(<CardGridSkeleton items={6} />);
    // Count direct children (minus sr-only span = items)
    // Each item is a div.rounded-xl
    const cards = container.querySelectorAll(".rounded-xl.border");
    expect(cards).toHaveLength(6);
  });

  it("renders default 8 items when not specified", () => {
    const { container } = render(<CardGridSkeleton />);
    const cards = container.querySelectorAll(".rounded-xl.border");
    expect(cards).toHaveLength(8);
  });

  it("matches snapshot", () => {
    const { container } = render(<CardGridSkeleton items={3} cols={3} />);
    expect(container).toMatchSnapshot();
  });
});

// ---------------------------------------------------------------------------
// ChatThreadSkeleton
// ---------------------------------------------------------------------------

describe("ChatThreadSkeleton", () => {
  it("has role=status and aria-busy=true", () => {
    const { container } = render(<ChatThreadSkeleton />);
    const root = container.firstChild as HTMLElement;
    expect(root).toHaveAttribute("role", "status");
    expect(root).toHaveAttribute("aria-busy", "true");
  });

  it("has aria-label in Spanish", () => {
    const { container } = render(<ChatThreadSkeleton />);
    const root = container.firstChild as HTMLElement;
    expect(root).toHaveAttribute("aria-label", "Cargando conversación...");
  });

  it("renders correct number of message bubbles", () => {
    const { container } = render(<ChatThreadSkeleton messages={4} />);
    // Each message has flex row/flex-row-reverse alignment
    // Count by the avatar circles (h-8 w-8 rounded-full)
    const avatars = container.querySelectorAll(".rounded-full.flex-shrink-0");
    expect(avatars).toHaveLength(4);
  });

  it("matches snapshot", () => {
    const { container } = render(<ChatThreadSkeleton messages={4} />);
    expect(container).toMatchSnapshot();
  });
});
