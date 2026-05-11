"use client";

import { useState, useCallback } from "react";
import {
  User,
  Phone,
  Mail,
  Tag,
  FileText,
  AlertTriangle,
  CheckCircle2,
  Clock,
  StickyNote,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { sileo } from "sileo";
import { formatDistanceToNow } from "date-fns";
import { es } from "date-fns/locale";
import { cn } from "@/lib/utils";
import api from "@/lib/api";
import type { InboxItemResponse, EscalationStatusInbox } from "@/lib/types";

interface ClientCardProps {
  conversation: InboxItemResponse;
  onConversationUpdated: () => void;
}

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true, locale: es });
  } catch {
    return "—";
  }
}

function EscalationStatusBadge({ status }: { status: EscalationStatusInbox }) {
  if (status === "none") return null;
  if (status === "pending") {
    return (
      <Badge variant="outline" className="gap-1 border-red-400 text-red-600 text-xs">
        <AlertTriangle className="h-3 w-3" />
        Pendiente
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="gap-1 border-orange-400 text-orange-600 text-xs">
      <Clock className="h-3 w-3" />
      En gestión
    </Badge>
  );
}

interface CollapsibleSectionProps {
  title: string;
  icon: React.ReactNode;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

function CollapsibleSection({
  title,
  icon,
  defaultOpen = true,
  children,
}: CollapsibleSectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div>
      <button
        type="button"
        onClick={() => setIsOpen((o) => !o)}
        className="flex items-center justify-between w-full py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
      >
        <span className="flex items-center gap-1.5">
          {icon}
          {title}
        </span>
        {isOpen ? (
          <ChevronUp className="h-3.5 w-3.5" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5" />
        )}
      </button>
      {isOpen && <div className="pb-2">{children}</div>}
    </div>
  );
}

interface EscalationCardProps {
  conversationHistoryId: string;
  escalationStatus: EscalationStatusInbox;
  onUpdated: () => void;
}

function EscalationCard({
  conversationHistoryId,
  escalationStatus,
  onUpdated,
}: EscalationCardProps) {
  const [isResolving, setIsResolving] = useState(false);

  const handleResolve = useCallback(async () => {
    // Resolve via the existing escalations API (legacy endpoint, maintained)
    // The PR5 spec marks "Resolver" as available but deferred implementation detail.
    // We show a placeholder since the resolve endpoint belongs to the legacy /escalations router.
    sileo.info({ title: "Próximamente", description: "Resolución disponible en /escalaciones" });
    onUpdated();
  }, [onUpdated]);

  return (
    <div className="rounded-lg border border-red-200 bg-red-50/50 p-3 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-red-800 flex items-center gap-1.5">
          <AlertTriangle className="h-4 w-4" />
          Escalación activa
        </span>
        <EscalationStatusBadge status={escalationStatus} />
      </div>

      <div className="flex gap-2">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                <Button
                  size="sm"
                  variant="outline"
                  className="text-xs"
                  disabled
                >
                  Asignarme
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent>Próximamente</TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <Button
          size="sm"
          variant="outline"
          className="text-xs border-green-400 text-green-700 hover:bg-green-50"
          onClick={handleResolve}
          disabled={isResolving}
        >
          <CheckCircle2 className="h-3 w-3 mr-1" />
          {isResolving ? "Resolviendo..." : "Resolver"}
        </Button>
      </div>
    </div>
  );
}

export function ClientCard({
  conversation,
  onConversationUpdated,
}: ClientCardProps) {
  const hasEscalation = conversation.escalation_status !== "none";

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="p-4 space-y-4">
        {/* Client info header */}
        <div className="space-y-3">
          {/* Avatar + name */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center flex-shrink-0">
              <User className="h-5 w-5 text-muted-foreground" />
            </div>
            <div className="min-w-0">
              <p className="font-semibold text-sm truncate">
                {conversation.user_name ?? "Sin nombre"}
              </p>
              <p className="text-xs text-muted-foreground">Cliente</p>
            </div>
          </div>

          {/* Contact fields */}
          <div className="space-y-1.5 text-sm">
            {conversation.user_phone && (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Phone className="h-3.5 w-3.5 flex-shrink-0" />
                <span className="truncate">{conversation.user_phone}</span>
              </div>
            )}
          </div>

          {/* Last activity */}
          <div className="text-xs text-muted-foreground">
            Última actividad: {formatRelative(conversation.last_message_at)}
          </div>
        </div>

        <Separator />

        {/* Escalation card */}
        {hasEscalation && (
          <>
            <EscalationCard
              conversationHistoryId={conversation.conversation_history_id}
              escalationStatus={conversation.escalation_status}
              onUpdated={onConversationUpdated}
            />
            <Separator />
          </>
        )}

        {/* Sections */}
        <CollapsibleSection
          title="Expediente activo"
          icon={<FileText className="h-3.5 w-3.5" />}
          defaultOpen
        >
          <div className="rounded-md bg-muted/30 p-3 text-sm text-muted-foreground">
            <p className="text-xs">Sin expediente activo</p>
            <p className="text-[10px] mt-1 opacity-70">
              La ficha de expediente mostrará aquí el caso en curso cuando esté disponible.
            </p>
          </div>
        </CollapsibleSection>

        <Separator />

        <CollapsibleSection
          title="Etiquetas Chatwoot"
          icon={<Tag className="h-3.5 w-3.5" />}
          defaultOpen={false}
        >
          <div className="rounded-md bg-muted/30 p-3 text-xs text-muted-foreground">
            Próximamente
          </div>
        </CollapsibleSection>

        <Separator />

        <CollapsibleSection
          title="Notas internas"
          icon={<StickyNote className="h-3.5 w-3.5" />}
          defaultOpen={false}
        >
          <div className="rounded-md bg-muted/30 p-3 text-xs text-muted-foreground">
            Próximamente
          </div>
        </CollapsibleSection>
      </div>
    </div>
  );
}
