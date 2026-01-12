import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import type { Element } from "@/lib/types";

/**
 * Hook to fetch and manage elements for a specific category.
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
        limit: 100, // Fetch all for category
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

  return {
    elements,
    isLoading,
    error,
    refetch: fetchElements,
  };
}
