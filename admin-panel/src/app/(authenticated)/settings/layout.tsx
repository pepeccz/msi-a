"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { Settings, Server, UserCog } from "lucide-react";
import { useAuth } from "@/contexts/auth-context";
import { cn } from "@/lib/utils";

interface TabItem {
  title: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  adminOnly?: boolean;
}

const tabs: TabItem[] = [
  { title: "Configuracion", href: "/settings/config", icon: Settings },
  { title: "Sistema", href: "/settings/system", icon: Server },
  { title: "Administradores", href: "/settings/admin-users", icon: UserCog, adminOnly: true },
];

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const { isAdmin } = useAuth();

  const visibleTabs = tabs.filter((tab) => !tab.adminOnly || isAdmin);

  return (
    <div className="p-6 space-y-6">
      {/* Header compartido */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Configuracion</h1>
        <p className="text-muted-foreground">
          Gestion del sistema, servicios y administradores
        </p>
      </div>

      {/* Navegacion por tabs */}
      <div className="inline-flex h-10 items-center justify-center rounded-md bg-muted p-1 text-muted-foreground">
        {visibleTabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = pathname === tab.href;

          return (
            <Link key={tab.href} href={tab.href}>
              <button
                className={cn(
                  "inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                  isActive
                    ? "bg-background text-foreground shadow-sm"
                    : "hover:bg-background/50"
                )}
              >
                <Icon className="h-4 w-4 mr-2" />
                {tab.title}
              </button>
            </Link>
          );
        })}
      </div>

      {/* Contenido de las sub-paginas */}
      <div>{children}</div>
    </div>
  );
}
