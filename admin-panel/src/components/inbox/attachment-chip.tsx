"use client";

import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface AttachmentChipProps {
  file: File;
  onRemove: () => void;
}

/**
 * AttachmentChip — preview chip for a pending upload file.
 *
 * Shows a 48×48 thumbnail (object-cover) created via URL.createObjectURL.
 * The blob URL is revoked on unmount to prevent memory leaks.
 * Filename is truncated to 20 chars to keep the chip compact.
 */
export function AttachmentChip({ file, onRemove }: AttachmentChipProps) {
  const objectUrlRef = useRef<string | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);

  // Create object URL once and revoke on unmount / file change
  useEffect(() => {
    const url = URL.createObjectURL(file);
    objectUrlRef.current = url;
    if (imgRef.current) {
      imgRef.current.src = url;
    }
    return () => {
      URL.revokeObjectURL(url);
      objectUrlRef.current = null;
    };
  }, [file]);

  const truncatedName =
    file.name.length > 20 ? `${file.name.slice(0, 17)}...` : file.name;

  return (
    <div
      className={cn(
        "relative flex-shrink-0 rounded-md overflow-hidden border border-border",
        "w-12 h-12 group",
      )}
      title={file.name}
    >
      {/* Thumbnail */}
      <img
        ref={imgRef}
        alt={truncatedName}
        className="w-full h-full object-cover"
      />

      {/* Remove button — appears on hover */}
      <button
        type="button"
        aria-label={`Quitar ${truncatedName}`}
        onClick={onRemove}
        className={cn(
          "absolute inset-0 flex items-center justify-center",
          "bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity",
          "focus:opacity-100",
        )}
      >
        <X className="h-3.5 w-3.5 text-white" />
      </button>
    </div>
  );
}
