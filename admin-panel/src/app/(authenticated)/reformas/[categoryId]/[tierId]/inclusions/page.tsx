"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, Plus } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { TierInclusionEditor } from "@/components/tier-inclusion-editor";
import { QuickElementDialog } from "@/components/quick-element-dialog";
import type { TariffTier, VehicleCategory } from "@/lib/types";

export default function InclusionsPage() {
  const params = useParams();
  const router = useRouter();

  const categoryId = params.categoryId as string;
  const tierId = params.tierId as string;

  const [category, setCategory] = useState<VehicleCategory | null>(null);
  const [tier, setTier] = useState<TariffTier | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isQuickCreateOpen, setIsQuickCreateOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    async function fetchData() {
      try {
        setIsLoading(true);
        const [categoryData, tierData] = await Promise.all([
          api.getVehicleCategory(categoryId),
          api.getTariffTier(tierId),
        ]);

        setCategory(categoryData);
        setTier(tierData);
      } catch (error) {
        console.error("Error fetching data:", error);
        toast.error("Error al cargar datos");
      } finally {
        setIsLoading(false);
      }
    }

    fetchData();
  }, [categoryId, tierId]);

  if (isLoading || !category || !tier) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-muted-foreground">Cargando...</div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => router.back()}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-3xl font-bold tracking-tight">
                Inclusiones: {tier.name}
              </h1>
              <Badge variant={tier.is_active ? "default" : "secondary"}>
                {tier.is_active ? "Activo" : "Inactivo"}
              </Badge>
            </div>
            <p className="text-muted-foreground">
              {category.name} • Codigo: <code className="text-xs bg-muted px-1 py-0.5 rounded">{tier.code}</code>
            </p>
          </div>
        </div>
        <Button onClick={() => setIsQuickCreateOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Crear Elemento Rapido
        </Button>
      </div>

      {/* Info Card */}
      <Card>
        <CardHeader>
          <CardTitle>Configurar Inclusiones</CardTitle>
          <CardDescription>
            Define qué elementos y tarifas están incluidas en "{tier.name}"
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-4">
            Puedes añadir elementos específicos o referencias a otras tarifas.
            Usa referencias para mantener estructura DRY - por ejemplo, si T1 incluye todo lo que T2 incluye,
            simplemente añade una referencia a T2 en lugar de duplicar todos los elementos.
          </p>
          <div className="space-y-2 text-sm">
            <p className="font-medium">Tipos de inclusiones:</p>
            <ul className="list-disc list-inside space-y-1 text-muted-foreground">
              <li>
                <strong>Elemento directo:</strong> Añade un elemento específico (ej: Escalera mecánica)
              </li>
              <li>
                <strong>Referencia a tarifa:</strong> Incluye todos los elementos de otra tarifa
              </li>
            </ul>
          </div>
        </CardContent>
      </Card>

      {/* Editor */}
      <TierInclusionEditor
        key={refreshKey}
        tierId={tierId}
        categoryId={categoryId}
        onUpdate={() => setRefreshKey((prev) => prev + 1)}
      />

      {/* Back Button */}
      <div className="flex justify-end">
        <Button variant="outline" onClick={() => router.back()}>Volver</Button>
      </div>

      {/* Quick Create Dialog */}
      <QuickElementDialog
        open={isQuickCreateOpen}
        onOpenChange={setIsQuickCreateOpen}
        categoryId={categoryId}
        tierId={tierId}
        onSuccess={() => {
          setIsQuickCreateOpen(false);
          setRefreshKey((prev) => prev + 1);
        }}
      />
    </div>
  );
}
