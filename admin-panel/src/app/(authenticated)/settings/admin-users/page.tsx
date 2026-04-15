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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Search,
  UserCog,
  Pencil,
  Plus,
  Trash2,
  Shield,
  User,
  Key,
  Clock,
} from "lucide-react";
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
import { sileo } from "sileo";
import api from "@/lib/api";
import { useAuth } from "@/contexts/auth-context";
import { PageContainer } from "@/components/shared/page-container";
import { PageHeader } from "@/components/shared/page-header";
import type {
  AdminUser,
  AdminRole,
  AdminUserCreate,
  AdminUserUpdate,
  AdminAccessLogEntry,
  ChatwootAgentEntry,
} from "@/lib/types";

export default function AdminUsersPage() {
  const { user: currentUser, isAdmin } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [accessLogs, setAccessLogs] = useState<AdminAccessLogEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingLogs, setIsLoadingLogs] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null);
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [isPasswordDialogOpen, setIsPasswordDialogOpen] = useState(false);
  const [deletingUser, setDeletingUser] = useState<AdminUser | null>(null);
  const [passwordUser, setPasswordUser] = useState<AdminUser | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isResyncing, setIsResyncing] = useState(false);
  const [isLinking, setIsLinking] = useState(false);
  const [chatwootAgents, setChatwootAgents] = useState<ChatwootAgentEntry[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string>("");
  const [resyncPassword, setResyncPassword] = useState("");
  const [activeTab, setActiveTab] = useState("users");

  // Form state for editing
  const [editForm, setEditForm] = useState<AdminUserUpdate>({});

  // Form state for creating
  const [createForm, setCreateForm] = useState<AdminUserCreate>({
    username: "",
    password: "",
    display_name: "",
    role: "agent",
    email: "",
  });

  // Form state for password change
  const [passwordForm, setPasswordForm] = useState({
    new_password: "",
    confirm_password: "",
  });

  useEffect(() => {
    fetchUsers();
  }, [roleFilter, statusFilter]);

  useEffect(() => {
    if (activeTab === "logs" && accessLogs.length === 0) {
      fetchAccessLogs();
    }
  }, [activeTab]);

  async function fetchUsers() {
    try {
      setIsLoading(true);
      const params: Record<string, string | number | boolean> = { limit: 100 };
      if (roleFilter !== "all") {
        params.role = roleFilter;
      }
      if (statusFilter !== "all") {
        params.is_active = statusFilter === "active";
      }
      const data = await api.getAdminUsers(params);
      setUsers(data.items);
    } catch (error) {
      console.error("Error fetching admin users:", error);
    } finally {
      setIsLoading(false);
    }
  }

  async function fetchAccessLogs() {
    try {
      setIsLoadingLogs(true);
      const data = await api.getAccessLog({ limit: 100 });
      setAccessLogs(data.items);
    } catch (error) {
      console.error("Error fetching access logs:", error);
    } finally {
      setIsLoadingLogs(false);
    }
  }

  const filteredUsers = users.filter((user) => {
    const search = searchQuery.toLowerCase();
    return (
      user.username.toLowerCase().includes(search) ||
      user.display_name?.toLowerCase().includes(search)
    );
  });

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString("es-ES", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const openEditDialog = (user: AdminUser) => {
    setEditingUser(user);
    setEditForm({
      display_name: user.display_name,
      role: user.role,
      is_active: user.is_active,
      email: user.email,
    });
    setIsEditDialogOpen(true);
  };

  const openPasswordDialog = (user: AdminUser) => {
    setPasswordUser(user);
    setPasswordForm({ new_password: "", confirm_password: "" });
    setIsPasswordDialogOpen(true);
  };

  const handleSave = async () => {
    if (!editingUser) return;

    setIsSaving(true);
    try {
      const updated = await api.updateAdminUser(editingUser.id, editForm);
      setUsers((prev) =>
        prev.map((u) => (u.id === updated.id ? updated : u))
      );
      setIsEditDialogOpen(false);
      setEditingUser(null);
      sileo.success({ title: "Actualizado correctamente" });
    } catch (error) {
      console.error("Error updating admin user:", error);
      sileo.error({ title: "Error al actualizar" });
    } finally {
      setIsSaving(false);
    }
  };

  const handleResync = async () => {
    if (!editingUser) return;
    // If no chatwoot_user_id, password is required for Platform API create
    if (!editingUser.chatwoot_user_id && !resyncPassword) {
      sileo.error({ title: "Se requiere contraseña para crear el agente en Chatwoot" });
      return;
    }
    setIsResyncing(true);
    try {
      const data = resyncPassword ? { password: resyncPassword } : undefined;
      await api.resyncAdminUserChatwoot(editingUser.id, data);
      sileo.success({ title: "Sincronizado con Chatwoot correctamente" });
      setIsEditDialogOpen(false);
      setEditingUser(null);
      setResyncPassword("");
      fetchUsers();
    } catch (error) {
      sileo.error({ title: "Error al sincronizar con Chatwoot", description: error instanceof Error ? error.message : "Desconocido" });
    } finally {
      setIsResyncing(false);
    }
  };

  const handleFetchChatwootAgents = async () => {
    try {
      const agents = await api.getChatwootAgents();
      setChatwootAgents(agents);
    } catch (error) {
      sileo.error({ title: "Error al obtener agentes de Chatwoot" });
    }
  };

  const handleLinkAgent = async () => {
    if (!editingUser || !selectedAgentId) return;
    setIsLinking(true);
    try {
      await api.linkChatwootAgent(editingUser.id, parseInt(selectedAgentId));
      sileo.success({ title: "Agente de Chatwoot vinculado correctamente" });
      setIsEditDialogOpen(false);
      setEditingUser(null);
      setSelectedAgentId("");
      fetchUsers();
    } catch (error) {
      sileo.error({ title: "Error al vincular", description: error instanceof Error ? error.message : "Desconocido" });
    } finally {
      setIsLinking(false);
    }
  };

  const handleCreate = async () => {
    if (!createForm.username || !createForm.password) return;
    if (createForm.role === "agent" && !createForm.email) {
      sileo.error({ title: "El email es obligatorio para el rol Agente" });
      return;
    }

    setIsSaving(true);
    try {
      const created = await api.createAdminUser(createForm);
      setUsers((prev) => [created, ...prev]);
      setIsCreateDialogOpen(false);
      setCreateForm({
        username: "",
        password: "",
        display_name: "",
        role: "agent",
        email: "",
      });
      sileo.success({ title: "Creado correctamente" });
    } catch (error) {
      console.error("Error creating admin user:", error);
      sileo.error({ title: "Error al crear" });
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deletingUser) return;

    setIsDeleting(true);
    try {
      await api.deleteAdminUser(deletingUser.id);
      setUsers((prev) => prev.filter((u) => u.id !== deletingUser.id));
      setIsDeleteDialogOpen(false);
      setDeletingUser(null);
      sileo.success({ title: "Administrador eliminado correctamente" });
    } catch (error) {
      console.error("Error deleting admin user:", error);
      sileo.error({ title: "Error al eliminar administrador" });
    } finally {
      setIsDeleting(false);
    }
  };

  const handlePasswordChange = async () => {
    if (!passwordUser) return;
    if (passwordForm.new_password !== passwordForm.confirm_password) {
      sileo.error({ title: "Las contrasenas no coinciden" });
      return;
    }
    if (passwordForm.new_password.length < 8) {
      sileo.error({ title: "La contrasena debe tener al menos 8 caracteres" });
      return;
    }

    setIsSaving(true);
    try {
      await api.changeAdminUserPassword(passwordUser.id, {
        new_password: passwordForm.new_password,
      });
      setIsPasswordDialogOpen(false);
      setPasswordUser(null);
      setPasswordForm({ new_password: "", confirm_password: "" });
      sileo.success({ title: "Contraseña cambiada correctamente" });
    } catch (error) {
      console.error("Error changing password:", error);
      sileo.error({ title: "Error al cambiar la contraseña" });
    } finally {
      setIsSaving(false);
    }
  };

  const getRoleBadge = (role: AdminRole) => {
    if (role === "admin") {
      return (
        <Badge variant="default" className="bg-purple-600 hover:bg-purple-700">
          <Shield className="h-3 w-3 mr-1" />
          Admin
        </Badge>
      );
    }
    return (
      <Badge variant="secondary">
        <User className="h-3 w-3 mr-1" />
        Agente
      </Badge>
    );
  };

  const getStatusBadge = (isActive: boolean) => {
    if (isActive) {
      return (
        <Badge variant="outline" className="border-green-500 text-green-600">
          Activo
        </Badge>
      );
    }
    return (
      <Badge variant="outline" className="border-red-500 text-red-600">
        Inactivo
      </Badge>
    );
  };

  const getActionBadge = (action: string) => {
    switch (action) {
      case "login":
        return <Badge variant="default">Login</Badge>;
      case "logout":
        return <Badge variant="secondary">Logout</Badge>;
      case "login_failed":
        return <Badge variant="destructive">Fallido</Badge>;
      default:
        return <Badge variant="outline">{action}</Badge>;
    }
  };

  // Non-admin users cannot access this page
  if (!isAdmin) {
    return (
      <PageContainer className="space-y-6">
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Shield className="h-12 w-12 text-muted-foreground/50 mb-4" />
            <p className="text-muted-foreground">
              No tienes permisos para acceder a esta seccion.
            </p>
          </CardContent>
        </Card>
      </PageContainer>
    );
  }

  return (
    <PageContainer className="space-y-6">
      <PageHeader
        title="Administradores"
        description="Gestión de usuarios del panel"
        actions={
          <Button onClick={() => setIsCreateDialogOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Nuevo Admin
          </Button>
        }
      />
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="users">
            <UserCog className="h-4 w-4 mr-2" />
            Usuarios
          </TabsTrigger>
          <TabsTrigger value="logs">
            <Clock className="h-4 w-4 mr-2" />
            Registro de Accesos
          </TabsTrigger>
        </TabsList>

        <TabsContent value="users" className="mt-4">
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Lista de Administradores</CardTitle>
                <CardDescription>
                  Usuarios con acceso al panel de administracion
                </CardDescription>
              </div>
              <div className="flex gap-4 mt-4">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="Buscar por nombre de usuario..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-9"
                  />
                </div>
                <Select value={roleFilter} onValueChange={setRoleFilter}>
                  <SelectTrigger className="w-[150px]">
                    <SelectValue placeholder="Rol" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos los roles</SelectItem>
                    <SelectItem value="admin">Admin</SelectItem>
                    <SelectItem value="agent">Agente</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger className="w-[150px]">
                    <SelectValue placeholder="Estado" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos</SelectItem>
                    <SelectItem value="active">Activos</SelectItem>
                    <SelectItem value="inactive">Inactivos</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-pulse text-muted-foreground">
                    Cargando administradores...
                  </div>
                </div>
              ) : filteredUsers.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 text-center">
                  <UserCog className="h-12 w-12 text-muted-foreground/50 mb-4" />
                  <p className="text-muted-foreground">
                    {searchQuery || roleFilter !== "all" || statusFilter !== "all"
                      ? "No se encontraron administradores con esos criterios"
                      : "No hay administradores registrados"}
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Usuario</TableHead>
                      <TableHead>Nombre</TableHead>
                      <TableHead>Email</TableHead>
                      <TableHead>Rol</TableHead>
                      <TableHead>Chatwoot</TableHead>
                      <TableHead>Estado</TableHead>
                      <TableHead>Creado</TableHead>
                      <TableHead className="w-[120px]">Acciones</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredUsers.map((user) => (
                      <TableRow key={user.id}>
                        <TableCell>
                          <div className="font-medium">{user.username}</div>
                        </TableCell>
                        <TableCell>
                          {user.display_name || (
                            <span className="text-muted-foreground">-</span>
                          )}
                        </TableCell>
                        <TableCell>
                          {user.email ? (
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <span className="text-sm truncate max-w-[150px] block">
                                    {user.email}
                                  </span>
                                </TooltipTrigger>
                                <TooltipContent>{user.email}</TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          ) : (
                            <span className="text-muted-foreground">&mdash;</span>
                          )}
                        </TableCell>
                        <TableCell>{getRoleBadge(user.role)}</TableCell>
                        <TableCell>
                          {user.role === "agent" ? (
                            user.chatwoot_user_id ? (
                              <Badge variant="outline" className="border-green-500 text-green-600 gap-1">
                                <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
                                Platform
                              </Badge>
                            ) : user.chatwoot_agent_id ? (
                              <Badge variant="outline" className="border-blue-500 text-blue-600 gap-1">
                                <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
                                Legacy
                              </Badge>
                            ) : (
                              <Badge variant="outline" className="border-yellow-500 text-yellow-600 gap-1">
                                <span className="h-1.5 w-1.5 rounded-full bg-yellow-500" />
                                Sin vincular
                              </Badge>
                            )
                          ) : (
                            <span className="text-muted-foreground">&mdash;</span>
                          )}
                        </TableCell>
                        <TableCell>{getStatusBadge(user.is_active)}</TableCell>
                        <TableCell className="text-muted-foreground">
                          {formatDate(user.created_at)}
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-1">
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={() => openEditDialog(user)}
                                    disabled={user.id === currentUser?.id}
                                  >
                                    <Pencil className="h-4 w-4" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>
                                  {user.id === currentUser?.id
                                    ? "No puedes editar tu propio usuario"
                                    : "Editar administrador"}
                                </TooltipContent>
                              </Tooltip>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={() => openPasswordDialog(user)}
                                  >
                                    <Key className="h-4 w-4" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>Cambiar contraseña</TooltipContent>
                              </Tooltip>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={() => {
                                      setDeletingUser(user);
                                      setIsDeleteDialogOpen(true);
                                    }}
                                    disabled={user.id === currentUser?.id}
                                    className="text-destructive hover:text-destructive"
                                  >
                                    <Trash2 className="h-4 w-4" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>
                                  {user.id === currentUser?.id
                                    ? "No puedes eliminar tu propio usuario"
                                    : "Eliminar administrador"}
                                </TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="logs" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Registro de Accesos</CardTitle>
              <CardDescription>
                Historial de login, logout y intentos fallidos
              </CardDescription>
            </CardHeader>
            <CardContent>
              {isLoadingLogs ? (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-pulse text-muted-foreground">
                    Cargando registros...
                  </div>
                </div>
              ) : accessLogs.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 text-center">
                  <Clock className="h-12 w-12 text-muted-foreground/50 mb-4" />
                  <p className="text-muted-foreground">
                    No hay registros de acceso
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Fecha</TableHead>
                      <TableHead>Usuario</TableHead>
                      <TableHead>Accion</TableHead>
                      <TableHead>IP</TableHead>
                      <TableHead>User Agent</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {accessLogs.map((log) => (
                      <TableRow key={log.id}>
                        <TableCell className="text-muted-foreground">
                          {formatDate(log.created_at)}
                        </TableCell>
                        <TableCell>
                          <div className="font-medium">
                            {log.username || "Desconocido"}
                          </div>
                        </TableCell>
                        <TableCell>{getActionBadge(log.action)}</TableCell>
                        <TableCell>
                          <code className="text-xs bg-muted px-1 py-0.5 rounded">
                            {log.ip_address || "-"}
                          </code>
                        </TableCell>
                        <TableCell className="max-w-[200px] truncate text-xs text-muted-foreground">
                          {log.user_agent || "-"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Edit User Dialog */}
      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Editar Administrador</DialogTitle>
            <DialogDescription>
              Modifica los datos del administrador. El nombre de usuario no se
              puede cambiar.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="username" className="text-xs">
                Usuario
              </Label>
              <Input
                id="username"
                value={editingUser?.username || ""}
                disabled
                className="h-8 text-sm"
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor="display_name" className="text-xs">
                Nombre
              </Label>
              <Input
                id="display_name"
                value={editForm.display_name || ""}
                onChange={(e) =>
                  setEditForm((prev) => ({
                    ...prev,
                    display_name: e.target.value,
                  }))
                }
                className="h-8 text-sm"
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor="edit_email" className="text-xs">
                Email{" "}
                {(editForm.role || editingUser?.role) === "agent" && (
                  <span className="text-destructive">*</span>
                )}
              </Label>
              <Input
                id="edit_email"
                type="email"
                value={editForm.email ?? editingUser?.email ?? ""}
                onChange={(e) =>
                  setEditForm((prev) => ({
                    ...prev,
                    email: e.target.value || null,
                  }))
                }
                placeholder="email@ejemplo.com"
                className="h-8 text-sm"
              />
              {(editForm.role || editingUser?.role) === "agent" && (
                <p className="text-xs text-muted-foreground">
                  Requerido para sincronización con Chatwoot
                </p>
              )}
            </div>

            <div className="space-y-1">
              <Label htmlFor="role" className="text-xs">
                Rol
              </Label>
              <Select
                value={editForm.role || "agent"}
                onValueChange={(value: AdminRole) =>
                  setEditForm((prev) => ({ ...prev, role: value }))
                }
              >
                <SelectTrigger className="h-8 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="admin">Admin</SelectItem>
                  <SelectItem value="agent">Agente</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {editingUser?.role === "agent" && (
              <div className="space-y-2">
                <Label className="text-xs">Chatwoot</Label>
                {editingUser.chatwoot_user_id ? (
                  /* State A: Platform-linked (full sync) */
                  <div className="flex items-center gap-2">
                    <Badge
                      variant="outline"
                      className="border-green-500 text-green-600 gap-1"
                    >
                      <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
                      Platform (User: {editingUser.chatwoot_user_id}
                      {editingUser.chatwoot_agent_id
                        ? `, Agent: ${editingUser.chatwoot_agent_id}`
                        : ""}
                      )
                    </Badge>
                  </div>
                ) : editingUser.chatwoot_agent_id ? (
                  /* State B: Legacy link (assignment only, no password sync) */
                  <div className="space-y-1">
                    <Badge
                      variant="outline"
                      className="border-blue-500 text-blue-600 gap-1"
                    >
                      <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
                      Legacy (Agent: {editingUser.chatwoot_agent_id})
                    </Badge>
                    <p className="text-xs text-muted-foreground">
                      Vinculación legacy — asignación de conversaciones activa,
                      sin sincronización de contraseña.
                    </p>
                  </div>
                ) : (
                  /* State C: Unlinked — create via Platform or link existing */
                  <div className="space-y-2">
                    <Badge
                      variant="outline"
                      className="border-yellow-500 text-yellow-600 gap-1"
                    >
                      <span className="h-1.5 w-1.5 rounded-full bg-yellow-500" />
                      Sin vincular
                    </Badge>

                    {/* Option 1: Create via Platform API (needs password) */}
                    <div className="space-y-1 rounded-md border p-2">
                      <p className="text-xs font-medium">
                        Crear en Chatwoot (Platform)
                      </p>
                      <Input
                        type="password"
                        placeholder="Contraseña para Chatwoot"
                        value={resyncPassword}
                        onChange={(e) => setResyncPassword(e.target.value)}
                        className="h-7 text-xs"
                      />
                      <p className="text-xs text-muted-foreground">
                        Mayúscula, minúscula, número y carácter especial
                      </p>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleResync}
                        disabled={isResyncing || !resyncPassword}
                        className="h-7 text-xs w-full"
                      >
                        {isResyncing
                          ? "Creando..."
                          : "Crear agente en Chatwoot"}
                      </Button>
                    </div>

                    {/* Option 2: Link existing Chatwoot agent */}
                    <div className="space-y-1 rounded-md border p-2">
                      <p className="text-xs font-medium">
                        Vincular agente existente (Legacy)
                      </p>
                      <div className="flex gap-1">
                        <Select
                          value={selectedAgentId}
                          onValueChange={setSelectedAgentId}
                        >
                          <SelectTrigger
                            className="h-7 text-xs flex-1"
                            onClick={() => {
                              if (chatwootAgents.length === 0)
                                handleFetchChatwootAgents();
                            }}
                          >
                            <SelectValue placeholder="Seleccionar agente..." />
                          </SelectTrigger>
                          <SelectContent>
                            {chatwootAgents.length === 0 ? (
                              <SelectItem value="__loading" disabled>
                                Cargando...
                              </SelectItem>
                            ) : (
                              chatwootAgents.map((agent) => (
                                <SelectItem
                                  key={agent.id}
                                  value={String(agent.id)}
                                >
                                  {agent.name} ({agent.email})
                                </SelectItem>
                              ))
                            )}
                          </SelectContent>
                        </Select>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={handleLinkAgent}
                          disabled={isLinking || !selectedAgentId}
                          className="h-7 text-xs"
                        >
                          {isLinking ? "..." : "Vincular"}
                        </Button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            <div className="space-y-1">
              <Label htmlFor="is_active" className="text-xs">
                Estado
              </Label>
              <Select
                value={editForm.is_active ? "active" : "inactive"}
                onValueChange={(value) =>
                  setEditForm((prev) => ({
                    ...prev,
                    is_active: value === "active",
                  }))
                }
              >
                <SelectTrigger className="h-8 text-sm">
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
            <Button onClick={handleSave} disabled={isSaving}>
              {isSaving ? "Guardando..." : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create User Dialog */}
      <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Nuevo Administrador</DialogTitle>
            <DialogDescription>
              Crea un nuevo usuario con acceso al panel de administracion.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="create_username" className="text-xs">
                Usuario *
              </Label>
              <Input
                id="create_username"
                value={createForm.username}
                onChange={(e) =>
                  setCreateForm((prev) => ({
                    ...prev,
                    username: e.target.value,
                  }))
                }
                placeholder="nombre_usuario"
                className="h-8 text-sm"
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor="create_password" className="text-xs">
                Contrasena *
              </Label>
              <Input
                id="create_password"
                type="password"
                value={createForm.password}
                onChange={(e) =>
                  setCreateForm((prev) => ({
                    ...prev,
                    password: e.target.value,
                  }))
                }
                placeholder="Min. 8 caracteres"
                className="h-8 text-sm"
              />
              <p className="text-xs text-muted-foreground">
                Mayúscula, minúscula, número y carácter especial
              </p>
            </div>

            <div className="space-y-1">
              <Label htmlFor="create_display_name" className="text-xs">
                Nombre
              </Label>
              <Input
                id="create_display_name"
                value={createForm.display_name || ""}
                onChange={(e) =>
                  setCreateForm((prev) => ({
                    ...prev,
                    display_name: e.target.value,
                  }))
                }
                placeholder="Nombre para mostrar"
                className="h-8 text-sm"
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor="create_email" className="text-xs">
                Email{" "}
                {createForm.role === "agent" && (
                  <span className="text-destructive">*</span>
                )}
              </Label>
              <Input
                id="create_email"
                type="email"
                value={createForm.email || ""}
                onChange={(e) =>
                  setCreateForm((prev) => ({
                    ...prev,
                    email: e.target.value,
                  }))
                }
                placeholder="email@ejemplo.com"
                className="h-8 text-sm"
              />
              {createForm.role === "agent" && (
                <p className="text-xs text-muted-foreground">
                  Requerido para sincronización con Chatwoot
                </p>
              )}
            </div>

            <div className="space-y-1">
              <Label htmlFor="create_role" className="text-xs">
                Rol
              </Label>
              <Select
                value={createForm.role || "agent"}
                onValueChange={(value: AdminRole) =>
                  setCreateForm((prev) => ({ ...prev, role: value }))
                }
              >
                <SelectTrigger className="h-8 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="admin">Admin</SelectItem>
                  <SelectItem value="agent">Agente</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsCreateDialogOpen(false)}
              disabled={isSaving}
            >
              Cancelar
            </Button>
            <Button
              onClick={handleCreate}
              disabled={
                isSaving ||
                !createForm.username ||
                !createForm.password ||
                createForm.password.length < 8
              }
            >
              {isSaving ? "Creando..." : "Crear Administrador"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Password Change Dialog */}
      <Dialog
        open={isPasswordDialogOpen}
        onOpenChange={setIsPasswordDialogOpen}
      >
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Cambiar Contrasena</DialogTitle>
            <DialogDescription>
              Establece una nueva contrasena para{" "}
              <span className="font-medium">{passwordUser?.username}</span>
              {passwordUser?.chatwoot_user_id && (
                <span className="block mt-1 text-green-600">
                  La contraseña se sincronizará automáticamente con Chatwoot.
                </span>
              )}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="new_password" className="text-xs">
                Nueva *
              </Label>
              <Input
                id="new_password"
                type="password"
                value={passwordForm.new_password}
                onChange={(e) =>
                  setPasswordForm((prev) => ({
                    ...prev,
                    new_password: e.target.value,
                  }))
                }
                placeholder="Min. 8 caracteres"
                className="h-8 text-sm"
              />
              <p className="text-xs text-muted-foreground">
                Mayúscula, minúscula, número y carácter especial
              </p>
            </div>

            <div className="space-y-1">
              <Label htmlFor="confirm_password" className="text-xs">
                Confirmar *
              </Label>
              <Input
                id="confirm_password"
                type="password"
                value={passwordForm.confirm_password}
                onChange={(e) =>
                  setPasswordForm((prev) => ({
                    ...prev,
                    confirm_password: e.target.value,
                  }))
                }
                placeholder="Repite la contrasena"
                className="h-8 text-sm"
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsPasswordDialogOpen(false)}
              disabled={isSaving}
            >
              Cancelar
            </Button>
            <Button
              onClick={handlePasswordChange}
              disabled={
                isSaving ||
                !passwordForm.new_password ||
                passwordForm.new_password.length < 8 ||
                passwordForm.new_password !== passwordForm.confirm_password
              }
            >
              {isSaving ? "Cambiando..." : "Cambiar Contrasena"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete User AlertDialog */}
      <AlertDialog
        open={isDeleteDialogOpen}
        onOpenChange={setIsDeleteDialogOpen}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Eliminar Administrador</AlertDialogTitle>
            <AlertDialogDescription>
              Esta seguro de eliminar a{" "}
              <span className="font-medium">
                {deletingUser?.display_name || deletingUser?.username}
              </span>
              ? Esta accion no se puede deshacer.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>
              Cancelar
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              disabled={isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? "Eliminando..." : "Eliminar"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageContainer>
  );
}
