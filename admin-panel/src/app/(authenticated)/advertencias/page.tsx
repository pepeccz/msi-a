"use client";

import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  AlertTriangle,
  Plus,
  Pencil,
  Info,
  XCircle,
  Trash2,
  X,
  CheckCircle2,
  Zap,
} from "lucide-react";
import { PageContainer } from "@/components/shared/page-container";
import { PageHeader } from "@/components/shared/page-header";
import { FilterBar } from "@/components/shared/filter-bar";
import api from "@/lib/api";
import { sileo } from "sileo";
import type {
  Warning,
  WarningCreate,
  WarningUpdate,
  WarningSeverity,
  TriggerConditions,
} from "@/lib/types";

const severityIcons = {
  info: <Info className="h-4 w-4" />,
  warning: <AlertTriangle className="h-4 w-4" />,
  error: <XCircle className="h-4 w-4" />,
};

const severityColors = {
  info: "bg-blue-100 text-blue-800 border-blue-200",
  warning: "bg-yellow-100 text-yellow-800 border-yellow-200",
  error: "bg-red-100 text-red-800 border-red-200",
};

const severityLabels = {
  info: "Informativo",
  warning: "Advertencia",
  error: "Error",
};

export default function AdvertenciasPage() {
  const [warnings, setWarnings] = useState<Warning[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");

  // Edit/Create dialog
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [editingWarning, setEditingWarning] = useState<Warning | null>(null);
  const [editForm, setEditForm] = useState<{
    code: string;
    message: string;
    severity: WarningSeverity;
    is_active: boolean;
    trigger_conditions: TriggerConditions;
  }>({
    code: "",
    message: "",
    severity: "warning",
    is_active: true,
    trigger_conditions: {
      element_keywords: [],
      show_with_elements: [],
      always_show: false,
    },
  });
  const [isSaving, setIsSaving] = useState(false);

  // Keyword input
  const [keywordInput, setKeywordInput] = useState("");
  const [elementInput, setElementInput] = useState("");

  // Delete dialog
  const [deleteWarning, setDeleteWarning] = useState<Warning | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    fetchWarnings();
  }, []);

  async function fetchWarnings() {
    try {
      const data = await api.getWarnings({ limit: 100 });
      setWarnings(data.items);
    } catch (error) {
      console.error("Error fetching warnings:", error);
    } finally {
      setIsLoading(false);
    }
  }

  const filteredWarnings = warnings.filter((warning) => {
    const search = searchQuery.toLowerCase();
    return (
      warning.code.toLowerCase().includes(search) ||
      warning.message.toLowerCase().includes(search)
    );
  });

  const openCreateDialog = () => {
    setEditingWarning(null);
    setEditForm({
      code: "",
      message: "",
      severity: "warning",
      is_active: true,
      trigger_conditions: {
        element_keywords: [],
        show_with_elements: [],
        always_show: false,
      },
    });
    setKeywordInput("");
    setElementInput("");
    setIsEditDialogOpen(true);
  };

  const openEditDialog = (warning: Warning) => {
    setEditingWarning(warning);
    setEditForm({
      code: warning.code,
      message: warning.message,
      severity: warning.severity,
      is_active: warning.is_active,
      trigger_conditions: warning.trigger_conditions || {
        element_keywords: [],
        show_with_elements: [],
        always_show: false,
      },
    });
    setKeywordInput("");
    setElementInput("");
    setIsEditDialogOpen(true);
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      if (editingWarning) {
        const updateData: WarningUpdate = {
          code: editForm.code,
          message: editForm.message,
          severity: editForm.severity,
          is_active: editForm.is_active,
          trigger_conditions: editForm.trigger_conditions,
        };
        await api.updateWarning(editingWarning.id, updateData);
      } else {
        const createData: WarningCreate = {
          code: editForm.code,
          message: editForm.message,
          severity: editForm.severity,
          is_active: editForm.is_active,
          trigger_conditions: editForm.trigger_conditions,
        };
        await api.createWarning(createData);
      }
      setIsEditDialogOpen(false);
      fetchWarnings();
    } catch (error) {
      console.error("Error saving warning:", error);
      sileo.error({ title: editingWarning ? "Error al guardar advertencia" : "Error al crear advertencia" });
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteWarning) return;
    setIsDeleting(true);
    try {
      await api.deleteWarning(deleteWarning.id);
      setDeleteWarning(null);
      fetchWarnings();
    } catch (error) {
      console.error("Error deleting warning:", error);
      sileo.error({ title: "Error al eliminar advertencia" });
    } finally {
      setIsDeleting(false);
    }
  };

  const addKeyword = () => {
    const keyword = keywordInput.trim().toLowerCase();
    if (keyword && !(editForm.trigger_conditions?.element_keywords ?? []).includes(keyword)) {
      setEditForm((prev) => ({
        ...prev,
        trigger_conditions: {
          ...prev.trigger_conditions,
          element_keywords: [...(prev.trigger_conditions?.element_keywords ?? []), keyword],
        },
      }));
      setKeywordInput("");
    }
  };

  const removeKeyword = (keyword: string) => {
    setEditForm((prev) => ({
      ...prev,
      trigger_conditions: {
        ...prev.trigger_conditions,
        element_keywords: (prev.trigger_conditions?.element_keywords ?? []).filter((k) => k !== keyword),
      },
    }));
  };

  const addElement = () => {
    const element = elementInput.trim().toLowerCase();
    if (element && !(editForm.trigger_conditions?.show_with_elements ?? []).includes(element)) {
      setEditForm((prev) => ({
        ...prev,
        trigger_conditions: {
          ...prev.trigger_conditions,
          show_with_elements: [...(prev.trigger_conditions?.show_with_elements ?? []), element],
        },
      }));
      setElementInput("");
    }
  };

  const removeElement = (element: string) => {
    setEditForm((prev) => ({
      ...prev,
      trigger_conditions: {
        ...prev.trigger_conditions,
        show_with_elements: (prev.trigger_conditions?.show_with_elements ?? []).filter((e) => e !== element),
      },
    }));
  };

  const getTriggerSummary = (tc: TriggerConditions | null) => {
    if (!tc) return "-";
    const parts: string[] = [];
    if (tc.always_show) parts.push("Siempre");
    if (tc.element_keywords?.length > 0) {
      parts.push(`Keywords: ${tc.element_keywords.slice(0, 2).join(", ")}${tc.element_keywords.length > 2 ? "..." : ""}`);
    }
    if (tc.show_with_elements?.length > 0) {
      parts.push(`Elementos: ${tc.show_with_elements.slice(0, 2).join(", ")}${tc.show_with_elements.length > 2 ? "..." : ""}`);
    }
    return parts.length > 0 ? parts.join(" | ") : "-";
  };

  return (
    <PageContainer className="space-y-6">
      <PageHeader
        title="Advertencias"
        description="Gestiona las advertencias que se muestran a los clientes"
        actions={
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">
              {warnings.length} advertencias
            </span>
          </div>
        }
      />

      {/* Summary Strip */}
      <div className="flex flex-wrap items-center gap-4 px-4 py-3 bg-muted/50 rounded-lg border text-sm">
        <span className="flex items-center gap-1.5">
          <Info className="h-4 w-4 text-blue-500" />
          <span className="text-muted-foreground">Informativas:</span>
          <span className="font-semibold">{warnings.filter((w) => w.severity === "info").length}</span>
        </span>
        <span className="flex items-center gap-1.5">
          <AlertTriangle className="h-4 w-4 text-yellow-500" />
          <span className="text-muted-foreground">Advertencias:</span>
          <span className="font-semibold">{warnings.filter((w) => w.severity === "warning").length}</span>
        </span>
        <span className="flex items-center gap-1.5">
          <XCircle className="h-4 w-4 text-red-500" />
          <span className="text-muted-foreground">Errores:</span>
          <span className="font-semibold">{warnings.filter((w) => w.severity === "error").length}</span>
        </span>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <Button onClick={openCreateDialog}>
              <Plus className="h-4 w-4 mr-2" />
              Nueva Advertencia
            </Button>
          </div>
          <FilterBar
            searchValue={searchQuery}
            onSearchChange={setSearchQuery}
            searchPlaceholder="Buscar por codigo o mensaje..."
            className="mt-4"
          />
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-pulse text-muted-foreground">
                Cargando advertencias...
              </div>
            </div>
          ) : filteredWarnings.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <AlertTriangle className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <p className="text-muted-foreground">
                {searchQuery
                  ? "No se encontraron advertencias con esos criterios"
                  : "No hay advertencias registradas"}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">Tipo</TableHead>
                  <TableHead className="w-36">Codigo</TableHead>
                  <TableHead>Mensaje</TableHead>
                  <TableHead className="w-64">Condiciones</TableHead>
                  <TableHead className="w-24 text-center">Estado</TableHead>
                  <TableHead className="w-24">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredWarnings.map((warning) => (
                  <TableRow key={warning.id}>
                    <TableCell>
                      <div
                        className={`inline-flex items-center justify-center w-8 h-8 rounded-full ${severityColors[warning.severity]}`}
                      >
                        {severityIcons[warning.severity]}
                      </div>
                    </TableCell>
                    <TableCell>
                      <code className="text-xs bg-muted px-2 py-1 rounded">
                        {warning.code}
                      </code>
                    </TableCell>
                    <TableCell className="max-w-md">
                      <p className="text-sm line-clamp-2">{warning.message}</p>
                    </TableCell>
                    <TableCell>
                      <div className="text-xs text-muted-foreground">
                        {getTriggerSummary(warning.trigger_conditions)}
                      </div>
                    </TableCell>
                    <TableCell className="text-center">
                      <Badge
                        variant={warning.is_active ? "default" : "secondary"}
                        className={warning.is_active ? "bg-green-600" : ""}
                      >
                        {warning.is_active ? (
                          <>
                            <CheckCircle2 className="h-3 w-3 mr-1" />
                            Activo
                          </>
                        ) : (
                          "Inactivo"
                        )}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <TooltipProvider>
                        <div className="flex gap-1">
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => openEditDialog(warning)}
                              >
                                <Pencil className="h-4 w-4" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>Editar advertencia</TooltipContent>
                          </Tooltip>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => setDeleteWarning(warning)}
                                className="text-destructive hover:text-destructive"
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>Eliminar advertencia</TooltipContent>
                          </Tooltip>
                        </div>
                      </TooltipProvider>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Edit/Create Dialog */}
      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editingWarning ? "Editar Advertencia" : "Nueva Advertencia"}
            </DialogTitle>
            <DialogDescription>
              {editingWarning
                ? "Modifica los datos de la advertencia"
                : "Crea una nueva advertencia"}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="code" className="text-xs">
                Codigo
              </Label>
              <Input
                id="code"
                value={editForm.code}
                onChange={(e) =>
                  setEditForm((prev) => ({ ...prev, code: e.target.value.toUpperCase() }))
                }
                placeholder="ADV_001"
                className="h-8 text-sm"
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor="severity" className="text-xs">
                Severidad
              </Label>
              <Select
                value={editForm.severity}
                onValueChange={(value: WarningSeverity) =>
                  setEditForm((prev) => ({ ...prev, severity: value }))
                }
              >
                <SelectTrigger className="h-8 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="info">Informativo</SelectItem>
                  <SelectItem value="warning">Advertencia</SelectItem>
                  <SelectItem value="error">Error</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <Label htmlFor="message" className="text-xs">
                Mensaje
              </Label>
              <Textarea
                id="message"
                value={editForm.message}
                onChange={(e) =>
                  setEditForm((prev) => ({ ...prev, message: e.target.value }))
                }
                placeholder="Mensaje que vera el cliente..."
                className="min-h-[100px]"
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor="is_active" className="text-xs">
                Estado
              </Label>
              <Select
                value={editForm.is_active ? "active" : "inactive"}
                onValueChange={(value) =>
                  setEditForm((prev) => ({ ...prev, is_active: value === "active" }))
                }
              >
                <SelectTrigger className="h-8 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Activo</SelectItem>
                  <SelectItem value="inactive">Inactivo</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <div className="flex items-center gap-2 mb-4 mt-4">
                <Zap className="h-4 w-4 text-yellow-500" />
                <span className="font-medium">Condiciones de Activacion</span>
              </div>

              {/* Always Show */}
              <div className="space-y-1 mb-4">
                <Label className="text-xs">Mostrar siempre</Label>
                <Select
                  value={editForm.trigger_conditions.always_show ? "yes" : "no"}
                  onValueChange={(value) =>
                    setEditForm((prev) => ({
                      ...prev,
                      trigger_conditions: {
                        ...prev.trigger_conditions,
                        always_show: value === "yes",
                      },
                    }))
                  }
                >
                  <SelectTrigger className="h-8 text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="no">No</SelectItem>
                    <SelectItem value="yes">Si</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Element Keywords */}
              <div className="space-y-1 mb-4">
                <Label className="text-xs">Keywords</Label>
                <div className="space-y-2">
                  <div className="flex gap-2">
                    <Input
                      value={keywordInput}
                      onChange={(e) => setKeywordInput(e.target.value)}
                      placeholder="Palabra clave..."
                      onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addKeyword())}
                    />
                    <Button type="button" variant="outline" onClick={addKeyword}>
                      <Plus className="h-4 w-4" />
                    </Button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {(editForm.trigger_conditions?.element_keywords ?? []).map((keyword) => (
                      <Badge key={keyword} variant="secondary" className="gap-1">
                        {keyword}
                        <button type="button" onClick={() => removeKeyword(keyword)}>
                          <X className="h-3 w-3" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    La advertencia se activa si el usuario menciona alguna de estas palabras
                  </p>
                </div>
              </div>

              {/* Show With Elements */}
              <div className="space-y-1">
                <Label className="text-xs">Con elementos</Label>
                <div className="space-y-2">
                  <div className="flex gap-2">
                    <Input
                      value={elementInput}
                      onChange={(e) => setElementInput(e.target.value)}
                      placeholder="Tipo de elemento..."
                      onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addElement())}
                    />
                    <Button type="button" variant="outline" onClick={addElement}>
                      <Plus className="h-4 w-4" />
                    </Button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {(editForm.trigger_conditions?.show_with_elements ?? []).map((element) => (
                      <Badge key={element} variant="outline" className="gap-1">
                        {element}
                        <button type="button" onClick={() => removeElement(element)}>
                          <X className="h-3 w-3" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    La advertencia se activa cuando se detectan estos tipos de elementos
                  </p>
                </div>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsEditDialogOpen(false)}
              disabled={isSaving}
            >
              Cancelar
            </Button>
            <Button
              onClick={handleSave}
              disabled={isSaving || !editForm.code.trim() || !editForm.message.trim()}
            >
              {isSaving ? "Guardando..." : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deleteWarning} onOpenChange={() => setDeleteWarning(null)}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>Eliminar Advertencia</DialogTitle>
            <DialogDescription>
              Estas seguro de eliminar la advertencia &quot;{deleteWarning?.code}&quot;?
              Esta accion no se puede deshacer.
            </DialogDescription>
          </DialogHeader>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteWarning(null)}
              disabled={isDeleting}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={isDeleting}
            >
              {isDeleting ? "Eliminando..." : "Eliminar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}
