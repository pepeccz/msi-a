"use client";

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
} from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Density = "comfortable" | "compact";

interface TableDensityContextType {
  density: Density;
  setDensity: (d: Density) => void;
  toggleDensity: () => void;
}

// ---------------------------------------------------------------------------
// Context (exported for direct useContext usage in table.tsx)
// ---------------------------------------------------------------------------

export const TableDensityContext = createContext<TableDensityContextType | undefined>(
  undefined
);

const STORAGE_KEY = "msia-admin:table-density";

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function TableDensityProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  // Start with "comfortable" — SSR-safe initial value.
  // The actual stored preference is applied in useEffect (client-only).
  const [density, setDensityState] = useState<Density>("comfortable");
  const [isHydrated, setIsHydrated] = useState(false);

  // Hydrate from localStorage after mount (avoids SSR/CSR mismatch)
  useEffect(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === "compact" || stored === "comfortable") {
        setDensityState(stored);
      }
    }
    setIsHydrated(true);
  }, []);

  // Persist to localStorage whenever density changes (after hydration)
  useEffect(() => {
    if (isHydrated && typeof window !== "undefined") {
      localStorage.setItem(STORAGE_KEY, density);
    }
  }, [density, isHydrated]);

  const setDensity = useCallback((d: Density) => {
    setDensityState(d);
  }, []);

  const toggleDensity = useCallback(() => {
    setDensityState((prev) => (prev === "comfortable" ? "compact" : "comfortable"));
  }, []);

  return (
    <TableDensityContext.Provider value={{ density, setDensity, toggleDensity }}>
      {children}
    </TableDensityContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useTableDensity(): TableDensityContextType {
  const context = useContext(TableDensityContext);
  if (context === undefined) {
    throw new Error(
      "useTableDensity must be used within a TableDensityProvider"
    );
  }
  return context;
}
