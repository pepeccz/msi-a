"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  Card,
  CardContent,
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
import { Separator } from "@/components/ui/separator";
import {
  ArrowLeft,
  User as UserIcon,
  Building2,
  Phone,
  Save,
  Calendar,
  MessageSquare,
  ChevronRight,
  FileText,
  Loader2,
  Brain,
  Clock,
  Tag,
} from "lucide-react";
import { sileo } from "sileo";
import api from "@/lib/api";
import type {
  User,
  ClientType,
  UserUpdate,
  ConversationHistory,
  CaseListItem,
  AgentProfile,
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
  const [agentProfile, setAgentProfile] = useState<AgentProfile | null>(null);
  const [isLoadingProfile, setIsLoadingProfile] = useState(true);

  const [formData, setFormData] = useState<UserUpdate>({});
  const [hasChanges, setHasChanges] = useState(false);

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
        sileo.error({ title: "Error al cargar usuario", description: error instanceof Error ? error.message : "Desconocido" });
      } finally {
        setIsLoading(false);
      }
    }

    fetchData();
  }, [userId]);

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

  useEffect(() => {
    api
      .getUserAgentProfile(userId)
      .then((data) => setAgentProfile(data.found ? data.profile : null))
      .catch(() => {
        sileo.error({ title: "Error al cargar memoria del agente" });
      })
      .finally(() => setIsLoadingProfile(false));
  }, [userId]);

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
      sileo.success({ title: "Usuario actualizado correctamente" });
    } catch (error) {
      console.error("Error saving user:", error);
      sileo.error({ title: "Error al guardar usuario", description: error instanceof Error ? error.message : "Desconocido" });
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
      pending_review: "Pendiente de revision",
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
    <div className="p-4 space-y-4">
      {/* Header — compact with all meta info */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={() => router.back()}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-semibold truncate">{displayName}</h1>
              {user.client_type === "professional" ? (
                <Badge variant="default" className="bg-blue-600 hover:bg-blue-700 shrink-0">
                  <Building2 className="h-3 w-3 mr-1" />
                  Profesional
                </Badge>
              ) : (
                <Badge variant="secondary" className="shrink-0">
                  <UserIcon className="h-3 w-3 mr-1" />
                  Particular
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
              <span className="flex items-center gap-1">
                <Phone className="h-3 w-3" />
                {user.phone}
              </span>
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                Registro: {formatDate(user.created_at)}
              </span>
              {user.last_activity_at && (
                <span className="flex items-center gap-1">
                  <Calendar className="h-3 w-3" />
                  Actividad: {formatDate(user.last_activity_at)}
                </span>
              )}
            </div>
          </div>
        </div>
        <Button
          size="sm"
          onClick={handleSave}
          disabled={isSaving || !hasChanges}
          className="shrink-0"
        >
          {isSaving ? (
            <Loader2 className="h-4 w-4 animate-spin mr-1" />
          ) : (
            <Save className="h-4 w-4 mr-1" />
          )}
          {isSaving ? "Guardando..." : "Guardar"}
        </Button>
      </div>

      {/* Main Content — 2 equal columns */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Left — Form */}
        <Card>
          <CardHeader className="py-3 px-4">
            <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
              Datos del usuario
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 pt-0 space-y-3">
            {/* Identity row */}
            <div className="grid gap-3 grid-cols-[1fr_1fr_auto]">
              <div className="space-y-1">
                <Label className="text-xs">Nombre</Label>
                <Input
                  value={formData.first_name || ""}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, first_name: e.target.value || null }))
                  }
                  disabled={isSaving}
                  placeholder="Nombre"
                  className="h-8 text-sm"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Apellidos</Label>
                <Input
                  value={formData.last_name || ""}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, last_name: e.target.value || null }))
                  }
                  disabled={isSaving}
                  placeholder="Apellidos"
                  className="h-8 text-sm"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Tipo</Label>
                <Select
                  value={formData.client_type || "particular"}
                  onValueChange={(value: ClientType) =>
                    setFormData((prev) => ({ ...prev, client_type: value }))
                  }
                  disabled={isSaving}
                >
                  <SelectTrigger className="h-8 text-sm w-[130px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="particular">Particular</SelectItem>
                    <SelectItem value="professional">Profesional</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Contact row */}
            <div className="grid gap-3 grid-cols-2">
              <div className="space-y-1">
                <Label className="text-xs">Email</Label>
                <Input
                  type="email"
                  value={formData.email || ""}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, email: e.target.value || null }))
                  }
                  disabled={isSaving}
                  placeholder="correo@ejemplo.com"
                  className="h-8 text-sm"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Telefono</Label>
                <Input value={user.phone} disabled className="h-8 text-sm font-mono bg-muted" />
              </div>
            </div>

            {/* Company row */}
            <div className="grid gap-3 grid-cols-2">
              <div className="space-y-1">
                <Label className="text-xs">Empresa</Label>
                <Input
                  value={formData.company_name || ""}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, company_name: e.target.value || null }))
                  }
                  disabled={isSaving}
                  placeholder="Nombre de la empresa"
                  className="h-8 text-sm"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">NIF/CIF</Label>
                <Input
                  value={formData.nif_cif || ""}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, nif_cif: e.target.value || null }))
                  }
                  disabled={isSaving}
                  placeholder="12345678A"
                  className="h-8 text-sm font-mono"
                />
              </div>
            </div>

            <Separator />

            {/* Address */}
            <div className="space-y-1">
              <Label className="text-xs">Direccion</Label>
              <Input
                value={formData.domicilio_calle || ""}
                onChange={(e) =>
                  setFormData((prev) => ({ ...prev, domicilio_calle: e.target.value || null }))
                }
                disabled={isSaving}
                placeholder="Calle y numero"
                className="h-8 text-sm"
              />
            </div>
            <div className="grid gap-3 grid-cols-3">
              <div className="space-y-1">
                <Label className="text-xs">Localidad</Label>
                <Input
                  value={formData.domicilio_localidad || ""}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, domicilio_localidad: e.target.value || null }))
                  }
                  disabled={isSaving}
                  placeholder="Ciudad"
                  className="h-8 text-sm"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Provincia</Label>
                <Input
                  value={formData.domicilio_provincia || ""}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, domicilio_provincia: e.target.value || null }))
                  }
                  disabled={isSaving}
                  placeholder="Provincia"
                  className="h-8 text-sm"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">C.P.</Label>
                <Input
                  value={formData.domicilio_cp || ""}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, domicilio_cp: e.target.value || null }))
                  }
                  disabled={isSaving}
                  placeholder="28001"
                  maxLength={5}
                  className="h-8 text-sm font-mono"
                />
              </div>
            </div>

            {/* Metadata — inline if present */}
            {Object.keys(user.metadata || {}).length > 0 && (
              <>
                <Separator />
                <div className="space-y-1">
                  <Label className="text-xs text-muted-foreground">Metadata</Label>
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(user.metadata || {}).map(([key, value]) => (
                      <Badge key={key} variant="outline" className="text-xs font-normal">
                        <code className="mr-1 text-muted-foreground">{key}:</code>
                        {String(value)}
                      </Badge>
                    ))}
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Right — Activity */}
        <div className="space-y-4">
          {/* Conversations */}
          <Card>
            <CardHeader className="py-2.5 px-4 flex-row items-center justify-between">
              <div className="flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-muted-foreground" />
                <CardTitle className="text-sm font-medium">
                  Conversaciones
                </CardTitle>
                <Badge variant="secondary" className="text-xs h-5">
                  {conversations.length}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="px-4 pb-3 pt-0">
              {conversations.length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-2">
                  Sin conversaciones
                </p>
              ) : (
                <div className="space-y-1 max-h-[180px] overflow-y-auto">
                  {conversations.map((conv) => (
                    <Link
                      key={conv.id}
                      href={`/conversations/${conv.id}`}
                      className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-muted/50 transition-colors text-sm group"
                    >
                      <span className="text-xs text-muted-foreground shrink-0 w-[110px]">
                        {formatDateTime(conv.started_at)}
                      </span>
                      <span className="text-xs text-muted-foreground shrink-0">
                        {conv.message_count} msg
                      </span>
                      {conv.summary && (
                        <span className="text-xs text-muted-foreground truncate flex-1">
                          — {conv.summary}
                        </span>
                      )}
                      <ChevronRight className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 shrink-0" />
                    </Link>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Cases */}
          <Card>
            <CardHeader className="py-2.5 px-4 flex-row items-center justify-between">
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-muted-foreground" />
                <CardTitle className="text-sm font-medium">
                  Expedientes
                </CardTitle>
                <Badge variant="secondary" className="text-xs h-5">
                  {isLoadingCases ? "..." : cases.length}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="px-4 pb-3 pt-0">
              {isLoadingCases ? (
                <div className="flex items-center justify-center py-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                </div>
              ) : cases.length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-2">
                  Sin expedientes
                </p>
              ) : (
                <div className="space-y-1 max-h-[180px] overflow-y-auto">
                  {cases.map((c) => (
                    <Link
                      key={c.id}
                      href={`/cases/${c.id}`}
                      className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-muted/50 transition-colors group"
                    >
                      <Badge
                        variant={getStatusVariant(c.status) as "default" | "secondary" | "destructive" | "outline"}
                        className="text-[10px] h-5 shrink-0"
                      >
                        {getStatusLabel(c.status)}
                      </Badge>
                      <span className="text-sm font-medium truncate">
                        {c.vehiculo_marca && c.vehiculo_modelo
                          ? `${c.vehiculo_marca} ${c.vehiculo_modelo}`
                          : "Sin vehiculo"}
                      </span>
                      {c.vehiculo_matricula && (
                        <span className="text-xs text-muted-foreground font-mono shrink-0">
                          {c.vehiculo_matricula}
                        </span>
                      )}
                      <span className="text-xs text-muted-foreground shrink-0 ml-auto">
                        {formatDate(c.created_at)}
                      </span>
                      <ChevronRight className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 shrink-0" />
                    </Link>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Agent Memory */}
          <Card>
            <CardHeader className="py-2.5 px-4 flex-row items-center justify-between">
              <div className="flex items-center gap-2">
                <Brain className="h-4 w-4 text-muted-foreground" />
                <CardTitle className="text-sm font-medium">
                  Memoria del Agente
                </CardTitle>
              </div>
            </CardHeader>
            <CardContent className="px-4 pb-3 pt-0">
              {isLoadingProfile ? (
                <div className="flex items-center justify-center py-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                </div>
              ) : agentProfile === null ? (
                <p className="text-xs text-muted-foreground text-center py-2">
                  Sin datos de memoria
                </p>
              ) : (
                <div className="space-y-3">
                  {/* Timestamps inline */}
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    {agentProfile.first_seen && (
                      <span>Primera: {formatDate(agentProfile.first_seen)}</span>
                    )}
                    {agentProfile.last_seen && (
                      <span>Ultima: {formatDate(agentProfile.last_seen)}</span>
                    )}
                    {agentProfile.client_type && (
                      <span>Tipo: {agentProfile.client_type}</span>
                    )}
                  </div>

                  {/* Past quotes */}
                  {agentProfile.past_quotes && agentProfile.past_quotes.length > 0 && (
                    <div className="space-y-1.5">
                      <p className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                        <Tag className="h-3 w-3" />
                        Presupuestos
                      </p>
                      <div className="space-y-1">
                        {agentProfile.past_quotes.map((q, i) => (
                          <div
                            key={i}
                            className="flex items-center gap-2 text-xs px-2 py-1 rounded bg-muted/40"
                          >
                            <span className="font-medium shrink-0 w-14">
                              {q.price != null ? `${q.price} €` : "—"}
                            </span>
                            <div className="flex flex-wrap gap-1 flex-1 min-w-0">
                              {q.elements.map((el) => (
                                <Badge key={el} variant="secondary" className="text-[10px] h-4 px-1">
                                  {el}
                                </Badge>
                              ))}
                            </div>
                            <span className="text-muted-foreground shrink-0">
                              {formatDate(q.date)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Past expedientes */}
                  {agentProfile.past_expedientes && agentProfile.past_expedientes.length > 0 && (
                    <div className="space-y-1.5">
                      <p className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                        <FileText className="h-3 w-3" />
                        Expedientes previos
                      </p>
                      <div className="space-y-1">
                        {agentProfile.past_expedientes.map((e, i) => (
                          <div
                            key={i}
                            className="flex items-center gap-2 text-xs px-2 py-1 rounded bg-muted/40"
                          >
                            <span className="font-mono text-[10px] shrink-0 w-14 truncate">
                              {e.case_id.slice(0, 8)}
                            </span>
                            <div className="flex flex-wrap gap-1 flex-1 min-w-0">
                              {e.elements.map((el) => (
                                <Badge key={el} variant="secondary" className="text-[10px] h-4 px-1">
                                  {el}
                                </Badge>
                              ))}
                            </div>
                            <span className="text-muted-foreground shrink-0">
                              {formatDate(e.date)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {(!agentProfile.past_quotes || agentProfile.past_quotes.length === 0) &&
                    (!agentProfile.past_expedientes || agentProfile.past_expedientes.length === 0) && (
                    <p className="text-xs text-muted-foreground text-center">
                      Sin presupuestos ni expedientes previos
                    </p>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
