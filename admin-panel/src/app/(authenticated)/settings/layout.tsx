"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { Settings, Server, UserCog, Receipt } from "lucide-react";
import { useAuth } from "@/contexts/auth-context";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface TabItem {
  title: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  adminOnly?: boolean;
}

const tabs: TabItem[] = [
  { title: "General", href: "/settings/config", icon: Settings },
  { title: "Sistema", href: "/settings/system", icon: Server },
  { title: "Facturación", href: "/settings/billing", icon: Receipt, adminOnly: true },
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
        <h1 className="text-3xl font-bold tracking-tight">Configuración</h1>
        <p className="text-muted-foreground">
          Gestion del sistema, servicios y administradores
        </p>
      </div>

      {/* Navegacion por tabs usando Radix Tabs */}
      <div className="overflow-x-auto">
        <Tabs value={pathname}>
          <TabsList className="w-full sm:w-auto">
            {visibleTabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <TabsTrigger key={tab.href} value={tab.href} asChild>
                  <Link href={tab.href}>
                    <Icon className="h-4 w-4 mr-2" />
                    {tab.title}
                  </Link>
                </TabsTrigger>
              );
            })}
          </TabsList>
        </Tabs>
      </div>

      {/* Contenido de las sub-paginas */}
      <div>{children}</div>
    </div>
  );
}
