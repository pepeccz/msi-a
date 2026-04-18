/**
 * Tests for PdfViewer component.
 *
 * Strategy: mock react-pdf so jsdom (no canvas support) can run the tests.
 * We test the React glue — state transitions, UI states, page navigation.
 */
import React from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";

// ─── Mock react-pdf ──────────────────────────────────────────────────────────
// We replace Document/Page with minimal test doubles that let us simulate
// onLoadSuccess and onLoadError callbacks programmatically.

let capturedOnLoadSuccess: ((pdf: { numPages: number }) => void) | null = null;
let capturedOnLoadError: ((error: Error) => void) | null = null;

jest.mock("react-pdf", () => {
  const MockDocument = ({
    children,
    onLoadSuccess,
    onLoadError,
    loading,
  }: {
    children?: React.ReactNode;
    onLoadSuccess?: (pdf: { numPages: number }) => void;
    onLoadError?: (error: Error) => void;
    loading?: React.ReactNode;
  }) => {
    capturedOnLoadSuccess = onLoadSuccess ?? null;
    capturedOnLoadError = onLoadError ?? null;
    // Render children (pages) when present; loading slot when not yet resolved
    return (
      <div data-testid="pdf-document">
        {loading}
        {children}
      </div>
    );
  };

  const MockPage = ({ pageNumber }: { pageNumber: number }) => (
    <div data-testid={`pdf-page-${pageNumber}`}>Page {pageNumber}</div>
  );

  return {
    Document: MockDocument,
    Page: MockPage,
    pdfjs: { GlobalWorkerOptions: { workerSrc: "" } },
  };
});

jest.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: { workerSrc: "" },
}));

// Import AFTER the mock is in place
import { PdfViewer } from "../pdf-viewer";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function renderViewer(url = "http://example.com/test.pdf", fileName = "test.pdf") {
  return render(<PdfViewer url={url} fileName={fileName} />);
}

// ─── Test: Loading state ──────────────────────────────────────────────────────

describe("PdfViewer — loading state", () => {
  beforeEach(() => {
    capturedOnLoadSuccess = null;
    capturedOnLoadError = null;
  });

  it("shows a loading skeleton before PDF resolves", () => {
    renderViewer();
    // The skeleton should be present (role="status" or aria-busy, or data-testid)
    // We match by the animate-pulse class that Skeleton renders
    const skeleton = document.querySelector(".animate-pulse");
    expect(skeleton).toBeInTheDocument();
  });
});

// ─── Test: Success state ─────────────────────────────────────────────────────

describe("PdfViewer — success state", () => {
  beforeEach(() => {
    capturedOnLoadSuccess = null;
    capturedOnLoadError = null;
  });

  it("displays page counter after PDF loads successfully", async () => {
    renderViewer();

    await act(async () => {
      capturedOnLoadSuccess!({ numPages: 3 });
    });

    // Page counter must show "1 / 3"
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
  });

  it("renders first page after successful load", async () => {
    renderViewer();

    await act(async () => {
      capturedOnLoadSuccess!({ numPages: 2 });
    });

    expect(screen.getByTestId("pdf-page-1")).toBeInTheDocument();
  });
});

// ─── Test: Page navigation ────────────────────────────────────────────────────

describe("PdfViewer — page navigation", () => {
  beforeEach(() => {
    capturedOnLoadSuccess = null;
    capturedOnLoadError = null;
  });

  it("prev button is disabled on first page", async () => {
    renderViewer();

    await act(async () => {
      capturedOnLoadSuccess!({ numPages: 3 });
    });

    const prevBtn = screen.getByRole("button", { name: /página anterior/i });
    expect(prevBtn).toBeDisabled();
  });

  it("next button is disabled on last page", async () => {
    renderViewer();

    await act(async () => {
      capturedOnLoadSuccess!({ numPages: 1 });
    });

    const nextBtn = screen.getByRole("button", { name: /página siguiente/i });
    expect(nextBtn).toBeDisabled();
  });

  it("clicking next increments page counter", async () => {
    renderViewer();

    await act(async () => {
      capturedOnLoadSuccess!({ numPages: 3 });
    });

    const nextBtn = screen.getByRole("button", { name: /página siguiente/i });
    await act(async () => {
      fireEvent.click(nextBtn);
    });

    expect(screen.getByText("2 / 3")).toBeInTheDocument();
  });

  it("clicking prev after next returns to previous page", async () => {
    renderViewer();

    await act(async () => {
      capturedOnLoadSuccess!({ numPages: 3 });
    });

    const nextBtn = screen.getByRole("button", { name: /página siguiente/i });
    const prevBtn = screen.getByRole("button", { name: /página anterior/i });

    await act(async () => {
      fireEvent.click(nextBtn);
    });
    // Now on page 2
    expect(screen.getByText("2 / 3")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(prevBtn);
    });
    // Back to page 1
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
  });
});

// ─── Test: Error state ───────────────────────────────────────────────────────

describe("PdfViewer — error state", () => {
  beforeEach(() => {
    capturedOnLoadSuccess = null;
    capturedOnLoadError = null;
  });

  it("shows error message when PDF fails to load", async () => {
    renderViewer("http://example.com/broken.pdf", "broken.pdf");

    await act(async () => {
      capturedOnLoadError!(new Error("Network error"));
    });

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/no se pudo cargar el pdf/i)).toBeInTheDocument();
  });

  it("shows a download fallback link when error occurs", async () => {
    const url = "http://example.com/broken.pdf";
    renderViewer(url, "broken.pdf");

    await act(async () => {
      capturedOnLoadError!(new Error("Network error"));
    });

    const link = screen.getByRole("link", { name: /descargar/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", url);
  });
});
