"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { sileo } from "sileo";
import api from "@/lib/api";
import type { AdminUser, Escalation } from "@/lib/types";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface AssignToDialogProps {
  escalationId: string;
  onAssigned: (updated: Escalation) => void;
  trigger: React.ReactNode;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AssignToDialog({
  escalationId,
  onAssigned,
  trigger,
}: AssignToDialogProps) {
  const [open, setOpen] = useState(false);
  const [admins, setAdmins] = useState<AdminUser[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const fetchAdmins = useCallback(async () => {
    setIsLoading(true);
    try {
      const result = await api.getAdminUsers({ is_active: true });
      setAdmins(result.items);
    } catch (err) {
      const error = err as Error;
      sileo.error({
        title: "No se pudo cargar la lista de agentes",
        description: error.message,
      });
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      setSelectedId(null);
      fetchAdmins();
    }
  }, [open, fetchAdmins]);

  const handleConfirm = useCallback(async () => {
    if (!selectedId) return;
    setIsSubmitting(true);
    try {
      const updated = await api.assignEscalation(escalationId, selectedId);
      onAssigned(updated);
      setOpen(false);
    } catch (err) {
      const error = err as Error;
      sileo.error({
        title: "No se pudo asignar",
        description: error.message ?? "Error desconocido",
      });
    } finally {
      setIsSubmitting(false);
    }
  }, [escalationId, selectedId, onAssigned]);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>Asignar escalación a un agente</DialogTitle>
        </DialogHeader>

        <div className="py-2 space-y-2 max-h-64 overflow-y-auto">
          {isLoading ? (
            <>
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </>
          ) : admins.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">
              No hay agentes activos disponibles
            </p>
          ) : (
            admins.map((admin) => {
              const label = admin.display_name ?? admin.username;
              const isSelected = selectedId === admin.id;
              return (
                <button
                  key={admin.id}
                  type="button"
                  onClick={() => setSelectedId(admin.id)}
                  className={
                    "w-full text-left px-3 py-2 rounded-md text-sm transition-colors " +
                    (isSelected
                      ? "bg-primary text-primary-foreground"
                      : "hover:bg-muted")
                  }
                >
                  {label}
                  <span className="ml-1 text-xs opacity-70">
                    @{admin.username}
                  </span>
                </button>
              );
            })
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => setOpen(false)}
            disabled={isSubmitting}
          >
            Cancelar
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={!selectedId || isSubmitting}
          >
            {isSubmitting ? "Asignando..." : "Asignar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
