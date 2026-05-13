"use client";

import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
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
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertTriangle,
  CheckCircle,
  Clock,
  RefreshCw,
  UserCheck,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { es } from "date-fns/locale";
import { sileo } from "sileo";
import api from "@/lib/api";
import type { Escalation, EscalationStatus, EscalationStats } from "@/lib/types";
import { EscalationCardActions } from "@/components/escalations/escalation-card-actions";
import { PageContainer } from "@/components/shared/page-container";
import { PageHeader } from "@/components/shared/page-header";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Status badge config
// ---------------------------------------------------------------------------

function getStatusBadge(status: EscalationStatus) {
  const config: Record<
    EscalationStatus,
    { label: string; variant: "default" | "secondary" | "outline"; icon: React.ComponentType<{ className?: string }> }
  > = {
    pending: { label: "Pendiente", variant: "default", icon: Clock },
    assigned: { label: "Asignada", variant: "secondary", icon: UserCheck },
    resolved: { label: "Resuelta", variant: "outline", icon: CheckCircle },
  };
  const { label, variant, icon: Icon } = config[status];
  return (
    <Badge variant={variant} className="gap-1 text-xs">
      <Icon className="h-3 w-3" />
      {label}
    </Badge>
  );
}

const SOURCE_LABEL: Record<string, string> = {
  tool_call: "Solicitud del bot",
  auto: "Auto-escalada",
  panic: "Panic button",
  fallback: "Reintentos agotados",
  case_completion: "Expediente completado",
};

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function EscalationsPage() {
  const searchParams = useSearchParams();
  const filterConversationId = searchParams.get("conversation_id");

  const [escalations, setEscalations] = useState<Escalation[]>([]);
  const [stats, setStats] = useState<EscalationStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<EscalationStatus | "all">("all");

  const fetchData = useCallback(async () => {
    try {
      const params: Record<string, string | number | undefined> = {
        limit: 100,
        offset: 0,
      };
      if (statusFilter !== "all") {
        params.status = statusFilter;
      }
      if (filterConversationId) {
        params.conversation_id = filterConversationId;
      }

      const [escalationResult, statsResult] = await Promise.all([
        api.getEscalations(params),
        api.getEscalationStats(),
      ]);

      setEscalations(escalationResult.items);
      setStats(statsResult);
    } catch (err) {
      const error = err as Error;
      sileo.error({
        title: "Error al cargar escalaciones",
        description: error.message,
      });
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter, filterConversationId]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30_000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleEscalationUpdate = useCallback(
    (updated: Escalation) => {
      setEscalations((prev) =>
        prev.map((e) => (e.id === updated.id ? updated : e)),
      );
      // Refresh stats after a mutation
      api
        .getEscalationStats()
        .then(setStats)
        .catch(() => {/* best-effort */});
    },
    [],
  );

  // Filter tabs
  const statusTabs: { label: string; value: EscalationStatus | "all" }[] = [
    { label: "Todas", value: "all" },
    { label: `Pendientes (${stats?.by_status?.pending ?? 0})`, value: "pending" },
    { label: `Asignadas (${stats?.by_status?.assigned ?? 0})`, value: "assigned" },
    { label: "Resueltas", value: "resolved" },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Escalaciones"
        description="Gestión de conversaciones que requieren atención humana"
        actions={
          <Button
            size="sm"
            variant="outline"
            onClick={fetchData}
            className="gap-1.5"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Actualizar
          </Button>
        }
      />

      {/* Stats strip */}
      {stats && (
        <div className="flex items-center gap-4 text-sm text-muted-foreground mb-4">
          <span className="flex items-center gap-1">
            <Clock className="h-3.5 w-3.5" />
            {stats.by_status?.pending ?? 0} pendientes
          </span>
          <span className="flex items-center gap-1">
            <UserCheck className="h-3.5 w-3.5" />
            {stats.by_status?.assigned ?? 0} asignadas
          </span>
          <span className="flex items-center gap-1">
            <CheckCircle className="h-3.5 w-3.5" />
            {stats.resolved_today ?? 0} resueltas hoy
          </span>
        </div>
      )}

      {/* Filter tabs */}
      <div className="flex gap-2 mb-4 flex-wrap">
        {statusTabs.map((tab) => (
          <Button
            key={tab.value}
            size="sm"
            variant={statusFilter === tab.value ? "default" : "outline"}
            onClick={() => setStatusFilter(tab.value)}
          >
            {tab.label}
          </Button>
        ))}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[...Array(5)].map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : escalations.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">
          <AlertTriangle className="h-8 w-8 mx-auto mb-2 opacity-40" />
          <p>No hay escalaciones</p>
        </div>
      ) : (
        <div className="rounded-md border overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Estado</TableHead>
                <TableHead>Conversación</TableHead>
                <TableHead>Motivo</TableHead>
                <TableHead>Origen</TableHead>
                <TableHead>Asignado a</TableHead>
                <TableHead>Fecha</TableHead>
                <TableHead className="text-right">Acciones</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {escalations.map((esc) => (
                <TableRow
                  key={esc.id}
                  className={cn(
                    esc.status === "resolved" && "opacity-60",
                  )}
                >
                  <TableCell>{getStatusBadge(esc.status)}</TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {esc.conversation_id}
                  </TableCell>
                  <TableCell className="max-w-[200px] truncate text-sm">
                    {esc.reason}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {SOURCE_LABEL[esc.source] ?? esc.source}
                  </TableCell>
                  <TableCell className="text-sm">
                    {esc.status === "assigned" && esc.assigned_to ? (
                      <span className="flex items-center gap-1">
                        <UserCheck className="h-3.5 w-3.5 text-muted-foreground" />
                        {esc.assigned_to.display_name ?? esc.assigned_to.username}
                      </span>
                    ) : (
                      <span className="text-muted-foreground text-xs">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                    {formatDistanceToNow(new Date(esc.triggered_at), {
                      addSuffix: true,
                      locale: es,
                    })}
                  </TableCell>
                  <TableCell className="text-right">
                    <EscalationCardActions
                      escalation={esc}
                      onUpdate={handleEscalationUpdate}
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </PageContainer>
  );
}
