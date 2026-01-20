"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  FileText,
  PhoneForwarded,
  MessageSquare,
  Car,
  BookOpen,
  MessageCircle,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Inbox,
  ArrowRight,
} from "lucide-react";
import { QuickAccessCard, RecentActivity, SystemHealth } from "@/components/dashboard";
import { GlobalSearch } from "@/components/global-search";
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

  const chatwootUrl = process.env.NEXT_PUBLIC_CHATWOOT_URL || "http://localhost:3000";

  // Helper to determine if a count requires attention
  const requiresAttention = (count: number) => count > 0;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Panel de control de MSI Automotive
        </p>
      </div>

      {/* Critical KPIs - Cards that require attention */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {/* Expedientes Pendientes */}
        <Link href="/cases?status=pending_review">
          <Card className={`cursor-pointer transition-all hover:shadow-md ${
            requiresAttention(kpis?.cases_pending_review || 0) 
              ? "border-red-200 bg-red-50 dark:bg-red-950/20 dark:border-red-800" 
              : ""
          }`}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                Expedientes Pendientes
              </CardTitle>
              <Inbox className={`h-4 w-4 ${
                requiresAttention(kpis?.cases_pending_review || 0) 
                  ? "text-red-500" 
                  : "text-muted-foreground"
              }`} />
            </CardHeader>
            <CardContent>
              <div className={`text-2xl font-bold ${
                requiresAttention(kpis?.cases_pending_review || 0) 
                  ? "text-red-600" 
                  : ""
              }`}>
                {isLoading ? (
                  <span className="animate-pulse">...</span>
                ) : (
                  kpis?.cases_pending_review ?? 0
                )}
              </div>
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                Esperando revision
                <ArrowRight className="h-3 w-3" />
              </p>
            </CardContent>
          </Card>
        </Link>

        {/* Escalaciones Pendientes */}
        <Link href="/escalations?status=pending">
          <Card className={`cursor-pointer transition-all hover:shadow-md ${
            requiresAttention(kpis?.escalations_pending || 0) 
              ? "border-red-200 bg-red-50 dark:bg-red-950/20 dark:border-red-800" 
              : ""
          }`}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                Escalaciones Pendientes
              </CardTitle>
              <AlertTriangle className={`h-4 w-4 ${
                requiresAttention(kpis?.escalations_pending || 0) 
                  ? "text-red-500" 
                  : "text-muted-foreground"
              }`} />
            </CardHeader>
            <CardContent>
              <div className={`text-2xl font-bold ${
                requiresAttention(kpis?.escalations_pending || 0) 
                  ? "text-red-600" 
                  : ""
              }`}>
                {isLoading ? (
                  <span className="animate-pulse">...</span>
                ) : (
                  kpis?.escalations_pending ?? 0
                )}
              </div>
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                Requieren atencion humana
                <ArrowRight className="h-3 w-3" />
              </p>
            </CardContent>
          </Card>
        </Link>

        {/* En Recoleccion */}
        <Link href="/cases?status=collecting">
          <Card className="cursor-pointer transition-all hover:shadow-md">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                En Recoleccion
              </CardTitle>
              <Clock className="h-4 w-4 text-blue-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-blue-600">
                {isLoading ? (
                  <span className="animate-pulse">...</span>
                ) : (
                  kpis?.cases_collecting ?? 0
                )}
              </div>
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                Recopilando datos
                <ArrowRight className="h-3 w-3" />
              </p>
            </CardContent>
          </Card>
        </Link>

        {/* Resueltos Hoy */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Resueltos Hoy
            </CardTitle>
            <CheckCircle2 className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">
              {isLoading ? (
                <span className="animate-pulse">...</span>
              ) : (
                (kpis?.cases_resolved_today ?? 0) + (kpis?.escalations_resolved_today ?? 0)
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              Expedientes y escalaciones
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Global Search */}
      <div>
        <GlobalSearch variant="inline" />
      </div>

      {/* Quick Access Section */}
      <div>
        <h2 className="text-lg font-semibold mb-4">Accesos Rapidos</h2>
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          <QuickAccessCard
            title="Expedientes"
            description="Gestionar casos de homologacion"
            href="/cases"
            icon={FileText}
            variant="primary"
          />
          <QuickAccessCard
            title="Escalaciones"
            description="Atender consultas escaladas"
            href="/escalations"
            icon={PhoneForwarded}
            variant={requiresAttention(kpis?.escalations_pending || 0) ? "warning" : "default"}
          />
          <QuickAccessCard
            title="Conversaciones"
            description="Historial de chats"
            href="/conversations"
            icon={MessageSquare}
          />
          <QuickAccessCard
            title="Reformas"
            description="Tarifas y categorias"
            href="/reformas"
            icon={Car}
          />
          <QuickAccessCard
            title="Normativas"
            description="Documentos RAG"
            href="/normativas"
            icon={BookOpen}
          />
          <QuickAccessCard
            title="Chatwoot"
            description="Abrir panel de chat"
            href={chatwootUrl}
            icon={MessageCircle}
            external
          />
        </div>
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
              Historico de conversaciones
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
