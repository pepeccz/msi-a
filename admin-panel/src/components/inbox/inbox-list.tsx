"use client";

import { useState, useEffect, useCallback } from "react";
import { Search, MessageSquare, Bot, AlertTriangle, Eye, User } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { es } from "date-fns/locale";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { FilterChips, type FilterChipOption } from "@/components/shared/filter-chips";
import { cn } from "@/lib/utils";
import { useInbox } from "@/hooks/use-inbox";
import type { InboxItemResponse, InboxTab } from "@/lib/types";

interface InboxListProps {
  selectedId: string | null;
  activeTab: InboxTab;
  onSelectConversation: (id: string) => void;
  onTabChange: (tab: InboxTab) => void;
}

const TAB_OPTIONS: FilterChipOption<InboxTab>[] = [
  { value: "todas", label: "Todas" },
  { value: "bot_on", label: "Bot ON" },
  { value: "bot_off", label: "Bot OFF" },
  { value: "escaladas", label: "Escaladas" },
  { value: "no_leidas", label: "No leídas" },
  { value: "mias", label: "Mías" },
];

function getInitials(name: string | null): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0][0]?.toUpperCase() ?? "?";
  return (parts[0][0] + (parts[parts.length - 1][0] ?? "")).toUpperCase();
}

// Deterministic color from a string (phone or id)
function avatarColorClass(seed: string): string {
  const colors = [
    "bg-blue-500",
    "bg-green-600",
    "bg-violet-600",
    "bg-orange-500",
    "bg-teal-600",
    "bg-rose-500",
    "bg-amber-500",
    "bg-indigo-600",
  ];
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = seed.charCodeAt(i) + ((hash << 5) - hash);
  }
  return colors[Math.abs(hash) % colors.length];
}

function formatRelativeTime(iso: string | null): string {
  if (!iso) return "";
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true, locale: es });
  } catch {
    return "";
  }
}

interface ConversationRowProps {
  item: InboxItemResponse;
  isSelected: boolean;
  onClick: () => void;
}

function ConversationRow({ item, isSelected, onClick }: ConversationRowProps) {
  const seed = item.user_phone ?? item.conversation_history_id;
  const colorClass = avatarColorClass(seed);
  const initials = getInitials(item.user_name);
  const hasEscalation = item.escalation_status !== "none";

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full text-left flex items-start gap-3 px-4 py-3 transition-colors border-l-[3px]",
        "hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset",
        isSelected
          ? "bg-muted/60 border-l-primary"
          : hasEscalation
            ? "border-l-red-400"
            : "border-l-transparent",
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-semibold",
          colorClass,
        )}
        aria-hidden
      >
        {initials}
      </div>

      {/* Main content */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-1">
          <span className="text-sm font-medium truncate">
            {item.user_name ?? item.user_phone ?? "Sin nombre"}
          </span>
          <span className="text-xs text-muted-foreground flex-shrink-0 ml-1">
            {formatRelativeTime(item.last_message_at)}
          </span>
        </div>

        {/* Phone if name is shown */}
        {item.user_name && item.user_phone && (
          <p className="text-xs text-muted-foreground truncate">
            {item.user_phone}
          </p>
        )}

        {/* Message preview */}
        <p className="text-xs text-muted-foreground truncate mt-0.5 leading-snug">
          {item.last_message_preview ?? "Sin mensajes"}
        </p>

        {/* Badges row */}
        <div className="flex flex-wrap items-center gap-1 mt-1">
          {/* Unread count */}
          {item.unread_count > 0 && (
            <Badge className="h-4 px-1.5 text-[10px] bg-primary text-primary-foreground">
              {item.unread_count}
            </Badge>
          )}

          {/* Bot status */}
          {item.bot_status === "paused" && (
            <Badge variant="outline" className="h-4 px-1.5 text-[10px] gap-0.5 text-yellow-700 border-yellow-400">
              <Bot className="h-2.5 w-2.5" />
              Pausado
            </Badge>
          )}
          {item.bot_status === "off_global" && (
            <Badge variant="outline" className="h-4 px-1.5 text-[10px] gap-0.5 text-muted-foreground">
              <Bot className="h-2.5 w-2.5" />
              OFF
            </Badge>
          )}

          {/* Escalation */}
          {item.escalation_status === "pending" && (
            <Badge variant="outline" className="h-4 px-1.5 text-[10px] gap-0.5 text-red-600 border-red-400">
              <AlertTriangle className="h-2.5 w-2.5" />
              Escalada
            </Badge>
          )}
          {item.escalation_status === "in_progress" && (
            <Badge variant="outline" className="h-4 px-1.5 text-[10px] gap-0.5 text-orange-600 border-orange-400">
              <AlertTriangle className="h-2.5 w-2.5" />
              En gestión
            </Badge>
          )}
        </div>

        {/* Paused by */}
        {item.paused_by_user_name && item.bot_status === "paused" && (
          <p className="text-[10px] text-yellow-700 mt-0.5 flex items-center gap-0.5">
            <User className="h-2.5 w-2.5" />
            Pausada por {item.paused_by_user_name}
          </p>
        )}
      </div>
    </button>
  );
}

