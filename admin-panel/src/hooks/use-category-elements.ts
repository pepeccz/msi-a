import { useState, useEffect, useCallback, useMemo } from "react";
import api from "@/lib/api";
import type { Element } from "@/lib/types";

export interface ElementTreeNode extends Element {
  children: Element[];
}

/**
 * Hook to fetch and manage elements for a specific category.
 * Returns both a flat list and a tree structure (parents with nested children).
 */
export function useCategoryElements(categoryId: string) {
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
        limit: 500,
      });
      setElements(response.items);
    } catch (err) {
      setError(err instanceof Error ? err : new Error("Error desconocido"));
      console.error("Error fetching elements:", err);
    } finally {
      setIsLoading(false);
    }
  }, [categoryId]);

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
