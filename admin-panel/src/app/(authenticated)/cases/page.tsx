"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
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
import { Input } from "@/components/ui/input";
import {
  FileText,
  CheckCircle2,
  Clock,
  RefreshCw,
  ExternalLink,
  Image as ImageIcon,
  Search,
  Eye,
  Play,
  Ban,
  AlertTriangle,
  Inbox,
} from "lucide-react";
import api from "@/lib/api";
import type { CaseListItem, CaseStats, CaseStatus } from "@/lib/types";

export default function CasesPage() {
  const router = useRouter();
  const [cases, setCases] = useState<CaseListItem[]>([]);
  const [stats, setStats] = useState<CaseStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("pending_review");
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const fetchData = useCallback(async () => {
    try {
      setIsLoading(true);
      const params: Record<string, string | number> = { limit: 100 };
      if (statusFilter !== "all") {
        params.status = statusFilter;
      }
      if (debouncedSearch) {
        params.search = debouncedSearch;
      }
      const [casesData, statsData] = await Promise.all([
        api.getCases(params),
        api.getCaseStats(),
      ]);
      setCases(casesData.items);
      setStats(statsData);
    } catch (error) {
      console.error("Error fetching cases:", error);
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter, debouncedSearch]);

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

  const getStatusBadge = (status: CaseStatus) => {
    switch (status) {
      case "collecting":
        return (
          <Badge variant="outline" className="border-blue-500 text-blue-600">
            <Clock className="h-3 w-3 mr-1" />
            Recolectando
          </Badge>
        );
      case "pending_images":
        return (
          <Badge variant="outline" className="border-orange-500 text-orange-600">
            <ImageIcon className="h-3 w-3 mr-1" />
            Faltan Imagenes
          </Badge>
        );
      case "pending_review":
        return (
          <Badge variant="destructive" className="bg-red-600">
            <Inbox className="h-3 w-3 mr-1" />
            Pendiente
          </Badge>
        );
      case "in_progress":
        return (
          <Badge variant="default" className="bg-yellow-600">
            <Play className="h-3 w-3 mr-1" />
            En Progreso
          </Badge>
        );
      case "resolved":
        return (
          <Badge variant="secondary" className="bg-green-600 text-white">
            <CheckCircle2 className="h-3 w-3 mr-1" />
            Resuelto
          </Badge>
        );
      case "cancelled":
        return (
          <Badge variant="outline" className="border-gray-500 text-gray-600">
            <Ban className="h-3 w-3 mr-1" />
            Cancelado
          </Badge>
        );
      case "abandoned":
        return (
          <Badge variant="outline" className="border-gray-400 text-gray-500">
            <AlertTriangle className="h-3 w-3 mr-1" />
            Abandonado
          </Badge>
        );
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  const openChatwoot = (conversationId: string) => {
    const chatwootBaseUrl = process.env.NEXT_PUBLIC_CHATWOOT_URL || "https://app.chatwoot.com";
    const chatwootAccountId = process.env.NEXT_PUBLIC_CHATWOOT_ACCOUNT_ID || "1";
    const chatwootUrl = `${chatwootBaseUrl}/app/accounts/${chatwootAccountId}/conversations/${conversationId}`;
    window.open(chatwootUrl, "_blank");
  };

  const handleViewCase = (caseId: string) => {
    router.push(`/cases/${caseId}`);
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Expedientes</h1>
          <p className="text-muted-foreground">
            Gestion de expedientes de homologacion
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
              <Inbox className="h-4 w-4 text-red-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-red-600">
                {stats.pending_review}
              </div>
              <p className="text-xs text-muted-foreground">
                Esperando revision
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">En Progreso</CardTitle>
              <Play className="h-4 w-4 text-yellow-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-yellow-600">
                {stats.in_progress}
              </div>
              <p className="text-xs text-muted-foreground">
                Siendo atendidos
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Resueltos Hoy</CardTitle>
              <CheckCircle2 className="h-4 w-4 text-green-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-green-600">
                {stats.resolved_today}
              </div>
              <p className="text-xs text-muted-foreground">
                Completados hoy
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Recolectando</CardTitle>
              <Clock className="h-4 w-4 text-blue-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-blue-600">
                {stats.collecting}
              </div>
              <p className="text-xs text-muted-foreground">
                Recopilando datos
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Cases Table */}
      <Card>
        <CardHeader>
          <CardTitle>Lista de Expedientes</CardTitle>
          <CardDescription>
            Expedientes de homologacion creados por usuarios
          </CardDescription>
          <div className="flex gap-4 mt-4">
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Estado" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="pending_review">Pendientes</SelectItem>
                <SelectItem value="in_progress">En Progreso</SelectItem>
                <SelectItem value="collecting">Recolectando</SelectItem>
                <SelectItem value="pending_images">Faltan Imagenes</SelectItem>
                <SelectItem value="resolved">Resueltos</SelectItem>
                <SelectItem value="cancelled">Cancelados</SelectItem>
                <SelectItem value="abandoned">Abandonados</SelectItem>
              </SelectContent>
            </Select>
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Buscar por nombre, email, matricula..."
                className="pl-8"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-pulse text-muted-foreground">
                Cargando expedientes...
              </div>
            </div>
          ) : cases.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <FileText className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <p className="text-muted-foreground">
                {statusFilter === "pending_review"
                  ? "No hay expedientes pendientes"
                  : debouncedSearch
                  ? "No se encontraron expedientes con ese criterio"
                  : "No se encontraron expedientes"}
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Estado</TableHead>
                  <TableHead>Cliente</TableHead>
                  <TableHead>Vehiculo</TableHead>
                  <TableHead>Elementos</TableHead>
                  <TableHead>Imagenes</TableHead>
                  <TableHead>Tarifa</TableHead>
                  <TableHead>Tiempo</TableHead>
                  <TableHead className="w-[120px]">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cases.map((c) => (
                  <TableRow
                    key={c.id}
                    className={
                      c.status === "pending_review"
                        ? "bg-red-50 dark:bg-red-950/20"
                        : c.status === "in_progress"
                        ? "bg-yellow-50 dark:bg-yellow-950/20"
                        : ""
                    }
                  >
                    <TableCell>{getStatusBadge(c.status)}</TableCell>
                    <TableCell>
                      <div className="flex flex-col">
                        <span className="font-medium">
                          {c.user_first_name || c.user_last_name
                            ? `${c.user_first_name || ""} ${c.user_last_name || ""}`.trim()
                            : "Sin nombre"}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {c.user_email || "Sin email"}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col">
                        <span className="font-medium">
                          {c.vehiculo_marca && c.vehiculo_modelo
                            ? `${c.vehiculo_marca} ${c.vehiculo_modelo}`
                            : "Sin datos"}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {c.vehiculo_matricula || "Sin matricula"}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col">
                        <span className="font-medium">{c.element_codes.length}</span>
                        <span className="text-xs text-muted-foreground">
                          {c.category_name || "Sin categoria"}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <ImageIcon className="h-4 w-4 text-muted-foreground" />
                        <span>{c.image_count}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      {c.tariff_amount ? (
                        <span className="font-medium">
                          {c.tariff_amount.toFixed(2)} EUR
                        </span>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col">
                        <span className="font-medium">
                          {getTimeSince(c.created_at)}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {formatDate(c.created_at)}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleViewCase(c.id)}
                          title="Ver detalle"
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openChatwoot(c.conversation_id)}
                          title="Abrir en Chatwoot"
                        >
                          <ExternalLink className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
