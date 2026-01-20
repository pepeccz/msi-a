"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  FileText,
  PhoneForwarded,
  Clock,
  ArrowRight,
  AlertTriangle,
  CheckCircle2,
} from "lucide-react";
import api from "@/lib/api";
import type { CaseListItem, Escalation } from "@/lib/types";

function getTimeSince(dateString: string): string {
  const diff = Date.now() - new Date(dateString).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 60) return `hace ${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `hace ${hours}h`;
  const days = Math.floor(hours / 24);
  return `hace ${days}d`;
}

export function RecentActivity() {
  const [recentCases, setRecentCases] = useState<CaseListItem[]>([]);
  const [pendingEscalations, setPendingEscalations] = useState<Escalation[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const [casesData, escalationsData] = await Promise.all([
          api.getCases({ limit: 5 }),
          api.getEscalations({ status: "pending", limit: 5 }),
        ]);
        setRecentCases(casesData.items);
        setPendingEscalations(escalationsData.items);
      } catch (error) {
        console.error("Error fetching recent activity:", error);
      } finally {
        setIsLoading(false);
      }
    }
    fetchData();
  }, []);

  const getCaseStatusColor = (status: string) => {
    switch (status) {
      case "pending_review":
        return "text-red-600";
      case "in_progress":
        return "text-yellow-600";
      case "collecting":
        return "text-blue-600";
      case "resolved":
        return "text-green-600";
      default:
        return "text-muted-foreground";
    }
  };

  const getCaseStatusLabel = (status: string) => {
    switch (status) {
      case "pending_review":
        return "Pendiente";
      case "in_progress":
        return "En progreso";
      case "collecting":
        return "Recolectando";
      case "resolved":
        return "Resuelto";
      case "cancelled":
        return "Cancelado";
      case "abandoned":
        return "Abandonado";
      default:
        return status;
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Actividad Reciente</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="animate-pulse space-y-4">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-12 bg-muted rounded" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg">Actividad Reciente</CardTitle>
        <CardDescription>
          Ultimos expedientes y escalaciones pendientes
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Recent Cases */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-sm font-medium flex items-center gap-2">
              <FileText className="h-4 w-4" />
              Ultimos Expedientes
            </h4>
            <Link href="/cases">
              <Button variant="ghost" size="sm" className="h-7 text-xs">
                Ver todos
                <ArrowRight className="h-3 w-3 ml-1" />
              </Button>
            </Link>
          </div>
          {recentCases.length === 0 ? (
            <p className="text-sm text-muted-foreground py-2">
              No hay expedientes recientes
            </p>
          ) : (
            <div className="space-y-2">
              {recentCases.map((c) => (
                <Link
                  key={c.id}
                  href={`/cases/${c.id}`}
                  className="flex items-center justify-between p-2 rounded-lg hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">
                        {c.user_first_name || c.user_last_name
                          ? `${c.user_first_name || ""} ${c.user_last_name || ""}`.trim()
                          : "Sin nombre"}
                      </p>
                      <p className="text-xs text-muted-foreground truncate">
                        {c.category_name || "Sin categoria"}{" "}
                        {c.vehiculo_matricula && `- ${c.vehiculo_matricula}`}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className={`text-xs font-medium ${getCaseStatusColor(c.status)}`}>
                      {getCaseStatusLabel(c.status)}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {getTimeSince(c.created_at)}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* Pending Escalations */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-sm font-medium flex items-center gap-2">
              <PhoneForwarded className="h-4 w-4" />
              Escalaciones Pendientes
            </h4>
            <Link href="/escalations">
              <Button variant="ghost" size="sm" className="h-7 text-xs">
                Ver todas
                <ArrowRight className="h-3 w-3 ml-1" />
              </Button>
            </Link>
          </div>
          {pendingEscalations.length === 0 ? (
            <div className="flex items-center gap-2 text-sm text-green-600 py-2">
              <CheckCircle2 className="h-4 w-4" />
              No hay escalaciones pendientes
            </div>
          ) : (
            <div className="space-y-2">
              {pendingEscalations.map((e) => (
                <Link
                  key={e.id}
                  href="/escalations"
                  className="flex items-center justify-between p-2 rounded-lg bg-red-50 hover:bg-red-100 dark:bg-red-950/20 dark:hover:bg-red-950/40 transition-colors"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <AlertTriangle className="h-4 w-4 text-red-500 flex-shrink-0" />
                    <p className="text-sm truncate">{e.reason}</p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <Badge variant="destructive" className="text-xs">
                      Pendiente
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {getTimeSince(e.triggered_at)}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
