"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/auth-context";
import { api } from "@/lib/api";
import type {
  LLMMetricsSummary,
  LLMProviderHealth,
  LLMHybridConfig,
} from "@/lib/types";
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
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import {
  Shield,
  Cpu,
  Cloud,
  TrendingDown,
  Activity,
  Clock,
  CheckCircle2,
  XCircle,
  Server,
  Zap,
  DollarSign,
  ArrowRight,
} from "lucide-react";

function formatNumber(num: number): string {
  if (num >= 1_000_000) {
    return (num / 1_000_000).toFixed(2) + "M";
  }
  if (num >= 1_000) {
    return (num / 1_000).toFixed(1) + "K";
  }
  return num.toLocaleString("es-ES");
}

function formatUsd(value: string | number | null): string {
  if (value === null) return "$0.00";
  const num = typeof value === "string" ? parseFloat(value) : value;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(num);
}

function getTierBadgeColor(tier: string): string {
  switch (tier) {
    case "local_fast":
      return "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200";
    case "local_capable":
      return "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200";
    case "cloud_standard":
      return "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200";
    case "cloud_advanced":
      return "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200";
    default:
      return "bg-gray-100 text-gray-800";
  }
}

function getTierLabel(tier: string): string {
  const labels: Record<string, string> = {
    local_fast: "Local Rapido",
    local_capable: "Local Capaz",
    cloud_standard: "Cloud Estandar",
    cloud_advanced: "Cloud Avanzado",
  };
  return labels[tier] || tier;
}

function getTaskTypeLabel(taskType: string): string {
  const labels: Record<string, string> = {
    classification: "Clasificacion",
    extraction: "Extraccion",
    rag_simple: "RAG Simple",
    rag_complex: "RAG Complejo",
    conversation: "Conversacion",
    tool_calling: "Herramientas",
    summarization: "Resumen",
    translation: "Traduccion",
  };
  return labels[taskType] || taskType;
}

