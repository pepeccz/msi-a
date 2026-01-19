"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
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
import api from "@/lib/api";
import type {
  Escalation,
  EscalationStats,
  EscalationStatus,
  EscalationSource,
} from "@/lib/types";

export default function EscalationsPage() {
  const [escalations, setEscalations] = useState<Escalation[]>([]);
  const [stats, setStats] = useState<EscalationStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("pending");
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
      const params: Record<string, string | number> = { limit: 100 };
      if (statusFilter !== "all") {
        params.status = statusFilter;
      }
      const [escalationsData, statsData] = await Promise.all([
        api.getEscalations(params),
        api.getEscalationStats(),
      ]);
      setEscalations(escalationsData.items);
      setStats(statsData);
    } catch (error) {
      console.error("Error fetching escalations:", error);
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

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
            Auto (Errores)
          </Badge>
        );
      case "error":
        return (
          <Badge variant="outline" className="border-red-500 text-red-600">
            <UserX className="h-3 w-3 mr-1" />
            Error
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
    } catch (error) {
      console.error("Error resolving escalation:", error);
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
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Escalaciones</h1>
          <p className="text-muted-foreground">
            Conversaciones escaladas a atencion humana
          </p>
        </div>
        <Button variant="outline" onClick={fetchData} disabled={isLoading}>
          <RefreshCw
            className={`h-4 w-4 mr-2 ${isLoading ? "animate-spin" : ""}`}
          />
          Actualizar
        </Button>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid gap-4 md:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Pendientes</CardTitle>
              <AlertTriangle className="h-4 w-4 text-red-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-red-600">
                {stats.pending}
              </div>
              <p className="text-xs text-muted-foreground">
                Requieren atencion
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">En Progreso</CardTitle>
              <RefreshCw className="h-4 w-4 text-yellow-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-yellow-600">
                {stats.in_progress}
              </div>
              <p className="text-xs text-muted-foreground">
                Siendo atendidas
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Resueltas Hoy</CardTitle>
              <CheckCircle2 className="h-4 w-4 text-green-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-green-600">
                {stats.resolved_today}
              </div>
              <p className="text-xs text-muted-foreground">
                Completadas hoy
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Hoy</CardTitle>
              <Clock className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_today}</div>
              <p className="text-xs text-muted-foreground">
                Escalaciones hoy
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Escalations Table */}
      <Card>
        <CardHeader>
          <CardTitle>Lista de Escalaciones</CardTitle>
          <CardDescription>
            Historial de conversaciones escaladas a humanos
          </CardDescription>
          <div className="flex gap-4 mt-4">
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Estado" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas</SelectItem>
                <SelectItem value="pending">Pendientes</SelectItem>
                <SelectItem value="in_progress">En Progreso</SelectItem>
                <SelectItem value="resolved">Resueltas</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-pulse text-muted-foreground">
                Cargando escalaciones...
              </div>
            </div>
          ) : escalations.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <CheckCircle2 className="h-12 w-12 text-green-500/50 mb-4" />
              <p className="text-muted-foreground">
                {statusFilter === "pending"
                  ? "No hay escalaciones pendientes"
                  : "No se encontraron escalaciones"}
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Estado</TableHead>
                  <TableHead>Tiempo</TableHead>
                  <TableHead>Motivo</TableHead>
                  <TableHead>Origen</TableHead>
                  <TableHead>Conversacion</TableHead>
                  <TableHead>Resuelta por</TableHead>
                  <TableHead className="w-[120px]">Acciones</TableHead>
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
          )}
        </CardContent>
      </Card>

      {/* Resolve Dialog */}
      <AlertDialog
        open={isResolveDialogOpen}
        onOpenChange={setIsResolveDialogOpen}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Resolver Escalacion</AlertDialogTitle>
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
    </div>
  );
}
