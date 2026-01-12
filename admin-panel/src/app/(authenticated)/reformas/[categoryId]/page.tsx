"use client";

import { useState, useEffect } from "react";
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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Car,
  ArrowLeft,
  FileText,
  Plus,
  Pencil,
  Trash2,
  Building2,
  User,
  CheckCircle2,
  Settings,
  Layers,
  ImageIcon,
  Globe,
  AlertTriangle,
} from "lucide-react";
import api from "@/lib/api";

// Custom hooks
import { useCategoryData } from "@/hooks/use-category-data";
import { useTierElements } from "@/hooks/use-tier-elements";
import { useCategoryElements } from "@/hooks/use-category-elements";

// Extracted dialog components
import { TierFormDialog } from "@/components/tariffs/tier-form-dialog";
import { BaseDocDialog } from "@/components/tariffs/base-doc-dialog";
import { DeleteConfirmationDialog } from "@/components/tariffs/delete-confirmation-dialog";
import { ElementFormDialog } from "@/components/tariffs/element-form-dialog";
import { ServiceFormDialog } from "@/components/tariffs/service-form-dialog";
import { ElementWarningsDialog } from "@/components/elements/element-warnings-dialog";

import type { TariffTier, BaseDocumentation, ClientType, Element, AdditionalService } from "@/lib/types";

