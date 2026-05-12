"use client";

import { useState, useCallback, useRef } from "react";
import { Send, Clock, AlertTriangle, FileText, Paperclip } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { sileo } from "sileo";
import { cn } from "@/lib/utils";
import { useWindowStatus } from "@/hooks/use-inbox";
import { TakeoverModal } from "./takeover-modal";
import { TemplateSelector } from "./template-selector";
import { AttachmentChip } from "./attachment-chip";
import api from "@/lib/api";
import type { BotStatus } from "@/lib/types";

interface MessageComposerProps {
  conversationHistoryId: string;
  botStatus: BotStatus;
  onMessageSent: () => void;
}

const MAX_ATTACHMENTS = 10;

function formatSecondsRemaining(seconds: number | null): string {
  if (seconds === null) return "";
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${mins}min`;
  return `${mins}min`;
}

/**
 * Checks localStorage to see if the takeover modal was already shown
 * for this conversation in this browser context.
 */
function wasTakeoverShown(convId: string): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem(`inbox_takeover_shown_${convId}`) === "true";
}

function markTakeoverShown(convId: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(`inbox_takeover_shown_${convId}`, "true");
}

/**
 * Merge new files into existing attachment list, capped at MAX_ATTACHMENTS.
 * Returns the merged list and a boolean indicating whether the cap was hit.
 */
function mergeFiles(existing: File[], incoming: File[]): { merged: File[]; capped: boolean } {
  const available = MAX_ATTACHMENTS - existing.length;
  if (available <= 0) return { merged: existing, capped: incoming.length > 0 };
  const toAdd = incoming.slice(0, available);
  const capped = incoming.length > available;
  return { merged: [...existing, ...toAdd], capped };
}

export function MessageComposer({
  conversationHistoryId,
  botStatus,
  onMessageSent,
}: MessageComposerProps) {
  const { data: windowStatus } = useWindowStatus(conversationHistoryId, 30_000);
  const [text, setText] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [showTakeover, setShowTakeover] = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);
  const [attachments, setAttachments] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);

  // Pending message held while the takeover modal is open
  const pendingTextRef = useRef<string>("");
  // Hidden file input triggered by paperclip button
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const within24h = windowStatus?.within_24h ?? true; // optimistic until known
  const secondsRemaining = windowStatus?.seconds_remaining ?? null;

  // -----------------------------------------------------------------------
  // File helpers
  // -----------------------------------------------------------------------

  const addFiles = useCallback((newFiles: File[]) => {
    const imageFiles = newFiles.filter((f) => f.type.startsWith("image/"));
    if (imageFiles.length === 0) return;

    setAttachments((prev) => {
      if (prev.length >= MAX_ATTACHMENTS) {
        sileo.warning({ title: `Máximo ${MAX_ATTACHMENTS} imágenes por mensaje` });
        return prev;
      }
      const { merged, capped } = mergeFiles(prev, imageFiles);
      if (capped) {
        sileo.warning({ title: `Máximo ${MAX_ATTACHMENTS} imágenes por mensaje` });
      }
      return merged;
    });
  }, []);

  const removeAttachment = useCallback((index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  }, []);

  // -----------------------------------------------------------------------
  // Paperclip button → hidden file input
  // -----------------------------------------------------------------------

  const handlePaperclipClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files ? Array.from(e.target.files) : [];
      addFiles(files);
      // Reset input so same file can be re-selected
      e.target.value = "";
    },
    [addFiles],
  );

  // -----------------------------------------------------------------------
  // Paste (Ctrl/Cmd+V on textarea)
  // -----------------------------------------------------------------------

  const handlePaste = useCallback(
    (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
      const items = Array.from(e.clipboardData.items);
      const imageFiles = items
        .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
        .map((item) => item.getAsFile())
        .filter((f): f is File => f !== null);

      if (imageFiles.length > 0) {
        e.preventDefault(); // don't paste image bytes as text
        addFiles(imageFiles);
      }
    },
    [addFiles],
  );

  // -----------------------------------------------------------------------
  // Drag-and-drop on composer wrapper
  // -----------------------------------------------------------------------

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    // Only clear when leaving the wrapper itself, not children
    if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
      setIsDragging(false);
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragging(false);
      const files = Array.from(e.dataTransfer.files);
      addFiles(files);
    },
    [addFiles],
  );

  // -----------------------------------------------------------------------
  // Send logic
  // -----------------------------------------------------------------------

  const handleSendText = useCallback(
    async (content: string) => {
      if (!content.trim()) return;
      setIsSending(true);
      try {
        const result = await api.sendMessage(conversationHistoryId, content.trim());
        setText("");
        onMessageSent();
        if (result.delivery_failed) {
          sileo.warning({
            title: "Mensaje guardado pero no entregado",
            description: "No se pudo entregar a WhatsApp. Reintentá o revisá la ventana de 24h.",
          });
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Error al enviar";
        if (msg.toLowerCase().includes("fuera") || msg.toLowerCase().includes("24")) {
          sileo.warning({
            title: "Fuera de ventana",
            description: "Usá una plantilla para contactar al cliente.",
          });
        } else {
          sileo.error({ title: "Error al enviar", description: msg });
        }
      } finally {
        setIsSending(false);
      }
    },
    [conversationHistoryId, onMessageSent],
  );

  const handleSendWithAttachments = useCallback(async () => {
    setIsSending(true);
    try {
      await api.uploadConversationAttachments(
        conversationHistoryId,
        attachments,
        text.trim() || undefined,
      );
      setAttachments([]);
      setText("");
      onMessageSent();
      sileo.success({ title: "Imágenes enviadas" });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Error al enviar imágenes";
      sileo.error({ title: "Error al enviar imágenes", description: msg });
      // Chips retained on failure — user can retry
    } finally {
      setIsSending(false);
    }
  }, [conversationHistoryId, attachments, text, onMessageSent]);

  const handleSendClick = useCallback(() => {
    if (attachments.length > 0) {
      handleSendWithAttachments();
      return;
    }

    if (!text.trim()) return;

    // Bot is active and we haven't shown the takeover modal yet → show it
    if (botStatus === "active" && !wasTakeoverShown(conversationHistoryId)) {
      pendingTextRef.current = text;
      setShowTakeover(true);
      return;
    }

    // Bot already paused or takeover already acknowledged → send directly
    handleSendText(text);
  }, [text, attachments, botStatus, conversationHistoryId, handleSendText, handleSendWithAttachments]);

  const handleTakeoverConfirm = useCallback(async () => {
    markTakeoverShown(conversationHistoryId);
    setShowTakeover(false);
    // send-message always auto-pauses, so we just send; the backend does the pause
    await handleSendText(pendingTextRef.current);
    pendingTextRef.current = "";
  }, [conversationHistoryId, handleSendText]);

  const handleTakeoverCancel = useCallback(() => {
    pendingTextRef.current = "";
    setShowTakeover(false);
  }, []);

  const handleSendTemplate = useCallback(
    async (
      templateName: string,
      params: Record<string, string>,
      language: string,
    ) => {
      try {
        const result = await api.sendTemplate(
          conversationHistoryId,
          templateName,
          params,
          language,
        );
        onMessageSent();
        if (result.delivery_failed) {
          sileo.warning({
            title: "Plantilla guardada pero no entregada",
            description: "No se pudo entregar a WhatsApp. Revisá el estado de la integración.",
          });
        } else {
          sileo.success({ title: "Plantilla enviada" });
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Error al enviar plantilla";
        sileo.error({ title: "Error al enviar plantilla", description: msg });
        throw err; // let TemplateSelector keep its state
      }
    },
    [conversationHistoryId, onMessageSent],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      // Ctrl+Enter or Cmd+Enter to send
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        handleSendClick();
      }
    },
    [handleSendClick],
  );

  // Send is disabled when: outside window, already sending, AND no text AND no chips
  const sendDisabled =
    !within24h || isSending || (!text.trim() && attachments.length === 0);

  return (
    <div
      className={cn(
        "border-t bg-background transition-colors",
        isDragging && "border-primary/50 bg-primary/5",
      )}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Outside 24h window banner */}
      {!within24h && (
        <div className="px-4 py-2 bg-amber-50 border-b border-amber-200 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-amber-800 text-sm">
            <Clock className="h-4 w-4 flex-shrink-0" />
            <span>
              Ventana de 24h cerrada — solo podés enviar plantillas
            </span>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="border-amber-400 text-amber-800 hover:bg-amber-100 flex-shrink-0 gap-1.5"
            onClick={() => setShowTemplates(true)}
          >
            <FileText className="h-3.5 w-3.5" />
            Enviar plantilla
          </Button>
        </div>
      )}

      {/* Window open indicator */}
      {within24h && secondsRemaining !== null && (
        <div className="px-4 pt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
          <Clock className="h-3 w-3" />
          <span>
            Ventana abierta — cierra en {formatSecondsRemaining(secondsRemaining)}
          </span>
        </div>
      )}

      {/* Drag overlay hint */}
      {isDragging && (
        <div className="px-4 pt-2 text-xs text-primary font-medium text-center">
          Suelta las imágenes aquí
        </div>
      )}

      {/* Attachment chips strip */}
      {attachments.length > 0 && (
        <div className="px-4 pt-2 flex flex-wrap gap-1.5" aria-label="Imágenes adjuntas">
          {attachments.map((file, index) => (
            <AttachmentChip
              key={`${file.name}-${index}`}
              file={file}
              onRemove={() => removeAttachment(index)}
            />
          ))}
        </div>
      )}

      {/* Composer area */}
      <div className="p-4 space-y-2">
        <div className="relative">
          <Textarea
            aria-label="Escribir mensaje"
            placeholder={
              within24h
                ? "Escribir mensaje... (Ctrl+Enter para enviar)"
                : "Ventana cerrada — usá una plantilla"
            }
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            rows={3}
            maxLength={4096}
            disabled={!within24h || isSending}
            className={cn(
              "resize-none pr-4",
              !within24h && "opacity-60 cursor-not-allowed",
            )}
          />
          {!within24h && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="flex items-center gap-2 text-muted-foreground text-sm bg-background/80 px-3 py-1.5 rounded-md">
                <AlertTriangle className="h-4 w-4" />
                Fuera de ventana 24h
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1">
            {/* Paperclip button */}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="gap-1.5 text-muted-foreground"
              onClick={handlePaperclipClick}
              disabled={!within24h || isSending}
              aria-label="Adjuntar imágenes"
            >
              <Paperclip className="h-3.5 w-3.5" />
            </Button>

            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={handleFileInputChange}
              aria-hidden="true"
            />

            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="gap-1.5 text-muted-foreground"
              onClick={() => setShowTemplates(true)}
            >
              <FileText className="h-3.5 w-3.5" />
              Plantilla
            </Button>
          </div>

          <div className="flex items-center gap-2">
            {text.length > 0 && (
              <span className="text-xs text-muted-foreground">
                {text.length}/4096
              </span>
            )}
            {attachments.length > 0 && (
              <span className="text-xs text-muted-foreground">
                {attachments.length}/{MAX_ATTACHMENTS} imágenes
              </span>
            )}
            <Button
              type="button"
              size="sm"
              onClick={handleSendClick}
              disabled={sendDisabled}
              className="gap-1.5"
            >
              <Send className="h-3.5 w-3.5" />
              {isSending ? "Enviando..." : "Enviar"}
            </Button>
          </div>
        </div>
      </div>

      <TakeoverModal
        open={showTakeover}
        onConfirm={handleTakeoverConfirm}
        onCancel={handleTakeoverCancel}
        isSubmitting={isSending}
      />

      <TemplateSelector
        open={showTemplates}
        onClose={() => setShowTemplates(false)}
        onSend={handleSendTemplate}
        isSubmitting={isSending}
      />
    </div>
  );
}
