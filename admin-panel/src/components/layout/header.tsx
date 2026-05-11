"use client";

import { Menu } from "lucide-react";
import { NotificationCenter } from "@/components/notification-center";
import { GlobalSearch } from "@/components/global-search";
import { ThemeToggle } from "@/components/shared/theme-toggle";
import { Button } from "@/components/ui/button";
import { useSidebar } from "@/contexts/sidebar-context";

export function Header() {
  const { isMobile, setMobileOpen } = useSidebar();

  return (
    <header className="sticky top-0 z-40 flex h-11 items-center justify-between border-b bg-background/95 px-6 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="flex items-center gap-2">
        {/* Hamburger — visible only on mobile (<1024px) */}
        {isMobile && (
          <Button
            variant="ghost"
            size="icon"
            aria-label="Abrir menú"
            onClick={() => setMobileOpen(true)}
            className="-ml-2"
          >
            <Menu className="h-5 w-5" />
          </Button>
        )}
      </div>
      <div className="flex items-center gap-4">
        <GlobalSearch variant="trigger" />
        <ThemeToggle />
        <NotificationCenter />
      </div>
    </header>
  );
}
