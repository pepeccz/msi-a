"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { MessageSquare, FileText } from "lucide-react";
import { cn } from "@/lib/utils";

interface TabItem {
  title: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
}

const tabs: TabItem[] = [
  { title: "Consulta", href: "/normativas/consulta", icon: MessageSquare },
  { title: "Documentos", href: "/normativas/documentos", icon: FileText },
];

export default function NormativasLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Normativas</h1>
        <p className="text-muted-foreground">
          Consulta normativas mediante IA y gestiona documentos regulatorios
        </p>
      </div>

      {/* Tab navigation */}
      <div className="inline-flex h-10 items-center justify-center rounded-md bg-muted p-1 text-muted-foreground">
        {tabs.map((tab) => {
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

      {/* Page content */}
      <div>{children}</div>
    </div>
  );
}
