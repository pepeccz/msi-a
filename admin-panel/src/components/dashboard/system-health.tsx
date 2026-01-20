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
  Server,
  Database,
  Bot,
  BookOpen,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import api from "@/lib/api";
import type { RAGHealthStatus, ContainerErrorStats } from "@/lib/types";

interface HealthState {
  api: "healthy" | "degraded" | "unknown";
  rag: RAGHealthStatus | null;
  errors: ContainerErrorStats | null;
}

export function SystemHealth() {
  const [health, setHealth] = useState<HealthState>({
    api: "unknown",
    rag: null,
    errors: null,
  });
  const [isLoading, setIsLoading] = useState(true);

  const fetchHealth = async () => {
    setIsLoading(true);
    try {
      const [apiHealth, ragHealth, errorStats] = await Promise.allSettled([
        api.health(),
        api.getRagHealth(),
        api.getContainerErrorStats(),
      ]);

      setHealth({
        api: apiHealth.status === "fulfilled" ? "healthy" : "degraded",
        rag: ragHealth.status === "fulfilled" ? ragHealth.value : null,
        errors: errorStats.status === "fulfilled" ? errorStats.value : null,
      });
    } catch (error) {
      console.error("Error fetching system health:", error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
    // Refresh every 60 seconds
    const interval = setInterval(fetchHealth, 60000);
    return () => clearInterval(interval);
  }, []);

  const getStatusIcon = (status: "healthy" | "degraded" | "unknown" | boolean) => {
    if (status === "healthy" || status === true) {
      return <CheckCircle2 className="h-4 w-4 text-green-500" />;
    }
    if (status === "degraded" || status === false) {
      return <AlertCircle className="h-4 w-4 text-red-500" />;
    }
    return <RefreshCw className="h-4 w-4 text-muted-foreground animate-spin" />;
  };

  const getStatusBadge = (status: "healthy" | "degraded" | "unknown" | boolean) => {
    if (status === "healthy" || status === true) {
      return <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200 dark:bg-green-950/50 dark:text-green-400 dark:border-green-800">OK</Badge>;
    }
    if (status === "degraded" || status === false) {
      return <Badge variant="destructive">Error</Badge>;
    }
    return <Badge variant="outline">...</Badge>;
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">Estado del Sistema</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="animate-pulse space-y-3">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-8 bg-muted rounded" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  const openErrorsCount = health.errors?.total_open || 0;

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
        {/* API Status */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Server className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm">API</span>
          </div>
          {getStatusBadge(health.api)}
        </div>

        {/* RAG Status */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm">RAG</span>
          </div>
          {health.rag ? (
            <div className="flex items-center gap-2">
              {getStatusBadge(health.rag.status === "healthy")}
              {health.rag.components.qdrant_collection && (
                <span className="text-xs text-muted-foreground">
                  ({health.rag.components.qdrant_collection.points_count} docs)
                </span>
              )}
            </div>
          ) : (
            getStatusBadge("unknown")
          )}
        </div>

        {/* RAG Components */}
        {health.rag && (
          <div className="pl-6 space-y-2 border-l-2 border-muted ml-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Embeddings</span>
              {getStatusIcon(health.rag.components.embedding_service)}
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Qdrant</span>
              {getStatusIcon(health.rag.components.qdrant)}
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Reranker</span>
              {getStatusIcon(health.rag.components.reranker)}
            </div>
          </div>
        )}

        {/* Errors */}
        <div className="flex items-center justify-between pt-2 border-t">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm">Errores abiertos</span>
          </div>
          {openErrorsCount > 0 ? (
            <Badge variant="destructive">{openErrorsCount}</Badge>
          ) : (
            <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200 dark:bg-green-950/50 dark:text-green-400 dark:border-green-800">
              0
            </Badge>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
