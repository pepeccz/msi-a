"use client";

import { useEffect, useState, useMemo } from "react";
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
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"; // For create dialog only
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Package,
  Search,
  Plus,
  Edit,
  Trash2,
  ChevronDown,
  Image as ImageIcon,
} from "lucide-react";
import api from "@/lib/api";
import type { Element, ElementWithImages, VehicleCategory, ElementCreate, ElementUpdate } from "@/lib/types";
import ElementForm from "@/components/elements/element-form";

interface ElementsState {
  items: Element[];
  total: number;
  skip: number;
  limit: number;
}

export default function ElementosPage() {
  const [elements, setElements] = useState<ElementsState>({
    items: [],
    total: 0,
    skip: 0,
    limit: 20,
  });
  const [categories, setCategories] = useState<VehicleCategory[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [deletingElement, setDeletingElement] = useState<Element | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

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

  // Fetch elements when filters or page changes
  useEffect(() => {
    async function fetchElements() {
      // category_id is required by the API
      if (!selectedCategory) {
        setIsLoading(false);
        return;
      }

      try {
        setIsLoading(true);
        const skip = (currentPage - 1) * elements.limit;

        const data = await api.getElements({
          skip,
          limit: elements.limit,
          category_id: selectedCategory,
        });
        setElements(data);
      } catch (error) {
        console.error("Error fetching elements:", error);
      } finally {
        setIsLoading(false);
      }
    }

    fetchElements();
  }, [selectedCategory, currentPage, elements.limit]);

  // Filter elements by search query (client-side)
  const filteredElements = useMemo(() => {
    if (!searchQuery.trim()) return elements.items;

    const query = searchQuery.toLowerCase();
    return elements.items.filter(
      (element) =>
        element.code.toLowerCase().includes(query) ||
        element.name.toLowerCase().includes(query) ||
        element.keywords.some((kw) => kw.toLowerCase().includes(query))
    );
  }, [elements.items, searchQuery]);

  // Handle create
  const handleCreate = async (data: ElementCreate | ElementUpdate) => {
    if (!selectedCategory) return;

    try {
      setIsSubmitting(true);
      await api.createElement(data as ElementCreate);
      setIsCreateDialogOpen(false);
      setSearchQuery("");
      setCurrentPage(1);

      // Refetch elements
      const result = await api.getElements({
        skip: 0,
        limit: elements.limit,
        category_id: selectedCategory,
      });
      setElements(result);
    } catch (error) {
      console.error("Error creating element:", error);
      alert("Error al crear elemento: " + (error instanceof Error ? error.message : "Desconocido"));
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

      // Refetch elements
      const skip = (currentPage - 1) * elements.limit;
      const result = await api.getElements({
        skip,
        limit: elements.limit,
        category_id: selectedCategory,
      });
      setElements(result);
    } catch (error) {
      console.error("Error deleting element:", error);
      alert("Error al eliminar elemento: " + (error instanceof Error ? error.message : "Desconocido"));
    } finally {
      setIsSubmitting(false);
    }
  };

  const totalPages = Math.ceil(elements.total / elements.limit);
  const categoryName = categories.find((c) => c.id === selectedCategory)?.name || "Todas";

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            Elementos Homologables
          </h1>
          <p className="text-muted-foreground">
            Gestiona el catálogo de elementos que los clientes pueden homologar
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Package className="h-5 w-5 text-muted-foreground" />
        </div>
      </div>

      {/* Main Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Elementos ({elements.total})</CardTitle>
              <CardDescription>
                Mostrando {filteredElements.length} de {elements.total} elementos
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
          <div className="flex gap-4">
            <div className="flex-1">
              <div className="relative">
                <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Buscar por código, nombre o keywords..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-8"
                />
              </div>
            </div>

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
          </div>

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
              <div className="border rounded-lg overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/50">
                      <TableHead className="w-[120px]">Código</TableHead>
                      <TableHead>Nombre</TableHead>
                      <TableHead className="w-[150px]">Categoría</TableHead>
                      <TableHead className="w-[80px] text-center">Imágenes</TableHead>
                      <TableHead className="w-[80px]">Estado</TableHead>
                      <TableHead className="w-[100px] text-right">Acciones</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredElements.map((element) => (
                      <TableRow key={element.id} className="hover:bg-muted/50 transition-colors">
                        <TableCell className="font-mono text-sm">{element.code}</TableCell>
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
                        <TableCell className="text-center text-sm text-muted-foreground">
                          {/* Will show image count after images are implemented */}
                          —
                        </TableCell>
                        <TableCell>
                          <Badge variant={element.is_active ? "default" : "secondary"}>
                            {element.is_active ? "Activo" : "Inactivo"}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-2">
                            <Link href={`/elementos/${element.id}`}>
                              <Button
                                variant="outline"
                                size="sm"
                                className="gap-1"
                              >
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
    </div>
  );
}
