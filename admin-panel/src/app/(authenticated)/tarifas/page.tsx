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
  Car,
  Search,
  Plus,
  Edit,
  Eye,
  ChevronRight,
  User,
  Briefcase,
} from "lucide-react";
import api from "@/lib/api";
import type { VehicleCategory, TariffTier, ClientType } from "@/lib/types";
import { CategoryFormDialog } from "@/components/categories/CategoryFormDialog";

interface CategoryWithTiers extends VehicleCategory {
  tariff_tiers?: TariffTier[];
}

export default function TarifasPage() {
  const [categories, setCategories] = useState<CategoryWithTiers[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [categoryDialogOpen, setCategoryDialogOpen] = useState(false);
  const [editingCategory, setEditingCategory] = useState<VehicleCategory | undefined>(undefined);

  const fetchCategories = async () => {
    try {
      const data = await api.getVehicleCategories({ limit: 50 });
      // Fetch tiers for each category
      const categoriesWithTiers = await Promise.all(
        data.items.map(async (category) => {
          try {
            const fullCategory = await api.getVehicleCategory(category.id);
            return {
              ...category,
              tariff_tiers: fullCategory.tariff_tiers,
            };
          } catch {
            return category;
          }
        })
      );
      setCategories(categoriesWithTiers);
    } catch (error) {
      console.error("Error fetching categories:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreateCategory = () => {
    setEditingCategory(undefined);
    setCategoryDialogOpen(true);
  };

  const handleEditCategory = (category: VehicleCategory) => {
    setEditingCategory(category);
    setCategoryDialogOpen(true);
  };

  const handleCategorySuccess = () => {
    fetchCategories();
  };

  useEffect(() => {
    fetchCategories();
  }, []);

  const filteredCategories = categories.filter((category) => {
    const search = searchQuery.toLowerCase();
    return (
      category.name.toLowerCase().includes(search) ||
      category.slug.toLowerCase().includes(search) ||
      category.description?.toLowerCase().includes(search)
    );
  });

  // Group categories by client_type
  const categoriesByType = useMemo(() => {
    const grouped: Record<ClientType, CategoryWithTiers[]> = {
      particular: [],
      professional: [],
    };
    filteredCategories.forEach((category) => {
      const type = category.client_type || "particular";
      if (grouped[type]) {
        grouped[type].push(category);
      }
    });
    return grouped;
  }, [filteredCategories]);

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat("es-ES", {
      style: "currency",
      currency: "EUR",
    }).format(price);
  };

  const clientTypeLabels: Record<ClientType, { label: string; icon: typeof User }> = {
    particular: { label: "Particulares", icon: User },
    professional: { label: "Profesionales", icon: Briefcase },
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            Tarifas de Homologacion
          </h1>
          <p className="text-muted-foreground">
            Gestiona las categorias de vehiculos y sus tarifas
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Car className="h-5 w-5 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">
            {categories.length} categorias
          </span>
        </div>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Categorias de Vehiculos</CardTitle>
              <CardDescription>
                Cada categoria tiene sus propias tarifas y elementos homologables
              </CardDescription>
            </div>
            <Button onClick={handleCreateCategory}>
              <Plus className="h-4 w-4 mr-2" />
              Nueva Categoria
            </Button>
          </div>
          <div className="relative mt-4">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Buscar categorias..."
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
                Cargando categorias...
              </div>
            </div>
          ) : filteredCategories.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <Car className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <p className="text-muted-foreground">
                {searchQuery
                  ? "No se encontraron categorias con esos criterios"
                  : "No hay categorias registradas. Ejecuta el seed para cargar los datos iniciales."}
              </p>
            </div>
          ) : (
            <div className="space-y-8">
              {(["particular", "professional"] as const).map((clientType) => {
                const typeCategories = categoriesByType[clientType];
                if (typeCategories.length === 0) return null;

                const { label, icon: TypeIcon } = clientTypeLabels[clientType];

                return (
                  <div key={clientType} className="space-y-4">
                    <div className="flex items-center gap-2 border-b pb-2">
                      <TypeIcon className="h-5 w-5 text-primary" />
                      <h2 className="text-xl font-semibold">{label}</h2>
                      <Badge variant="outline" className="ml-2">
                        {typeCategories.length} categoria{typeCategories.length !== 1 ? "s" : ""}
                      </Badge>
                    </div>

                    <div className="space-y-4">
                      {typeCategories.map((category) => (
                        <Card key={category.id} className="border-l-4 border-l-primary">
                          <CardHeader className="pb-3">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-3">
                                <div className="p-2 bg-primary/10 rounded-lg">
                                  <Car className="h-5 w-5 text-primary" />
                                </div>
                                <div>
                                  <CardTitle className="text-lg flex items-center gap-2">
                                    {category.name}
                                    <Badge
                                      variant={category.is_active ? "default" : "secondary"}
                                    >
                                      {category.is_active ? "Activo" : "Inactivo"}
                                    </Badge>
                                  </CardTitle>
                                  <CardDescription>
                                    Slug: <code className="text-xs">{category.slug}</code>
                                    {category.description && ` - ${category.description}`}
                                  </CardDescription>
                                </div>
                              </div>
                              <div className="flex items-center gap-2">
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => handleEditCategory(category)}
                                >
                                  <Edit className="h-4 w-4" />
                                </Button>
                                <Link href={`/tarifas/${category.id}`}>
                                  <Button variant="default" size="sm">
                                    <Eye className="h-4 w-4 mr-1" />
                                    Ver Detalles
                                    <ChevronRight className="h-4 w-4 ml-1" />
                                  </Button>
                                </Link>
                              </div>
                            </div>
                          </CardHeader>
                          <CardContent>
                            {category.tariff_tiers && category.tariff_tiers.length > 0 ? (
                              <Table>
                                <TableHeader>
                                  <TableRow>
                                    <TableHead className="w-24">Codigo</TableHead>
                                    <TableHead>Nombre</TableHead>
                                    <TableHead>Condiciones</TableHead>
                                    <TableHead className="text-right">Precio</TableHead>
                                    <TableHead className="w-24">Estado</TableHead>
                                  </TableRow>
                                </TableHeader>
                                <TableBody>
                                  {category.tariff_tiers
                                    .sort((a, b) => a.sort_order - b.sort_order)
                                    .map((tier) => (
                                      <TableRow key={tier.id}>
                                        <TableCell>
                                          <Badge variant="outline">{tier.code}</Badge>
                                        </TableCell>
                                        <TableCell className="font-medium">
                                          {tier.name}
                                        </TableCell>
                                        <TableCell className="text-muted-foreground text-sm max-w-md truncate">
                                          {tier.conditions || "-"}
                                        </TableCell>
                                        <TableCell className="text-right font-semibold">
                                          {formatPrice(tier.price)}
                                        </TableCell>
                                        <TableCell>
                                          <Badge
                                            variant={tier.is_active ? "default" : "secondary"}
                                          >
                                            {tier.is_active ? "Activo" : "Inactivo"}
                                          </Badge>
                                        </TableCell>
                                      </TableRow>
                                    ))}
                                </TableBody>
                              </Table>
                            ) : (
                              <p className="text-muted-foreground text-sm text-center py-4">
                                No hay tarifas configuradas para esta categoria
                              </p>
                            )}
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <CategoryFormDialog
        open={categoryDialogOpen}
        onOpenChange={setCategoryDialogOpen}
        category={editingCategory}
        onSuccess={handleCategorySuccess}
      />
    </div>
  );
}