export function InboxList({
  selectedId,
  activeTab,
  onSelectConversation,
  onTabChange,
}: InboxListProps) {
  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");

  // Debounce search 300ms
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchInput), 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const { data, isLoading, error } = useInbox({
    tab: activeTab,
    search: debouncedSearch || undefined,
    page: 1,
    page_size: 50,
  });

  const tabsWithCounts: FilterChipOption<InboxTab>[] = TAB_OPTIONS.map(
    (opt) => ({
      ...opt,
      count: opt.value === activeTab ? data?.total : undefined,
    }),
  );

  const handleTabChange = useCallback(
    (val: InboxTab | null) => {
      onTabChange(val ?? "todas");
    },
    [onTabChange],
  );

  return (
    <div className="flex flex-col h-full">
      {/* Header: search + total */}
      <div className="flex-shrink-0 px-4 pt-4 pb-2 space-y-2">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground pointer-events-none" />
            <Input
              aria-label="Buscar conversaciones"
              placeholder="Buscar..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="pl-8 h-8 text-sm"
            />
          </div>
          {data && (
            <span className="text-xs text-muted-foreground whitespace-nowrap flex-shrink-0">
              {data.total} conv.
            </span>
          )}
        </div>
      </div>

      {/* Tabs (FilterChips) */}
      <div className="flex-shrink-0 border-b">
        <FilterChips<InboxTab>
          options={tabsWithCounts}
          value={activeTab}
          onChange={handleTabChange}
          aria-label="Filtrar conversaciones"
          className="px-3 py-2 gap-1.5"
        />
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && !data && (
          <div className="space-y-1 p-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex items-start gap-3 px-4 py-3">
                <Skeleton className="h-9 w-9 rounded-full flex-shrink-0" />
                <div className="flex-1 space-y-1.5">
                  <Skeleton className="h-3 w-3/4" />
                  <Skeleton className="h-3 w-full" />
                  <Skeleton className="h-3 w-1/2" />
                </div>
              </div>
            ))}
          </div>
        )}

        {error && (
          <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
            <AlertTriangle className="h-8 w-8 text-destructive mb-2" />
            <p className="text-sm text-destructive font-medium">Error al cargar</p>
            <p className="text-xs text-muted-foreground mt-1">{error}</p>
          </div>
        )}

        {!isLoading && !error && data?.items.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
            <MessageSquare className="h-8 w-8 text-muted-foreground mb-2" />
            <p className="text-sm font-medium text-muted-foreground">
              Sin conversaciones
            </p>
            {debouncedSearch && (
              <p className="text-xs text-muted-foreground mt-1">
                Probá con otro término de búsqueda
              </p>
            )}
          </div>
        )}

        {data?.items.map((item) => (
          <ConversationRow
            key={item.conversation_history_id}
            item={item}
            isSelected={item.conversation_history_id === selectedId}
            onClick={() => onSelectConversation(item.conversation_history_id)}
          />
        ))}
      </div>
    </div>
  );
}
