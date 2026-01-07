"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Car,
  ArrowLeft,
  FileText,
  Plus,
  Image as ImageIcon,
  Pencil,
  Trash2,
  Building2,
  User,
  Users,
  X,
  CheckCircle2,
} from "lucide-react";
import api from "@/lib/api";
import { ImageUpload } from "@/components/image-upload";
import type {
  VehicleCategoryWithDetails,
  TariffTier,
  TariffTierCreate,
  TariffTierUpdate,
  TierClientType,
  ClassificationRules,
  BaseDocumentation,
  ElementDocumentation,
  ElementDocumentationCreate,
  ElementDocumentationUpdate,
} from "@/lib/types";

const CLIENT_TYPE_LABELS: Record<TierClientType, string> = {
  particular: "Particular",
  professional: "Profesional",
  all: "Todos",
};

export default function CategoryDetailPage() {
  const params = useParams();
  const router = useRouter();
  const categoryId = params.categoryId as string;

  const [category, setCategory] = useState<VehicleCategoryWithDetails | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [clientTypeFilter, setClientTypeFilter] = useState<string>("all");

  // Edit/Create tier dialog
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [editingTier, setEditingTier] = useState<TariffTier | null>(null);
  const [tierForm, setTierForm] = useState<{
    code: string;
    name: string;
    description: string;
    price: string;
    conditions: string;
    client_type: TierClientType;
    classification_rules: ClassificationRules;
    min_elements: string;
    max_elements: string;
    is_active: boolean;
  }>({
    code: "",
    name: "",
    description: "",
    price: "",
    conditions: "",
    client_type: "all",
    classification_rules: {
      applies_if_any: [],
      priority: 0,
      requires_project: false,
    },
    min_elements: "",
    max_elements: "",
    is_active: true,
  });
  const [isSaving, setIsSaving] = useState(false);
  const [keywordInput, setKeywordInput] = useState("");

  // Delete dialog
  const [deleteTier, setDeleteTier] = useState<TariffTier | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // Element Documentation state
  const [isElementDocDialogOpen, setIsElementDocDialogOpen] = useState(false);
  const [editingElementDoc, setEditingElementDoc] = useState<ElementDocumentation | null>(null);
  const [elementDocForm, setElementDocForm] = useState<{
    element_keywords: string[];
    description: string;
    image_url: string | null;
    is_active: boolean;
  }>({
    element_keywords: [],
    description: "",
    image_url: null,
    is_active: true,
  });
  const [isSavingElementDoc, setIsSavingElementDoc] = useState(false);
  const [elementDocKeywordInput, setElementDocKeywordInput] = useState("");
  const [deleteElementDoc, setDeleteElementDoc] = useState<ElementDocumentation | null>(null);
  const [isDeletingElementDoc, setIsDeletingElementDoc] = useState(false);

  // Base Documentation state
  const [isBaseDocDialogOpen, setIsBaseDocDialogOpen] = useState(false);
  const [editingBaseDoc, setEditingBaseDoc] = useState<BaseDocumentation | null>(null);
  const [baseDocForm, setBaseDocForm] = useState<{
    description: string;
    image_url: string | null;
    sort_order: number;
  }>({
    description: "",
    image_url: null,
    sort_order: 0,
  });
  const [isSavingBaseDoc, setIsSavingBaseDoc] = useState(false);
  const [deleteBaseDoc, setDeleteBaseDoc] = useState<BaseDocumentation | null>(null);
  const [isDeletingBaseDoc, setIsDeletingBaseDoc] = useState(false);

  useEffect(() => {
    fetchCategory();
  }, [categoryId]);

  async function fetchCategory() {
    try {
      const data = await api.getVehicleCategory(categoryId);
      setCategory(data);
    } catch (error) {
      console.error("Error fetching category:", error);
    } finally {
      setIsLoading(false);
    }
  }

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat("es-ES", {
      style: "currency",
      currency: "EUR",
    }).format(price);
  };

  const openCreateDialog = () => {
    setEditingTier(null);
    setTierForm({
      code: "",
      name: "",
      description: "",
      price: "",
      conditions: "",
      client_type: "all",
      classification_rules: {
        applies_if_any: [],
        priority: 0,
        requires_project: false,
      },
      min_elements: "",
      max_elements: "",
      is_active: true,
    });
    setKeywordInput("");
    setIsEditDialogOpen(true);
  };

  const openEditDialog = (tier: TariffTier) => {
    setEditingTier(tier);
    setTierForm({
      code: tier.code,
      name: tier.name,
      description: tier.description || "",
      price: tier.price.toString(),
      conditions: tier.conditions || "",
      client_type: tier.client_type,
      classification_rules: tier.classification_rules || {
        applies_if_any: [],
        priority: 0,
        requires_project: false,
      },
      min_elements: tier.min_elements?.toString() || "",
      max_elements: tier.max_elements?.toString() || "",
      is_active: tier.is_active,
    });
    setKeywordInput("");
    setIsEditDialogOpen(true);
  };

  const handleSaveTier = async () => {
    setIsSaving(true);
    try {
      const price = parseFloat(tierForm.price);
      if (isNaN(price)) return;

      const data = {
        code: tierForm.code,
        name: tierForm.name,
        description: tierForm.description || null,
        price,
        conditions: tierForm.conditions || null,
        client_type: tierForm.client_type,
        classification_rules: tierForm.classification_rules,
        min_elements: tierForm.min_elements ? parseInt(tierForm.min_elements) : null,
        max_elements: tierForm.max_elements ? parseInt(tierForm.max_elements) : null,
        is_active: tierForm.is_active,
      };

      if (editingTier) {
        await api.updateTariffTier(editingTier.id, data as TariffTierUpdate);
      } else {
        await api.createTariffTier({ ...data, category_id: categoryId } as TariffTierCreate);
      }

      setIsEditDialogOpen(false);
      fetchCategory();
    } catch (error) {
      console.error("Error saving tier:", error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteTier = async () => {
    if (!deleteTier) return;
    setIsDeleting(true);
    try {
      await api.deleteTariffTier(deleteTier.id);
      setDeleteTier(null);
      fetchCategory();
    } catch (error) {
      console.error("Error deleting tier:", error);
    } finally {
      setIsDeleting(false);
    }
  };

  // Element Documentation handlers
  const openCreateElementDocDialog = () => {
    setEditingElementDoc(null);
    setElementDocForm({
      element_keywords: [],
      description: "",
      image_url: null,
      is_active: true,
    });
    setElementDocKeywordInput("");
    setIsElementDocDialogOpen(true);
  };

  const openEditElementDocDialog = (doc: ElementDocumentation) => {
    setEditingElementDoc(doc);
    setElementDocForm({
      element_keywords: doc.element_keywords,
      description: doc.description,
      image_url: doc.image_url,
      is_active: doc.is_active,
    });
    setElementDocKeywordInput("");
    setIsElementDocDialogOpen(true);
  };

  const handleSaveElementDoc = async () => {
    setIsSavingElementDoc(true);
    try {
      const data = {
        element_keywords: elementDocForm.element_keywords,
        description: elementDocForm.description,
        image_url: elementDocForm.image_url,
        is_active: elementDocForm.is_active,
      };

      if (editingElementDoc) {
        await api.updateElementDocumentation(editingElementDoc.id, data as ElementDocumentationUpdate);
      } else {
        await api.createElementDocumentation({ ...data, category_id: categoryId } as ElementDocumentationCreate);
      }

      setIsElementDocDialogOpen(false);
      fetchCategory();
    } catch (error) {
      console.error("Error saving element documentation:", error);
    } finally {
      setIsSavingElementDoc(false);
    }
  };

  const handleDeleteElementDoc = async () => {
    if (!deleteElementDoc) return;
    setIsDeletingElementDoc(true);
    try {
      await api.deleteElementDocumentation(deleteElementDoc.id);
      setDeleteElementDoc(null);
      fetchCategory();
    } catch (error) {
      console.error("Error deleting element documentation:", error);
    } finally {
      setIsDeletingElementDoc(false);
    }
  };

  const addElementDocKeyword = () => {
    const keyword = elementDocKeywordInput.trim().toLowerCase();
    if (keyword && !elementDocForm.element_keywords.includes(keyword)) {
      setElementDocForm((prev) => ({
        ...prev,
        element_keywords: [...prev.element_keywords, keyword],
      }));
      setElementDocKeywordInput("");
    }
  };

  const removeElementDocKeyword = (keyword: string) => {
    setElementDocForm((prev) => ({
      ...prev,
      element_keywords: prev.element_keywords.filter((k) => k !== keyword),
    }));
  };

  // Base Documentation handlers
  const openCreateBaseDocDialog = () => {
    setEditingBaseDoc(null);
    setBaseDocForm({
      description: "",
      image_url: null,
      sort_order: category?.base_documentation?.length || 0,
    });
    setIsBaseDocDialogOpen(true);
  };

  const openEditBaseDocDialog = (doc: BaseDocumentation) => {
    setEditingBaseDoc(doc);
    setBaseDocForm({
      description: doc.description,
      image_url: doc.image_url,
      sort_order: doc.sort_order,
    });
    setIsBaseDocDialogOpen(true);
  };

  const handleSaveBaseDoc = async () => {
    setIsSavingBaseDoc(true);
    try {
      const data = {
        description: baseDocForm.description,
        image_url: baseDocForm.image_url,
        sort_order: baseDocForm.sort_order,
      };

      if (editingBaseDoc) {
        await api.updateBaseDocumentation(editingBaseDoc.id, data);
      } else {
        await api.createBaseDocumentation({
          ...data,
          category_id: categoryId
        });
      }

      setIsBaseDocDialogOpen(false);
      fetchCategory();
    } catch (error) {
      console.error("Error saving base documentation:", error);
    } finally {
      setIsSavingBaseDoc(false);
    }
  };

  const handleDeleteBaseDoc = async () => {
    if (!deleteBaseDoc) return;
    setIsDeletingBaseDoc(true);
    try {
      await api.deleteBaseDocumentation(deleteBaseDoc.id);
      setDeleteBaseDoc(null);
      fetchCategory();
    } catch (error) {
      console.error("Error deleting base documentation:", error);
    } finally {
      setIsDeletingBaseDoc(false);
    }
  };

  const addKeyword = () => {
    const keyword = keywordInput.trim().toLowerCase();
    if (keyword && !tierForm.classification_rules.applies_if_any.includes(keyword)) {
      setTierForm((prev) => ({
        ...prev,
        classification_rules: {
          ...prev.classification_rules,
          applies_if_any: [...prev.classification_rules.applies_if_any, keyword],
        },
      }));
      setKeywordInput("");
    }
  };

  const removeKeyword = (keyword: string) => {
    setTierForm((prev) => ({
      ...prev,
      classification_rules: {
        ...prev.classification_rules,
        applies_if_any: prev.classification_rules.applies_if_any.filter((k) => k !== keyword),
      },
    }));
  };

  const getClientTypeBadge = (clientType: TierClientType) => {
    switch (clientType) {
      case "professional":
        return (
          <Badge variant="default" className="bg-blue-600 hover:bg-blue-700">
            <Building2 className="h-3 w-3 mr-1" />
            Profesional
          </Badge>
        );
      case "particular":
        return (
          <Badge variant="secondary">
            <User className="h-3 w-3 mr-1" />
            Particular
          </Badge>
        );
      default:
        return (
          <Badge variant="outline">
            <Users className="h-3 w-3 mr-1" />
            Todos
          </Badge>
        );
    }
  };

  // Filter tiers by client type
  const filteredTiers = category?.tariff_tiers?.filter((tier) => {
    if (clientTypeFilter === "all") return true;
    return tier.client_type === clientTypeFilter || tier.client_type === "all";
  }) || [];

  if (isLoading) {
    return (
      <div className="p-6">
        <div className="flex items-center justify-center py-8">
          <div className="animate-pulse text-muted-foreground">
            Cargando categoria...
          </div>
        </div>
      </div>
    );
  }

  if (!category) {
    return (
      <div className="p-6">
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <Car className="h-12 w-12 text-muted-foreground/50 mb-4" />
          <p className="text-muted-foreground">Categoria no encontrada</p>
          <Button variant="outline" className="mt-4" onClick={() => router.push("/tarifas")}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            Volver a Tarifas
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/tarifas">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-5 w-5" />
            </Button>
          </Link>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-bold tracking-tight">{category.name}</h1>
              <Badge variant={category.is_active ? "default" : "secondary"}>
                {category.is_active ? "Activo" : "Inactivo"}
              </Badge>
            </div>
            <p className="text-muted-foreground">
              {category.description || `Gestion de tarifas para ${category.name.toLowerCase()}`}
            </p>
          </div>
        </div>
      </div>

      {/* Stats Overview */}
      <div className="grid grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Tarifas
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{category.tariff_tiers?.length || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Secciones Prompt
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{category.prompt_sections?.length || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Documentos Base
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{category.base_documentation?.length || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Servicios Extra
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{category.additional_services?.length || 0}</div>
          </CardContent>
        </Card>
      </div>

      {/* Tariff Tiers */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Car className="h-5 w-5" />
                Tarifas
              </CardTitle>
              <CardDescription>
                Precios segun el tipo de proyecto y cliente
              </CardDescription>
            </div>
            <div className="flex items-center gap-4">
              <Select value={clientTypeFilter} onValueChange={setClientTypeFilter}>
                <SelectTrigger className="w-[160px]">
                  <SelectValue placeholder="Tipo cliente" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="particular">Particular</SelectItem>
                  <SelectItem value="professional">Profesional</SelectItem>
                </SelectContent>
              </Select>
              <Button onClick={openCreateDialog}>
                <Plus className="h-4 w-4 mr-2" />
                Nueva Tarifa
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {filteredTiers.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <Car className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <p className="text-muted-foreground mb-4">
                No hay tarifas configuradas
              </p>
              <Button onClick={openCreateDialog}>
                <Plus className="h-4 w-4 mr-2" />
                Nueva Tarifa
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-24">Codigo</TableHead>
                  <TableHead>Nombre</TableHead>
                  <TableHead>Cliente</TableHead>
                  <TableHead>Condiciones</TableHead>
                  <TableHead className="text-right">Precio</TableHead>
                  <TableHead className="w-20 text-center">Estado</TableHead>
                  <TableHead className="w-24">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredTiers
                  .sort((a, b) => a.sort_order - b.sort_order)
                  .map((tier) => (
                    <TableRow key={tier.id}>
                      <TableCell>
                        <Badge variant="outline">{tier.code}</Badge>
                      </TableCell>
                      <TableCell>
                        <div className="font-medium">{tier.name}</div>
                        {tier.description && (
                          <div className="text-xs text-muted-foreground truncate max-w-xs">
                            {tier.description}
                          </div>
                        )}
                      </TableCell>
                      <TableCell>{getClientTypeBadge(tier.client_type)}</TableCell>
                      <TableCell className="text-muted-foreground text-sm max-w-xs">
                        <div className="truncate">{tier.conditions || "-"}</div>
                        {tier.classification_rules?.applies_if_any?.length ? (
                          <div className="text-xs mt-1">
                            Keywords: {tier.classification_rules.applies_if_any.slice(0, 2).join(", ")}
                            {tier.classification_rules.applies_if_any.length > 2 && "..."}
                          </div>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-right">
                        <span className="font-semibold">{formatPrice(tier.price)}</span>
                      </TableCell>
                      <TableCell className="text-center">
                        <Badge
                          variant={tier.is_active ? "default" : "secondary"}
                          className={tier.is_active ? "bg-green-600" : ""}
                        >
                          {tier.is_active ? (
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
                        <div className="flex gap-1">
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-8 w-8"
                            onClick={() => openEditDialog(tier)}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-8 w-8"
                            onClick={() => setDeleteTier(tier)}
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Base Documentation */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                Documentacion Base
              </CardTitle>
              <CardDescription>
                Documentos requeridos para todas las homologaciones de esta categoria
              </CardDescription>
            </div>
            <Button onClick={openCreateBaseDocDialog}>
              <Plus className="h-4 w-4 mr-2" />
              Nueva Documentación
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {category.base_documentation?.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <FileText className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <p className="text-muted-foreground mb-4">
                No hay documentacion base configurada
              </p>
              <Button onClick={openCreateBaseDocDialog}>
                <Plus className="h-4 w-4 mr-2" />
                Nueva Documentación
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              {category.base_documentation
                ?.sort((a, b) => a.sort_order - b.sort_order)
                .map((doc, index) => (
                  <div
                    key={doc.id}
                    className="flex items-start gap-4 p-4 border rounded-lg"
                  >
                    <div className="flex items-center justify-center w-8 h-8 bg-muted rounded-full text-sm font-medium flex-shrink-0">
                      {index + 1}
                    </div>

                    {doc.image_url && (
                      <div className="relative w-20 h-20 rounded overflow-hidden bg-muted flex-shrink-0">
                        <img
                          src={doc.image_url}
                          alt="Ejemplo"
                          className="object-cover w-full h-full"
                        />
                      </div>
                    )}

                    <div className="flex-1 min-w-0">
                      <p className="text-sm">{doc.description}</p>
                      {!doc.image_url && (
                        <Badge variant="outline" className="text-xs mt-2">
                          Sin imagen
                        </Badge>
                      )}
                    </div>

                    <div className="flex gap-1 flex-shrink-0">
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        onClick={() => openEditBaseDocDialog(doc)}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        onClick={() => setDeleteBaseDoc(doc)}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </div>
                ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Element Documentation */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <ImageIcon className="h-5 w-5" />
                Documentacion por Elemento
              </CardTitle>
              <CardDescription>
                Requisitos especificos segun el elemento a homologar (keywords)
              </CardDescription>
            </div>
            <Button onClick={openCreateElementDocDialog}>
              <Plus className="h-4 w-4 mr-2" />
              Nueva Documentacion
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {category.element_documentation?.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <ImageIcon className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <p className="text-muted-foreground mb-4">
                No hay documentacion por elemento configurada
              </p>
              <Button onClick={openCreateElementDocDialog}>
                <Plus className="h-4 w-4 mr-2" />
                Nueva Documentacion
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              {category.element_documentation
                ?.sort((a, b) => a.sort_order - b.sort_order)
                .map((doc) => (
                  <div
                    key={doc.id}
                    className="flex items-start gap-4 p-4 border rounded-lg"
                  >
                    {doc.image_url && (
                      <div className="relative w-20 h-20 rounded overflow-hidden bg-muted flex-shrink-0">
                        <img
                          src={doc.image_url}
                          alt="Ejemplo"
                          className="object-cover w-full h-full"
                        />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap gap-1 mb-2">
                        {doc.element_keywords.map((keyword) => (
                          <Badge key={keyword} variant="secondary" className="text-xs">
                            {keyword}
                          </Badge>
                        ))}
                      </div>
                      <p className="text-sm">{doc.description}</p>
                      <div className="flex items-center gap-2 mt-2">
                        <Badge variant={doc.is_active ? "default" : "outline"} className="text-xs">
                          {doc.is_active ? "Activo" : "Inactivo"}
                        </Badge>
                      </div>
                    </div>
                    <div className="flex gap-1 flex-shrink-0">
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        onClick={() => openEditElementDocDialog(doc)}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        onClick={() => setDeleteElementDoc(doc)}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </div>
                ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Additional Services */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Plus className="h-5 w-5" />
                Servicios Adicionales
              </CardTitle>
              <CardDescription>
                Servicios extra disponibles para esta categoria
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {category.additional_services?.length === 0 ? (
            <p className="text-muted-foreground text-sm text-center py-4">
              No hay servicios adicionales configurados
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Codigo</TableHead>
                  <TableHead>Nombre</TableHead>
                  <TableHead>Descripcion</TableHead>
                  <TableHead className="text-right">Precio</TableHead>
                  <TableHead className="text-center">Estado</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {category.additional_services
                  ?.sort((a, b) => a.sort_order - b.sort_order)
                  .map((service) => (
                    <TableRow key={service.id}>
                      <TableCell>
                        <code className="text-xs bg-muted px-1 py-0.5 rounded">
                          {service.code}
                        </code>
                      </TableCell>
                      <TableCell className="font-medium">{service.name}</TableCell>
                      <TableCell className="text-muted-foreground text-sm max-w-xs truncate">
                        {service.description || "-"}
                      </TableCell>
                      <TableCell className="text-right font-semibold">
                        {formatPrice(service.price)}
                      </TableCell>
                      <TableCell className="text-center">
                        <Badge variant={service.is_active ? "default" : "secondary"}>
                          {service.is_active ? "Activo" : "Inactivo"}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Edit/Create Tier Dialog */}
      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editingTier ? "Editar Tarifa" : "Nueva Tarifa"}
            </DialogTitle>
            <DialogDescription>
              {editingTier
                ? "Modifica los datos de la tarifa"
                : "Crea una nueva tarifa para esta categoria"}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="code">Codigo</Label>
                <Input
                  id="code"
                  value={tierForm.code}
                  onChange={(e) =>
                    setTierForm((prev) => ({ ...prev, code: e.target.value.toUpperCase() }))
                  }
                  placeholder="T1"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="price">Precio (EUR)</Label>
                <Input
                  id="price"
                  type="number"
                  step="0.01"
                  value={tierForm.price}
                  onChange={(e) =>
                    setTierForm((prev) => ({ ...prev, price: e.target.value }))
                  }
                  placeholder="450"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="name">Nombre</Label>
              <Input
                id="name"
                value={tierForm.name}
                onChange={(e) =>
                  setTierForm((prev) => ({ ...prev, name: e.target.value }))
                }
                placeholder="Tarifa Basica"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">Descripcion</Label>
              <Textarea
                id="description"
                value={tierForm.description}
                onChange={(e) =>
                  setTierForm((prev) => ({ ...prev, description: e.target.value }))
                }
                placeholder="Descripcion de la tarifa..."
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Tipo de Cliente</Label>
                <Select
                  value={tierForm.client_type}
                  onValueChange={(value: TierClientType) =>
                    setTierForm((prev) => ({ ...prev, client_type: value }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos</SelectItem>
                    <SelectItem value="particular">Particular</SelectItem>
                    <SelectItem value="professional">Profesional</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Estado</Label>
                <Select
                  value={tierForm.is_active ? "active" : "inactive"}
                  onValueChange={(value) =>
                    setTierForm((prev) => ({ ...prev, is_active: value === "active" }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="active">Activo</SelectItem>
                    <SelectItem value="inactive">Inactivo</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="conditions">Condiciones</Label>
              <Textarea
                id="conditions"
                value={tierForm.conditions}
                onChange={(e) =>
                  setTierForm((prev) => ({ ...prev, conditions: e.target.value }))
                }
                placeholder="Condiciones de aplicacion de la tarifa..."
              />
            </div>

            <div className="space-y-2">
              <Label>Keywords de clasificacion (para la IA)</Label>
              <div className="flex gap-2">
                <Input
                  value={keywordInput}
                  onChange={(e) => setKeywordInput(e.target.value)}
                  placeholder="escape, silenciador..."
                  onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addKeyword())}
                />
                <Button type="button" variant="outline" onClick={addKeyword}>
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
              <div className="flex flex-wrap gap-2 mt-2">
                {tierForm.classification_rules.applies_if_any.map((keyword) => (
                  <Badge key={keyword} variant="secondary" className="gap-1">
                    {keyword}
                    <button type="button" onClick={() => removeKeyword(keyword)}>
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                La IA aplicara esta tarifa si el usuario menciona alguna de estas palabras
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="min_elements">Min. Elementos</Label>
                <Input
                  id="min_elements"
                  type="number"
                  value={tierForm.min_elements}
                  onChange={(e) =>
                    setTierForm((prev) => ({ ...prev, min_elements: e.target.value }))
                  }
                  placeholder="Opcional"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="max_elements">Max. Elementos</Label>
                <Input
                  id="max_elements"
                  type="number"
                  value={tierForm.max_elements}
                  onChange={(e) =>
                    setTierForm((prev) => ({ ...prev, max_elements: e.target.value }))
                  }
                  placeholder="Opcional"
                />
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
              onClick={handleSaveTier}
              disabled={isSaving || !tierForm.code.trim() || !tierForm.name.trim() || !tierForm.price}
            >
              {isSaving ? "Guardando..." : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deleteTier} onOpenChange={() => setDeleteTier(null)}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>Eliminar Tarifa</DialogTitle>
            <DialogDescription>
              Estas seguro de eliminar la tarifa &quot;{deleteTier?.name}&quot; ({deleteTier?.code})?
              Esta accion no se puede deshacer.
            </DialogDescription>
          </DialogHeader>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteTier(null)}
              disabled={isDeleting}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteTier}
              disabled={isDeleting}
            >
              {isDeleting ? "Eliminando..." : "Eliminar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Element Documentation Dialog */}
      <Dialog open={isElementDocDialogOpen} onOpenChange={setIsElementDocDialogOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>
              {editingElementDoc ? "Editar Documentacion" : "Nueva Documentacion por Elemento"}
            </DialogTitle>
            <DialogDescription>
              Define los keywords que activaran esta documentacion especifica
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label>Keywords (palabras clave)</Label>
              <div className="flex gap-2">
                <Input
                  value={elementDocKeywordInput}
                  onChange={(e) => setElementDocKeywordInput(e.target.value)}
                  placeholder="escalera, toldo, bola remolque..."
                  onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addElementDocKeyword())}
                />
                <Button type="button" variant="outline" onClick={addElementDocKeyword}>
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
              <div className="flex flex-wrap gap-2 mt-2">
                {elementDocForm.element_keywords.map((keyword) => (
                  <Badge key={keyword} variant="secondary" className="gap-1">
                    {keyword}
                    <button type="button" onClick={() => removeElementDocKeyword(keyword)}>
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                El bot mostrara esta documentacion cuando el usuario mencione alguna de estas palabras
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="elemDocDescription">Descripcion del requisito</Label>
              <Textarea
                id="elemDocDescription"
                value={elementDocForm.description}
                onChange={(e) =>
                  setElementDocForm((prev) => ({ ...prev, description: e.target.value }))
                }
                placeholder="Foto de la escalera instalada, midiendo el nuevo ancho total del vehiculo..."
                rows={3}
              />
            </div>

            <div className="space-y-2">
              <Label>Imagen de ejemplo</Label>
              <ImageUpload
                value={elementDocForm.image_url}
                onChange={(url) =>
                  setElementDocForm((prev) => ({ ...prev, image_url: url }))
                }
                category="element"
              />
            </div>

            <div className="space-y-2">
              <Label>Estado</Label>
              <Select
                value={elementDocForm.is_active ? "active" : "inactive"}
                onValueChange={(value) =>
                  setElementDocForm((prev) => ({ ...prev, is_active: value === "active" }))
                }
              >
                <SelectTrigger>
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
              onClick={() => setIsElementDocDialogOpen(false)}
              disabled={isSavingElementDoc}
            >
              Cancelar
            </Button>
            <Button
              onClick={handleSaveElementDoc}
              disabled={
                isSavingElementDoc ||
                elementDocForm.element_keywords.length === 0 ||
                !elementDocForm.description.trim()
              }
            >
              {isSavingElementDoc ? "Guardando..." : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Element Documentation Dialog */}
      <Dialog open={!!deleteElementDoc} onOpenChange={() => setDeleteElementDoc(null)}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>Eliminar Documentacion</DialogTitle>
            <DialogDescription>
              Estas seguro de eliminar esta documentacion por elemento? Esta accion no se puede deshacer.
            </DialogDescription>
          </DialogHeader>

          {deleteElementDoc && (
            <div className="flex flex-wrap gap-1 py-2">
              {deleteElementDoc.element_keywords.map((kw) => (
                <Badge key={kw} variant="secondary">
                  {kw}
                </Badge>
              ))}
            </div>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteElementDoc(null)}
              disabled={isDeletingElementDoc}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteElementDoc}
              disabled={isDeletingElementDoc}
            >
              {isDeletingElementDoc ? "Eliminando..." : "Eliminar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Base Documentation Dialog */}
      <Dialog open={isBaseDocDialogOpen} onOpenChange={setIsBaseDocDialogOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>
              {editingBaseDoc ? "Editar Documentación" : "Nueva Documentación Base"}
            </DialogTitle>
            <DialogDescription>
              Define un requisito de documentación que aplica a todas las homologaciones
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="baseDocDescription">Descripción del requisito</Label>
              <Textarea
                id="baseDocDescription"
                value={baseDocForm.description}
                onChange={(e) =>
                  setBaseDocForm((prev) => ({ ...prev, description: e.target.value }))
                }
                placeholder="Ej: Ficha técnica del vehículo (ambas caras)"
                rows={3}
              />
            </div>

            <div className="space-y-2">
              <Label>Imagen de ejemplo (opcional)</Label>
              <ImageUpload
                value={baseDocForm.image_url}
                onChange={(url) =>
                  setBaseDocForm((prev) => ({ ...prev, image_url: url }))
                }
                category="documentation"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="baseSortOrder">Orden</Label>
              <Input
                id="baseSortOrder"
                type="number"
                value={baseDocForm.sort_order}
                onChange={(e) =>
                  setBaseDocForm((prev) => ({
                    ...prev,
                    sort_order: parseInt(e.target.value) || 0
                  }))
                }
              />
              <p className="text-xs text-muted-foreground">
                Orden en que aparecerá en la lista (menor = primero)
              </p>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsBaseDocDialogOpen(false)}
              disabled={isSavingBaseDoc}
            >
              Cancelar
            </Button>
            <Button
              onClick={handleSaveBaseDoc}
              disabled={isSavingBaseDoc || !baseDocForm.description.trim()}
            >
              {isSavingBaseDoc ? "Guardando..." : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Base Documentation Dialog */}
      <Dialog open={!!deleteBaseDoc} onOpenChange={() => setDeleteBaseDoc(null)}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>Eliminar Documentación</DialogTitle>
            <DialogDescription>
              ¿Estás seguro de eliminar esta documentación base? Esta acción no se puede deshacer.
            </DialogDescription>
          </DialogHeader>

          {deleteBaseDoc && (
            <div className="py-2">
              <p className="text-sm font-medium">{deleteBaseDoc.description}</p>
            </div>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteBaseDoc(null)}
              disabled={isDeletingBaseDoc}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteBaseDoc}
              disabled={isDeletingBaseDoc}
            >
              {isDeletingBaseDoc ? "Eliminando..." : "Eliminar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