export default function CategoryDetailPage() {
  const params = useParams();
  const router = useRouter();
  const categoryId = params.categoryId as string;

  // Use custom hook for category data
  const { category, isLoading, refetch } = useCategoryData(categoryId);

  // Tier dialog state (simplified)
  const [tierDialog, setTierDialog] = useState<{
    open: boolean;
    tier: TariffTier | null;
  }>({ open: false, tier: null });
  const [deleteTier, setDeleteTier] = useState<TariffTier | null>(null);

  // Base documentation dialog state (simplified)
  const [baseDocDialog, setBaseDocDialog] = useState<{
    open: boolean;
    doc: BaseDocumentation | null;
  }>({ open: false, doc: null });
  const [deleteBaseDoc, setDeleteBaseDoc] = useState<BaseDocumentation | null>(null);

  // Element dialog state
  const [elementDialog, setElementDialog] = useState<{
    open: boolean;
    element: Element | null;
  }>({ open: false, element: null });
  const [deleteElement, setDeleteElement] = useState<Element | null>(null);
  const [warningsElement, setWarningsElement] = useState<Element | null>(null);

  // Service dialog state
  const [serviceDialog, setServiceDialog] = useState<{
    open: boolean;
    service: AdditionalService | null;
  }>({ open: false, service: null });
  const [deleteService, setDeleteService] = useState<AdditionalService | null>(null);
  const [globalServices, setGlobalServices] = useState<AdditionalService[]>([]);

  // All tiers (no filtering needed - category already determines client type)
  const tiers = category?.tariff_tiers || [];

  // Fetch elements for this category
  const { elements, isLoading: isLoadingElements, refetch: refetchElements } =
    useCategoryElements(categoryId);

  // Fetch element counts for all tiers
  const { tierElementCounts } = useTierElements(category?.tariff_tiers);

  // Fetch global services
  const fetchGlobalServices = async () => {
    try {
      const response = await api.getAdditionalServices({ limit: 100 });
      const globals = response.items.filter((s) => s.category_id === null);
      setGlobalServices(globals);
    } catch (error) {
      console.error("Error fetching global services:", error);
    }
  };

  useEffect(() => {
    fetchGlobalServices();
  }, []);

  // Combine category services with global services
  const allServices = [
    ...(category?.additional_services || []),
    ...globalServices.filter(
      (gs) => !category?.additional_services?.some((cs) => cs.id === gs.id)
    ),
  ].sort((a, b) => a.sort_order - b.sort_order);

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat("es-ES", {
      style: "currency",
      currency: "EUR",
    }).format(price);
  };

  // Get category client type badge
  const getCategoryClientTypeBadge = (clientType: ClientType) => {
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
    }
  };

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
          <Button variant="outline" className="mt-4" onClick={() => router.push("/reformas")}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            Volver a Reformas
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
          <Link href="/reformas">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-5 w-5" />
            </Button>
          </Link>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-bold tracking-tight">{category.name}</h1>
              {category.client_type && getCategoryClientTypeBadge(category.client_type)}
              <Badge variant={category.is_active ? "default" : "secondary"}>
                {category.is_active ? "Activo" : "Inactivo"}
              </Badge>
            </div>
            <p className="text-muted-foreground">
              {category.description || `Gestion de tarifas para ${category.name.toLowerCase()}`}
              <span className="text-xs ml-2">({category.slug})</span>
            </p>
          </div>
        </div>
      </div>

      {/* Stats Overview */}
      <div className="grid grid-cols-5 gap-4">
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
              Elementos
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{elements?.length || 0}</div>
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
                Precios segun el tipo de proyecto
              </CardDescription>
            </div>
            <Button onClick={() => setTierDialog({ open: true, tier: null })}>
              <Plus className="h-4 w-4 mr-2" />
              Nueva Tarifa
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {tiers.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <Car className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <p className="text-muted-foreground mb-4">
                No hay tarifas configuradas
              </p>
              <Button onClick={() => setTierDialog({ open: true, tier: null })}>
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
                  <TableHead>Condiciones</TableHead>
                  <TableHead className="text-right">Precio</TableHead>
                  <TableHead className="w-28">Elementos</TableHead>
                  <TableHead className="w-20 text-center">Estado</TableHead>
                  <TableHead className="w-40">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tiers
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
                      <TableCell>
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Badge variant="outline" className="cursor-help">
                                {tierElementCounts[tier.id]?.total_elements || 0} elem.
                              </Badge>
                            </TooltipTrigger>
                            <TooltipContent side="left" className="max-w-xs">
                              <div className="space-y-1">
                                {tierElementCounts[tier.id]?.total_elements > 0 ? (
                                  <>
                                    <p className="font-medium text-xs mb-1">Elementos incluidos:</p>
                                    {Object.entries(tierElementCounts[tier.id]?.elements || {})
                                      .slice(0, 5)
                                      .map(([elementId, qty]) => (
                                        <div key={elementId} className="text-xs">
                                          {qty ? `(max: ${qty})` : "(ilimitado)"}
                                        </div>
                                      ))}
                                    {tierElementCounts[tier.id]?.total_elements > 5 && (
                                      <div className="text-xs text-muted-foreground mt-1">
                                        +{tierElementCounts[tier.id].total_elements - 5} más...
                                      </div>
                                    )}
                                  </>
                                ) : (
                                  <div className="text-xs text-muted-foreground">
                                    Sin elementos configurados
                                  </div>
                                )}
                              </div>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
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
                            size="sm"
                            variant="outline"
                            className="h-8"
                            onClick={() => router.push(`/reformas/${categoryId}/${tier.id}/inclusions`)}
                          >
                            <Settings className="h-3 w-3 mr-1" />
                            Gestionar
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-8 w-8"
                            onClick={() => setTierDialog({ open: true, tier })}
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
            <Button onClick={() => setBaseDocDialog({ open: true, doc: null })}>
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
              <Button onClick={() => setBaseDocDialog({ open: true, doc: null })}>
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
                        onClick={() => setBaseDocDialog({ open: true, doc })}
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

      {/* Elements Section */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Layers className="h-5 w-5" />
                Elementos de la Categoria
              </CardTitle>
              <CardDescription>
                Elementos que pueden incluirse en las tarifas de homologacion
              </CardDescription>
            </div>
            <Button onClick={() => setElementDialog({ open: true, element: null })}>
              <Plus className="h-4 w-4 mr-2" />
              Nuevo Elemento
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {isLoadingElements ? (
            <div className="flex items-center justify-center py-8">
              <div className="text-muted-foreground">Cargando elementos...</div>
            </div>
          ) : elements.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <Layers className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <p className="text-muted-foreground mb-4">
                No hay elementos configurados
              </p>
              <Button onClick={() => setElementDialog({ open: true, element: null })}>
                <Plus className="h-4 w-4 mr-2" />
                Nuevo Elemento
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-32">Codigo</TableHead>
                  <TableHead>Nombre</TableHead>
                  <TableHead>Keywords</TableHead>
                  <TableHead className="w-24 text-center">Imagenes</TableHead>
                  <TableHead className="w-20 text-center">Estado</TableHead>
                  <TableHead className="w-32">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {elements
                  .sort((a, b) => a.sort_order - b.sort_order)
                  .map((element) => (
                    <TableRow key={element.id}>
                      <TableCell>
                        <code className="text-xs bg-muted px-2 py-1 rounded font-mono">
                          {element.code}
                        </code>
                      </TableCell>
                      <TableCell>
                        <div className="font-medium">{element.name}</div>
                        {element.description && (
                          <div className="text-xs text-muted-foreground truncate max-w-xs">
                            {element.description}
                          </div>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {element.keywords?.slice(0, 3).map((keyword) => (
                            <Badge key={keyword} variant="outline" className="text-xs">
                              {keyword}
                            </Badge>
                          ))}
                          {element.keywords?.length > 3 && (
                            <Badge variant="outline" className="text-xs">
                              +{element.keywords.length - 3}
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="text-center">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => router.push(`/elementos/${element.id}`)}
                          className="h-8"
                        >
                          <ImageIcon className="h-4 w-4 mr-1" />
                          Ver
                        </Button>
                      </TableCell>
                      <TableCell className="text-center">
                        <Badge variant={element.is_active ? "default" : "secondary"}>
                          {element.is_active ? "Activo" : "Inactivo"}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  size="icon"
                                  variant="ghost"
                                  className="h-8 w-8"
                                  onClick={() => setWarningsElement(element)}
                                >
                                  <AlertTriangle className="h-4 w-4 text-amber-500" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>
                                <p>Gestionar advertencias</p>
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-8 w-8"
                            onClick={() => setElementDialog({ open: true, element })}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-8 w-8"
                            onClick={() => setDeleteElement(element)}
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
                Servicios extra disponibles para esta categoria (incluye globales)
              </CardDescription>
            </div>
            <Button onClick={() => setServiceDialog({ open: true, service: null })}>
              <Plus className="h-4 w-4 mr-2" />
              Anadir Servicio
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {allServices.length === 0 ? (
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
                  <TableHead className="text-center">Ambito</TableHead>
                  <TableHead className="text-center">Estado</TableHead>
                  <TableHead className="w-20">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {allServices.map((service) => (
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
                      {service.category_id === null ? (
                        <Badge variant="outline" className="gap-1">
                          <Globe className="h-3 w-3" />
                          Global
                        </Badge>
                      ) : (
                        <Badge variant="secondary">Categoria</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-center">
                      <Badge variant={service.is_active ? "default" : "secondary"}>
                        {service.is_active ? "Activo" : "Inactivo"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8"
                          onClick={() => setServiceDialog({ open: true, service })}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8"
                          onClick={() => setDeleteService(service)}
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

      {/* Tier Form Dialog */}
      <TierFormDialog
        open={tierDialog.open}
        onOpenChange={(open) => setTierDialog({ open, tier: null })}
        tier={tierDialog.tier}
        categoryId={categoryId}
        onSuccess={refetch}
      />

      {/* Delete Tier Dialog */}
      <DeleteConfirmationDialog
        open={!!deleteTier}
        onOpenChange={() => setDeleteTier(null)}
        title="Eliminar Tarifa"
        description={`Estas seguro de eliminar la tarifa "${deleteTier?.name}" (${deleteTier?.code})? Esta accion no se puede deshacer.`}
        onConfirm={async () => {
          if (deleteTier) {
            await api.deleteTariffTier(deleteTier.id);
            setDeleteTier(null);
            refetch();
          }
        }}
      />

      {/* Base Documentation Dialog */}
      <BaseDocDialog
        open={baseDocDialog.open}
        onOpenChange={(open) => setBaseDocDialog({ open, doc: null })}
        doc={baseDocDialog.doc}
        categoryId={categoryId}
        defaultSortOrder={category.base_documentation?.length || 0}
        onSuccess={refetch}
      />

      {/* Delete Base Documentation Dialog */}
      <DeleteConfirmationDialog
        open={!!deleteBaseDoc}
        onOpenChange={() => setDeleteBaseDoc(null)}
        title="Eliminar Documentacion"
        description="Estas seguro de eliminar esta documentacion base? Esta accion no se puede deshacer."
        itemDescription={deleteBaseDoc?.description}
        onConfirm={async () => {
          if (deleteBaseDoc) {
            await api.deleteBaseDocumentation(deleteBaseDoc.id);
            setDeleteBaseDoc(null);
            refetch();
          }
        }}
      />

      {/* Element Form Dialog */}
      <ElementFormDialog
        open={elementDialog.open}
        onOpenChange={(open) => setElementDialog({ open, element: null })}
        element={elementDialog.element}
        categoryId={categoryId}
        onSuccess={() => {
          refetchElements();
          refetch();
        }}
      />

      {/* Delete Element Dialog */}
      <DeleteConfirmationDialog
        open={!!deleteElement}
        onOpenChange={() => setDeleteElement(null)}
        title="Eliminar Elemento"
        description={`Estas seguro de eliminar el elemento "${deleteElement?.name}" (${deleteElement?.code})? Esta accion no se puede deshacer.`}
        itemDescription={deleteElement?.description || undefined}
        onConfirm={async () => {
          if (deleteElement) {
            await api.deleteElement(deleteElement.id);
            setDeleteElement(null);
            refetchElements();
            refetch();
          }
        }}
      />

      {/* Element Warnings Dialog */}
      <ElementWarningsDialog
        open={!!warningsElement}
        onOpenChange={() => setWarningsElement(null)}
        element={warningsElement}
      />

      {/* Service Form Dialog */}
      <ServiceFormDialog
        open={serviceDialog.open}
        onOpenChange={(open) => setServiceDialog({ open, service: null })}
        service={serviceDialog.service}
        categoryId={categoryId}
        defaultSortOrder={allServices.length}
        onSuccess={() => {
          refetch();
          fetchGlobalServices();
        }}
      />

      {/* Delete Service Dialog */}
      <DeleteConfirmationDialog
        open={!!deleteService}
        onOpenChange={() => setDeleteService(null)}
        title="Eliminar Servicio"
        description={`Estas seguro de eliminar el servicio "${deleteService?.name}" (${deleteService?.code})? Esta accion no se puede deshacer.`}
        itemDescription={deleteService?.description || undefined}
        onConfirm={async () => {
          if (deleteService) {
            await api.deleteAdditionalService(deleteService.id);
            setDeleteService(null);
            refetch();
            fetchGlobalServices();
          }
        }}
      />
    </div>
  );
}
