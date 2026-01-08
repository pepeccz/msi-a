"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
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
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Settings, AlertTriangle, Loader2 } from "lucide-react";
import api from "@/lib/api";
import type { SystemSetting } from "@/lib/types";

export default function ConfigPage() {
  const [settings, setSettings] = useState<SystemSetting[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Panic button state
  const [agentEnabled, setAgentEnabled] = useState(true);
  const [disabledMessage, setDisabledMessage] = useState("");
  const [originalMessage, setOriginalMessage] = useState("");
  const [isUpdating, setIsUpdating] = useState(false);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);

  useEffect(() => {
    async function fetchSettings() {
      try {
        const data = await api.getSystemSettings();
        setSettings(data.items);

        // Extract panic button settings
        const agentSetting = data.items.find((s) => s.key === "agent_enabled");
        const messageSetting = data.items.find(
          (s) => s.key === "agent_disabled_message"
        );

        setAgentEnabled(agentSetting?.value === "true");
        setDisabledMessage(messageSetting?.value || "");
        setOriginalMessage(messageSetting?.value || "");
      } catch (error) {
        console.error("Error fetching settings:", error);
        toast.error("Error al cargar la configuracion");
      } finally {
        setIsLoading(false);
      }
    }
    fetchSettings();
  }, []);

  // Handle switch toggle - show confirmation only when disabling
  async function handleToggleAgent(checked: boolean) {
    if (!checked) {
      // Disabling - show confirmation dialog
      setShowConfirmDialog(true);
      return;
    }

    // Enabling - proceed directly
    await performToggle(true);
  }

  // Perform the actual toggle after confirmation
  async function performToggle(enabled: boolean) {
    setIsUpdating(true);
    try {
      await api.updateSystemSetting("agent_enabled", enabled);
      setAgentEnabled(enabled);

      // Update local settings list
      setSettings((prev) =>
        prev.map((s) =>
          s.key === "agent_enabled"
            ? { ...s, value: enabled ? "true" : "false" }
            : s
        )
      );

      toast.success(enabled ? "Agente activado" : "Agente desactivado");
    } catch (error) {
      console.error("Error toggling agent:", error);
      toast.error("Error al cambiar el estado del agente");
    } finally {
      setIsUpdating(false);
      setShowConfirmDialog(false);
    }
  }

  // Save disabled message
  async function handleSaveMessage() {
    if (disabledMessage.length > 500) {
      toast.error("El mensaje no puede superar los 500 caracteres");
      return;
    }

    if (disabledMessage.trim().length === 0) {
      toast.error("El mensaje no puede estar vacio");
      return;
    }

    setIsUpdating(true);
    try {
      await api.updateSystemSetting("agent_disabled_message", disabledMessage);
      setOriginalMessage(disabledMessage);

      // Update local settings list
      setSettings((prev) =>
        prev.map((s) =>
          s.key === "agent_disabled_message"
            ? { ...s, value: disabledMessage }
            : s
        )
      );

      toast.success("Mensaje actualizado");
    } catch (error) {
      console.error("Error saving message:", error);
      toast.error("Error al guardar el mensaje");
    } finally {
      setIsUpdating(false);
    }
  }

  // Filter out panic button settings from the general settings table
  const otherSettings = settings.filter(
    (s) => s.key !== "agent_enabled" && s.key !== "agent_disabled_message"
  );

  return (
    <div className="space-y-6">
      {/* Panic Button Card - Highlighted */}
      <Card
        className={
          agentEnabled
            ? "border-green-200 bg-green-50/30"
            : "border-red-300 bg-red-50/50"
        }
      >
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <AlertTriangle
                  className={`h-5 w-5 ${
                    agentEnabled ? "text-green-600" : "text-red-600"
                  }`}
                />
                Modo de Emergencia
              </CardTitle>
              <CardDescription>
                Desactiva temporalmente el agente automatico
              </CardDescription>
            </div>
            <Badge variant={agentEnabled ? "default" : "destructive"}>
              {agentEnabled ? "ACTIVO" : "DESACTIVADO"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <>
              {/* Switch for agent enabled */}
              <div className="flex items-start gap-3">
                <Switch
                  id="agent-enabled"
                  checked={agentEnabled}
                  onCheckedChange={handleToggleAgent}
                  disabled={isUpdating}
                />
                <div className="flex-1">
                  <Label
                    htmlFor="agent-enabled"
                    className="text-base font-medium cursor-pointer"
                  >
                    Agente Automatico
                  </Label>
                  <p className="text-sm text-muted-foreground">
                    {agentEnabled
                      ? "El agente responde automaticamente a los mensajes de WhatsApp"
                      : "Los mensajes reciben una respuesta automatica y se escalan a humanos"}
                  </p>
                </div>
              </div>

              {/* Custom message editor */}
              <div className="space-y-2 border-t pt-4">
                <Label htmlFor="disabled-message">
                  Mensaje cuando esta desactivado
                </Label>
                <Textarea
                  id="disabled-message"
                  value={disabledMessage}
                  onChange={(e) => setDisabledMessage(e.target.value)}
                  placeholder="Escribe el mensaje que veran los clientes cuando el agente este desactivado..."
                  rows={4}
                  maxLength={500}
                  disabled={isUpdating}
                  className="resize-none"
                />
                <div className="flex justify-between items-center">
                  <p className="text-xs text-muted-foreground">
                    {disabledMessage.length} / 500 caracteres
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleSaveMessage}
                    disabled={
                      isUpdating || disabledMessage === originalMessage
                    }
                  >
                    {isUpdating ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Guardando...
                      </>
                    ) : (
                      "Guardar mensaje"
                    )}
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Confirmation Dialog for Disabling Agent */}
      <AlertDialog open={showConfirmDialog} onOpenChange={setShowConfirmDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-red-600" />
              Desactivar el agente?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Los clientes recibiran un mensaje automatico y sus consultas
              quedaran pendientes para atencion humana. Se creara una escalacion
              por cada conversacion nueva.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isUpdating}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => performToggle(false)}
              disabled={isUpdating}
              className="bg-red-600 hover:bg-red-700"
            >
              {isUpdating ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Desactivando...
                </>
              ) : (
                "Desactivar agente"
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Other System Settings Card */}
      <Card>
        <CardHeader>
          <CardTitle>Configuracion del Sistema</CardTitle>
          <CardDescription>
            Otros parametros de configuracion del agente y el sistema
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : otherSettings.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <Settings className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <p className="text-muted-foreground">
                No hay otras configuraciones definidas
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Clave</TableHead>
                  <TableHead>Valor</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Descripcion</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {otherSettings.map((setting) => (
                  <TableRow key={setting.id}>
                    <TableCell>
                      <code className="text-sm bg-muted px-1 py-0.5 rounded">
                        {setting.key}
                      </code>
                    </TableCell>
                    <TableCell className="font-mono text-sm max-w-xs truncate">
                      {setting.value}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{setting.value_type}</Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground max-w-xs truncate">
                      {setting.description || "-"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
