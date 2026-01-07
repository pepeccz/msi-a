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
import { MessageSquare } from "lucide-react";
import api from "@/lib/api";
import type { ConversationHistory } from "@/lib/types";

export default function ConversationsPage() {
  const [conversations, setConversations] = useState<ConversationHistory[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function fetchConversations() {
      try {
        const data = await api.getConversations({ limit: 50 });
        setConversations(data.items);
      } catch (error) {
        console.error("Error fetching conversations:", error);
      } finally {
        setIsLoading(false);
      }
    }
    fetchConversations();
  }, []);

  const formatDateTime = (dateString: string) => {
    return new Date(dateString).toLocaleString("es-ES", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Conversaciones</h1>
          <p className="text-muted-foreground">
            Historial de conversaciones con clientes
          </p>
        </div>
        <div className="flex items-center gap-2">
          <MessageSquare className="h-5 w-5 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">
            {conversations.length} conversaciones
          </span>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Historial de Conversaciones</CardTitle>
          <CardDescription>
            Todas las conversaciones procesadas por el agente MSI-a
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-pulse text-muted-foreground">
                Cargando conversaciones...
              </div>
            </div>
          ) : conversations.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <MessageSquare className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <p className="text-muted-foreground">
                No hay conversaciones registradas aun
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID Conversacion</TableHead>
                  <TableHead>Inicio</TableHead>
                  <TableHead>Fin</TableHead>
                  <TableHead>Mensajes</TableHead>
                  <TableHead>Resumen</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {conversations.map((conversation) => (
                  <TableRow key={conversation.id}>
                    <TableCell>
                      <Badge variant="outline">
                        {conversation.conversation_id.slice(0, 12)}...
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {formatDateTime(conversation.started_at)}
                    </TableCell>
                    <TableCell>
                      {conversation.ended_at
                        ? formatDateTime(conversation.ended_at)
                        : "-"}
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">
                        {conversation.message_count}
                      </Badge>
                    </TableCell>
                    <TableCell className="max-w-xs truncate">
                      {conversation.summary || "-"}
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
