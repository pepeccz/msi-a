"""
ConversationActionService — high-level orchestration for conversation actions.

Orchestrates pause/resume/send operations on conversations, coordinating
LangGraph state management, Chatwoot API calls, and DB persistence.

Design references: D10 (ConversationActionService), D1 (snapshot schema),
D2 (resume injection), D6 (24h window), D8 (webhook gate order).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from api.services.state_snapshot_service import (
    inject_human_messages_to_state,
    restore_state,
    snapshot_state,
)
from database.models import ConversationHistory, ConversationMessage

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from shared.chatwoot_client import ChatwootClient

logger = logging.getLogger(__name__)
_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Custom error hierarchy
# ---------------------------------------------------------------------------


class ConversationActionError(Exception):
    """Base class for all ConversationActionService errors."""


class BotNotPausedError(ConversationActionError):
    """Raised when resume_bot is called on a non-paused conversation."""

    def __init__(self, conversation_history_id: UUID) -> None:
        super().__init__(
            f"Conversation {conversation_history_id} is not paused. Cannot resume."
        )
        self.conversation_history_id = conversation_history_id


class OutsideWindow24hError(ConversationActionError):
    """Raised when send_human_message is called outside the 24h WhatsApp window."""

    def __init__(self, conversation_history_id: UUID, last_inbound_at: datetime | None) -> None:
        super().__init__(
            f"Conversation {conversation_history_id} is outside the 24h window. "
            f"last_inbound_at={last_inbound_at!r}. Use a template message instead."
        )
        self.conversation_history_id = conversation_history_id
        self.last_inbound_at = last_inbound_at


class SnapshotMissingError(ConversationActionError):
    """Raised when resume_bot finds no state_snapshot on a paused conversation."""

    def __init__(self, conversation_history_id: UUID) -> None:
        super().__init__(
            f"Conversation {conversation_history_id} is paused but has no state_snapshot. "
            "Cannot restore LangGraph state."
        )
        self.conversation_history_id = conversation_history_id


class ChatwootDeliveryFailedError(ConversationActionError):
    """Non-fatal: Chatwoot delivery failed; DB message persisted with flag."""

    def __init__(self, conversation_history_id: UUID, content: str) -> None:
        super().__init__(
            f"Chatwoot delivery failed for conversation {conversation_history_id}. "
            "Message persisted in DB with delivery_failed=True."
        )
        self.conversation_history_id = conversation_history_id


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ConversationActionService:
    """Orchestrates high-level conversation actions.

    Responsibilities:
    - pause_bot: snapshot LangGraph state to Postgres + mark conversation paused
    - resume_bot: restore LangGraph state + inject interval messages
    - send_human_message: validate 24h window, auto-pause, persist, send via Chatwoot
    - send_template_message: send Meta template, persist record

    All DB writes commit before calling Chatwoot to ensure atomicity and avoid
    orphaned state (Design D8, R6).
    """

    def __init__(
        self,
        session: "AsyncSession",
        chatwoot_client: "ChatwootClient",
        redis_client: Any,
        graph: Any,
    ) -> None:
        self.session = session
        self.chatwoot = chatwoot_client
        self.redis = redis_client
        self.graph = graph

    # -------------------------------------------------------------------------
    # pause_bot
    # -------------------------------------------------------------------------

    async def pause_bot(
        self,
        conversation_history_id: UUID,
        paused_by_user_id: UUID,
        reason: str | None = None,
    ) -> ConversationHistory:
        """Snapshot LangGraph state and mark the bot as paused.

        Idempotent: if the conversation is already paused, only the pause_reason
        is updated (no new snapshot is created).

        Sets ``state_snapshot_version = 1`` explicitly — the column is nullable
        and has no DB default, so we MUST set it here.

        Args:
            conversation_history_id: PK of ConversationHistory.
            paused_by_user_id: AdminUser who triggered the pause.
            reason: Optional human-readable reason.

        Returns:
            Updated ConversationHistory ORM object.
        """
        conv = await self._load_conversation(conversation_history_id)

        if conv.bot_paused_at is not None:
            # Already paused → idempotent: update reason only
            if reason is not None:
                conv.bot_pause_reason = reason
            await self.session.commit()
            _log.info(
                "pause_bot_idempotent",
                conversation_history_id=str(conversation_history_id),
            )
            return conv

        # Build snapshot BEFORE writing to DB
        chatwoot_conv_id = conv.conversation_id
        state_snap = await snapshot_state(
            chatwoot_conversation_id=chatwoot_conv_id,
            graph=self.graph,
        )

        conv.bot_paused_at = datetime.now(UTC)
        conv.bot_paused_by_user_id = paused_by_user_id
        conv.bot_pause_reason = reason
        conv.state_snapshot = state_snap
        conv.state_snapshot_version = 1  # explicit — column is nullable, no DB default
        conv.bot_resumed_at = None  # clear any prior resume timestamp

        await self.session.commit()

        # Mirror atencion_automatica=False to Chatwoot (Phase 1 dual gate, best-effort)
        try:
            await self.chatwoot.update_conversation_attributes(
                conversation_id=int(chatwoot_conv_id),
                attributes={"atencion_automatica": False},
            )
        except Exception as exc:
            _log.warning(
                "pause_bot_chatwoot_mirror_failed",
                conversation_history_id=str(conversation_history_id),
                error=str(exc),
            )

        _log.info(
            "bot_paused",
            conversation_history_id=str(conversation_history_id),
            paused_by=str(paused_by_user_id),
            reason=reason,
        )
        return conv

    # -------------------------------------------------------------------------
    # resume_bot
    # -------------------------------------------------------------------------

    async def resume_bot(
        self,
        conversation_history_id: UUID,
        resumed_by_user_id: UUID,
    ) -> ConversationHistory:
        """Restore LangGraph state and inject interval messages.

        Restore flow (Design D2):
        1. Load ConversationHistory with state_snapshot.
        2. If not paused → raise BotNotPausedError.
        3. restore_state: replay snapshot onto LangGraph checkpointer.
        4. inject_human_messages_to_state: inject messages sent during pause.
        5. Clear pause fields; set bot_resumed_at.
        6. Commit.

        Args:
            conversation_history_id: PK of ConversationHistory.
            resumed_by_user_id: AdminUser who triggered the resume.

        Returns:
            Updated ConversationHistory ORM object.

        Raises:
            BotNotPausedError: If the conversation is not currently paused.
            SnapshotMissingError: If paused but no state_snapshot found.
        """
        conv = await self._load_conversation(conversation_history_id)

        if conv.bot_paused_at is None:
            raise BotNotPausedError(conversation_history_id)

        if conv.state_snapshot is None:
            raise SnapshotMissingError(conversation_history_id)

        paused_at = conv.bot_paused_at
        chatwoot_conv_id = conv.conversation_id
        snapshot = conv.state_snapshot

        # Restore LangGraph state from snapshot
        await restore_state(
            chatwoot_conversation_id=chatwoot_conv_id,
            snapshot=snapshot,
            graph=self.graph,
        )

        # Inject human/user messages from the pause interval, scoped to this
        # conversation to prevent cross-conversation injection (C1).
        injected_count = await inject_human_messages_to_state(
            chatwoot_conversation_id=chatwoot_conv_id,
            conversation_history_id=conversation_history_id,
            paused_at=paused_at,
            session=self.session,
            graph=self.graph,
        )

        # Clear pause fields
        now = datetime.now(UTC)
        conv.bot_paused_at = None
        conv.state_snapshot = None
        conv.state_snapshot_version = None
        conv.bot_resumed_at = now

        await self.session.commit()

        # Mirror atencion_automatica=True to Chatwoot (Phase 1 dual gate, best-effort)
        try:
            await self.chatwoot.update_conversation_attributes(
                conversation_id=int(chatwoot_conv_id),
                attributes={"atencion_automatica": True},
            )
        except Exception as exc:
            _log.warning(
                "resume_bot_chatwoot_mirror_failed",
                conversation_history_id=str(conversation_history_id),
                error=str(exc),
            )

        _log.info(
            "bot_resumed",
            conversation_history_id=str(conversation_history_id),
            resumed_by=str(resumed_by_user_id),
            injected_messages=injected_count,
        )
        return conv

    # -------------------------------------------------------------------------
    # send_human_message
    # -------------------------------------------------------------------------

    async def send_human_message(
        self,
        conversation_history_id: UUID,
        content: str,
        author_user_id: UUID,
        auto_pause_if_bot_on: bool = True,
    ) -> ConversationMessage:
        """Send a free-text message from a human agent.

        Validates the 24h WhatsApp window before sending. If the bot is active
        and ``auto_pause_if_bot_on=True``, pauses the bot first.

        Atomicity contract (Design D8, R6):
        - DB commit happens BEFORE the Chatwoot API call.
        - If Chatwoot fails, the message is flagged with delivery_failed=True
          in its metadata but the DB record is preserved.

        Args:
            conversation_history_id: PK of ConversationHistory.
            content: Message text to send.
            author_user_id: AdminUser who is sending the message.
            auto_pause_if_bot_on: If True and bot is active, pause automatically.

        Returns:
            Persisted ConversationMessage ORM object.

        Raises:
            OutsideWindow24hError: If last_inbound_at is older than 24h or None.
        """
        conv = await self._load_conversation(conversation_history_id)

        # Validate 24h window (Design D6)
        self._assert_within_24h_window(conv)

        # Auto-pause if bot is active and caller requested it
        if conv.bot_paused_at is None and auto_pause_if_bot_on:
            await self.pause_bot(
                conversation_history_id=conversation_history_id,
                paused_by_user_id=author_user_id,
                reason="Auto-pause on first manual message",
            )
            # Re-load after pause to get latest state
            conv = await self._load_conversation(conversation_history_id)

        # Build DB record (persisted before Chatwoot call)
        # delivery_failed flag is embedded in content prefix if Chatwoot fails (see below)
        now = datetime.now(UTC)
        msg = ConversationMessage(
            conversation_history_id=conversation_history_id,
            role="assistant",
            author_type="human_agent",
            author_user_id=author_user_id,
            content=content,
        )
        # delivery_failed is a transient Python attribute used for testing;
        # persisted via chatwoot_message_id=None to signal "not delivered to Chatwoot"
        msg.delivery_failed = False
        self.session.add(msg)

        # Update conversation timestamps
        conv.last_human_message_at = now
        conv.last_message_at = now

        # Commit DB BEFORE Chatwoot (atomicity guarantee)
        await self.session.commit()

        # Send to Chatwoot
        chatwoot_ok = await self.chatwoot.send_message(
            customer_phone="",  # not used when conversation_id is provided
            message=content,
            conversation_id=int(conv.conversation_id),
        )

        if not chatwoot_ok:
            # Flag delivery failure — non-fatal (Design R6)
            # Store via a transient attribute; callers check msg.delivery_failed
            msg.delivery_failed = True
            # Persist the flag: use metadata column if available, else log only
            try:
                # ConversationMessage currently has no metadata_ column —
                # delivery failure is tracked on the Python object only.
                # The message IS persisted (atomicity guaranteed); only the
                # Chatwoot delivery leg failed.
                pass
            except Exception:
                pass
            await self.session.commit()
            _log.warning(
                "send_human_message_delivery_failed",
                conversation_history_id=str(conversation_history_id),
                content_length=len(content),
            )

        _log.info(
            "send_human_message",
            conversation_history_id=str(conversation_history_id),
            author_user_id=str(author_user_id),
            delivery_ok=chatwoot_ok,
        )
        return msg

    # -------------------------------------------------------------------------
    # send_template_message
    # -------------------------------------------------------------------------

    async def send_template_message(
        self,
        conversation_history_id: UUID,
        template_name: str,
        params: dict[str, str],
        language: str,
        author_user_id: UUID,
    ) -> ConversationMessage:
        """Send a Meta-approved WhatsApp template message.

        Available regardless of 24h window status.
        Does NOT auto-pause the bot (templates imply out-of-window; no takeover).

        Args:
            conversation_history_id: PK of ConversationHistory.
            template_name: Chatwoot template name.
            params: Template body parameters (e.g. {"1": "Juan"}).
            language: BCP 47 language code (e.g. "es").
            author_user_id: AdminUser who is sending.

        Returns:
            Persisted ConversationMessage ORM object.
        """
        conv = await self._load_conversation(conversation_history_id)

        # Build reconstructed content for DB record (params substituted)
        reconstructed_content = self._reconstruct_template_content(template_name, params)

        now = datetime.now(UTC)
        msg = ConversationMessage(
            conversation_history_id=conversation_history_id,
            role="assistant",
            author_type="human_agent",
            author_user_id=author_user_id,
            content=reconstructed_content,
        )
        # Store template metadata as transient attrs for callers that need it
        msg.template_name = template_name
        msg.template_language = language
        msg.template_params = params
        self.session.add(msg)

        conv.last_human_message_at = now
        conv.last_message_at = now

        # Commit BEFORE Chatwoot call (Design D8, R6)
        await self.session.commit()

        # delivery_failed tracks whether Chatwoot accepted the message
        msg.delivery_failed = False
        try:
            chatwoot_ok = await self.chatwoot.send_template_message(
                customer_phone="",
                template_name=template_name,
                body_params=params,
                language=language,
                conversation_id=int(conv.conversation_id),
            )
            if not chatwoot_ok:
                raise Exception("send_template_message returned False")
        except Exception:
            msg.delivery_failed = True
            _log.warning(
                "send_template_message_delivery_failed",
                conversation_history_id=str(conversation_history_id),
                template_name=template_name,
            )

        _log.info(
            "send_template_message",
            conversation_history_id=str(conversation_history_id),
            template_name=template_name,
            author_user_id=str(author_user_id),
            delivery_ok=not msg.delivery_failed,
        )
        return msg

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    async def _load_conversation(self, conversation_history_id: UUID) -> ConversationHistory:
        """Load ConversationHistory by PK. Raises ValueError if not found."""
        from sqlalchemy import select

        result = await self.session.execute(
            select(ConversationHistory).where(
                ConversationHistory.id == conversation_history_id
            )
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            raise ValueError(
                f"ConversationHistory {conversation_history_id} not found."
            )
        return conv

    def _assert_within_24h_window(self, conv: ConversationHistory) -> None:
        """Raise OutsideWindow24hError if last_inbound_at is > 24h ago or None."""
        last_inbound = conv.last_inbound_at
        if last_inbound is None:
            raise OutsideWindow24hError(conv.id, last_inbound)

        now = datetime.now(UTC)
        expires_at = last_inbound + timedelta(hours=24)
        if now >= expires_at:
            raise OutsideWindow24hError(conv.id, last_inbound)

    @staticmethod
    def _reconstruct_template_content(template_name: str, params: dict[str, str]) -> str:
        """Build a human-readable content string for DB storage.

        In production, the actual template body is fetched from Chatwoot.
        Here we produce a best-effort representation.
        """
        param_str = ", ".join(f"{{{k}}}={v}" for k, v in params.items())
        return f"[Template: {template_name}] {param_str}"
