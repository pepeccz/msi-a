"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import {
  Home,
  FileText,
  PhoneForwarded,
  MessageSquare,
  Users,
  Car,
  Package,
  AlertTriangle,
  BookOpen,
  Image,
  Settings,
  type LucideIcon,
} from "lucide-react";
import api from "@/lib/api";
import type { Element, VehicleCategory, TariffTier, User } from "@/lib/types";

export interface SearchResult {
  id: string;
  type: "page" | "element" | "category" | "tier" | "user";
  title: string;
  subtitle?: string;
  icon: LucideIcon;
  href: string;
  keywords?: string[];
}

interface SearchablePageDefinition {
  title: string;
  href: string;
  icon: LucideIcon;
  keywords: string[];
}

// Paginas estaticas buscables
const SEARCHABLE_PAGES: SearchablePageDefinition[] = [
  {
    title: "Dashboard",
    href: "/dashboard",
    icon: Home,
    keywords: ["inicio", "panel", "principal", "kpis"],
  },
  {
    title: "Expedientes",
    href: "/cases",
    icon: FileText,
    keywords: ["casos", "homologaciones", "tramites"],
  },
  {
    title: "Escalaciones",
    href: "/escalations",
    icon: PhoneForwarded,
    keywords: ["escalar", "humano", "atencion"],
  },
  {
    title: "Conversaciones",
    href: "/conversations",
    icon: MessageSquare,
    keywords: ["chat", "historial", "mensajes"],
  },
  {
    title: "Usuarios",
    href: "/users",
    icon: Users,
    keywords: ["clientes", "telefono", "contactos"],
  },
  {
    title: "Reformas",
    href: "/reformas",
    icon: Car,
    keywords: ["tarifas", "categorias", "precios", "vehiculos"],
  },
  {
    title: "Elementos",
    href: "/elementos",
    icon: Package,
    keywords: ["piezas", "componentes", "items"],
  },
  {
    title: "Advertencias",
    href: "/advertencias",
    icon: AlertTriangle,
    keywords: ["warnings", "avisos", "alertas"],
  },
  {
    title: "Normativas",
    href: "/normativas",
    icon: BookOpen,
    keywords: ["documentos", "rag", "regulacion", "leyes"],
  },
  {
    title: "Imagenes",
    href: "/imagenes",
    icon: Image,
    keywords: ["fotos", "galeria", "multimedia"],
  },
  {
    title: "Configuracion",
    href: "/settings",
    icon: Settings,
    keywords: ["ajustes", "sistema", "opciones"],
  },
];

interface UseGlobalSearchOptions {
  debounceMs?: number;
  minQueryLength?: number;
}

interface UseGlobalSearchReturn {
  query: string;
  setQuery: (q: string) => void;
  isLoading: boolean;
  // Grouped results
  pages: SearchResult[];
  elements: SearchResult[];
  categories: SearchResult[];
  tiers: SearchResult[];
  users: SearchResult[];
  // All results flattened
  allResults: SearchResult[];
  // Has any results
  hasResults: boolean;
}