export default function LLMMetricsPage() {
  const { isAdmin } = useAuth();
  const [loading, setLoading] = useState(true);
  const [metrics, setMetrics] = useState<LLMMetricsSummary | null>(null);
  const [health, setHealth] = useState<LLMProviderHealth | null>(null);
  const [config, setConfig] = useState<LLMHybridConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState("7");

  useEffect(() => {
    if (!isAdmin) return;

    async function fetchData() {
      setLoading(true);
      setError(null);

      try {
        const [metricsData, healthData, configData] = await Promise.all([
          api.getLLMMetricsSummary(parseInt(days)),
          api.getLLMMetricsHealth(),
          api.getLLMMetricsConfig(),
        ]);

        setMetrics(metricsData);
        setHealth(healthData);
        setConfig(configData);
      } catch (err) {
        console.error("Failed to fetch LLM metrics:", err);
        setError("Error al cargar las metricas LLM");
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, [isAdmin, days]);

  if (!isAdmin) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12">
          <Shield className="h-12 w-12 text-muted-foreground mb-4" />
          <p className="text-muted-foreground text-center">
            No tienes permisos para acceder a esta seccion.
          </p>
        </CardContent>
      </Card>
    );
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <Card key={i}>
              <CardHeader className="pb-2">
                <Skeleton className="h-4 w-24" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-8 w-32" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12">
          <XCircle className="h-12 w-12 text-destructive mb-4" />
          <p className="text-destructive">{error}</p>
        </CardContent>
      </Card>
    );
  }

  const savings = metrics?.cost_savings;
  const localPercentage = savings?.local_percentage || 0;

  return (
    <div className="space-y-6">
      {/* Header with period selector */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Metricas LLM Hibrido</h1>
          <p className="text-muted-foreground">
            Monitoreo de la arquitectura hibrida local + cloud
          </p>
        </div>
        <Select value={days} onValueChange={setDays}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Periodo" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="1">Ultimo dia</SelectItem>
            <SelectItem value="7">Ultimos 7 dias</SelectItem>
            <SelectItem value="30">Ultimos 30 dias</SelectItem>
            <SelectItem value="90">Ultimos 90 dias</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Provider Health Status */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Ollama (Local)</CardTitle>
            <Cpu className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              {health?.ollama.status === "healthy" ? (
                <>
                  <CheckCircle2 className="h-5 w-5 text-green-500" />
                  <span className="text-green-600 font-medium">Operativo</span>
                </>
              ) : (
                <>
                  <XCircle className="h-5 w-5 text-red-500" />
                  <span className="text-red-600 font-medium">No disponible</span>
                </>
              )}
            </div>
            {health?.ollama.models_available && (
              <p className="text-xs text-muted-foreground mt-2">
                Modelos: {health.ollama.models_available.slice(0, 3).join(", ")}
                {health.ollama.models_available.length > 3 && "..."}
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">OpenRouter (Cloud)</CardTitle>
            <Cloud className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              {health?.openrouter.status === "healthy" ? (
                <>
                  <CheckCircle2 className="h-5 w-5 text-green-500" />
                  <span className="text-green-600 font-medium">Operativo</span>
                </>
              ) : (
                <>
                  <XCircle className="h-5 w-5 text-red-500" />
                  <span className="text-red-600 font-medium">No disponible</span>
                </>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              Modelo: {config?.tiers.cloud_standard?.model || "gpt-4o-mini"}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Cost Savings Summary */}
      <Card className="border-green-200 dark:border-green-900">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingDown className="h-5 w-5 text-green-500" />
            Ahorro por Arquitectura Hibrida
          </CardTitle>
          <CardDescription>
            Comparacion de costes: hibrido vs 100% cloud
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="text-center">
              <div className="text-3xl font-bold text-green-600">
                {savings?.savings_percentage.toFixed(1)}%
              </div>
              <p className="text-sm text-muted-foreground">Ahorro</p>
            </div>
            <div className="text-center">
              <div className="text-2xl font-semibold">
                {formatUsd(savings?.estimated_savings_usd || "0")}
              </div>
              <p className="text-sm text-muted-foreground">Ahorro USD</p>
            </div>
            <div className="text-center">
              <div className="text-2xl font-semibold">
                {formatUsd(savings?.actual_cost_usd || "0")}
              </div>
              <p className="text-sm text-muted-foreground">Coste Real</p>
            </div>
            <div className="text-center">
              <div className="text-2xl font-semibold text-muted-foreground">
                {formatUsd(savings?.hypothetical_cloud_cost_usd || "0")}
              </div>
              <p className="text-sm text-muted-foreground">Si fuera 100% Cloud</p>
            </div>
          </div>

          {/* Local vs Cloud Distribution */}
          <div className="mt-6">
            <div className="flex justify-between text-sm mb-2">
              <span className="flex items-center gap-1">
                <Cpu className="h-4 w-4" /> Local: {localPercentage.toFixed(1)}%
              </span>
              <span className="flex items-center gap-1">
                <Cloud className="h-4 w-4" /> Cloud: {(100 - localPercentage).toFixed(1)}%
              </span>
            </div>
            <Progress value={localPercentage} className="h-3" />
            <div className="flex justify-between text-xs text-muted-foreground mt-1">
              <span>{formatNumber(savings?.local_calls || 0)} llamadas</span>
              <span>{formatNumber(savings?.cloud_calls || 0)} llamadas</span>
            </div>
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="tiers" className="space-y-4">
        <TabsList>
          <TabsTrigger value="tiers">Por Tier</TabsTrigger>
          <TabsTrigger value="tasks">Por Tipo de Tarea</TabsTrigger>
          <TabsTrigger value="config">Configuracion</TabsTrigger>
        </TabsList>

        {/* Tier Statistics */}
        <TabsContent value="tiers">
          <Card>
            <CardHeader>
              <CardTitle>Estadisticas por Tier</CardTitle>
              <CardDescription>
                Rendimiento y uso de cada nivel de modelo
              </CardDescription>
            </CardHeader>
            <CardContent>
              {metrics?.tier_stats.length === 0 ? (
                <p className="text-center text-muted-foreground py-8">
                  No hay datos de metricas para el periodo seleccionado
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Tier</TableHead>
                      <TableHead>Proveedor</TableHead>
                      <TableHead className="text-right">Llamadas</TableHead>
                      <TableHead className="text-right">Exito</TableHead>
                      <TableHead className="text-right">Latencia</TableHead>
                      <TableHead className="text-right">Tokens</TableHead>
                      <TableHead className="text-right">Coste</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {metrics?.tier_stats.map((stat) => (
                      <TableRow key={`${stat.tier}-${stat.provider}`}>
                        <TableCell>
                          <Badge className={getTierBadgeColor(stat.tier)}>
                            {getTierLabel(stat.tier)}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {stat.provider === "ollama" ? (
                            <span className="flex items-center gap-1">
                              <Cpu className="h-4 w-4" /> Ollama
                            </span>
                          ) : (
                            <span className="flex items-center gap-1">
                              <Cloud className="h-4 w-4" /> OpenRouter
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="text-right">
                          {formatNumber(stat.total_calls)}
                        </TableCell>
                        <TableCell className="text-right">
                          <span className={stat.success_rate >= 95 ? "text-green-600" : stat.success_rate >= 80 ? "text-yellow-600" : "text-red-600"}>
                            {stat.success_rate.toFixed(1)}%
                          </span>
                        </TableCell>
                        <TableCell className="text-right">
                          {stat.avg_latency_ms.toFixed(0)}ms
                        </TableCell>
                        <TableCell className="text-right">
                          {formatNumber((stat.total_input_tokens || 0) + (stat.total_output_tokens || 0))}
                        </TableCell>
                        <TableCell className="text-right font-medium">
                          {formatUsd(stat.estimated_cost_usd)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Task Type Statistics */}
        <TabsContent value="tasks">
          <Card>
            <CardHeader>
              <CardTitle>Estadisticas por Tipo de Tarea</CardTitle>
              <CardDescription>
                Distribucion de llamadas local vs cloud por tipo de tarea
              </CardDescription>
            </CardHeader>
            <CardContent>
              {metrics?.task_type_stats.length === 0 ? (
                <p className="text-center text-muted-foreground py-8">
                  No hay datos de metricas para el periodo seleccionado
                </p>
              ) : (
                <div className="space-y-4">
                  {metrics?.task_type_stats.map((stat) => (
                    <div key={stat.task_type} className="border rounded-lg p-4">
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-medium">
                          {getTaskTypeLabel(stat.task_type)}
                        </span>
                        <span className="text-sm text-muted-foreground">
                          {formatNumber(stat.total_calls)} llamadas | {stat.avg_latency_ms.toFixed(0)}ms avg
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Progress value={stat.local_percentage} className="flex-1 h-2" />
                        <span className="text-sm w-16 text-right">
                          {stat.local_percentage.toFixed(0)}% local
                        </span>
                      </div>
                      <div className="flex justify-between text-xs text-muted-foreground mt-1">
                        <span className="flex items-center gap-1">
                          <Cpu className="h-3 w-3" /> {formatNumber(stat.local_calls)}
                        </span>
                        <span className="flex items-center gap-1">
                          <Cloud className="h-3 w-3" /> {formatNumber(stat.cloud_calls)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Fallback Statistics */}
          <Card className="mt-4">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Activity className="h-5 w-5" />
                Fallbacks
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-8">
                <div>
                  <div className="text-2xl font-bold">
                    {metrics?.fallback_count || 0}
                  </div>
                  <p className="text-sm text-muted-foreground">Total fallbacks</p>
                </div>
                <div>
                  <div className="text-2xl font-bold">
                    {(metrics?.fallback_rate || 0).toFixed(2)}%
                  </div>
                  <p className="text-sm text-muted-foreground">Tasa de fallback</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Configuration */}
        <TabsContent value="config">
          <Card>
            <CardHeader>
              <CardTitle>Configuracion Actual</CardTitle>
              <CardDescription>
                Ajustes de la arquitectura hibrida LLM
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-6">
                {/* Status */}
                <div className="flex items-center gap-2">
                  <span className="font-medium">Arquitectura Hibrida:</span>
                  {config?.hybrid_enabled ? (
                    <Badge className="bg-green-100 text-green-800">Activada</Badge>
                  ) : (
                    <Badge variant="secondary">Desactivada</Badge>
                  )}
                </div>

                {/* Tier Configuration */}
                <div>
                  <h3 className="font-medium mb-3">Tiers de Modelos</h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {Object.entries(config?.tiers || {}).map(([tier, info]) => (
                      <div key={tier} className="border rounded-lg p-4">
                        <Badge className={getTierBadgeColor(tier)}>
                          {getTierLabel(tier)}
                        </Badge>
                        <p className="mt-2 font-mono text-sm">{info.model}</p>
                        <div className="mt-2 flex flex-wrap gap-1">
                          {info.tasks.map((task) => (
                            <Badge key={task} variant="outline" className="text-xs">
                              {getTaskTypeLabel(task)}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Routing Configuration */}
                <div>
                  <h3 className="font-medium mb-3">Routing por Componente</h3>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Componente</TableHead>
                        <TableHead>Usa Local</TableHead>
                        <TableHead>Modelo</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {Object.entries(config?.routing || {}).map(([component, routing]) => (
                        <TableRow key={component}>
                          <TableCell className="font-medium">
                            {component.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase())}
                          </TableCell>
                          <TableCell>
                            {routing.use_local ? (
                              <CheckCircle2 className="h-5 w-5 text-green-500" />
                            ) : (
                              <XCircle className="h-5 w-5 text-muted-foreground" />
                            )}
                          </TableCell>
                          <TableCell className="font-mono text-sm">
                            {routing.model}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>

                {/* Metrics Config */}
                <div className="flex items-center gap-6">
                  <div>
                    <span className="font-medium">Metricas:</span>{" "}
                    {config?.metrics_enabled ? "Activadas" : "Desactivadas"}
                  </div>
                  <div>
                    <span className="font-medium">Retencion:</span>{" "}
                    {config?.metrics_retention_days} dias
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
