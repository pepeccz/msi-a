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
} from "lucide-react";
import api from "@/lib/api";
import type {
  ElementWithImages,
  VehicleCategory,
  ElementImageCreate,
  ElementImageUpdate,
  ElementUpdate,
  ElementImageType,
} from "@/lib/types";

const IMAGE_TYPE_LABELS: Record<ElementImageType, string> = {
  example: "Ejemplo",
  required_document: "Documento Requerido",
  warning: "Advertencia",
};

export default function ElementDetailPage() {
  const params = useParams();
  const router = useRouter();
  const elementId = params.id as string;

  const [element, setElement] = useState<ElementWithImages | null>(null);
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
  });

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
  const fileInputRef = useRef<HTMLInputElement>(null);

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
        });
      } catch (error) {
        console.error("Error fetching element:", error);
        alert("Error al cargar elemento: " + (error instanceof Error ? error.message : "Desconocido"));
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
      const data: ElementUpdate = {
        code: element.code,
        name: formData.name,
        description: formData.description || undefined,
        keywords: formData.keywords,
        aliases: formData.aliases,
        is_active: formData.is_active,
      };

      await api.updateElement(elementId, data);
      alert("Elemento actualizado correctamente");
    } catch (error) {
      console.error("Error saving element:", error);
      alert("Error al guardar elemento: " + (error instanceof Error ? error.message : "Desconocido"));
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

    const reader = new FileReader();
    reader.onload = (event) => {
      setUploadPreview(event.target?.result as string);
    };
    reader.readAsDataURL(file);
  };

  const handleUploadImage = async () => {
    if (!uploadedFile || !element) return;

    try {
      setIsSaving(true);

      // In a real app, you'd upload to S3 and get the URL
      // For now, we'll use a placeholder
      const imageUrl = uploadPreview; // In production: upload to S3

      const imageData: ElementImageCreate = {
        image_url: imageUrl,
        title: imageFormData.title,
        description: imageFormData.description,
        image_type: imageFormData.image_type,
        is_required: imageFormData.is_required,
      };

      await api.createElementImage(elementId, imageData);

      // Refresh element data
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

      alert("Imagen subida correctamente");
    } catch (error) {
      console.error("Error uploading image:", error);
      alert("Error al subir imagen: " + (error instanceof Error ? error.message : "Desconocido"));
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

      alert("Imagen eliminada correctamente");
    } catch (error) {
      console.error("Error deleting image:", error);
      alert("Error al eliminar imagen: " + (error instanceof Error ? error.message : "Desconocido"));
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
        <Link href="/elementos">
          <Button variant="outline" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
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
            </CardContent>
          </Card>

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

          {/* Action Buttons */}
          <div className="flex gap-3 justify-end pt-4 border-t">
            <Link href="/elementos">
              <Button variant="outline">Cancelar</Button>
            </Link>
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
                      <DialogTitle>Subir Nueva Imagen</DialogTitle>
                      <DialogDescription>
                        Añade una nueva imagen para este elemento
                      </DialogDescription>
                    </DialogHeader>

                    <div className="space-y-4">
                      {/* File Upload */}
                      <div className="space-y-2">
                        <Label htmlFor="file-input">Imagen *</Label>
                        <input
                          ref={fileInputRef}
                          id="file-input"
                          type="file"
                          accept="image/*"
                          onChange={handleFileSelect}
                          className="hidden"
                          disabled={isSaving}
                        />
                        <Button
                          type="button"
                          variant="outline"
                          className="w-full"
                          onClick={() => fileInputRef.current?.click()}
                          disabled={isSaving}
                        >
                          <Upload className="h-4 w-4 mr-2" />
                          Seleccionar Imagen
                        </Button>
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
                        <Label htmlFor="title">Título</Label>
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
                        <Label htmlFor="img-desc">Descripción *</Label>
                        <Textarea
                          id="img-desc"
                          value={imageFormData.description}
                          onChange={(e) =>
                            setImageFormData((prev) => ({
                              ...prev,
                              description: e.target.value,
                            }))
                          }
                          placeholder="Descripción de la imagen"
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
                          onClick={handleUploadImage}
                          disabled={isSaving || !uploadedFile || !imageFormData.description}
                        >
                          {isSaving ? "Subiendo..." : "Subir Imagen"}
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
    </div>
  );
}
