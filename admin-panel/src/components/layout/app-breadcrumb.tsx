"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight, Home } from "lucide-react";

const PATH_LABELS: Record<string, string> = {
  dashboard:       "Dashboard",
  cases:           "Expedientes",
  escalations:     "Escalaciones",
  users:           "Usuarios",
  conversations:   "Conversaciones",
  reformas:        "Reformas",
  elementos:       "Elementos",
  advertencias:    "Advertencias",
  imagenes:        "Imágenes",
  normativas:      "Normativas",
  consulta:        "Consulta RAG",
  documentos:      "Documentos",
  settings:        "Configuración",
  config:          "General",
  system:          "Sistema",
  "admin-users":   "Administradores",
  usage:           "Uso de Tokens",
  inclusions:      "Inclusiones",
  tariffs:         "Tarifas",
  categories:      "Categorías",
  warnings:        "Advertencias",
  "rag-query":     "Consulta RAG",
};

function isUUID(segment: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
    segment
  );
}

function getSegmentLabel(segment: string): string {
  if (isUUID(segment)) return "Detalle";
  return (
    PATH_LABELS[segment] ??
    segment
      .replace(/-/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

export function AppBreadcrumb() {
  const pathname = usePathname();

  // Filtrar segmentos vacíos y grupos de rutas Next.js como (authenticated)
  const segments = pathname
    .split("/")
    .filter(Boolean)
    .filter((s) => !s.startsWith("("));

  // No mostrar en la raíz ni en páginas de primer nivel (ej: /dashboard solo)
  if (segments.length <= 1) return null;

  const crumbs = segments.map((segment, idx) => {
    const href = "/" + segments.slice(0, idx + 1).join("/");
    const label = getSegmentLabel(segment);
    const isLast = idx === segments.length - 1;
    return { href, label, isLast };
  });

  return (
    <nav
      aria-label="Breadcrumb"
      className="flex items-center gap-1 px-6 py-2 text-sm border-b bg-background text-muted-foreground"
    >
      <Link
        href="/dashboard"
        className="hover:text-foreground transition-colors flex items-center"
        aria-label="Inicio"
      >
        <Home className="h-3.5 w-3.5" />
      </Link>
      {crumbs.map((crumb) => (
        <span key={crumb.href} className="flex items-center gap-1">
          <ChevronRight className="h-3.5 w-3.5 flex-shrink-0" />
          {crumb.isLast ? (
            <span className="text-foreground font-medium">{crumb.label}</span>
          ) : (
            <Link
              href={crumb.href}
              className="hover:text-foreground transition-colors"
            >
              {crumb.label}
            </Link>
          )}
        </span>
      ))}
    </nav>
  );
}
