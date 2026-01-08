"use client";

import { usePathname } from "next/navigation";
import { EscalationNotifications } from "@/components/escalation-notifications";

const pageTitles: Record<string, string> = {
  "/dashboard": "Dashboard",
  "/escalations": "Escalaciones",
  "/users": "Usuarios",
  "/conversations": "Conversaciones",
  "/tarifas": "Categorias de Tarifas",
  "/advertencias": "Advertencias",
  "/servicios": "Servicios Adicionales",
  "/normativas": "Normativas",
  "/settings": "Configuracion",
  "/imagenes": "Imagenes",
  "/prompts": "Prompts",
};

export function Header() {
  const pathname = usePathname();

  // Get the base path for nested routes
  const basePath = "/" + (pathname?.split("/")[1] || "");
  const title = pageTitles[basePath] || pageTitles[pathname || ""] || "";

  return (
    <header className="sticky top-0 z-40 flex h-14 items-center justify-between border-b bg-background/95 px-6 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="flex items-center gap-2">
        {title && (
          <h1 className="text-lg font-semibold text-foreground">{title}</h1>
        )}
      </div>
      <div className="flex items-center gap-2">
        <EscalationNotifications />
      </div>
    </header>
  );
}
