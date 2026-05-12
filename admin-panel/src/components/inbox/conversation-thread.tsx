"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  Bot,
  ArrowLeft,
  MessageSquare,
  ChevronUp,
  Phone,
  Pause,
  Play,
  PhoneForwarded,
  Image as ImageIcon,
  Trash2,
} from "lucide-react";
import { formatDistanceToNow, format } from "date-fns";
import { es } from "date-fns/locale";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
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
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { sileo } from "sileo";
import { cn } from "@/lib/utils";
import { useConversation } from "@/hooks/use-inbox";
import { useAuth } from "@/contexts/auth-context";
import { MessageComposer } from "./message-composer";
import api from "@/lib/api";
import type {
  ConversationMessageResponse,
  MessageAttachment,
  AuthorType,
  BotStatus,
  InboxItemResponse,
} from "@/lib/types";
import { MessageAttachments } from "./message-attachments";
import { AttachmentLightbox } from "./attachment-lightbox";
import { groupMessages } from "@/lib/inbox-grouping";
import type { MessageGroup, AlbumGroup } from "@/lib/inbox-grouping";

interface ConversationThreadProps {
  conversation: InboxItemResponse;
  onConversationUpdated: () => void;
  onConversationDeleted?: () => void;
  onBack?: () => void;
}

function formatTimestamp(iso: string): string {
  try {
    const date = new Date(iso);
    return format(date, "d MMM · HH:mm", { locale: es });
  } catch {
    return "";
  }
}

function getBubbleStyle(authorType: AuthorType): {
  align: "left" | "right" | "center";
  bubbleClass: string;
  label: string | null;
} {
  switch (authorType) {
    case "user":
      return {
        align: "left",
        bubbleClass: "bg-muted text-foreground rounded-tl-none",
        label: null,
      };
    case "bot":
      return {
        align: "right",
        bubbleClass: "bg-blue-100 text-blue-900 rounded-tr-none dark:bg-blue-900/40 dark:text-blue-100",
        label: "Bot",
      };
    case "human_agent":
      return {
        align: "right",
        bubbleClass: "bg-green-100 text-green-900 rounded-tr-none dark:bg-green-900/40 dark:text-green-100",
        label: null, // filled with author_user_name below
      };
    case "system":
      return {
        align: "center",
        bubbleClass: "bg-transparent text-muted-foreground italic text-xs",
        label: null,
      };
  }
}

