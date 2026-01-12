"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
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
import { Search, Users, Pencil, Building2, User, Plus, Trash2 } from "lucide-react";
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
import api from "@/lib/api";
import type { User as UserType, ClientType, UserCreate, UserUpdate } from "@/lib/types";

export default function UsersPage() {
  const router = useRouter();
  const [users, setUsers] = useState<UserType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [clientTypeFilter, setClientTypeFilter] = useState<string>("all");
  const [editingUser, setEditingUser] = useState<UserType | null>(null);
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [deletingUser, setDeletingUser] = useState<UserType | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // Form state for editing
  const [editForm, setEditForm] = useState<UserUpdate>({});

  // Form state for creating
  const [createForm, setCreateForm] = useState<UserCreate>({
    phone: "",
    client_type: "particular",
  });

  useEffect(() => {
    fetchUsers();
  }, [clientTypeFilter]);

  async function fetchUsers() {
    try {
      setIsLoading(true);
      const params: Record<string, string | number> = {
        limit: 100,
        sort_by: "last_activity",
      };
      if (clientTypeFilter !== "all") {
        params.client_type = clientTypeFilter;
      }
      const data = await api.getUsers(params);
      setUsers(data.items);
    } catch (error) {
      console.error("Error fetching users:", error);
    } finally {
      setIsLoading(false);
    }
  }

  const filteredUsers = users.filter((user) => {
    const search = searchQuery.toLowerCase();
    return (
      user.phone.toLowerCase().includes(search) ||
      user.first_name?.toLowerCase().includes(search) ||
      user.last_name?.toLowerCase().includes(search) ||
      user.email?.toLowerCase().includes(search) ||
      user.company_name?.toLowerCase().includes(search) ||
      user.nif_cif?.toLowerCase().includes(search)
    );
  });

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString("es-ES", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  };

  const openEditDialog = (user: UserType) => {
    setEditingUser(user);
    setEditForm({
      first_name: user.first_name,
      last_name: user.last_name,
      email: user.email,
      nif_cif: user.nif_cif,
      company_name: user.company_name,
      client_type: user.client_type,
    });
    setIsEditDialogOpen(true);
  };

  const handleSave = async () => {
    if (!editingUser) return;

    setIsSaving(true);
    try {
      const updated = await api.updateUser(editingUser.id, editForm);
      setUsers((prev) =>
        prev.map((u) => (u.id === updated.id ? updated : u))
      );
      setIsEditDialogOpen(false);
      setEditingUser(null);
    } catch (error) {
      console.error("Error updating user:", error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleCreate = async () => {
    if (!createForm.phone) return;

    setIsSaving(true);
    try {
      const created = await api.createUser(createForm);
      setUsers((prev) => [created, ...prev]);
      setIsCreateDialogOpen(false);
      setCreateForm({ phone: "", client_type: "particular" });
    } catch (error) {
      console.error("Error creating user:", error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deletingUser) return;

    setIsDeleting(true);
    try {
      await api.deleteUser(deletingUser.id);
      setUsers((prev) => prev.filter((u) => u.id !== deletingUser.id));
      setIsDeleteDialogOpen(false);
      setDeletingUser(null);
    } catch (error) {
      console.error("Error deleting user:", error);
    } finally {
      setIsDeleting(false);
    }
  };

  const getClientTypeBadge = (clientType: ClientType) => {
    if (clientType === "professional") {
      return (
        <Badge variant="default" className="bg-blue-600 hover:bg-blue-700">
          <Building2 className="h-3 w-3 mr-1" />
          Profesional
        </Badge>
      );
    }
    return (
      <Badge variant="secondary">
        <User className="h-3 w-3 mr-1" />
        Particular
      </Badge>
    );
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Usuarios</h1>
          <p className="text-muted-foreground">
            Gestion de usuarios de MSI Automotive
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Users className="h-5 w-5 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">
              {filteredUsers.length} usuarios
            </span>
          </div>
          <Button onClick={() => setIsCreateDialogOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Nuevo Usuario
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Lista de Usuarios</CardTitle>
          <CardDescription>
            Todos los usuarios que han contactado a traves de WhatsApp
          </CardDescription>
          <div className="flex gap-4 mt-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Buscar por nombre, telefono, email, NIF/CIF..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
              />
            </div>
            <Select
              value={clientTypeFilter}
              onValueChange={setClientTypeFilter}
            >
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Tipo de usuario" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="particular">Particular</SelectItem>
                <SelectItem value="professional">Profesional</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-pulse text-muted-foreground">
                Cargando usuarios...
              </div>
            </div>
          ) : filteredUsers.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <Users className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <p className="text-muted-foreground">
                {searchQuery || clientTypeFilter !== "all"
                  ? "No se encontraron usuarios con esos criterios"
                  : "No hay usuarios registrados aun"}
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nombre</TableHead>
                  <TableHead>Telefono</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Empresa</TableHead>
                  <TableHead>NIF/CIF</TableHead>
                  <TableHead>Ultima Actividad</TableHead>
                  <TableHead>Registro</TableHead>
                  <TableHead className="w-[80px]">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredUsers.map((user) => (
                  <TableRow
                    key={user.id}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => router.push(`/users/${user.id}`)}
                  >
                    <TableCell>
                      <div className="font-medium">
                        {user.first_name || user.last_name
                          ? `${user.first_name || ""} ${user.last_name || ""}`.trim()
                          : "-"}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{user.phone}</Badge>
                    </TableCell>
                    <TableCell>
                      {getClientTypeBadge(user.client_type)}
                    </TableCell>
                    <TableCell>{user.email || "-"}</TableCell>
                    <TableCell>{user.company_name || "-"}</TableCell>
                    <TableCell>{user.nif_cif || "-"}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatDate(user.last_activity_at || user.created_at)}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatDate(user.created_at)}
                    </TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => openEditDialog(user)}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => {
                            setDeletingUser(user);
                            setIsDeleteDialogOpen(true);
                          }}
                          className="text-destructive hover:text-destructive"
                        >
                          <Trash2 className="h-4 w-4" />
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

      {/* Edit User Dialog */}
      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Editar Usuario</DialogTitle>
            <DialogDescription>
              Modifica los datos del usuario. El telefono no se puede cambiar.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="phone" className="text-right">
                Telefono
              </Label>
              <Input
                id="phone"
                value={editingUser?.phone || ""}
                disabled
                className="col-span-3"
              />
            </div>

            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="client_type" className="text-right">
                Tipo
              </Label>
              <Select
                value={editForm.client_type || "particular"}
                onValueChange={(value: ClientType) =>
                  setEditForm((prev) => ({ ...prev, client_type: value }))
                }
              >
                <SelectTrigger className="col-span-3">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="particular">Particular</SelectItem>
                  <SelectItem value="professional">Profesional</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="first_name" className="text-right">
                Nombre
              </Label>
              <Input
                id="first_name"
                value={editForm.first_name || ""}
                onChange={(e) =>
                  setEditForm((prev) => ({ ...prev, first_name: e.target.value }))
                }
                className="col-span-3"
              />
            </div>

            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="last_name" className="text-right">
                Apellidos
              </Label>
              <Input
                id="last_name"
                value={editForm.last_name || ""}
                onChange={(e) =>
                  setEditForm((prev) => ({ ...prev, last_name: e.target.value }))
                }
                className="col-span-3"
              />
            </div>

            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="email" className="text-right">
                Email
              </Label>
              <Input
                id="email"
                type="email"
                value={editForm.email || ""}
                onChange={(e) =>
                  setEditForm((prev) => ({ ...prev, email: e.target.value }))
                }
                className="col-span-3"
              />
            </div>

            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="company_name" className="text-right">
                Empresa
              </Label>
              <Input
                id="company_name"
                value={editForm.company_name || ""}
                onChange={(e) =>
                  setEditForm((prev) => ({ ...prev, company_name: e.target.value }))
                }
                className="col-span-3"
              />
            </div>

            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="nif_cif" className="text-right">
                NIF/CIF
              </Label>
              <Input
                id="nif_cif"
                value={editForm.nif_cif || ""}
                onChange={(e) =>
                  setEditForm((prev) => ({ ...prev, nif_cif: e.target.value }))
                }
                className="col-span-3"
              />
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
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Nuevo Usuario</DialogTitle>
            <DialogDescription>
              Crea un nuevo usuario manualmente.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="create_phone" className="text-right">
                Telefono *
              </Label>
              <Input
                id="create_phone"
                value={createForm.phone}
                onChange={(e) =>
                  setCreateForm((prev) => ({ ...prev, phone: e.target.value }))
                }
                placeholder="+34612345678"
                className="col-span-3"
              />
            </div>

            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="create_client_type" className="text-right">
                Tipo
              </Label>
              <Select
                value={createForm.client_type || "particular"}
                onValueChange={(value: ClientType) =>
                  setCreateForm((prev) => ({ ...prev, client_type: value }))
                }
              >
                <SelectTrigger className="col-span-3">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="particular">Particular</SelectItem>
                  <SelectItem value="professional">Profesional</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="create_first_name" className="text-right">
                Nombre
              </Label>
              <Input
                id="create_first_name"
                value={createForm.first_name || ""}
                onChange={(e) =>
                  setCreateForm((prev) => ({ ...prev, first_name: e.target.value }))
                }
                className="col-span-3"
              />
            </div>

            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="create_last_name" className="text-right">
                Apellidos
              </Label>
              <Input
                id="create_last_name"
                value={createForm.last_name || ""}
                onChange={(e) =>
                  setCreateForm((prev) => ({ ...prev, last_name: e.target.value }))
                }
                className="col-span-3"
              />
            </div>

            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="create_email" className="text-right">
                Email
              </Label>
              <Input
                id="create_email"
                type="email"
                value={createForm.email || ""}
                onChange={(e) =>
                  setCreateForm((prev) => ({ ...prev, email: e.target.value }))
                }
                className="col-span-3"
              />
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
            <Button onClick={handleCreate} disabled={isSaving || !createForm.phone}>
              {isSaving ? "Creando..." : "Crear Usuario"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete User AlertDialog */}
      <AlertDialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Eliminar Usuario</AlertDialogTitle>
            <AlertDialogDescription>
              Esta seguro de eliminar a{" "}
              <span className="font-medium">
                {deletingUser?.first_name || deletingUser?.last_name
                  ? `${deletingUser.first_name || ""} ${deletingUser.last_name || ""}`.trim()
                  : deletingUser?.phone}
              </span>
              ? Esta accion no se puede deshacer.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>Cancelar</AlertDialogCancel>
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
    </div>
  );
}
