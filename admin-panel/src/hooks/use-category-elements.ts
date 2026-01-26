import { useState, useEffect, useCallback, useMemo } from "react";
import api from "@/lib/api";
import type { Element } from "@/lib/types";
import { DEFAULT_ELEMENTS_LIMIT } from "@/lib/constants";

export interface ElementTreeNode extends Element {
  children: Element[];
}

interface UseCategoryElementsOptions {
  /** Maximum number of elements to fetch (default: 500) */
  limit?: number;
}

/**
 * Hook to fetch and manage elements for a specific category.
 * Returns both a flat list and a tree structure (parents with nested children).
 * 
 * @param categoryId - Category UUID
 * @param options - Optional configuration (limit, etc.)
 */
export function useCategoryElements(
  categoryId: string,
  options: UseCategoryElementsOptions = {}
) {
  const { limit = DEFAULT_ELEMENTS_LIMIT } = options;
  
  const [elements, setElements] = useState<Element[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchElements = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const response = await api.getElements({
        category_id: categoryId,
        skip: 0,
        limit,
      });
      setElements(response.items);
    } catch (err) {
      setError(err instanceof Error ? err : new Error("Error desconocido"));
      console.error("Error fetching elements:", err);
    } finally {
      setIsLoading(false);
    }
  }, [categoryId, limit]);

  useEffect(() => {
    fetchElements();
  }, [fetchElements]);

  // Build tree structure: parents with their children nested
  const elementTree = useMemo<ElementTreeNode[]>(() => {
    const parents = elements.filter((e) => !e.parent_element_id);
    return parents
      .map((parent) => ({
        ...parent,
        children: elements
          .filter((e) => e.parent_element_id === parent.id)
          .sort((a, b) => a.sort_order - b.sort_order),
      }))
      .sort((a, b) => a.sort_order - b.sort_order);
  }, [elements]);

  return {
    elements,
    elementTree,
    isLoading,
    error,
    refetch: fetchElements,
  };
}