function LegacyImagePlaceholder({ count }: { count: number }) {
  return (
    <div className="flex items-center gap-1 italic text-muted-foreground text-sm px-1 py-1">
      <ImageIcon className="h-3.5 w-3.5 flex-shrink-0" />
      <span>
        Imagen no disponible
        {count > 1 ? ` — ${count} imágenes` : count === 1 ? " — 1 imagen" : ""}
      </span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// AlbumBubble — renders a grouped album from the inbox-grouping pre-processor
// ─────────────────────────────────────────────────────────────────

interface AlbumBubbleProps {
  group: AlbumGroup;
  onOpenLightbox: (attachments: MessageAttachment[], index: number) => void;
}

function AlbumBubble({ group, onOpenLightbox }: AlbumBubbleProps) {
  const { align, bubbleClass, label } = getBubbleStyle(group.author_type as Parameters<typeof getBubbleStyle>[0]);
  void label; // album has no caption — label is unused here

  return (
    <div
      className={cn(
        "flex flex-col max-w-[75%]",
        align === "right" ? "items-end ml-auto" : "items-start",
      )}
    >
      <div className={cn("relative rounded-2xl px-1 py-1", bubbleClass)}>
        <MessageAttachments
          attachments={group.attachments}
          onOpen={onOpenLightbox}
        />
      </div>
      {/* Timestamp of the last message in the album */}
      <span className="text-[10px] text-muted-foreground mt-0.5 px-1">
        {formatTimestamp(group.timestamp)}
      </span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────

interface MessageBubbleProps {
  msg: ConversationMessageResponse;
  onOpenLightbox: (attachments: MessageAttachment[], index: number) => void;
}

function MessageBubble({ msg, onOpenLightbox }: MessageBubbleProps) {
  const { align, bubbleClass, label } = getBubbleStyle(msg.author_type);
  const displayLabel =
    msg.author_type === "human_agent"
      ? (msg.author_user_name ?? "Agente")
      : label;

  const hasAttachments = Array.isArray(msg.attachments) && msg.attachments.length > 0;

  if (align === "center") {
    return (
      <div className="flex justify-center my-2">
        <span className={cn("px-3 py-1 rounded-full", bubbleClass)}>
          {msg.content}
        </span>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex flex-col max-w-[75%]",
        align === "right" ? "items-end ml-auto" : "items-start",
      )}
    >
      {displayLabel && (
        <span className="text-[10px] text-muted-foreground mb-0.5 px-1">
          {displayLabel}
        </span>
      )}
      <div className={cn("relative rounded-2xl px-3 py-2 text-sm", bubbleClass)}>
        {/* Attachments: real images if available, legacy placeholder if has_images but no rows */}
        {hasAttachments ? (
          <MessageAttachments
            attachments={msg.attachments}
            onOpen={onOpenLightbox}
          />
        ) : msg.has_images ? (
          <LegacyImagePlaceholder count={msg.image_count} />
        ) : null}
        {msg.content && <p className="whitespace-pre-wrap break-words">{msg.content}</p>}
        {msg.delivery_failed && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="absolute -bottom-1 -right-1 bg-background rounded-full">
                  <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
                </span>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                No se entregó a Chatwoot
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
      </div>
      <span className="text-[10px] text-muted-foreground mt-0.5 px-1">
        {formatTimestamp(msg.created_at)}
      </span>
    </div>
  );
}

interface EscalateDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: (reason: string, priority?: "low" | "medium" | "high") => void;
  isSubmitting: boolean;
}

function EscalateDialog({ open, onClose, onConfirm, isSubmitting }: EscalateDialogProps) {
  const [reason, setReason] = useState("");
  const [priority, setPriority] = useState<"" | "low" | "medium" | "high">("");

  function handleConfirm() {
    if (!reason.trim()) return;
    onConfirm(reason.trim(), priority || undefined);
  }

  function handleClose() {
    setReason("");
    setPriority("");
    onClose();
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && handleClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <PhoneForwarded className="h-4 w-4 text-destructive" />
            Escalar conversación
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="escalate-reason">Motivo *</Label>
            <Textarea
              id="escalate-reason"
              placeholder="Describí el motivo de la escalación..."
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              maxLength={1000}
              className="resize-none"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="escalate-priority">Prioridad (opcional)</Label>
            <select
              id="escalate-priority"
              value={priority}
              onChange={(e) => setPriority(e.target.value as "" | "low" | "medium" | "high")}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="">Sin prioridad</option>
              <option value="low">Baja</option>
              <option value="medium">Media</option>
              <option value="high">Alta</option>
            </select>
          </div>
        </div>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={handleClose} disabled={isSubmitting}>
            Cancelar
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={isSubmitting || !reason.trim()}
          >
            {isSubmitting ? "Escalando..." : "Confirmar escalación"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ConversationThread({
  conversation,
  onConversationUpdated,
  onConversationDeleted,
  onBack,
}: ConversationThreadProps) {
  const { messages, isLoading, isLoadingMore, error, hasMore, loadMore, refresh } =
    useConversation(conversation.conversation_history_id, 5_000);

  const { isAdmin } = useAuth();
  const router = useRouter();

  const bottomRef = useRef<HTMLDivElement>(null);
  const [hasSentMarkRead, setHasSentMarkRead] = useState(false);
  const [isPausingOrResuming, setIsPausingOrResuming] = useState(false);
  const [showEscalateDialog, setShowEscalateDialog] = useState(false);
  const [isEscalating, setIsEscalating] = useState(false);
  const [showResumeConfirm, setShowResumeConfirm] = useState(false);
  const [showPauseDialog, setShowPauseDialog] = useState(false);
  const [pauseReason, setPauseReason] = useState("");
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const botStatus = conversation.bot_status as BotStatus;

  // Lightbox state: null = closed, object = open with selected group + index
  const [lightbox, setLightbox] = useState<{
    attachments: MessageAttachment[];
    index: number;
  } | null>(null);

  const openLightbox = useCallback(
    (attachments: MessageAttachment[], index: number) => {
      setLightbox({ attachments, index });
    },
    [],
  );

  const closeLightbox = useCallback(() => {
    setLightbox(null);
  }, []);

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    if (!isLoading && messages.length > 0) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages.length, isLoading]);

  // Mark all messages as read when the conversation is opened
  useEffect(() => {
    if (hasSentMarkRead) return;
    setHasSentMarkRead(true);
    api
      .markRead(conversation.conversation_history_id)
      .catch(() => null); // fire-and-forget, non-critical
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversation.conversation_history_id]);

  const handlePauseConfirm = useCallback(async () => {
    setShowPauseDialog(false);
    setIsPausingOrResuming(true);
    try {
      await api.pauseBot(conversation.conversation_history_id, pauseReason.trim() || undefined);
      setPauseReason("");
      sileo.success({ title: "Bot pausado" });
      onConversationUpdated();
    } catch (err) {
      sileo.error({
        title: "Error al pausar",
        description: err instanceof Error ? err.message : "Error desconocido",
      });
    } finally {
      setIsPausingOrResuming(false);
    }
  }, [conversation.conversation_history_id, onConversationUpdated, pauseReason]);

  const handleResume = useCallback(async () => {
    setShowResumeConfirm(false);
    setIsPausingOrResuming(true);
    try {
      await api.resumeBot(conversation.conversation_history_id);
      sileo.success({ title: "Bot reanudado" });
      onConversationUpdated();
    } catch (err) {
      sileo.error({
        title: "Error al reanudar",
        description: err instanceof Error ? err.message : "Error desconocido",
      });
    } finally {
      setIsPausingOrResuming(false);
    }
  }, [conversation.conversation_history_id, onConversationUpdated]);

  const handleEscalate = useCallback(
    async (reason: string, priority?: "low" | "medium" | "high") => {
      setIsEscalating(true);
      try {
        await api.escalateConversation(
          conversation.conversation_history_id,
          reason,
          priority,
        );
        sileo.success({ title: "Conversación escalada" });
        setShowEscalateDialog(false);
        onConversationUpdated();
      } catch (err) {
        sileo.error({
          title: "Error al escalar",
          description: err instanceof Error ? err.message : "Error desconocido",
        });
      } finally {
        setIsEscalating(false);
      }
    },
    [conversation.conversation_history_id, onConversationUpdated],
  );

  const handleDeleteConversation = useCallback(async () => {
    setIsDeleting(true);
    try {
      await api.deleteConversation(conversation.conversation_history_id);
      sileo.success({ title: "Conversación eliminada" });
      setShowDeleteConfirm(false);
      onConversationDeleted?.();
      router.replace("/inbox");
    } catch (err) {
      const status = (err as { status?: number })?.status;
      if (status === 403) {
        sileo.error({ title: "No tenés permisos para eliminar conversaciones" });
      } else {
        sileo.error({ title: "No se pudo eliminar. Reintentá." });
      }
    } finally {
      setIsDeleting(false);
    }
  }, [conversation.conversation_history_id, onConversationDeleted, router]);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex-shrink-0 border-b px-4 py-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          {/* Back button — only visible on mobile (hidden on lg+) */}
          {onBack && (
            <Button
              size="icon"
              variant="ghost"
              onClick={onBack}
              className="lg:hidden flex-shrink-0 h-8 w-8"
              aria-label="Volver a la lista"
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
          )}
          <div className="min-w-0">
            <p className="font-medium text-sm truncate">
              {conversation.user_name ?? "Sin nombre"}
            </p>
            {conversation.user_phone && (
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                <Phone className="h-3 w-3" />
                {conversation.user_phone}
              </p>
            )}
          </div>
          <BotStatusBadge status={botStatus} />
        </div>

        <div className="flex items-center gap-1.5 flex-shrink-0">
          {botStatus === "paused" ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowResumeConfirm(true)}
              disabled={isPausingOrResuming}
              className="gap-1.5"
            >
              <Play className="h-3.5 w-3.5" />
              Reanudar
            </Button>
          ) : botStatus === "active" ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowPauseDialog(true)}
              disabled={isPausingOrResuming}
              className="gap-1.5"
            >
              <Pause className="h-3.5 w-3.5" />
              Pausar bot
            </Button>
          ) : null}

          {conversation.escalation_status === "none" && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowEscalateDialog(true)}
              disabled={isPausingOrResuming}
              className="gap-1.5 text-destructive border-destructive/40 hover:bg-destructive/10"
            >
              <PhoneForwarded className="h-3.5 w-3.5" />
              Escalar
            </Button>
          )}

          {isAdmin && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setShowDeleteConfirm(true)}
              disabled={isDeleting}
              className="gap-1.5 text-destructive hover:bg-destructive/10"
              aria-label="Eliminar conversación"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </div>

      {/* Banners */}
      {botStatus === "paused" && (
        <div className="flex-shrink-0 bg-yellow-50 border-b border-yellow-200 px-4 py-2 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-yellow-800 text-sm">
            <Bot className="h-4 w-4 flex-shrink-0" />
            <span>
              Bot pausado
              {conversation.paused_by_user_name
                ? ` por ${conversation.paused_by_user_name}`
                : ""}
            </span>
          </div>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setShowResumeConfirm(true)}
            className="text-yellow-800 hover:text-yellow-900 hover:bg-yellow-100"
          >
            Reanudar
          </Button>
        </div>
      )}

      {conversation.escalation_status !== "none" && (
        <div className="flex-shrink-0 bg-red-50 border-b border-red-200 px-4 py-2 flex items-center gap-2 text-red-800 text-sm">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          <span>
            Conversación escalada
            {conversation.escalation_status === "in_progress"
              ? " — en gestión"
              : " — pendiente"}
          </span>
        </div>
      )}

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {/* Load more button */}
        {hasMore && !isLoadingMore && (
          <div className="flex justify-center">
            <Button
              size="sm"
              variant="ghost"
              onClick={loadMore}
              className="gap-1.5 text-xs text-muted-foreground"
            >
              <ChevronUp className="h-3.5 w-3.5" />
              Cargar mensajes anteriores
            </Button>
          </div>
        )}
        {isLoadingMore && (
          <div className="flex justify-center py-2">
            <Skeleton className="h-8 w-40" />
          </div>
        )}

        {isLoading && (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className={cn(
                  "flex flex-col gap-1",
                  i % 2 === 0 ? "items-start" : "items-end ml-auto",
                )}
                style={{ maxWidth: "75%" }}
              >
                <Skeleton className="h-10 w-48 rounded-2xl" />
                <Skeleton className="h-3 w-16" />
              </div>
            ))}
          </div>
        )}

        {error && (
          <div className="flex flex-col items-center py-8 gap-2">
            <AlertTriangle className="h-8 w-8 text-destructive" />
            <p className="text-sm text-destructive">{error}</p>
            <Button size="sm" variant="outline" onClick={refresh}>
              Reintentar
            </Button>
          </div>
        )}

        {!isLoading && !error && messages.length === 0 && (
          <div className="flex flex-col items-center py-12 gap-2 text-muted-foreground">
            <MessageSquare className="h-8 w-8" />
            <p className="text-sm">Sin mensajes aún</p>
          </div>
        )}

        {groupMessages(messages).map((group: MessageGroup, index: number) =>
          group.type === "album" ? (
            <AlbumBubble
              key={`album-${index}`}
              group={group}
              onOpenLightbox={openLightbox}
            />
          ) : (
            <MessageBubble
              key={group.message.id}
              msg={group.message}
              onOpenLightbox={openLightbox}
            />
          ),
        )}

        <div ref={bottomRef} />
      </div>

      {/* Composer — pinned at bottom */}
      <div className="flex-shrink-0">
        <MessageComposer
          conversationHistoryId={conversation.conversation_history_id}
          botStatus={botStatus}
          onMessageSent={() => {
            refresh();
            onConversationUpdated();
          }}
        />
      </div>

      {/* Resume confirmation */}
      <AlertDialog open={showResumeConfirm} onOpenChange={setShowResumeConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Reanudar el bot?</AlertDialogTitle>
            <AlertDialogDescription>
              El bot volverá a responder automáticamente a este cliente.
              Los mensajes enviados durante la pausa serán inyectados al contexto.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleResume}>
              Reanudar bot
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Escalate dialog */}
      <EscalateDialog
        open={showEscalateDialog}
        onClose={() => setShowEscalateDialog(false)}
        onConfirm={handleEscalate}
        isSubmitting={isEscalating}
      />

      {/* Delete conversation dialog — admin only */}
      <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Eliminar esta conversación?</AlertDialogTitle>
            <AlertDialogDescription>
              Esto elimina los mensajes, casos asociados, imágenes y estado en Redis.{" "}
              <strong>Esta acción no se puede deshacer.</strong>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConversation}
              disabled={isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? "Eliminando..." : "Eliminar"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Pause confirmation dialog */}
      <AlertDialog
        open={showPauseDialog}
        onOpenChange={(o) => {
          if (!o) {
            setShowPauseDialog(false);
            setPauseReason("");
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Pausar el bot para esta conversación?</AlertDialogTitle>
            <AlertDialogDescription>
              El bot dejará de responder hasta que reanudes. Podés agregar un motivo (opcional).
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="px-1 py-2">
            <Textarea
              placeholder="Motivo (opcional)"
              value={pauseReason}
              onChange={(e) => setPauseReason(e.target.value)}
              maxLength={500}
              rows={3}
              className="resize-none"
              aria-label="Motivo de pausa"
            />
            {pauseReason.length > 0 && (
              <p className="text-xs text-muted-foreground mt-1 text-right">
                {pauseReason.length}/500
              </p>
            )}
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setPauseReason("")}>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handlePauseConfirm} disabled={isPausingOrResuming}>
              {isPausingOrResuming ? "Pausando..." : "Pausar bot"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Attachment lightbox — one per thread, opened by MessageAttachments */}
      {lightbox && (
        <AttachmentLightbox
          attachments={lightbox.attachments}
          initialIndex={lightbox.index}
          open={true}
          onClose={closeLightbox}
        />
      )}
    </div>
  );
}

function BotStatusBadge({ status }: { status: BotStatus }) {
  if (status === "active") {
    return (
      <Badge variant="outline" className="gap-1 border-green-400 text-green-700 text-[10px]">
        <Bot className="h-3 w-3" />
        Bot ON
      </Badge>
    );
  }
  if (status === "paused") {
    return (
      <Badge variant="outline" className="gap-1 border-yellow-400 text-yellow-700 text-[10px]">
        <Bot className="h-3 w-3" />
        Pausado
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="gap-1 text-muted-foreground text-[10px]">
      <Bot className="h-3 w-3" />
      Bot OFF
    </Badge>
  );
}
