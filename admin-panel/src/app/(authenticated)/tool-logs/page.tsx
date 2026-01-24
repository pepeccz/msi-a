"use client";

import { useState, useEffect, useCallback } from "react";
import { Search, Terminal, Clock, AlertCircle, CheckCircle, XCircle } from "lucide-react";
import api from "@/lib/api";
import type { ToolCallLog, ToolLogStats, PaginatedToolLogs } from "@/lib/types";

const RESULT_BADGES: Record<string, { icon: typeof CheckCircle; color: string; label: string }> = {
  success: { icon: CheckCircle, color: "text-green-600 bg-green-50", label: "OK" },
  error: { icon: XCircle, color: "text-red-600 bg-red-50", label: "Error" },
  blocked: { icon: AlertCircle, color: "text-yellow-600 bg-yellow-50", label: "Bloqueado" },
};

export default function ToolLogsPage() {
  const [logs, setLogs] = useState<ToolCallLog[]>([]);
  const [stats, setStats] = useState<ToolLogStats[]>([]);
  const [total, setTotal] = useState(0);
  const [toolNames, setToolNames] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Filters
  const [conversationId, setConversationId] = useState("");
  const [selectedTool, setSelectedTool] = useState("");
  const [selectedResult, setSelectedResult] = useState("");
  const [page, setPage] = useState(0);
  const LIMIT = 30;

  const loadData = useCallback(async () => {
    try {
      setIsLoading(true);
      const [logsData, statsData, names] = await Promise.all([
        api.getToolLogs({
          conversation_id: conversationId || undefined,
          tool_name: selectedTool || undefined,
          result_type: selectedResult || undefined,
          skip: page * LIMIT,
          limit: LIMIT,
        }),
        api.getToolLogStats(),
        api.getToolNames(),
      ]);
      setLogs(logsData.items);
      setTotal(logsData.total);
      setStats(statsData);
      setToolNames(names);
    } catch (error) {
      console.error("Error loading tool logs:", error);
    } finally {
      setIsLoading(false);
    }
  }, [conversationId, selectedTool, selectedResult, page]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleSearch = () => {
    setPage(0);
    loadData();
  };

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Terminal className="h-6 w-6" />
          Tool Call Logs
        </h1>
        <p className="text-muted-foreground mt-1">
          Registro de todas las llamadas a herramientas del agente para debugging
        </p>
      </div>

      {/* Stats Overview */}
      {stats.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {stats.slice(0, 6).map((stat) => (
            <div key={stat.tool_name} className="border rounded-lg p-3 bg-card">
              <p className="text-xs font-mono truncate" title={stat.tool_name}>
                {stat.tool_name.replace(/_/g, " ")}
              </p>
              <div className="flex items-baseline gap-1 mt-1">
                <span className="text-lg font-bold">{stat.total_calls}</span>
                <span className="text-xs text-muted-foreground">calls</span>
              </div>
              <div className="flex gap-2 text-xs mt-1">
                {stat.error_count > 0 && (
                  <span className="text-red-600">{stat.error_count} err</span>
                )}
                {stat.avg_execution_ms && (
                  <span className="text-muted-foreground">{Math.round(stat.avg_execution_ms)}ms</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-end">
        <div>
          <label className="text-xs text-muted-foreground">Conversation ID</label>
          <div className="flex gap-1 mt-1">
            <input
              type="text"
              value={conversationId}
              onChange={(e) => setConversationId(e.target.value)}
              placeholder="ID de conversacion"
              className="px-3 py-1.5 border rounded-md bg-background text-sm w-36"
            />
          </div>
        </div>
        <div>
          <label className="text-xs text-muted-foreground">Tool</label>
          <select
            value={selectedTool}
            onChange={(e) => { setSelectedTool(e.target.value); setPage(0); }}
            className="block mt-1 px-3 py-1.5 border rounded-md bg-background text-sm"
          >
            <option value="">Todos</option>
            {toolNames.map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs text-muted-foreground">Resultado</label>
          <select
            value={selectedResult}
            onChange={(e) => { setSelectedResult(e.target.value); setPage(0); }}
            className="block mt-1 px-3 py-1.5 border rounded-md bg-background text-sm"
          >
            <option value="">Todos</option>
            <option value="success">Success</option>
            <option value="error">Error</option>
            <option value="blocked">Blocked</option>
          </select>
        </div>
        <button
          onClick={handleSearch}
          className="flex items-center gap-1 px-3 py-1.5 bg-primary text-primary-foreground rounded-md text-sm"
        >
          <Search className="h-3 w-3" />
          Buscar
        </button>
        <span className="text-xs text-muted-foreground self-center">
          {total} resultados
        </span>
      </div>

      {/* Logs Table */}
      {isLoading ? (
        <p className="text-muted-foreground">Cargando...</p>
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="text-left p-2 font-medium">Timestamp</th>
                <th className="text-left p-2 font-medium">Conv ID</th>
                <th className="text-left p-2 font-medium">Tool</th>
                <th className="text-left p-2 font-medium">Resultado</th>
                <th className="text-left p-2 font-medium">Tiempo</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => {
                const badge = RESULT_BADGES[log.result_type] || RESULT_BADGES.success;
                const BadgeIcon = badge.icon;
                const isExpanded = expandedId === log.id;

                return (
                  <>
                    <tr
                      key={log.id}
                      onClick={() => setExpandedId(isExpanded ? null : log.id)}
                      className="border-t hover:bg-muted/30 cursor-pointer"
                    >
                      <td className="p-2 text-xs font-mono text-muted-foreground">
                        {new Date(log.timestamp).toLocaleString("es-ES", { 
                          day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" 
                        })}
                      </td>
                      <td className="p-2 font-mono text-xs">{log.conversation_id}</td>
                      <td className="p-2 font-mono text-xs">{log.tool_name}</td>
                      <td className="p-2">
                        <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs ${badge.color}`}>
                          <BadgeIcon className="h-3 w-3" />
                          {badge.label}
                        </span>
                      </td>
                      <td className="p-2 text-xs text-muted-foreground">
                        {log.execution_time_ms ? (
                          <span className="flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            {log.execution_time_ms}ms
                          </span>
                        ) : "-"}
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr key={`${log.id}-detail`} className="border-t bg-muted/20">
                        <td colSpan={5} className="p-3">
                          <div className="space-y-2 text-xs">
                            {log.parameters && (
                              <div>
                                <span className="font-medium">Parametros:</span>
                                <pre className="mt-1 p-2 bg-background rounded overflow-x-auto">
                                  {JSON.stringify(log.parameters, null, 2)}
                                </pre>
                              </div>
                            )}
                            {log.result_summary && (
                              <div>
                                <span className="font-medium">Resultado:</span>
                                <pre className="mt-1 p-2 bg-background rounded overflow-x-auto whitespace-pre-wrap">
                                  {log.result_summary}
                                </pre>
                              </div>
                            )}
                            {log.error_message && (
                              <div>
                                <span className="font-medium text-red-600">Error:</span>
                                <pre className="mt-1 p-2 bg-red-50 rounded overflow-x-auto whitespace-pre-wrap">
                                  {log.error_message}
                                </pre>
                              </div>
                            )}
                            <p className="text-muted-foreground">
                              Iteracion: {log.iteration} | Full timestamp: {log.timestamp}
                            </p>
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
              {logs.length === 0 && (
                <tr>
                  <td colSpan={5} className="p-8 text-center text-muted-foreground">
                    No hay logs disponibles
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {total > LIMIT && (
        <div className="flex justify-center gap-2">
          <button
            onClick={() => setPage(Math.max(0, page - 1))}
            disabled={page === 0}
            className="px-3 py-1 border rounded text-sm disabled:opacity-50"
          >
            Anterior
          </button>
          <span className="px-3 py-1 text-sm text-muted-foreground">
            Pagina {page + 1} de {Math.ceil(total / LIMIT)}
          </span>
          <button
            onClick={() => setPage(page + 1)}
            disabled={(page + 1) * LIMIT >= total}
            className="px-3 py-1 border rounded text-sm disabled:opacity-50"
          >
            Siguiente
          </button>
        </div>
      )}
    </div>
  );
}
