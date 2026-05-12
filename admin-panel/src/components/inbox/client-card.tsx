"use client";

import { useState, useCallback } from "react";
import {
  User,
  Phone,
  FileText,
  AlertTriangle,
  CheckCircle2,
  Clock,
  StickyNote,
  ChevronDown,
  ChevronUp,
  Bot,
  FileCheck,
  PowerOff,
  type LucideIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
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
import { sileo } from "sileo";
import { formatDistanceToNow } from "date-fns";
import { es } from "date-fns/locale";
import { cn } from "@/lib/utils";
import api from "@/lib/api";
import type { InboxItemResponse, EscalationStatusInbox, EscalationSource } from "@/lib/types";

const SOURCE_MAP: Record<
  EscalationSource,
  { icon: LucideIcon; cls: string; label: string }
> = {
  tool_call: { icon: Phone, cls: "bg-blue-100 text-blue-800", label: "Pidió hablar con persona" },
  auto_escalation: { icon: Bot, cls: "bg-purple-100 text-purple-800", label: "Auto-escalada" },
  error: { icon: AlertTriangle, cls: "bg-red-100 text-red-800", label: "Error técnico" },
  case_completion: { icon: FileCheck, cls: "bg-green-100 text-green-800", label: "Expediente completado" },
  agent_disabled: { icon: PowerOff, cls: "bg-orange-100 text-orange-800", label: "Bot desactivado" },
};

function EscalationSourceBadge({ source }: { source: EscalationSource | null }) {
  if (!source) return null;
  const { icon: Icon, cls, label } = SOURCE_MAP[source];
  return (
    <Badge className={cn("gap-1 text-xs border-0 font-medium", cls)}>
      <Icon className="h-3 w-3" />
      {label}
    </Badge>
  );
}

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
  escalationId: string | null;
  escalationStatus: EscalationStatusInbox;
  escalationSource: EscalationSource | null;
  onUpdated: () => void;
}

function EscalationCard({
  escalationId,
  escalationStatus,
  escalationSource,
  onUpdated,
}: EscalationCardProps) {
  const [isResolving, setIsResolving] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const canResolve =
    escalationId !== null &&
    (escalationStatus === "pending" || escalationStatus === "in_progress");

  const handleConfirmResolve = useCallback(async () => {
    if (!escalationId) return;
    setIsResolving(true);
    try {
      await api.resolveEscalation(escalationId);
      sileo.success({ title: "Escalación resuelta" });
      onUpdated();
    } catch (err) {
      const status = (err as { status?: number })?.status;
      if (status === 409) {
        sileo.warning({ title: "Esta escalación ya fue resuelta" });
      } else {
        sileo.error({ title: "No se pudo resolver. Reintentá." });
      }
    } finally {
      setIsResolving(false);
      setShowConfirm(false);
    }
  }, [escalationId, onUpdated]);

  return (
    <>
      <div className="rounded-lg border border-red-200 bg-red-50/50 p-3 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-red-800 flex items-center gap-1.5">
            <AlertTriangle className="h-4 w-4" />
            Escalación activa
          </span>
          <EscalationStatusBadge status={escalationStatus} />
        </div>

        {escalationSource && (
          <div>
            <EscalationSourceBadge source={escalationSource} />
          </div>
        )}

        {canResolve && (
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              className="text-xs border-green-400 text-green-700 hover:bg-green-50"
              onClick={() => setShowConfirm(true)}
              disabled={isResolving}
            >
              <CheckCircle2 className="h-3 w-3 mr-1" />
              {isResolving ? "Resolviendo..." : "Resolver"}
            </Button>
          </div>
        )}
      </div>

      <AlertDialog open={showConfirm} onOpenChange={setShowConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Marcar escalación como resuelta?</AlertDialogTitle>
            <AlertDialogDescription>
              La escalación quedará cerrada. El bot NO se reactivará automáticamente;
              si querés reanudarlo, hacelo manualmente desde el thread.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isResolving}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmResolve}
              disabled={isResolving}
              className="bg-green-600 hover:bg-green-700 text-white"
            >
              {isResolving ? "Resolviendo..." : "Resolver"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
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
              {conversation.user_phone && (
                <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                  <Phone className="h-3 w-3 flex-shrink-0" />
                  <span className="truncate">{conversation.user_phone}</span>
                </p>
              )}
            </div>
          </div>

          {/* Last activity */}
          <div className="text-xs text-muted-foreground flex items-center gap-1">
            <Clock className="h-3 w-3" />
            Última actividad: {formatRelative(conversation.last_message_at)}
          </div>
        </div>

        <Separator />

        {/* Escalation card */}
        {hasEscalation && (
          <>
            <EscalationCard
              escalationId={conversation.escalation_id}
              escalationStatus={conversation.escalation_status}
              escalationSource={conversation.escalation_source}
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
