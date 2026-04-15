"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import {
  Car,
  Plus,
  Edit,
  ChevronRight,
  User,
  Briefcase,
  Layers,
  Tag,
} from "lucide-react";
import { PageContainer } from "@/components/shared/page-container";
import { PageHeader } from "@/components/shared/page-header";
import { FilterBar } from "@/components/shared/filter-bar";
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

  const handleEditCategory = (e: React.MouseEvent, category: VehicleCategory) => {
    e.preventDefault();
    e.stopPropagation();
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

  const getPriceRange = (tiers?: TariffTier[]) => {
    if (!tiers || tiers.length === 0) return null;
    const activeTiers = tiers.filter((t) => t.is_active);
    if (activeTiers.length === 0) return null;
    const prices = activeTiers.map((t) => t.price);
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    if (min === max) return formatPrice(min);
    return `${formatPrice(min)} — ${formatPrice(max)}`;
  };

  const clientTypeLabels: Record<ClientType, { label: string; icon: typeof User }> = {
    particular: { label: "Particulares", icon: User },
    professional: { label: "Profesionales", icon: Briefcase },
  };

  return (
    <PageContainer className="space-y-6">
      <PageHeader
        title="Reformas de Homologacion"
        description="Gestiona las categorias de vehiculos y sus reformas"
        actions={
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground">
              {categories.length} categorias
            </span>
            <Button onClick={handleCreateCategory}>
              <Plus className="h-4 w-4 mr-2" />
              Nueva Categoria
            </Button>
          </div>
        }
      />

      <FilterBar
        searchValue={searchQuery}
        onSearchChange={setSearchQuery}
        searchPlaceholder="Buscar categorias..."
      />

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-pulse text-muted-foreground">
            Cargando categorias...
          </div>
        </div>
      ) : filteredCategories.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <Car className="h-12 w-12 text-muted-foreground/50 mb-4" />
          <p className="text-muted-foreground">
            {searchQuery
              ? "No se encontraron categorias con esos criterios"
              : "No hay categorias registradas. Ejecuta el seed para cargar los datos iniciales."}
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {(["particular", "professional"] as const).map((clientType) => {
            const typeCategories = categoriesByType[clientType];
            if (typeCategories.length === 0) return null;

            const { label, icon: TypeIcon } = clientTypeLabels[clientType];

            return (
              <div key={clientType} className="space-y-3">
                <div className="flex items-center gap-2">
                  <TypeIcon className="h-4 w-4 text-muted-foreground" />
                  <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
                    {label}
                  </h2>
                  <Badge variant="outline" className="text-xs">
                    {typeCategories.length}
                  </Badge>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {typeCategories.map((category) => {
                    const tierCount = category.tariff_tiers?.filter((t) => t.is_active).length ?? 0;
                    const priceRange = getPriceRange(category.tariff_tiers);

                    return (
                      <Link
                        key={category.id}
                        href={`/reformas/${category.id}`}
                        className="block group"
                      >
                        <Card className="h-full transition-all hover:shadow-md hover:border-primary/50 group-hover:bg-muted/30">
                          <CardHeader className="pb-2">
                            <div className="flex items-start justify-between">
                              <div className="flex items-center gap-2.5 min-w-0">
                                <span className="text-xl shrink-0">
                                  {category.icon || "🚗"}
                                </span>
                                <CardTitle className="text-base truncate">
                                  {category.name}
                                </CardTitle>
                              </div>
                              <div className="flex items-center gap-1 shrink-0 ml-2">
                                {!category.is_active && (
                                  <Badge variant="secondary" className="text-xs">
                                    Inactivo
                                  </Badge>
                                )}
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity"
                                  onClick={(e) => handleEditCategory(e, category)}
                                >
                                  <Edit className="h-3.5 w-3.5" />
                                </Button>
                                <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                              </div>
                            </div>
                          </CardHeader>
                          <CardContent className="pt-0">
                            {category.description && (
                              <p className="text-xs text-muted-foreground line-clamp-1 mb-3">
                                {category.description}
                              </p>
                            )}
                            <div className="flex items-center gap-4 text-xs text-muted-foreground">
                              <span className="flex items-center gap-1">
                                <Layers className="h-3.5 w-3.5" />
                                {tierCount} {tierCount === 1 ? "tier" : "tiers"}
                              </span>
                              {priceRange && (
                                <span className="flex items-center gap-1 font-medium text-foreground">
                                  <Tag className="h-3.5 w-3.5 text-muted-foreground" />
                                  {priceRange}
                                </span>
                              )}
                            </div>
                          </CardContent>
                        </Card>
                      </Link>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <CategoryFormDialog
        open={categoryDialogOpen}
        onOpenChange={setCategoryDialogOpen}
        category={editingCategory}
        onSuccess={handleCategorySuccess}
      />
    </PageContainer>
  );
}
