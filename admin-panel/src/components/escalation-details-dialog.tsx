"use client";

import type { Escalation, EscalationSource, EscalationStatus } from "@/lib/types";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Card, CardContent } from "@/components/ui/card";
import {
  Clock,
  User,
  MessageSquare,
  ExternalLink,
  AlertTriangle,
  Phone,
  Bot,
  CheckCircle2,
  RefreshCw,
  FileCheck,
  Power,
} from "lucide-react";

interface EscalationDetailsDialogProps {
  escalation: Escalation | null;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EscalationDetailsDialog({
  escalation,
  isOpen,
  onOpenChange,
}: EscalationDetailsDialogProps) {
  if (!escalation) return null;

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString("es-ES", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  };

  const getTimeDuration = (start: string, end?: string | null) => {
    const startTime = new Date(start).getTime();
    const endTime = end ? new Date(end).getTime() : Date.now();
    const diff = endTime - startTime;

    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));

    if (days > 0) return `${days}d ${hours}h ${minutes}m`;
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
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

  const openChatwoot = () => {
    const chatwootBaseUrl = process.env.NEXT_PUBLIC_CHATWOOT_URL || "https://app.chatwoot.com";
    const chatwootAccountId = process.env.NEXT_PUBLIC_CHATWOOT_ACCOUNT_ID || "1";
    const chatwootUrl = `${chatwootBaseUrl}/app/accounts/${chatwootAccountId}/conversations/${escalation.conversation_id}`;
    window.open(chatwootUrl, "_blank");
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-xl">Detalles de Escalacion</DialogTitle>
          <DialogDescription>
            ID: {escalation.id.slice(0, 8)}...{escalation.id.slice(-4)}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Status and Source */}
          <div className="flex gap-2 items-center">
            {getStatusBadge(escalation.status)}
            {getSourceBadge(escalation.source)}
          </div>

          <Separator />

          {/* Reason - Full Text */}
          <div>
            <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-orange-500" />
              Motivo de Escalacion
            </h3>
            <Card>
              <CardContent className="pt-4">
                <p className="text-sm whitespace-pre-wrap leading-relaxed">
                  {escalation.reason}
                </p>
              </CardContent>
            </Card>
          </div>

          <Separator />

          {/* Context Information */}
          <div>
            <h3 className="text-sm font-semibold mb-3">Informacion de Contexto</h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  <MessageSquare className="h-3 w-3" />
                  Conversacion
                </p>
                <p className="text-sm font-medium">#{escalation.conversation_id}</p>
              </div>

              {escalation.user_phone && (
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground flex items-center gap-1">
                    <User className="h-3 w-3" />
                    Usuario
                  </p>
                  <p className="text-sm font-medium">{escalation.user_phone}</p>
                </div>
              )}

              <div className="space-y-1">
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  Disparada
                </p>
                <p className="text-sm font-medium">
                  {formatDate(escalation.triggered_at)}
                </p>
              </div>

              <div className="space-y-1">
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  Tiempo transcurrido
                </p>
                <p className="text-sm font-medium">
                  {getTimeDuration(escalation.triggered_at, escalation.resolved_at)}
                </p>
              </div>
            </div>
          </div>

          {/* Metadata if exists */}
          {escalation.metadata && Object.keys(escalation.metadata).length > 0 && (
            <>
              <Separator />
              <div>
                <h3 className="text-sm font-semibold mb-2">Metadata Adicional</h3>
                <Card>
                  <CardContent className="pt-4">
                    <pre className="text-xs bg-muted p-2 rounded overflow-x-auto">
                      {JSON.stringify(escalation.metadata, null, 2)}
                    </pre>
                  </CardContent>
                </Card>
              </div>
            </>
          )}

          {/* Resolution Info */}
          {escalation.status === "resolved" && escalation.resolved_at && (
            <>
              <Separator />
              <div>
                <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-green-600" />
                  Informacion de Resolucion
                </h3>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">Resuelta por</p>
                    <p className="text-sm font-medium">
                      {escalation.resolved_by || "Desconocido"}
                    </p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">Fecha de resolucion</p>
                    <p className="text-sm font-medium">
                      {formatDate(escalation.resolved_at)}
                    </p>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={openChatwoot}>
            <ExternalLink className="h-4 w-4 mr-2" />
            Abrir en Chatwoot
          </Button>
          <Button onClick={() => onOpenChange(false)}>Cerrar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
