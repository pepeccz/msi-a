"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Image from "next/image";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
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
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import {
  ArrowLeft,
  CheckCircle2,
  Clock,
  RefreshCw,
  ExternalLink,
  Image as ImageIcon,
  Play,
  Ban,
  AlertTriangle,
  Inbox,
  Download,
  FileArchive,
  User,
  Car,
  Mail,
  Phone,
  FileText,
  Check,
  X,
  ZoomIn,
  IdCard,
  MapPin,
  Wrench,
  Building2,
  Ruler,
} from "lucide-react";
import api from "@/lib/api";
import type { Case, CaseStatus, CaseImage, CaseElementData } from "@/lib/types";

export default function CaseDetailPage() {
  const params = useParams();
  const router = useRouter();
  const caseId = params.id as string;

  const [caseData, setCaseData] = useState<Case | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [selectedImage, setSelectedImage] = useState<CaseImage | null>(null);
  const [isImageDialogOpen, setIsImageDialogOpen] = useState(false);
  const [isResolveDialogOpen, setIsResolveDialogOpen] = useState(false);
  const [elementDataList, setElementDataList] = useState<CaseElementData[]>([]);

  const fetchCase = useCallback(async () => {
    try {
      setIsLoading(true);
      const data = await api.getCase(caseId);
      setCaseData(data);
      
      // Fetch element data
      try {
        const elementDataResponse = await api.getCaseElementDataList(caseId);
        setElementDataList(elementDataResponse.elements);
      } catch (error) {
        // Element data might not exist yet
        console.error("Error fetching element data:", error);
        setElementDataList([]);
      }
    } catch (error) {
      console.error("Error fetching case:", error);
    } finally {
      setIsLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    fetchCase();
  }, [fetchCase]);

  const formatDate = (dateString: string | null) => {
    if (!dateString) return "-";
    return new Date(dateString).toLocaleString("es-ES", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const getStatusBadge = (status: CaseStatus) => {
    switch (status) {
      case "collecting":
        return (
          <Badge variant="outline" className="border-blue-500 text-blue-600">
            <Clock className="h-3 w-3 mr-1" />
            Recolectando
          </Badge>
        );
      case "pending_images":
        return (
          <Badge variant="outline" className="border-orange-500 text-orange-600">
            <ImageIcon className="h-3 w-3 mr-1" />
            Faltan Imagenes
          </Badge>
        );
      case "pending_review":
        return (
          <Badge variant="destructive" className="bg-red-600">
            <Inbox className="h-3 w-3 mr-1" />
            Pendiente
          </Badge>
        );
      case "in_progress":
        return (
          <Badge variant="default" className="bg-yellow-600">
            <Play className="h-3 w-3 mr-1" />
            En Progreso
          </Badge>
        );
      case "resolved":
        return (
          <Badge variant="secondary" className="bg-green-600 text-white">
            <CheckCircle2 className="h-3 w-3 mr-1" />
            Resuelto
          </Badge>
        );
      case "cancelled":
        return (
          <Badge variant="outline" className="border-gray-500 text-gray-600">
            <Ban className="h-3 w-3 mr-1" />
            Cancelado
          </Badge>
        );
      case "abandoned":
        return (
          <Badge variant="outline" className="border-gray-400 text-gray-500">
            <AlertTriangle className="h-3 w-3 mr-1" />
            Abandonado
          </Badge>
        );
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  const getCollectionStepBadge = (step: string | null | undefined) => {
    if (!step) return null;

    const stepConfig: Record<string, { label: string; color: string }> = {
      collect_images: { label: "Recibiendo Imagenes", color: "border-blue-500 text-blue-600" },
      collect_personal: { label: "Datos Personales", color: "border-indigo-500 text-indigo-600" },
      collect_vehicle: { label: "Datos Vehiculo", color: "border-cyan-500 text-cyan-600" },
      collect_workshop: { label: "Datos Taller", color: "border-violet-500 text-violet-600" },
      review_summary: { label: "Revision Final", color: "border-amber-500 text-amber-600" },
      completed: { label: "Completado", color: "border-green-500 text-green-600" },
    };

    const config = stepConfig[step];
    if (!config) return null;

    return (
      <Badge variant="outline" className={config.color}>
        {config.label}
      </Badge>
    );
  };

  const handleTakeCase = async () => {
    if (!caseData) return;
    try {
      setIsActionLoading(true);
      await api.takeCase(caseId);
      await fetchCase();
    } catch (error) {
      console.error("Error taking case:", error);
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleResolveCase = async () => {
    if (!caseData) return;
    try {
      setIsActionLoading(true);
      await api.resolveCase(caseId);
      setIsResolveDialogOpen(false);
      await fetchCase();
    } catch (error) {
      console.error("Error resolving case:", error);
    } finally {
      setIsActionLoading(false);
    }
  };

  const openChatwoot = () => {
    if (!caseData) return;
    const chatwootBaseUrl = process.env.NEXT_PUBLIC_CHATWOOT_URL || "https://app.chatwoot.com";
    const chatwootAccountId = process.env.NEXT_PUBLIC_CHATWOOT_ACCOUNT_ID || "1";
    const chatwootUrl = `${chatwootBaseUrl}/app/accounts/${chatwootAccountId}/conversations/${caseData.conversation_id}`;
    window.open(chatwootUrl, "_blank");
  };

  const handleImageClick = (image: CaseImage) => {
    setSelectedImage(image);
    setIsImageDialogOpen(true);
  };

  const downloadImage = (image: CaseImage) => {
    const url = api.getCaseImageDownloadUrl(caseId, image.id);
    window.open(url, "_blank");
  };

  const downloadAllImages = () => {
    const url = api.getCaseImagesZipUrl(caseId);
    window.open(url, "_blank");
  };

  // Helper component for image thumbnails
  const ImageThumbnail = ({ image }: { image: CaseImage }) => (
    <div
      className="relative aspect-square rounded-lg border overflow-hidden cursor-pointer group"
      onClick={() => handleImageClick(image)}
    >
      <Image
        src={image.url}
        alt={image.display_name}
        fill
        className="object-cover"
        sizes="150px"
      />
      <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
        <ZoomIn className="h-6 w-6 text-white" />
      </div>
      {/* Validation indicator */}
      {image.is_valid === true && (
        <div className="absolute bottom-1 right-1 bg-green-500 p-1 rounded-full">
          <Check className="h-3 w-3 text-white" />
        </div>
      )}
      {image.is_valid === false && (
        <div className="absolute bottom-1 right-1 bg-red-500 p-1 rounded-full">
          <X className="h-3 w-3 text-white" />
        </div>
      )}
      {/* Image name overlay */}
      <div className="absolute bottom-0 left-0 right-0 bg-black/60 px-2 py-1">
        <p className="text-xs text-white truncate">{image.display_name}</p>
      </div>
    </div>
  );

  if (isLoading) {
    return (
      <div className="p-6 flex items-center justify-center">
        <div className="animate-pulse text-muted-foreground">
          Cargando expediente...
        </div>
      </div>
    );
  }

  if (!caseData) {
    return (
      <div className="p-6">
        <div className="text-center py-8">
          <p className="text-muted-foreground">Expediente no encontrado</p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => router.back()}
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Volver a la lista
          </Button>
        </div>
      </div>
    );
  }

  // Filter base documentation images (those without element_code)
  const baseDocImages = caseData.images?.filter(
    (img) => !img.element_code
  ) || [];

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.back()}
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Volver
          </Button>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">
              Expediente #{caseData.conversation_id}
            </h1>
            <p className="text-muted-foreground">
              Creado el {formatDate(caseData.created_at)}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {getStatusBadge(caseData.status)}
          {caseData.status === "collecting" && caseData.current_step && (
            getCollectionStepBadge(caseData.current_step)
          )}
          <Button variant="outline" size="sm" onClick={openChatwoot}>
            <ExternalLink className="h-4 w-4 mr-2" />
            Chatwoot
          </Button>
          <Button variant="outline" size="sm" onClick={fetchCase}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Action Buttons */}
      {(caseData.status === "pending_review" ||
        caseData.status === "in_progress") && (
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">
                  {caseData.status === "pending_review"
                    ? "Este expediente esta pendiente de revision"
                    : "Este expediente esta en progreso"}
                </p>
                <p className="text-sm text-muted-foreground">
                  {caseData.status === "pending_review"
                    ? "Toma el expediente para comenzar a trabajar en el"
                    : "Marcalo como resuelto cuando hayas terminado"}
                </p>
              </div>
              <div className="flex gap-2">
                {caseData.status === "pending_review" && (
                  <Button onClick={handleTakeCase} disabled={isActionLoading}>
                    <Play className="h-4 w-4 mr-2" />
                    Tomar Expediente
                  </Button>
                )}
                {caseData.status === "in_progress" && (
                  <Button
                    variant="default"
                    className="bg-green-600 hover:bg-green-700"
                    onClick={() => setIsResolveDialogOpen(true)}
                    disabled={isActionLoading}
                  >
                    <CheckCircle2 className="h-4 w-4 mr-2" />
                    Marcar Resuelto
                  </Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        {/* Personal Data */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <User className="h-5 w-5" />
              Datos Personales
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Nombre</p>
                <p className="font-medium">{caseData.user_first_name || "-"}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Apellidos</p>
                <p className="font-medium">{caseData.user_last_name || "-"}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <IdCard className="h-4 w-4 text-muted-foreground" />
              <span className="font-mono">{caseData.user_nif_cif || "-"}</span>
            </div>
            <Separator />
            <div className="flex items-center gap-2">
              <Mail className="h-4 w-4 text-muted-foreground" />
              <span>{caseData.user_email || "-"}</span>
            </div>
            <div className="flex items-center gap-2">
              <Phone className="h-4 w-4 text-muted-foreground" />
              <span>{caseData.user_phone || "-"}</span>
            </div>
            {(caseData.user_domicilio_calle || caseData.user_domicilio_localidad) && (
              <>
                <Separator />
                <div className="flex items-start gap-2">
                  <MapPin className="h-4 w-4 text-muted-foreground mt-0.5" />
                  <div className="text-sm">
                    {caseData.user_domicilio_calle && <p>{caseData.user_domicilio_calle}</p>}
                    <p>
                      {[caseData.user_domicilio_cp, caseData.user_domicilio_localidad, caseData.user_domicilio_provincia]
                        .filter(Boolean)
                        .join(", ")}
                    </p>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Vehicle Data */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Car className="h-5 w-5" />
              Datos del Vehiculo
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Marca</p>
                <p className="font-medium">{caseData.vehiculo_marca || "-"}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Modelo</p>
                <p className="font-medium">{caseData.vehiculo_modelo || "-"}</p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Año</p>
                <p className="font-medium">{caseData.vehiculo_anio || "-"}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Matricula</p>
                <p className="font-medium">{caseData.vehiculo_matricula || "-"}</p>
              </div>
            </div>
            {caseData.vehiculo_bastidor && (
              <>
                <Separator />
                <div>
                  <p className="text-sm text-muted-foreground">Bastidor (VIN)</p>
                  <p className="font-mono text-sm">{caseData.vehiculo_bastidor}</p>
                </div>
              </>
            )}
            {/* Dimensional Changes */}
            {(caseData.cambio_plazas || caseData.cambio_altura || caseData.cambio_ancho || caseData.cambio_longitud) && (
              <>
                <Separator />
                <div>
                  <p className="text-sm text-muted-foreground flex items-center gap-1 mb-2">
                    <Ruler className="h-3 w-3" />
                    Cambios Dimensionales
                  </p>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    {caseData.cambio_plazas && (
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-xs">Plazas</Badge>
                        <span>{caseData.plazas_iniciales} → {caseData.plazas_finales}</span>
                      </div>
                    )}
                    {caseData.cambio_altura && (
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-xs">Altura</Badge>
                        <span>{caseData.altura_final} mm</span>
                      </div>
                    )}
                    {caseData.cambio_ancho && (
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-xs">Ancho</Badge>
                        <span>{caseData.ancho_final} mm</span>
                      </div>
                    )}
                    {caseData.cambio_longitud && (
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-xs">Longitud</Badge>
                        <span>{caseData.longitud_final} mm</span>
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Homologation Data */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Datos de Homologacion
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="text-sm text-muted-foreground">Categoria</p>
              <p className="font-medium">{caseData.category_name || "-"}</p>
            </div>
            {caseData.itv_nombre && (
              <>
                <Separator />
                <div>
                  <p className="text-sm text-muted-foreground">ITV</p>
                  <p className="font-medium">{caseData.itv_nombre}</p>
                </div>
              </>
            )}
            <Separator />
            <div>
              <p className="text-sm text-muted-foreground">Tarifa Calculada</p>
              <p className="text-xl font-bold">
                {caseData.tariff_amount
                  ? `${caseData.tariff_amount.toFixed(2)} EUR`
                  : "-"}
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Status Info */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock className="h-5 w-5" />
              Estado y Fechas
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Estado</p>
                <div className="mt-1">{getStatusBadge(caseData.status)}</div>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Resuelto por</p>
                <p className="font-medium">{caseData.resolved_by || "-"}</p>
              </div>
            </div>
            <Separator />
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-muted-foreground">Creado</p>
                <p>{formatDate(caseData.created_at)}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Actualizado</p>
                <p>{formatDate(caseData.updated_at)}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Completado</p>
                <p>{formatDate(caseData.completed_at)}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Resuelto</p>
                <p>{formatDate(caseData.resolved_at)}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Workshop/Certificate Section - Always shown */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Wrench className="h-5 w-5" />
            Certificado de Taller
          </CardTitle>
          <CardDescription>
            {caseData.taller_propio === true
              ? "El cliente aporta certificado de taller propio"
              : caseData.taller_propio === false
              ? "MSI aporta el certificado de taller"
              : "Pendiente de definir"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {caseData.taller_propio === true ? (
            // Taller propio - mostrar datos del taller
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              <div>
                <p className="text-sm text-muted-foreground">Nombre del Taller</p>
                <p className="font-medium">{caseData.taller_nombre || "-"}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Responsable</p>
                <p className="font-medium">{caseData.taller_responsable || "-"}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Telefono</p>
                <p className="font-medium">{caseData.taller_telefono || "-"}</p>
              </div>
              <div className="md:col-span-2">
                <p className="text-sm text-muted-foreground">Direccion</p>
                <p className="font-medium">
                  {caseData.taller_domicilio || "-"}
                  {(caseData.taller_ciudad || caseData.taller_provincia) && (
                    <span className="text-muted-foreground">
                      {" - "}
                      {[caseData.taller_ciudad, caseData.taller_provincia].filter(Boolean).join(", ")}
                    </span>
                  )}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Registro Industrial</p>
                <p className="font-mono text-sm">{caseData.taller_registro_industrial || "-"}</p>
              </div>
              {caseData.taller_actividad && (
                <div className="md:col-span-2 lg:col-span-3">
                  <p className="text-sm text-muted-foreground">Actividad</p>
                  <p className="font-medium">{caseData.taller_actividad}</p>
                </div>
              )}
            </div>
          ) : caseData.taller_propio === false ? (
            // MSI aporta certificado
            <div className="flex items-center gap-3 p-4 bg-blue-50 dark:bg-blue-950 rounded-lg">
              <Building2 className="h-6 w-6 text-blue-600" />
              <div>
                <p className="font-medium text-blue-700 dark:text-blue-400">
                  MSI aporta certificado de taller
                </p>
                <p className="text-sm text-blue-600 dark:text-blue-500">
                  +85 EUR +IVA incluido en el presupuesto
                </p>
              </div>
            </div>
          ) : (
            // No definido todavia
            <div className="flex items-center gap-3 p-4 bg-gray-50 dark:bg-gray-900 rounded-lg">
              <Clock className="h-6 w-6 text-gray-400" />
              <div>
                <p className="font-medium text-gray-600 dark:text-gray-400">
                  Pendiente de definir
                </p>
                <p className="text-sm text-gray-500">
                  El cliente aun no ha indicado si aporta taller propio o necesita certificado de MSI
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Images and Elements - Unified Section */}
      {(baseDocImages.length > 0 || caseData.element_codes.length > 0) && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <ImageIcon className="h-5 w-5" />
                Imagenes y Elementos
              </CardTitle>
              {caseData.images && caseData.images.length > 0 && (
                <Button variant="outline" onClick={downloadAllImages}>
                  <FileArchive className="h-4 w-4 mr-2" />
                  Descargar ZIP
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            <Accordion type="multiple" defaultValue={["base-docs"]} className="w-full">
              {/* Base Documentation */}
              {baseDocImages.length > 0 && (
                <AccordionItem value="base-docs" className="border rounded-lg mb-2">
                  <AccordionTrigger className="px-4 py-3 hover:no-underline">
                    <div className="flex items-center justify-between w-full pr-4">
                      <span className="font-medium">Documentacion Base</span>
                      <span className="text-sm text-muted-foreground">
                        {baseDocImages.length} foto{baseDocImages.length !== 1 ? "s" : ""}
                      </span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="px-4 pb-4">
                    <div className="space-y-3">
                      <p className="text-sm text-muted-foreground">
                        Ficha tecnica, permiso de circulacion y vistas del vehiculo
                      </p>
                      <div className="grid grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
                        {baseDocImages.map((image) => (
                          <ImageThumbnail key={image.id} image={image} />
                        ))}
                      </div>
                    </div>
                  </AccordionContent>
                </AccordionItem>
              )}

              {/* Elements */}
              {caseData.element_codes.map((code) => {
                const elementData = elementDataList.find((ed) => ed.element_code === code);
                const elementImages = caseData.images?.filter(
                  (img) => img.element_code === code
                ) || [];

                return (
                  <AccordionItem key={code} value={code} className="border rounded-lg mb-2 last:mb-0">
                    <AccordionTrigger className="px-4 py-3 hover:no-underline">
                      <div className="flex items-center justify-between w-full pr-4">
                        <div className="flex items-center gap-2 flex-wrap">
                          <Badge variant="outline" className="font-mono text-base">
                            {code}
                          </Badge>
                          {elementData ? (
                            <Badge
                              variant={
                                elementData.status === "completed"
                                  ? "default"
                                  : elementData.status === "pending_data"
                                  ? "secondary"
                                  : "outline"
                              }
                              className={
                                elementData.status === "completed"
                                  ? "bg-green-600"
                                  : elementData.status === "pending_data"
                                  ? "bg-yellow-100 text-yellow-800"
                                  : "border-orange-400 text-orange-600"
                              }
                            >
                              {elementData.status === "completed"
                                ? "Completado"
                                : elementData.status === "pending_data"
                                ? "Faltan datos"
                                : "Faltan fotos"}
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="border-gray-300 text-gray-500">
                              Sin datos
                            </Badge>
                          )}
                        </div>
                        <span className="text-sm text-muted-foreground">
                          {elementImages.length} foto{elementImages.length !== 1 ? "s" : ""}
                        </span>
                      </div>
                    </AccordionTrigger>
                    <AccordionContent className="px-4 pb-4">
                      <div className="space-y-4">
                        {/* Element Photos */}
                        {elementImages.length > 0 ? (
                          <div>
                            <p className="text-sm font-medium text-muted-foreground mb-3">
                              Fotos del elemento
                            </p>
                            <div className="grid grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
                              {elementImages.map((img) => (
                                <ImageThumbnail key={img.id} image={img} />
                              ))}
                            </div>
                          </div>
                        ) : (
                          <div className="text-center py-6 text-muted-foreground bg-muted/30 rounded-lg">
                            Sin fotos recibidas
                          </div>
                        )}

                        {/* Collected Data */}
                        {elementData?.field_values && Object.keys(elementData.field_values).length > 0 ? (
                          <div>
                            <p className="text-sm font-medium text-muted-foreground mb-3">
                              Datos recopilados
                            </p>
                            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                              {Object.entries(elementData.field_values).map(([key, value]) => (
                                <div key={key} className="text-sm bg-muted/50 rounded px-3 py-2">
                                  <span className="text-muted-foreground">{key}:</span>{" "}
                                  <span className="font-medium">{String(value)}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : elementImages.length > 0 ? (
                          <div className="text-sm text-muted-foreground">
                            Sin datos recopilados
                          </div>
                        ) : null}
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                );
              })}
            </Accordion>
          </CardContent>
        </Card>
      )}

      {/* Notes */}
      {caseData.notes && (
        <Card>
          <CardHeader>
            <CardTitle>Notas</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="whitespace-pre-wrap text-sm font-sans">
              {caseData.notes}
            </pre>
          </CardContent>
        </Card>
      )}

      {/* Image Preview Dialog */}
      <Dialog open={isImageDialogOpen} onOpenChange={setIsImageDialogOpen}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>{selectedImage?.display_name}</DialogTitle>
          </DialogHeader>
          {selectedImage && (
            <div className="space-y-4">
              <div className="relative aspect-video bg-muted rounded-lg overflow-hidden">
                <Image
                  src={selectedImage.url}
                  alt={selectedImage.display_name}
                  fill
                  className="object-contain"
                  sizes="(max-width: 1200px) 100vw, 1200px"
                />
              </div>
              <div className="flex items-center justify-between">
                <div className="space-y-1">
                  {selectedImage.element_code && (
                    <p className="text-sm">
                      <span className="text-muted-foreground">Elemento:</span>{" "}
                      {selectedImage.element_code}
                    </p>
                  )}
                  {selectedImage.description && (
                    <p className="text-sm">
                      <span className="text-muted-foreground">Descripcion:</span>{" "}
                      {selectedImage.description}
                    </p>
                  )}
                  <p className="text-sm text-muted-foreground">
                    {selectedImage.mime_type} - {selectedImage.file_size ? `${Math.round(selectedImage.file_size / 1024)} KB` : ""}
                  </p>
                </div>
                <Button onClick={() => downloadImage(selectedImage)}>
                  <Download className="h-4 w-4 mr-2" />
                  Descargar
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Resolve Confirmation Dialog */}
      <AlertDialog open={isResolveDialogOpen} onOpenChange={setIsResolveDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Resolver Expediente</AlertDialogTitle>
            <AlertDialogDescription>
              Marcar este expediente como resuelto indica que el cliente ha sido
              atendido satisfactoriamente. El bot sera reactivado en la
              conversacion de WhatsApp.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isActionLoading}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleResolveCase}
              disabled={isActionLoading}
              className="bg-green-600 hover:bg-green-700"
            >
              {isActionLoading ? "Resolviendo..." : "Marcar como Resuelto"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
