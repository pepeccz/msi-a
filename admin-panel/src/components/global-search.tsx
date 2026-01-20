"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Search, Loader2 } from "lucide-react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { Button } from "@/components/ui/button";
import { useGlobalSearch, type SearchResult } from "@/hooks/use-global-search";
import { cn } from "@/lib/utils";

interface GlobalSearchProps {
  /**
   * Modo de visualizacion:
   * - "trigger": Muestra un boton que abre el dialog (para header)
   * - "inline": Muestra una barra de busqueda que abre el dialog (para dashboard)
   */
  variant?: "trigger" | "inline";
}

export function GlobalSearch({ variant = "trigger" }: GlobalSearchProps) {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const {
    query,
    setQuery,
    isLoading,
    pages,
    elements,
    categories,
    tiers,
    users,
    hasResults,
  } = useGlobalSearch();

  // Keyboard shortcut: Cmd/Ctrl + K
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((open) => !open);
      }
    };

    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  // Handle selection
  const handleSelect = useCallback(
    (result: SearchResult) => {
      setOpen(false);
      setQuery("");
      router.push(result.href);
    },
    [router, setQuery]
  );

  // Reset query when dialog closes
  useEffect(() => {
    if (!open) {
      setQuery("");
    }
  }, [open, setQuery]);

  // Render trigger button (for header)
  const renderTrigger = () => (
    <Button
      variant="outline"
      className={cn(
        "relative h-9 w-9 p-0 xl:h-10 xl:w-60 xl:justify-start xl:px-3 xl:py-2"
      )}
      onClick={() => setOpen(true)}
    >
      <Search className="h-4 w-4 xl:mr-2" />
      <span className="hidden xl:inline-flex">Buscar...</span>
      <kbd className="pointer-events-none absolute right-1.5 top-2 hidden h-6 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium opacity-100 xl:flex">
        <span className="text-xs">⌘</span>K
      </kbd>
    </Button>
  );

  // Render inline search bar (for dashboard)
  const renderInline = () => (
    <div
      className="relative cursor-pointer"
      onClick={() => setOpen(true)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          setOpen(true);
        }
      }}
    >
      <div className="flex h-12 w-full items-center rounded-lg border bg-background px-4 text-muted-foreground shadow-sm transition-colors hover:border-primary/50 hover:bg-accent">
        <Search className="mr-3 h-5 w-5" />
        <span className="flex-1 text-left">
          Buscar paginas, elementos, usuarios...
        </span>
        <kbd className="pointer-events-none hidden h-6 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium opacity-100 sm:flex">
          <span className="text-xs">⌘</span>K
        </kbd>
      </div>
    </div>
  );

  // Group labels in Spanish
  const groupLabels = {
    page: "Paginas",
    element: "Elementos",
    category: "Categorias",
    tier: "Tarifas",
    user: "Usuarios",
  };

  return (
    <>
      {variant === "trigger" ? renderTrigger() : renderInline()}

      <CommandDialog open={open} onOpenChange={setOpen}>
        <CommandInput
          placeholder="Buscar paginas, elementos, usuarios..."
          value={query}
          onValueChange={setQuery}
        />
        <CommandList>
          {isLoading && (
            <div className="flex items-center justify-center py-6">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          )}

          {!isLoading && !hasResults && query.length > 0 && (
            <CommandEmpty>
              No se encontraron resultados para &quot;{query}&quot;
            </CommandEmpty>
          )}

          {!isLoading && pages.length > 0 && (
            <CommandGroup heading={groupLabels.page}>
              {pages.map((result) => (
                <CommandItem
                  key={result.id}
                  value={`${result.title} ${result.keywords?.join(" ") || ""}`}
                  onSelect={() => handleSelect(result)}
                  className="cursor-pointer"
                >
                  <result.icon className="mr-2 h-4 w-4" />
                  <span>{result.title}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          )}

          {!isLoading && elements.length > 0 && (
            <>
              <CommandSeparator />
              <CommandGroup heading={groupLabels.element}>
                {elements.map((result) => (
                  <CommandItem
                    key={result.id}
                    value={`${result.title} ${result.subtitle || ""} ${result.keywords?.join(" ") || ""}`}
                    onSelect={() => handleSelect(result)}
                    className="cursor-pointer"
                  >
                    <result.icon className="mr-2 h-4 w-4" />
                    <div className="flex flex-col">
                      <span>{result.title}</span>
                      {result.subtitle && (
                        <span className="text-xs text-muted-foreground">
                          {result.subtitle}
                        </span>
                      )}
                    </div>
                  </CommandItem>
                ))}
              </CommandGroup>
            </>
          )}

          {!isLoading && categories.length > 0 && (
            <>
              <CommandSeparator />
              <CommandGroup heading={groupLabels.category}>
                {categories.map((result) => (
                  <CommandItem
                    key={result.id}
                    value={`${result.title} ${result.subtitle || ""}`}
                    onSelect={() => handleSelect(result)}
                    className="cursor-pointer"
                  >
                    <result.icon className="mr-2 h-4 w-4" />
                    <div className="flex flex-col">
                      <span>{result.title}</span>
                      {result.subtitle && (
                        <span className="text-xs text-muted-foreground">
                          {result.subtitle}
                        </span>
                      )}
                    </div>
                  </CommandItem>
                ))}
              </CommandGroup>
            </>
          )}

          {!isLoading && tiers.length > 0 && (
            <>
              <CommandSeparator />
              <CommandGroup heading={groupLabels.tier}>
                {tiers.map((result) => (
                  <CommandItem
                    key={result.id}
                    value={`${result.title} ${result.subtitle || ""}`}
                    onSelect={() => handleSelect(result)}
                    className="cursor-pointer"
                  >
                    <result.icon className="mr-2 h-4 w-4" />
                    <div className="flex flex-col">
                      <span>{result.title}</span>
                      {result.subtitle && (
                        <span className="text-xs text-muted-foreground">
                          {result.subtitle}
                        </span>
                      )}
                    </div>
                  </CommandItem>
                ))}
              </CommandGroup>
            </>
          )}

          {!isLoading && users.length > 0 && (
            <>
              <CommandSeparator />
              <CommandGroup heading={groupLabels.user}>
                {users.map((result) => (
                  <CommandItem
                    key={result.id}
                    value={`${result.title} ${result.subtitle || ""}`}
                    onSelect={() => handleSelect(result)}
                    className="cursor-pointer"
                  >
                    <result.icon className="mr-2 h-4 w-4" />
                    <div className="flex flex-col">
                      <span>{result.title}</span>
                      {result.subtitle && (
                        <span className="text-xs text-muted-foreground">
                          {result.subtitle}
                        </span>
                      )}
                    </div>
                  </CommandItem>
                ))}
              </CommandGroup>
            </>
          )}
        </CommandList>
      </CommandDialog>
    </>
  );
}
