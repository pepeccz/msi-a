"use client";

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
} from "react";
import { useIsMobile } from "@/hooks/use-media-query";

interface SidebarContextType {
  /** Whether the desktop sidebar is collapsed to icon-only mode */
  isCollapsed: boolean;
  /** Toggle desktop collapsed state */
  toggle: () => void;
  /** Collapse desktop sidebar */
  collapse: () => void;
  /** Expand desktop sidebar */
  expand: () => void;
  /** Whether the mobile sheet drawer is open */
  isMobileOpen: boolean;
  /** Open the mobile sheet drawer */
  setMobileOpen: (open: boolean) => void;
  /** True when viewport is narrower than 1024px (lg breakpoint) */
  isMobile: boolean;
}

const SidebarContext = createContext<SidebarContextType | undefined>(undefined);

const STORAGE_KEY = "sidebar_collapsed";

export function SidebarProvider({ children }: { children: React.ReactNode }) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isHydrated, setIsHydrated] = useState(false);
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const isMobile = useIsMobile();

  // Restore desktop collapsed state from localStorage
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored !== null) {
      setIsCollapsed(stored === "true");
    }
    setIsHydrated(true);
  }, []);

  // Persist desktop collapsed state (mobile open state is never persisted)
  useEffect(() => {
    if (isHydrated) {
      localStorage.setItem(STORAGE_KEY, String(isCollapsed));
    }
  }, [isCollapsed, isHydrated]);

  // Close mobile drawer automatically when viewport grows to desktop size
  useEffect(() => {
    if (!isMobile && isMobileOpen) {
      setIsMobileOpen(false);
    }
  }, [isMobile, isMobileOpen]);

  const toggle = useCallback(() => {
    setIsCollapsed((prev) => !prev);
  }, []);

  const collapse = useCallback(() => {
    setIsCollapsed(true);
  }, []);

  const expand = useCallback(() => {
    setIsCollapsed(false);
  }, []);

  const setMobileOpen = useCallback((open: boolean) => {
    setIsMobileOpen(open);
  }, []);

  return (
    <SidebarContext.Provider
      value={{
        isCollapsed,
        toggle,
        collapse,
        expand,
        isMobileOpen,
        setMobileOpen,
        isMobile,
      }}
    >
      {children}
    </SidebarContext.Provider>
  );
}

export function useSidebar() {
  const context = useContext(SidebarContext);
  if (context === undefined) {
    throw new Error("useSidebar must be used within a SidebarProvider");
  }
  return context;
}
