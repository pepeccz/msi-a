"use client";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

import { useState } from "react";
import { Document, Page } from "react-pdf";
import { GlobalWorkerOptions } from "pdfjs-dist";
import { ChevronLeft, ChevronRight, AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

// Configure worker once at module scope.
// Import GlobalWorkerOptions DIRECTLY from pdfjs-dist rather than via the
// `pdfjs` re-export from react-pdf — Turbopack cannot resolve the virtual
// module factory of `export * as pdfjs` across the nested-dep path, which
// crashes with "module factory is not available" at runtime.
// See: react-pdf/pdfjs-dist re-export incompatibility with Turbopack HMR.
GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

// ─── Constants ───────────────────────────────────────────────────────────────

const FIRST_PAGE = 1;

// ─── Types ───────────────────────────────────────────────────────────────────

export interface PdfViewerProps {
  url: string;
  fileName?: string;
  className?: string;
  onError?: (error: Error) => void;
}

// ─── Component ───────────────────────────────────────────────────────────────

/**
 * PdfViewer — renders a PDF on canvas using react-pdf (pdfjs-dist under the hood).
 *
 * Immune to browser PDF-viewer settings and Brave Shields because it renders
 * entirely on <canvas>, not via <iframe>/<embed>.
 *
 * Must be loaded via next/dynamic({ ssr: false }) — pdfjs reads DOMMatrix/Path2D
 * at module init which are not available in Node.
 */
export function PdfViewer({ url, fileName, className, onError }: PdfViewerProps) {
  const [numPages, setNumPages] = useState<number | null>(null);
  const [currentPage, setCurrentPage] = useState(FIRST_PAGE);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  function handleLoadSuccess({ numPages: total }: { numPages: number }) {
    setNumPages(total);
    setIsLoading(false);
  }

  function handleLoadError(err: Error) {
    setError(err);
    setIsLoading(false);
    onError?.(err);
  }

  function goToPrev() {
    setCurrentPage((p) => Math.max(FIRST_PAGE, p - 1));
  }

  function goToNext() {
    setCurrentPage((p) => Math.min(numPages ?? FIRST_PAGE, p + 1));
  }

  if (error) {
    return (
      <div className={cn("flex flex-col gap-3 p-4", className)}>
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>No se pudo cargar el PDF</AlertTitle>
          <AlertDescription className="mt-2">
            {error.message}
          </AlertDescription>
        </Alert>
        <Button variant="outline" asChild>
          <a href={url} download={fileName ?? true}>
            Descargar
          </a>
        </Button>
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col items-center gap-2 w-full h-full", className)}>
      {/* PDF canvas area */}
      {/*
        Nested wrapper pattern: the outer div scrolls; the inner div uses
        `min-h-full` so the page is vertically centered when it fits and
        anchored to the top (scrollable) when it overflows. `items-center`
        on a tall child would clip its top because scrollTop cannot be
        negative under flex centering.
      */}
      <div className="flex-1 w-full overflow-auto min-h-0 py-4">
        <div className="min-h-full flex items-start justify-center">
          <Document
            key={url}
            file={url}
            onLoadSuccess={handleLoadSuccess}
            onLoadError={handleLoadError}
            loading={
              <Skeleton className="w-full h-full min-h-[50vh]" />
            }
          >
            {!isLoading && numPages !== null && (
              <Page
                pageNumber={currentPage}
                renderTextLayer
                renderAnnotationLayer
              />
            )}
          </Document>
        </div>
      </div>

      {/* Page navigation bar — visible once loaded */}
      {numPages !== null && (
        <div className="flex items-center gap-3 py-2 px-4 bg-background/80 backdrop-blur-sm rounded-md border">
          <Button
            variant="ghost"
            size="icon"
            onClick={goToPrev}
            disabled={currentPage <= FIRST_PAGE}
            aria-label="Página anterior"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>

          <span className="text-sm font-medium tabular-nums">
            {currentPage} / {numPages}
          </span>

          <Button
            variant="ghost"
            size="icon"
            onClick={goToNext}
            disabled={currentPage >= numPages}
            aria-label="Página siguiente"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}

export default PdfViewer;
