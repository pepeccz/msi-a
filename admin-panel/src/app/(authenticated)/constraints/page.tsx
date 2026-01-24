"use client";

import { useState, useEffect, useCallback } from "react";
import { Plus, Pencil, Trash2, Shield, ShieldCheck, ShieldX } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import type { ResponseConstraint, ResponseConstraintCreate, ResponseConstraintUpdate, VehicleCategory } from "@/lib/types";

export default function ConstraintsPage() {
  const [constraints, setConstraints] = useState<ResponseConstraint[]>([]);
  const [categories, setCategories] = useState<VehicleCategory[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editingConstraint, setEditingConstraint] = useState<ResponseConstraint | null>(null);

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
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Eliminar este constraint?")) return;
    try {
      await api.deleteConstraint(id);
      toast.success("Constraint eliminado");
      loadData();
    } catch (error) {
      toast.error("Error eliminando constraint");
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

  if (isLoading) {
    return <div className="p-6"><p className="text-muted-foreground">Cargando...</p></div>;
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Shield className="h-6 w-6" />
            Response Constraints
          </h1>
          <p className="text-muted-foreground mt-1">
            Reglas anti-alucinacion que validan las respuestas del agente contra herramientas requeridas
          </p>
        </div>
        <button
          onClick={() => { resetForm(); setEditingConstraint(null); setShowDialog(true); }}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
        >
          <Plus className="h-4 w-4" />
          Nuevo Constraint
        </button>
      </div>

      {/* Constraints List */}
      <div className="space-y-3">
        {constraints.map((constraint) => (
          <div
            key={constraint.id}
            className={`border rounded-lg p-4 ${constraint.is_active ? "bg-card" : "bg-muted/50 opacity-60"}`}
          >
            <div className="flex items-start justify-between">
              <div className="flex-1 space-y-2">
                <div className="flex items-center gap-2">
                  {constraint.is_active ? (
                    <ShieldCheck className="h-4 w-4 text-green-500" />
                  ) : (
                    <ShieldX className="h-4 w-4 text-red-500" />
                  )}
                  <span className="font-mono text-sm font-medium">{constraint.constraint_type}</span>
                  <span className="text-xs bg-secondary px-2 py-0.5 rounded">
                    Prioridad: {constraint.priority}
                  </span>
                  {constraint.category_name && (
                    <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded">
                      {constraint.category_name}
                    </span>
                  )}
                  {!constraint.category_id && (
                    <span className="text-xs bg-purple-100 text-purple-800 px-2 py-0.5 rounded">
                      Global
                    </span>
                  )}
                </div>
                <div className="text-sm space-y-1">
                  <p><span className="text-muted-foreground">Patron:</span>{" "}
                    <code className="text-xs bg-muted px-1 py-0.5 rounded break-all">{constraint.detection_pattern}</code>
                  </p>
                  <p><span className="text-muted-foreground">Tool requerido:</span>{" "}
                    <code className="text-xs bg-muted px-1 py-0.5 rounded">{constraint.required_tool}</code>
                  </p>
                  <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                    {constraint.error_injection.substring(0, 150)}...
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1 ml-4">
                <button
                  onClick={() => handleToggleActive(constraint)}
                  className="p-2 hover:bg-secondary rounded"
                  title={constraint.is_active ? "Desactivar" : "Activar"}
                >
                  {constraint.is_active ? (
                    <ShieldCheck className="h-4 w-4 text-green-500" />
                  ) : (
                    <ShieldX className="h-4 w-4 text-red-500" />
                  )}
                </button>
                <button
                  onClick={() => openEdit(constraint)}
                  className="p-2 hover:bg-secondary rounded"
                >
                  <Pencil className="h-4 w-4" />
                </button>
                <button
                  onClick={() => handleDelete(constraint.id)}
                  className="p-2 hover:bg-destructive/10 rounded text-destructive"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        ))}
        {constraints.length === 0 && (
          <p className="text-center text-muted-foreground py-8">No hay constraints configurados</p>
        )}
      </div>

      {/* Dialog */}
      {showDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-card border rounded-lg p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <h2 className="text-lg font-bold mb-4">
              {editingConstraint ? "Editar Constraint" : "Nuevo Constraint"}
            </h2>
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium">Categoria (opcional - vacio = global)</label>
                <select
                  value={form.category_id || ""}
                  onChange={(e) => setForm({ ...form, category_id: e.target.value || null })}
                  className="w-full mt-1 px-3 py-2 border rounded-md bg-background"
                >
                  <option value="">Global (todas las categorias)</option>
                  {categories.map((cat) => (
                    <option key={cat.id} value={cat.id}>{cat.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm font-medium">Tipo de Constraint</label>
                <input
                  type="text"
                  value={form.constraint_type}
                  onChange={(e) => setForm({ ...form, constraint_type: e.target.value })}
                  placeholder="ej: price_requires_tool"
                  className="w-full mt-1 px-3 py-2 border rounded-md bg-background"
                />
              </div>
              <div>
                <label className="text-sm font-medium">Patron de Deteccion (regex)</label>
                <input
                  type="text"
                  value={form.detection_pattern}
                  onChange={(e) => setForm({ ...form, detection_pattern: e.target.value })}
                  placeholder="\\d+\\s*€|presupuesto.*\\d+"
                  className="w-full mt-1 px-3 py-2 border rounded-md bg-background font-mono text-sm"
                />
                <p className="text-xs text-muted-foreground mt-1">Regex que detecta una posible violacion en la respuesta del LLM</p>
              </div>
              <div>
                <label className="text-sm font-medium">Tool Requerido (pipe-separated para multiples)</label>
                <input
                  type="text"
                  value={form.required_tool}
                  onChange={(e) => setForm({ ...form, required_tool: e.target.value })}
                  placeholder="calcular_tarifa_con_elementos|obtener_documentacion_elemento"
                  className="w-full mt-1 px-3 py-2 border rounded-md bg-background font-mono text-sm"
                />
              </div>
              <div>
                <label className="text-sm font-medium">Mensaje de Correccion (inyectado al LLM)</label>
                <textarea
                  value={form.error_injection}
                  onChange={(e) => setForm({ ...form, error_injection: e.target.value })}
                  rows={4}
                  placeholder="CORRECCION OBLIGATORIA: ..."
                  className="w-full mt-1 px-3 py-2 border rounded-md bg-background text-sm"
                />
              </div>
              <div className="flex gap-4">
                <div>
                  <label className="text-sm font-medium">Prioridad</label>
                  <input
                    type="number"
                    value={form.priority}
                    onChange={(e) => setForm({ ...form, priority: parseInt(e.target.value) || 0 })}
                    className="w-24 mt-1 px-3 py-2 border rounded-md bg-background"
                  />
                </div>
                <div className="flex items-center gap-2 pt-6">
                  <input
                    type="checkbox"
                    checked={form.is_active}
                    onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                    className="h-4 w-4"
                  />
                  <label className="text-sm">Activo</label>
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={() => { setShowDialog(false); setEditingConstraint(null); }}
                className="px-4 py-2 border rounded-md hover:bg-secondary"
              >
                Cancelar
              </button>
              <button
                onClick={handleSubmit}
                className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
              >
                {editingConstraint ? "Guardar" : "Crear"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
