"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useEffect, useState, useCallback } from "react";
import {
  Users,
  LayoutDashboard,
  Settings,
  LogOut,
  MessageSquare,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  MessageCircle,
  Car,
  AlertTriangle,
  FileText,
  ImageIcon,
  BookOpen,
  PhoneForwarded,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAuth } from "@/contexts/auth-context";
import { useSidebar } from "@/contexts/sidebar-context";
import api from "@/lib/api";

interface NavItem {
  title: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: number;
}

interface ExternalLinkItem {
  title: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
}

const mainNav: NavItem[] = [
  {
    title: "Dashboard",
    href: "/dashboard",
    icon: LayoutDashboard,
  },
  {
    title: "Escalaciones",
    href: "/escalations",
    icon: PhoneForwarded,
  },
  {
    title: "Usuarios",
    href: "/users",
    icon: Users,
  },
  {
    title: "Conversaciones",
    href: "/conversations",
    icon: MessageSquare,
  },
];

const tariffNav: NavItem[] = [
  {
    title: "Reformas",
    href: "/reformas",
    icon: Car,
  },
  {
    title: "Advertencias",
    href: "/advertencias",
    icon: AlertTriangle,
  },
];

const ragNav: NavItem[] = [
  {
    title: "Normativas",
    href: "/normativas",
    icon: BookOpen,
  },
];

const systemNav: NavItem[] = [
  {
    title: "Configuracion",
    href: "/settings",
    icon: Settings,
  },
  {
    title: "Imagenes",
    href: "/imagenes",
    icon: ImageIcon,
  },
  {
    title: "Prompts",
    href: "/prompts",
    icon: FileText,
  },
];

const externalLinks: ExternalLinkItem[] = [
  {
    title: "Chatwoot",
    href: process.env.NEXT_PUBLIC_CHATWOOT_URL || "http://localhost:3000",
    icon: MessageCircle,
  },
];

function NavSection({
  title,
  items,
  isCollapsed,
}: {
  title: string;
  items: NavItem[];
  isCollapsed: boolean;
}) {
  const pathname = usePathname();

  return (
    <div className={cn("py-2", isCollapsed ? "px-2" : "px-3")}>
      {!isCollapsed && (
        <h2 className="mb-2 px-4 text-xs font-semibold tracking-tight text-muted-foreground uppercase">
          {title}
        </h2>
      )}
      <div className="space-y-1">
        {items.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href;

          return (
            <TooltipProvider key={item.href} delayDuration={0}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Link href={item.href}>
                    <Button
                      variant={isActive ? "secondary" : "ghost"}
                      className={cn(
                        "w-full relative",
                        isCollapsed ? "justify-center px-2" : "justify-start",
                        isActive &&
                          "bg-sidebar-accent text-sidebar-accent-foreground"
                      )}
                    >
                      <Icon
                        className={cn("h-4 w-4", !isCollapsed && "mr-2")}
                      />
                      {!isCollapsed && (
                        <span className="truncate flex-1 text-left">{item.title}</span>
                      )}
                      {item.badge !== undefined && item.badge > 0 && (
                        <Badge
                          variant="destructive"
                          className={cn(
                            "h-5 min-w-[20px] px-1.5 text-xs font-bold",
                            isCollapsed && "absolute -top-1 -right-1"
                          )}
                        >
                          {item.badge > 99 ? "99+" : item.badge}
                        </Badge>
                      )}
                    </Button>
                  </Link>
                </TooltipTrigger>
                {isCollapsed && (
                  <TooltipContent side="right">
                    {item.title}
                    {item.badge !== undefined && item.badge > 0 && (
                      <span className="ml-2 text-red-400">({item.badge} pendientes)</span>
                    )}
                  </TooltipContent>
                )}
              </Tooltip>
            </TooltipProvider>
          );
        })}
      </div>
    </div>
  );
}

function ExternalLinksSection({
  title,
  items,
  isCollapsed,
}: {
  title: string;
  items: ExternalLinkItem[];
  isCollapsed: boolean;
}) {
  return (
    <div className={cn("py-2", isCollapsed ? "px-2" : "px-3")}>
      {!isCollapsed && (
        <h2 className="mb-2 px-4 text-xs font-semibold tracking-tight text-muted-foreground uppercase">
          {title}
        </h2>
      )}
      <div className="space-y-1">
        {items.map((item) => {
          const Icon = item.icon;

          return (
            <TooltipProvider key={item.href} delayDuration={0}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <a
                    href={item.href}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <Button
                      variant="ghost"
                      className={cn(
                        "w-full",
                        isCollapsed ? "justify-center px-2" : "justify-start"
                      )}
                    >
                      <Icon
                        className={cn("h-4 w-4", !isCollapsed && "mr-2")}
                      />
                      {!isCollapsed && (
                        <>
                          <span className="truncate flex-1">{item.title}</span>
                          <ExternalLink className="h-3 w-3 ml-1 text-muted-foreground" />
                        </>
                      )}
                    </Button>
                  </a>
                </TooltipTrigger>
                {isCollapsed && (
                  <TooltipContent side="right">
                    {item.title} (abre en nueva pestana)
                  </TooltipContent>
                )}
              </Tooltip>
            </TooltipProvider>
          );
        })}
      </div>
    </div>
  );
}

