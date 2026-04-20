"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  Image as ImageIcon,
  Bot,
  Loader2,
  Trash2,
  Hash,
  FileText,
  Search,
  ChevronRight,
} from "lucide-react";
import { sileo } from "sileo";
import api from "@/lib/api";
import type { ConversationHistory, ConversationMessage } from "@/lib/types";

export default function ConversationDetailPage() {
  const params = useParams();
  const router = useRouter();
  const conversationId = params.id as string;

  const [conversation, setConversation] = useState<ConversationHistory | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isMessagesOpen, setIsMessagesOpen] = useState(false);
  const [messageSearch, setMessageSearch] = useState("");

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
      sileo.error({ title: "Error al cargar los mensajes" });
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
      sileo.success({ title: "Conversacion eliminada correctamente" });
      router.push("/conversations");
    } catch (error) {
      console.error("Error deleting conversation:", error);
      sileo.error({ title: "Error al eliminar conversacion" });
      setIsDeleting(false);
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

    if (days > 0) return `${days}d ${hours}h ${minutes}m`;
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
  };

  // Messages sorted newest first, filtered by search
  const filteredMessages = useMemo(() => {
    const sorted = [...messages].reverse();
    if (!messageSearch.trim()) return sorted;
    const q = messageSearch.toLowerCase();
    return sorted.filter((msg) => msg.content.toLowerCase().includes(q));
  }, [messages, messageSearch]);

  // Search match count
  const searchMatchCount = messageSearch.trim()
    ? filteredMessages.length
    : null;

  const imageCount = messages
    .filter((m) => m.has_images)
    .reduce((acc, m) => acc + (m.image_count || 0), 0);

  if (isLoading) {
    return (
      <div className="p-4 sm:p-6 flex items-center justify-center min-h-[400px] max-w-7xl mx-auto">
        <div className="animate-pulse text-muted-foreground">
          Cargando conversacion...
        </div>
      </div>
    );
  }

  if (!conversation) {
    return (
      <div className="p-4 sm:p-6 max-w-7xl mx-auto">
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <MessageSquare className="h-12 w-12 text-muted-foreground/50 mb-4" />
          <p className="text-muted-foreground mb-4">Conversacion no encontrada</p>
          <Button variant="outline" onClick={() => router.back()}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            Volver
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-5 max-w-7xl mx-auto">
      {/* ================================================================
          HEADER — compact, all key info in one strip
          ================================================================ */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <Button
            variant="ghost"
            size="sm"
            className="mt-0.5 shrink-0"
            onClick={() => router.back()}
          >
            <ArrowLeft className="h-4 w-4 mr-1" />
            <span className="hidden sm:inline">Volver</span>
          </Button>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight">
                Conversacion #{conversation.conversation_id}
              </h1>
              {conversation.ended_at ? (
                <Badge variant="outline">Finalizada</Badge>
              ) : (
                <Badge variant="default">Activa</Badge>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-1 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                Iniciada {formatDateTime(conversation.started_at)}
              </span>
              <span className="hidden sm:inline">·</span>
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {getTimeDuration(conversation.started_at, conversation.ended_at)}
              </span>
              <span className="hidden sm:inline">·</span>
              <span className="font-medium text-foreground">
                {messages.length} mensaje{messages.length !== 1 ? "s" : ""}
              </span>
              {imageCount > 0 && (
                <>
                  <span className="hidden sm:inline">·</span>
                  <span>
                    {imageCount} imagen{imageCount !== 1 ? "es" : ""}
                  </span>
                </>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Button
            variant="outline"
            size="sm"
            onClick={() => window.open(conversation.chatwoot_url, "_blank")}
          >
            <ExternalLink className="h-4 w-4" />
            <span className="ml-1.5 hidden sm:inline">Chatwoot</span>
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8 text-destructive hover:text-destructive"
            onClick={() => setIsDeleteDialogOpen(true)}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* ================================================================
          MAIN CONTENT — 2 columns (data left, user + messages right)
          ================================================================ */}
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        {/* Left — Conversation data */}
        <Card>
          <CardHeader className="py-2.5 px-4 flex-row items-center justify-between space-y-0">
            <div className="flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-muted-foreground" />
              <CardTitle className="text-sm font-medium">
                Datos de la conversacion
              </CardTitle>
            </div>
          </CardHeader>
          <CardContent className="px-4 pb-4 pt-0 space-y-4">
            <div className="grid gap-4 grid-cols-2 sm:grid-cols-3">
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  <Calendar className="h-3 w-3" />
                  Inicio
                </p>
                <p className="text-sm font-medium">
                  {formatDateTime(conversation.started_at)}
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  <Calendar className="h-3 w-3" />
                  {conversation.ended_at ? "Fin" : "Estado"}
                </p>
                <p className="text-sm font-medium">
                  {conversation.ended_at
                    ? formatDateTime(conversation.ended_at)
                    : "En curso"}
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  Duracion
                </p>
                <p className="text-sm font-medium">
                  {getTimeDuration(
                    conversation.started_at,
                    conversation.ended_at
                  )}
                </p>
              </div>
            </div>

            <Separator />

            <div className="grid gap-4 grid-cols-2 sm:grid-cols-3">
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  <MessageSquare className="h-3 w-3" />
                  Mensajes
                </p>
                <p className="text-sm font-medium">{messages.length}</p>
              </div>
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  <ImageIcon className="h-3 w-3" />
                  Imagenes
                </p>
                <p className="text-sm font-medium">{imageCount}</p>
              </div>
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  <Hash className="h-3 w-3" />
                  Chatwoot ID
                </p>
                <p className="text-sm font-medium font-mono">
                  #{conversation.conversation_id}
                </p>
              </div>
            </div>

            {conversation.summary && (
              <>
                <Separator />
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground flex items-center gap-1">
                    <FileText className="h-3 w-3" />
                    Resumen
                  </p>
                  <p className="text-sm text-muted-foreground whitespace-pre-wrap bg-muted/50 rounded px-3 py-2">
                    {conversation.summary}
                  </p>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Right — User + Messages */}
        <div className="space-y-4">
          {/* User */}
          <Card>
            <CardHeader className="py-2.5 px-4 flex-row items-center justify-between space-y-0">
              <div className="flex items-center gap-2">
                <User className="h-4 w-4 text-muted-foreground" />
                <CardTitle className="text-sm font-medium">Usuario</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="px-4 pb-3 pt-0">
              {conversation.user_id ? (
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className="h-9 w-9 rounded-full bg-muted flex items-center justify-center shrink-0">
                      <User className="h-4 w-4 text-muted-foreground" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">
                        {conversation.user_name || "Sin nombre"}
                      </p>
                      {conversation.user_phone && (
                        <p className="text-xs text-muted-foreground flex items-center gap-1">
                          <Phone className="h-3 w-3" />
                          {conversation.user_phone}
                        </p>
                      )}
                    </div>
                  </div>
                  <Link href={`/users/${conversation.user_id}`}>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 text-xs shrink-0"
                    >
                      Ver perfil
                      <ChevronRight className="h-3 w-3 ml-1" />
                    </Button>
                  </Link>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground text-center py-2">
                  Sin usuario asociado
                </p>
              )}
            </CardContent>
          </Card>

          {/* Messages */}
          <Card>
            <CardHeader className="py-2.5 px-4 flex-row items-center justify-between space-y-0">
              <div className="flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-muted-foreground" />
                <CardTitle className="text-sm font-medium">
                  Historial de mensajes
                </CardTitle>
                <Badge variant="secondary" className="text-xs h-5">
                  {messages.length}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="px-4 pb-3 pt-0">
              {isLoadingMessages ? (
                <div className="flex items-center justify-center py-3">
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                </div>
              ) : messages.length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-2">
                  Sin mensajes almacenados
                </p>
              ) : (
                <div className="space-y-2">
                  <p className="text-xs text-muted-foreground">
                    Ultimo:{" "}
                    {formatDateTime(messages[messages.length - 1].created_at)}
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full h-8 text-xs"
                    onClick={() => setIsMessagesOpen(true)}
                  >
                    Abrir historial completo
                    <ChevronRight className="h-3 w-3 ml-1" />
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Messages Modal */}
      <Dialog open={isMessagesOpen} onOpenChange={setIsMessagesOpen}>
        <DialogContent className="max-w-3xl h-[85vh] flex flex-col p-0 gap-0">
          <DialogHeader className="px-4 py-3 border-b shrink-0">
            <div className="flex items-center justify-between gap-3">
              <DialogTitle className="text-base">
                Mensajes — Conversacion #{conversation.conversation_id}
              </DialogTitle>
              <Badge variant="secondary" className="shrink-0">
                {searchMatchCount !== null
                  ? `${searchMatchCount} resultado${searchMatchCount !== 1 ? "s" : ""}`
                  : `${messages.length} mensajes`}
              </Badge>
            </div>
            <div className="relative mt-2">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                value={messageSearch}
                onChange={(e) => setMessageSearch(e.target.value)}
                placeholder="Buscar en mensajes..."
                className="h-8 text-sm pl-8"
              />
            </div>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto px-4 py-3">
            {isLoadingMessages ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground mr-2" />
                <span className="text-sm text-muted-foreground">Cargando mensajes...</span>
              </div>
            ) : filteredMessages.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <MessageSquare className="h-10 w-10 text-muted-foreground/50 mb-3" />
                <p className="text-sm text-muted-foreground">
                  {messageSearch.trim()
                    ? "No se encontraron mensajes con ese texto"
                    : "No hay mensajes almacenados"}
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {filteredMessages.map((msg) => {
                  // Highlight search matches
                  const highlightContent = (content: string) => {
                    if (!messageSearch.trim()) return content;
                    const regex = new RegExp(`(${messageSearch.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, "gi");
                    const parts = content.split(regex);
                    return parts.map((part, i) =>
                      regex.test(part) ? (
                        <mark key={i} className="bg-yellow-200 dark:bg-yellow-800 rounded px-0.5">
                          {part}
                        </mark>
                      ) : (
                        part
                      )
                    );
                  };

                  return (
                    <div
                      key={msg.id}
                      className={`flex gap-2.5 ${
                        msg.role === "assistant" ? "" : "flex-row-reverse"
                      }`}
                    >
                      <div
                        className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center ${
                          msg.role === "assistant"
                            ? "bg-primary/10 text-primary"
                            : "bg-secondary text-secondary-foreground"
                        }`}
                      >
                        {msg.role === "assistant" ? (
                          <Bot className="h-3.5 w-3.5" />
                        ) : (
                          <User className="h-3.5 w-3.5" />
                        )}
                      </div>

                      <div
                        className={`flex-1 max-w-[80%] ${
                          msg.role === "assistant" ? "mr-auto" : "ml-auto"
                        }`}
                      >
                        <div
                          className={`rounded-lg px-3 py-2 ${
                            msg.role === "assistant"
                              ? "bg-muted"
                              : "bg-primary text-primary-foreground"
                          }`}
                        >
                          <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">
                            {highlightContent(msg.content)}
                          </p>
                          {msg.has_images && (
                            <div
                              className={`mt-1 flex items-center gap-1 text-xs ${
                                msg.role === "assistant"
                                  ? "text-muted-foreground"
                                  : "opacity-75"
                              }`}
                            >
                              <ImageIcon className="h-3 w-3" />
                              {msg.image_count} imagen{msg.image_count !== 1 ? "es" : ""}
                            </div>
                          )}
                        </div>
                        <div
                          className={`text-[11px] text-muted-foreground mt-0.5 px-1 ${
                            msg.role === "assistant" ? "text-left" : "text-right"
                          }`}
                        >
                          {formatDateTime(msg.created_at)}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

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
