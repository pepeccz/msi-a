"use client";

import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
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
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  FileText,
  Plus,
  Pencil,
  Eye,
  Trash2,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import api from "@/lib/api";
import type {
  VehicleCategory,
  TariffPromptSection,
  TariffPromptSectionCreate,
  TariffPromptSectionUpdate,
  PromptSectionType,
  PromptPreview,
} from "@/lib/types";

const SECTION_TYPES: { value: PromptSectionType; label: string }[] = [
  { value: "algorithm", label: "Algoritmo de Decision" },
  { value: "recognition_table", label: "Tabla de Reconocimiento" },
  { value: "special_cases", label: "Casos Especiales" },
  { value: "footer", label: "Pie de Prompt" },
];

const getSectionLabel = (type: PromptSectionType) => {
  return SECTION_TYPES.find((s) => s.value === type)?.label || type;
};

export default function PromptsPage() {
  const [categories, setCategories] = useState<VehicleCategory[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [sections, setSections] = useState<TariffPromptSection[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSectionsLoading, setIsSectionsLoading] = useState(false);

  // Edit/Create dialog
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [editingSection, setEditingSection] = useState<TariffPromptSection | null>(null);
  const [editForm, setEditForm] = useState<{
    section_type: PromptSectionType;
    content: string;
    is_active: boolean;
  }>({
    section_type: "algorithm",
    content: "",
    is_active: true,
  });
  const [isSaving, setIsSaving] = useState(false);

  // Preview dialog
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [preview, setPreview] = useState<PromptPreview | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [previewClientType, setPreviewClientType] = useState<string>("particular");

  // Delete confirmation
  const [deleteSection, setDeleteSection] = useState<TariffPromptSection | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    fetchCategories();
  }, []);

  useEffect(() => {
    if (selectedCategory) {
      fetchSections();
    }
  }, [selectedCategory]);

  async function fetchCategories() {
    try {
      const data = await api.getVehicleCategories({ limit: 100 });
      setCategories(data.items.filter((c) => c.is_active));
      if (data.items.length > 0) {
        setSelectedCategory(data.items[0].id);
      }
    } catch (error) {
      console.error("Error fetching categories:", error);
    } finally {
      setIsLoading(false);
    }
  }

  async function fetchSections() {
    setIsSectionsLoading(true);
    try {
      const data = await api.getPromptSections({ category_id: selectedCategory });
      setSections(data.items);
    } catch (error) {
      console.error("Error fetching sections:", error);
    } finally {
      setIsSectionsLoading(false);
    }
  }

  const openCreateDialog = () => {
    setEditingSection(null);
    setEditForm({
      section_type: "algorithm",
      content: "",
      is_active: true,
    });
    setIsEditDialogOpen(true);
  };

  const openEditDialog = (section: TariffPromptSection) => {
    setEditingSection(section);
    setEditForm({
      section_type: section.section_type,
      content: section.content,
      is_active: section.is_active,
    });
    setIsEditDialogOpen(true);
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      if (editingSection) {
        // Update
        const updateData: TariffPromptSectionUpdate = {
          content: editForm.content,
          is_active: editForm.is_active,
        };
        await api.updatePromptSection(editingSection.id, updateData);
      } else {
        // Create
        const createData: TariffPromptSectionCreate = {
          category_id: selectedCategory,
          section_type: editForm.section_type,
          content: editForm.content,
          is_active: editForm.is_active,
        };
        await api.createPromptSection(createData);
      }
      setIsEditDialogOpen(false);
      fetchSections();
    } catch (error) {
      console.error("Error saving section:", error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteSection) return;
    setIsDeleting(true);
    try {
      await api.deletePromptSection(deleteSection.id);
      setDeleteSection(null);
      fetchSections();
    } catch (error) {
      console.error("Error deleting section:", error);
    } finally {
      setIsDeleting(false);
    }
  };

  const loadPreview = async () => {
    setIsPreviewLoading(true);
    try {
      const data = await api.previewCategoryPrompt(selectedCategory);
      setPreview(data);
      setIsPreviewOpen(true);
    } catch (error) {
      console.error("Error loading preview:", error);
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const selectedCategoryName =
    categories.find((c) => c.id === selectedCategory)?.name || "";

  // Get which section types are already used
  const usedSectionTypes = sections.map((s) => s.section_type);
  const availableSectionTypes = SECTION_TYPES.filter(
    (t) => !usedSectionTypes.includes(t.value) || editingSection?.section_type === t.value
  );

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Prompts</h1>
          <p className="text-muted-foreground">
            Gestiona las secciones editables de los prompts del agente
          </p>
        </div>
        <div className="flex items-center gap-2">
          <FileText className="h-5 w-5 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">
            {sections.length} secciones
          </span>
        </div>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Secciones de Prompt</CardTitle>
              <CardDescription>
                Cada categoria puede tener secciones personalizadas que se combinan
                con el prompt base
              </CardDescription>
            </div>
            <div className="flex items-center gap-4">
              <Select
                value={selectedCategory}
                onValueChange={setSelectedCategory}
                disabled={isLoading}
              >
                <SelectTrigger className="w-[200px]">
                  <SelectValue placeholder="Seleccionar categoria" />
                </SelectTrigger>
                <SelectContent>
                  {categories.map((category) => (
                    <SelectItem key={category.id} value={category.id}>
                      {category.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading || isSectionsLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-pulse text-muted-foreground">
                Cargando...
              </div>
            </div>
          ) : !selectedCategory ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <FileText className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <p className="text-muted-foreground">
                Selecciona una categoria para ver sus secciones
              </p>
            </div>
          ) : sections.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <FileText className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <p className="text-muted-foreground mb-4">
                No hay secciones definidas para {selectedCategoryName}
              </p>
              <Button onClick={openCreateDialog}>
                <Plus className="h-4 w-4 mr-2" />
                Nueva Seccion
              </Button>
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tipo de Seccion</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead>Version</TableHead>
                    <TableHead>Ultima Actualizacion</TableHead>
                    <TableHead className="w-[120px]">Acciones</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sections.map((section) => (
                    <TableRow key={section.id}>
                      <TableCell>
                        <div className="font-medium">
                          {getSectionLabel(section.section_type)}
                        </div>
                        <div className="text-sm text-muted-foreground">
                          {section.content.length} caracteres
                        </div>
                      </TableCell>
                      <TableCell>
                        {section.is_active ? (
                          <Badge variant="default" className="bg-green-600">
                            <CheckCircle2 className="h-3 w-3 mr-1" />
                            Activo
                          </Badge>
                        ) : (
                          <Badge variant="secondary">
                            <XCircle className="h-3 w-3 mr-1" />
                            Inactivo
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">v{section.version}</Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {new Date(section.updated_at).toLocaleString("es-ES", {
                          day: "2-digit",
                          month: "2-digit",
                          year: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => openEditDialog(section)}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setDeleteSection(section)}
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              <div className="flex justify-between mt-6">
                <Button onClick={openCreateDialog} disabled={availableSectionTypes.length === 0}>
                  <Plus className="h-4 w-4 mr-2" />
                  Nueva Seccion
                </Button>
                <div className="flex items-center gap-2">
                  <Select value={previewClientType} onValueChange={setPreviewClientType}>
                    <SelectTrigger className="w-[140px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="particular">Particular</SelectItem>
                      <SelectItem value="professional">Profesional</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button variant="outline" onClick={loadPreview} disabled={isPreviewLoading}>
                    <Eye className="h-4 w-4 mr-2" />
                    {isPreviewLoading ? "Cargando..." : "Preview Prompt"}
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Edit/Create Dialog */}
      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent className="sm:max-w-[700px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editingSection ? "Editar Seccion" : "Nueva Seccion"}
            </DialogTitle>
            <DialogDescription>
              {editingSection
                ? `Modificando seccion de ${selectedCategoryName}`
                : `Creando nueva seccion para ${selectedCategoryName}`}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="section_type" className="text-right">
                Tipo
              </Label>
              <Select
                value={editForm.section_type}
                onValueChange={(value: PromptSectionType) =>
                  setEditForm((prev) => ({ ...prev, section_type: value }))
                }
                disabled={!!editingSection}
              >
                <SelectTrigger className="col-span-3">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(editingSection ? SECTION_TYPES : availableSectionTypes).map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {type.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-4 items-start gap-4">
              <Label htmlFor="content" className="text-right pt-2">
                Contenido
              </Label>
              <Textarea
                id="content"
                value={editForm.content}
                onChange={(e) =>
                  setEditForm((prev) => ({ ...prev, content: e.target.value }))
                }
                className="col-span-3 min-h-[300px] font-mono text-sm"
                placeholder="Contenido en formato Markdown..."
              />
            </div>

            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="is_active" className="text-right">
                Estado
              </Label>
              <Select
                value={editForm.is_active ? "active" : "inactive"}
                onValueChange={(value) =>
                  setEditForm((prev) => ({ ...prev, is_active: value === "active" }))
                }
              >
                <SelectTrigger className="col-span-3">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Activo</SelectItem>
                  <SelectItem value="inactive">Inactivo</SelectItem>
                </SelectContent>
              </Select>
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
            <Button onClick={handleSave} disabled={isSaving || !editForm.content.trim()}>
              {isSaving ? "Guardando..." : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Preview Dialog */}
      <Dialog open={isPreviewOpen} onOpenChange={setIsPreviewOpen}>
        <DialogContent className="sm:max-w-[900px] max-h-[90vh]">
          <DialogHeader>
            <DialogTitle>Preview del Prompt - {selectedCategoryName}</DialogTitle>
            <DialogDescription>
              Vista previa del prompt completo generado para cliente {previewClientType}
            </DialogDescription>
          </DialogHeader>

          {preview && (
            <div className="space-y-4">
              <div className="flex gap-4 text-sm">
                <Badge variant="outline">
                  {preview.tiers_count} tarifas
                </Badge>
                <Badge variant="outline">
                  {preview.warnings_count} advertencias
                </Badge>
                <Badge variant="outline">
                  {preview.prompt_length.toLocaleString()} caracteres
                </Badge>
              </div>

              <div className="border rounded-lg overflow-hidden">
                <div className="bg-muted px-4 py-2 border-b">
                  <span className="text-sm font-medium">Prompt Completo</span>
                </div>
                <pre className="p-4 text-sm overflow-auto max-h-[500px] whitespace-pre-wrap font-mono bg-background">
                  {preview.full_prompt}
                </pre>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsPreviewOpen(false)}>
              Cerrar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deleteSection} onOpenChange={() => setDeleteSection(null)}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>Eliminar Seccion</DialogTitle>
            <DialogDescription>
              Estas seguro de eliminar la seccion &quot;{deleteSection && getSectionLabel(deleteSection.section_type)}&quot;?
              Esta accion no se puede deshacer.
            </DialogDescription>
          </DialogHeader>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteSection(null)}
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
    </div>
  );
}
