"use client";

import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Globe } from "lucide-react";
import api from "@/lib/api";
import type { AdditionalService, AdditionalServiceCreate, AdditionalServiceUpdate } from "@/lib/types";

interface ServiceFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  service: AdditionalService | null;
  categoryId: string | null;
  defaultSortOrder?: number;
  onSuccess: () => void;
}

export function ServiceFormDialog({
  open,
  onOpenChange,
  service,
  categoryId,
  defaultSortOrder = 0,
  onSuccess,
}: ServiceFormDialogProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [formData, setFormData] = useState({
    code: "",
    name: "",
    description: "",
    price: "",
    is_active: true,
    sort_order: defaultSortOrder,
    is_global: false,
  });

  useEffect(() => {
    if (service) {
      setFormData({
        code: service.code,
        name: service.name,
        description: service.description || "",
        price: service.price.toString(),
        is_active: service.is_active,
        sort_order: service.sort_order,
        is_global: service.category_id === null,
      });
    } else {
      setFormData({
        code: "",
        name: "",
        description: "",
        price: "",
        is_active: true,
        sort_order: defaultSortOrder,
        is_global: false,
      });
    }
  }, [service, defaultSortOrder]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      const effectiveCategoryId = formData.is_global ? null : categoryId;

      if (service) {
        const updateData: AdditionalServiceUpdate = {
          code: formData.code,
          name: formData.name,
          description: formData.description || null,
          price: parseFloat(formData.price),
          is_active: formData.is_active,
          sort_order: formData.sort_order,
          category_id: effectiveCategoryId,
        };
        await api.updateAdditionalService(service.id, updateData);
      } else {
        const createData: AdditionalServiceCreate = {
          code: formData.code,
          name: formData.name,
          description: formData.description || null,
          price: parseFloat(formData.price),
          is_active: formData.is_active,
          sort_order: formData.sort_order,
          category_id: effectiveCategoryId,
        };
        await api.createAdditionalService(createData);
      }

      onSuccess();
      onOpenChange(false);
    } catch (error) {
      console.error("Error saving service:", error);
      alert("Error al guardar el servicio");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            {service ? "Editar Servicio" : "Nuevo Servicio"}
          </DialogTitle>
          <DialogDescription>
            {service
              ? "Modifica los datos del servicio adicional"
              : "Crea un nuevo servicio adicional"}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="code">Codigo</Label>
            <Input
              id="code"
              value={formData.code}
              onChange={(e) => setFormData({ ...formData, code: e.target.value })}
              placeholder="CERT_TALLER"
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="name">Nombre</Label>
            <Input
              id="name"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="Certificado de taller"
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="description">Descripcion</Label>
            <Textarea
              id="description"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="Descripcion del servicio..."
              rows={2}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="price">Precio (EUR)</Label>
              <Input
                id="price"
                type="number"
                step="0.01"
                min="0"
                value={formData.price}
                onChange={(e) => setFormData({ ...formData, price: e.target.value })}
                placeholder="85.00"
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="sort_order">Orden</Label>
              <Input
                id="sort_order"
                type="number"
                value={formData.sort_order}
                onChange={(e) => setFormData({ ...formData, sort_order: parseInt(e.target.value) || 0 })}
              />
            </div>
          </div>

          <div className="flex items-center justify-between py-2 px-3 bg-muted/50 rounded-lg">
            <div className="flex items-center gap-2">
              <Globe className="h-4 w-4 text-muted-foreground" />
              <div>
                <Label htmlFor="is_global" className="text-sm font-medium cursor-pointer">
                  Servicio Global
                </Label>
                <p className="text-xs text-muted-foreground">
                  Disponible en todas las categorias
                </p>
              </div>
            </div>
            <Switch
              id="is_global"
              checked={formData.is_global}
              onCheckedChange={(checked) => setFormData({ ...formData, is_global: checked })}
            />
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Switch
                id="is_active"
                checked={formData.is_active}
                onCheckedChange={(checked) => setFormData({ ...formData, is_active: checked })}
              />
              <Label htmlFor="is_active">Activo</Label>
            </div>
            {formData.is_global && (
              <Badge variant="secondary" className="gap-1">
                <Globe className="h-3 w-3" />
                Global
              </Badge>
            )}
          </div>

          <div className="flex justify-end gap-2 pt-4">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={isLoading}>
              {isLoading ? "Guardando..." : service ? "Guardar" : "Crear"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
