"use client";

import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogClose,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { MessageAttachment } from "@/lib/types";

interface AttachmentLightboxProps {
  attachments: MessageAttachment[];
  initialIndex: number;
  open: boolean;
  onClose: () => void;
}

/**
 * AttachmentLightbox — full-size image viewer with arrow navigation.
 *
 * - Uses Radix Dialog (Esc key handled natively by Radix)
 * - Arrow keys (← →) navigate between images via useEffect listener
 * - Renders current image full-size, centered in viewport
 */
export function AttachmentLightbox({
  attachments,
  initialIndex,
  open,
  onClose,
}: AttachmentLightboxProps) {
  const [currentIndex, setCurrentIndex] = useState(initialIndex);

  // Sync currentIndex when the lightbox opens with a new initial index
  useEffect(() => {
    if (open) {
      setCurrentIndex(initialIndex);
    }
  }, [open, initialIndex]);

  // Keyboard navigation: ArrowLeft / ArrowRight
  useEffect(() => {
    if (!open) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "ArrowLeft") {
        setCurrentIndex((prev) => Math.max(0, prev - 1));
      } else if (e.key === "ArrowRight") {
        setCurrentIndex((prev) => Math.min(attachments.length - 1, prev + 1));
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, attachments.length]);

  if (!attachments.length) return null;

  const current = attachments[currentIndex];
  const hasPrev = currentIndex > 0;
  const hasNext = currentIndex < attachments.length - 1;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        className={cn(
          "max-w-none w-screen h-screen p-0 m-0 flex items-center justify-center",
          "bg-black/90 border-none rounded-none",
        )}
      >
        {/* Close button */}
        <DialogClose asChild>
          <Button
            size="icon"
            variant="ghost"
            className="absolute top-4 right-4 z-10 text-white hover:bg-white/20"
            aria-label="Cerrar"
          >
            <X className="h-5 w-5" />
          </Button>
        </DialogClose>

        {/* Previous arrow */}
        {hasPrev && (
          <Button
            size="icon"
            variant="ghost"
            onClick={() => setCurrentIndex((prev) => prev - 1)}
            className="absolute left-4 top-1/2 -translate-y-1/2 z-10 text-white hover:bg-white/20"
            aria-label="Imagen anterior"
          >
            <ChevronLeft className="h-6 w-6" />
          </Button>
        )}

        {/* Current image */}
        <div className="flex items-center justify-center w-full h-full px-16">
          <img
            key={current.id}
            src={current.url}
            alt={current.filename ?? "imagen"}
            className="max-w-full max-h-full object-contain"
            loading="eager"
          />
        </div>

        {/* Next arrow */}
        {hasNext && (
          <Button
            size="icon"
            variant="ghost"
            onClick={() => setCurrentIndex((prev) => prev + 1)}
            className="absolute right-4 top-1/2 -translate-y-1/2 z-10 text-white hover:bg-white/20"
            aria-label="Imagen siguiente"
          >
            <ChevronRight className="h-6 w-6" />
          </Button>
        )}

        {/* Counter */}
        {attachments.length > 1 && (
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 text-white text-sm bg-black/50 rounded-full px-3 py-1">
            {currentIndex + 1} / {attachments.length}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
