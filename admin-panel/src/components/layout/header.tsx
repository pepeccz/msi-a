"use client";

import { usePathname } from "next/navigation";
import { Menu } from "lucide-react";
import { NotificationCenter } from "@/components/notification-center";
import { GlobalSearch } from "@/components/global-search";
import { ThemeToggle } from "@/components/shared/theme-toggle";
import { Button } from "@/components/ui/button";
import { useSidebar } from "@/contexts/sidebar-context";

const pageTitles: Record<string, string> = {
  "/dashboard": "Dashboard",
  "/escalations": "Escalaciones",
  "/users": "Usuarios",
  "/conversations": "Conversaciones",
  "/reformas": "Reformas de Homologacion",
  "/advertencias": "Advertencias",
  "/normativas": "Normativas",
  "/settings": "Configuración",
  "/imagenes": "Imagenes",
  "/prompts": "Prompts",
};

export function Header() {
  const pathname = usePathname();
  const { isMobile, setMobileOpen } = useSidebar();

  // Get the base path for nested routes
  const basePath = "/" + (pathname?.split("/")[1] || "");
  const title = pageTitles[basePath] || pageTitles[pathname || ""] || "";

  return (
    <header className="sticky top-0 z-40 flex h-14 items-center justify-between border-b bg-background/95 px-6 backdrop-blur supports-[backdrop-filter]:bg-background/60">
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
        {title && (
          <h1 className="text-lg font-semibold text-foreground">{title}</h1>
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
