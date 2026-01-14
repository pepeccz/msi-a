"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
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
import {
  CheckCircle,
  XCircle,
  Loader2,
  RefreshCw,
  Square,
  Trash2,
  Play,
  Pause,
  AlertTriangle,
  Eye,
  Ban,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import api from "@/lib/api";
import type {
  SystemService,
  SystemServiceName,
  ContainerErrorLog,
  ContainerErrorStats,
  ContainerErrorStatus,
} from "@/lib/types";

interface HealthStatus {
  status: string;
  redis: string;
  postgres: string;
}

const SERVICE_LABELS: Record<SystemServiceName, { name: string; description: string }> = {
  api: { name: "API (FastAPI)", description: "Webhooks y endpoints REST - Puerto 8000" },
  agent: { name: "Agent (LangGraph)", description: "Orquestador de conversaciones con IA" },
  postgres: { name: "PostgreSQL", description: "Base de datos principal - Puerto 5432" },
  redis: { name: "Redis Stack", description: "Cache y checkpointing - Puerto 6379" },
  "admin-panel": { name: "Admin Panel", description: "Panel de administracion - Puerto 8001" },
  ollama: { name: "Ollama", description: "Servidor LLM local - Puerto 11434" },
  qdrant: { name: "Qdrant", description: "Base de datos vectorial RAG - Puerto 6333" },
  "document-processor": { name: "Document Processor", description: "Worker de procesamiento de documentos" },
};

function StatusIndicator({ status }: { status: string }) {
  if (status === "connected" || status === "healthy" || status === "running") {
    return <CheckCircle className="h-5 w-5 text-green-500" />;
  }
  if (status === "disconnected" || status === "degraded" || status === "exited") {
    return <XCircle className="h-5 w-5 text-red-500" />;
  }
  if (status === "starting" || status === "restarting") {
    return <Loader2 className="h-5 w-5 animate-spin text-yellow-500" />;
  }
  return <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />;
}

function ServiceStatusBadge({ status, health }: { status: string; health: string | null }) {
  const getVariant = (): "default" | "destructive" | "secondary" | "outline" => {
    if (status === "running") {
      if (health === "healthy") return "default";
      if (health === "unhealthy") return "destructive";
      return "secondary";
    }
    if (status === "exited") return "destructive";
    return "outline";
  };

  const getText = () => {
    if (status === "running") {
      if (health === "healthy") return "Healthy";
      if (health === "unhealthy") return "Unhealthy";
      if (health === "starting") return "Starting";
      return "Running";
    }
    return status.charAt(0).toUpperCase() + status.slice(1);
  };

  return <Badge variant={getVariant()}>{getText()}</Badge>;
}

export default function SystemPage() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [services, setServices] = useState<SystemService[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Service actions state
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean;
    service: SystemServiceName | null;
    action: "restart" | "stop";
  }>({ open: false, service: null, action: "restart" });

  // Logs state
  const [selectedLogService, setSelectedLogService] = useState<SystemServiceName>("api");
  const [logs, setLogs] = useState<string[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [logFilter, setLogFilter] = useState<"all" | "error" | "warning" | "info" | "debug">("all");
  const eventSourceRef = useRef<EventSource | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Error logs state
  const [errorLogs, setErrorLogs] = useState<ContainerErrorLog[]>([]);
  const [errorStats, setErrorStats] = useState<ContainerErrorStats | null>(null);
  const [errorFilter, setErrorFilter] = useState<{
    service: string | null;
    status: ContainerErrorStatus;
  }>({ service: null, status: "open" });
  const [errorPage, setErrorPage] = useState(1);
  const [errorTotal, setErrorTotal] = useState(0);
  const [selectedError, setSelectedError] = useState<ContainerErrorLog | null>(null);
  const [resolveDialogOpen, setResolveDialogOpen] = useState(false);
  const [resolveNotes, setResolveNotes] = useState("");

  // Helper to detect log level from line content
  const getLogLevel = (line: string): "error" | "warning" | "info" | "debug" => {
    const upper = line.toUpperCase();
    if (upper.includes("ERROR") || upper.includes("CRITICAL") || upper.includes("EXCEPTION")) return "error";
    if (upper.includes("WARNING") || upper.includes("WARN")) return "warning";
    if (upper.includes("DEBUG")) return "debug";
    return "info";
  };

  // Get color class for log level
  const getLogColor = (level: string): string => {
    switch (level) {
      case "error": return "text-red-400";
      case "warning": return "text-yellow-400";
      case "debug": return "text-zinc-500";
      default: return "text-zinc-100";
    }
  };

  // Filter logs by level
  const filteredLogs = logs.filter((line) => {
    if (logFilter === "all") return true;
    return getLogLevel(line) === logFilter;
  });

  // Fetch health status
  const fetchHealth = useCallback(async () => {
    try {
      const data = await api.health();
      setHealth(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error conectando al API");
    }
  }, []);

  // Fetch services status
  const fetchServices = useCallback(async () => {
    try {
      const data = await api.getSystemServices();
      setServices(data.services);
    } catch (err) {
      console.error("Error fetching services:", err);
    }
  }, []);

  // Fetch error logs
  const fetchErrorLogs = useCallback(async () => {
    try {
      const params: Record<string, string | number> = {
        page: errorPage,
        page_size: 20,
        status: errorFilter.status,
      };
      if (errorFilter.service) {
        params.service = errorFilter.service;
      }
      const data = await api.getContainerErrors(params);
      setErrorLogs(data.items);
      setErrorTotal(data.total);
    } catch (err) {
      console.error("Error fetching error logs:", err);
    }
  }, [errorPage, errorFilter]);

  // Fetch error stats
  const fetchErrorStats = useCallback(async () => {
    try {
      const stats = await api.getContainerErrorStats();
      setErrorStats(stats);
    } catch (err) {
      console.error("Error fetching error stats:", err);
    }
  }, []);

  // Initial load and periodic refresh
  useEffect(() => {
    async function loadData() {
      setIsLoading(true);
      await Promise.all([fetchHealth(), fetchServices(), fetchErrorStats()]);
      setIsLoading(false);
    }
    loadData();

    // Refresh every 30 seconds
    const interval = setInterval(() => {
      fetchHealth();
      fetchServices();
      fetchErrorStats();
    }, 30000);
    return () => clearInterval(interval);
  }, [fetchHealth, fetchServices, fetchErrorStats]);

  // Fetch error logs when filter or page changes
  useEffect(() => {
    fetchErrorLogs();
  }, [fetchErrorLogs]);

  // Start log streaming
  const startLogStream = useCallback(() => {
    // Close existing stream
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const token = api.getToken();
    if (!token) {
      toast.error("No hay sesion activa. Por favor, inicia sesion de nuevo.");
      return;
    }

    // Use relative URL to go through Next.js proxy (works with rewrites)
    // This ensures SSE works when accessing admin panel remotely
    const url = `/api/admin/system/${selectedLogService}/logs?tail=100&token=${encodeURIComponent(token)}`;

    const eventSource = new EventSource(url);

    eventSource.onopen = () => {
      setIsStreaming(true);
      setLogs([]); // Clear logs - historical logs will flow from Docker
    };

    eventSource.onmessage = (event) => {
      const line = event.data;
      if (line && !line.startsWith("Error:")) {
        setLogs((prev) => {
          const newLogs = [...prev, line];
          // Keep last 500 lines
          if (newLogs.length > 500) {
            return newLogs.slice(-500);
          }
          return newLogs;
        });
      } else if (line && line.startsWith("Error:")) {
        toast.error(line);
      }
    };

    eventSource.onerror = (err) => {
      console.error("EventSource error:", err);
      setIsStreaming(false);
      eventSource.close();
      toast.error("Conexion perdida con el servidor de logs");
    };

    eventSourceRef.current = eventSource;
  }, [selectedLogService]);

  // Stop log streaming
  const stopLogStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setIsStreaming(false);
  }, []);

  // Auto-scroll logs
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  // Restart when service changes
  useEffect(() => {
    if (isStreaming) {
      stopLogStream();
      startLogStream();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLogService]);

  // Service actions
  const handleServiceAction = async (action: "restart" | "stop") => {
    const service = confirmDialog.service;
    if (!service) return;

    setConfirmDialog({ open: false, service: null, action: "restart" });
    setActionInProgress(service);

    try {
      const result = action === "restart"
        ? await api.restartService(service)
        : await api.stopService(service);

      if (result.success) {
        toast.success(result.message);
        // Refresh services status
        await fetchServices();
      } else {
        toast.error(result.message);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Error ejecutando accion");
    } finally {
      setActionInProgress(null);
    }
  };

  const clearLogs = () => {
    setLogs([]);
  };

  // Resolve error
  const handleResolveError = async (status: "resolved" | "ignored") => {
    if (!selectedError) return;
    try {
      const result = await api.resolveContainerError(selectedError.id, {
        status,
        notes: resolveNotes || undefined,
      });
      if (result.success) {
        toast.success(result.message);
        setResolveDialogOpen(false);
        setSelectedError(null);
        setResolveNotes("");
        fetchErrorLogs();
        fetchErrorStats();
      } else {
        toast.error(result.message);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Error al resolver");
    }
  };

  // Delete error
  const handleDeleteError = async (errorId: string) => {
    try {
      const result = await api.deleteContainerError(errorId);
      if (result.success) {
        toast.success(result.message);
        fetchErrorLogs();
        fetchErrorStats();
      } else {
        toast.error(result.message);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Error al eliminar");
    }
  };

  return (
    <div className="space-y-6">
      {/* Health Status Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Estado General</CardTitle>
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <StatusIndicator status={health?.status || "unknown"} />
            )}
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold capitalize">
              {isLoading ? "..." : health?.status || "Desconocido"}
            </div>
            <p className="text-xs text-muted-foreground">Estado del API backend</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">PostgreSQL</CardTitle>
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <StatusIndicator status={health?.postgres || "unknown"} />
            )}
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold capitalize">
              {isLoading ? "..." : health?.postgres || "Desconocido"}
            </div>
            <p className="text-xs text-muted-foreground">Base de datos principal</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Redis</CardTitle>
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <StatusIndicator status={health?.redis || "unknown"} />
            )}
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold capitalize">
              {isLoading ? "..." : health?.redis || "Desconocido"}
            </div>
            <p className="text-xs text-muted-foreground">Cache y checkpointing</p>
          </CardContent>
        </Card>
      </div>

      {error && (
        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="pt-6">
            <p className="text-sm text-amber-800">
              <strong>Error:</strong> {error}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Services Control */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Control de Servicios</CardTitle>
              <CardDescription>
                Gestiona los contenedores Docker del sistema
              </CardDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                fetchHealth();
                fetchServices();
              }}
            >
              <RefreshCw className="mr-2 h-4 w-4" />
              Actualizar
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {services.map((service) => {
              const label = SERVICE_LABELS[service.name];
              const isCurrentService = actionInProgress === service.name;
              const canStop = service.name !== "api"; // Can't stop API from panel

              return (
                <div
                  key={service.name}
                  className="flex items-center justify-between border-b pb-4 last:border-0 last:pb-0"
                >
                  <div className="flex items-center gap-4">
                    <StatusIndicator status={service.status} />
                    <div>
                      <p className="font-medium">{label?.name || service.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {label?.description || service.container}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <ServiceStatusBadge status={service.status} health={service.health} />
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={isCurrentService}
                      onClick={() =>
                        setConfirmDialog({
                          open: true,
                          service: service.name,
                          action: "restart",
                        })
                      }
                    >
                      {isCurrentService ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <RefreshCw className="h-4 w-4" />
                      )}
                      <span className="ml-1 hidden sm:inline">Reiniciar</span>
                    </Button>
                    {canStop && (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={isCurrentService || service.status !== "running"}
                        onClick={() =>
                          setConfirmDialog({
                            open: true,
                            service: service.name,
                            action: "stop",
                          })
                        }
                      >
                        <Square className="h-4 w-4" />
                        <span className="ml-1 hidden sm:inline">Detener</span>
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}

            {services.length === 0 && !isLoading && (
              <p className="text-center text-muted-foreground py-4">
                No se pudieron cargar los servicios
              </p>
            )}

            {isLoading && (
              <div className="flex justify-center py-4">
                <Loader2 className="h-6 w-6 animate-spin" />
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Logs Section */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Logs en Tiempo Real</CardTitle>
              <CardDescription>
                Streaming de logs de los contenedores Docker
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Select
                value={selectedLogService}
                onValueChange={(value) => setSelectedLogService(value as SystemServiceName)}
              >
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="Seleccionar servicio" />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(SERVICE_LABELS).map(([key, label]) => (
                    <SelectItem key={key} value={key}>
                      {label.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={logFilter}
                onValueChange={(value) => setLogFilter(value as typeof logFilter)}
              >
                <SelectTrigger className="w-[120px]">
                  <SelectValue placeholder="Filtrar" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="error">Errores</SelectItem>
                  <SelectItem value="warning">Warnings</SelectItem>
                  <SelectItem value="info">Info</SelectItem>
                  <SelectItem value="debug">Debug</SelectItem>
                </SelectContent>
              </Select>
              {isStreaming ? (
                <Button variant="outline" size="sm" onClick={stopLogStream}>
                  <Pause className="mr-2 h-4 w-4" />
                  Pausar
                </Button>
              ) : (
                <Button variant="outline" size="sm" onClick={startLogStream}>
                  <Play className="mr-2 h-4 w-4" />
                  Iniciar
                </Button>
              )}
              <Button variant="ghost" size="sm" onClick={clearLogs}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[400px] w-full rounded-md border bg-zinc-950 p-4">
            <div className="font-mono text-xs">
              {logs.length === 0 ? (
                <p className="text-zinc-500">
                  {isStreaming
                    ? "Esperando logs..."
                    : "Pulsa 'Iniciar' para ver los logs en tiempo real"}
                </p>
              ) : filteredLogs.length === 0 ? (
                <p className="text-zinc-500">
                  No hay logs que coincidan con el filtro seleccionado
                </p>
              ) : (
                filteredLogs.map((line, index) => {
                  const level = getLogLevel(line);
                  return (
                    <div
                      key={index}
                      className={`whitespace-pre-wrap break-all hover:bg-zinc-900 py-0.5 ${getLogColor(level)}`}
                    >
                      {line}
                    </div>
                  );
                })
              )}
              <div ref={logsEndRef} />
            </div>
          </ScrollArea>
        </CardContent>
      </Card>

      {/* Error Logs Section */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-destructive" />
                Registro de Errores
                {errorStats && errorStats.total_open > 0 && (
                  <Badge variant="destructive">{errorStats.total_open} abiertos</Badge>
                )}
              </CardTitle>
              <CardDescription>
                Errores detectados en los contenedores Docker
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Select
                value={errorFilter.service || "all"}
                onValueChange={(value) =>
                  setErrorFilter((prev) => ({
                    ...prev,
                    service: value === "all" ? null : value,
                  }))
                }
              >
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="Servicio" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos los servicios</SelectItem>
                  {Object.entries(SERVICE_LABELS).map(([key, label]) => (
                    <SelectItem key={key} value={key}>
                      {label.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={errorFilter.status}
                onValueChange={(value) =>
                  setErrorFilter((prev) => ({
                    ...prev,
                    status: value as ContainerErrorStatus,
                  }))
                }
              >
                <SelectTrigger className="w-[140px]">
                  <SelectValue placeholder="Estado" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="open">Abiertos</SelectItem>
                  <SelectItem value="resolved">Resueltos</SelectItem>
                  <SelectItem value="ignored">Ignorados</SelectItem>
                </SelectContent>
              </Select>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  fetchErrorLogs();
                  fetchErrorStats();
                }}
              >
                <RefreshCw className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {errorLogs.length === 0 ? (
            <p className="text-center text-muted-foreground py-8">
              {errorFilter.status === "open"
                ? "No hay errores abiertos"
                : "No hay errores en este filtro"}
            </p>
          ) : (
            <div className="space-y-4">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Servicio</TableHead>
                    <TableHead>Nivel</TableHead>
                    <TableHead className="max-w-[400px]">Mensaje</TableHead>
                    <TableHead>Fecha</TableHead>
                    <TableHead className="w-[120px]">Acciones</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {errorLogs.map((error) => (
                    <TableRow key={error.id}>
                      <TableCell>
                        <Badge variant="outline">
                          {SERVICE_LABELS[error.service_name]?.name || error.service_name}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            error.level === "CRITICAL" || error.level === "FATAL"
                              ? "destructive"
                              : error.level === "ERROR"
                              ? "default"
                              : "secondary"
                          }
                        >
                          {error.level}
                        </Badge>
                      </TableCell>
                      <TableCell className="max-w-[400px]">
                        <button
                          className="text-left text-sm truncate block w-full hover:underline"
                          onClick={() => setSelectedError(error)}
                          title={error.message}
                        >
                          {error.message.substring(0, 100)}
                          {error.message.length > 100 && "..."}
                        </button>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground whitespace-nowrap">
                        {new Date(error.log_timestamp).toLocaleString()}
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setSelectedError(error)}
                            title="Ver detalle"
                          >
                            <Eye className="h-4 w-4" />
                          </Button>
                          {error.status === "open" && (
                            <>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => {
                                  setSelectedError(error);
                                  setResolveDialogOpen(true);
                                }}
                                title="Resolver"
                              >
                                <CheckCircle className="h-4 w-4 text-green-500" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={async () => {
                                  setSelectedError(error);
                                  await api.resolveContainerError(error.id, { status: "ignored" });
                                  toast.success("Error ignorado");
                                  fetchErrorLogs();
                                  fetchErrorStats();
                                  setSelectedError(null);
                                }}
                                title="Ignorar"
                              >
                                <Ban className="h-4 w-4 text-muted-foreground" />
                              </Button>
                            </>
                          )}
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDeleteError(error.id)}
                            title="Eliminar"
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {/* Pagination */}
              {errorTotal > 20 && (
                <div className="flex justify-center gap-2 pt-4">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={errorPage === 1}
                    onClick={() => setErrorPage((p) => p - 1)}
                  >
                    Anterior
                  </Button>
                  <span className="text-sm text-muted-foreground py-2">
                    Pagina {errorPage} de {Math.ceil(errorTotal / 20)}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={errorPage >= Math.ceil(errorTotal / 20)}
                    onClick={() => setErrorPage((p) => p + 1)}
                  >
                    Siguiente
                  </Button>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Error Detail Dialog */}
      <Dialog
        open={!!selectedError && !resolveDialogOpen}
        onOpenChange={(open) => {
          if (!open) setSelectedError(null);
        }}
      >
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Badge
                variant={
                  selectedError?.level === "CRITICAL" || selectedError?.level === "FATAL"
                    ? "destructive"
                    : "default"
                }
              >
                {selectedError?.level}
              </Badge>
              {selectedError && SERVICE_LABELS[selectedError.service_name]?.name}
            </DialogTitle>
            <DialogDescription>
              {selectedError && new Date(selectedError.log_timestamp).toLocaleString()}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <h4 className="font-semibold mb-2">Mensaje</h4>
              <p className="text-sm bg-muted p-3 rounded break-words">{selectedError?.message}</p>
            </div>
            {selectedError?.stack_trace && (
              <div>
                <h4 className="font-semibold mb-2">Stack Trace</h4>
                <pre className="text-xs bg-zinc-950 text-zinc-100 p-3 rounded overflow-auto max-h-[200px]">
                  {selectedError.stack_trace}
                </pre>
              </div>
            )}
            {selectedError?.context && Object.keys(selectedError.context).length > 0 && (
              <div>
                <h4 className="font-semibold mb-2">Contexto</h4>
                <pre className="text-xs bg-muted p-3 rounded overflow-auto max-h-[150px]">
                  {JSON.stringify(selectedError.context, null, 2)}
                </pre>
              </div>
            )}
            {selectedError?.resolved_by && (
              <div>
                <h4 className="font-semibold mb-2">Resolucion</h4>
                <p className="text-sm">
                  <strong>Estado:</strong> {selectedError.status}
                  <br />
                  <strong>Por:</strong> {selectedError.resolved_by}
                  <br />
                  <strong>Fecha:</strong>{" "}
                  {selectedError.resolved_at &&
                    new Date(selectedError.resolved_at).toLocaleString()}
                  {selectedError.resolution_notes && (
                    <>
                      <br />
                      <strong>Notas:</strong> {selectedError.resolution_notes}
                    </>
                  )}
                </p>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Resolve Error Dialog */}
      <AlertDialog open={resolveDialogOpen} onOpenChange={setResolveDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Marcar como resuelto</AlertDialogTitle>
            <AlertDialogDescription>
              Agrega notas opcionales sobre la resolucion de este error.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <Textarea
            className="min-h-[80px]"
            placeholder="Notas de resolucion (opcional)..."
            value={resolveNotes}
            onChange={(e) => setResolveNotes(e.target.value)}
          />
          <AlertDialogFooter>
            <AlertDialogCancel
              onClick={() => {
                setResolveNotes("");
                setSelectedError(null);
              }}
            >
              Cancelar
            </AlertDialogCancel>
            <AlertDialogAction onClick={() => handleResolveError("resolved")}>
              Marcar Resuelto
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Confirmation Dialog */}
      <AlertDialog
        open={confirmDialog.open}
        onOpenChange={(open) =>
          setConfirmDialog({ ...confirmDialog, open })
        }
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirmDialog.action === "restart"
                ? "Reiniciar servicio"
                : "Detener servicio"}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirmDialog.action === "restart" ? (
                <>
                  Estas seguro de que quieres reiniciar{" "}
                  <strong>
                    {confirmDialog.service &&
                      SERVICE_LABELS[confirmDialog.service]?.name}
                  </strong>
                  ? El servicio estara no disponible durante unos segundos.
                </>
              ) : (
                <>
                  Estas seguro de que quieres detener{" "}
                  <strong>
                    {confirmDialog.service &&
                      SERVICE_LABELS[confirmDialog.service]?.name}
                  </strong>
                  ? El servicio quedara inactivo hasta que lo reinicies
                  manualmente.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => handleServiceAction(confirmDialog.action)}
              className={
                confirmDialog.action === "stop"
                  ? "bg-destructive hover:bg-destructive/90"
                  : ""
              }
            >
              {confirmDialog.action === "restart" ? "Reiniciar" : "Detener"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
