import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import type { VehicleCategoryWithDetails } from "@/lib/types";

/**
 * Hook to fetch and manage category data with refetch capability.
 */
export function useCategoryData(categoryId: string) {
  const [category, setCategory] = useState<VehicleCategoryWithDetails | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchCategory = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await api.getVehicleCategory(categoryId);
      setCategory(data);
    } catch (err) {
      setError(err instanceof Error ? err : new Error("Error desconocido"));
      console.error("Error fetching category:", err);
    } finally {
      setIsLoading(false);
    }
  }, [categoryId]);

  useEffect(() => {
    fetchCategory();
  }, [fetchCategory]);

  return {
    category,
    isLoading,
    error,
    refetch: fetchCategory,
  };
}
