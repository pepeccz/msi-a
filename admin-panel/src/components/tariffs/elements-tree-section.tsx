"use client";

import { useState, useMemo, useCallback, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Layers,
  Plus,
  Trash2,
  ImageIcon,
  AlertTriangle,
  ChevronRight,
  ChevronDown,
  Search,
} from "lucide-react";
import type { Element } from "@/lib/types";
import type { ElementTreeNode } from "@/hooks/use-category-elements";

interface ElementsTreeSectionProps {
  elements: Element[];
  elementTree: ElementTreeNode[];
  isLoading: boolean;
  onCreateElement: () => void;
  onDeleteElement: (element: Element) => void;
}

export function ElementsTreeSection({
  elements,
  elementTree,
  isLoading,
  onCreateElement,
  onDeleteElement,
}: ElementsTreeSectionProps) {
  const router = useRouter();
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  // Debounce search input
  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    debounceRef.current = setTimeout(() => {
      setDebouncedQuery(searchQuery);
    }, 300);
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [searchQuery]);

  // Filter tree based on search query
  const filteredTree = useMemo(() => {
    if (!debouncedQuery.trim()) return elementTree;

    const query = debouncedQuery.toLowerCase().trim();

    return elementTree
      .map((parent) => {
        const parentMatches =
          parent.code.toLowerCase().includes(query) ||
          parent.name.toLowerCase().includes(query) ||
          parent.keywords?.some((k) => k.toLowerCase().includes(query));

        const matchingChildren = parent.children.filter(
          (child) =>
            child.code.toLowerCase().includes(query) ||
            child.name.toLowerCase().includes(query) ||
            child.keywords?.some((k) => k.toLowerCase().includes(query))
        );

        if (parentMatches || matchingChildren.length > 0) {
          return {
            ...parent,
            children: parentMatches ? parent.children : matchingChildren,
            _autoExpand: matchingChildren.length > 0,
          };
        }
        return null;
      })
      .filter(Boolean) as (ElementTreeNode & { _autoExpand?: boolean })[];
  }, [elementTree, debouncedQuery]);

  // Determine which nodes should be expanded (manual + auto from search)
  const isExpanded = useCallback(
    (nodeId: string) => {
      if (debouncedQuery.trim()) {
        const node = filteredTree.find((n) => n.id === nodeId);
        return node?._autoExpand || expandedIds.has(nodeId);
      }
      return expandedIds.has(nodeId);
    },
    [expandedIds, debouncedQuery, filteredTree]
  );

  const toggleExpanded = (nodeId: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  };

  // Check if an element matches the search (for highlighting)
  const matchesSearch = useCallback(
    (element: Element) => {
      if (!debouncedQuery.trim()) return false;
      const query = debouncedQuery.toLowerCase().trim();
      return (
        element.code.toLowerCase().includes(query) ||
        element.name.toLowerCase().includes(query) ||
        element.keywords?.some((k) => k.toLowerCase().includes(query))
      );
    },
    [debouncedQuery]
  );

  const renderElementRow = (
    element: Element,
    isChild: boolean = false,
    isLastChild: boolean = false,
    parentHasChildren: boolean = false
  ) => {
    const hasChildren = !isChild && (element as ElementTreeNode).children?.length > 0;
    const childCount = (element as ElementTreeNode).children?.length || element.child_count || 0;
    const expanded = isExpanded(element.id);
    const highlighted = debouncedQuery.trim() && matchesSearch(element);

    return (
      <TableRow
        key={element.id}
        className={`${highlighted ? "bg-yellow-50 dark:bg-yellow-950/20" : ""} ${
          isChild ? "border-l-0" : ""
        }`}
      >
        {/* Código + child count badge */}
        <TableCell className={isChild ? "pl-2" : ""}>
          <div className="flex items-center gap-2">
            {isChild ? (
              <div className="flex items-center">
                <div className="w-6 border-l-2 border-b-2 border-muted-foreground/20 h-4 -mt-2 ml-2 rounded-bl-sm" />
              </div>
            ) : hasChildren ? (
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 p-0"
                onClick={() => toggleExpanded(element.id)}
              >
                {expanded ? (
                  <ChevronDown className="h-4 w-4" />
                ) : (
                  <ChevronRight className="h-4 w-4" />
                )}
              </Button>
            ) : (
              <div className="w-6" />
            )}
            <code className="text-xs bg-muted px-2 py-1 rounded font-mono">
              {element.code}
            </code>
            {!isChild && childCount > 0 && (
              <Badge variant="secondary" className="text-xs px-1.5 py-0 h-5">
                {childCount}
              </Badge>
            )}
          </div>
        </TableCell>

        {/* Nombre */}
        <TableCell>
          <div className={isChild ? "pl-4" : ""}>
            <div className="font-medium">{element.name}</div>
            {element.description && (
              <div className="text-xs text-muted-foreground truncate max-w-xs">
                {element.description}
              </div>
            )}
          </div>
        </TableCell>

        {/* Keywords */}
        <TableCell>
          <div className="flex flex-wrap gap-1">
            {element.keywords?.slice(0, 3).map((keyword) => (
              <Badge key={keyword} variant="outline" className="text-xs">
                {keyword}
              </Badge>
            ))}
            {element.keywords?.length > 3 && (
              <Badge variant="outline" className="text-xs">
                +{element.keywords.length - 3}
              </Badge>
            )}
          </div>
        </TableCell>

        {/* Estado */}
        <TableCell className="text-center">
          <Badge variant={element.is_active ? "default" : "secondary"}>
            {element.is_active ? "Activo" : "Inactivo"}
          </Badge>
        </TableCell>

        {/* Acciones */}
        <TableCell>
          <div className="flex items-center gap-3">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex items-center gap-1 text-sm text-muted-foreground">
                    <ImageIcon className="h-4 w-4" />
                    <span>{element.image_count ?? 0}</span>
                  </div>
                </TooltipTrigger>
                <TooltipContent>
                  <p>{element.image_count ?? 0} imagenes</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>

            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex items-center gap-1 text-sm text-muted-foreground">
                    <AlertTriangle className="h-4 w-4" />
                    <span>{element.warning_count ?? 0}</span>
                  </div>
                </TooltipTrigger>
                <TooltipContent>
                  <p>{element.warning_count ?? 0} advertencias</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>

            <Button
              size="sm"
              variant="outline"
              onClick={() => router.push(`/elementos/${element.id}`)}
            >
              Gestionar
            </Button>

            <Button
              size="icon"
              variant="ghost"
              className="h-8 w-8"
              onClick={() => onDeleteElement(element)}
            >
              <Trash2 className="h-4 w-4 text-destructive" />
            </Button>
          </div>
        </TableCell>
      </TableRow>
    );
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Layers className="h-5 w-5" />
              Elementos de la Categoria
            </CardTitle>
            <CardDescription>
              Elementos que pueden incluirse en las tarifas de homologacion
            </CardDescription>
          </div>
          <Button onClick={onCreateElement}>
            <Plus className="h-4 w-4 mr-2" />
            Nuevo Elemento
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <div className="text-muted-foreground">Cargando elementos...</div>
          </div>
        ) : elements.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <Layers className="h-12 w-12 text-muted-foreground/50 mb-4" />
            <p className="text-muted-foreground mb-4">
              No hay elementos configurados
            </p>
            <Button onClick={onCreateElement}>
              <Plus className="h-4 w-4 mr-2" />
              Nuevo Elemento
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Search input */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Buscar por nombre, codigo o keywords..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
              />
            </div>

            {/* Results info when searching */}
            {debouncedQuery.trim() && (
              <div className="text-sm text-muted-foreground">
                {filteredTree.length === 0
                  ? "Sin resultados"
                  : `${filteredTree.length} elemento${filteredTree.length !== 1 ? "s" : ""} encontrado${filteredTree.length !== 1 ? "s" : ""}`}
              </div>
            )}

            {/* Tree table */}
            {filteredTree.length > 0 && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-48">Codigo</TableHead>
                    <TableHead>Nombre</TableHead>
                    <TableHead>Keywords</TableHead>
                    <TableHead className="w-20 text-center">Estado</TableHead>
                    <TableHead className="w-56">Acciones</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredTree.flatMap((parent) => {
                    const expanded = isExpanded(parent.id);
                    const rows = [renderElementRow(parent, false)];

                    if (expanded && parent.children.length > 0) {
                      parent.children.forEach((child, idx) => {
                        rows.push(
                          renderElementRow(
                            child,
                            true,
                            idx === parent.children.length - 1,
                            true
                          )
                        );
                      });
                    }

                    return rows;
                  })}
                </TableBody>
              </Table>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
