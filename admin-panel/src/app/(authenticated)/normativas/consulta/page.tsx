"use client";

import { useState, useRef, useEffect } from "react";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Send, Loader2, FileText, ChevronDown, ChevronUp, Clock } from "lucide-react";
import api from "@/lib/api";
import type { RAGQueryResponse, RAGCitation } from "@/lib/types";

// Fallback for crypto.randomUUID in non-secure contexts (HTTP)
function generateId(): string {
  try {
    return crypto.randomUUID();
  } catch {
    // crypto.randomUUID not available in HTTP context
    return `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;
  }
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: RAGCitation[];
  performance?: RAGQueryResponse["performance"];
  timestamp: Date;
}

export default function ConsultaPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [expandedCitations, setExpandedCitations] = useState<Set<string>>(new Set());
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content: input,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await api.ragQuery(input);
      const assistantMessage: Message = {
        id: generateId(),
        role: "assistant",
        content: response.answer,
        citations: response.citations,
        performance: response.performance,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error("Query failed:", error);
      setMessages((prev) => [
        ...prev,
        {
          id: generateId(),
          role: "assistant",
          content: "Error al procesar la consulta. Por favor, intentalo de nuevo.",
          timestamp: new Date(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleCitation = (citationId: string) => {
    setExpandedCitations((prev) => {
      const next = new Set(prev);
      if (next.has(citationId)) {
        next.delete(citationId);
      } else {
        next.add(citationId);
      }
      return next;
    });
  };

  return (
    <div className="max-w-5xl mx-auto space-y-4">
      {/* Chat area */}
      <Card className="p-4 h-[600px] overflow-y-auto">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <FileText className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-muted-foreground font-medium">
              Pregunta sobre normativas de homologacion de vehiculos
            </p>
            <p className="text-sm text-muted-foreground mt-2 max-w-md">
              Ejemplo: &quot;Que dice el RD 2822/1998 sobre faros antiniebla?&quot;
            </p>
            <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-2">
              {[
                "Requisitos para homologar un vehiculo importado",
                "Normativa sobre modificaciones de motor",
                "Documentacion necesaria para reformas de importancia",
                "Plazos para la inspeccion tecnica",
              ].map((example) => (
                <Button
                  key={example}
                  variant="outline"
                  size="sm"
                  className="text-xs justify-start"
                  onClick={() => setInput(example)}
                >
                  {example}
                </Button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {messages.map((msg) => (
              <div key={msg.id} className={msg.role === "user" ? "text-right" : ""}>
                <div
                  className={`inline-block max-w-[85%] p-4 rounded-lg ${
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted"
                  }`}
                >
                  <p className="whitespace-pre-wrap text-sm">{msg.content}</p>

                  {/* Performance metrics for assistant */}
                  {msg.role === "assistant" && msg.performance && (
                    <div className="mt-2 pt-2 border-t border-border/50 flex items-center gap-2 text-xs text-muted-foreground">
                      <Clock className="h-3 w-3" />
                      <span>
                        {msg.performance.cache_hit
                          ? "Cache"
                          : `${msg.performance.total_ms}ms`}
                      </span>
                      {!msg.performance.cache_hit && (
                        <span className="text-muted-foreground/60">
                          (embed: {msg.performance.embedding_ms}ms, busqueda: {msg.performance.retrieval_ms}ms,
                          rerank: {msg.performance.rerank_ms}ms, llm: {msg.performance.llm_ms}ms)
                        </span>
                      )}
                    </div>
                  )}
                </div>

                {/* Citations */}
                {msg.citations && msg.citations.length > 0 && (
                  <div className="mt-3 space-y-2 text-left max-w-[85%] ml-0">
                    <p className="text-sm font-medium text-muted-foreground">
                      Referencias ({msg.citations.length}):
                    </p>
                    {msg.citations.map((citation, citIdx) => {
                      const citationId = `${msg.id}-${citIdx}`;
                      const isExpanded = expandedCitations.has(citationId);
                      return (
                        <Card
                          key={citIdx}
                          className="p-3 cursor-pointer hover:bg-muted/50 transition-colors"
                          onClick={() => toggleCitation(citationId)}
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex-1">
                              <p className="font-medium text-sm">
                                {citation.document_title}
                              </p>
                              {(citation.article_number || citation.section_title) && (
                                <p className="text-xs text-muted-foreground mt-1">
                                  {citation.article_number}
                                  {citation.article_number && citation.section_title && " - "}
                                  {citation.section_title}
                                </p>
                              )}
                              <p className="text-xs text-muted-foreground mt-1">
                                Paginas: {citation.page_numbers.join(", ")} | Relevancia:{" "}
                                {(citation.rerank_score * 100).toFixed(0)}%
                              </p>
                            </div>
                            {isExpanded ? (
                              <ChevronUp className="h-4 w-4 text-muted-foreground ml-2 flex-shrink-0" />
                            ) : (
                              <ChevronDown className="h-4 w-4 text-muted-foreground ml-2 flex-shrink-0" />
                            )}
                          </div>
                          {isExpanded && (
                            <div className="mt-2 pt-2 border-t">
                              <p className="text-xs text-muted-foreground whitespace-pre-wrap">
                                {citation.content_preview}
                              </p>
                            </div>
                          )}
                        </Card>
                      );
                    })}
                  </div>
                )}
              </div>
            ))}
            {isLoading && (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span className="text-sm">Buscando en normativas...</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </Card>

      {/* Input area */}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Pregunta sobre normativas..."
          disabled={isLoading}
          className="flex-1"
        />
        <Button type="submit" disabled={isLoading || !input.trim()}>
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      </form>
    </div>
  );
}
