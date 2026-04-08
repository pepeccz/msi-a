"use client";

import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";

import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Root, Trigger, Close — thin re-exports so callers never import from Radix
// ---------------------------------------------------------------------------

const Sheet = DialogPrimitive.Root;
Sheet.displayName = "Sheet";

const SheetTrigger = DialogPrimitive.Trigger;
SheetTrigger.displayName = "SheetTrigger";

const SheetClose = DialogPrimitive.Close;
SheetClose.displayName = "SheetClose";

const SheetPortal = DialogPrimitive.Portal;
SheetPortal.displayName = "SheetPortal";

// ---------------------------------------------------------------------------
// Overlay — semi-transparent backdrop, closes sheet on click (handled by
// Radix automatically when the user clicks outside the Content area)
// ---------------------------------------------------------------------------

const SheetOverlay = React.forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn(
      "fixed inset-0 z-50 bg-black/80",
      "data-[state=open]:animate-in data-[state=closed]:animate-out",
      "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
      className
    )}
    {...props}
  />
));
SheetOverlay.displayName = "SheetOverlay";

// ---------------------------------------------------------------------------
// Content — the actual side panel
// ---------------------------------------------------------------------------

export type SheetSide = "left" | "right";

const sideVariants: Record<SheetSide, string> = {
  left: [
    "inset-y-0 left-0 h-full w-64",
    "border-r",
    // Enter: slide in from the left
    "data-[state=open]:animate-in data-[state=open]:slide-in-from-left",
    // Exit: slide out to the left
    "data-[state=closed]:animate-out data-[state=closed]:slide-out-to-left",
  ].join(" "),
  right: [
    "inset-y-0 right-0 h-full w-64",
    "border-l",
    // Enter: slide in from the right
    "data-[state=open]:animate-in data-[state=open]:slide-in-from-right",
    // Exit: slide out to the right
    "data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right",
  ].join(" "),
};

interface SheetContentProps
  extends React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> {
  /** Which edge the panel slides from. Defaults to `"left"`. */
  side?: SheetSide;
}

const SheetContent = React.forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Content>,
  SheetContentProps
>(({ className, side = "left", children, ...props }, ref) => (
  <SheetPortal>
    <SheetOverlay />
    <DialogPrimitive.Content
      ref={ref}
      className={cn(
        // Base: fixed full-height panel, sitting on top of overlay
        "fixed z-50 flex flex-col",
        "bg-background shadow-xl",
        // Shared animation timing
        "duration-300 ease-in-out",
        // Fade in/out (combined with slide)
        "data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0",
        // Side-specific positioning + slide animation
        sideVariants[side],
        className
      )}
      {...props}
    >
      {children}
      {/* Close button — keyboard (Escape) is handled by Radix automatically */}
      <DialogPrimitive.Close
        className={cn(
          "absolute top-4 rounded-sm opacity-70 ring-offset-background",
          "transition-opacity hover:opacity-100",
          "focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
          "disabled:pointer-events-none",
          "data-[state=open]:bg-accent data-[state=open]:text-muted-foreground",
          // Mirror close-button side to match panel side
          side === "left" ? "right-4" : "left-4"
        )}
        aria-label="Cerrar"
      >
        <X className="h-4 w-4" />
        <span className="sr-only">Cerrar</span>
      </DialogPrimitive.Close>
    </DialogPrimitive.Content>
  </SheetPortal>
));
SheetContent.displayName = "SheetContent";

// ---------------------------------------------------------------------------
// Header / Footer / Title / Description — convenience wrappers that match
// the Dialog component API so callers can use a consistent style
// ---------------------------------------------------------------------------

const SheetHeader = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn("flex flex-col space-y-1.5 px-4 py-4 text-left", className)}
    {...props}
  />
);
SheetHeader.displayName = "SheetHeader";

const SheetFooter = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "mt-auto flex flex-col-reverse gap-2 px-4 py-4 sm:flex-row sm:justify-end",
      className
    )}
    {...props}
  />
);
SheetFooter.displayName = "SheetFooter";

const SheetTitle = React.forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn("text-lg font-semibold leading-none tracking-tight", className)}
    {...props}
  />
));
SheetTitle.displayName = "SheetTitle";

const SheetDescription = React.forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    className={cn("text-sm text-muted-foreground", className)}
    {...props}
  />
));
SheetDescription.displayName = "SheetDescription";

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

export {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetOverlay,
  SheetPortal,
  SheetTitle,
  SheetTrigger,
};
