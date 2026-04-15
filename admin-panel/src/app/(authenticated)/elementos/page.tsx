"use client";

import { Fragment, useEffect, useState, useMemo } from "react";
import Link from "next/link";
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

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

import {
  Package,
  Plus,
  Edit,
  Trash2,
  ChevronDown,
  GitBranch,
  List,
  Network,
} from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { PageContainer } from "@/components/shared/page-container";
import { PageHeader } from "@/components/shared/page-header";
import { FilterBar } from "@/components/shared/filter-bar";
import api from "@/lib/api";
import type {
  Element,
  ElementWithChildren,
  VehicleCategory,
  ElementCreate,
  ElementUpdate,
} from "@/lib/types";
import { sileo } from "sileo";
import ElementForm from "@/components/elements/element-form";
import { cn } from "@/lib/utils";

type ViewMode = "flat" | "hierarchy";

interface ElementsState {
  items: Element[];
  total: number;
  skip: number;
  limit: number;
}

interface HierarchicalElementsState {
  items: ElementWithChildren[];
  total: number;
  skip: number;
  limit: number;
}

export default function ElementosPage() {
  const [elements, setElements] = useState<ElementsState>({
    items: [],
    total: 0,
    skip: 0,
    limit: 50,
  });
  const [hierarchicalElements, setHierarchicalElements] = useState<HierarchicalElementsState>({
    items: [],
    total: 0,
    skip: 0,
    limit: 50,
  });
  const [categories, setCategories] = useState<VehicleCategory[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [deletingElement, setDeletingElement] = useState<Element | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("hierarchy");
  const [expandedElements, setExpandedElements] = useState<Set<string>>(new Set());

  // Fetch categories on mount and auto-select first one
  useEffect(() => {
    async function fetchCategories() {
      try {
        const data = await api.getVehicleCategories({ limit: 100 });
        setCategories(data.items);
        // Auto-select first category if none selected
        if (data.items.length > 0 && !selectedCategory) {
          setSelectedCategory(data.items[0].id);
        }
      } catch (error) {
        console.error("Error fetching categories:", error);
      }
    }
    fetchCategories();
  }, [selectedCategory]);

  // Fetch elements when filters, page, or view mode changes
  useEffect(() => {
    async function fetchElements() {
      if (!selectedCategory) {
        setIsLoading(false);
        return;
      }

      try {
        setIsLoading(true);
        const skip = (currentPage - 1) * elements.limit;

        if (viewMode === "hierarchy") {
          const data = await api.getElementsWithChildren({
            skip,
            limit: elements.limit,
            category_id: selectedCategory,
          });
          setHierarchicalElements(data);
        } else {
          const data = await api.getElements({
            skip,
            limit: elements.limit,
            category_id: selectedCategory,
          });
          setElements(data);
        }
      } catch (error) {
        console.error("Error fetching elements:", error);
      } finally {
        setIsLoading(false);
      }
    }

    fetchElements();
  }, [selectedCategory, currentPage, elements.limit, viewMode]);

  // Filter elements by search query (client-side)
  const filteredElements = useMemo(() => {
    const items = viewMode === "hierarchy" ? hierarchicalElements.items : elements.items;
    if (!searchQuery.trim()) return items;

    const query = searchQuery.toLowerCase();
    return items.filter((element) => {
      const matchesElement =
        element.code.toLowerCase().includes(query) ||
        element.name.toLowerCase().includes(query) ||
        element.keywords.some((kw) => kw.toLowerCase().includes(query));

      // In hierarchy mode, also check children
      if (viewMode === "hierarchy" && "children" in element) {
        const matchesChildren = (element as ElementWithChildren).children?.some(
          (child) =>
            child.code.toLowerCase().includes(query) ||
            child.name.toLowerCase().includes(query) ||
            child.keywords.some((kw) => kw.toLowerCase().includes(query))
        );
        return matchesElement || matchesChildren;
      }

      return matchesElement;
    });
  }, [elements.items, hierarchicalElements.items, searchQuery, viewMode]);

  // Handle create
  const handleCreate = async (data: ElementCreate | ElementUpdate) => {
    if (!selectedCategory) return;

    try {
      setIsSubmitting(true);
      await api.createElement(data as ElementCreate);
      setIsCreateDialogOpen(false);
      setSearchQuery("");
      setCurrentPage(1);

      // Refetch elements based on view mode
      if (viewMode === "hierarchy") {
        const result = await api.getElementsWithChildren({
          skip: 0,
          limit: elements.limit,
          category_id: selectedCategory,
        });
        setHierarchicalElements(result);
      } else {
        const result = await api.getElements({
          skip: 0,
          limit: elements.limit,
          category_id: selectedCategory,
        });
        setElements(result);
      }
    } catch (error) {
      console.error("Error creating element:", error);
      sileo.error({ title: "Error al crear elemento", description: error instanceof Error ? error.message : "Desconocido" });
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle delete
  const handleDelete = async () => {
    if (!deletingElement || !selectedCategory) return;

    try {
      setIsSubmitting(true);
      await api.deleteElement(deletingElement.id);
      setDeletingElement(null);

      // Refetch elements based on view mode
      const skip = (currentPage - 1) * elements.limit;
      if (viewMode === "hierarchy") {
        const result = await api.getElementsWithChildren({
          skip,
          limit: elements.limit,
          category_id: selectedCategory,
        });
        setHierarchicalElements(result);
      } else {
        const result = await api.getElements({
          skip,
          limit: elements.limit,
          category_id: selectedCategory,
        });
        setElements(result);
      }
    } catch (error) {
      console.error("Error deleting element:", error);
      sileo.error({ title: "Error al eliminar elemento", description: error instanceof Error ? error.message : "Desconocido" });
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle toggle active/inactive
  const handleToggleActive = async (element: Element, newValue: boolean) => {
    try {
      await api.updateElement(element.id, { is_active: newValue });
      sileo.success({ title: newValue
          ? `Elemento "${element.name}" activado`
          : `Elemento "${element.name}" desactivado` });

      // Refetch elements based on view mode
      const skip = (currentPage - 1) * elements.limit;
      if (viewMode === "hierarchy") {
        const result = await api.getElementsWithChildren({
          skip,
          limit: elements.limit,
          category_id: selectedCategory!,
        });
        setHierarchicalElements(result);
      } else {
        const result = await api.getElements({
          skip,
          limit: elements.limit,
          category_id: selectedCategory!,
        });
        setElements(result);
      }
    } catch (error) {
      console.error("Error toggling element active state:", error);
      sileo.error({ title: "Error al cambiar el estado del elemento" });
    }
  };

  const currentTotal = viewMode === "hierarchy" ? hierarchicalElements.total : elements.total;
  const totalPages = Math.ceil(currentTotal / elements.limit);
  const categoryName = categories.find((c) => c.id === selectedCategory)?.name || "Todas";

  // Toggle expand/collapse for hierarchical elements
  const toggleExpanded = (elementId: string) => {
    setExpandedElements((prev) => {
      const next = new Set(prev);
      if (next.has(elementId)) {
        next.delete(elementId);
      } else {
        next.add(elementId);
      }
      return next;
    });
  };

  // Render hierarchical element row with valid HTML structure
  const renderHierarchicalRow = (element: ElementWithChildren) => {
    const hasChildren = element.children && element.children.length > 0;
    const isExpanded = expandedElements.has(element.id);

    return (
      <Fragment key={element.id}>
        {/* Parent row */}
        <TableRow 
          className={cn(
            "hover:bg-muted/50 transition-colors",
            hasChildren && "cursor-pointer"
          )}
          onClick={hasChildren ? () => toggleExpanded(element.id) : undefined}
        >
          <TableCell className="font-mono text-sm">
            <div className="flex items-center gap-2">
              {hasChildren ? (
                <ChevronDown 
                  className={cn(
                    "h-4 w-4 transition-transform duration-200 flex-shrink-0",
                    !isExpanded && "-rotate-90"
                  )}
                />
              ) : (
                <span className="w-4 flex-shrink-0" />
              )}
              <span>{element.code}</span>
              {hasChildren && (
                <Badge variant="outline" className="text-xs ml-2">
                  {element.children.length} variante{element.children.length !== 1 ? "s" : ""}
                </Badge>
              )}
            </div>
          </TableCell>
          <TableCell>
            <div>
              <p className="font-medium">{element.name}</p>
              {element.keywords.length > 0 && (
                <p className="text-xs text-muted-foreground mt-1">
                  Keywords: {element.keywords.slice(0, 2).join(", ")}
                  {element.keywords.length > 2 && ` +${element.keywords.length - 2}`}
                </p>
              )}
            </div>
          </TableCell>
          <TableCell className="text-sm">
            {categories.find((c) => c.id === element.category_id)?.name || "-"}
          </TableCell>
          <TableCell className="text-center text-sm text-muted-foreground">—</TableCell>
          <TableCell onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2">
              <Switch
                checked={element.is_active}
                onCheckedChange={(checked) => handleToggleActive(element, checked)}
              />
              <span className="text-xs text-muted-foreground">
                {element.is_active ? "Activo" : "Inactivo"}
              </span>
            </div>
          </TableCell>
          <TableCell className="text-right">
            <div className="flex justify-end gap-2" onClick={(e) => e.stopPropagation()}>
              <Link href={`/elementos/${element.id}`}>
                <Button variant="outline" size="sm" className="gap-1">
                  <Edit className="h-4 w-4" />
                  <span className="hidden sm:inline">Editar</span>
                </Button>
              </Link>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDeletingElement(element)}
                className="gap-1 text-destructive hover:text-destructive"
              >
                <Trash2 className="h-4 w-4" />
                <span className="hidden sm:inline">Eliminar</span>
              </Button>
            </div>
          </TableCell>
        </TableRow>

        {/* Children rows (only if expanded) */}
        {hasChildren && isExpanded && element.children.map((child) => (
          <TableRow 
            key={child.id} 
            className="hover:bg-muted/30 transition-colors bg-muted/10"
          >
            <TableCell className="font-mono text-sm">
              <div className="flex items-center gap-2 pl-8">
                <GitBranch className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                {child.variant_code && (
                  <Badge variant="secondary" className="text-xs">
                    {child.variant_code}
                  </Badge>
                )}
                <span>{child.code}</span>
              </div>
            </TableCell>
            <TableCell>
              <div className="pl-2">
                <p className="font-medium text-sm">{child.name}</p>
                {child.keywords.length > 0 && (
                  <p className="text-xs text-muted-foreground mt-1">
                    Keywords: {child.keywords.slice(0, 2).join(", ")}
                    {child.keywords.length > 2 && ` +${child.keywords.length - 2}`}
                  </p>
                )}
              </div>
            </TableCell>
            <TableCell className="text-sm">
              {categories.find((c) => c.id === child.category_id)?.name || "-"}
            </TableCell>
            <TableCell className="text-center text-sm text-muted-foreground">—</TableCell>
            <TableCell>
              <div className="flex items-center gap-2">
                <Switch
                  checked={child.is_active}
                  onCheckedChange={(checked) => handleToggleActive(child, checked)}
                />
                <span className="text-xs text-muted-foreground">
                  {child.is_active ? "Activo" : "Inactivo"}
                </span>
              </div>
            </TableCell>
            <TableCell className="text-right">
              <div className="flex justify-end gap-2">
                <Link href={`/elementos/${child.id}`}>
                  <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                    <Edit className="h-4 w-4" />
                  </Button>
                </Link>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 w-8 p-0 text-destructive hover:text-destructive"
                  onClick={() => setDeletingElement(child)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </TableCell>
          </TableRow>
        ))}
      </Fragment>
    );
  };

  return (
    <PageContainer className="space-y-6">
      <PageHeader
        title="Elementos Homologables"
        description="Gestiona el catálogo de elementos que los clientes pueden homologar"
      />

      {/* Main Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Elementos ({currentTotal})</CardTitle>
              <CardDescription>
                Mostrando {filteredElements.length} de {currentTotal} elementos
                {selectedCategory && ` en ${categoryName}`}
              </CardDescription>
            </div>
            <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
              <DialogTrigger asChild>
                <Button className="gap-2">
                  <Plus className="h-4 w-4" />
                  Nuevo Elemento
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle>Crear Nuevo Elemento</DialogTitle>
                  <DialogDescription>
                    Añade un nuevo elemento homologable a la base de datos
                  </DialogDescription>
                </DialogHeader>
                <ElementForm
                  categories={categories}
                  onSubmit={handleCreate}
                  isSubmitting={isSubmitting}
                  onCancel={() => setIsCreateDialogOpen(false)}
                />
              </DialogContent>
            </Dialog>
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          {/* Filters */}
          <FilterBar
            searchValue={searchQuery}
            onSearchChange={setSearchQuery}
            searchPlaceholder="Buscar por código, nombre o keywords..."
          >
            <Select value={selectedCategory || ""} onValueChange={setSelectedCategory}>
              <SelectTrigger className="w-[200px]">
                <SelectValue placeholder="Selecciona categoría" />
              </SelectTrigger>
              <SelectContent>
                {categories.map((category) => (
                  <SelectItem key={category.id} value={category.id}>
                    {category.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* View Mode Toggle */}
            <div className="flex border rounded-lg overflow-hidden">
              <Button
                variant={viewMode === "hierarchy" ? "default" : "ghost"}
                size="sm"
                onClick={() => setViewMode("hierarchy")}
                className="rounded-none gap-2"
              >
                <Network className="h-4 w-4" />
                Jerárquica
              </Button>
              <Button
                variant={viewMode === "flat" ? "default" : "ghost"}
                size="sm"
                onClick={() => setViewMode("flat")}
                className="rounded-none gap-2"
              >
                <List className="h-4 w-4" />
                Plana
              </Button>
            </div>
          </FilterBar>

          {/* Table */}
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="text-muted-foreground">Cargando elementos...</div>
            </div>
          ) : filteredElements.length === 0 ? (
            <div className="flex items-center justify-center py-8">
              <div className="text-center">
                <Package className="h-12 w-12 text-muted-foreground mx-auto mb-2 opacity-50" />
                <p className="text-muted-foreground">No hay elementos para mostrar</p>
                {searchQuery && (
                  <button
                    onClick={() => setSearchQuery("")}
                    className="text-sm text-primary hover:underline mt-2"
                  >
                    Limpiar búsqueda
                  </button>
                )}
              </div>
            </div>
          ) : (
            <>
              <div className="border rounded-lg overflow-hidden overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/50">
                      <TableHead className="w-[150px]">Código</TableHead>
                      <TableHead>Nombre</TableHead>
                      <TableHead className="w-[150px]">Categoría</TableHead>
                      <TableHead className="w-[80px] text-center">Imágenes</TableHead>
                      <TableHead className="w-[80px]">Estado</TableHead>
                      <TableHead className="w-[120px] text-right">Acciones</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {viewMode === "hierarchy"
                      ? (filteredElements as ElementWithChildren[]).map(renderHierarchicalRow)
                      : (filteredElements as Element[]).map((element) => (
                          <TableRow key={element.id} className="hover:bg-muted/50 transition-colors">
                            <TableCell className="font-mono text-sm">
                              <div className="flex items-center gap-2">
                                {element.parent_element_id && (
                                  <GitBranch className="h-4 w-4 text-muted-foreground" />
                                )}
                                {element.code}
                                {element.variant_code && (
                                  <Badge variant="secondary" className="text-xs">
                                    {element.variant_code}
                                  </Badge>
                                )}
                              </div>
                            </TableCell>
                            <TableCell>
                              <div>
                                <p className="font-medium">{element.name}</p>
                                {element.keywords.length > 0 && (
                                  <p className="text-xs text-muted-foreground mt-1">
                                    Keywords: {element.keywords.slice(0, 2).join(", ")}
                                    {element.keywords.length > 2 && ` +${element.keywords.length - 2}`}
                                  </p>
                                )}
                              </div>
                            </TableCell>
                            <TableCell className="text-sm">
                              {categories.find((c) => c.id === element.category_id)?.name || "-"}
                            </TableCell>
                            <TableCell className="text-center text-sm text-muted-foreground">—</TableCell>
                            <TableCell>
                              <div className="flex items-center gap-2">
                                <Switch
                                  checked={element.is_active}
                                  onCheckedChange={(checked) => handleToggleActive(element, checked)}
                                />
                                <span className="text-xs text-muted-foreground">
                                  {element.is_active ? "Activo" : "Inactivo"}
                                </span>
                              </div>
                            </TableCell>
                            <TableCell className="text-right">
                              <div className="flex justify-end gap-2">
                                <Link href={`/elementos/${element.id}`}>
                                  <Button variant="outline" size="sm" className="gap-1">
                                    <Edit className="h-4 w-4" />
                                    <span className="hidden sm:inline">Editar</span>
                                  </Button>
                                </Link>
                                <AlertDialog
                                  open={deletingElement?.id === element.id}
                                  onOpenChange={(open) => {
                                    if (!open) setDeletingElement(null);
                                  }}
                                >
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => setDeletingElement(element)}
                                    className="gap-1 text-destructive hover:text-destructive"
                                  >
                                    <Trash2 className="h-4 w-4" />
                                    <span className="hidden sm:inline">Eliminar</span>
                                  </Button>
                                  <AlertDialogContent>
                                    <AlertDialogHeader>
                                      <AlertDialogTitle>¿Eliminar elemento?</AlertDialogTitle>
                                      <AlertDialogDescription>
                                        ¿Está seguro de que desea eliminar el elemento "{element.name}"? Esta acción no se puede deshacer.
                                      </AlertDialogDescription>
                                    </AlertDialogHeader>
                                    <div className="flex gap-3 justify-end">
                                      <AlertDialogCancel>Cancelar</AlertDialogCancel>
                                      <AlertDialogAction
                                        onClick={handleDelete}
                                        disabled={isSubmitting}
                                        className="bg-destructive hover:bg-destructive/90"
                                      >
                                        {isSubmitting ? "Eliminando..." : "Eliminar"}
                                      </AlertDialogAction>
                                    </div>
                                  </AlertDialogContent>
                                </AlertDialog>
                              </div>
                            </TableCell>
                          </TableRow>
                        ))}
                  </TableBody>
                </Table>
              </div>

              {/* Delete Confirmation for Hierarchy View */}
              {viewMode === "hierarchy" && deletingElement && (
                <AlertDialog
                  open={!!deletingElement}
                  onOpenChange={(open) => {
                    if (!open) setDeletingElement(null);
                  }}
                >
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>¿Eliminar elemento?</AlertDialogTitle>
                      <AlertDialogDescription>
                        ¿Está seguro de que desea eliminar el elemento "{deletingElement.name}"?
                        {(deletingElement as ElementWithChildren).children?.length > 0 && (
                          <span className="block mt-2 text-destructive font-medium">
                            Este elemento tiene {(deletingElement as ElementWithChildren).children.length} variante(s) que también serán eliminadas.
                          </span>
                        )}
                        Esta acción no se puede deshacer.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <div className="flex gap-3 justify-end">
                      <AlertDialogCancel>Cancelar</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={handleDelete}
                        disabled={isSubmitting}
                        className="bg-destructive hover:bg-destructive/90"
                      >
                        {isSubmitting ? "Eliminando..." : "Eliminar"}
                      </AlertDialogAction>
                    </div>
                  </AlertDialogContent>
                </AlertDialog>
              )}

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between pt-4">
                  <div className="text-sm text-muted-foreground">
                    Página {currentPage} de {totalPages}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                      disabled={currentPage === 1}
                    >
                      Anterior
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                      disabled={currentPage === totalPages}
                    >
                      Siguiente
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </PageContainer>
  );
}
