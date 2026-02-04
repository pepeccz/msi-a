"use client";

import { Fragment, useState, type ReactNode } from "react";
import { TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

/**
 * Element type with optional children (minimal interface for flexibility)
 */
export interface HierarchicalElement {
  id: string;
  children?: any[];
  [key: string]: any; // Allow additional properties
}

export interface HierarchicalElementRowProps<T extends HierarchicalElement = HierarchicalElement> {
  /**
   * Element to render (parent or child)
   */
  element: T;

  /**
   * Render function for table cells
   * @param element - The element to render
   * @param isChild - Whether this is a child element (for indentation)
   * @param hasChildren - Whether this element has children (for expand icon)
   * @param isExpanded - Whether this element is currently expanded
   * @param onToggleExpand - Function to toggle expansion
   */
  renderColumns: (
    element: T,
    isChild: boolean,
    hasChildren: boolean,
    isExpanded: boolean,
    onToggleExpand: () => void
  ) => ReactNode;

  /**
   * Nesting level (for deep hierarchies, 0 = root)
   * @default 0
   */
  level?: number;

  /**
   * Custom className for parent row
   */
  className?: string;

  /**
   * Custom className for child rows
   */
  childClassName?: string;

  /**
   * Optional click handler for parent row (overrides default expand behavior)
   */
  onClick?: (element: T) => void;
}

/**
 * Reusable hierarchical element row component.
 * 
 * Renders a parent row with expand/collapse functionality for children.
 * Uses Fragment with key to satisfy React's list rendering requirements.
 * 
 * @example
 * ```tsx
 * <HierarchicalElementRow
 *   element={element}
 *   renderColumns={(el, isChild, hasChildren, isExpanded, onToggle) => (
 *     <>
 *       <TableCell>
 *         {hasChildren && (
 *           <Button onClick={onToggle}>
 *             <ChevronDown className={cn(!isExpanded && "-rotate-90")} />
 *           </Button>
 *         )}
 *         <div className={cn(isChild && "pl-8")}>{el.code}</div>
 *       </TableCell>
 *       <TableCell>{el.name}</TableCell>
 *     </>
 *   )}
 * />
 * ```
 */
export function HierarchicalElementRow<T extends HierarchicalElement = HierarchicalElement>({
  element,
  renderColumns,
  level = 0,
  className,
  childClassName,
  onClick,
}: HierarchicalElementRowProps<T>) {
  const [isExpanded, setIsExpanded] = useState(false);
  
  const hasChildren = element.children && element.children.length > 0;

  const handleToggleExpand = () => {
    setIsExpanded((prev) => !prev);
  };

  const handleRowClick = () => {
    if (onClick) {
      onClick(element);
    } else if (hasChildren) {
      handleToggleExpand();
    }
  };

  return (
    <Fragment key={element.id}>
      {/* Parent row */}
      <TableRow
        onClick={hasChildren || onClick ? handleRowClick : undefined}
        className={cn(
          "hover:bg-muted/50 transition-colors",
          (hasChildren || onClick) && "cursor-pointer",
          className
        )}
      >
        {renderColumns(element, false, !!hasChildren, isExpanded, handleToggleExpand)}
      </TableRow>

      {/* Children rows (only if expanded) */}
      {hasChildren && isExpanded && element.children!.map((child) => (
        <TableRow 
          key={child.id} 
          className={cn(
            "bg-muted/10 hover:bg-muted/30 transition-colors",
            childClassName
          )}
        >
          {renderColumns(child, true, false, false, () => {})}
        </TableRow>
      ))}
    </Fragment>
  );
}
