"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { Bell, Clock, ExternalLink, Phone, Bot, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import api from "@/lib/api";
import type { Escalation, EscalationSource } from "@/lib/types";

export function EscalationNotifications() {
  const [escalations, setEscalations] = useState<Escalation[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isOpen, setIsOpen] = useState(false);

  const fetchEscalations = useCallback(async () => {
    try {
      setIsLoading(true);
      const [statsData, escalationsData] = await Promise.all([
        api.getEscalationStats(),
        api.getEscalations({ status: "pending", limit: 5 }),
      ]);
      setPendingCount(statsData.pending);
      setEscalations(escalationsData.items);
    } catch (error) {
      console.debug("Could not fetch escalations:", error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial fetch and polling every 30 seconds
  useEffect(() => {
    fetchEscalations();
    const interval = setInterval(fetchEscalations, 30000);
    return () => clearInterval(interval);
  }, [fetchEscalations]);

  // Refresh when popover opens
  useEffect(() => {
    if (isOpen) {
      fetchEscalations();
    }
  }, [isOpen, fetchEscalations]);

  const getTimeSince = (dateString: string) => {
    const diff = Date.now() - new Date(dateString).getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h`;
    const days = Math.floor(hours / 24);
    return `${days}d`;
  };

  const getSourceIcon = (source: EscalationSource) => {
    switch (source) {
      case "tool_call":
        return <Phone className="h-3 w-3" />;
      case "auto_escalation":
        return <Bot className="h-3 w-3" />;
      case "error":
        return <AlertTriangle className="h-3 w-3" />;
      default:
        return <Clock className="h-3 w-3" />;
    }
  };

  const openChatwoot = (conversationId: string) => {
    const chatwootUrl = process.env.NEXT_PUBLIC_CHATWOOT_URL || "http://localhost:3000";
    window.open(`${chatwootUrl}/app/accounts/1/conversations/${conversationId}`, "_blank");
  };

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative"
          aria-label={`${pendingCount} escalaciones pendientes`}
        >
          <Bell className="h-5 w-5" />
          {pendingCount > 0 && (
            <Badge
              variant="destructive"
              className="absolute -top-1 -right-1 h-5 min-w-[20px] px-1.5 text-xs font-bold"
            >
              {pendingCount > 99 ? "99+" : pendingCount}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between p-4 pb-2">
          <h4 className="font-semibold text-sm">Escalaciones Pendientes</h4>
          {pendingCount > 0 && (
            <Badge variant="destructive" className="text-xs">
              {pendingCount}
            </Badge>
          )}
        </div>
        <Separator />
        <div className="max-h-[300px] overflow-y-auto">
          {isLoading && escalations.length === 0 ? (
            <div className="p-4 text-center text-sm text-muted-foreground">
              Cargando...
            </div>
          ) : escalations.length === 0 ? (
            <div className="p-4 text-center">
              <div className="text-green-500 mb-2">
                <Bell className="h-8 w-8 mx-auto opacity-50" />
              </div>
              <p className="text-sm text-muted-foreground">
                No hay escalaciones pendientes
              </p>
            </div>
          ) : (
            <div className="divide-y">
              {escalations.map((escalation) => (
                <div
                  key={escalation.id}
                  className="p-3 hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-start gap-2">
                    <div
                      className={cn(
                        "mt-0.5 p-1 rounded",
                        escalation.source === "auto_escalation"
                          ? "bg-orange-100 text-orange-600 dark:bg-orange-900/30"
                          : escalation.source === "error"
                          ? "bg-red-100 text-red-600 dark:bg-red-900/30"
                          : "bg-blue-100 text-blue-600 dark:bg-blue-900/30"
                      )}
                    >
                      {getSourceIcon(escalation.source)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">
                        {escalation.reason}
                      </p>
                      <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        <span>{getTimeSince(escalation.triggered_at)}</span>
                        {escalation.user_phone && (
                          <>
                            <span>|</span>
                            <span>{escalation.user_phone}</span>
                          </>
                        )}
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 flex-shrink-0"
                      onClick={(e) => {
                        e.preventDefault();
                        openChatwoot(escalation.conversation_id);
                      }}
                      title="Abrir en Chatwoot"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        <Separator />
        <div className="p-2">
          <Link href="/escalations" onClick={() => setIsOpen(false)}>
            <Button variant="ghost" className="w-full justify-center text-sm">
              Ver todas las escalaciones
            </Button>
          </Link>
        </div>
      </PopoverContent>
    </Popover>
  );
}
