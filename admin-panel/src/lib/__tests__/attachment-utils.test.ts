/**
 * Tests for polymorphic attachment utilities.
 *
 * Spec: docs/system/03-admin-panel/paginas-y-flujos.md — escenario 16.bis
 * Verifies MIME-based branching logic for the attachment viewer in cases/[id].
 */

import {
  getAttachmentTypeLabel,
  isImageAttachment,
  isPdfAttachment,
} from "../attachment-utils";

describe("isPdfAttachment", () => {
  it("returns true for application/pdf", () => {
    expect(isPdfAttachment({ mime_type: "application/pdf" })).toBe(true);
  });

  it("returns false for image/jpeg", () => {
    expect(isPdfAttachment({ mime_type: "image/jpeg" })).toBe(false);
  });

  it("returns false for image/png", () => {
    expect(isPdfAttachment({ mime_type: "image/png" })).toBe(false);
  });

  it("returns false for empty string", () => {
    expect(isPdfAttachment({ mime_type: "" })).toBe(false);
  });
});

describe("isImageAttachment", () => {
  it("returns true for image/jpeg", () => {
    expect(isImageAttachment({ mime_type: "image/jpeg" })).toBe(true);
  });

  it("returns true for image/png", () => {
    expect(isImageAttachment({ mime_type: "image/png" })).toBe(true);
  });

  it("returns true for image/webp", () => {
    expect(isImageAttachment({ mime_type: "image/webp" })).toBe(true);
  });

  it("returns false for application/pdf", () => {
    expect(isImageAttachment({ mime_type: "application/pdf" })).toBe(false);
  });
});

describe("getAttachmentTypeLabel", () => {
  it("returns 'PDF' for application/pdf", () => {
    expect(getAttachmentTypeLabel({ mime_type: "application/pdf" })).toBe("PDF");
  });

  it("returns 'Imagen' for image/jpeg", () => {
    expect(getAttachmentTypeLabel({ mime_type: "image/jpeg" })).toBe("Imagen");
  });

  it("returns 'Archivo' for unknown type", () => {
    expect(getAttachmentTypeLabel({ mime_type: "application/octet-stream" })).toBe("Archivo");
  });
});
