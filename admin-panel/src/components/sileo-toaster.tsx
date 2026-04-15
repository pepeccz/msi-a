"use client";

import { useState, useEffect } from "react";
import { Toaster } from "sileo";

function resolveTheme(): "light" | "dark" {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

export function SileoToaster() {
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    const html = document.documentElement;
    setTheme(resolveTheme());
    const observer = new MutationObserver(() => setTheme(resolveTheme()));
    observer.observe(html, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  return (
    <Toaster
      position="top-center"
      theme={theme}
      offset={{ top: 16 }}
    />
  );
}