export function useGlobalSearch(
  options: UseGlobalSearchOptions = {}
): UseGlobalSearchReturn {
  const { debounceMs = 300, minQueryLength = 2 } = options;

  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  // Entity data from API
  const [elements, setElements] = useState<Element[]>([]);
  const [categories, setCategories] = useState<VehicleCategory[]>([]);
  const [tiers, setTiers] = useState<TariffTier[]>([]);
  const [users, setUsers] = useState<User[]>([]);

  // Debounce query
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(query);
    }, debounceMs);

    return () => clearTimeout(timer);
  }, [query, debounceMs]);

  // Fetch entities when query changes
  const fetchEntities = useCallback(async (searchQuery: string) => {
    if (searchQuery.length < minQueryLength) {
      setElements([]);
      setCategories([]);
      setTiers([]);
      setUsers([]);
      return;
    }

    setIsLoading(true);
    try {
      // Fetch all entities in parallel
      const [elementsRes, categoriesRes, tiersRes, usersRes] = await Promise.all(
        [
          api.getElements({ search: searchQuery, limit: 10 }),
          api.getVehicleCategories({ limit: 50 }),
          api.getTariffTiers({ search: searchQuery, limit: 10 }),
          api.getUsers({ search: searchQuery, limit: 10 }),
        ]
      );

      setElements(elementsRes.items || []);
      setCategories(categoriesRes.items || []);
      setTiers(tiersRes.items || []);
      setUsers(usersRes.items || []);
    } catch (error) {
      console.error("Error fetching search results:", error);
    } finally {
      setIsLoading(false);
    }
  }, [minQueryLength]);

  useEffect(() => {
    fetchEntities(debouncedQuery);
  }, [debouncedQuery, fetchEntities]);

  // Filter pages (local, no API needed)
  const filteredPages = useMemo((): SearchResult[] => {
    if (query.length < 1) {
      // Show all pages when no query
      return SEARCHABLE_PAGES.map((page) => ({
        id: `page-${page.href}`,
        type: "page" as const,
        title: page.title,
        icon: page.icon,
        href: page.href,
        keywords: page.keywords,
      }));
    }

    const lowerQuery = query.toLowerCase();
    return SEARCHABLE_PAGES.filter((page) => {
      const titleMatch = page.title.toLowerCase().includes(lowerQuery);
      const keywordMatch = page.keywords.some((k) =>
        k.toLowerCase().includes(lowerQuery)
      );
      return titleMatch || keywordMatch;
    }).map((page) => ({
      id: `page-${page.href}`,
      type: "page" as const,
      title: page.title,
      icon: page.icon,
      href: page.href,
      keywords: page.keywords,
    }));
  }, [query]);

  // Convert elements to SearchResult
  const elementResults = useMemo((): SearchResult[] => {
    return elements.map((el) => ({
      id: `element-${el.id}`,
      type: "element" as const,
      title: el.name,
      subtitle: el.code,
      icon: Package,
      href: `/elementos/${el.id}`,
      keywords: el.keywords,
    }));
  }, [elements]);

  // Filter categories locally (already fetched all)
  const categoryResults = useMemo((): SearchResult[] => {
    if (query.length < 1) return [];

    const lowerQuery = query.toLowerCase();
    return categories
      .filter((cat) => {
        const nameMatch = cat.name.toLowerCase().includes(lowerQuery);
        const slugMatch = cat.slug.toLowerCase().includes(lowerQuery);
        return nameMatch || slugMatch;
      })
      .slice(0, 10)
      .map((cat) => ({
        id: `category-${cat.id}`,
        type: "category" as const,
        title: cat.name,
        subtitle: cat.client_type === "particular" ? "Particular" : "Profesional",
        icon: Car,
        href: `/reformas/${cat.id}`,
      }));
  }, [categories, query]);

  // Convert tiers to SearchResult
  const tierResults = useMemo((): SearchResult[] => {
    return tiers.map((tier) => ({
      id: `tier-${tier.id}`,
      type: "tier" as const,
      title: tier.name,
      subtitle: `${tier.code} - ${tier.price.toFixed(2)}€`,
      icon: Car,
      href: `/reformas/${tier.category_id}?tier=${tier.id}`,
    }));
  }, [tiers]);

  // Convert users to SearchResult
  const userResults = useMemo((): SearchResult[] => {
    return users.map((user) => {
      const name =
        user.first_name || user.last_name
          ? `${user.first_name || ""} ${user.last_name || ""}`.trim()
          : user.phone;
      return {
        id: `user-${user.id}`,
        type: "user" as const,
        title: name,
        subtitle: user.phone,
        icon: Users,
        href: `/users/${user.id}`,
      };
    });
  }, [users]);

  // All results combined
  const allResults = useMemo(() => {
    return [
      ...filteredPages,
      ...elementResults,
      ...categoryResults,
      ...tierResults,
      ...userResults,
    ];
  }, [filteredPages, elementResults, categoryResults, tierResults, userResults]);

  const hasResults = allResults.length > 0;

  return {
    query,
    setQuery,
    isLoading,
    pages: filteredPages,
    elements: elementResults,
    categories: categoryResults,
    tiers: tierResults,
    users: userResults,
    allResults,
    hasResults,
  };
}
