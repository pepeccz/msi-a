/**
 * Tests for Sidebar — Slice 1 critical paths.
 *
 * Scope:
 *   - Nav items render with correct labels
 *   - Active nav item receives aria-current="page" and active-indicator class
 *   - Active indicator 3px bar is rendered for active items only
 *   - Sidebar does NOT render a density toggle (table density is table-only)
 *   - Collapse toggle has correct dynamic aria-label
 *
 * Heavy deps (useAuth, useSidebar, api, next/navigation, DirtyFormContext)
 * are fully mocked — behaviour under test is class/aria output, not logic.
 */

import React from "react";
import { render, screen } from "@testing-library/react";

// ─── Mock Next.js navigation ────────────────────────────────────────────────
jest.mock("next/navigation", () => ({
  usePathname: jest.fn(() => "/cases"),
  useRouter: jest.fn(() => ({ push: jest.fn() })),
}));

// ─── Mock Next.js Image (avoid real img processing) ─────────────────────────
jest.mock("next/image", () => {
  // eslint-disable-next-line @next/next/no-img-element
  const MockImage = (props: React.ImgHTMLAttributes<HTMLImageElement>) => (
    // biome-ignore lint/a11y/useAltText: test mock
    <img {...props} alt={props.alt ?? ""} />
  );
  MockImage.displayName = "MockImage";
  return MockImage;
});

// ─── Mock auth context ───────────────────────────────────────────────────────
jest.mock("@/contexts/auth-context", () => ({
  useAuth: jest.fn(() => ({
    user: { display_name: "Admin", username: "admin", role: "admin" },
    logout: jest.fn(),
  })),
}));

// ─── Mock sidebar context ────────────────────────────────────────────────────
const mockToggle = jest.fn();
jest.mock("@/contexts/sidebar-context", () => ({
  useSidebar: jest.fn(() => ({
    isCollapsed: false,
    toggle: mockToggle,
    isMobile: false,
    isMobileOpen: false,
    setMobileOpen: jest.fn(),
  })),
}));

// ─── Mock dirty form context ─────────────────────────────────────────────────
jest.mock("@/contexts/dirty-form-context", () => ({
  useDirtyFormSafe: jest.fn(() => ({
    hasAnyDirty: false,
    guardNavigation: jest.fn(() => Promise.resolve(true)),
  })),
}));

// ─── Mock API (badge polling) ────────────────────────────────────────────────
jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: {
    getEscalationStats: jest.fn(() =>
      Promise.resolve({ pending: 3, by_status: {} })
    ),
    getCaseStats: jest.fn(() =>
      Promise.resolve({ pending_review: 5, by_status: {} })
    ),
  },
}));

