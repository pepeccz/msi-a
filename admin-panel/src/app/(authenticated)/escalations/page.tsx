"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
// Card imports removed — unified card uses plain div (Slice 2)
import { StatCard } from "@/components/dashboard";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { FilterChips, type FilterChipOption } from "@/components/shared/filter-chips";
import { Button } from "@/components/ui/button";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  RefreshCw,
  ExternalLink,
  Phone,
  Bot,
  UserX,
  Eye,
  FileCheck,
  Power,
} from "lucide-react";
import { EscalationDetailsDialog } from "@/components/escalation-details-dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { sileo } from "sileo";
import api from "@/lib/api";
import type {
  Escalation,
  EscalationStats,
  EscalationStatus,
  EscalationSource,
} from "@/lib/types";
import { PageContainer } from "@/components/shared/page-container";
import { PageHeader } from "@/components/shared/page-header";
import { DensityToggle } from "@/components/shared/density-toggle";
import { useListUrlState } from "@/hooks/use-list-url-state";
import { TableSkeleton } from "@/components/ui/skeleton-archetypes";
import { ErrorCard } from "@/components/shared/error-card";

export default function EscalationsPage() {
  const [params, setParams] = useListUrlState({
    defaults: { status: "all" },
  });
  const [escalations, setEscalations] = useState<Escalation[]>([]);
  const [stats, setStats] = useState<EscalationStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [fetchError, setFetchError] = useState<Error | null>(null);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [isResolveDialogOpen, setIsResolveDialogOpen] = useState(false);
  const [selectedEscalation, setSelectedEscalation] =
    useState<Escalation | null>(null);
  const [selectedEscalationForDetails, setSelectedEscalationForDetails] =
    useState<Escalation | null>(null);
  const [isDetailsDialogOpen, setIsDetailsDialogOpen] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      setIsLoading(true);
      setFetchError(null);
      const apiParams: Record<string, string | number> = { limit: 100 };
      if (params.status !== "all") {
        apiParams.status = params.status;
      }
      const [escalationsData, statsData] = await Promise.all([
        api.getEscalations(apiParams),
        api.getEscalationStats(),
      ]);
      setEscalations(escalationsData.items);
      setStats(statsData);
    } catch (error) {
      console.error("Error fetching escalations:", error);
      setFetchError(error instanceof Error ? error : new Error("Error al cargar escalaciones"));
    } finally {
      setIsLoading(false);
    }
  }, [params.status]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Build FilterChips options from stats.by_status + a "Todas" sentinel
  const escalationChipOptions = useMemo((): FilterChipOption<string>[] => {
    const byStatus = stats?.by_status ?? {};
    const totalCount = Object.values(byStatus).reduce((a, b) => a + b, 0);

    const STATUS_LABELS: Record<string, string> = {
      pending: "Pendientes",
      in_progress: "En Progreso",
      resolved: "Resueltas",
    };

    const statusChips = Object.entries(STATUS_LABELS).map(([value, label]) => ({
      value,
      label,
      count: byStatus[value] ?? 0,
    }));

    return [
      { value: "all", label: "Todas", count: totalCount },
      ...statusChips,
    ];
  }, [stats]);

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString("es-ES", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const getTimeSince = (dateString: string) => {
    const diff = Date.now() - new Date(dateString).getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h`;
    const days = Math.floor(hours / 24);
    return `${days}d`;
  };

  const getStatusBadge = (status: EscalationStatus) => {
    switch (status) {
      case "pending":
        return (
          <Badge variant="destructive" className="bg-red-600">
            <Clock className="h-3 w-3 mr-1" />
            Pendiente
          </Badge>
        );
      case "in_progress":
        return (
          <Badge variant="default" className="bg-yellow-600">
            <RefreshCw className="h-3 w-3 mr-1" />
            En Progreso
          </Badge>
        );
      case "resolved":
        return (
          <Badge variant="secondary" className="bg-green-600 text-white">
            <CheckCircle2 className="h-3 w-3 mr-1" />
            Resuelta
          </Badge>
        );
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  const getSourceBadge = (source: EscalationSource) => {
    switch (source) {
      case "tool_call":
        return (
          <Badge variant="outline">
            <Phone className="h-3 w-3 mr-1" />
            Solicitud Usuario
          </Badge>
        );
      case "auto_escalation":
        return (
          <Badge variant="outline" className="border-orange-500 text-orange-600">
            <Bot className="h-3 w-3 mr-1" />
            Auto (3+ Errores)
          </Badge>
        );
      case "error":
        return (
          <Badge variant="outline" className="border-red-500 text-red-600">
            <AlertTriangle className="h-3 w-3 mr-1" />
            Error Tecnico
          </Badge>
        );
      case "case_completion":
        return (
          <Badge variant="outline" className="border-green-500 text-green-600">
            <FileCheck className="h-3 w-3 mr-1" />
            Expediente Completo
          </Badge>
        );
      case "agent_disabled":
        return (
          <Badge variant="outline" className="border-gray-500 text-gray-600">
            <Power className="h-3 w-3 mr-1" />
            Bot Desactivado
          </Badge>
        );
      default:
        return <Badge variant="outline">{source}</Badge>;
    }
  };

  const handleResolve = async () => {
    if (!selectedEscalation) return;

    setResolvingId(selectedEscalation.id);
    try {
      await api.resolveEscalation(selectedEscalation.id);
      setEscalations((prev) =>
        prev.map((e) =>
          e.id === selectedEscalation.id ? { ...e, status: "resolved" as EscalationStatus } : e
        )
      );
      // Refresh stats
      const newStats = await api.getEscalationStats();
      setStats(newStats);
      setIsResolveDialogOpen(false);
      setSelectedEscalation(null);
      sileo.success({ title: "Resuelto correctamente" });
    } catch (error) {
      console.error("Error resolving escalation:", error);
      sileo.error({ title: "Error al resolver" });
    } finally {
      setResolvingId(null);
    }
  };

  const openChatwoot = (conversationId: string) => {
    const chatwootBaseUrl = process.env.NEXT_PUBLIC_CHATWOOT_URL || "https://app.chatwoot.com";
    const chatwootAccountId = process.env.NEXT_PUBLIC_CHATWOOT_ACCOUNT_ID || "1";
    const chatwootUrl = `${chatwootBaseUrl}/app/accounts/${chatwootAccountId}/conversations/${conversationId}`;
    window.open(chatwootUrl, "_blank");
  };

  const handleViewDetails = (escalation: Escalation) => {
    setSelectedEscalationForDetails(escalation);
    setIsDetailsDialogOpen(true);
  };

  return (
    <PageContainer className="space-y-6">
      <PageHeader
        title="Escalaciones"
        description="Conversaciones escaladas a atencion humana"
        actions={
          <>
            <DensityToggle />
            <Button variant="outline" onClick={fetchData} disabled={isLoading}>
              <RefreshCw
                className={`h-4 w-4 mr-2 ${isLoading ? "animate-spin" : ""}`}
              />
              Actualizar
            </Button>
          </>
        }
      />

      {/* Stats Cards */}
      {stats && (
        <div className="grid gap-3 md:grid-cols-4">
          <StatCard
            title="Pendientes"
            value={stats.pending}
            subtitle="Requieren atención"
            icon={AlertTriangle}
            valueColor="red"
            conditionalColor={false}
            href="/escalations?status=pending"
          />
          <StatCard
            title="En Progreso"
            value={stats.in_progress}
            subtitle="Siendo atendidas"
            icon={RefreshCw}
            valueColor="yellow"
            conditionalColor={true}
            href="/escalations?status=in_progress"
          />
          <StatCard
            title="Resueltas Hoy"
            value={stats.resolved_today}
            subtitle="Completadas hoy"
            icon={CheckCircle2}
            valueColor="green"
            conditionalColor={true}
          />
          <StatCard
            title="Total Hoy"
            value={stats.total_today}
            subtitle="Generadas hoy"
            icon={Clock}
            valueColor="neutral"
          />
        </div>
      )}

      {/* Escalations Table — unified card (Slice 2+3) */}
      <div className="rounded-lg border bg-card overflow-hidden">
        {/* FilterChips — status filter pills (Slice 3) */}
        <div className="border-b">
          <FilterChips
            options={escalationChipOptions}
            value={params.status === "all" ? null : params.status}
            onChange={(v) => setParams({ status: v ?? "all" })}
            aria-label="Filtrar escalaciones por estado"
          />
        </div>
        <div className="p-0">
          {isLoading ? (
            <div className="p-4">
              <TableSkeleton rows={8} cols={[{ width: "10%" }, { width: "15%" }, { width: "30%" }, { width: "15%" }, { width: "15%" }, { width: "15%" }]} />
            </div>
          ) : fetchError ? (
            <div className="p-4">
              <ErrorCard error={fetchError} onRetry={fetchData} message="No se pudieron cargar las escalaciones." />
            </div>
          ) : escalations.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <CheckCircle2 className="h-12 w-12 text-green-500/50 mb-4" />
              <p className="text-muted-foreground">
                {params.status === "pending"
                  ? "No hay escalaciones pendientes"
                  : "No se encontraron escalaciones"}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[120px]">Estado</TableHead>
                  <TableHead className="w-[140px]">Tiempo</TableHead>
                  <TableHead>Motivo</TableHead>
                  <TableHead className="w-[160px]">Origen</TableHead>
                  <TableHead className="w-[140px]">Conversacion</TableHead>
                  <TableHead className="w-[120px]">Resuelta por</TableHead>
                  <TableHead className="w-[110px]">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {escalations.map((escalation) => (
                  <TableRow
                    key={escalation.id}
                    className={
                      escalation.status === "pending"
                        ? "bg-red-50 dark:bg-red-950/20"
                        : ""
                    }
                  >
                    <TableCell>{getStatusBadge(escalation.status)}</TableCell>
                    <TableCell>
                      <div className="flex flex-col">
                        <span className="font-medium">
                          {getTimeSince(escalation.triggered_at)}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {formatDate(escalation.triggered_at)}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div
                        className="max-w-[300px] flex items-center gap-2 cursor-pointer hover:text-primary transition-colors"
                        onClick={() => handleViewDetails(escalation)}
                        title="Ver detalles completos"
                      >
                        <span className="truncate">{escalation.reason}</span>
                        <Eye className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                      </div>
                    </TableCell>
                    <TableCell>{getSourceBadge(escalation.source)}</TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => openChatwoot(escalation.conversation_id)}
                      >
                        #{escalation.conversation_id}
                        <ExternalLink className="h-3 w-3 ml-1" />
                      </Button>
                    </TableCell>
                    <TableCell>
                      {escalation.resolved_by || "-"}
                    </TableCell>
                    <TableCell>
                      {escalation.status !== "resolved" && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setSelectedEscalation(escalation);
                            setIsResolveDialogOpen(true);
                          }}
                          disabled={resolvingId === escalation.id}
                        >
                          {resolvingId === escalation.id ? (
                            <RefreshCw className="h-4 w-4 animate-spin" />
                          ) : (
                            <>
                              <CheckCircle2 className="h-4 w-4 mr-1" />
                              Resolver
                            </>
                          )}
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            </div>
          )}
        </div>
      </div>

      {/* Resolve Dialog */}
      <AlertDialog
        open={isResolveDialogOpen}
        onOpenChange={setIsResolveDialogOpen}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Resolver Escalación</AlertDialogTitle>
            <AlertDialogDescription>
              Marcar esta escalacion como resuelta indica que el cliente ha sido
              atendido satisfactoriamente.
              <br />
              <br />
              <strong>Motivo:</strong> {selectedEscalation?.reason}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={resolvingId !== null}>
              Cancelar
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleResolve}
              disabled={resolvingId !== null}
              className="bg-green-600 hover:bg-green-700"
            >
              {resolvingId !== null ? "Resolviendo..." : "Marcar como Resuelta"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Details Dialog */}
      <EscalationDetailsDialog
        escalation={selectedEscalationForDetails}
        isOpen={isDetailsDialogOpen}
        onOpenChange={setIsDetailsDialogOpen}
      />
    </PageContainer>
  );
}
