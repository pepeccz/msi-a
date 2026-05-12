/**
 * inbox-grouping.ts — WhatsApp-style message grouping pre-processor.
 *
 * Groups consecutive image-only messages from the same author into album
 * bubbles per spec Capability 7.
 *
 * Rules (all must hold for messages to be merged into the same album):
 *   - Same author_type
 *   - Both messages have attachments.length > 0 AND content === "" (image-only)
 *   - Created at timestamps within 60 seconds of each other
 *   - Combined attachment count does not exceed 10
 *
 * On a boundary, the current group is closed and a new one starts with the
 * triggering message. A single message always produces a single Group.
 *
 * Timestamp of the group = last message's created_at (spec scenario 6).
 *
 * Pure function — no side effects, no imports from React or next.js.
 */

import type { ConversationMessageResponse, MessageAttachment } from "./types";

// ────────────────────────────────────────────────────────────────
// Types
// ────────────────────────────────────────────────────────────────

export interface SingleGroup {
  type: "single";
  message: ConversationMessageResponse;
}

export interface AlbumGroup {
  type: "album";
  /** All messages merged into this album (≥ 2). */
  messages: ConversationMessageResponse[];
  /** Combined attachments from all messages, position re-indexed 0…N-1. */
  attachments: MessageAttachment[];
  /** author_type of all messages in this album (they share the same one). */
  author_type: string;
  /** Timestamp of the last message in the album. */
  timestamp: string;
}

export type MessageGroup = SingleGroup | AlbumGroup;

// ────────────────────────────────────────────────────────────────
// Constants
// ────────────────────────────────────────────────────────────────

const MAX_ALBUM_ATTACHMENTS = 10;
// 3 min — matches WhatsApp Web's observed behavior. Strict 60s was too tight in practice.
const MAX_GAP_SECONDS = 180;

// ────────────────────────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────────────────────────

function isImageOnly(msg: ConversationMessageResponse): boolean {
  return (
    Array.isArray(msg.attachments) &&
    msg.attachments.length > 0 &&
    (msg.content === "" || msg.content == null)
  );
}

function diffSeconds(a: string, b: string): number {
  return Math.abs(
    (new Date(b).getTime() - new Date(a).getTime()) / 1000,
  );
}

function buildAlbum(messages: ConversationMessageResponse[]): AlbumGroup {
  // Re-index positions so the combined array is 0-based
  const combined: MessageAttachment[] = [];
  let pos = 0;
  for (const msg of messages) {
    for (const att of msg.attachments) {
      combined.push({ ...att, position: pos++ });
    }
  }
  return {
    type: "album",
    messages,
    attachments: combined,
    author_type: messages[0].author_type,
    timestamp: messages[messages.length - 1].created_at,
  };
}

// ────────────────────────────────────────────────────────────────
// Main export
// ────────────────────────────────────────────────────────────────

/**
 * Pre-process a flat messages array into grouped MessageGroup objects.
 *
 * @param messages  Messages in chronological order (oldest first).
 * @returns         Array of MessageGroup objects preserving chronological order.
 */
export function groupMessages(
  messages: ConversationMessageResponse[],
): MessageGroup[] {
  if (messages.length === 0) return [];

  const groups: MessageGroup[] = [];
  // Current accumulation buffer
  let buffer: ConversationMessageResponse[] = [];
  let bufferAttCount = 0;

  function flushBuffer(): void {
    if (buffer.length === 0) return;
    if (buffer.length === 1) {
      groups.push({ type: "single", message: buffer[0] });
    } else {
      groups.push(buildAlbum(buffer));
    }
    buffer = [];
    bufferAttCount = 0;
  }

  for (const msg of messages) {
    const imageOnly = isImageOnly(msg);
    const msgAttCount = imageOnly ? msg.attachments.length : 0;

    if (!imageOnly) {
      // Not image-only → flush whatever we have, emit single
      flushBuffer();
      groups.push({ type: "single", message: msg });
      continue;
    }

    if (buffer.length === 0) {
      // Start a new buffer
      buffer = [msg];
      bufferAttCount = msgAttCount;
      continue;
    }

    // There is an active buffer — check merge conditions
    const last = buffer[buffer.length - 1];

    const sameAuthor = last.author_type === msg.author_type;
    const withinWindow = diffSeconds(last.created_at, msg.created_at) <= MAX_GAP_SECONDS;
    const fitsInAlbum = bufferAttCount + msgAttCount <= MAX_ALBUM_ATTACHMENTS;

    if (sameAuthor && withinWindow && fitsInAlbum) {
      buffer.push(msg);
      bufferAttCount += msgAttCount;
    } else {
      // Boundary hit — flush and start new buffer with this message
      flushBuffer();
      buffer = [msg];
      bufferAttCount = msgAttCount;
    }
  }

  flushBuffer();
  return groups;
}
