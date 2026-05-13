"use client";

import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { UserCheck, Unlock, CheckCircle, Play } from "lucide-react";
import { sileo } from "sileo";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/auth-context";
import api from "@/lib/api";
import { AssignToDialog } from "./assign-to-dialog";
import type { Escalation } from "@/lib/types";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface EscalationCardActionsProps {
  escalation: Escalation;
  onUpdate: (updated: Escalation) => void;
}

// ---------------------------------------------------------------------------
// UI State
// ---------------------------------------------------------------------------

type UiState =
  | { kind: "idle" }
  | { kind: "assigning" }
  | { kind: "unassigning" }
  | { kind: "resolving" }
  | { kind: "resuming" };

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function EscalationCardActions({
  escalation,
  onUpdate,
}: EscalationCardActionsProps) {
  const { user } = useAuth();
  const [uiState, setUiState] = useState<UiState>({ kind: "idle" });

  // Optimistic snapshot for rollback
  const [optimisticEscalation, setOptimisticEscalation] =
    useState<Escalation>(escalation);

  // Sync when parent changes (e.g. after full fetchData)
  const currentEscalation =
    uiState.kind === "idle" ? escalation : optimisticEscalation;

  const handleAssignSelf = useCallback(async () => {
    if (!user) return;
    setUiState({ kind: "assigning" });

    // Optimistic update
    const optimistic: Escalation = {
      ...escalation,
      status: "assigned",
      assigned_to_user_id: user.id,
      assigned_to: {
        id: user.id,
        username: user.username,
        display_name: user.display_name,
      },
      assigned_at: new Date().toISOString(),
    };
    setOptimisticEscalation(optimistic);

    try {
      const updated = await api.assignEscalation(escalation.id, user.id);
      onUpdate(updated);
      sileo.success({ title: "Escalación asignada a ti" });
    } catch (err) {
      const error = err as Error & { status?: number };
      setOptimisticEscalation(escalation); // revert
      if (error.status === 409 || error.message?.includes("409")) {
        sileo.warning({ title: "Otro agente la tomó primero" });
      } else {
        sileo.error({
          title: "No se pudo asignar",
          description: error.message ?? "Error desconocido",
        });
      }
    } finally {
      setUiState({ kind: "idle" });
    }
  }, [escalation, user, onUpdate]);

  const handleUnassign = useCallback(async () => {
    setUiState({ kind: "unassigning" });

    // Optimistic update
    const optimistic: Escalation = {
      ...escalation,
      status: "pending",
      assigned_to_user_id: null,
      assigned_to: null,
      assigned_at: null,
    };
    setOptimisticEscalation(optimistic);

    try {
      const updated = await api.unassignEscalation(escalation.id);
      onUpdate(updated);
      sileo.success({ title: "Escalación liberada" });
    } catch (err) {
      const error = err as Error;
      setOptimisticEscalation(escalation); // revert
      sileo.error({
        title: "No se pudo liberar",
        description: error.message ?? "Error desconocido",
      });
    } finally {
      setUiState({ kind: "idle" });
    }
  }, [escalation, onUpdate]);

  const handleResolve = useCallback(async () => {
    setUiState({ kind: "resolving" });

    try {
      const updated = await api.resolveEscalation(escalation.id);
      onUpdate(updated);
      sileo.success({ title: "Escalación resuelta" });
    } catch (err) {
      const error = err as Error;
      sileo.error({
        title: "No se pudo resolver",
        description: error.message ?? "Error desconocido",
      });
    } finally {
      setUiState({ kind: "idle" });
    }
  }, [escalation.id, onUpdate]);

  // ─── pending ───────────────────────────────────────────────────────────────
  if (currentEscalation.status === "pending") {
    return (
      <div className="flex items-center gap-2 flex-wrap">
        <Button
          size="sm"
          onClick={handleAssignSelf}
          disabled={uiState.kind !== "idle"}
          className="gap-1.5"
        >
          <UserCheck className="h-3.5 w-3.5" />
          {uiState.kind === "assigning" ? "Asignando..." : "Asignarme"}
        </Button>

        <AssignToDialog
          escalationId={escalation.id}
          onAssigned={(updated) => {
            onUpdate(updated);
            sileo.success({ title: "Escalación asignada" });
          }}
          trigger={
            <Button
              size="sm"
              variant="outline"
              disabled={uiState.kind !== "idle"}
            >
              Asignar a...
            </Button>
          }
        />
      </div>
    );
  }

  // ─── assigned ──────────────────────────────────────────────────────────────
  if (currentEscalation.status === "assigned") {
    const assignedName =
      currentEscalation.assigned_to?.display_name ??
      currentEscalation.assigned_to?.username ??
      "–";

    return (
      <div className="flex items-center gap-2 flex-wrap">
        <Badge
          variant="secondary"
          className={cn("gap-1 text-xs font-medium")}
        >
          <UserCheck className="h-3 w-3" />
          Asignado a {assignedName}
        </Badge>

        {/* Liberar — AlertDialog confirm */}
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button
              size="sm"
              variant="outline"
              disabled={uiState.kind !== "idle"}
            >
              <Unlock className="h-3.5 w-3.5 mr-1" />
              {uiState.kind === "unassigning" ? "Liberando..." : "Liberar"}
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>¿Liberar escalación?</AlertDialogTitle>
              <AlertDialogDescription>
                La escalación volverá a estado pendiente. El bot seguirá pausado
                hasta que lo reanudes manualmente.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancelar</AlertDialogCancel>
              <AlertDialogAction onClick={handleUnassign}>
                Liberar
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        {/* Resolver — AlertDialog confirm */}
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button
              size="sm"
              disabled={uiState.kind !== "idle"}
              className="gap-1.5"
            >
              <CheckCircle className="h-3.5 w-3.5" />
              {uiState.kind === "resolving" ? "Resolviendo..." : "Resolver"}
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>¿Resolver escalación?</AlertDialogTitle>
              <AlertDialogDescription>
                La escalación se marcará como resuelta. El bot sigue pausado —
                reanúdalo desde la conversación si querés que el bot vuelva a
                responder.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancelar</AlertDialogCancel>
              <AlertDialogAction onClick={handleResolve}>
                Resolver
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        {/* Reanudar bot — TODO: wire resumeBot when escalation carries conversation_history_id
         * Spec scenario 4.10 (Rule 8): Reanudar bot without resolving → only bot_paused_at cleared.
         * The resumeBot API takes a conversation_history_id (not conversation_id string).
         * Escalation.conversation_id is the Chatwoot conversation string ID; we need the
         * conversation_history UUID. Exposing it requires extending EscalationResponse in C2.9.
         * For now, render a disabled button as a placeholder. */}
        <Button
          size="sm"
          variant="ghost"
          disabled
          title="Disponible en la próxima versión — reanuda el bot desde la conversación"
          className="gap-1.5 text-muted-foreground"
        >
          <Play className="h-3.5 w-3.5" />
          Reanudar bot
        </Button>
      </div>
    );
  }

  // ─── resolved ──────────────────────────────────────────────────────────────
  const resolvedName =
    currentEscalation.resolved_by ?? "–";

  return (
    <div className="flex items-center gap-2">
      <Badge variant="outline" className="text-xs text-muted-foreground">
        <CheckCircle className="h-3 w-3 mr-1" />
        Resuelto por {resolvedName}
      </Badge>
    </div>
  );
}
