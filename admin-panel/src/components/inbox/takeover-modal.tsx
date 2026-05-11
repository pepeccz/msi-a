"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Bot } from "lucide-react";

interface TakeoverModalProps {
  open: boolean;
  onConfirm: (reason?: string) => void;
  onCancel: () => void;
  isSubmitting?: boolean;
}

/**
 * TakeoverModal — confirmation dialog shown the first time an agent sends
 * a message while the bot is still active for the conversation.
 *
 * The backend auto-pauses the bot when send-message is called (the
 * default behavior is auto_pause_if_bot_on=True), so all we need here
 * is user consent + an optional reason.
 *
 * Persistence: the calling component stores a localStorage flag
 * `inbox_takeover_shown_<conv_id>` so this modal is only shown once
 * per conversation per browser session.
 */
export function TakeoverModal({
  open,
  onConfirm,
  onCancel,
  isSubmitting = false,
}: TakeoverModalProps) {
  const [reason, setReason] = useState("");

  function handleConfirm() {
    onConfirm(reason.trim() || undefined);
  }

  function handleCancel() {
    setReason("");
    onCancel();
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && handleCancel()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-2 mb-1">
            <Bot className="h-5 w-5 text-yellow-600" />
            <DialogTitle>¿Pausar bot para esta conversación?</DialogTitle>
          </div>
          <DialogDescription>
            Si enviás este mensaje, el bot dejará de responder a este cliente.
            Podrás reactivarlo desde el panel cuando termines.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2 py-2">
          <Label htmlFor="takeover-reason">Motivo (opcional)</Label>
          <Textarea
            id="takeover-reason"
            placeholder="Ej: El cliente solicita hablar con un agente"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={500}
            rows={3}
            className="resize-none"
          />
          <p className="text-xs text-muted-foreground text-right">
            {reason.length}/500
          </p>
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            type="button"
            variant="outline"
            onClick={handleCancel}
            disabled={isSubmitting}
          >
            Cancelar
          </Button>
          <Button
            type="button"
            onClick={handleConfirm}
            disabled={isSubmitting}
          >
            {isSubmitting ? "Enviando..." : "Confirmar y enviar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
