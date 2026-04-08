"use client";

import { useState, useEffect, useCallback } from "react";
import { Plus, Pencil, Trash2, Shield, ShieldCheck, ShieldX } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import type { ResponseConstraint, ResponseConstraintCreate, ResponseConstraintUpdate, VehicleCategory } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
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
import { PageHeader } from "@/components/shared/page-header";
import { cn } from "@/lib/utils";

export default function ConstraintsPage() {
  const [constraints, setConstraints] = useState<ResponseConstraint[]>([]);
  const [categories, setCategories] = useState<VehicleCategory[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editingConstraint, setEditingConstraint] = useState<ResponseConstraint | null>(null);

  // Delete confirmation dialog state
  const [deleteTarget, setDeleteTarget] = useState<ResponseConstraint | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // Form state
  const [form, setForm] = useState<ResponseConstraintCreate>({
    category_id: null,
    constraint_type: "",
    detection_pattern: "",
    required_tool: "",
    error_injection: "",
    is_active: true,
    priority: 0,
  });

  const loadData = useCallback(async () => {
    try {
      setIsLoading(true);
      const [constraintData, catData] = await Promise.all([
        api.getConstraints(),
        api.getVehicleCategories(),
      ]);
      setConstraints(constraintData);
      setCategories(catData.items || []);
    } catch (error) {
      toast.error("Error cargando constraints");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleSubmit = async () => {
    setIsSaving(true);
    try {
      if (editingConstraint) {
        const updateData: ResponseConstraintUpdate = { ...form };
        await api.updateConstraint(editingConstraint.id, updateData);
        toast.success("Constraint actualizado");
      } else {
        await api.createConstraint(form);
        toast.success("Constraint creado");
      }
      setShowDialog(false);
      setEditingConstraint(null);
      resetForm();
      loadData();
    } catch (error) {
      toast.error("Error guardando constraint");
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    setIsDeleting(true);
    try {
      await api.deleteConstraint(deleteTarget.id);
      toast.success("Constraint eliminado");
      setDeleteTarget(null);
      loadData();
    } catch (error) {
      toast.error("Error eliminando constraint");
    } finally {
      setIsDeleting(false);
    }
  };

  const handleToggleActive = async (constraint: ResponseConstraint) => {
    try {
      await api.updateConstraint(constraint.id, { is_active: !constraint.is_active });
      toast.success(constraint.is_active ? "Constraint desactivado" : "Constraint activado");
      loadData();
    } catch (error) {
      toast.error("Error actualizando constraint");
    }
  };

  const openEdit = (constraint: ResponseConstraint) => {
    setEditingConstraint(constraint);
    setForm({
      category_id: constraint.category_id,
      constraint_type: constraint.constraint_type,
      detection_pattern: constraint.detection_pattern,
      required_tool: constraint.required_tool,
      error_injection: constraint.error_injection,
      is_active: constraint.is_active,
      priority: constraint.priority,
    });
    setShowDialog(true);
  };

  const resetForm = () => {
    setForm({
      category_id: null,
      constraint_type: "",
      detection_pattern: "",
      required_tool: "",
      error_injection: "",
      is_active: true,
      priority: 0,
    });
  };

  const handleOpenCreate = () => {
    resetForm();
    setEditingConstraint(null);
    setShowDialog(true);
  };

  const handleDialogOpenChange = (open: boolean) => {
    setShowDialog(open);
    if (!open) {
      setEditingConstraint(null);
      resetForm();
    }
  };

  if (isLoading) {
    return (
      <div className="p-6">
        <p className="text-muted-foreground animate-pulse">Cargando...</p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title="Response Constraints"
        description="Reglas anti-alucinacion que validan las respuestas del agente contra herramientas requeridas"
        actions={
          <Button onClick={handleOpenCreate}>
            <Plus className="h-4 w-4" />
            Nuevo Constraint
          </Button>
        }
      />

      {/* Constraints List */}
      <div className="space-y-3">
        {constraints.map((constraint) => (
          <div
            key={constraint.id}
            className={cn(
              "border rounded-lg p-4",
              constraint.is_active ? "bg-card" : "bg-muted/50 opacity-60"
            )}
          >
            <div className="flex items-start justify-between">
              <div className="flex-1 space-y-2">
                <div className="flex items-center gap-2 flex-wrap">
                  {constraint.is_active ? (
                    <ShieldCheck className="h-4 w-4 text-green-500 shrink-0" />
                  ) : (
                    <ShieldX className="h-4 w-4 text-red-500 shrink-0" />
                  )}
                  <span className="font-mono text-sm font-medium">{constraint.constraint_type}</span>
                  <span className="text-xs bg-secondary px-2 py-0.5 rounded">
                    Prioridad: {constraint.priority}
                  </span>
                  {constraint.category_name && (
                    <span className="text-xs bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300 px-2 py-0.5 rounded">
                      {constraint.category_name}
                    </span>
                  )}
                  {!constraint.category_id && (
                    <span className="text-xs bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300 px-2 py-0.5 rounded">
                      Global
                    </span>
                  )}
                </div>
                <div className="text-sm space-y-1">
                  <p>
                    <span className="text-muted-foreground">Patron:</span>{" "}
                    <code className="text-xs bg-muted px-1 py-0.5 rounded break-all">{constraint.detection_pattern}</code>
                  </p>
                  <p>
                    <span className="text-muted-foreground">Tool requerido:</span>{" "}
                    <code className="text-xs bg-muted px-1 py-0.5 rounded">{constraint.required_tool}</code>
                  </p>
                  <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                    {constraint.error_injection.substring(0, 150)}...
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1 ml-4 shrink-0">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => handleToggleActive(constraint)}
                  title={constraint.is_active ? "Desactivar" : "Activar"}
                >
                  {constraint.is_active ? (
                    <ShieldCheck className="h-4 w-4 text-green-500" />
                  ) : (
                    <ShieldX className="h-4 w-4 text-red-500" />
                  )}
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => openEdit(constraint)}
                  title="Editar"
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="text-destructive hover:text-destructive hover:bg-destructive/10"
                  onClick={() => setDeleteTarget(constraint)}
                  title="Eliminar"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </div>
        ))}

        {constraints.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <Shield className="h-12 w-12 text-muted-foreground mb-3" />
            <p className="text-muted-foreground">No hay constraints configurados</p>
          </div>
        )}
      </div>

      {/* Create / Edit Dialog */}
      <Dialog open={showDialog} onOpenChange={handleDialogOpenChange}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {editingConstraint ? "Editar Constraint" : "Nuevo Constraint"}
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4 py-2">
            {/* Category */}
            <div className="space-y-1.5">
              <Label htmlFor="constraint-category">
                Categoria <span className="text-muted-foreground font-normal">(opcional — vacio = global)</span>
              </Label>
              <Select
                value={form.category_id || ""}
                onValueChange={(value) =>
                  setForm({ ...form, category_id: value === "__global__" ? null : value })
                }
              >
                <SelectTrigger id="constraint-category">
                  <SelectValue placeholder="Global (todas las categorias)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__global__">Global (todas las categorias)</SelectItem>
                  {categories.map((cat) => (
                    <SelectItem key={cat.id} value={cat.id}>
                      {cat.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Constraint Type */}
            <div className="space-y-1.5">
              <Label htmlFor="constraint-type">Tipo de Constraint</Label>
              <Input
                id="constraint-type"
                value={form.constraint_type}
                onChange={(e) => setForm({ ...form, constraint_type: e.target.value })}
                placeholder="ej: price_requires_tool"
              />
            </div>

            {/* Detection Pattern */}
            <div className="space-y-1.5">
              <Label htmlFor="constraint-pattern">Patron de Deteccion (regex)</Label>
              <Input
                id="constraint-pattern"
                value={form.detection_pattern}
                onChange={(e) => setForm({ ...form, detection_pattern: e.target.value })}
                placeholder="\d+\s*€|presupuesto.*\d+"
                className="font-mono text-sm"
              />
              <p className="text-xs text-muted-foreground">
                Regex que detecta una posible violacion en la respuesta del LLM
              </p>
            </div>

            {/* Required Tool */}
            <div className="space-y-1.5">
              <Label htmlFor="constraint-tool">
                Tool Requerido{" "}
                <span className="text-muted-foreground font-normal">(pipe-separated para multiples)</span>
              </Label>
              <Input
                id="constraint-tool"
                value={form.required_tool}
                onChange={(e) => setForm({ ...form, required_tool: e.target.value })}
                placeholder="calcular_tarifa_con_elementos|obtener_documentacion_elemento"
                className="font-mono text-sm"
              />
            </div>

            {/* Error Injection */}
            <div className="space-y-1.5">
              <Label htmlFor="constraint-injection">Mensaje de Correccion (inyectado al LLM)</Label>
              <Textarea
                id="constraint-injection"
                value={form.error_injection}
                onChange={(e) => setForm({ ...form, error_injection: e.target.value })}
                rows={4}
                placeholder="CORRECCION OBLIGATORIA: ..."
                className="text-sm resize-none"
              />
            </div>

            {/* Priority + Active */}
            <div className="flex gap-6 items-end">
              <div className="space-y-1.5">
                <Label htmlFor="constraint-priority">Prioridad</Label>
                <Input
                  id="constraint-priority"
                  type="number"
                  value={form.priority}
                  onChange={(e) =>
                    setForm({ ...form, priority: parseInt(e.target.value) || 0 })
                  }
                  className="w-24"
                />
              </div>
              <div className="flex items-center gap-2 pb-1">
                <Switch
                  id="constraint-active"
                  checked={form.is_active}
                  onCheckedChange={(checked) => setForm({ ...form, is_active: checked })}
                />
                <Label htmlFor="constraint-active" className="cursor-pointer">
                  Activo
                </Label>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => handleDialogOpenChange(false)}
              disabled={isSaving}
            >
              Cancelar
            </Button>
            <Button onClick={handleSubmit} disabled={isSaving}>
              {isSaving ? "Guardando..." : editingConstraint ? "Guardar" : "Crear"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation AlertDialog */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Eliminar este constraint?</AlertDialogTitle>
            <AlertDialogDescription>
              {deleteTarget && (
                <>
                  Se eliminará el constraint{" "}
                  <span className="font-mono font-medium text-foreground">
                    {deleteTarget.constraint_type}
                  </span>
                  . Esta acción no se puede deshacer.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
              disabled={isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? "Eliminando..." : "Eliminar"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
