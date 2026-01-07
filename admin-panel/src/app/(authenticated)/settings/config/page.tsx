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
import { Badge } from "@/components/ui/badge";
import { Settings } from "lucide-react";
import api from "@/lib/api";
import type { SystemSetting } from "@/lib/types";

export default function ConfigPage() {
  const [settings, setSettings] = useState<SystemSetting[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function fetchSettings() {
      try {
        const data = await api.getSystemSettings();
        setSettings(data.items);
      } catch (error) {
        console.error("Error fetching settings:", error);
      } finally {
        setIsLoading(false);
      }
    }
    fetchSettings();
  }, []);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Configuracion del Sistema</CardTitle>
          <CardDescription>
            Parametros de configuracion del agente y el sistema
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-pulse text-muted-foreground">
                Cargando configuracion...
              </div>
            </div>
          ) : settings.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <Settings className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <p className="text-muted-foreground">
                No hay configuraciones definidas
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
                {settings.map((setting) => (
                  <TableRow key={setting.id}>
                    <TableCell>
                      <code className="text-sm bg-muted px-1 py-0.5 rounded">
                        {setting.key}
                      </code>
                    </TableCell>
                    <TableCell className="font-mono text-sm">
                      {setting.value}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{setting.value_type}</Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
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
