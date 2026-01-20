"use client";

import { createContext, useContext, useState, useEffect, ReactNode } from "react";

interface GlobalSearchContextType {
  open: boolean;
  openSearch: () => void;
  closeSearch: () => void;
  toggleSearch: () => void;
}

const GlobalSearchContext = createContext<GlobalSearchContextType | undefined>(
  undefined
);

export function GlobalSearchProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);

  // Global keyboard shortcut: Cmd/Ctrl + K
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((prevOpen) => !prevOpen);
      }
    };

    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  const openSearch = () => setOpen(true);
  const closeSearch = () => setOpen(false);
  const toggleSearch = () => setOpen((prev) => !prev);

  return (
    <GlobalSearchContext.Provider
      value={{ open, openSearch, closeSearch, toggleSearch }}
    >
      {children}
    </GlobalSearchContext.Provider>
  );
}

export function useGlobalSearchState() {
  const context = useContext(GlobalSearchContext);
  if (context === undefined) {
    throw new Error(
      "useGlobalSearchState must be used within a GlobalSearchProvider"
    );
  }
  return context;
}