// ─── Import after mocks ──────────────────────────────────────────────────────
import { Sidebar } from "../sidebar";
import { usePathname } from "next/navigation";
import { useSidebar } from "@/contexts/sidebar-context";

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("Sidebar — Slice 1 critical paths", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // Default: expanded, pathname = /cases
    (usePathname as jest.Mock).mockReturnValue("/cases");
    (useSidebar as jest.Mock).mockReturnValue({
      isCollapsed: false,
      toggle: mockToggle,
      isMobile: false,
      isMobileOpen: false,
      setMobileOpen: jest.fn(),
    });
  });

  // (a) Nav items render
  it("renders all main nav item labels when expanded", () => {
    render(<Sidebar />);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Expedientes")).toBeInTheDocument();
    expect(screen.getByText("Escalaciones")).toBeInTheDocument();
    expect(screen.getByText("Usuarios")).toBeInTheDocument();
    expect(screen.getByText("Conversaciones")).toBeInTheDocument();
  });

  // (b) aria-current="page" on active item
  it("sets aria-current='page' on the active nav link", () => {
    (usePathname as jest.Mock).mockReturnValue("/cases");
    render(<Sidebar />);

    // The active link wraps an anchor with aria-current
    const activeLinks = document.querySelectorAll('[aria-current="page"]');
    expect(activeLinks.length).toBe(1);
    // The active link should be the /cases one — check href
    const activeLink = activeLinks[0] as HTMLAnchorElement;
    expect(activeLink.getAttribute("href")).toBe("/cases");
  });

  // (c) No aria-current on inactive items
  it("does NOT set aria-current on inactive nav links", () => {
    (usePathname as jest.Mock).mockReturnValue("/cases");
    render(<Sidebar />);

    // All links without aria-current
    const allLinks = document.querySelectorAll('a[href]');
    const inactiveLinks = Array.from(allLinks).filter(
      (l) => l.getAttribute("href") !== "/cases" && l.getAttribute("aria-current")
    );
    expect(inactiveLinks.length).toBe(0);
  });

  // (d) 3px active indicator bar rendered for active item
  it("renders the 3px active indicator span for the active nav item", () => {
    (usePathname as jest.Mock).mockReturnValue("/cases");
    render(<Sidebar />);

    // The active bar is an absolutely-positioned span with bg-sidebar-primary class
    const activeBar = document.querySelector(".bg-sidebar-primary");
    expect(activeBar).toBeInTheDocument();
    expect(activeBar?.tagName.toLowerCase()).toBe("span");
  });

  // (e) Active bar NOT rendered for inactive items
  it("does not render active indicator bar for inactive nav items", () => {
    (usePathname as jest.Mock).mockReturnValue("/cases");
    render(<Sidebar />);

    // Only one active bar should exist across all nav items
    const activeBars = document.querySelectorAll(".bg-sidebar-primary");
    expect(activeBars.length).toBe(1);
  });

  // (f) No density toggle rendered — density is table-only (Fase 0)
  it("does NOT render a density toggle button inside the sidebar", () => {
    render(<Sidebar />);
    // Density toggle has aria-label "Cambiar densidad" in Fase 0
    const densityBtn = screen.queryByRole("button", {
      name: /densidad|density/i,
    });
    expect(densityBtn).toBeNull();
  });

  // (g) Collapse toggle has correct aria-label when expanded
  it("collapse toggle has aria-label 'Colapsar menú' when sidebar is expanded", () => {
    (useSidebar as jest.Mock).mockReturnValue({
      isCollapsed: false,
      toggle: mockToggle,
      isMobile: false,
      isMobileOpen: false,
      setMobileOpen: jest.fn(),
    });
    render(<Sidebar />);

    const collapseBtn = screen.getByRole("button", { name: "Colapsar menú" });
    expect(collapseBtn).toBeInTheDocument();
  });

  // (h) Collapse toggle has correct aria-label when collapsed
  it("collapse toggle has aria-label 'Expandir menú' when sidebar is collapsed", () => {
    (useSidebar as jest.Mock).mockReturnValue({
      isCollapsed: true,
      toggle: mockToggle,
      isMobile: false,
      isMobileOpen: false,
      setMobileOpen: jest.fn(),
    });
    render(<Sidebar />);

    const expandBtn = screen.getByRole("button", { name: "Expandir menú" });
    expect(expandBtn).toBeInTheDocument();
  });

  // (i) Logo applies brightness/invert ONLY in dark mode
  it("applies brightness/invert filters only in dark mode", () => {
    render(<Sidebar />);
    const logo = screen.getByAltText("MSI Automotive");
    expect(logo.className).toContain("dark:brightness-0");
    expect(logo.className).toContain("dark:invert");
  });

  // (j) Section labels exist in DOM (group nav semantics preserved)
  it("renders nav group labels when expanded", () => {
    render(<Sidebar />);
    // Labels use uppercase styling but text is "Principal", "Sistema", "Herramientas"
    expect(screen.getByText("Principal")).toBeInTheDocument();
    expect(screen.getByText("Sistema")).toBeInTheDocument();
    expect(screen.getByText("Herramientas")).toBeInTheDocument();
  });
});
