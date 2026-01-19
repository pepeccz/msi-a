"use client";

import { useEffect, useState, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  ArrowLeft,
  Plus,
  Trash2,
  Edit,
  Upload,
  X,
  GripVertical,
  Image as ImageIcon,
  AlertTriangle,
  GitBranch,
  ExternalLink,
  Network,
} from "lucide-react";
import { toast } from "sonner";
import { ImageGalleryDialog } from "@/components/image-upload";
import { ElementWarningsDialog } from "@/components/elements/element-warnings-dialog";
import api from "@/lib/api";
import type {
  ElementWithImagesAndChildren,
  VehicleCategory,
  ElementImageCreate,
  ElementImageUpdate,
  ElementUpdate,
  ElementImageType,
  ElementWarningAssociation,
  Warning,
} from "@/lib/types";

const IMAGE_TYPE_LABELS: Record<ElementImageType, string> = {
  example: "Ejemplo",
  required_document: "Documento Requerido",
  warning: "Advertencia",
  step: "Paso",
  calculation: "Cálculo",
};

export default function ElementDetailPage() {
  const params = useParams();
  const router = useRouter();
  const elementId = params.id as string;

  const [element, setElement] = useState<ElementWithImagesAndChildren | null>(null);
  const [categories, setCategories] = useState<VehicleCategory[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  // Form state
  const [formData, setFormData] = useState({
    name: "",
    description: "",
    keywords: [] as string[],
    aliases: [] as string[],
    is_active: true,
    // Hierarchy fields
    parent_element_id: "" as string,
    variant_type: "",
    variant_code: "",
    question_hint: "",
  });

  // Available elements for parent selection
  const [availableParents, setAvailableParents] = useState<ElementWithImagesAndChildren[]>([]);

  const [newKeyword, setNewKeyword] = useState("");
  const [newAlias, setNewAlias] = useState("");

  // Image management
  const [editingImage, setEditingImage] = useState<any>(null);
  const [isImageDialogOpen, setIsImageDialogOpen] = useState(false);
  const [isUploadDialogOpen, setIsUploadDialogOpen] = useState(false);
  const [deletingImageId, setDeletingImageId] = useState<string | null>(null);
  const [imageFormData, setImageFormData] = useState({
    title: "",
    description: "",
    image_type: "example" as ElementImageType,
    is_required: false,
  });

  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [uploadPreview, setUploadPreview] = useState<string>("");
  const [showGallery, setShowGallery] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Warnings state
  const [warningsDialogOpen, setWarningsDialogOpen] = useState(false);
  const [elementWarnings, setElementWarnings] = useState<ElementWarningAssociation[]>([]);
  const [allWarnings, setAllWarnings] = useState<Warning[]>([]);

  // Fetch warnings for this element
  const fetchWarnings = async () => {
    try {
      const [warnings, allWarningsData] = await Promise.all([
        api.getElementWarnings(elementId),
        api.getWarnings({ limit: 100 }),
      ]);
      setElementWarnings(warnings);
      setAllWarnings(allWarningsData.items);
    } catch (error) {
      console.error("Error fetching warnings:", error);
    }
  };

  // Fetch element and categories
  useEffect(() => {
    async function fetchData() {
      try {
        setIsLoading(true);
        const [elementData, categoriesData] = await Promise.all([
          api.getElement(elementId),
          api.getVehicleCategories({ limit: 100 }),
        ]);

        setElement(elementData);
        setCategories(categoriesData.items);

        // Initialize form data
        setFormData({
          name: elementData.name,
          description: elementData.description || "",
          keywords: elementData.keywords,
          aliases: elementData.aliases || [],
          is_active: elementData.is_active,
          // Hierarchy fields
          parent_element_id: elementData.parent_element_id || "",
          variant_type: elementData.variant_type || "",
          variant_code: elementData.variant_code || "",
          question_hint: elementData.question_hint || "",
        });

        // Fetch elements of same category for parent selection
        try {
          const elementsData = await api.getElements({
            category_id: elementData.category_id,
            limit: 200,
          });
          // Filter out the current element and its children
          const validParents = elementsData.items.filter(
            (e) => e.id !== elementId &&
                   e.parent_element_id !== elementId // Can't select own children as parent
          );
          setAvailableParents(validParents as ElementWithImagesAndChildren[]);
        } catch (err) {
          console.error("Error fetching available parents:", err);
        }

        // Fetch warnings
        fetchWarnings();
      } catch (error) {
        console.error("Error fetching element:", error);
        toast.error("Error al cargar elemento: " + (error instanceof Error ? error.message : "Desconocido"));
      } finally {
        setIsLoading(false);
      }
    }

    fetchData();
  }, [elementId]);

  // Handle form submission
  const handleSaveElement = async () => {
    if (!element) return;

    try {
      setIsSaving(true);

      // Build hierarchy fields
      const hierarchyFields = formData.parent_element_id
        ? {
            parent_element_id: formData.parent_element_id,
            variant_type: formData.variant_type || null,
            variant_code: formData.variant_code || null,
          }
        : {
            parent_element_id: null, // Explicitly null to remove parent
            variant_type: null,
            variant_code: null,
          };

      const data: ElementUpdate = {
        code: element.code,
        name: formData.name,
        description: formData.description || undefined,
        keywords: formData.keywords,
        aliases: formData.aliases,
        is_active: formData.is_active,
        question_hint: formData.question_hint || null,
        ...hierarchyFields,
      };

      await api.updateElement(elementId, data);

      // Refresh element data to show updated hierarchy
      const updatedElement = await api.getElement(elementId);
      setElement(updatedElement);

      toast.success("Elemento actualizado correctamente");
    } catch (error) {
      console.error("Error saving element:", error);
      toast.error("Error al guardar elemento: " + (error instanceof Error ? error.message : "Desconocido"));
    } finally {
      setIsSaving(false);
    }
  };

  // Keyword handlers
  const handleAddKeyword = () => {
    if (newKeyword.trim() && !formData.keywords.includes(newKeyword.toLowerCase())) {
      setFormData((prev) => ({
        ...prev,
        keywords: [...prev.keywords, newKeyword.toLowerCase()],
      }));
      setNewKeyword("");
    }
  };

  const handleRemoveKeyword = (keyword: string) => {
    setFormData((prev) => ({
      ...prev,
      keywords: prev.keywords.filter((k) => k !== keyword),
    }));
  };

  // Alias handlers
  const handleAddAlias = () => {
    if (newAlias.trim() && !formData.aliases.includes(newAlias.toLowerCase())) {
      setFormData((prev) => ({
        ...prev,
        aliases: [...prev.aliases, newAlias.toLowerCase()],
      }));
      setNewAlias("");
    }
  };

  const handleRemoveAlias = (alias: string) => {
    setFormData((prev) => ({
      ...prev,
      aliases: prev.aliases.filter((a) => a !== alias),
    }));
  };

  // Image handlers
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadedFile(file);

    // Auto-rellenar nombre desde el archivo (sin extensión)
    const nameWithoutExt = file.name.replace(/\.[^/.]+$/, "");
    setImageFormData(prev => ({ ...prev, title: nameWithoutExt }));

    const reader = new FileReader();
    reader.onload = (event) => {
      setUploadPreview(event.target?.result as string);
    };
    reader.readAsDataURL(file);
  };

  // Manejar selección desde galería
  const handleSelectFromGallery = (url: string) => {
    setShowGallery(false);
    setUploadPreview(url);
    setUploadedFile(null); // Limpiar archivo si había uno
    // Auto-rellenar título desde el nombre del archivo en la URL
    const filename = url.split("/").pop()?.split("?")[0] || "";
    const nameWithoutExt = filename.replace(/\.[^/.]+$/, "").replace(/_/g, " ");
    setImageFormData(prev => ({ ...prev, title: nameWithoutExt }));
  };

  // Guardar imagen (ya sea de archivo o de galería)
  const handleSaveImage = async () => {
    if (!element || !imageFormData.title.trim()) return;
    if (!uploadedFile && !uploadPreview) return;

    try {
      setIsSaving(true);

      let imageUrl: string;

      if (uploadedFile) {
        // Subir archivo nuevo
        const uploaded = await api.uploadImage(uploadedFile, "element");
        imageUrl = uploaded.url;
      } else {
        // Usar URL de galería
        imageUrl = uploadPreview;
      }

      const imageData: ElementImageCreate = {
        image_url: imageUrl,
        title: imageFormData.title.trim(),
        description: imageFormData.description || undefined,
        image_type: imageFormData.image_type,
        is_required: imageFormData.is_required,
      };

      await api.createElementImage(elementId, imageData);

      // Refrescar y limpiar
      const updatedElement = await api.getElement(elementId);
      setElement(updatedElement);

      // Reset form
      setUploadedFile(null);
      setUploadPreview("");
      setImageFormData({
        title: "",
        description: "",
        image_type: "example",
        is_required: false,
      });
      setIsUploadDialogOpen(false);
      toast.success("Imagen añadida correctamente");
    } catch (error) {
      console.error("Error saving image:", error);
      toast.error("Error al guardar imagen: " + (error instanceof Error ? error.message : "Desconocido"));
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteImage = async () => {
    if (!deletingImageId) return;

    try {
      setIsSaving(true);
      await api.deleteElementImage(deletingImageId);

      // Refresh element data
      const updatedElement = await api.getElement(elementId);
      setElement(updatedElement);
      setDeletingImageId(null);

      toast.success("Imagen eliminada correctamente");
    } catch (error) {
      console.error("Error deleting image:", error);
      toast.error("Error al eliminar imagen: " + (error instanceof Error ? error.message : "Desconocido"));
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading || !element) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-muted-foreground">Cargando elemento...</div>
      </div>
    );
  }

  const category = categories.find((c) => c.id === element.category_id);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="outline" size="icon" onClick={() => router.back()}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{element.name}</h1>
          <p className="text-muted-foreground">
            {category?.name} • {element.code}
          </p>
        </div>
      </div>

      {/* Main Content */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left Column - Form */}
        <div className="lg:col-span-2 space-y-6">
          {/* Información Básica */}
          <Card>
            <CardHeader>
              <CardTitle>Información Básica</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>Código</Label>
                <Input value={element.code} disabled className="font-mono" />
                <p className="text-xs text-muted-foreground">Identificador único (no editable)</p>
              </div>

              <div className="space-y-2">
                <Label>Categoría</Label>
                <Input value={category?.name || "-"} disabled />
              </div>

              <div className="space-y-2">
                <Label htmlFor="name">Nombre *</Label>
                <Input
                  id="name"
                  value={formData.name}
                  onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))}
                  disabled={isSaving}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">Descripción</Label>
                <Textarea
                  id="description"
                  value={formData.description}
                  onChange={(e) => setFormData((prev) => ({ ...prev, description: e.target.value }))}
                  disabled={isSaving}
                  rows={3}
                />
                <p className="text-xs text-muted-foreground">Opcional</p>
              </div>

              <div className="flex items-center justify-between p-3 border rounded-lg bg-muted/50">
                <Label htmlFor="is_active" className="cursor-pointer">
                  <span className="font-medium">Elemento Activo</span>
                  <p className="text-xs text-muted-foreground">Los inactivos no aparecen en búsquedas</p>
                </Label>
                <Switch
                  id="is_active"
                  checked={formData.is_active}
                  onCheckedChange={(checked) =>
                    setFormData((prev) => ({ ...prev, is_active: checked }))
                  }
                  disabled={isSaving}
                />
              </div>

              {/* Hierarchy Section - Editable */}
              <div className="p-4 border rounded-lg bg-muted/30 space-y-4">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <GitBranch className="h-4 w-4" />
                  Jerarquía (Variantes)
                </div>

                {/* Parent Element Selector */}
                <div className="space-y-2">
                  <Label htmlFor="parent_element">Elemento Padre</Label>
                  <Select
                    value={formData.parent_element_id || "none"}
                    onValueChange={(value) =>
                      setFormData((prev) => ({
                        ...prev,
                        parent_element_id: value === "none" ? "" : value,
                        // Clear variant fields if removing parent
                        ...(value === "none" ? { variant_type: "", variant_code: "" } : {}),
                      }))
                    }
                    disabled={isSaving}
                  >
                    <SelectTrigger id="parent_element">
                      <SelectValue placeholder="Sin padre (elemento base)" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">Ninguno - Elemento Base</SelectItem>
                      {availableParents
                        .filter((el) => el.id !== elementId)
                        .map((el) => (
                          <SelectItem key={el.id} value={el.id}>
                            {el.code} - {el.name}
                          </SelectItem>
                        ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    Si seleccionas un padre, este elemento será una variante
                  </p>
                </div>

                {/* Variant Fields - Only show if parent selected */}
                {formData.parent_element_id && (
                  <>
                    <div className="space-y-2">
                      <Label htmlFor="variant_type">Tipo de Variante</Label>
                      <Input
                        id="variant_type"
                        placeholder="Ej: mmr_option, installation_type, suspension_type"
                        value={formData.variant_type}
                        onChange={(e) =>
                          setFormData((prev) => ({
                            ...prev,
                            variant_type: e.target.value.toLowerCase(),
                          }))
                        }
                        disabled={isSaving}
                      />
                      <p className="text-xs text-muted-foreground">
                        Categoría de la variante (ej: mmr_option, installation_type)
                      </p>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="variant_code">Código de Variante</Label>
                      <Input
                        id="variant_code"
                        placeholder="Ej: SIN_MMR, CON_MMR, FULL_AIR"
                        value={formData.variant_code}
                        onChange={(e) =>
                          setFormData((prev) => ({
                            ...prev,
                            variant_code: e.target.value.toUpperCase(),
                          }))
                        }
                        disabled={isSaving}
                        className="font-mono"
                      />
                      <p className="text-xs text-muted-foreground">
                        Identificador corto de esta variante (mayúsculas)
                      </p>
                    </div>
                  </>
                )}

                {/* Question hint - Only for base elements (no parent) */}
                {!formData.parent_element_id && (
                  <div className="space-y-2">
                    <Label htmlFor="question_hint">Pregunta para variantes</Label>
                    <Textarea
                      id="question_hint"
                      value={formData.question_hint}
                      onChange={(e) =>
                        setFormData((prev) => ({ ...prev, question_hint: e.target.value }))
                      }
                      placeholder="¿El toldo afecta a la luz de gálibo del vehículo?"
                      className="min-h-[80px]"
                      disabled={isSaving}
                    />
                    <p className="text-xs text-muted-foreground">
                      Pregunta que el agente usará para determinar qué variante necesita el usuario.
                    </p>
                  </div>
                )}

                {/* Show current parent if exists */}
                {element.parent && (
                  <div className="mt-2 p-2 bg-blue-50 dark:bg-blue-950/30 rounded border border-blue-200 dark:border-blue-800">
                    <p className="text-xs text-blue-700 dark:text-blue-300 mb-1">Padre actual:</p>
                    <Link href={`/elementos/${element.parent.id}`} className="text-sm font-medium hover:underline">
                      {element.parent.code} - {element.parent.name}
                    </Link>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Parent Element Card */}
          {element.parent && (
            <Card className="border-blue-200 dark:border-blue-800">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Network className="h-4 w-4 text-blue-600" />
                  Elemento Padre
                </CardTitle>
                <CardDescription>
                  Este elemento es una variante de otro elemento
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-3 p-3 border rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors">
                  <div className="flex-1 min-w-0">
                    <code className="text-sm font-mono bg-background px-2 py-0.5 rounded">
                      {element.parent.code}
                    </code>
                    <p className="text-sm font-medium mt-1">{element.parent.name}</p>
                  </div>
                  <Link href={`/elementos/${element.parent.id}`}>
                    <Button variant="outline" size="sm" className="gap-1">
                      <ExternalLink className="h-3 w-3" />
                      Ver
                    </Button>
                  </Link>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Children/Variants Card */}
          {element.children && element.children.length > 0 && (
            <Card className="border-green-200 dark:border-green-800">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <GitBranch className="h-4 w-4 text-green-600" />
                  Variantes ({element.children.length})
                </CardTitle>
                <CardDescription>
                  Este elemento tiene las siguientes variantes
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {element.children.map((child) => (
                    <div
                      key={child.id}
                      className="flex items-center gap-3 p-3 border rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          {child.variant_code && (
                            <Badge variant="secondary" className="text-xs">
                              {child.variant_code}
                            </Badge>
                          )}
                          <code className="text-sm font-mono bg-background px-2 py-0.5 rounded">
                            {child.code}
                          </code>
                        </div>
                        <p className="text-sm mt-1">{child.name}</p>
                      </div>
                      <Link href={`/elementos/${child.id}`}>
                        <Button variant="outline" size="sm" className="gap-1">
                          <ExternalLink className="h-3 w-3" />
                          Ver
                        </Button>
                      </Link>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Keywords */}
          <Card>
            <CardHeader>
              <CardTitle>Keywords para Matching</CardTitle>
              <CardDescription>
                Términos usados para identificar este elemento en descripciones de clientes
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-2">
                <Input
                  placeholder="Escribe un keyword y presiona Enter..."
                  value={newKeyword}
                  onChange={(e) => setNewKeyword(e.target.value)}
                  onKeyPress={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleAddKeyword();
                    }
                  }}
                  disabled={isSaving}
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleAddKeyword}
                  disabled={isSaving || !newKeyword.trim()}
                >
                  Añadir
                </Button>
              </div>

              {formData.keywords.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {formData.keywords.map((keyword) => (
                    <Badge key={keyword} variant="secondary" className="gap-1">
                      {keyword}
                      <button
                        type="button"
                        onClick={() => handleRemoveKeyword(keyword)}
                        disabled={isSaving}
                        className="ml-1 hover:text-destructive"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Aliases */}
          <Card>
            <CardHeader>
              <CardTitle>Aliases (Nombres Alternativos)</CardTitle>
              <CardDescription>
                Otros nombres con los que se conoce este elemento
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-2">
                <Input
                  placeholder="ej: escalerilla, peldaños..."
                  value={newAlias}
                  onChange={(e) => setNewAlias(e.target.value)}
                  onKeyPress={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleAddAlias();
                    }
                  }}
                  disabled={isSaving}
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleAddAlias}
                  disabled={isSaving || !newAlias.trim()}
                >
                  Añadir
                </Button>
              </div>

              {formData.aliases.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {formData.aliases.map((alias) => (
                    <Badge key={alias} variant="outline" className="gap-1">
                      {alias}
                      <button
                        type="button"
                        onClick={() => handleRemoveAlias(alias)}
                        disabled={isSaving}
                        className="ml-1 hover:text-destructive"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Advertencias */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <AlertTriangle className="h-5 w-5" />
                    Advertencias
                  </CardTitle>
                  <CardDescription>
                    Advertencias que se mostraran al seleccionar este elemento
                  </CardDescription>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setWarningsDialogOpen(true)}
                >
                  Gestionar
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {elementWarnings.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">
                  No hay advertencias asociadas
                </p>
              ) : (
                <div className="space-y-2">
                  {elementWarnings.map((assoc) => {
                    const warning = allWarnings.find((w) => w.id === assoc.warning_id);
                    if (!warning) return null;

                    return (
                      <div
                        key={assoc.id}
                        className="flex items-start gap-2 p-2 border rounded-lg"
                      >
                        <Badge
                          variant={
                            warning.severity === "error"
                              ? "destructive"
                              : warning.severity === "warning"
                              ? "default"
                              : "secondary"
                          }
                          className="mt-0.5"
                        >
                          {warning.severity}
                        </Badge>
                        <div className="flex-1 min-w-0">
                          <code className="text-xs bg-muted px-1.5 py-0.5 rounded">
                            {warning.code}
                          </code>
                          <p className="text-sm text-muted-foreground truncate mt-1">
                            {warning.message}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Action Buttons */}
          <div className="flex gap-3 justify-end pt-4 border-t">
            <Button variant="outline" onClick={() => router.back()}>Cancelar</Button>
            <Button onClick={handleSaveElement} disabled={isSaving}>
              {isSaving ? "Guardando..." : "Guardar Cambios"}
            </Button>
          </div>
        </div>

        {/* Right Column - Images */}
        <div className="lg:col-span-1">
          <Card className="sticky top-6">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Imágenes ({element.images.length})</CardTitle>
                <Dialog open={isUploadDialogOpen} onOpenChange={setIsUploadDialogOpen}>
                  <DialogTrigger asChild>
                    <Button size="sm" className="gap-2">
                      <Plus className="h-4 w-4" />
                      Subir
                    </Button>
                  </DialogTrigger>
                  <DialogContent className="max-w-md">
                    <DialogHeader>
                      <DialogTitle>Añadir Imagen</DialogTitle>
                      <DialogDescription>
                        Sube una nueva imagen o selecciona una de la galería
                      </DialogDescription>
                    </DialogHeader>

                    <div className="space-y-4">
                      {/* File Upload / Gallery Selection */}
                      <div className="space-y-2">
                        <Label>Imagen *</Label>
                        <input
                          ref={fileInputRef}
                          id="file-input"
                          type="file"
                          accept="image/*"
                          onChange={handleFileSelect}
                          className="hidden"
                          disabled={isSaving}
                        />
                        <div className="flex gap-2">
                          <Button
                            type="button"
                            variant="outline"
                            className="flex-1"
                            onClick={() => fileInputRef.current?.click()}
                            disabled={isSaving}
                          >
                            <Upload className="h-4 w-4 mr-2" />
                            Subir archivo
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            className="flex-1"
                            onClick={() => setShowGallery(true)}
                            disabled={isSaving}
                          >
                            <ImageIcon className="h-4 w-4 mr-2" />
                            Galería
                          </Button>
                        </div>
                      </div>

                      {/* Preview */}
                      {uploadPreview && (
                        <div className="relative w-full h-40 rounded-lg border bg-muted overflow-hidden">
                          <Image
                            src={uploadPreview}
                            alt="Preview"
                            fill
                            className="object-cover"
                          />
                        </div>
                      )}

                      {/* Form Fields */}
                      <div className="space-y-2">
                        <Label htmlFor="title">Nombre *</Label>
                        <Input
                          id="title"
                          value={imageFormData.title}
                          onChange={(e) =>
                            setImageFormData((prev) => ({
                              ...prev,
                              title: e.target.value,
                            }))
                          }
                          placeholder="ej: Vista trasera cerrada"
                          disabled={isSaving}
                        />
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="img-desc">Descripción</Label>
                        <Textarea
                          id="img-desc"
                          value={imageFormData.description}
                          onChange={(e) =>
                            setImageFormData((prev) => ({
                              ...prev,
                              description: e.target.value,
                            }))
                          }
                          placeholder="Descripción de la imagen (opcional)"
                          rows={2}
                          disabled={isSaving}
                        />
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="image-type">Tipo de Imagen</Label>
                        <Select
                          value={imageFormData.image_type}
                          onValueChange={(value) =>
                            setImageFormData((prev) => ({
                              ...prev,
                              image_type: value as ElementImageType,
                            }))
                          }
                          disabled={isSaving}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="example">Ejemplo</SelectItem>
                            <SelectItem value="required_document">
                              Documento Requerido
                            </SelectItem>
                            <SelectItem value="warning">Advertencia</SelectItem>
                            <SelectItem value="step">Paso</SelectItem>
                            <SelectItem value="calculation">Calculo</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="flex items-center justify-between">
                        <Label htmlFor="is-required" className="cursor-pointer">
                          Es requerida
                        </Label>
                        <Switch
                          id="is-required"
                          checked={imageFormData.is_required}
                          onCheckedChange={(checked) =>
                            setImageFormData((prev) => ({
                              ...prev,
                              is_required: checked,
                            }))
                          }
                          disabled={isSaving}
                        />
                      </div>

                      <div className="flex gap-2 justify-end pt-4">
                        <Button
                          type="button"
                          variant="outline"
                          onClick={() => setIsUploadDialogOpen(false)}
                          disabled={isSaving}
                        >
                          Cancelar
                        </Button>
                        <Button
                          onClick={handleSaveImage}
                          disabled={isSaving || (!uploadedFile && !uploadPreview) || !imageFormData.title.trim()}
                        >
                          {isSaving ? "Guardando..." : "Guardar Imagen"}
                        </Button>
                      </div>
                    </div>
                  </DialogContent>
                </Dialog>
              </div>
            </CardHeader>

            <CardContent className="space-y-4">
              {element.images.length === 0 ? (
                <div className="text-center py-8">
                  <ImageIcon className="h-12 w-12 text-muted-foreground mx-auto mb-2 opacity-50" />
                  <p className="text-sm text-muted-foreground">Sin imágenes</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {element.images.map((image) => (
                    <div
                      key={image.id}
                      className="flex gap-2 p-2 border rounded-lg hover:bg-muted/50 transition-colors"
                    >
                      <div className="flex-shrink-0">
                        <div className="relative w-12 h-12 rounded border bg-muted overflow-hidden">
                          <Image
                            src={image.image_url}
                            alt={image.title || image.description || "Imagen del elemento"}
                            fill
                            className="object-cover"
                          />
                        </div>
                      </div>

                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">
                          {image.title || image.description}
                        </p>
                        <div className="flex gap-1 flex-wrap">
                          <Badge variant="secondary" className="text-xs">
                            {IMAGE_TYPE_LABELS[image.image_type]}
                          </Badge>
                          {image.is_required && (
                            <Badge variant="destructive" className="text-xs">
                              Requerida
                            </Badge>
                          )}
                        </div>
                      </div>

                      <button
                        onClick={() => setDeletingImageId(image.id)}
                        className="flex-shrink-0 p-1 text-muted-foreground hover:text-destructive transition-colors"
                        disabled={isSaving}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Delete Image Confirmation */}
      <AlertDialog open={!!deletingImageId} onOpenChange={(open) => !open && setDeletingImageId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Eliminar imagen?</AlertDialogTitle>
            <AlertDialogDescription>
              Esta acción no se puede deshacer.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="flex gap-3 justify-end">
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteImage}
              disabled={isSaving}
              className="bg-destructive hover:bg-destructive/90"
            >
              {isSaving ? "Eliminando..." : "Eliminar"}
            </AlertDialogAction>
          </div>
        </AlertDialogContent>
      </AlertDialog>

      {/* Warnings Dialog */}
      <ElementWarningsDialog
        open={warningsDialogOpen}
        onOpenChange={setWarningsDialogOpen}
        element={element}
        onSuccess={fetchWarnings}
      />

      {/* Image Gallery Dialog */}
      <ImageGalleryDialog
        open={showGallery}
        onOpenChange={setShowGallery}
        onSelect={handleSelectFromGallery}
        category="element"
      />
    </div>
  );
}
