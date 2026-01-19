"use client";

import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { AlertTriangle, Plus, Trash2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import type { Element, Warning, ElementWarningAssociation, ShowCondition, WarningSeverity } from "@/lib/types";

interface ElementWarningsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  element: Element | null;
  onSuccess?: () => void;
}

export function ElementWarningsDialog({
  open,
  onOpenChange,
  element,
  onSuccess,
}: ElementWarningsDialogProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [associations, setAssociations] = useState<ElementWarningAssociation[]>([]);
  const [allWarnings, setAllWarnings] = useState<Warning[]>([]);
  const [selectedWarningId, setSelectedWarningId] = useState<string>("");
  const [showCondition, setShowCondition] = useState<ShowCondition>("always");
  const [thresholdQuantity, setThresholdQuantity] = useState<string>("");
  const [isAdding, setIsAdding] = useState(false);

  // New warning form state
  const [newWarningCode, setNewWarningCode] = useState("");
  const [newWarningMessage, setNewWarningMessage] = useState("");
  const [newWarningSeverity, setNewWarningSeverity] = useState<WarningSeverity>("warning");
  const [isCreating, setIsCreating] = useState(false);

  useEffect(() => {
    if (open && element) {
      fetchData();
    }
  }, [open, element]);

  const fetchData = async () => {
    if (!element) return;

    setIsLoading(true);
    try {
      const [assocs, warningsData] = await Promise.all([
        api.getElementWarnings(element.id),
        api.getWarnings({ limit: 100 }),
      ]);
      setAssociations(assocs);
      setAllWarnings(warningsData.items);
    } catch (error) {
      console.error("Error fetching data:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleAddAssociation = async () => {
    if (!element || !selectedWarningId) return;

    setIsAdding(true);
    try {
      await api.createElementWarningAssociation(element.id, {
        warning_id: selectedWarningId,
        show_condition: showCondition,
        threshold_quantity: thresholdQuantity ? parseInt(thresholdQuantity) : null,
      });
      await fetchData();
      setSelectedWarningId("");
      setShowCondition("always");
      setThresholdQuantity("");
      onSuccess?.();
    } catch (error) {
      console.error("Error adding association:", error);
      toast.error("Error al asociar la advertencia");
    } finally {
      setIsAdding(false);
    }
  };

  const handleRemoveAssociation = async (warningId: string) => {
    if (!element) return;

    try {
      await api.deleteElementWarningAssociation(element.id, warningId);
      setAssociations((prev) => prev.filter((a) => a.warning_id !== warningId));
      onSuccess?.();
    } catch (error) {
      console.error("Error removing association:", error);
      toast.error("Error al eliminar la asociacion");
    }
  };

  const handleCreateAndAssociate = async () => {
    if (!element || !newWarningCode || !newWarningMessage) return;

    setIsCreating(true);
    try {
      // Create the new warning
      const newWarning = await api.createWarning({
        code: newWarningCode,
        message: newWarningMessage,
        severity: newWarningSeverity,
        is_active: true,
      });

      // Associate it with the element
      await api.createElementWarningAssociation(element.id, {
        warning_id: newWarning.id,
        show_condition: showCondition,
        threshold_quantity: thresholdQuantity ? parseInt(thresholdQuantity) : null,
      });

      // Refresh data and reset form
      await fetchData();
      setNewWarningCode("");
      setNewWarningMessage("");
      setNewWarningSeverity("warning");
      setShowCondition("always");
      setThresholdQuantity("");
      onSuccess?.();
    } catch (error) {
      console.error("Error creating warning:", error);
      toast.error("Error al crear la advertencia. Verifica que el codigo no exista.");
    } finally {
      setIsCreating(false);
    }
  };

  const getWarningById = (id: string) => allWarnings.find((w) => w.id === id);

  const availableWarnings = allWarnings.filter(
    (w) => !associations.some((a) => a.warning_id === w.id)
  );

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case "error":
        return "destructive";
      case "warning":
        return "default";
      default:
        return "secondary";
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5" />
            Advertencias: {element?.name}
          </DialogTitle>
          <DialogDescription>
            Gestiona las advertencias asociadas a este elemento. Las advertencias
            se mostraran cuando este elemento sea seleccionado.
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="space-y-6">
            {/* Current Associations */}
            <div className="space-y-3">
              <h3 className="text-sm font-semibold">Advertencias Asociadas</h3>
              {associations.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  No hay advertencias asociadas a este elemento
                </p>
              ) : (
                <div className="space-y-2">
                  {associations.map((assoc) => {
                    const warning = getWarningById(assoc.warning_id);
                    if (!warning) return null;

                    return (
                      <div
                        key={assoc.id}
                        className="flex items-start justify-between gap-3 p-3 border rounded-lg"
                      >
                        <div className="flex-1 space-y-1">
                          <div className="flex items-center gap-2">
                            <Badge variant={getSeverityColor(warning.severity)}>
                              {warning.severity}
                            </Badge>
                            <code className="text-xs bg-muted px-1.5 py-0.5 rounded">
                              {warning.code}
                            </code>
                          </div>
                          <p className="text-sm">{warning.message}</p>
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <span>Condicion: {assoc.show_condition}</span>
                            {assoc.threshold_quantity && (
                              <span>• Cantidad minima: {assoc.threshold_quantity}</span>
                            )}
                          </div>
                        </div>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-destructive hover:text-destructive"
                          onClick={() => handleRemoveAssociation(assoc.warning_id)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Add New Association */}
            <div className="space-y-4 border-t pt-4">
              <h3 className="text-sm font-semibold">Agregar Advertencia</h3>

              {availableWarnings.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-2">
                  No hay mas advertencias disponibles para asociar
                </p>
              ) : (
                <>
                  <div className="space-y-2">
                    <Label>Advertencia</Label>
                    <Select value={selectedWarningId} onValueChange={setSelectedWarningId}>
                      <SelectTrigger>
                        <SelectValue placeholder="Selecciona una advertencia" />
                      </SelectTrigger>
                      <SelectContent>
                        {availableWarnings.map((warning) => (
                          <SelectItem key={warning.id} value={warning.id}>
                            <div className="flex items-center gap-2">
                              <Badge
                                variant={getSeverityColor(warning.severity)}
                                className="text-xs"
                              >
                                {warning.severity}
                              </Badge>
                              <span className="text-xs text-muted-foreground">
                                {warning.code}
                              </span>
                              <span className="truncate max-w-[300px]">
                                {warning.message.substring(0, 50)}
                                {warning.message.length > 50 ? "..." : ""}
                              </span>
                            </div>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>Condicion</Label>
                      <Select
                        value={showCondition}
                        onValueChange={(v) => setShowCondition(v as ShowCondition)}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="always">Siempre</SelectItem>
                          <SelectItem value="if_selected">Si seleccionado</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-2">
                      <Label>Cantidad minima (opcional)</Label>
                      <Input
                        type="number"
                        min="1"
                        value={thresholdQuantity}
                        onChange={(e) => setThresholdQuantity(e.target.value)}
                        placeholder="Ej: 5"
                      />
                    </div>
                  </div>

                  <Button
                    onClick={handleAddAssociation}
                    disabled={!selectedWarningId || isAdding}
                    className="w-full"
                  >
                    {isAdding ? (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <Plus className="h-4 w-4 mr-2" />
                    )}
                    Asociar Advertencia
                  </Button>
                </>
              )}
            </div>

            {/* Separator */}
            <div className="relative py-4">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t" />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-background px-2 text-muted-foreground">
                  o crear nueva
                </span>
              </div>
            </div>

            {/* Create New Warning */}
            <div className="space-y-4">
              <h3 className="text-sm font-semibold">Crear Nueva Advertencia</h3>

              <div className="space-y-2">
                <Label>Codigo</Label>
                <Input
                  value={newWarningCode}
                  onChange={(e) =>
                    setNewWarningCode(
                      e.target.value.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "")
                    )
                  }
                  placeholder="ej: marcado_obligatorio"
                  disabled={isCreating}
                />
                <p className="text-xs text-muted-foreground">
                  Solo letras minusculas, numeros y guiones bajos
                </p>
              </div>

              <div className="space-y-2">
                <Label>Mensaje</Label>
                <Textarea
                  value={newWarningMessage}
                  onChange={(e) => setNewWarningMessage(e.target.value)}
                  placeholder="Mensaje de la advertencia..."
                  rows={2}
                  disabled={isCreating}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Severidad</Label>
                  <Select
                    value={newWarningSeverity}
                    onValueChange={(value: WarningSeverity) => setNewWarningSeverity(value)}
                    disabled={isCreating}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="info">Info</SelectItem>
                      <SelectItem value="warning">Warning</SelectItem>
                      <SelectItem value="error">Error</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label>Condicion</Label>
                  <Select
                    value={showCondition}
                    onValueChange={(v) => setShowCondition(v as ShowCondition)}
                    disabled={isCreating}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="always">Siempre</SelectItem>
                      <SelectItem value="if_selected">Si seleccionado</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <Button
                onClick={handleCreateAndAssociate}
                disabled={!newWarningCode || !newWarningMessage || isCreating}
                className="w-full"
                variant="secondary"
              >
                {isCreating ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Plus className="h-4 w-4 mr-2" />
                )}
                Crear y Asociar
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
