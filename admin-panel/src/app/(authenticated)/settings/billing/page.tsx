"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import type {
  CurrentEstimate,
  Invoice,
  InvoiceListResponse,
  StripeStatus,
  FiscalDetails,
} from "@/lib/types";
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
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { useAuth } from "@/contexts/auth-context";
import { sileo } from "sileo";
import {
  Shield,
  FileText,
  Download,
  Ban,
  CreditCard,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Building2,
  User,
} from "lucide-react";

// -------------------------------------------------------
// Helpers
// -------------------------------------------------------

const MONTH_NAMES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

function formatEur(num: number): string {
  return new Intl.NumberFormat("es-ES", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num) + " €";
}

function formatNumber(num: number): string {
  return new Intl.NumberFormat("es-ES").format(num);
}

function formatPeriod(month: number, year: number): string {
  return `${MONTH_NAMES[month - 1]} ${year}`;
}

// -------------------------------------------------------
// Invoice status badge
// -------------------------------------------------------

type InvoiceStatus = "issued" | "paid" | "overdue" | "void" | "draft";

const INVOICE_STATUS_CONFIG: Record<
  InvoiceStatus,
  { label: string; variant: "default" | "secondary" | "destructive" | "outline" }
> = {
  issued: { label: "Emitida", variant: "default" },
  paid: { label: "Pagada", variant: "secondary" },
  overdue: { label: "Vencida", variant: "destructive" },
  void: { label: "Anulada", variant: "secondary" },
  draft: { label: "Borrador", variant: "outline" },
};

function InvoiceStatusBadge({ status }: { status: string }) {
  const cfg = INVOICE_STATUS_CONFIG[status as InvoiceStatus] ?? {
    label: status,
    variant: "outline" as const,
  };
  const extraClass =
    status === "paid"
      ? "bg-green-100 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-400"
      : status === "issued"
      ? "bg-blue-100 text-blue-800 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400"
      : "";

  return (
    <Badge variant={cfg.variant} className={extraClass}>
      {cfg.label}
    </Badge>
  );
}

// -------------------------------------------------------
// Section 1 — Current Month Summary
// -------------------------------------------------------

