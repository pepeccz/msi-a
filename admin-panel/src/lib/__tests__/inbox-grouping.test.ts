/**
 * Unit tests for inbox-grouping.ts — pure groupMessages() function.
 *
 * TDD cycle: RED (tests written alongside implementation — T14)
 *
 * Spec Capability 7 scenarios:
 *   1. 3 image-only messages within 10s → 1 album group
 *   2. Image with caption breaks the group
 *   3. Different sender breaks the group
 *   4. Time gap > 180s breaks the group (relaxed from initial 60s to match WhatsApp Web)
 *   5. Group exceeds 10 images → splits into multiple groups
 *   6. Grouped album shows last message timestamp
 *
 * Additional edge cases:
 *   - Empty array → []
 *   - Single non-image message → 1 single group
 *   - Mix of image-only and captioned → correct grouping
 *   - Attachments re-indexed 0-based across merged messages
 */

import { groupMessages } from "../inbox-grouping";
import type { ConversationMessageResponse, MessageAttachment } from "../types";

// ────────────────────────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────────────────────────

let idCounter = 0;

function makeId(): string {
  return `msg-${++idCounter}`;
}

function makeAtt(position = 0): MessageAttachment {
  return {
    id: `att-${++idCounter}`,
    url: `/conversation-images/conv/${idCounter}.png`,
    kind: "image",
    content_type: "image/png",
    filename: `img${idCounter}.png`,
    size_bytes: 100,
    width: 10,
    height: 10,
    position,
    created_at: new Date().toISOString(),
  };
}

function makeMsg(
  options: {
    authorType?: string;
    content?: string;
    attachments?: MessageAttachment[];
    createdAt?: string;
  } = {},
): ConversationMessageResponse {
  const {
    authorType = "user",
    content = "",
    attachments = [],
    createdAt = new Date().toISOString(),
  } = options;

  return {
    id: makeId(),
    conversation_history_id: "conv-1",
    role: "user",
    author_type: authorType as ConversationMessageResponse["author_type"],
    author_user_id: null,
    author_user_name: null,
    content,
    created_at: createdAt,
    is_read: true,
    has_images: attachments.length > 0,
    image_count: attachments.length,
    chatwoot_message_id: null,
    delivery_failed: false,
    attachments,
  };
}

/** Build an ISO timestamp offset from a base by seconds. */
function offsetSeconds(base: string, seconds: number): string {
  return new Date(new Date(base).getTime() + seconds * 1000).toISOString();
}

// ────────────────────────────────────────────────────────────────
// Tests
// ────────────────────────────────────────────────────────────────

beforeEach(() => {
  idCounter = 0;
});

