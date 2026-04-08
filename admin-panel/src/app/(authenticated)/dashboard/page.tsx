"use client";

import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Clock,
  CheckCircle2,
  AlertTriangle,
  Inbox,
} from "lucide-react";
import { RecentActivity, SystemHealth, StatCard } from "@/components/dashboard";
import { PageContainer } from "@/components/shared/page-container";
import { PageHeader } from "@/components/shared/page-header";
import api from "@/lib/api";
import type { DashboardKPIs } from "@/lib/types";

export default function DashboardPage() {
  const [kpis, setKpis] = useState<DashboardKPIs | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function fetchKPIs() {
      try {
        const data = await api.getDashboardKPIs();
        setKpis(data);
      } catch (error) {
        console.error("Error fetching KPIs:", error);
      } finally {
        setIsLoading(false);
      }
    }
    fetchKPIs();

    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchKPIs, 30000);
    return () => clearInterval(interval);
  }, []);

  const resolvedTotal =
    (kpis?.cases_resolved_today ?? 0) + (kpis?.escalations_resolved_today ?? 0);

  return (
    <PageContainer className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Panel de control de MSI Automotive"
      />

      {/* Critical KPIs - Cards that require attention */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Expedientes Pendientes"
          value={kpis?.cases_pending_review ?? 0}
          subtitle="Esperando revisión"
          icon={Inbox}
          valueColor="red"
          conditionalColor={false}
          href="/cases?status=pending_review"
          isLoading={isLoading}
        />
        <StatCard
          title="Escalaciones Pendientes"
          value={kpis?.escalations_pending ?? 0}
          subtitle="Requieren atención humana"
          icon={AlertTriangle}
          valueColor="red"
          conditionalColor={false}
          href="/escalations?status=pending"
          isLoading={isLoading}
        />
        <StatCard
          title="En Recolección"
          value={kpis?.cases_collecting ?? 0}
          subtitle="Recopilando datos"
          icon={Clock}
          valueColor="neutral"
          href="/cases?status=collecting"
          isLoading={isLoading}
        />
        <StatCard
          title="Resueltos Hoy"
          value={resolvedTotal}
          subtitle="Expedientes y escalaciones"
          icon={CheckCircle2}
          valueColor="green"
          conditionalColor={true}
          isLoading={isLoading}
        />
      </div>

      {/* Activity and Health Section */}
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <RecentActivity />
        </div>
        <div>
          <SystemHealth />
        </div>
      </div>

      {/* General Stats (secondary info) */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Usuarios
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-xl font-semibold">
              {isLoading ? "..." : kpis?.total_users ?? 0}
            </div>
            <p className="text-xs text-muted-foreground">
              Clientes registrados en el sistema
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Conversaciones
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-xl font-semibold">
              {isLoading ? "..." : kpis?.total_conversations ?? 0}
            </div>
            <p className="text-xs text-muted-foreground">
              Histórico de conversaciones
            </p>
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}
