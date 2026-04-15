"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, Plus } from "lucide-react";
import { sileo } from "sileo";
import api from "@/lib/api";
import { PageContainer } from "@/components/shared/page-container";
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
        sileo.error({ title: "Error al cargar datos" });
      } finally {
        setIsLoading(false);
      }
    }

    fetchData();
  }, [categoryId, tierId]);

  if (isLoading || !category || !tier) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center py-12">
          <div className="text-muted-foreground">Cargando...</div>
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={() => router.back()}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold truncate">Inclusiones: {tier?.name}</h1>
            {tier?.is_active ? (
              <Badge variant="default" className="shrink-0">Activo</Badge>
            ) : (
              <Badge variant="secondary" className="shrink-0">Inactivo</Badge>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            {category?.name} • <code className="text-xs">{tier?.code}</code>
          </p>
        </div>
        <Button size="sm" onClick={() => setIsQuickCreateOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Crear Elemento Rapido
        </Button>
      </div>

      {/* Inline hint */}
      <p className="text-xs text-muted-foreground px-1">
        Añade elementos directos o referencias a otras tarifas. Las referencias son DRY — si T1 incluye T2, agrega una referencia a T2 en lugar de duplicar elementos.
      </p>

      {/* Editor */}
      <TierInclusionEditor
        key={refreshKey}
        tierId={tierId}
        categoryId={categoryId}
        onUpdate={() => setRefreshKey((prev) => prev + 1)}
      />

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
    </PageContainer>
  );
}
