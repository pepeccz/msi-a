"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Package,
  Plus,
  Trash2,
  AlertCircle,
  Infinity,
  Check,
  Loader2,
} from "lucide-react";
import api from "@/lib/api";
import type {
  TariffTier,
  Element,
  TierElementInclusion,
  TierElementInclusionCreate,
  TierElementsPreview,
} from "@/lib/types";

interface TierInclusionEditorProps {
  tierId: string;
  categoryId: string;
  onUpdate?: () => void;
}

interface InclusionConfig {
  id: string;
  type: "element" | "tier";
  name: string;
  code?: string;
  currentMaxQuantity: number | null;
}

export function TierInclusionEditor({
  tierId,
  categoryId,
  onUpdate,
}: TierInclusionEditorProps) {
  const [elements, setElements] = useState<Element[]>([]);
  const [tiers, setTiers] = useState<TariffTier[]>([]);
  const [inclusions, setInclusions] = useState<TierElementInclusion[]>([]);
  const [preview, setPreview] = useState<TierElementsPreview | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Modal states
  const [isConfigDialogOpen, setIsConfigDialogOpen] = useState(false);
  const [configMode, setConfigMode] = useState<"add" | "edit">("add");
  const [selectedItem, setSelectedItem] = useState<InclusionConfig | null>(null);
  const [maxQuantity, setMaxQuantity] = useState<string>("");
  const [useUnlimited, setUseUnlimited] = useState(true);

  const [searchElements, setSearchElements] = useState("");
  const [searchTiers, setSearchTiers] = useState("");

  const [deletingInclusion, setDeletingInclusion] = useState<TierElementInclusion | null>(null);
  const [circularError, setCircularError] = useState<string>("");

  // Fetch data
  useEffect(() => {
    async function fetchData() {
      try {
        setIsLoading(true);
        const [elementsData, tiersData, inclusionsData, previewData] = await Promise.all([
          api.getElements({ category_id: categoryId, limit: 1000 }),
          api.getTariffTiers({ category_id: categoryId }),
          api.getTierInclusions(tierId),
          api.getTierResolvedElements(tierId),
        ]);

        setElements(elementsData.items);
        setTiers(tiersData.items.filter((t) => t.id !== tierId));
        setInclusions(inclusionsData);
        setPreview(previewData);
      } catch (error) {
        console.error("Error fetching data:", error);
      } finally {
        setIsLoading(false);
      }
    }

    fetchData();
  }, [tierId, categoryId]);

  // Check for circular references (simple DFS)
  const checkCircularReference = useCallback(
    (sourceId: string, targetId: string, isTargetTier: boolean): boolean => {
      if (!isTargetTier) return false;

      const visited = new Set<string>();
      const recursionStack = new Set<string>();

      function hasCycle(nodeId: string): boolean {
        visited.add(nodeId);
        recursionStack.add(nodeId);

        // Get inclusions from this tier
        const tierInclusions = inclusions.filter(
          (inc) => inc.tier_id === nodeId && inc.included_tier_id
        );

        for (const inc of tierInclusions) {
          const neighbor = inc.included_tier_id;
          if (!neighbor) continue;

          if (!visited.has(neighbor)) {
            if (hasCycle(neighbor)) return true;
          } else if (recursionStack.has(neighbor)) {
            return true;
          }
        }

        recursionStack.delete(nodeId);
        return false;
      }

      // Add the potential new edge temporarily
      if (hasCycle(sourceId)) {
        return true;
      }

      return false;
    },
    [inclusions]
  );

  // Handle opening config dialog
  const handleOpenConfig = (item: InclusionConfig, mode: "add" | "edit" = "add") => {
    setSelectedItem(item);
    setConfigMode(mode);

    if (mode === "edit") {
      setMaxQuantity(item.currentMaxQuantity?.toString() || "");
      setUseUnlimited(item.currentMaxQuantity === null);
    } else {
      setMaxQuantity("");
      setUseUnlimited(true);
    }

    setCircularError("");
    setIsConfigDialogOpen(true);
  };

  // Handle adding/updating inclusion
  const handleSaveInclusion = async () => {
    if (!selectedItem) return;

    try {
      // Check circular reference if adding a tier
      if (selectedItem.type === "tier" && configMode === "add") {
        if (checkCircularReference(tierId, selectedItem.id, true)) {
          setCircularError(
            `No puedes crear esta referencia porque causaría un bucle circular. Verifica la estructura de tus tarifas.`
          );
          return;
        }
      }

      setIsSaving(true);

      const finalMaxQuantity = useUnlimited ? null : parseInt(maxQuantity) || null;

      if (configMode === "add") {
        const inclusionData: TierElementInclusionCreate = {
          element_id:
            selectedItem.type === "element" ? selectedItem.id : undefined,
          included_tier_id:
            selectedItem.type === "tier" ? selectedItem.id : undefined,
          max_quantity: finalMaxQuantity,
          notes:
            selectedItem.type === "tier"
              ? `Incluye todos los elementos de ${selectedItem.name}`
              : `Incluye ${selectedItem.name}`,
        };

        await api.createTierInclusion(tierId, inclusionData);
      } else {
        // Edit existing inclusion - find it by item id
        const existingInclusion = inclusions.find(
          (inc) =>
            (selectedItem.type === "element" && inc.element_id === selectedItem.id) ||
            (selectedItem.type === "tier" && inc.included_tier_id === selectedItem.id)
        );

        if (existingInclusion) {
          await api.updateTierInclusion(tierId, existingInclusion.id, {
            max_quantity: finalMaxQuantity,
          });
        }
      }

      // Refresh data
      await refreshInclusions();
      setIsConfigDialogOpen(false);
      setSelectedItem(null);
    } catch (error) {
      console.error("Error saving inclusion:", error);
      alert("Error al guardar inclusión: " + (error instanceof Error ? error.message : "Desconocido"));
    } finally {
      setIsSaving(false);
    }
  };

  // Handle deleting inclusion
  const handleDeleteInclusion = async () => {
    if (!deletingInclusion) return;

    try {
      setIsSaving(true);
      await api.deleteTierInclusion(tierId, deletingInclusion.id);
      await refreshInclusions();
      setDeletingInclusion(null);
    } catch (error) {
      console.error("Error deleting inclusion:", error);
      alert("Error al eliminar inclusión: " + (error instanceof Error ? error.message : "Desconocido"));
    } finally {
      setIsSaving(false);
    }
  };

  // Refresh inclusions and preview
  const refreshInclusions = async () => {
    try {
      setIsRefreshing(true);
      const [incData, prevData] = await Promise.all([
        api.getTierInclusions(tierId),
        api.getTierResolvedElements(tierId),
      ]);
      setInclusions(incData);
      setPreview(prevData);
      onUpdate?.();
    } catch (error) {
      console.error("Error refreshing:", error);
    } finally {
      setIsRefreshing(false);
    }
  };

  // Get already included items
  const includedElementIds = inclusions
    .filter((inc) => inc.element_id)
    .map((inc) => inc.element_id);
  const includedTierIds = inclusions
    .filter((inc) => inc.included_tier_id)
    .map((inc) => inc.included_tier_id);

  // Filter available items
  const availableElements = elements.filter(
    (e) => !includedElementIds.includes(e.id) && e.name.toLowerCase().includes(searchElements.toLowerCase())
  );
  const availableTiers = tiers.filter(
    (t) =>
      !includedTierIds.includes(t.id) &&
      t.name.toLowerCase().includes(searchTiers.toLowerCase())
  );

  // Get included items with their configs
  const includedItems = inclusions.map((inc) => {
    if (inc.element_id) {
      const elem = elements.find((e) => e.id === inc.element_id);
      return {
        inclusion: inc,
        item: {
          id: inc.element_id,
          type: "element" as const,
          name: elem?.name || "Desconocido",
          code: elem?.code,
        },
      };
    } else {
      const tier = tiers.find((t) => t.id === inc.included_tier_id);
      return {
        inclusion: inc,
        item: {
          id: inc.included_tier_id || "",
          type: "tier" as const,
          name: tier?.name || "Desconocido",
          code: tier?.code,
        },
      };
    }
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-muted-foreground">Cargando configuración...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Available Items */}
        <Card>
          <CardHeader>
            <CardTitle>Elementos Disponibles</CardTitle>
            <CardDescription>Elementos que puedes añadir a esta tarifa</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Input
              placeholder="Buscar elementos..."
              value={searchElements}
              onChange={(e) => setSearchElements(e.target.value)}
            />

            <div className="space-y-2 max-h-64 overflow-y-auto">
              {availableElements.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">
                  {searchElements ? "No se encontraron elementos" : "Todos los elementos están incluidos"}
                </p>
              ) : (
                availableElements.map((elem) => (
                  <button
                    key={elem.id}
                    onClick={() =>
                      handleOpenConfig({
                        id: elem.id,
                        type: "element",
                        name: elem.name,
                        code: elem.code,
                        currentMaxQuantity: null,
                      })
                    }
                    className="w-full text-left p-2 rounded border hover:bg-muted transition-colors"
                    disabled={isSaving}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-sm">{elem.name}</p>
                        <p className="text-xs text-muted-foreground">{elem.code}</p>
                      </div>
                      <Plus className="h-4 w-4 flex-shrink-0" />
                    </div>
                  </button>
                ))
              )}
            </div>

            <div className="border-t pt-4">
              <h4 className="text-sm font-medium mb-3">Tarifas Disponibles</h4>
              <Input
                placeholder="Buscar tarifas..."
                value={searchTiers}
                onChange={(e) => setSearchTiers(e.target.value)}
                className="mb-3"
              />

              <div className="space-y-2 max-h-48 overflow-y-auto">
                {availableTiers.length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-4">
                    {searchTiers ? "No se encontraron tarifas" : "Todas las tarifas están incluidas"}
                  </p>
                ) : (
                  availableTiers.map((tier) => (
                    <button
                      key={tier.id}
                      onClick={() =>
                        handleOpenConfig({
                          id: tier.id,
                          type: "tier",
                          name: tier.name,
                          code: tier.code,
                          currentMaxQuantity: null,
                        })
                      }
                      className="w-full text-left p-2 rounded border hover:bg-muted transition-colors"
                      disabled={isSaving}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-sm">{tier.name}</p>
                          <p className="text-xs text-muted-foreground">{tier.code}</p>
                        </div>
                        <Plus className="h-4 w-4 flex-shrink-0" />
                      </div>
                    </button>
                  ))
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Included Items */}
        <Card>
          <CardHeader>
            <CardTitle>Incluidos en esta Tarifa</CardTitle>
            <CardDescription>Referencias actuales ({includedItems.length})</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {includedItems.length === 0 ? (
                <div className="text-center py-8">
                  <Package className="h-12 w-12 text-muted-foreground mx-auto mb-2 opacity-50" />
                  <p className="text-sm text-muted-foreground">Sin inclusiones configuradas</p>
                </div>
              ) : (
                includedItems.map(({ inclusion, item }) => (
                  <div
                    key={inclusion.id}
                    className="flex items-center justify-between p-2 border rounded bg-muted/50"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="font-medium text-sm">{item.name}</p>
                        <Badge
                          variant={
                            item.type === "element" ? "secondary" : "default"
                          }
                          className="text-xs"
                        >
                          {item.type === "element" ? "Elemento" : "Tarifa"}
                        </Badge>
                      </div>
                      <p className="text-xs text-muted-foreground">{item.code}</p>

                      {/* Quantity badge */}
                      <div className="flex items-center gap-1 mt-1">
                        <Badge variant="outline" className="text-xs">
                          {inclusion.max_quantity === null ? (
                            <>
                              <Infinity className="h-3 w-3 mr-1" />
                              Ilimitado
                            </>
                          ) : (
                            <>
                              Máx: {inclusion.max_quantity}
                            </>
                          )}
                        </Badge>
                      </div>
                    </div>

                    <div className="flex items-center gap-1 flex-shrink-0">
                      <button
                        onClick={() =>
                          handleOpenConfig(
                            {
                              id: item.id,
                              type: item.type,
                              name: item.name,
                              code: item.code,
                              currentMaxQuantity: inclusion.max_quantity,
                            },
                            "edit"
                          )
                        }
                        className="p-1 text-muted-foreground hover:text-foreground transition-colors"
                        disabled={isSaving}
                        title="Editar límites"
                      >
                        <Package className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => setDeletingInclusion(inclusion)}
                        className="p-1 text-muted-foreground hover:text-destructive transition-colors"
                        disabled={isSaving}
                        title="Eliminar"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Preview */}
      {preview && (
        <Card>
          <CardHeader>
            <CardTitle>Vista Previa - Elementos Resueltos</CardTitle>
            <CardDescription>
              Esta tarifa incluye {preview.total_elements} elemento(s) único(s) considerando referencias recursivas
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isRefreshing ? (
              <div className="flex items-center justify-center py-6">
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Calculando elementos...
              </div>
            ) : (
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {Object.entries(preview.elements).length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Sin elementos resueltos
                  </p>
                ) : (
                  Object.entries(preview.elements).map(([elementId, maxQty]) => {
                    const elem = elements.find((e) => e.id === elementId);
                    return (
                      <div
                        key={elementId}
                        className="flex items-center justify-between p-2 border rounded text-sm"
                      >
                        <div className="flex items-center gap-2">
                          <Check className="h-4 w-4 text-green-600" />
                          <span className="font-medium">{elem?.name}</span>
                        </div>
                        {maxQty === null ? (
                          <Badge variant="outline" className="text-xs">
                            <Infinity className="h-3 w-3 mr-1" />
                            Ilimitado
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="text-xs">
                            Máx: {maxQty}
                          </Badge>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Config Dialog */}
      <Dialog open={isConfigDialogOpen} onOpenChange={setIsConfigDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {configMode === "add" ? "Añadir Inclusión" : "Editar Límites"}
            </DialogTitle>
            <DialogDescription>
              {selectedItem?.type === "element"
                ? `Configurar inclusión de elemento: ${selectedItem?.name}`
                : `Configurar referencia a tarifa: ${selectedItem?.name}`}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {circularError && (
              <div className="p-3 rounded-lg bg-destructive/10 text-destructive text-sm flex items-start gap-2">
                <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
                <span>{circularError}</span>
              </div>
            )}

            <div className="space-y-3">
              <Label>Límite de Cantidad</Label>

              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <input
                    type="radio"
                    id="unlimited"
                    checked={useUnlimited}
                    onChange={() => setUseUnlimited(true)}
                    disabled={isSaving}
                  />
                  <Label htmlFor="unlimited" className="cursor-pointer font-normal">
                    Ilimitado
                  </Label>
                </div>

                <div className="flex items-center gap-2">
                  <input
                    type="radio"
                    id="limited"
                    checked={!useUnlimited}
                    onChange={() => setUseUnlimited(false)}
                    disabled={isSaving}
                  />
                  <Label htmlFor="limited" className="cursor-pointer font-normal">
                    Máximo
                  </Label>
                </div>

                {!useUnlimited && (
                  <div className="ml-6">
                    <Input
                      type="number"
                      min="1"
                      value={maxQuantity}
                      onChange={(e) => setMaxQuantity(e.target.value)}
                      placeholder="Cantidad máxima"
                      disabled={isSaving}
                    />
                  </div>
                )}
              </div>
            </div>

            <div className="flex gap-3 justify-end pt-4 border-t">
              <button
                onClick={() => setIsConfigDialogOpen(false)}
                disabled={isSaving}
                className="px-3 py-2 text-sm rounded-md border hover:bg-muted disabled:opacity-50"
              >
                Cancelar
              </button>
              <button
                onClick={handleSaveInclusion}
                disabled={isSaving || (!useUnlimited && !maxQuantity)}
                className="px-3 py-2 text-sm rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {isSaving ? "Guardando..." : "Guardar"}
              </button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={!!deletingInclusion} onOpenChange={(open) => !open && setDeletingInclusion(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Eliminar inclusión?</AlertDialogTitle>
            <AlertDialogDescription>
              Esta acción eliminará la referencia a "{deletingInclusion?.element_id ? elements.find((e) => e.id === deletingInclusion.element_id)?.name : tiers.find((t) => t.id === deletingInclusion?.included_tier_id)?.name}".
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="flex gap-3 justify-end">
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteInclusion}
              disabled={isSaving}
              className="bg-destructive hover:bg-destructive/90"
            >
              {isSaving ? "Eliminando..." : "Eliminar"}
            </AlertDialogAction>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
