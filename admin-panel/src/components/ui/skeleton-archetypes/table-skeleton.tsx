import * as React from "react";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

// Repeating width pattern to approximate real content rhythm and reduce CLS
const CELL_WIDTHS = ["60%", "40%", "70%", "50%", "80%"];

interface ColConfig {
  width?: string;
}

interface TableSkeletonProps {
  /** Number of skeleton rows to render. Default: 8 */
  rows?: number;
  /**
   * Column configuration. Each entry optionally specifies a width.
   * If not provided, defaults to 4 columns with the repeating pattern.
   */
  cols?: ColConfig[];
  /** Whether to render the table header row. Default: true */
  showHeader?: boolean;
  className?: string;
}

/**
 * TableSkeleton — renders a full `<Table>` shell with ghost rows/cells.
 *
 * Uses the actual Table/TableRow/TableCell primitives so the skeleton
 * layout matches the post-load table (prevents CLS).
 *
 * Accessibility: role="status" + aria-busy="true" on the root.
 *
 * @example
 * <TableSkeleton rows={8} cols={[{ width: "30%" }, { width: "20%" }, {}]} />
 */
export function TableSkeleton({
  rows = 8,
  cols,
  showHeader = true,
  className,
}: TableSkeletonProps) {
  const resolvedCols: ColConfig[] =
    cols && cols.length > 0
      ? cols
      : [{ width: "30%" }, { width: "20%" }, { width: "15%" }, { width: "25%" }];

  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Cargando datos..."
      aria-live="polite"
      className={cn("w-full", className)}
    >
      <Table>
        {showHeader && (
          <TableHeader>
            <TableRow>
              {resolvedCols.map((col, colIdx) => (
                <TableHead key={colIdx}>
                  <Skeleton
                    className="h-4"
                    style={{
                      width:
                        col.width ??
                        CELL_WIDTHS[colIdx % CELL_WIDTHS.length],
                    }}
                  />
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
        )}
        <TableBody>
          {Array.from({ length: rows }).map((_, rowIdx) => (
            <TableRow key={rowIdx}>
              {resolvedCols.map((col, colIdx) => (
                <TableCell key={colIdx}>
                  <Skeleton
                    className="h-4"
                    style={{
                      width:
                        col.width ??
                        CELL_WIDTHS[(rowIdx + colIdx) % CELL_WIDTHS.length],
                    }}
                  />
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <span className="sr-only">Cargando datos...</span>
    </div>
  );
}
