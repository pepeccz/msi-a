"""
MSI Automotive - ConversationState schema for LangGraph StateGraph.

This module defines the typed state structure for the conversation graph.
"""

from datetime import datetime
from typing import Any, TypedDict


class ConversationState(TypedDict, total=False):
    """
    State schema for MSI Automotive conversation agent.

    All fields are optional (total=False) to allow partial state updates.

    Fields:
        # Core Metadata
        conversation_id: LangGraph thread_id for checkpointing
        user_phone: E.164 phone (e.g., +34612345678)
        user_name: User name from WhatsApp
        user_id: Database user UUID (if exists)
        client_type: User type ("particular" or "professional")

        # Messages
        messages: Recent conversation history (FIFO windowing)
            Format: [{"role": "user"|"assistant", "content": str, "timestamp": str}]
        user_message: Incoming message to process
        conversation_summary: Summary for context window management
        total_message_count: Total messages (including summarized)

        # Current State
        current_state: Current conversation state (e.g., "idle", "inquiry")
        fsm_state: FSM state dict (for future expansion)

        # Flags
        is_first_interaction: True if user's first message ever
        escalation_triggered: Whether escalated to human
        escalation_reason: Why escalated (e.g., "complex_case")
        error_count: Consecutive errors (for auto-escalation)
        images_sent_for_current_quote: Whether example images were already sent for current quote

        # Pending Action (for confirmation flow)
        pending_action: Action awaiting user confirmation (e.g., "iniciar_expediente")
        pending_action_context: Tool arguments to use when user confirms

        # Tool Results
        pending_images: Image metadata from tool calls (documentation examples)
            Format: {"images": [{"url": str, "tipo": str, "descripcion": str}], "follow_up_message": str | None}
            Legacy format: [{"url": str, "tipo": str, "descripcion": str}]
            tipo: "base" (documentación base) | "elemento" (documentación específica)
        tarifa_actual: Cached tariff result from calcular_tarifa_con_elementos
            Format: {"tier_id": str, "tier_name": str, "price": float, "element_codes": list, "imagenes_ejemplo": list}

        # Incoming Attachments (from current message)
        incoming_attachments: Attachments from current user message
            Format: [{"id": int, "file_type": str, "data_url": str}]
            Used by case collection FSM to process user-uploaded images

        # Context (for future expansion)
        context: Dict for storing conversation context data

        # Timestamps
        created_at: Conversation start (Europe/Madrid)
        updated_at: Last modification (Europe/Madrid)

        # Node Tracking
        last_node: Last executed node (for debugging)
    """

    # Core Metadata
    conversation_id: str
    user_phone: str
    user_name: str | None
    user_id: str | None
    client_type: str | None  # "particular" or "professional"

    # Messages
    messages: list[dict[str, Any]]
    user_message: str | None
    conversation_summary: str | None
    total_message_count: int

    # Current State
    current_state: str
    fsm_state: dict[str, Any] | None

    # Flags
    is_first_interaction: bool
    escalation_triggered: bool
    escalation_reason: str | None
    error_count: int
    images_sent_for_current_quote: bool

    # Pending Action (for confirmation flow)
    pending_action: str | None  # "iniciar_expediente", etc.
    pending_action_context: dict[str, Any] | None  # Tool arguments for pending action

    # Tool Results
    pending_images: list[dict[str, Any]] | dict[str, Any]
    tarifa_actual: dict[str, Any] | None

    # Incoming Attachments
    incoming_attachments: list[dict[str, Any]]

    # Context
    context: dict[str, Any]

    # Timestamps
    created_at: datetime
    updated_at: datetime

    # Node Tracking
    last_node: str | None
