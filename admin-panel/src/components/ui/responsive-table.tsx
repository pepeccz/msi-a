"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { useIsMobile } from "@/hooks/use-media-query";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ColumnDef<T> {
  /** Unique identifier for this column */
  key: string;
  /** Header label (shown in <th> on desktop, used as label on mobile) */
  header: string;
  /** Renders the cell content for a given row */
  cell: (row: T) => React.ReactNode;
  /** When true the column is omitted entirely from the mobile card view */
  hideOnMobile?: boolean;
  /**
   * The primary column maps to the card title (font-medium).
   * Only one column should be marked primary.
   */
  isPrimary?: boolean;
  /**
   * The secondary column maps to the card subtitle (text-sm text-muted-foreground).
   * Only one column should be marked secondary.
   */
  isSecondary?: boolean;
}

export interface ResponsiveTableProps<T> {
  data: T[];
  columns: ColumnDef<T>[];
  /** Returns a stable unique key for each row (used as React key) */
  keyExtractor: (row: T) => string;
  /** When true, renders a skeleton loading state */
  isLoading?: boolean;
  /** Message shown when data is empty (after loading) */
  emptyMessage?: string;
  /** Called when the user clicks a row or card */
  onRowClick?: (row: T) => void;
  className?: string;
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function TableSkeleton() {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="Cargando...">
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="h-10 w-full animate-pulse rounded-md bg-muted"
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex items-center justify-center py-10">
      <p className="text-sm text-muted-foreground">{message}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Desktop table view
// ---------------------------------------------------------------------------

function DesktopView<T>({
  data,
  columns,
  keyExtractor,
  onRowClick,
}: Pick<
  ResponsiveTableProps<T>,
  "data" | "columns" | "keyExtractor" | "onRowClick"
>) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          {columns.map((col) => (
            <TableHead key={col.key}>{col.header}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.map((row) => (
          <TableRow
            key={keyExtractor(row)}
            onClick={onRowClick ? () => onRowClick(row) : undefined}
            className={cn(onRowClick && "cursor-pointer")}
          >
            {columns.map((col) => (
              <TableCell key={col.key}>{col.cell(row)}</TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

// ---------------------------------------------------------------------------
// Mobile card view
// ---------------------------------------------------------------------------

function MobileView<T>({
  data,
  columns,
  keyExtractor,
  onRowClick,
}: Pick<
  ResponsiveTableProps<T>,
  "data" | "columns" | "keyExtractor" | "onRowClick"
>) {
  const primaryCol = columns.find((c) => c.isPrimary);
  const secondaryCol = columns.find((c) => c.isSecondary);
  // Columns shown as label:value grid — skip primary, secondary, and hidden ones
  const detailCols = columns.filter(
    (c) => !c.isPrimary && !c.isSecondary && !c.hideOnMobile
  );

  return (
    <div className="space-y-2">
      {data.map((row) => (
        <Card
          key={keyExtractor(row)}
          onClick={onRowClick ? () => onRowClick(row) : undefined}
          className={cn(
            "overflow-hidden",
            onRowClick &&
              "cursor-pointer transition-colors hover:bg-muted/50 active:bg-muted"
          )}
        >
          <CardContent className="p-3 md:p-4">
            {/* Card header — primary + secondary */}
            {(primaryCol || secondaryCol) && (
              <div className="mb-2">
                {primaryCol && (
                  <p className="font-medium leading-snug">
                    {primaryCol.cell(row)}
                  </p>
                )}
                {secondaryCol && (
                  <p className="text-sm text-muted-foreground">
                    {secondaryCol.cell(row)}
                  </p>
                )}
              </div>
            )}

            {/* Detail grid — label : value pairs */}
            {detailCols.length > 0 && (
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
                {detailCols.map((col) => (
                  <React.Fragment key={col.key}>
                    <dt className="text-xs text-muted-foreground">
                      {col.header}
                    </dt>
                    <dd className="text-xs">{col.cell(row)}</dd>
                  </React.Fragment>
                ))}
              </dl>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ResponsiveTable — public component
// ---------------------------------------------------------------------------

/**
 * Renders a `<Table>` on desktop (≥ 1024px) and a card-based list on mobile
 * (< 1024px), switching automatically via the `useIsMobile()` hook.
 *
 * Column roles:
 * - `isPrimary`    → card title (font-medium)
 * - `isSecondary`  → card subtitle (text-sm text-muted-foreground)
 * - `hideOnMobile` → column is hidden on mobile entirely
 * - all others     → rendered as label:value pairs inside a detail grid
 *
 * @example
 * <ResponsiveTable
 *   data={users}
 *   keyExtractor={(u) => u.id}
 *   columns={[
 *     { key: "name", header: "Nombre", cell: (u) => u.name, isPrimary: true },
 *     { key: "email", header: "Email", cell: (u) => u.email, isSecondary: true },
 *     { key: "role", header: "Rol", cell: (u) => <Badge>{u.role}</Badge> },
 *     { key: "actions", header: "", cell: (u) => <Actions user={u} />, hideOnMobile: true },
 *   ]}
 *   onRowClick={(u) => router.push(`/users/${u.id}`)}
 * />
 */
export function ResponsiveTable<T>({
  data,
  columns,
  keyExtractor,
  isLoading = false,
  emptyMessage = "No hay datos disponibles",
  onRowClick,
  className,
}: ResponsiveTableProps<T>) {
  const isMobile = useIsMobile();

  return (
    <div className={cn("w-full", className)}>
      {isLoading ? (
        <TableSkeleton />
      ) : data.length === 0 ? (
        <EmptyState message={emptyMessage} />
      ) : isMobile ? (
        <MobileView
          data={data}
          columns={columns}
          keyExtractor={keyExtractor}
          onRowClick={onRowClick}
        />
      ) : (
        <DesktopView
          data={data}
          columns={columns}
          keyExtractor={keyExtractor}
          onRowClick={onRowClick}
        />
      )}
    </div>
  );
}
