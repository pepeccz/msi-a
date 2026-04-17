/**
 * Polymorphic attachment utilities.
 *
 * Provides MIME-based branching helpers for rendering attachments in the
 * admin panel. Image attachments render with <Image /> (Next.js), while PDF
 * attachments render with <iframe> for native browser PDF viewing.
 */

import type { CaseImage } from "./types";

/**
 * Returns true if the attachment is a PDF document.
 * Used to branch rendering: iframe for PDF, <Image> for images.
 */
export function isPdfAttachment(attachment: Pick<CaseImage, "mime_type">): boolean {
  return attachment.mime_type === "application/pdf";
}

/**
 * Returns true if the attachment is an image type.
 */
export function isImageAttachment(attachment: Pick<CaseImage, "mime_type">): boolean {
  return attachment.mime_type.startsWith("image/");
}

/**
 * Returns a human-readable label for the attachment type.
 * Used for accessibility and UI labels.
 */
export function getAttachmentTypeLabel(attachment: Pick<CaseImage, "mime_type">): string {
  if (isPdfAttachment(attachment)) return "PDF";
  if (isImageAttachment(attachment)) return "Imagen";
  return "Archivo";
}
