"use client";

import { cn } from "@/lib/utils";
import type { MessageAttachment } from "@/lib/types";

interface MessageAttachmentsProps {
  attachments: MessageAttachment[];
  onOpen: (attachments: MessageAttachment[], index: number) => void;
}

/**
 * MessageAttachments — renders a CSS grid of image thumbnails.
 *
 * Layout rules (design A7):
 *   1  → single image, max-width 320px, native aspect ratio
 *   2  → 1×2 row (grid-cols-2)
 *   3  → 1 large left (row-span-2) + 2 stacked right
 *   4  → 2×2 grid
 *   5  → 2×3 grid, 5 cells (last cell of row 2 empty)
 *   6  → 2×3 full grid
 *   7+ → 2×3 grid, first 5 shown, 6th cell = thumbnail with "+N" overlay
 *         where N = total − 6
 */
export function MessageAttachments({
  attachments,
  onOpen,
}: MessageAttachmentsProps) {
  if (!attachments || attachments.length === 0) return null;

  const count = attachments.length;

  const handleClick = (index: number) => {
    onOpen(attachments, index);
  };

  // ── 1 image ──────────────────────────────────────────────────────────────
  if (count === 1) {
    return (
      <div className="mt-1">
        <AttachmentThumb
          att={attachments[0]}
          onClick={() => handleClick(0)}
          className="max-w-[320px] w-full rounded-lg overflow-hidden"
          imgClassName="w-full h-auto object-cover"
        />
      </div>
    );
  }

  // ── 2 images ─────────────────────────────────────────────────────────────
  if (count === 2) {
    return (
      <div className="mt-1 grid grid-cols-2 gap-0.5">
        {attachments.map((att, i) => (
          <AttachmentThumb
            key={att.id}
            att={att}
            onClick={() => handleClick(i)}
            className="overflow-hidden rounded-sm"
            imgClassName="w-full h-28 object-cover"
          />
        ))}
      </div>
    );
  }

  // ── 3 images ─────────────────────────────────────────────────────────────
  if (count === 3) {
    return (
      <div className="mt-1 grid grid-cols-2 gap-0.5" style={{ gridTemplateRows: "auto auto" }}>
        {/* Left: large spanning 2 rows */}
        <AttachmentThumb
          att={attachments[0]}
          onClick={() => handleClick(0)}
          className="overflow-hidden rounded-sm row-span-2"
          imgClassName="w-full h-full object-cover"
          style={{ minHeight: "112px" }}
        />
        {/* Right: 2 stacked */}
        <AttachmentThumb
          att={attachments[1]}
          onClick={() => handleClick(1)}
          className="overflow-hidden rounded-sm"
          imgClassName="w-full h-14 object-cover"
        />
        <AttachmentThumb
          att={attachments[2]}
          onClick={() => handleClick(2)}
          className="overflow-hidden rounded-sm"
          imgClassName="w-full h-14 object-cover"
        />
      </div>
    );
  }

  // ── 4 images ─────────────────────────────────────────────────────────────
  if (count === 4) {
    return (
      <div className="mt-1 grid grid-cols-2 gap-0.5">
        {attachments.map((att, i) => (
          <AttachmentThumb
            key={att.id}
            att={att}
            onClick={() => handleClick(i)}
            className="overflow-hidden rounded-sm"
            imgClassName="w-full h-28 object-cover"
          />
        ))}
      </div>
    );
  }

  // ── 5 images ─────────────────────────────────────────────────────────────
  if (count === 5) {
    return (
      <div className="mt-1 grid grid-cols-3 gap-0.5">
        {attachments.slice(0, 5).map((att, i) => (
          <AttachmentThumb
            key={att.id}
            att={att}
            onClick={() => handleClick(i)}
            className={cn("overflow-hidden rounded-sm", i === 4 && "col-span-1")}
            imgClassName="w-full h-20 object-cover"
          />
        ))}
        {/* Empty 6th slot to maintain grid shape */}
        <div aria-hidden />
      </div>
    );
  }

  // ── 6 images ─────────────────────────────────────────────────────────────
  if (count === 6) {
    return (
      <div className="mt-1 grid grid-cols-3 gap-0.5">
        {attachments.map((att, i) => (
          <AttachmentThumb
            key={att.id}
            att={att}
            onClick={() => handleClick(i)}
            className="overflow-hidden rounded-sm"
            imgClassName="w-full h-20 object-cover"
          />
        ))}
      </div>
    );
  }

  // ── 7+ images: show first 5 + overlay on 6th showing "+N" ────────────────
  const visibleAttachments = attachments.slice(0, 6);
  const hiddenCount = count - 6; // how many are hidden beyond the 6 visible

  return (
    <div className="mt-1 grid grid-cols-3 gap-0.5">
      {visibleAttachments.slice(0, 5).map((att, i) => (
        <AttachmentThumb
          key={att.id}
          att={att}
          onClick={() => handleClick(i)}
          className="overflow-hidden rounded-sm"
          imgClassName="w-full h-20 object-cover"
        />
      ))}
      {/* 6th cell: thumbnail + overlay */}
      <button
        type="button"
        onClick={() => handleClick(5)}
        className="relative overflow-hidden rounded-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={`Ver ${hiddenCount + 1} imágenes más`}
      >
        <img
          src={visibleAttachments[5].url}
          alt={visibleAttachments[5].filename ?? "imagen"}
          loading="lazy"
          className="w-full h-20 object-cover"
          onError={(e) => {
            (e.currentTarget as HTMLImageElement).src =
              "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24'%3E%3C/svg%3E";
          }}
        />
        <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
          <span className="text-white text-sm font-semibold">
            +{hiddenCount}
          </span>
        </div>
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Internal: single attachment thumbnail cell
// ---------------------------------------------------------------------------

interface AttachmentThumbProps {
  att: MessageAttachment;
  onClick: () => void;
  className?: string;
  imgClassName?: string;
  style?: React.CSSProperties;
}

function AttachmentThumb({
  att,
  onClick,
  className,
  imgClassName,
  style,
}: AttachmentThumbProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
      style={style}
      aria-label={att.filename ?? "imagen"}
    >
      <img
        src={att.url}
        alt={att.filename ?? "imagen"}
        loading="lazy"
        className={imgClassName}
        onError={(e) => {
          const img = e.currentTarget as HTMLImageElement;
          img.src =
            "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24'%3E%3C/svg%3E";
          img.className = cn(imgClassName, "opacity-50");
        }}
      />
    </button>
  );
}