export function Sidebar() {
  const { logout, user } = useAuth();
  const { isCollapsed, toggle } = useSidebar();
  const [pendingEscalations, setPendingEscalations] = useState(0);

  // Fetch pending escalations count
  const fetchPendingEscalations = useCallback(async () => {
    try {
      const stats = await api.getEscalationStats();
      setPendingEscalations(stats.pending);
    } catch (error) {
      // Silently fail - not critical for sidebar
      console.debug("Could not fetch escalation stats:", error);
    }
  }, []);

  // Initial fetch and polling every 30 seconds
  useEffect(() => {
    fetchPendingEscalations();
    const interval = setInterval(fetchPendingEscalations, 30000);
    return () => clearInterval(interval);
  }, [fetchPendingEscalations]);

  // Create mainNav with dynamic badge
  const mainNavWithBadge: NavItem[] = mainNav.map((item) => {
    if (item.href === "/escalations") {
      return { ...item, badge: pendingEscalations };
    }
    return item;
  });

  // Get display name for user section
  const displayName = user?.display_name || user?.username || "Admin";
  const roleLabel = user?.role === "admin" ? "Administrador" : "Usuario";

  return (
    <div
      className={cn(
        "relative flex h-full flex-col border-r bg-sidebar transition-all duration-300 ease-in-out",
        isCollapsed ? "w-16" : "w-64"
      )}
    >
      {/* Floating Toggle Button */}
      <TooltipProvider delayDuration={0}>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="outline"
              size="icon"
              onClick={toggle}
              className="absolute -right-3 top-20 z-50 h-6 w-6 rounded-full border bg-background shadow-md hover:bg-accent"
            >
              {isCollapsed ? (
                <ChevronRight className="h-3 w-3" />
              ) : (
                <ChevronLeft className="h-3 w-3" />
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">
            {isCollapsed ? "Expandir menu" : "Colapsar menu"}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      {/* Logo/Brand */}
      <div className="flex h-16 items-center border-b px-3">
        <Link
          href="/dashboard"
          className={cn(
            "flex items-center gap-2 overflow-hidden",
            isCollapsed && "justify-center"
          )}
        >
          <Image
            src="/logo.png"
            width={isCollapsed ? 40 : 120}
            height={isCollapsed ? 40 : 40}
            alt="MSI Automotive"
            className="flex-shrink-0 object-contain"
          />
        </Link>
      </div>

      {/* Navigation */}
      <div className="flex-1 overflow-y-auto py-4">
        <NavSection title="Principal" items={mainNavWithBadge} isCollapsed={isCollapsed} />
        <Separator className="my-2" />
        <NavSection title="Reformas" items={tariffNav} isCollapsed={isCollapsed} />
        <Separator className="my-2" />
        <NavSection title="RAG" items={ragNav} isCollapsed={isCollapsed} />
        <Separator className="my-2" />
        <NavSection title="Sistema" items={systemNav} isCollapsed={isCollapsed} />
        <Separator className="my-2" />
        <ExternalLinksSection title="Herramientas" items={externalLinks} isCollapsed={isCollapsed} />
      </div>

      {/* Powered by Zanovix */}
      <div className={cn("px-3 py-2", isCollapsed && "px-2")}>
        <a
          href="https://zanovix.com"
          target="_blank"
          rel="noopener noreferrer"
          className={cn(
            "flex items-center text-xs text-muted-foreground hover:text-foreground transition-colors",
            "justify-center"
          )}
        >
          {isCollapsed ? (
            <TooltipProvider delayDuration={0}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="font-medium">Z</span>
                </TooltipTrigger>
                <TooltipContent side="right">Powered by Zanovix</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          ) : (
            <span>
              Powered by <span className="font-medium hover:underline">Zanovix</span>
            </span>
          )}
        </a>
      </div>

      {/* User section */}
      <div className="border-t p-2">
        {isCollapsed ? (
          <div className="flex flex-col items-center gap-2">
            <TooltipProvider delayDuration={0}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-medium cursor-default">
                    {displayName.charAt(0).toUpperCase()}
                  </div>
                </TooltipTrigger>
                <TooltipContent side="right">
                  {displayName} ({roleLabel})
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <TooltipProvider delayDuration={0}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={logout}
                    className="h-8 w-8 text-muted-foreground hover:text-foreground"
                  >
                    <LogOut className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="right">Cerrar sesion</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        ) : (
          <div className="flex items-center gap-3 rounded-lg bg-sidebar-accent p-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-medium flex-shrink-0">
              {displayName.charAt(0).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-sidebar-foreground truncate">
                {displayName}
              </p>
              <p className="text-xs text-muted-foreground">{roleLabel}</p>
            </div>
            <TooltipProvider delayDuration={0}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={logout}
                    className="h-8 w-8 text-muted-foreground hover:text-foreground flex-shrink-0"
                  >
                    <LogOut className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="top">Cerrar sesion</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        )}
      </div>
    </div>
  );
}
