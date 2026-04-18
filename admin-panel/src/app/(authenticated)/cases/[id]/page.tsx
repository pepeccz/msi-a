"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import Image from "next/image";
import dynamic from "next/dynamic";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
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
  ChevronLeft,
  ChevronRight,
  Images,
} from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import api from "@/lib/api";
import type {
  Case,
  CaseStatus,
  CaseImage,
  CaseElementData,
} from "@/lib/types";

// PDF viewer loaded lazily — keeps the initial bundle free of the ~800 KB worker
const PdfViewer = dynamic(
  () => import("@/components/pdf-viewer").then((m) => m.PdfViewer),
  {
    ssr: false,
    loading: () => <Skeleton className="w-full h-[60vh] sm:h-[65vh]" />,
  },
);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(dateString: string | null) {
  if (!dateString) return "—";
  return new Date(dateString).toLocaleString("es-ES", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDateShort(dateString: string | null) {
  if (!dateString) return "—";
  return new Date(dateString).toLocaleString("es-ES", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

const STATUS_CONFIG: Record<
  CaseStatus,
  { label: string; className: string; icon: React.ElementType }
> = {
  collecting: {
    label: "Recolectando",
    className: "border-blue-500 text-blue-600",
    icon: Clock,
  },
  pending_images: {
    label: "Faltan Imágenes",
    className: "border-orange-500 text-orange-600",
    icon: ImageIcon,
  },
  pending_review: {
    label: "Pendiente",
    className: "bg-red-600 text-white border-red-600",
    icon: Inbox,
  },
  in_progress: {
    label: "En Progreso",
    className: "bg-yellow-600 text-white border-yellow-600",
    icon: Play,
  },
  resolved: {
    label: "Resuelto",
    className: "bg-green-600 text-white border-green-600",
    icon: CheckCircle2,
  },
  cancelled: {
    label: "Cancelado",
    className: "border-gray-500 text-gray-600",
    icon: Ban,
  },
  abandoned: {
    label: "Abandonado",
    className: "border-gray-400 text-gray-500",
    icon: AlertTriangle,
  },
};

function StatusBadge({ status }: { status: CaseStatus }) {
  const config = STATUS_CONFIG[status];
  if (!config) return <Badge variant="outline">{status}</Badge>;
  const Icon = config.icon;
  return (
    <Badge variant="outline" className={config.className}>
      <Icon className="h-3 w-3 mr-1" />
      {config.label}
    </Badge>
  );
}

const STEP_CONFIG: Record<string, { label: string; color: string }> = {
  collect_images: {
    label: "Recibiendo Imágenes",
    color: "border-blue-500 text-blue-600",
  },
  collect_personal: {
    label: "Datos Personales",
    color: "border-indigo-500 text-indigo-600",
  },
  collect_vehicle: {
    label: "Datos Vehículo",
    color: "border-cyan-500 text-cyan-600",
  },
  collect_workshop: {
    label: "Datos Taller",
    color: "border-violet-500 text-violet-600",
  },
  review_summary: {
    label: "Revisión Final",
    color: "border-amber-500 text-amber-600",
  },
  completed: {
    label: "Completado",
    color: "border-green-500 text-green-600",
  },
};

function CollectionStepBadge({ step }: { step: string | null | undefined }) {
  if (!step) return null;
  const config = STEP_CONFIG[step];
  if (!config) return null;
  return (
    <Badge variant="outline" className={config.color}>
      {config.label}
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// Data field component — only renders when value is truthy
// ---------------------------------------------------------------------------

function DataField({
  label,
  value,
  icon: Icon,
  mono,
  className,
}: {
  label: string;
  value: string | number | null | undefined;
  icon?: React.ElementType;
  mono?: boolean;
  className?: string;
}) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className={className}>
      <p className="text-xs text-muted-foreground">{label}</p>
      <div className="flex items-center gap-1.5 mt-0.5">
        {Icon && <Icon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />}
        <p className={`text-sm font-medium truncate ${mono ? "font-mono" : ""}`}>
          {value}
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isPdf(image: CaseImage): boolean {
  return image.mime_type === "application/pdf";
}

// ---------------------------------------------------------------------------
// Image thumbnail
// ---------------------------------------------------------------------------

function ImageThumbnail({
  image,
  onClick,
}: {
  image: CaseImage;
  onClick: () => void;
}) {
  return (
    <div
      className="relative aspect-square rounded-lg border overflow-hidden cursor-pointer group"
      onClick={onClick}
    >
      {isPdf(image) ? (
        <div className="absolute inset-0 bg-muted flex flex-col items-center justify-center gap-1.5 px-2">
          <FileText className="h-10 w-10 text-muted-foreground shrink-0" />
          <p className="text-[10px] text-muted-foreground text-center truncate w-full leading-tight">
            {image.display_name}
          </p>
        </div>
      ) : (
        <Image
          src={image.url}
          alt={image.display_name}
          fill
          className="object-cover"
          sizes="(max-width: 640px) 33vw, (max-width: 1024px) 25vw, 150px"
        />
      )}
      <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
        <ZoomIn className="h-6 w-6 text-white" />
      </div>
      {image.is_valid === true && (
        <div className="absolute top-1 right-1 bg-green-500 p-0.5 rounded-full">
          <Check className="h-3 w-3 text-white" />
        </div>
      )}
      {image.is_valid === false && (
        <div className="absolute top-1 right-1 bg-red-500 p-0.5 rounded-full">
          <X className="h-3 w-3 text-white" />
        </div>
      )}
      {!isPdf(image) && (
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent px-1.5 py-1">
          <p className="text-[10px] text-white truncate leading-tight">
            {image.display_name}
          </p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Lightbox — full-screen image viewer with prev/next
// ---------------------------------------------------------------------------

function ImageLightbox({
  images,
  initialIndex,
  open,
  onOpenChange,
  onDownload,
}: {
  images: CaseImage[];
  initialIndex: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDownload: (image: CaseImage) => void;
}) {
  const [currentIndex, setCurrentIndex] = useState(initialIndex);
  const containerRef = useRef<HTMLDivElement>(null);

  // Reset index when opening with a new image
  useEffect(() => {
    if (open) setCurrentIndex(initialIndex);
  }, [open, initialIndex]);

  // Focus container for keyboard events
  useEffect(() => {
    if (open && containerRef.current) {
      containerRef.current.focus();
    }
  }, [open, currentIndex]);

  const current = images[currentIndex];
  if (!current) return null;

  const hasPrev = currentIndex > 0;
  const hasNext = currentIndex < images.length - 1;

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowLeft" && hasPrev) setCurrentIndex((i) => i - 1);
    if (e.key === "ArrowRight" && hasNext) setCurrentIndex((i) => i + 1);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl max-h-[90vh] p-0 gap-0 overflow-hidden">
        <div
          ref={containerRef}
          tabIndex={0}
          onKeyDown={handleKeyDown}
          className="outline-none flex flex-col h-full"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b">
            <DialogHeader className="flex-1 min-w-0">
              <DialogTitle className="text-sm font-medium truncate pr-4">
                {current.display_name}
              </DialogTitle>
            </DialogHeader>
            <div className="flex items-center gap-2 shrink-0">
              <span className="text-xs text-muted-foreground tabular-nums">
                {currentIndex + 1} / {images.length}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => onDownload(current)}
              >
                <Download className="h-3.5 w-3.5 mr-1.5" />
                Descargar
              </Button>
            </div>
          </div>

          {/* Image/PDF area with navigation */}
          <div className="relative flex-1 min-h-0 bg-black/5 dark:bg-black/20 flex items-center justify-center">
            {/* Prev button */}
            {hasPrev && (
              <button
                onClick={() => setCurrentIndex((i) => i - 1)}
                className="absolute left-2 z-10 p-2 rounded-full bg-black/40 hover:bg-black/60 text-white transition-colors"
                aria-label="Imagen anterior"
              >
                <ChevronLeft className="h-5 w-5" />
              </button>
            )}

            {/* Image or PDF viewer */}
            {isPdf(current) ? (
              <PdfViewer
                key={current.id}
                url={current.url}
                fileName={current.display_name}
                className="w-full h-[60vh] sm:h-[65vh]"
              />
            ) : (
              <div className="relative w-full h-[60vh] sm:h-[65vh]">
                <Image
                  key={current.id}
                  src={current.url}
                  alt={current.display_name}
                  fill
                  className="object-contain"
                  sizes="(max-width: 1200px) 100vw, 1200px"
                  priority
                />
              </div>
            )}

            {/* Next button */}
            {hasNext && (
              <button
                onClick={() => setCurrentIndex((i) => i + 1)}
                className="absolute right-2 z-10 p-2 rounded-full bg-black/40 hover:bg-black/60 text-white transition-colors"
                aria-label="Siguiente imagen"
              >
                <ChevronRight className="h-5 w-5" />
              </button>
            )}
          </div>

          {/* Footer metadata */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2.5 border-t text-xs text-muted-foreground">
            {current.element_code && (
              <span>
                Elemento: <strong className="text-foreground">{current.element_code}</strong>
              </span>
            )}
            {current.description && (
              <span>
                Descripción: <strong className="text-foreground">{current.description}</strong>
              </span>
            )}
            {current.mime_type && <span>{current.mime_type}</span>}
            {current.file_size && (
              <span>{Math.round(current.file_size / 1024)} KB</span>
            )}
            {current.is_valid === true && (
              <Badge variant="outline" className="text-green-600 border-green-500 text-[10px] h-5">
                <Check className="h-2.5 w-2.5 mr-0.5" /> Válida
              </Badge>
            )}
            {current.is_valid === false && (
              <Badge variant="outline" className="text-red-600 border-red-500 text-[10px] h-5">
                <X className="h-2.5 w-2.5 mr-0.5" /> Inválida
              </Badge>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function CaseDetailPage() {
  const params = useParams();
  const router = useRouter();
  const caseId = params.id as string;

  const [caseData, setCaseData] = useState<Case | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [isResolveDialogOpen, setIsResolveDialogOpen] = useState(false);
  const [elementDataList, setElementDataList] = useState<CaseElementData[]>([]);

  // Lightbox state
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [lightboxIndex, setLightboxIndex] = useState(0);
  const [lightboxImages, setLightboxImages] = useState<CaseImage[]>([]);

  const fetchCase = useCallback(async () => {
    try {
      setIsLoading(true);
      const data = await api.getCase(caseId);
      setCaseData(data);

      try {
        const elementDataResponse = await api.getCaseElementDataList(caseId);
        setElementDataList(elementDataResponse.elements);
      } catch {
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

  // ---- Actions ----

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
    const chatwootBaseUrl =
      process.env.NEXT_PUBLIC_CHATWOOT_URL || "https://app.chatwoot.com";
    const chatwootAccountId =
      process.env.NEXT_PUBLIC_CHATWOOT_ACCOUNT_ID || "1";
    window.open(
      `${chatwootBaseUrl}/app/accounts/${chatwootAccountId}/conversations/${caseData.conversation_id}`,
      "_blank"
    );
  };

  // ---- Image helpers ----

  const openLightbox = (images: CaseImage[], index: number) => {
    setLightboxImages(images);
    setLightboxIndex(index);
    setLightboxOpen(true);
  };

  const downloadImage = async (image: CaseImage) => {
    try {
      const url = api.getCaseImageDownloadUrl(caseId, image.id);
      const blob = await api.downloadFile(url);
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = image.display_name || image.id;
      a.click();
      URL.revokeObjectURL(objectUrl);
    } catch (error) {
      console.error("Error downloading image:", error);
    }
  };

  const downloadAllImages = async () => {
    try {
      const url = api.getCaseImagesZipUrl(caseId);
      const blob = await api.downloadFile(url);
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = `caso-${caseId}-imagenes.zip`;
      a.click();
      URL.revokeObjectURL(objectUrl);
    } catch (error) {
      console.error("Error downloading images:", error);
    }
  };

  // ---- Loading / Not found ----

  if (isLoading) {
    return (
      <div className="p-6 flex items-center justify-center min-h-[50vh]">
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

  // ---- Derived data ----

  const allImages = caseData.images || [];
  const baseDocImages = allImages.filter((img) => !img.element_code);
  const totalImageCount = allImages.length;

  // Build address string
  const address = [
    caseData.user_domicilio_calle,
    [
      caseData.user_domicilio_cp,
      caseData.user_domicilio_localidad,
      caseData.user_domicilio_provincia,
    ]
      .filter(Boolean)
      .join(", "),
  ]
    .filter(Boolean)
    .join(" — ");

  // Dimensional changes
  const dimensionalChanges: { label: string; value: string }[] = [];
  if (caseData.cambio_plazas)
    dimensionalChanges.push({
      label: "Plazas",
      value: `${caseData.plazas_iniciales} → ${caseData.plazas_finales}`,
    });
  if (caseData.cambio_altura)
    dimensionalChanges.push({
      label: "Altura",
      value: `${caseData.altura_final} mm`,
    });
  if (caseData.cambio_ancho)
    dimensionalChanges.push({
      label: "Ancho",
      value: `${caseData.ancho_final} mm`,
    });
  if (caseData.cambio_longitud)
    dimensionalChanges.push({
      label: "Longitud",
      value: `${caseData.longitud_final} mm`,
    });

  // Group images by element for the "all images" tab
  // Include element groups even without images if they have data
  const imageGroups: {
    label: string;
    code: string | null;
    images: CaseImage[];
    elementData?: CaseElementData;
  }[] = [];
  if (baseDocImages.length > 0) {
    imageGroups.push({
      label: "Documentación Base",
      code: null,
      images: baseDocImages,
    });
  }
  for (const code of caseData.element_codes) {
    const imgs = allImages.filter((img) => img.element_code === code);
    const elData = elementDataList.find((ed) => ed.element_code === code);
    // Show tab if there are images OR element data
    if (imgs.length > 0 || elData) {
      imageGroups.push({ label: code, code, images: imgs, elementData: elData });
    }
  }

  return (
    <TooltipProvider>
      <div className="p-4 sm:p-6 space-y-4 sm:space-y-5 max-w-7xl mx-auto">
        {/* ================================================================
            HEADER — compact, all key info in one strip
            ================================================================ */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3">
            <Button
              variant="ghost"
              size="sm"
              className="mt-0.5 shrink-0"
              onClick={() => router.back()}
            >
              <ArrowLeft className="h-4 w-4 mr-1" />
              <span className="hidden sm:inline">Volver</span>
            </Button>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-xl sm:text-2xl font-bold tracking-tight">
                  Expediente #{caseData.conversation_id}
                </h1>
                <StatusBadge status={caseData.status} />
                {caseData.status === "collecting" && caseData.current_step && (
                  <CollectionStepBadge step={caseData.current_step} />
                )}
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-1 text-xs text-muted-foreground">
                <span>Creado {formatDateShort(caseData.created_at)}</span>
                {caseData.category_name && (
                  <>
                    <span className="hidden sm:inline">·</span>
                    <span className="font-medium text-foreground">
                      {caseData.category_name}
                    </span>
                  </>
                )}
                {caseData.tariff_amount != null && (
                  <>
                    <span className="hidden sm:inline">·</span>
                    <span className="font-semibold text-foreground">
                      {caseData.tariff_amount.toFixed(2)} EUR
                    </span>
                  </>
                )}
                {totalImageCount > 0 && (
                  <>
                    <span className="hidden sm:inline">·</span>
                    <span>{totalImageCount} imagen{totalImageCount !== 1 ? "es" : ""}</span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {caseData.status === "pending_review" && (
              <Button
                size="sm"
                onClick={handleTakeCase}
                disabled={isActionLoading}
              >
                <Play className="h-3.5 w-3.5 mr-1.5" />
                Tomar
              </Button>
            )}
            {caseData.status === "in_progress" && (
              <Button
                size="sm"
                className="bg-green-600 hover:bg-green-700"
                onClick={() => setIsResolveDialogOpen(true)}
                disabled={isActionLoading}
              >
                <CheckCircle2 className="h-3.5 w-3.5 mr-1.5" />
                Resolver
              </Button>
            )}
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="outline" size="sm" onClick={openChatwoot}>
                  <ExternalLink className="h-4 w-4" />
                  <span className="ml-1.5 hidden sm:inline">Chatwoot</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent>Abrir conversación en Chatwoot</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="outline" size="icon" className="h-8 w-8" onClick={fetchCase}>
                  <RefreshCw className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Actualizar</TooltipContent>
            </Tooltip>
          </div>
        </div>

        {/* ================================================================
            IMAGES SECTION — prominent, with tabs for grouped / all view
            ================================================================ */}
        {imageGroups.length > 0 && (
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Images className="h-5 w-5" />
                  Imágenes y Elementos
                  {totalImageCount > 0 && (
                    <Badge variant="secondary" className="ml-1 text-xs">
                      {totalImageCount} foto{totalImageCount !== 1 ? "s" : ""}
                    </Badge>
                  )}
                </CardTitle>
                {totalImageCount > 0 && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={downloadAllImages}
                  >
                    <FileArchive className="h-3.5 w-3.5 mr-1.5" />
                    <span className="hidden sm:inline">Descargar</span> ZIP
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              {imageGroups.length === 1 && !imageGroups[0].elementData ? (
                // Single group with no element data — no tabs needed
                <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8 gap-2 sm:gap-3">
                  {imageGroups[0].images.map((img, i) => (
                    <ImageThumbnail
                      key={img.id}
                      image={img}
                      onClick={() => openLightbox(allImages, allImages.indexOf(img))}
                    />
                  ))}
                </div>
              ) : (
                // Multiple groups or element data present — use tabs
                <Tabs defaultValue="all" className="w-full">
                  <TabsList className="w-full justify-start overflow-x-auto h-auto flex-wrap gap-1 bg-transparent p-0 mb-3">
                    {totalImageCount > 0 && (
                      <TabsTrigger
                        value="all"
                        className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground text-xs h-7"
                      >
                        Todas ({totalImageCount})
                      </TabsTrigger>
                    )}
                    {imageGroups.map((group) => (
                      <TabsTrigger
                        key={group.code ?? "base"}
                        value={group.code ?? "base"}
                        className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground text-xs h-7"
                      >
                        <span className="flex items-center gap-1.5">
                          {group.label}
                          {group.images.length > 0 && (
                            <span className="text-[10px] opacity-70">
                              ({group.images.length})
                            </span>
                          )}
                          {group.code === null ? (
                            <span
                              className={`inline-block w-1.5 h-1.5 rounded-full ${
                                group.images.length > 0
                                  ? "bg-green-500"
                                  : "bg-orange-500"
                              }`}
                            />
                          ) : group.elementData ? (
                            <span
                              className={`inline-block w-1.5 h-1.5 rounded-full ${
                                group.elementData.status === "completed"
                                  ? "bg-green-500"
                                  : group.elementData.status === "pending_data"
                                    ? "bg-yellow-500"
                                    : "bg-orange-500"
                              }`}
                            />
                          ) : null}
                        </span>
                      </TabsTrigger>
                    ))}
                  </TabsList>

                  {/* All images tab */}
                  <TabsContent value="all">
                    <div className="space-y-5">
                      {/* All photos grid */}
                      {totalImageCount > 0 && (
                        <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8 gap-2 sm:gap-3">
                          {allImages.map((img, i) => (
                            <ImageThumbnail
                              key={img.id}
                              image={img}
                              onClick={() => openLightbox(allImages, i)}
                            />
                          ))}
                        </div>
                      )}

                      {/* Element data summary for all elements */}
                      {elementDataList.length > 0 && (
                        <div className="space-y-3">
                          <Separator />
                          <p className="text-xs font-medium text-muted-foreground">
                            Datos recopilados por elemento
                          </p>
                          <div className="grid gap-3 sm:grid-cols-2">
                            {elementDataList.map((ed) => (
                              <div
                                key={ed.element_code}
                                className="rounded-lg border p-3 space-y-2"
                              >
                                <div className="flex items-center gap-2">
                                  <Badge variant="outline" className="font-mono text-xs">
                                    {ed.element_code}
                                  </Badge>
                                  <Badge
                                    variant={ed.status === "completed" ? "default" : "secondary"}
                                    className={
                                      ed.status === "completed"
                                        ? "bg-green-600 text-xs"
                                        : ed.status === "pending_data"
                                          ? "bg-yellow-100 text-yellow-800 text-xs"
                                          : "border-orange-400 text-orange-600 text-xs"
                                    }
                                  >
                                    {ed.status === "completed"
                                      ? "Completado"
                                      : ed.status === "pending_data"
                                        ? "Faltan datos"
                                        : "Faltan fotos"}
                                  </Badge>
                                </div>
                                {ed.field_values &&
                                  Object.keys(ed.field_values).length > 0 && (
                                    <div className="grid grid-cols-2 gap-1">
                                      {Object.entries(ed.field_values).map(
                                        ([key, value]) => (
                                          <div
                                            key={key}
                                            className="text-xs bg-muted/50 rounded px-2 py-1"
                                          >
                                            <span className="text-muted-foreground">
                                              {key}:
                                            </span>{" "}
                                            <span className="font-medium">
                                              {String(value)}
                                            </span>
                                          </div>
                                        )
                                      )}
                                    </div>
                                  )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </TabsContent>

                  {/* Per-group tabs */}
                  {imageGroups.map((group) => (
                    <TabsContent key={group.code ?? "base"} value={group.code ?? "base"}>
                      <div className="space-y-4">
                        {/* Element status + data */}
                        {group.elementData && (
                          <div className="space-y-3">
                            <div className="flex items-center gap-2">
                              <Badge
                                variant={
                                  group.elementData.status === "completed"
                                    ? "default"
                                    : "secondary"
                                }
                                className={
                                  group.elementData.status === "completed"
                                    ? "bg-green-600 text-xs"
                                    : group.elementData.status === "pending_data"
                                      ? "bg-yellow-100 text-yellow-800 text-xs"
                                      : "border-orange-400 text-orange-600 text-xs"
                                }
                              >
                                {group.elementData.status === "completed"
                                  ? "Completado"
                                  : group.elementData.status === "pending_data"
                                    ? "Faltan datos"
                                    : "Faltan fotos"}
                              </Badge>
                            </div>

                            {group.elementData.field_values &&
                              Object.keys(group.elementData.field_values).length > 0 && (
                                <div>
                                  <p className="text-xs font-medium text-muted-foreground mb-2">
                                    Datos recopilados
                                  </p>
                                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-1.5">
                                    {Object.entries(group.elementData.field_values).map(
                                      ([key, value]) => (
                                        <div
                                          key={key}
                                          className="text-xs bg-muted/50 rounded px-2.5 py-1.5"
                                        >
                                          <span className="text-muted-foreground">
                                            {key}:
                                          </span>{" "}
                                          <span className="font-medium">
                                            {String(value)}
                                          </span>
                                        </div>
                                      )
                                    )}
                                  </div>
                                </div>
                              )}
                          </div>
                        )}

                        {/* Photos */}
                        {group.images.length > 0 ? (
                          <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8 gap-2 sm:gap-3">
                            {group.images.map((img) => (
                              <ImageThumbnail
                                key={img.id}
                                image={img}
                                onClick={() =>
                                  openLightbox(
                                    group.images,
                                    group.images.indexOf(img)
                                  )
                                }
                              />
                            ))}
                          </div>
                        ) : group.elementData ? (
                          <div className="text-center py-4 text-xs text-muted-foreground bg-muted/30 rounded-lg">
                            Sin fotos recibidas para este elemento
                          </div>
                        ) : null}
                      </div>
                    </TabsContent>
                  ))}
                </Tabs>
              )}
            </CardContent>
          </Card>
        )}

        {/* ================================================================
            DATA SECTIONS — compact property grid, 2 cols on desktop
            ================================================================ */}
        <div className="grid gap-4 md:grid-cols-2">
          {/* ---- Personal Data ---- */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <User className="h-4 w-4" />
                Datos Personales
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 pt-0">
              <div className="grid grid-cols-2 gap-x-4 gap-y-2">
                <DataField label="Nombre" value={caseData.user_first_name} />
                <DataField label="Apellidos" value={caseData.user_last_name} />
              </div>
              <DataField label="NIF/CIF" value={caseData.user_nif_cif} icon={IdCard} mono />
              <DataField label="Email" value={caseData.user_email} icon={Mail} />
              <DataField
                label="Teléfono"
                value={
                  caseData.user_phone
                    ? `${caseData.user_phone} (WhatsApp)`
                    : null
                }
                icon={Phone}
              />
              {address && (
                <DataField label="Dirección" value={address} icon={MapPin} />
              )}

              {/* Show placeholder if no personal data at all */}
              {!caseData.user_first_name &&
                !caseData.user_last_name &&
                !caseData.user_nif_cif &&
                !caseData.user_email &&
                !caseData.user_phone && (
                  <p className="text-xs text-muted-foreground italic py-2">
                    Sin datos personales recopilados
                  </p>
                )}
            </CardContent>
          </Card>

          {/* ---- Vehicle Data ---- */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <Car className="h-4 w-4" />
                Datos del Vehículo
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 pt-0">
              <div className="grid grid-cols-2 gap-x-4 gap-y-2">
                <DataField label="Marca" value={caseData.vehiculo_marca} />
                <DataField label="Modelo" value={caseData.vehiculo_modelo} />
                <DataField label="Año" value={caseData.vehiculo_anio} />
                <DataField label="Matrícula" value={caseData.vehiculo_matricula} />
              </div>
              <DataField
                label="Bastidor (VIN)"
                value={caseData.vehiculo_bastidor}
                mono
              />

              {/* Dimensional changes */}
              {dimensionalChanges.length > 0 && (
                <div className="pt-1">
                  <p className="text-xs text-muted-foreground flex items-center gap-1 mb-1.5">
                    <Ruler className="h-3 w-3" />
                    Cambios Dimensionales
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {dimensionalChanges.map((dc) => (
                      <Badge key={dc.label} variant="outline" className="text-xs font-normal">
                        {dc.label}: <strong className="ml-1">{dc.value}</strong>
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* Show placeholder if no vehicle data at all */}
              {!caseData.vehiculo_marca &&
                !caseData.vehiculo_modelo &&
                !caseData.vehiculo_anio &&
                !caseData.vehiculo_matricula &&
                !caseData.vehiculo_bastidor &&
                dimensionalChanges.length === 0 && (
                  <p className="text-xs text-muted-foreground italic py-2">
                    Sin datos del vehículo recopilados
                  </p>
                )}
            </CardContent>
          </Card>

          {/* ---- Homologación + Estado (merged into one compact card) ---- */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <FileText className="h-4 w-4" />
                Homologación
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 pt-0">
              <DataField label="Categoría" value={caseData.category_name} />
              <DataField label="ITV" value={caseData.itv_nombre} />
              {caseData.tariff_amount != null && (
                <div>
                  <p className="text-xs text-muted-foreground">Tarifa Calculada</p>
                  <p className="text-lg font-bold mt-0.5">
                    {caseData.tariff_amount.toFixed(2)} EUR
                  </p>
                </div>
              )}
              {!caseData.category_name && !caseData.itv_nombre && caseData.tariff_amount == null && (
                <p className="text-xs text-muted-foreground italic py-2">
                  Sin datos de homologación
                </p>
              )}
            </CardContent>
          </Card>

          {/* ---- Estado y Fechas ---- */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <Clock className="h-4 w-4" />
                Estado y Fechas
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 pt-0">
              <DataField label="Resuelto por" value={caseData.resolved_by} />
              <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
                <div>
                  <p className="text-muted-foreground">Creado</p>
                  <p className="font-medium">{formatDate(caseData.created_at)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Actualizado</p>
                  <p className="font-medium">{formatDate(caseData.updated_at)}</p>
                </div>
                {caseData.completed_at && (
                  <div>
                    <p className="text-muted-foreground">Completado</p>
                    <p className="font-medium">{formatDate(caseData.completed_at)}</p>
                  </div>
                )}
                {caseData.resolved_at && (
                  <div>
                    <p className="text-muted-foreground">Resuelto</p>
                    <p className="font-medium">{formatDate(caseData.resolved_at)}</p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* ================================================================
            WORKSHOP / CERTIFICATE
            ================================================================ */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <Wrench className="h-4 w-4" />
              Certificado de Taller
            </CardTitle>
            <CardDescription className="text-xs">
              {caseData.taller_propio === true
                ? "El cliente aporta certificado de taller propio"
                : caseData.taller_propio === false
                  ? "MSI aporta el certificado de taller"
                  : "Pendiente de definir"}
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-0">
            {caseData.taller_propio === true ? (
              <div className="grid gap-x-4 gap-y-2 grid-cols-2 lg:grid-cols-3">
                <DataField label="Nombre del Taller" value={caseData.taller_nombre} />
                <DataField label="Responsable" value={caseData.taller_responsable} />
                <DataField label="Teléfono" value={caseData.taller_telefono} icon={Phone} />
                <DataField
                  label="Dirección"
                  value={
                    [
                      caseData.taller_domicilio,
                      [caseData.taller_ciudad, caseData.taller_provincia]
                        .filter(Boolean)
                        .join(", "),
                    ]
                      .filter(Boolean)
                      .join(" — ") || null
                  }
                  className="col-span-2"
                />
                <DataField
                  label="Registro Industrial"
                  value={caseData.taller_registro_industrial}
                  mono
                />
                {caseData.taller_actividad && (
                  <DataField
                    label="Actividad"
                    value={caseData.taller_actividad}
                    className="col-span-full"
                  />
                )}
              </div>
            ) : caseData.taller_propio === false ? (
              <div className="flex items-center gap-3 p-3 bg-blue-50 dark:bg-blue-950 rounded-lg">
                <Building2 className="h-5 w-5 text-blue-600 shrink-0" />
                <div className="text-sm">
                  <p className="font-medium text-blue-700 dark:text-blue-400">
                    MSI aporta certificado de taller
                  </p>
                  <p className="text-xs text-blue-600 dark:text-blue-500">
                    +85 EUR +IVA incluido en el presupuesto
                  </p>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                <Clock className="h-5 w-5 text-muted-foreground shrink-0" />
                <div className="text-sm">
                  <p className="font-medium text-muted-foreground">
                    Pendiente de definir
                  </p>
                  <p className="text-xs text-muted-foreground">
                    El cliente aún no ha indicado si aporta taller propio
                  </p>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* ================================================================
            NOTES
            ================================================================ */}
        {caseData.notes && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Notas</CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <p className="whitespace-pre-wrap text-sm">
                {caseData.notes}
              </p>
            </CardContent>
          </Card>
        )}

        {/* ================================================================
            LIGHTBOX
            ================================================================ */}
        <ImageLightbox
          images={lightboxImages}
          initialIndex={lightboxIndex}
          open={lightboxOpen}
          onOpenChange={setLightboxOpen}
          onDownload={downloadImage}
        />

        {/* ================================================================
            RESOLVE CONFIRMATION
            ================================================================ */}
        <AlertDialog
          open={isResolveDialogOpen}
          onOpenChange={setIsResolveDialogOpen}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Resolver Expediente</AlertDialogTitle>
              <AlertDialogDescription>
                Marcar este expediente como resuelto indica que el cliente ha sido
                atendido satisfactoriamente. El bot será reactivado en la
                conversación de WhatsApp.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={isActionLoading}>
                Cancelar
              </AlertDialogCancel>
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
    </TooltipProvider>
  );
}
