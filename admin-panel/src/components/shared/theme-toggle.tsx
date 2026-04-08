"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";

const THEME_KEY = "msi-admin-theme";

type Theme = "light" | "dark";

/**
 * Reads the current applied theme from document and localStorage.
 * Returns "dark" if the <html> element has the "dark" class, otherwise "light".
 */
function getAppliedTheme(): Theme {
  if (typeof document === "undefined") return "light";
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

/**
 * ThemeToggle — Simple light/dark mode button.
 *
 * - Reads/writes localStorage key "msi-admin-theme"
 * - Toggles the `dark` class on `<html>` element
 * - FOUC prevention script in layout.tsx applies the theme before first paint
 * - Designed to be placed in the header before the user profile area
 *
 * @example
 * <ThemeToggle />
 */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("light");

  // Sync state with the actual applied theme on mount
  useEffect(() => {
    setTheme(getAppliedTheme());
  }, []);

  function toggleTheme() {
    const next: Theme = theme === "light" ? "dark" : "light";

    // Apply to DOM
    if (next === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }

    // Persist preference
    localStorage.setItem(THEME_KEY, next);

    // Update local state
    setTheme(next);
  }

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggleTheme}
      aria-label={theme === "light" ? "Activar modo oscuro" : "Activar modo claro"}
      title={theme === "light" ? "Activar modo oscuro" : "Activar modo claro"}
    >
      {theme === "light" ? (
        <Moon className="h-4 w-4" />
      ) : (
        <Sun className="h-4 w-4" />
      )}
    </Button>
  );
}
