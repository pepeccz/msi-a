"use client";

/**
 * Unified Inbox — /inbox (T21)
 *
 * 3-column layout:
 *   Left  (320px): conversation list with tabs + search
 *   Center (flex-1): message thread + composer
 *   Right (320px): client ficha
 *
 * State synchronised to URL: /inbox?conv=<uuid>&tab=<tab>
 * Mobile: single column at a time with back navigation.
 */

import { useState, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { MessageSquare, Inbox } from "lucide-react";
import { cn } from "@/lib/utils";
import { useInbox } from "@/hooks/use-inbox";
import { InboxList } from "@/components/inbox/inbox-list";
import { ConversationThread } from "@/components/inbox/conversation-thread";
import { ClientCard } from "@/components/inbox/client-card";
import type { InboxItemResponse, InboxTab, InboxStats, InboxParams } from "@/lib/types";

type SortOption = NonNullable<InboxParams["sort"]>;

const VALID_SORT_VALUES: SortOption[] = [
  "last_message_at_desc",
  "last_message_at_asc",
  "started_at_desc",
  "unread_first",
];

function isValidSort(value: string | null): value is SortOption {
  return VALID_SORT_VALUES.includes(value as SortOption);
}

const VALID_TABS: InboxTab[] = [
  "todas",
  "bot_on",
  "bot_off",
  "escaladas",
  "no_leidas",
  "mias",
];

function isValidTab(value: string | null): value is InboxTab {
  return VALID_TABS.includes(value as InboxTab);
}

interface StatCardProps {
  label: string;
  value: number;
  colorClass: string;
}

function StatCard({ label, value, colorClass }: StatCardProps) {
  return (
    <div className={cn("rounded-md px-2.5 py-1.5 flex flex-col items-center min-w-0", colorClass)}>
      <span className="text-base font-bold leading-none">{value}</span>
      <span className="text-[10px] font-medium mt-0.5 truncate">{label}</span>
    </div>
  );
}

function InboxStatsRow({ stats }: { stats: InboxStats }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5 px-4 pb-2">
      <StatCard
        label="Pendientes"
        value={stats.pending}
        colorClass="bg-red-50 text-red-700"
      />
      <StatCard
        label="En progreso"
        value={stats.in_progress}
        colorClass="bg-amber-50 text-amber-700"
      />
      <StatCard
        label="Resueltas hoy"
        value={stats.resolved_today}
        colorClass="bg-green-50 text-green-700"
      />
      <StatCard
        label="Total hoy"
        value={stats.total_today}
        colorClass="bg-muted text-muted-foreground"
      />
    </div>
  );
}

function EmptyCenter() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground">
      <Inbox className="h-12 w-12 opacity-40" />
      <p className="text-sm font-medium">Seleccioná una conversación</p>
      <p className="text-xs opacity-70">
        El thread y la ficha del cliente aparecerán aquí
      </p>
    </div>
  );
}

export default function InboxPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Read initial state from URL
  const urlConvId = searchParams.get("conv");
  const urlTab = searchParams.get("tab");
  const urlSort = searchParams.get("sort");

  const [selectedConvId, setSelectedConvId] = useState<string | null>(
    urlConvId ?? null,
  );
  const [activeTab, setActiveTab] = useState<InboxTab>(
    isValidTab(urlTab) ? urlTab : "todas",
  );
  const [activeSort, setActiveSort] = useState<SortOption>(
    isValidSort(urlSort) ? urlSort : "last_message_at_desc",
  );

  // Mobile: track which column is visible
  const [mobileView, setMobileView] = useState<"list" | "thread" | "card">(
    "list",
  );

  // Fetch the full inbox to find the selected conversation object
  const { data: inboxData, refresh: refreshInbox } = useInbox(
    { tab: activeTab, page: 1, page_size: 50, sort: activeSort },
    10_000,
  );

  const selectedConversation: InboxItemResponse | null =
    inboxData?.items.find(
      (item) => item.conversation_history_id === selectedConvId,
    ) ?? null;

  // Sync URL when selection, tab, or sort changes
  const syncUrl = useCallback(
    (convId: string | null, tab: InboxTab, sort: SortOption) => {
      const params = new URLSearchParams();
      if (convId) params.set("conv", convId);
      params.set("tab", tab);
      if (sort !== "last_message_at_desc") params.set("sort", sort);
      router.replace(`/inbox?${params.toString()}`, { scroll: false });
    },
    [router],
  );

  const handleSelectConversation = useCallback(
    (id: string) => {
      setSelectedConvId(id);
      syncUrl(id, activeTab, activeSort);
      setMobileView("thread");
    },
    [activeTab, activeSort, syncUrl],
  );

  const handleTabChange = useCallback(
    (tab: InboxTab) => {
      setActiveTab(tab);
      syncUrl(selectedConvId, tab, activeSort);
    },
    [selectedConvId, activeSort, syncUrl],
  );

  const handleSortChange = useCallback(
    (sort: SortOption) => {
      setActiveSort(sort);
      syncUrl(selectedConvId, activeTab, sort);
    },
    [selectedConvId, activeTab, syncUrl],
  );

  const handleConversationUpdated = useCallback(() => {
    refreshInbox();
  }, [refreshInbox]);

  const handleBackToList = useCallback(() => {
    setMobileView("list");
  }, []);

  const handleShowCard = useCallback(() => {
    setMobileView("card");
  }, []);

  return (
    <div className="flex h-full overflow-hidden">
      {/* LEFT: conversation list */}
      <div
        className={cn(
          // Desktop: always visible, fixed width
          "hidden lg:flex flex-col border-r bg-background",
          "w-[340px] flex-shrink-0",
          // Mobile: visible when mobileView === "list"
          mobileView === "list" && "flex lg:flex w-full lg:w-[340px]",
        )}
      >
        <div className="flex-shrink-0 border-b">
          <div className="px-4 py-3">
            <h1 className="text-base font-semibold flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-primary" />
              Bandeja
            </h1>
          </div>
          {inboxData?.stats && (
            <InboxStatsRow stats={inboxData.stats} />
          )}
        </div>
        <div className="flex-1 overflow-hidden">
          <InboxList
            selectedId={selectedConvId}
            activeTab={activeTab}
            onSelectConversation={handleSelectConversation}
            onTabChange={handleTabChange}
            sort={activeSort}
            onSortChange={handleSortChange}
          />
        </div>
      </div>

      {/* CENTER: thread */}
      <div
        className={cn(
          "hidden lg:flex flex-col flex-1 overflow-hidden border-r bg-background",
          mobileView === "thread" && "flex lg:flex w-full lg:flex-1",
        )}
      >
        {selectedConversation ? (
          <ConversationThread
            conversation={selectedConversation}
            onConversationUpdated={handleConversationUpdated}
            onBack={handleBackToList}
          />
        ) : (
          <EmptyCenter />
        )}
      </div>

      {/* RIGHT: client ficha */}
      <div
        className={cn(
          "hidden lg:flex flex-col",
          "w-[320px] flex-shrink-0 bg-background overflow-hidden",
          mobileView === "card" && "flex lg:flex w-full lg:w-[320px]",
        )}
      >
        <div className="flex-shrink-0 px-4 py-3 border-b">
          <p className="text-sm font-semibold text-muted-foreground">
            Ficha del cliente
          </p>
        </div>
        {selectedConversation ? (
          <div className="flex-1 overflow-hidden">
            <ClientCard
              conversation={selectedConversation}
              onConversationUpdated={handleConversationUpdated}
            />
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground">
            <p className="text-xs">Sin conversación seleccionada</p>
          </div>
        )}
      </div>
    </div>
  );
}
