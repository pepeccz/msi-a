"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MessageSquare, ExternalLink, User, ArrowUpDown } from "lucide-react";
import api from "@/lib/api";
import type { ConversationHistory } from "@/lib/types";
import { ConversationDetailsDialog } from "@/components/conversation-details-dialog";

export default function ConversationsPage() {
  const [conversations, setConversations] = useState<ConversationHistory[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [sortBy, setSortBy] = useState<string>("started_at");
  const [selectedConversation, setSelectedConversation] =
    useState<ConversationHistory | null>(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  const fetchConversations = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await api.getConversations({ limit: 100, sort_by: sortBy });
      setConversations(data.items);
    } catch (error) {
      console.error("Error fetching conversations:", error);
    } finally {
      setIsLoading(false);
    }
  }, [sortBy]);

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  const formatDateTime = (dateString: string) => {
    return new Date(dateString).toLocaleString("es-ES", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const handleRowClick = (conversation: ConversationHistory) => {
    setSelectedConversation(conversation);
    setIsDialogOpen(true);
  };

  const openChatwoot = (
    e: React.MouseEvent,
    conversation: ConversationHistory
  ) => {
    e.stopPropagation();
    window.open(conversation.chatwoot_url, "_blank");
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
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <ArrowUpDown className="h-4 w-4 text-muted-foreground" />
            <Select value={sortBy} onValueChange={setSortBy}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Ordenar por" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="started_at">Fecha de inicio</SelectItem>
                <SelectItem value="last_activity">Ultima actividad</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2">
            <MessageSquare className="h-5 w-5 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">
              {conversations.length} conversaciones
            </span>
          </div>
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
                  <TableHead>Usuario</TableHead>
                  <TableHead>ID Conversacion</TableHead>
                  <TableHead>Inicio</TableHead>
                  <TableHead>Mensajes</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="w-[100px]">Chatwoot</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {conversations.map((conversation) => (
                  <TableRow
                    key={conversation.id}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => handleRowClick(conversation)}
                  >
                    <TableCell>
                      {conversation.user_id ? (
                        <Link
                          href={`/users/${conversation.user_id}`}
                          className="flex items-center gap-2 hover:underline text-primary"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <User className="h-4 w-4" />
                          <span className="truncate max-w-[150px]">
                            {conversation.user_name ||
                              conversation.user_phone ||
                              "Sin nombre"}
                          </span>
                        </Link>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        #{conversation.conversation_id}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm">
                      {formatDateTime(conversation.started_at)}
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">
                        {conversation.message_count}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {conversation.ended_at ? (
                        <Badge variant="outline">Finalizada</Badge>
                      ) : (
                        <Badge variant="default">Activa</Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={(e) => openChatwoot(e, conversation)}
                        title="Abrir en Chatwoot"
                      >
                        <ExternalLink className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <ConversationDetailsDialog
        conversation={selectedConversation}
        isOpen={isDialogOpen}
        onOpenChange={setIsDialogOpen}
      />
    </div>
  );
}