describe("groupMessages()", () => {
  // Edge: empty array
  it("returns empty array for empty input", () => {
    expect(groupMessages([])).toEqual([]);
  });

  // Edge: single non-image message
  it("wraps a single non-image message as a single group", () => {
    const msg = makeMsg({ content: "hello" });
    const groups = groupMessages([msg]);
    expect(groups).toHaveLength(1);
    expect(groups[0].type).toBe("single");
    if (groups[0].type === "single") {
      expect(groups[0].message.id).toBe(msg.id);
    }
  });

  // Scenario 1: 3 image-only messages within 10s → 1 album
  it("merges 3 image-only messages from same author within 10s into 1 album", () => {
    const t0 = new Date("2026-01-01T12:00:00Z").toISOString();
    const msgs = [
      makeMsg({ attachments: [makeAtt()], createdAt: t0 }),
      makeMsg({ attachments: [makeAtt()], createdAt: offsetSeconds(t0, 3) }),
      makeMsg({ attachments: [makeAtt()], createdAt: offsetSeconds(t0, 7) }),
    ];

    const groups = groupMessages(msgs);
    expect(groups).toHaveLength(1);
    expect(groups[0].type).toBe("album");
    if (groups[0].type === "album") {
      expect(groups[0].messages).toHaveLength(3);
      expect(groups[0].attachments).toHaveLength(3);
    }
  });

  // Scenario 2: Image with caption breaks the group
  it("does not merge image+caption message — it breaks any group", () => {
    const t0 = new Date("2026-01-01T12:00:00Z").toISOString();
    const msgA = makeMsg({ attachments: [makeAtt()], createdAt: t0 });
    const msgB = makeMsg({
      attachments: [makeAtt()],
      content: "aquí va la foto",
      createdAt: offsetSeconds(t0, 2),
    }); // has caption — should NOT merge
    const msgC = makeMsg({ attachments: [makeAtt()], createdAt: offsetSeconds(t0, 4) });

    const groups = groupMessages([msgA, msgB, msgC]);
    expect(groups).toHaveLength(3);
    expect(groups.every((g) => g.type === "single")).toBe(true);
  });

  // Scenario 3: Different sender breaks the group
  it("splits at author_type change", () => {
    const t0 = new Date("2026-01-01T12:00:00Z").toISOString();
    const msgUser = makeMsg({ authorType: "user", attachments: [makeAtt()], createdAt: t0 });
    const msgBot = makeMsg({
      authorType: "assistant",
      attachments: [makeAtt()],
      createdAt: offsetSeconds(t0, 5),
    });

    const groups = groupMessages([msgUser, msgBot]);
    expect(groups).toHaveLength(2);
    expect(groups[0].type).toBe("single");
    expect(groups[1].type).toBe("single");
  });

  // Scenario 4: Time gap > 180s breaks the group
  it("splits when consecutive messages are more than 180s apart", () => {
    const t0 = new Date("2026-01-01T12:00:00Z").toISOString();
    const msgA = makeMsg({ attachments: [makeAtt()], createdAt: t0 });
    const msgB = makeMsg({ attachments: [makeAtt()], createdAt: offsetSeconds(t0, 200) });

    const groups = groupMessages([msgA, msgB]);
    expect(groups).toHaveLength(2);
    expect(groups.every((g) => g.type === "single")).toBe(true);
  });

  // Exactly 180s gap — should still be merged
  it("merges messages that are exactly 180s apart", () => {
    const t0 = new Date("2026-01-01T12:00:00Z").toISOString();
    const msgA = makeMsg({ attachments: [makeAtt()], createdAt: t0 });
    const msgB = makeMsg({ attachments: [makeAtt()], createdAt: offsetSeconds(t0, 180) });

    const groups = groupMessages([msgA, msgB]);
    expect(groups).toHaveLength(1);
    expect(groups[0].type).toBe("album");
  });

  // Scenario 5: Group exceeds 10 images — splits
  it("splits into 2 groups when combined attachments would exceed 10", () => {
    const t0 = new Date("2026-01-01T12:00:00Z").toISOString();
    // 10 messages × 1 attachment = 10 → all in one album
    const msgs10 = Array.from({ length: 10 }, (_, i) =>
      makeMsg({ attachments: [makeAtt()], createdAt: offsetSeconds(t0, i * 2) }),
    );
    // 11th message would push to 11 → must start a new group
    const msg11 = makeMsg({
      attachments: [makeAtt()],
      createdAt: offsetSeconds(t0, 22),
    });

    const groups = groupMessages([...msgs10, msg11]);
    expect(groups).toHaveLength(2);
    expect(groups[0].type).toBe("album");
    if (groups[0].type === "album") {
      expect(groups[0].attachments).toHaveLength(10);
    }
    // Second group is a single (1 message)
    expect(groups[1].type).toBe("single");
  });

  // 12 consecutive image-only messages → 2 groups (10 + 2)
  it("splits 12 messages into groups of 10 and 2", () => {
    const t0 = new Date("2026-01-01T12:00:00Z").toISOString();
    const msgs = Array.from({ length: 12 }, (_, i) =>
      makeMsg({ attachments: [makeAtt()], createdAt: offsetSeconds(t0, i * 2) }),
    );

    const groups = groupMessages(msgs);
    expect(groups).toHaveLength(2);
    if (groups[0].type === "album") {
      expect(groups[0].attachments).toHaveLength(10);
    }
    if (groups[1].type === "album") {
      expect(groups[1].attachments).toHaveLength(2);
    } else if (groups[1].type === "single") {
      // single with 2 attachments — also valid if msg has 2 atts
      expect(groups[1].message.attachments).toHaveLength(1);
    }
  });

  // Scenario 6: Grouped album shows last message timestamp
  it("album timestamp equals the last message's created_at", () => {
    const t0 = new Date("2026-01-01T12:00:00Z").toISOString();
    const t1 = offsetSeconds(t0, 5);
    const t2 = offsetSeconds(t0, 10);
    const msgs = [
      makeMsg({ attachments: [makeAtt()], createdAt: t0 }),
      makeMsg({ attachments: [makeAtt()], createdAt: t1 }),
      makeMsg({ attachments: [makeAtt()], createdAt: t2 }),
    ];

    const groups = groupMessages(msgs);
    expect(groups[0].type).toBe("album");
    if (groups[0].type === "album") {
      expect(groups[0].timestamp).toBe(t2);
    }
  });

  // Attachment positions re-indexed 0-based in album
  it("re-indexes attachment positions 0-based across merged messages", () => {
    const t0 = new Date("2026-01-01T12:00:00Z").toISOString();
    const msgs = [
      makeMsg({ attachments: [makeAtt(0)], createdAt: t0 }),
      makeMsg({ attachments: [makeAtt(0), makeAtt(1)], createdAt: offsetSeconds(t0, 3) }),
    ];

    const groups = groupMessages(msgs);
    expect(groups[0].type).toBe("album");
    if (groups[0].type === "album") {
      const positions = groups[0].attachments.map((a) => a.position);
      expect(positions).toEqual([0, 1, 2]);
    }
  });

  // Non-image messages should remain single
  it("does not merge text-only messages", () => {
    const t0 = new Date("2026-01-01T12:00:00Z").toISOString();
    const msgs = [
      makeMsg({ content: "hola", createdAt: t0 }),
      makeMsg({ content: "¿cómo estás?", createdAt: offsetSeconds(t0, 2) }),
    ];
    const groups = groupMessages(msgs);
    expect(groups).toHaveLength(2);
    expect(groups.every((g) => g.type === "single")).toBe(true);
  });

  // Mixed: text, image-only, image-only, text → [single, album, single]
  it("correctly handles mixed text and image-only sequences", () => {
    const t0 = new Date("2026-01-01T12:00:00Z").toISOString();
    const msgs = [
      makeMsg({ content: "texto", createdAt: t0 }),
      makeMsg({ attachments: [makeAtt()], createdAt: offsetSeconds(t0, 5) }),
      makeMsg({ attachments: [makeAtt()], createdAt: offsetSeconds(t0, 8) }),
      makeMsg({ content: "otro texto", createdAt: offsetSeconds(t0, 10) }),
    ];
    const groups = groupMessages(msgs);
    expect(groups).toHaveLength(3);
    expect(groups[0].type).toBe("single");
    expect(groups[1].type).toBe("album");
    expect(groups[2].type).toBe("single");
  });
});
