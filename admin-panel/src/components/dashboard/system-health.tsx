"use client";

import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Server,
  CheckCircle2,
  RefreshCw,
  AlertCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import api from "@/lib/api";

type ServiceStatus = "healthy" | "degraded" | "unknown";

export function SystemHealth() {
  const [apiStatus, setApiStatus] = useState<ServiceStatus>("unknown");
  const [isLoading, setIsLoading] = useState(true);

  const fetchHealth = async () => {
    setIsLoading(true);
    try {
      await api.health();
      setApiStatus("healthy");
    } catch {
      setApiStatus("degraded");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 60000);
    return () => clearInterval(interval);
  }, []);

  const getStatusBadge = (status: ServiceStatus) => {
    if (status === "healthy") {
      return <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200 dark:bg-green-950/50 dark:text-green-400 dark:border-green-800">OK</Badge>;
    }
    if (status === "degraded") {
      return <Badge variant="destructive">Error</Badge>;
    }
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge variant="outline" className="cursor-help">Desconocido</Badge>
          </TooltipTrigger>
          <TooltipContent>
            <p>No se pudo obtener el estado. Puede estar cargando o sin conexión.</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">Estado del Sistema</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="animate-pulse space-y-3">
            <div className="h-8 bg-muted rounded" />
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-lg">Estado del Sistema</CardTitle>
            <CardDescription>Salud de servicios</CardDescription>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={fetchHealth}
            disabled={isLoading}
            className="h-8 w-8"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Server className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm">API</span>
          </div>
          {getStatusBadge(apiStatus)}
        </div>
      </CardContent>
    </Card>
  );
}
