"use client";

import type { ConversationHistory } from "@/lib/types";
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
import {
  Clock,
  User,
  MessageSquare,
  ExternalLink,
  Phone,
  Hash,
  Calendar,
  FileText,
} from "lucide-react";
import { useRouter } from "next/navigation";
import Link from "next/link";

interface ConversationDetailsDialogProps {
  conversation: ConversationHistory | null;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ConversationDetailsDialog({
  conversation,
  isOpen,
  onOpenChange,
}: ConversationDetailsDialogProps) {
  const router = useRouter();

  if (!conversation) return null;

  const formatDateTime = (dateString: string) => {
    return new Date(dateString).toLocaleString("es-ES", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
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

  const openChatwoot = () => {
    window.open(conversation.chatwoot_url, "_blank");
  };

  const goToDetails = () => {
    onOpenChange(false);
    router.push(`/conversations/${conversation.id}`);
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-xl">Detalles de Conversacion</DialogTitle>
          <DialogDescription>
            Chatwoot #{conversation.conversation_id}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Status Badge */}
          <div className="flex gap-2 items-center">
            <Badge variant="secondary">
              <MessageSquare className="h-3 w-3 mr-1" />
              {conversation.message_count} mensajes
            </Badge>
            {conversation.ended_at ? (
              <Badge variant="outline">Finalizada</Badge>
            ) : (
              <Badge variant="default">Activa</Badge>
            )}
          </div>

          <Separator />

          {/* User Information */}
          <div>
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <User className="h-4 w-4" />
              Usuario
            </h3>
            {conversation.user_id ? (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm">
                    {conversation.user_name || "Sin nombre"}
                  </span>
                </div>
                {conversation.user_phone && (
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Phone className="h-3 w-3" />
                    <span className="text-sm">{conversation.user_phone}</span>
                  </div>
                )}
                <Link
                  href={`/users/${conversation.user_id}`}
                  className="text-sm text-primary hover:underline inline-flex items-center gap-1"
                  onClick={() => onOpenChange(false)}
                >
                  Ver perfil completo
                  <ExternalLink className="h-3 w-3" />
                </Link>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Sin usuario asociado
              </p>
            )}
          </div>

          <Separator />

          {/* Time Information */}
          <div>
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <Clock className="h-4 w-4" />
              Tiempos
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  <Calendar className="h-3 w-3" />
                  Inicio
                </p>
                <p className="text-sm font-medium">
                  {formatDateTime(conversation.started_at)}
                </p>
              </div>

              <div className="space-y-1">
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  <Calendar className="h-3 w-3" />
                  {conversation.ended_at ? "Fin" : "Duracion"}
                </p>
                <p className="text-sm font-medium">
                  {conversation.ended_at
                    ? formatDateTime(conversation.ended_at)
                    : getTimeDuration(conversation.started_at)}
                </p>
              </div>
            </div>
          </div>

          {/* Summary if exists */}
          {conversation.summary && (
            <>
              <Separator />
              <div>
                <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  Resumen
                </h3>
                <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                  {conversation.summary}
                </p>
              </div>
            </>
          )}

          {/* IDs */}
          <Separator />
          <div>
            <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
              <Hash className="h-4 w-4" />
              Identificadores
            </h3>
            <div className="space-y-1 text-xs text-muted-foreground">
              <p>ID interno: {conversation.id}</p>
              <p>ID Chatwoot: {conversation.conversation_id}</p>
            </div>
          </div>
        </div>

        <DialogFooter className="gap-2 sm:gap-2">
          <Button variant="outline" onClick={openChatwoot}>
            <ExternalLink className="h-4 w-4 mr-2" />
            Abrir en Chatwoot
          </Button>
          <Button onClick={goToDetails}>Ver detalles completos</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
