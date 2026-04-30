import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merges class names using clsx and tailwind-merge.
 * Handles conditional classes and resolves Tailwind CSS conflicts.
 *
 * @example
 * cn("px-4 py-2", isActive && "bg-primary", "text-sm")
 * cn("p-4 p-6")  // → "p-6" (tailwind-merge resolves conflict)
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
