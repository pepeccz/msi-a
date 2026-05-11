"use client";

import { useState, useCallback, useRef } from "react";
import { Send, Clock, AlertTriangle, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { sileo } from "sileo";
import { cn } from "@/lib/utils";
import { useWindowStatus } from "@/hooks/use-inbox";
import { TakeoverModal } from "./takeover-modal";
import { TemplateSelector } from "./template-selector";
import api from "@/lib/api";
import type { BotStatus } from "@/lib/types";

interface MessageComposerProps {
  conversationHistoryId: string;
  botStatus: BotStatus;
  onMessageSent: () => void;
}

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
  // Pending message held while the takeover modal is open
  const pendingTextRef = useRef<string>("");

  const within24h = windowStatus?.within_24h ?? true; // optimistic until known
  const secondsRemaining = windowStatus?.seconds_remaining ?? null;

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

  const handleSendClick = useCallback(() => {
    if (!text.trim()) return;

    // Bot is active and we haven't shown the takeover modal yet → show it
    if (botStatus === "active" && !wasTakeoverShown(conversationHistoryId)) {
      pendingTextRef.current = text;
      setShowTakeover(true);
      return;
    }

    // Bot already paused or takeover already acknowledged → send directly
    handleSendText(text);
  }, [text, botStatus, conversationHistoryId, handleSendText]);

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

  return (
    <div className="border-t bg-background">
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

          <div className="flex items-center gap-2">
            {text.length > 0 && (
              <span className="text-xs text-muted-foreground">
                {text.length}/4096
              </span>
            )}
            <Button
              type="button"
              size="sm"
              onClick={handleSendClick}
              disabled={!within24h || !text.trim() || isSending}
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
