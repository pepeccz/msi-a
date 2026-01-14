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
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ArrowLeft,
  User as UserIcon,
  Building2,
  Phone,
  Mail,
  Calendar,
  MessageSquare,
  ChevronRight,
  FileText,
  Loader2,
} from "lucide-react";
import api from "@/lib/api";
import type {
  User,
  ClientType,
  UserUpdate,
  ConversationHistory,
  CaseListItem,
} from "@/lib/types";

export default function UserDetailPage() {
  const params = useParams();
  const router = useRouter();
  const userId = params.id as string;

  const [user, setUser] = useState<User | null>(null);
  const [conversations, setConversations] = useState<ConversationHistory[]>([]);
  const [cases, setCases] = useState<CaseListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingCases, setIsLoadingCases] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  // Form state
  const [formData, setFormData] = useState<UserUpdate>({});
  const [hasChanges, setHasChanges] = useState(false);

  // Fetch user and conversations
  useEffect(() => {
    async function fetchData() {
      try {
        setIsLoading(true);
        const [userData, conversationsData] = await Promise.all([
          api.getUser(userId),
          api.getConversations({ user_id: userId, limit: 50 }),
        ]);

        setUser(userData);
        setConversations(conversationsData.items);

        // Initialize form data
        setFormData({
          first_name: userData.first_name,
          last_name: userData.last_name,
          email: userData.email,
          nif_cif: userData.nif_cif,
          company_name: userData.company_name,
          client_type: userData.client_type,
          domicilio_calle: userData.domicilio_calle,
          domicilio_localidad: userData.domicilio_localidad,
          domicilio_provincia: userData.domicilio_provincia,
          domicilio_cp: userData.domicilio_cp,
        });
      } catch (error) {
        console.error("Error fetching user:", error);
        alert(
          "Error al cargar usuario: " +
            (error instanceof Error ? error.message : "Desconocido")
        );
      } finally {
        setIsLoading(false);
      }
    }

    fetchData();
  }, [userId]);

  // Fetch user's cases
  useEffect(() => {
    async function fetchCases() {
      try {
        setIsLoadingCases(true);
        const response = await api.getCases({ user_id: userId, limit: 50 });
        setCases(response.items);
      } catch (error) {
        console.error("Error fetching cases:", error);
      } finally {
        setIsLoadingCases(false);
      }
    }

    fetchCases();
  }, [userId]);

  // Track changes
  useEffect(() => {
    if (!user) return;

    const changed =
      formData.first_name !== user.first_name ||
      formData.last_name !== user.last_name ||
      formData.email !== user.email ||
      formData.nif_cif !== user.nif_cif ||
      formData.company_name !== user.company_name ||
      formData.client_type !== user.client_type ||
      formData.domicilio_calle !== user.domicilio_calle ||
      formData.domicilio_localidad !== user.domicilio_localidad ||
      formData.domicilio_provincia !== user.domicilio_provincia ||
      formData.domicilio_cp !== user.domicilio_cp;

    setHasChanges(changed);
  }, [formData, user]);

  const handleSave = async () => {
    if (!user) return;

    try {
      setIsSaving(true);
      const updated = await api.updateUser(userId, formData);
      setUser(updated);
      setHasChanges(false);
      alert("Usuario actualizado correctamente");
    } catch (error) {
      console.error("Error saving user:", error);
      alert(
        "Error al guardar usuario: " +
          (error instanceof Error ? error.message : "Desconocido")
      );
    } finally {
      setIsSaving(false);
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString("es-ES", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  };

  const formatDateTime = (dateString: string) => {
    return new Date(dateString).toLocaleString("es-ES", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const getStatusVariant = (status: string) => {
    switch (status) {
      case "resolved":
        return "default";
      case "in_progress":
        return "secondary";
      case "pending_review":
        return "destructive";
      case "collecting":
      case "pending_images":
        return "outline";
      default:
        return "outline";
    }
  };

  const getStatusLabel = (status: string) => {
    const labels: Record<string, string> = {
      collecting: "Recopilando",
      pending_images: "Esperando imagenes",
      pending_review: "Pendiente revision",
      in_progress: "En proceso",
      resolved: "Resuelto",
      cancelled: "Cancelado",
      abandoned: "Abandonado",
    };
    return labels[status] || status;
  };

  if (isLoading || !user) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-muted-foreground">Cargando usuario...</div>
      </div>
    );
  }

  const displayName =
    user.first_name || user.last_name
      ? `${user.first_name || ""} ${user.last_name || ""}`.trim()
      : user.phone;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link href="/users">
          <Button variant="outline" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div className="flex-1">
          <h1 className="text-3xl font-bold tracking-tight">{displayName}</h1>
          <div className="flex items-center gap-2 text-muted-foreground">
            <Phone className="h-4 w-4" />
            <span>{user.phone}</span>
            <span className="mx-2">|</span>
            {user.client_type === "professional" ? (
              <Badge variant="default" className="bg-blue-600 hover:bg-blue-700">
                <Building2 className="h-3 w-3 mr-1" />
                Profesional
              </Badge>
            ) : (
              <Badge variant="secondary">
                <UserIcon className="h-3 w-3 mr-1" />
                Particular
              </Badge>
            )}
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left Column - Form */}
        <div className="lg:col-span-2 space-y-6">
          {/* Informacion del Usuario */}
          <Card>
            <CardHeader>
              <CardTitle>Informacion del Usuario</CardTitle>
              <CardDescription>
                Datos personales y de contacto
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>Telefono</Label>
                <Input value={user.phone} disabled className="font-mono" />
                <p className="text-xs text-muted-foreground">
                  Identificador unico (no editable)
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="client_type">Tipo de Cliente</Label>
                <Select
                  value={formData.client_type || "particular"}
                  onValueChange={(value: ClientType) =>
                    setFormData((prev) => ({ ...prev, client_type: value }))
                  }
                  disabled={isSaving}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="particular">Particular</SelectItem>
                    <SelectItem value="professional">Profesional</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="first_name">Nombre</Label>
                  <Input
                    id="first_name"
                    value={formData.first_name || ""}
                    onChange={(e) =>
                      setFormData((prev) => ({
                        ...prev,
                        first_name: e.target.value || null,
                      }))
                    }
                    disabled={isSaving}
                    placeholder="Nombre"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="last_name">Apellidos</Label>
                  <Input
                    id="last_name"
                    value={formData.last_name || ""}
                    onChange={(e) =>
                      setFormData((prev) => ({
                        ...prev,
                        last_name: e.target.value || null,
                      }))
                    }
                    disabled={isSaving}
                    placeholder="Apellidos"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={formData.email || ""}
                  onChange={(e) =>
                    setFormData((prev) => ({
                      ...prev,
                      email: e.target.value || null,
                    }))
                  }
                  disabled={isSaving}
                  placeholder="correo@ejemplo.com"
                />
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="company_name">Empresa</Label>
                  <Input
                    id="company_name"
                    value={formData.company_name || ""}
                    onChange={(e) =>
                      setFormData((prev) => ({
                        ...prev,
                        company_name: e.target.value || null,
                      }))
                    }
                    disabled={isSaving}
                    placeholder="Nombre de la empresa"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="nif_cif">NIF/CIF</Label>
                  <Input
                    id="nif_cif"
                    value={formData.nif_cif || ""}
                    onChange={(e) =>
                      setFormData((prev) => ({
                        ...prev,
                        nif_cif: e.target.value || null,
                      }))
                    }
                    disabled={isSaving}
                    placeholder="12345678A"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Direccion */}
          <Card>
            <CardHeader>
              <CardTitle>Direccion</CardTitle>
              <CardDescription>
                Direccion de facturacion y homologacion
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="domicilio_calle">Calle y Numero</Label>
                <Input
                  id="domicilio_calle"
                  value={formData.domicilio_calle || ""}
                  onChange={(e) =>
                    setFormData((prev) => ({
                      ...prev,
                      domicilio_calle: e.target.value || null,
                    }))
                  }
                  disabled={isSaving}
                  placeholder="Calle Principal, 123"
                />
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <div className="space-y-2">
                  <Label htmlFor="domicilio_localidad">Localidad</Label>
                  <Input
                    id="domicilio_localidad"
                    value={formData.domicilio_localidad || ""}
                    onChange={(e) =>
                      setFormData((prev) => ({
                        ...prev,
                        domicilio_localidad: e.target.value || null,
                      }))
                    }
                    disabled={isSaving}
                    placeholder="Ciudad"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="domicilio_provincia">Provincia</Label>
                  <Input
                    id="domicilio_provincia"
                    value={formData.domicilio_provincia || ""}
                    onChange={(e) =>
                      setFormData((prev) => ({
                        ...prev,
                        domicilio_provincia: e.target.value || null,
                      }))
                    }
                    disabled={isSaving}
                    placeholder="Provincia"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="domicilio_cp">Codigo Postal</Label>
                  <Input
                    id="domicilio_cp"
                    value={formData.domicilio_cp || ""}
                    onChange={(e) =>
                      setFormData((prev) => ({
                        ...prev,
                        domicilio_cp: e.target.value || null,
                      }))
                    }
                    disabled={isSaving}
                    placeholder="28001"
                    maxLength={5}
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Action Buttons */}
          <div className="flex gap-3 justify-end pt-4 border-t">
            <Link href="/users">
              <Button variant="outline">Cancelar</Button>
            </Link>
            <Button
              onClick={handleSave}
              disabled={isSaving || !hasChanges}
            >
              {isSaving ? "Guardando..." : "Guardar Cambios"}
            </Button>
          </div>
        </div>

        {/* Right Column - Info */}
        <div className="lg:col-span-1 space-y-6">
          {/* Conversaciones */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <MessageSquare className="h-5 w-5" />
                Conversaciones ({conversations.length})
              </CardTitle>
              <CardDescription>
                Historial de conversaciones con este usuario
              </CardDescription>
            </CardHeader>
            <CardContent>
              {conversations.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">
                  No hay conversaciones registradas
                </p>
              ) : (
                <div className="space-y-2 max-h-[300px] overflow-y-auto">
                  {conversations.map((conv) => (
                    <div
                      key={conv.id}
                      className="flex items-start gap-2 p-2 border rounded-lg"
                    >
                      <Calendar className="h-4 w-4 mt-0.5 text-muted-foreground" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium">
                          {formatDateTime(conv.started_at)}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {conv.message_count} mensajes
                          {conv.ended_at && ` - Finalizada`}
                        </p>
                        {conv.summary && (
                          <p className="text-xs text-muted-foreground mt-1 truncate">
                            {conv.summary}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Expedientes */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                Expedientes ({cases.length})
              </CardTitle>
              <CardDescription>
                Casos asociados a este usuario
              </CardDescription>
            </CardHeader>
            <CardContent>
              {isLoadingCases ? (
                <div className="flex items-center justify-center py-4">
                  <Loader2 className="h-4 w-4 animate-spin" />
                </div>
              ) : cases.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">
                  Sin expedientes
                </p>
              ) : (
                <div className="space-y-2 max-h-[300px] overflow-y-auto">
                  {cases.map((c) => (
                    <Link
                      key={c.id}
                      href={`/cases/${c.id}`}
                      className="block p-3 rounded-lg border hover:bg-muted/50 transition-colors"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <Badge variant={getStatusVariant(c.status) as "default" | "secondary" | "destructive" | "outline"}>
                              {getStatusLabel(c.status)}
                            </Badge>
                            {c.vehiculo_marca && c.vehiculo_modelo && (
                              <span className="text-sm font-medium truncate">
                                {c.vehiculo_marca} {c.vehiculo_modelo}
                              </span>
                            )}
                          </div>
                          <div className="text-xs text-muted-foreground mt-1">
                            {c.vehiculo_matricula && <span>{c.vehiculo_matricula} - </span>}
                            {formatDate(c.created_at)}
                          </div>
                        </div>
                        <ChevronRight className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                      </div>
                    </Link>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Metadata */}
          <Card>
            <CardHeader>
              <CardTitle>Metadata</CardTitle>
              <CardDescription>
                Datos adicionales del usuario
              </CardDescription>
            </CardHeader>
            <CardContent>
              {Object.keys(user.metadata || {}).length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">
                  Sin datos adicionales
                </p>
              ) : (
                <div className="space-y-2">
                  {Object.entries(user.metadata || {}).map(([key, value]) => (
                    <div
                      key={key}
                      className="flex items-start gap-2 p-2 border rounded-lg"
                    >
                      <code className="text-xs bg-muted px-1.5 py-0.5 rounded">
                        {key}
                      </code>
                      <span className="text-sm text-muted-foreground flex-1 truncate">
                        {String(value)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Fechas */}
          <Card>
            <CardHeader>
              <CardTitle>Fechas</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-sm text-muted-foreground">Registro</span>
                <span className="text-sm font-medium">
                  {formatDateTime(user.created_at)}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-muted-foreground">
                  Ultima actualizacion
                </span>
                <span className="text-sm font-medium">
                  {formatDateTime(user.updated_at)}
                </span>
              </div>
              {user.last_activity_at && (
                <div className="flex justify-between items-center">
                  <span className="text-sm text-muted-foreground">
                    Ultima actividad
                  </span>
                  <span className="text-sm font-medium">
                    {formatDateTime(user.last_activity_at)}
                  </span>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
