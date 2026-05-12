"use client";

import { useState, useCallback, useRef } from "react";
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
  RefreshCw,
  ExternalLink,
  X,
  type LucideIcon,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
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
import { useInboxSidebar } from "@/hooks/use-inbox-sidebar";
import type {
  InboxItemResponse,
  EscalationStatusInbox,
  EscalationSource,
  InboxNote,
  InboxClientSummary,
  InboxActiveCase,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// Source badge configuration
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true, locale: es });
  } catch {
    return "—";
  }
}

function getCaseStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: "Pendiente",
    in_progress: "En progreso",
    resolved: "Resuelto",
    cancelled: "Cancelado",
    closed: "Cerrado",
  };
  return labels[status] ?? status;
}

function getCaseStatusVariant(
  status: string,
): "default" | "secondary" | "destructive" | "outline" {
  if (status === "in_progress") return "default";
  if (status === "pending") return "secondary";
  if (status === "resolved") return "outline";
  return "destructive";
}

// ---------------------------------------------------------------------------
// Shared sub-components
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// EscalationCard (preserved from original)
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// ClientSummaryPanel
// ---------------------------------------------------------------------------

interface ClientSummaryPanelProps {
  client: InboxClientSummary | null;
  isLoading: boolean;
}

function ClientSummaryPanel({ client, isLoading }: ClientSummaryPanelProps) {
  if (isLoading) {
    return (
      <div className="space-y-2 px-1">
        <Skeleton className="h-3 w-3/4" />
        <Skeleton className="h-3 w-1/2" />
        <Skeleton className="h-3 w-2/3" />
        <Skeleton className="h-3 w-1/2" />
      </div>
    );
  }

  if (!client) {
    return (
      <p className="text-xs text-muted-foreground px-1">Sin datos del cliente</p>
    );
  }

  return (
    <div className="space-y-1.5 text-xs text-muted-foreground px-1">
      <div className="flex justify-between">
        <span>Cliente desde</span>
        <span className="text-foreground font-medium">{formatRelative(client.created_at)}</span>
      </div>
      <div className="flex justify-between">
        <span>Expedientes</span>
        <span className="text-foreground font-medium">{client.cases_count}</span>
      </div>
      <div className="flex justify-between">
        <span>Facturado total</span>
        <span className="text-foreground font-medium">
          {client.billed_total_eur.toLocaleString("es-ES", {
            style: "currency",
            currency: "EUR",
            minimumFractionDigits: 0,
            maximumFractionDigits: 2,
          })}
        </span>
      </div>
      <div className="flex justify-between">
        <span>Última actividad</span>
        <span className="text-foreground font-medium">{formatRelative(client.last_activity_at)}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ActiveCasePanel
// ---------------------------------------------------------------------------

interface ActiveCasePanelProps {
  activeCase: InboxActiveCase | null;
  isLoading: boolean;
}

function ActiveCasePanel({ activeCase, isLoading }: ActiveCasePanelProps) {
  const router = useRouter();

  if (isLoading) {
    return (
      <div className="space-y-2 px-1">
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-3 w-2/3" />
        <Skeleton className="h-3 w-1/2" />
        <Skeleton className="h-2 w-full rounded-full" />
      </div>
    );
  }

  if (!activeCase) {
    return (
      <p className="text-xs text-muted-foreground px-1">Sin expediente activo</p>
    );
  }

  const progressPercent = Math.min(100, Math.max(0, activeCase.progress_percent));

  return (
    <div className="space-y-2 px-1">
      {/* Header row */}
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-mono font-semibold text-foreground">
          #{activeCase.case_number_short}
        </span>
        <Badge variant={getCaseStatusVariant(activeCase.status)} className="text-[10px] h-5">
          {getCaseStatusLabel(activeCase.status)}
        </Badge>
      </div>

      {/* Category */}
      {activeCase.category_name && (
        <p className="text-xs font-medium text-foreground">{activeCase.category_name}</p>
      )}

      {/* Subtitle */}
      <p className="text-[11px] text-muted-foreground leading-snug">
        {[
          activeCase.client_type_label,
          activeCase.tier_code,
          activeCase.tier_price_eur != null
            ? `Tarifa ${activeCase.tier_price_eur.toLocaleString("es-ES", { style: "currency", currency: "EUR", minimumFractionDigits: 0 })}`
            : null,
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="flex justify-between text-[11px] text-muted-foreground">
          <span>{activeCase.elements_complete}/{activeCase.elements_total} elementos</span>
          <span>{progressPercent}%</span>
        </div>
        <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
          <div
            className="h-full rounded-full bg-primary transition-all duration-300"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex gap-2 pt-1">
        <Button
          size="sm"
          variant="outline"
          className="h-7 text-xs gap-1"
          onClick={() => router.push(`/cases/${activeCase.id}`)}
        >
          <ExternalLink className="h-3 w-3" />
          Abrir
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// NotesPanel
// ---------------------------------------------------------------------------

interface NoteItemProps {
  note: InboxNote;
  onDelete: (noteId: string) => Promise<void>;
}

function NoteItem({ note, onDelete }: NoteItemProps) {
  const [showConfirm, setShowConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const handleConfirmDelete = useCallback(async () => {
    setIsDeleting(true);
    try {
      await onDelete(note.id);
      sileo.success({ title: "Nota eliminada" });
    } catch {
      sileo.error({ title: "No se pudo eliminar la nota. Reintentá." });
    } finally {
      setIsDeleting(false);
      setShowConfirm(false);
    }
  }, [note.id, onDelete]);

  return (
    <>
      <div className="group relative rounded-md border bg-muted/20 p-2.5 space-y-1">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <span className="text-[11px] font-medium text-foreground">
              {note.author_name ?? "Eliminado"}
            </span>
            <span className="text-[10px] text-muted-foreground ml-1.5">
              {formatRelative(note.created_at)}
            </span>
          </div>
          {note.can_delete && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-5 w-5 p-0 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive flex-shrink-0"
              onClick={() => setShowConfirm(true)}
              disabled={isDeleting}
              aria-label="Eliminar nota"
            >
              <X className="h-3 w-3" />
            </Button>
          )}
        </div>
        <p className="text-xs text-foreground whitespace-pre-wrap break-words">{note.content}</p>
      </div>

      <AlertDialog open={showConfirm} onOpenChange={setShowConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Eliminar esta nota?</AlertDialogTitle>
            <AlertDialogDescription>
              Esta acción no se puede deshacer.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmDelete}
              disabled={isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? "Eliminando..." : "Eliminar"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

interface NotesPanelProps {
  notes: InboxNote[];
  isLoading: boolean;
  onAdd: (content: string) => Promise<void>;
  onDelete: (noteId: string) => Promise<void>;
}

function NotesPanel({ notes, isLoading, onAdd, onDelete }: NotesPanelProps) {
  const [content, setContent] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const handleSubmit = useCallback(async () => {
    const trimmed = content.trim();
    if (!trimmed) return;

    setIsSubmitting(true);
    try {
      await onAdd(trimmed);
      setContent("");
      sileo.success({ title: "Nota añadida" });
    } catch {
      sileo.error({ title: "No se pudo guardar la nota. Reintentá." });
      // textarea retains content
    } finally {
      setIsSubmitting(false);
    }
  }, [content, onAdd]);

  if (isLoading) {
    return (
      <div className="space-y-2 px-1">
        <Skeleton className="h-12 w-full rounded-md" />
        <Skeleton className="h-12 w-full rounded-md" />
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* Notes list */}
      {notes.length === 0 ? (
        <p className="text-xs text-muted-foreground px-1">Sin notas todavía</p>
      ) : (
        <div className="space-y-1.5">
          {notes.map((note) => (
            <NoteItem key={note.id} note={note} onDelete={onDelete} />
          ))}
        </div>
      )}

      {/* Add note form */}
      <div className="space-y-2 pt-1">
        <Textarea
          ref={textareaRef}
          placeholder="Escribir nota interna..."
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={2}
          maxLength={2000}
          disabled={isSubmitting}
          className="resize-none text-xs"
          aria-label="Nueva nota interna"
        />
        <div className="flex items-center justify-between gap-2">
          {content.length > 0 && (
            <span className="text-[10px] text-muted-foreground">{content.length}/2000</span>
          )}
          <Button
            type="button"
            size="sm"
            className="h-7 text-xs ml-auto"
            disabled={isSubmitting || !content.trim()}
            onClick={handleSubmit}
          >
            {isSubmitting ? "Añadiendo..." : "Añadir nota"}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main ClientCard export
// ---------------------------------------------------------------------------

interface ClientCardProps {
  conversation: InboxItemResponse;
  onConversationUpdated: () => void;
}

export function ClientCard({
  conversation,
  onConversationUpdated,
}: ClientCardProps) {
  const hasEscalation = conversation.escalation_status !== "none";
  const { data, isLoading, error, refresh, addNote, removeNote } =
    useInboxSidebar(conversation.conversation_history_id ?? null);

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

        {/* Error state */}
        {error && !isLoading && (
          <>
            <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 space-y-2">
              <p className="text-xs text-destructive font-medium">Error al cargar la ficha</p>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-7 text-xs gap-1 border-destructive/40 text-destructive hover:bg-destructive/10"
                onClick={refresh}
              >
                <RefreshCw className="h-3 w-3" />
                Reintentar
              </Button>
            </div>
            <Separator />
          </>
        )}

        {/* Resumen del cliente */}
        <CollapsibleSection
          title="Resumen del cliente"
          icon={<User className="h-3.5 w-3.5" />}
          defaultOpen
        >
          <ClientSummaryPanel client={data?.client ?? null} isLoading={isLoading} />
        </CollapsibleSection>

        <Separator />

        {/* Expediente activo */}
        <CollapsibleSection
          title="Expediente activo"
          icon={<FileText className="h-3.5 w-3.5" />}
          defaultOpen
        >
          <ActiveCasePanel activeCase={data?.active_case ?? null} isLoading={isLoading} />
        </CollapsibleSection>

        <Separator />

        {/* Notas internas */}
        <CollapsibleSection
          title="Notas internas"
          icon={<StickyNote className="h-3.5 w-3.5" />}
          defaultOpen={false}
        >
          <NotesPanel
            notes={data?.notes ?? []}
            isLoading={isLoading}
            onAdd={addNote}
            onDelete={removeNote}
          />
        </CollapsibleSection>
      </div>
    </div>
  );
}
