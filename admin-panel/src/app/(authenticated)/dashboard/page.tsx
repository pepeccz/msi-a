"use client";

import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Users, MessageSquare, TrendingUp, AlertCircle } from "lucide-react";
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
  }, []);

  const kpiCards = [
    {
      title: "Total Usuarios",
      value: kpis?.total_users ?? 0,
      icon: Users,
      description: "Usuarios registrados",
    },
    {
      title: "Conversaciones",
      value: kpis?.total_conversations ?? 0,
      icon: MessageSquare,
      description: "Total de conversaciones",
    },
    {
      title: "Mensajes Hoy",
      value: kpis?.messages_today ?? 0,
      icon: TrendingUp,
      description: "Mensajes procesados hoy",
    },
    {
      title: "Escalaciones",
      value: kpis?.escalations_pending ?? 0,
      icon: AlertCircle,
      description: "Pendientes de atencion",
    },
  ];

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Bienvenido al panel de administracion de MSI Automotive
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {kpiCards.map((kpi) => {
          const Icon = kpi.icon;
          return (
            <Card key={kpi.title}>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">
                  {kpi.title}
                </CardTitle>
                <Icon className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {isLoading ? (
                    <span className="animate-pulse">...</span>
                  ) : (
                    kpi.value
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  {kpi.description}
                </p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Actividad Reciente</CardTitle>
          <CardDescription>
            Las ultimas conversaciones y consultas de usuarios
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground text-sm">
            Los graficos y actividad detallada se mostraran aqui una vez que el
            sistema tenga datos suficientes.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