function CurrentMonthSummary({
  estimate,
  loading,
  error,
}: {
  estimate: CurrentEstimate | null;
  loading: boolean;
  error: string | null;
}) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[...Array(3)].map((_, i) => (
          <Card key={i}>
            <CardHeader className="pb-2">
              <Skeleton className="h-4 w-28" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-24 mb-2" />
              <Skeleton className="h-3 w-40" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-6 text-center text-destructive text-sm">
          {error}
        </CardContent>
      </Card>
    );
  }

  return (
    <div>
      <h2 className="text-lg font-semibold mb-4">Estimación del mes actual</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Mantenimiento */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Mantenimiento
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {formatEur(parseFloat(estimate?.maintenance_eur ?? "0"))}
            </div>
          </CardContent>
        </Card>

        {/* Consumo IA */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Consumo IA
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {formatEur(parseFloat(estimate?.token_eur ?? "0"))}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {formatNumber(estimate?.input_tokens ?? 0)} entrada ·{" "}
              {formatNumber(estimate?.output_tokens ?? 0)} salida tokens
            </p>
          </CardContent>
        </Card>

        {/* Total Estimado */}
        <Card className="border-primary/30 bg-primary/5">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Estimado
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-primary">
              {formatEur(parseFloat(estimate?.total_eur ?? "0"))}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Base: {formatEur(parseFloat(estimate?.subtotal_eur ?? "0"))} + IVA (
              {parseFloat(estimate?.iva_rate ?? "0").toFixed(0)}%):{" "}
              {formatEur(parseFloat(estimate?.iva_amount_eur ?? "0"))}
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// -------------------------------------------------------
// Section 2 — Invoice History
// -------------------------------------------------------

function InvoiceHistory() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [voidTarget, setVoidTarget] = useState<Invoice | null>(null);
  const [voiding, setVoiding] = useState(false);

  const PAGE_SIZE = 10;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const fetchInvoices = useCallback(async (p: number) => {
    setLoading(true);
    setError(null);
    try {
      const result: InvoiceListResponse = await api.getBillingInvoices(p);
      setInvoices(result.invoices);
      setTotal(result.total);
    } catch {
      setError("Error al cargar el historial de facturas");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchInvoices(page);
  }, [fetchInvoices, page]);

  async function handleVoid() {
    if (!voidTarget) return;
    setVoiding(true);
    try {
      await api.voidInvoice(voidTarget.id);
      sileo.success({ title: `Factura ${voidTarget.invoice_number} anulada` });
      setVoidTarget(null);
      fetchInvoices(page);
    } catch {
      sileo.error({ title: "Error al anular la factura" });
    } finally {
      setVoiding(false);
    }
  }

  return (
    <div>
      <h2 className="text-lg font-semibold mb-4">Historial de facturas</h2>
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-6 space-y-3">
              {[...Array(4)].map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : error ? (
            <div className="py-8 text-center text-destructive text-sm">{error}</div>
          ) : invoices.length === 0 ? (
            <div className="py-8 text-center text-muted-foreground text-sm">
              No hay facturas disponibles
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Número</TableHead>
                  <TableHead>Período</TableHead>
                  <TableHead className="text-right">Subtotal</TableHead>
                  <TableHead className="text-right">IVA</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="text-right">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {invoices.map((inv) => (
                  <TableRow key={inv.id}>
                    <TableCell className="font-mono text-sm">{inv.invoice_number}</TableCell>
                    <TableCell>{formatPeriod(inv.month, inv.year)}</TableCell>
                    <TableCell className="text-right">
                      {formatEur(inv.subtotal_eur)}
                    </TableCell>
                    <TableCell className="text-right">
                      {formatEur(inv.iva_amount_eur)}
                    </TableCell>
                    <TableCell className="text-right font-semibold">
                      {formatEur(inv.total_eur)}
                    </TableCell>
                    <TableCell>
                      <InvoiceStatusBadge status={inv.status} />
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          title="Descargar PDF"
                          onClick={() =>
                            window.open(api.getInvoicePdfUrl(inv.id), "_blank")
                          }
                        >
                          <Download className="h-4 w-4" />
                        </Button>
                        {(inv.status === "issued" || inv.status === "overdue") && (
                          <Button
                            variant="ghost"
                            size="icon"
                            title="Anular factura"
                            onClick={() => setVoidTarget(inv)}
                          >
                            <Ban className="h-4 w-4 text-destructive" />
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {/* Pagination */}
          {!loading && !error && invoices.length > 0 && (
            <div className="flex items-center justify-between px-4 py-3 border-t">
              <span className="text-sm text-muted-foreground">
                Página {page} de {totalPages}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}
                >
                  <ChevronLeft className="h-4 w-4 mr-1" />
                  Anterior
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Siguiente
                  <ChevronRight className="h-4 w-4 ml-1" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Void confirmation dialog */}
      <AlertDialog
        open={!!voidTarget}
        onOpenChange={(open) => !open && setVoidTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              ¿Anular factura {voidTarget?.invoice_number}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Esta acción marcará la factura como anulada. No se puede deshacer.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={voiding}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleVoid}
              disabled={voiding}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {voiding ? "Anulando..." : "Anular factura"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// -------------------------------------------------------
// Section 3 — Payment Setup
// -------------------------------------------------------

function PaymentSetup({
  status,
  loading,
  error,
}: {
  status: StripeStatus | null;
  loading: boolean;
  error: string | null;
}) {
  const [creatingSession, setCreatingSession] = useState(false);

  async function handleSetup() {
    setCreatingSession(true);
    try {
      const session = await api.createStripeSetupSession();
      window.location.href = session.session_url;
    } catch {
      sileo.error({ title: "Error al iniciar la configuración de pago" });
      setCreatingSession(false);
    }
  }

  return (
    <div>
      <h2 className="text-lg font-semibold mb-4">Método de pago</h2>
      <Card>
        <CardContent className="pt-6">
          {loading ? (
            <div className="space-y-3">
              <Skeleton className="h-5 w-48" />
              <Skeleton className="h-4 w-64" />
            </div>
          ) : error ? (
            <p className="text-destructive text-sm">{error}</p>
          ) : status?.has_payment_method ? (
            <div className="flex items-center gap-3">
              <div className="h-9 w-9 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center flex-shrink-0">
                <CreditCard className="h-5 w-5 text-green-600 dark:text-green-400" />
              </div>
              <div>
                <p className="text-sm font-medium">Domiciliación SEPA configurada</p>
                <p className="text-sm text-muted-foreground">
                  {status.bank_name} ····{status.last4}
                </p>
              </div>
              <Badge
                variant="secondary"
                className="ml-auto bg-green-100 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-400"
              >
                Activo
              </Badge>
            </div>
          ) : (
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
              <div className="flex items-center gap-3">
                <div className="h-9 w-9 rounded-full bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center flex-shrink-0">
                  <AlertTriangle className="h-5 w-5 text-amber-600 dark:text-amber-400" />
                </div>
                <div>
                  <p className="text-sm font-medium">Sin método de pago</p>
                  <p className="text-sm text-muted-foreground">
                    Configura una domiciliación SEPA para el cobro automático
                  </p>
                </div>
              </div>
              <Button
                onClick={handleSetup}
                disabled={creatingSession}
                className="sm:ml-auto"
              >
                <CreditCard className="h-4 w-4 mr-2" />
                {creatingSession ? "Redirigiendo..." : "Configurar domiciliación SEPA"}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// -------------------------------------------------------
// Section 4 — Billing Details
// -------------------------------------------------------

function BillingDetails({
  details,
  loading,
  error,
}: {
  details: FiscalDetails | null;
  loading: boolean;
  error: string | null;
}) {
  const hasData =
    details &&
    (details.company.name ||
      details.company.nif ||
      details.company.address ||
      details.client.name ||
      details.client.nif ||
      details.client.address);

  return (
    <div>
      <h2 className="text-lg font-semibold mb-4">Datos fiscales</h2>
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[...Array(2)].map((_, i) => (
            <Card key={i}>
              <CardHeader className="pb-2">
                <Skeleton className="h-5 w-32" />
              </CardHeader>
              <CardContent className="space-y-2">
                <Skeleton className="h-4 w-48" />
                <Skeleton className="h-4 w-36" />
                <Skeleton className="h-4 w-56" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : error ? (
        <Card>
          <CardContent className="py-6 text-center text-destructive text-sm">
            {error}
          </CardContent>
        </Card>
      ) : !hasData ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground text-sm">
            Datos fiscales no configurados
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Our company */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Building2 className="h-4 w-4 text-muted-foreground" />
                Nuestra empresa
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              {details.company.name && (
                <p className="font-medium">{details.company.name}</p>
              )}
              {details.company.nif && (
                <p className="text-muted-foreground">NIF: {details.company.nif}</p>
              )}
              {details.company.address && (
                <p className="text-muted-foreground">{details.company.address}</p>
              )}
            </CardContent>
          </Card>

          {/* Client */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <User className="h-4 w-4 text-muted-foreground" />
                Cliente
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              {details.client.name && (
                <p className="font-medium">{details.client.name}</p>
              )}
              {details.client.nif && (
                <p className="text-muted-foreground">NIF: {details.client.nif}</p>
              )}
              {details.client.address && (
                <p className="text-muted-foreground">{details.client.address}</p>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

// -------------------------------------------------------
// Main page
// -------------------------------------------------------

export default function BillingPage() {
  const { isAdmin } = useAuth();

  // Section states
  const [estimate, setEstimate] = useState<CurrentEstimate | null>(null);
  const [estimateLoading, setEstimateLoading] = useState(true);
  const [estimateError, setEstimateError] = useState<string | null>(null);

  const [stripeStatus, setStripeStatus] = useState<StripeStatus | null>(null);
  const [stripeLoading, setStripeLoading] = useState(true);
  const [stripeError, setStripeError] = useState<string | null>(null);

  const [fiscalDetails, setFiscalDetails] = useState<FiscalDetails | null>(null);
  const [fiscalLoading, setFiscalLoading] = useState(true);
  const [fiscalError, setFiscalError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAdmin) return;

    async function fetchAll() {
      const [estimateResult, stripeResult, fiscalResult] = await Promise.allSettled([
        api.getBillingEstimate(),
        api.getStripeStatus(),
        api.getFiscalDetails(),
      ]);

      if (estimateResult.status === "fulfilled") {
        setEstimate(estimateResult.value);
      } else {
        setEstimateError("Error al cargar la estimación del mes");
      }
      setEstimateLoading(false);

      if (stripeResult.status === "fulfilled") {
        setStripeStatus(stripeResult.value);
      } else {
        setStripeError("Error al cargar el estado de pago");
      }
      setStripeLoading(false);

      if (fiscalResult.status === "fulfilled") {
        setFiscalDetails(fiscalResult.value);
      } else {
        setFiscalError("Error al cargar los datos fiscales");
      }
      setFiscalLoading(false);
    }

    fetchAll();
  }, [isAdmin]);

  if (!isAdmin) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12">
          <Shield className="h-12 w-12 text-muted-foreground mb-4" />
          <p className="text-muted-foreground text-center">
            No tienes permisos para acceder a esta sección.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-8">
      <CurrentMonthSummary
        estimate={estimate}
        loading={estimateLoading}
        error={estimateError}
      />

      <Separator />

      <InvoiceHistory />

      <Separator />

      <PaymentSetup
        status={stripeStatus}
        loading={stripeLoading}
        error={stripeError}
      />

      <Separator />

      <BillingDetails
        details={fiscalDetails}
        loading={fiscalLoading}
        error={fiscalError}
      />
    </div>
  );
}
