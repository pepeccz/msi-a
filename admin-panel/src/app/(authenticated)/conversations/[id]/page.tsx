"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
  Calendar,
  MessageSquare,
  ExternalLink,
  Clock,
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

  const [conversation, setConversation] = useState<ConversationHistory | null>(null);
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
    <div className="p-4 space-y-3">
      {/* Header bar — everything in one dense row */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={() => router.back()}>
          <ArrowLeft className="h-4 w-4" />
        </Button>

        <div className="flex items-center gap-2 min-w-0 flex-1">
          <h1 className="text-lg font-semibold shrink-0">
            Conversacion #{conversation.conversation_id}
          </h1>

          {conversation.ended_at ? (
            <Badge variant="outline" className="shrink-0">Finalizada</Badge>
          ) : (
            <Badge variant="default" className="shrink-0">Activa</Badge>
          )}

          <Badge variant="secondary" className="shrink-0">
            {conversation.message_count} msg
          </Badge>

          {/* Meta info */}
          <div className="hidden md:flex items-center gap-3 text-xs text-muted-foreground ml-2">
            <span className="flex items-center gap-1">
              <Calendar className="h-3 w-3" />
              {formatDateTime(conversation.started_at)}
            </span>
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {getTimeDuration(conversation.started_at, conversation.ended_at)}
            </span>
            {conversation.user_name && (
              <Link
                href={`/users/${conversation.user_id}`}
                className="flex items-center gap-1 hover:text-foreground transition-colors"
              >
                <User className="h-3 w-3" />
                {conversation.user_name}
              </Link>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1.5 shrink-0">
          <Button
            variant="outline"
            size="sm"
            className="h-8"
            onClick={() => window.open(conversation.chatwoot_url, "_blank")}
          >
            <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
            Chatwoot
          </Button>
          <Button
            variant="destructive"
            size="sm"
            className="h-8"
            onClick={() => setIsDeleteDialogOpen(true)}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Summary — compact if present */}
      {conversation.summary && (
        <div className="text-sm text-muted-foreground bg-muted/50 rounded-lg px-4 py-2.5 border border-border/50">
          {conversation.summary}
        </div>
      )}

      {/* Messages — full width, no card wrapper */}
      {isLoadingMessages ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground mr-2" />
          <span className="text-sm text-muted-foreground">Cargando mensajes...</span>
        </div>
      ) : messages.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <MessageSquare className="h-10 w-10 text-muted-foreground/50 mb-3" />
          <p className="text-sm text-muted-foreground">
            No hay mensajes almacenados para esta conversacion
          </p>
        </div>
      ) : (
        <div className="space-y-3 max-w-3xl mx-auto">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-2.5 ${
                msg.role === "assistant" ? "" : "flex-row-reverse"
              }`}
            >
              {/* Avatar */}
              <div
                className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
                  msg.role === "assistant"
                    ? "bg-primary/10 text-primary"
                    : "bg-secondary text-secondary-foreground"
                }`}
              >
                {msg.role === "assistant" ? (
                  <Bot className="h-4 w-4" />
                ) : (
                  <User className="h-4 w-4" />
                )}
              </div>

              {/* Message Bubble */}
              <div
                className={`flex-1 max-w-[80%] ${
                  msg.role === "assistant" ? "mr-auto" : "ml-auto"
                }`}
              >
                <div
                  className={`rounded-lg px-3.5 py-2.5 ${
                    msg.role === "assistant"
                      ? "bg-muted"
                      : "bg-primary text-primary-foreground"
                  }`}
                >
                  <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">
                    {msg.content}
                  </p>
                  {msg.has_images && (
                    <div
                      className={`mt-1.5 flex items-center gap-1 text-xs ${
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
                  {formatTime(msg.created_at)}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

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
