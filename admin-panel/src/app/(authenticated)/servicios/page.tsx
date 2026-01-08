"use client";

import { useEffect, useState } from "react";
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Plus,
  Search,
  Edit,
  Trash2,
  DollarSign,
  Globe,
  Car,
} from "lucide-react";
import api from "@/lib/api";
import type { AdditionalService, VehicleCategory } from "@/lib/types";

export default function ServiciosPage() {
  const [services, setServices] = useState<AdditionalService[]>([]);
  const [categories, setCategories] = useState<VehicleCategory[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");

  // Dialog states
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [editingService, setEditingService] = useState<AdditionalService | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Delete dialog
  const [deleteService, setDeleteService] = useState<AdditionalService | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // Form state
  const [editForm, setEditForm] = useState({
    code: "",
    name: "",
    description: "",
    price: 0,
    is_active: true,
    sort_order: 0,
    category_id: null as string | null,
  });

  useEffect(() => {
    async function fetchData() {
      try {
        const [servicesData, categoriesData] = await Promise.all([
          api.getAdditionalServices({ limit: 100 }),
          api.getVehicleCategories({ limit: 50 }),
        ]);
        setServices(servicesData.items);
        setCategories(categoriesData.items);
      } catch (error) {
        console.error("Error fetching data:", error);
      } finally {
        setIsLoading(false);
      }
    }
    fetchData();
  }, []);

  const fetchServices = async () => {
    try {
      const servicesData = await api.getAdditionalServices({ limit: 100 });
      setServices(servicesData.items);
    } catch (error) {
      console.error("Error fetching services:", error);
    }
  };

  const openCreateDialog = () => {
    setEditingService(null);
    setEditForm({
      code: "",
      name: "",
      description: "",
      price: 0,
      is_active: true,
      sort_order: 0,
      category_id: null,
    });
    setIsEditDialogOpen(true);
  };

  const openEditDialog = (service: AdditionalService) => {
    setEditingService(service);
    setEditForm({
      code: service.code,
      name: service.name,
      description: service.description || "",
      price: service.price,
      is_active: service.is_active,
      sort_order: service.sort_order,
      category_id: service.category_id,
    });
    setIsEditDialogOpen(true);
  };

  const handleSave = async () => {
    try {
      setIsSaving(true);

      if (editingService) {
        // Update - exclude code since it shouldn't be changed
        const { code, ...updateData } = editForm;
        await api.updateAdditionalService(editingService.id, updateData);
      } else {
        // Create
        await api.createAdditionalService(editForm);
      }

      setIsEditDialogOpen(false);
      await fetchServices();
    } catch (error) {
      console.error("Error saving service:", error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteService) return;

    try {
      setIsDeleting(true);
      await api.deleteAdditionalService(deleteService.id);
      setDeleteService(null);
      await fetchServices();
    } catch (error) {
      console.error("Error deleting service:", error);
    } finally {
      setIsDeleting(false);
    }
  };

  const filteredServices = services.filter((service) => {
    const search = searchQuery.toLowerCase();
    return (
      service.name.toLowerCase().includes(search) ||
      service.code.toLowerCase().includes(search) ||
      service.description?.toLowerCase().includes(search)
    );
  });

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat("es-ES", {
      style: "currency",
      currency: "EUR",
    }).format(price);
  };

  const getCategoryName = (categoryId: string | null) => {
    if (!categoryId) return null;
    return categories.find((c) => c.id === categoryId)?.name || "Desconocido";
  };

  // Separate global and category-specific services
  const globalServices = filteredServices.filter((s) => !s.category_id);
  const categoryServices = filteredServices.filter((s) => s.category_id);

  // Group category services by category
  const servicesByCategory = categoryServices.reduce((acc, service) => {
    const categoryName = getCategoryName(service.category_id) || "Sin Categoria";
    if (!acc[categoryName]) acc[categoryName] = [];
    acc[categoryName].push(service);
    return acc;
  }, {} as Record<string, AdditionalService[]>);

  // Calculate totals
  const totalRevenuePotential = services.reduce((sum, s) => sum + s.price, 0);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            Servicios Adicionales
          </h1>
          <p className="text-muted-foreground">
            Gestiona los servicios extra disponibles para homologaciones
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Plus className="h-5 w-5 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">
            {services.length} servicios
          </span>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <Globe className="h-4 w-4" />
              Servicios Globales
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{globalServices.length}</div>
            <p className="text-xs text-muted-foreground">
              Disponibles para todas las categorias
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <Car className="h-4 w-4" />
              Servicios por Categoria
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{categoryServices.length}</div>
            <p className="text-xs text-muted-foreground">
              Especificos de cada categoria
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <DollarSign className="h-4 w-4" />
              Precio Medio
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {formatPrice(
                services.length > 0 ? totalRevenuePotential / services.length : 0
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              Por servicio adicional
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Search and Add */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Lista de Servicios</CardTitle>
              <CardDescription>
                Certificados de taller, urgencias, ensayos adicionales y mas
              </CardDescription>
            </div>
            <Button onClick={openCreateDialog}>
              <Plus className="h-4 w-4 mr-2" />
              Nuevo Servicio
            </Button>
          </div>
          <div className="relative mt-4">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Buscar servicios..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-pulse text-muted-foreground">
                Cargando servicios...
              </div>
            </div>
          ) : filteredServices.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <Plus className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <p className="text-muted-foreground">
                {searchQuery
                  ? "No se encontraron servicios con esos criterios"
                  : "No hay servicios adicionales registrados"}
              </p>
            </div>
          ) : (
            <div className="space-y-8">
              {/* Global Services */}
              {globalServices.length > 0 && (
                <div>
                  <h3 className="font-semibold text-lg mb-3 flex items-center gap-2">
                    <Globe className="h-5 w-5" />
                    Servicios Globales
                    <Badge variant="secondary">{globalServices.length}</Badge>
                  </h3>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-40">Codigo</TableHead>
                        <TableHead>Nombre</TableHead>
                        <TableHead>Descripcion</TableHead>
                        <TableHead className="text-right">Precio</TableHead>
                        <TableHead className="w-24 text-center">Estado</TableHead>
                        <TableHead className="w-24">Acciones</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {globalServices
                        .sort((a, b) => a.sort_order - b.sort_order)
                        .map((service) => (
                          <TableRow key={service.id}>
                            <TableCell>
                              <code className="text-xs bg-muted px-2 py-1 rounded">
                                {service.code}
                              </code>
                            </TableCell>
                            <TableCell className="font-medium">
                              {service.name}
                            </TableCell>
                            <TableCell className="text-muted-foreground text-sm max-w-md truncate">
                              {service.description || "-"}
                            </TableCell>
                            <TableCell className="text-right font-semibold">
                              {formatPrice(service.price)}
                            </TableCell>
                            <TableCell className="text-center">
                              <Badge
                                variant={service.is_active ? "default" : "secondary"}
                              >
                                {service.is_active ? "Activo" : "Inactivo"}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              <div className="flex items-center gap-1">
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  onClick={() => openEditDialog(service)}
                                >
                                  <Edit className="h-4 w-4" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  onClick={() => setDeleteService(service)}
                                >
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              </div>
                            </TableCell>
                          </TableRow>
                        ))}
                    </TableBody>
                  </Table>
                </div>
              )}

              {/* Category-specific Services */}
              {Object.entries(servicesByCategory).map(
                ([categoryName, catServices]) => (
                  <div key={categoryName}>
                    <h3 className="font-semibold text-lg mb-3 flex items-center gap-2">
                      <Car className="h-5 w-5" />
                      {categoryName}
                      <Badge variant="secondary">{catServices.length}</Badge>
                    </h3>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-40">Codigo</TableHead>
                          <TableHead>Nombre</TableHead>
                          <TableHead>Descripcion</TableHead>
                          <TableHead className="text-right">Precio</TableHead>
                          <TableHead className="w-24 text-center">Estado</TableHead>
                          <TableHead className="w-24">Acciones</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {catServices
                          .sort((a, b) => a.sort_order - b.sort_order)
                          .map((service) => (
                            <TableRow key={service.id}>
                              <TableCell>
                                <code className="text-xs bg-muted px-2 py-1 rounded">
                                  {service.code}
                                </code>
                              </TableCell>
                              <TableCell className="font-medium">
                                {service.name}
                              </TableCell>
                              <TableCell className="text-muted-foreground text-sm max-w-md truncate">
                                {service.description || "-"}
                              </TableCell>
                              <TableCell className="text-right font-semibold">
                                {formatPrice(service.price)}
                              </TableCell>
                              <TableCell className="text-center">
                                <Badge
                                  variant={
                                    service.is_active ? "default" : "secondary"
                                  }
                                >
                                  {service.is_active ? "Activo" : "Inactivo"}
                                </Badge>
                              </TableCell>
                              <TableCell>
                                <div className="flex items-center gap-1">
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={() => openEditDialog(service)}
                                  >
                                    <Edit className="h-4 w-4" />
                                  </Button>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={() => setDeleteService(service)}
                                  >
                                    <Trash2 className="h-4 w-4" />
                                  </Button>
                                </div>
                              </TableCell>
                            </TableRow>
                          ))}
                      </TableBody>
                    </Table>
                  </div>
                )
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Edit/Create Dialog */}
      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {editingService ? "Editar Servicio" : "Nuevo Servicio"}
            </DialogTitle>
            <DialogDescription>
              {editingService
                ? "Modifica los datos del servicio adicional"
                : "Crea un nuevo servicio adicional"}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {/* Selector de Categoría */}
            <div>
              <Label htmlFor="category">Categoria</Label>
              <Select
                value={editForm.category_id || "global"}
                onValueChange={(value) =>
                  setEditForm({
                    ...editForm,
                    category_id: value === "global" ? null : value,
                  })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="global">
                    Global (todas las categorias)
                  </SelectItem>
                  {categories.map((cat) => (
                    <SelectItem key={cat.id} value={cat.id}>
                      {cat.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Código */}
            <div>
              <Label htmlFor="code">Codigo</Label>
              <Input
                id="code"
                value={editForm.code}
                onChange={(e) =>
                  setEditForm({ ...editForm, code: e.target.value })
                }
                placeholder="certificado_taller"
                disabled={!!editingService}
              />
              {editingService && (
                <p className="text-xs text-muted-foreground mt-1">
                  El codigo no se puede modificar una vez creado
                </p>
              )}
            </div>

            {/* Nombre */}
            <div>
              <Label htmlFor="name">Nombre</Label>
              <Input
                id="name"
                value={editForm.name}
                onChange={(e) =>
                  setEditForm({ ...editForm, name: e.target.value })
                }
                placeholder="Certificado de Taller"
              />
            </div>

            {/* Descripción */}
            <div>
              <Label htmlFor="description">Descripcion</Label>
              <Textarea
                id="description"
                value={editForm.description}
                onChange={(e) =>
                  setEditForm({ ...editForm, description: e.target.value })
                }
                rows={3}
                placeholder="Descripcion del servicio..."
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              {/* Precio */}
              <div>
                <Label htmlFor="price">Precio (EUR)</Label>
                <Input
                  id="price"
                  type="number"
                  step="0.01"
                  min="0"
                  value={editForm.price}
                  onChange={(e) =>
                    setEditForm({
                      ...editForm,
                      price: parseFloat(e.target.value) || 0,
                    })
                  }
                />
              </div>

              {/* Orden */}
              <div>
                <Label htmlFor="sort_order">Orden</Label>
                <Input
                  id="sort_order"
                  type="number"
                  value={editForm.sort_order}
                  onChange={(e) =>
                    setEditForm({
                      ...editForm,
                      sort_order: parseInt(e.target.value) || 0,
                    })
                  }
                />
              </div>
            </div>

            {/* Estado Activo */}
            <div className="flex items-center space-x-2">
              <Switch
                id="is_active"
                checked={editForm.is_active}
                onCheckedChange={(checked) =>
                  setEditForm({ ...editForm, is_active: checked })
                }
              />
              <Label htmlFor="is_active">Servicio activo</Label>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsEditDialogOpen(false)}
              disabled={isSaving}
            >
              Cancelar
            </Button>
            <Button
              onClick={handleSave}
              disabled={isSaving || !editForm.code.trim() || !editForm.name.trim()}
            >
              {isSaving ? "Guardando..." : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog
        open={!!deleteService}
        onOpenChange={() => setDeleteService(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Eliminar servicio?</AlertDialogTitle>
            <AlertDialogDescription>
              Estas a punto de eliminar el servicio:{" "}
              <strong>{deleteService?.name}</strong>
              <br />
              Esta accion no se puede deshacer.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              disabled={isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? "Eliminando..." : "Eliminar"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
