"use client";

import { useEffect, useState, useCallback } from "react";
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
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
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
import {
  ArrowLeft,
  User,
  Phone,
  Calendar,
  MessageSquare,
  ExternalLink,
  Clock,
  FileText,
  Hash,
  Image as ImageIcon,
  Bot,
  Loader2,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import type { ConversationHistory, ConversationMessage } from "@/lib/types";

export default function ConversationDetailPage() {
  const params = useParams();
  const router = useRouter();
  const conversationId = params.id as string;

  const [conversation, setConversation] = useState<ConversationHistory | null>(
    null
  );
  const [isLoading, setIsLoading] = useState(true);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const fetchConversation = useCallback(async () => {
    try {
      setIsLoading(true);
      const data = await api.getConversation(conversationId);
      setConversation(data);
    } catch (error) {
      console.error("Error fetching conversation:", error);
    } finally {
      setIsLoading(false);
    }
  }, [conversationId]);

  const fetchMessages = useCallback(async () => {
    try {
      setIsLoadingMessages(true);
      const response = await api.getConversationMessages(conversationId, {
        limit: 200,
      });
      setMessages(response.messages);
    } catch (error) {
      console.error("Error fetching messages:", error);
      toast.error("Error al cargar los mensajes");
    } finally {
      setIsLoadingMessages(false);
    }
  }, [conversationId]);

  useEffect(() => {
    fetchConversation();
    fetchMessages();
  }, [fetchConversation, fetchMessages]);

  const handleDeleteConversation = async () => {
    if (!conversation) return;
    setIsDeleting(true);
    try {
      await api.deleteConversation(conversation.id);
      toast.success("Conversacion eliminada correctamente");
      router.push("/conversations");
    } catch (error) {
      console.error("Error deleting conversation:", error);
      toast.error("Error al eliminar conversacion");
      setIsDeleting(false);
    }
  };

  const formatDateTime = (dateString: string) => {
    return new Date(dateString).toLocaleString("es-ES", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  };

  const formatTime = (dateString: string) => {
    return new Date(dateString).toLocaleTimeString("es-ES", {
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const getTimeDuration = (start: string, end?: string | null) => {
    const startTime = new Date(start).getTime();
    const endTime = end ? new Date(end).getTime() : Date.now();
    const diff = endTime - startTime;

    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));

    if (days > 0) return `${days} dias, ${hours}h ${minutes}m`;
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes} minutos`;
  };

  if (isLoading) {
    return (
      <div className="p-6 flex items-center justify-center min-h-[400px]">
        <div className="animate-pulse text-muted-foreground">
          Cargando conversacion...
        </div>
      </div>
    );
  }

  if (!conversation) {
    return (
      <div className="p-6">
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <MessageSquare className="h-12 w-12 text-muted-foreground/50 mb-4" />
          <p className="text-muted-foreground mb-4">
            Conversacion no encontrada
          </p>
          <Button variant="outline" onClick={() => router.back()}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            Volver
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => router.back()}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
              <MessageSquare className="h-6 w-6" />
              Conversacion #{conversation.conversation_id}
            </h1>
            <p className="text-muted-foreground">
              Detalles de la conversacion
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => window.open(conversation.chatwoot_url, "_blank")}
          >
            <ExternalLink className="h-4 w-4 mr-2" />
            Abrir en Chatwoot
          </Button>
          <Button
            variant="destructive"
            onClick={() => setIsDeleteDialogOpen(true)}
          >
            <Trash2 className="h-4 w-4 mr-2" />
            Eliminar
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content - 2 columns */}
        <div className="lg:col-span-2 space-y-6">
          {/* Conversation Info Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <MessageSquare className="h-5 w-5" />
                Informacion de la Conversacion
              </CardTitle>
              <CardDescription>
                Datos generales de la conversacion
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Status */}
              <div className="flex gap-2">
                <Badge variant="secondary">
                  <MessageSquare className="h-3 w-3 mr-1" />
                  {conversation.message_count} mensajes
                </Badge>
                {conversation.ended_at ? (
                  <Badge variant="outline">Finalizada</Badge>
                ) : (
                  <Badge variant="default">Activa</Badge>
                )}
              </div>

              <Separator />

              {/* Time Information */}
              <div className="grid grid-cols-2 gap-6">
                <div className="space-y-1">
                  <p className="text-sm text-muted-foreground flex items-center gap-1">
                    <Calendar className="h-3 w-3" />
                    Fecha de inicio
                  </p>
                  <p className="font-medium">
                    {formatDateTime(conversation.started_at)}
                  </p>
                </div>

                <div className="space-y-1">
                  <p className="text-sm text-muted-foreground flex items-center gap-1">
                    <Calendar className="h-3 w-3" />
                    {conversation.ended_at ? "Fecha de fin" : "Duracion"}
                  </p>
                  <p className="font-medium">
                    {conversation.ended_at
                      ? formatDateTime(conversation.ended_at)
                      : getTimeDuration(conversation.started_at)}
                  </p>
                </div>

                {conversation.ended_at && (
                  <div className="space-y-1">
                    <p className="text-sm text-muted-foreground flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      Duracion total
                    </p>
                    <p className="font-medium">
                      {getTimeDuration(
                        conversation.started_at,
                        conversation.ended_at
                      )}
                    </p>
                  </div>
                )}
              </div>

              {/* Summary */}
              {conversation.summary && (
                <>
                  <Separator />
                  <div className="space-y-2">
                    <p className="text-sm font-medium flex items-center gap-1">
                      <FileText className="h-4 w-4" />
                      Resumen de la conversacion
                    </p>
                    <p className="text-sm text-muted-foreground whitespace-pre-wrap bg-muted p-4 rounded-lg">
                      {conversation.summary}
                    </p>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          {/* Messages History Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <MessageSquare className="h-5 w-5" />
                Historial de Mensajes
                {messages.length > 0 && (
                  <Badge variant="secondary" className="ml-2">
                    {messages.length}
                  </Badge>
                )}
              </CardTitle>
              <CardDescription>
                Conversacion completa entre el usuario y el agente
              </CardDescription>
            </CardHeader>
            <CardContent>
              {isLoadingMessages ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground mr-2" />
                  <span className="text-muted-foreground">
                    Cargando mensajes...
                  </span>
                </div>
              ) : messages.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-center">
                  <MessageSquare className="h-12 w-12 text-muted-foreground/50 mb-4" />
                  <p className="text-sm text-muted-foreground mb-2">
                    No hay mensajes almacenados para esta conversacion
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Los mensajes solo se almacenan a partir de la nueva
                    implementacion
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  {messages.map((msg, index) => (
                    <div
                      key={msg.id}
                      className={`flex gap-3 ${
                        msg.role === "assistant" ? "" : "flex-row-reverse"
                      }`}
                    >
                      {/* Avatar */}
                      <div
                        className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${
                          msg.role === "assistant"
                            ? "bg-primary/10 text-primary"
                            : "bg-secondary text-secondary-foreground"
                        }`}
                      >
                        {msg.role === "assistant" ? (
                          <Bot className="h-5 w-5" />
                        ) : (
                          <User className="h-5 w-5" />
                        )}
                      </div>

                      {/* Message Bubble */}
                      <div
                        className={`flex-1 max-w-[80%] ${
                          msg.role === "assistant" ? "mr-auto" : "ml-auto"
                        }`}
                      >
                        <div
                          className={`rounded-lg px-4 py-3 ${
                            msg.role === "assistant"
                              ? "bg-muted"
                              : "bg-primary text-primary-foreground"
                          }`}
                        >
                          <p className="whitespace-pre-wrap break-words text-sm">
                            {msg.content}
                          </p>
                          {msg.has_images && (
                            <div
                              className={`mt-2 flex items-center gap-1 text-xs ${
                                msg.role === "assistant"
                                  ? "text-muted-foreground"
                                  : "opacity-80"
                              }`}
                            >
                              <ImageIcon className="h-3 w-3" />
                              {msg.image_count} imagen
                              {msg.image_count !== 1 ? "es" : ""}
                            </div>
                          )}
                        </div>
                        <div
                          className={`text-xs text-muted-foreground mt-1 px-2 ${
                            msg.role === "assistant" ? "text-left" : "text-right"
                          }`}
                        >
                          {formatTime(msg.created_at)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Sidebar - 1 column */}
        <div className="space-y-6">
          {/* User Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <User className="h-4 w-4" />
                Usuario
              </CardTitle>
            </CardHeader>
            <CardContent>
              {conversation.user_id ? (
                <div className="space-y-4">
                  <div className="space-y-2">
                    <p className="font-medium">
                      {conversation.user_name || "Sin nombre"}
                    </p>
                    {conversation.user_phone && (
                      <p className="text-sm text-muted-foreground flex items-center gap-1">
                        <Phone className="h-3 w-3" />
                        {conversation.user_phone}
                      </p>
                    )}
                  </div>
                  <Link href={`/users/${conversation.user_id}`}>
                    <Button variant="outline" size="sm" className="w-full">
                      Ver perfil completo
                    </Button>
                  </Link>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Sin usuario asociado
                </p>
              )}
            </CardContent>
          </Card>

          {/* IDs Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Hash className="h-4 w-4" />
                Identificadores
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">ID interno</p>
                <p className="text-xs font-mono bg-muted p-2 rounded break-all">
                  {conversation.id}
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">ID Chatwoot</p>
                <p className="text-sm font-medium">
                  #{conversation.conversation_id}
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Quick Actions Card */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Acciones rapidas</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <Button
                variant="outline"
                size="sm"
                className="w-full justify-start"
                onClick={() => window.open(conversation.chatwoot_url, "_blank")}
              >
                <ExternalLink className="h-4 w-4 mr-2" />
                Abrir en Chatwoot
              </Button>
              {conversation.user_id && (
                <Link href={`/users/${conversation.user_id}`} className="block">
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full justify-start"
                  >
                    <User className="h-4 w-4 mr-2" />
                    Ver perfil de usuario
                  </Button>
                </Link>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Eliminar Conversacion</AlertDialogTitle>
            <AlertDialogDescription>
              Se eliminara la conversacion #{conversation.conversation_id} y todos sus mensajes asociados.
              Esta accion no se puede deshacer.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConversation}
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
