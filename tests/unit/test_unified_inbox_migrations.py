"""
TDD tests for unified-inbox PR1 migrations and model updates.

RED phase: these tests MUST fail before migrations/models are applied.
GREEN phase: pass after running migrations and updating models.

Tests cover:
- T01: ConversationHistory pause/snapshot columns
- T02: ConversationMessage attribution + read tracking
- T03: Escalation resolved_by FK
- T04: SQLAlchemy model updates
"""

import uuid
from datetime import datetime, UTC

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# =============================================================================
# T01 — ConversationHistory new columns
# =============================================================================

class TestConversationHistoryColumns:
    """T01: Verify new pause/snapshot columns on ConversationHistory."""

    async def test_bot_paused_at_accepts_none(self, db_session: AsyncSession) -> None:
        """bot_paused_at is nullable — should default to None."""
        from database.models import ConversationHistory, User

        user = User(phone=f"+34600{uuid.uuid4().int % 10000000:07d}")
        db_session.add(user)
        await db_session.flush()

        conv = ConversationHistory(
            user_id=user.id,
            conversation_id=f"test-conv-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(conv)
        await db_session.commit()
        await db_session.refresh(conv)

        assert conv.bot_paused_at is None

    async def test_bot_paused_at_accepts_datetime(self, db_session: AsyncSession) -> None:
        """bot_paused_at accepts a timezone-aware datetime."""
        from database.models import ConversationHistory, User

        user = User(phone=f"+34600{uuid.uuid4().int % 10000000:07d}")
        db_session.add(user)
        await db_session.flush()

        now = datetime.now(UTC)
        conv = ConversationHistory(
            user_id=user.id,
            conversation_id=f"test-conv-{uuid.uuid4().hex[:8]}",
            bot_paused_at=now,
        )
        db_session.add(conv)
        await db_session.commit()
        await db_session.refresh(conv)

        assert conv.bot_paused_at is not None

    async def test_bot_resumed_at_nullable(self, db_session: AsyncSession) -> None:
        """bot_resumed_at is nullable."""
        from database.models import ConversationHistory, User

        user = User(phone=f"+34600{uuid.uuid4().int % 10000000:07d}")
        db_session.add(user)
        await db_session.flush()

        conv = ConversationHistory(
            user_id=user.id,
            conversation_id=f"test-conv-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(conv)
        await db_session.commit()
        await db_session.refresh(conv)

        assert conv.bot_resumed_at is None

    async def test_bot_paused_by_user_id_fk_nullable(self, db_session: AsyncSession) -> None:
        """bot_paused_by_user_id FK to admin_users is nullable."""
        from database.models import ConversationHistory, User

        user = User(phone=f"+34600{uuid.uuid4().int % 10000000:07d}")
        db_session.add(user)
        await db_session.flush()

        conv = ConversationHistory(
            user_id=user.id,
            conversation_id=f"test-conv-{uuid.uuid4().hex[:8]}",
            bot_paused_by_user_id=None,
        )
        db_session.add(conv)
        await db_session.commit()
        await db_session.refresh(conv)

        assert conv.bot_paused_by_user_id is None

    async def test_state_snapshot_nullable(self, db_session: AsyncSession) -> None:
        """state_snapshot is nullable JSONB."""
        from database.models import ConversationHistory, User

        user = User(phone=f"+34600{uuid.uuid4().int % 10000000:07d}")
        db_session.add(user)
        await db_session.flush()

        conv = ConversationHistory(
            user_id=user.id,
            conversation_id=f"test-conv-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(conv)
        await db_session.commit()
        await db_session.refresh(conv)

        assert conv.state_snapshot is None

    async def test_state_snapshot_accepts_dict(self, db_session: AsyncSession) -> None:
        """state_snapshot accepts a JSON-serializable dict."""
        from database.models import ConversationHistory, User

        user = User(phone=f"+34600{uuid.uuid4().int % 10000000:07d}")
        db_session.add(user)
        await db_session.flush()

        snapshot = {"version": 1, "state": {"current_mode": "PRE_EXPEDIENTE_MODE"}}
        conv = ConversationHistory(
            user_id=user.id,
            conversation_id=f"test-conv-{uuid.uuid4().hex[:8]}",
            state_snapshot=snapshot,
        )
        db_session.add(conv)
        await db_session.commit()
        await db_session.refresh(conv)

        assert conv.state_snapshot == snapshot
        assert conv.state_snapshot["version"] == 1

    async def test_state_snapshot_version_nullable(self, db_session: AsyncSession) -> None:
        """state_snapshot_version is nullable integer."""
        from database.models import ConversationHistory, User

        user = User(phone=f"+34600{uuid.uuid4().int % 10000000:07d}")
        db_session.add(user)
        await db_session.flush()

        conv = ConversationHistory(
            user_id=user.id,
            conversation_id=f"test-conv-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(conv)
        await db_session.commit()
        await db_session.refresh(conv)

        assert conv.state_snapshot_version is None

    async def test_last_inbound_at_nullable(self, db_session: AsyncSession) -> None:
        """last_inbound_at is nullable."""
        from database.models import ConversationHistory, User

        user = User(phone=f"+34600{uuid.uuid4().int % 10000000:07d}")
        db_session.add(user)
        await db_session.flush()

        conv = ConversationHistory(
            user_id=user.id,
            conversation_id=f"test-conv-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(conv)
        await db_session.commit()
        await db_session.refresh(conv)

        assert conv.last_inbound_at is None

    async def test_last_human_message_at_nullable(self, db_session: AsyncSession) -> None:
        """last_human_message_at is nullable."""
        from database.models import ConversationHistory, User

        user = User(phone=f"+34600{uuid.uuid4().int % 10000000:07d}")
        db_session.add(user)
        await db_session.flush()

        conv = ConversationHistory(
            user_id=user.id,
            conversation_id=f"test-conv-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(conv)
        await db_session.commit()
        await db_session.refresh(conv)

        assert conv.last_human_message_at is None

    async def test_paused_by_user_relationship(self, db_session: AsyncSession) -> None:
        """paused_by_user relationship loads the AdminUser."""
        from database.models import AdminUser, ConversationHistory, User

        admin = AdminUser(
            username=f"admin-{uuid.uuid4().hex[:6]}",
            password_hash="$2b$12$test",
            role="admin",
        )
        db_session.add(admin)
        await db_session.flush()

        user = User(phone=f"+34600{uuid.uuid4().int % 10000000:07d}")
        db_session.add(user)
        await db_session.flush()

        conv = ConversationHistory(
            user_id=user.id,
            conversation_id=f"test-conv-{uuid.uuid4().hex[:8]}",
            bot_paused_at=datetime.now(UTC),
            bot_paused_by_user_id=admin.id,
        )
        db_session.add(conv)
        await db_session.commit()
        await db_session.refresh(conv)

        assert conv.paused_by_user is not None
        assert conv.paused_by_user.id == admin.id


# =============================================================================
# T02 — ConversationMessage attribution + read tracking
# =============================================================================

class TestConversationMessageAttribution:
    """T02: Verify author_type, author_user_id, is_read on ConversationMessage."""

    async def _make_conversation(self, db_session: AsyncSession):
        """Helper: create a minimal User + ConversationHistory."""
        from database.models import ConversationHistory, User

        user = User(phone=f"+34600{uuid.uuid4().int % 10000000:07d}")
        db_session.add(user)
        await db_session.flush()

        conv = ConversationHistory(
            user_id=user.id,
            conversation_id=f"test-conv-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(conv)
        await db_session.flush()
        return conv

    async def test_author_type_defaults_to_bot(self, db_session: AsyncSession) -> None:
        """author_type defaults to 'bot' on new messages."""
        from database.models import ConversationMessage

        conv = await self._make_conversation(db_session)
        msg = ConversationMessage(
            conversation_history_id=conv.id,
            role="assistant",
            content="Hola, soy el bot.",
        )
        db_session.add(msg)
        await db_session.commit()
        await db_session.refresh(msg)

        assert msg.author_type == "bot"

    async def test_author_type_accepts_human_agent(self, db_session: AsyncSession) -> None:
        """author_type='human_agent' is valid when author_user_id is set."""
        from database.models import AdminUser, ConversationMessage

        conv = await self._make_conversation(db_session)

        admin = AdminUser(
            username=f"agente-{uuid.uuid4().hex[:6]}",
            password_hash="$2b$12$test",
            role="agent",
        )
        db_session.add(admin)
        await db_session.flush()

        msg = ConversationMessage(
            conversation_history_id=conv.id,
            role="assistant",
            content="Mensaje de agente humano.",
            author_type="human_agent",
            author_user_id=admin.id,
        )
        db_session.add(msg)
        await db_session.commit()
        await db_session.refresh(msg)

        assert msg.author_type == "human_agent"
        assert msg.author_user_id == admin.id

    async def test_author_type_accepts_system(self, db_session: AsyncSession) -> None:
        """author_type='system' is valid."""
        from database.models import ConversationMessage

        conv = await self._make_conversation(db_session)
        msg = ConversationMessage(
            conversation_history_id=conv.id,
            role="assistant",
            content="[Sistema] Bot pausado.",
            author_type="system",
        )
        db_session.add(msg)
        await db_session.commit()
        await db_session.refresh(msg)

        assert msg.author_type == "system"

    async def test_author_type_accepts_user(self, db_session: AsyncSession) -> None:
        """author_type='user' is valid for WhatsApp customer messages."""
        from database.models import ConversationMessage

        conv = await self._make_conversation(db_session)
        msg = ConversationMessage(
            conversation_history_id=conv.id,
            role="user",
            content="Hola, necesito información.",
            author_type="user",
        )
        db_session.add(msg)
        await db_session.commit()
        await db_session.refresh(msg)

        assert msg.author_type == "user"

    async def test_check_constraint_human_agent_requires_user_id(
        self, db_session: AsyncSession
    ) -> None:
        """CHECK: human_agent author_type MUST have author_user_id NOT NULL."""
        from sqlalchemy.exc import IntegrityError
        from database.models import ConversationMessage

        conv = await self._make_conversation(db_session)
        msg = ConversationMessage(
            conversation_history_id=conv.id,
            role="assistant",
            content="Mensaje sin usuario.",
            author_type="human_agent",
            author_user_id=None,  # Violates constraint
        )
        db_session.add(msg)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_is_read_defaults_to_false(self, db_session: AsyncSession) -> None:
        """is_read defaults to False on new messages."""
        from database.models import ConversationMessage

        conv = await self._make_conversation(db_session)
        msg = ConversationMessage(
            conversation_history_id=conv.id,
            role="user",
            content="Nuevo mensaje.",
        )
        db_session.add(msg)
        await db_session.commit()
        await db_session.refresh(msg)

        assert msg.is_read is False

    async def test_is_read_can_be_set_true(self, db_session: AsyncSession) -> None:
        """is_read can be set to True."""
        from database.models import ConversationMessage

        conv = await self._make_conversation(db_session)
        msg = ConversationMessage(
            conversation_history_id=conv.id,
            role="user",
            content="Mensaje leído.",
            is_read=True,
        )
        db_session.add(msg)
        await db_session.commit()
        await db_session.refresh(msg)

        assert msg.is_read is True

    async def test_is_legacy_defaults_to_false(self, db_session: AsyncSession) -> None:
        """is_legacy defaults to False on new messages."""
        from database.models import ConversationMessage

        conv = await self._make_conversation(db_session)
        msg = ConversationMessage(
            conversation_history_id=conv.id,
            role="user",
            content="Nuevo mensaje.",
        )
        db_session.add(msg)
        await db_session.commit()
        await db_session.refresh(msg)

        assert msg.is_legacy is False

    async def test_author_user_relationship_loads(self, db_session: AsyncSession) -> None:
        """author_user relationship loads the linked AdminUser."""
        from database.models import AdminUser, ConversationMessage

        conv = await self._make_conversation(db_session)

        admin = AdminUser(
            username=f"agente2-{uuid.uuid4().hex[:6]}",
            password_hash="$2b$12$test",
            role="agent",
        )
        db_session.add(admin)
        await db_session.flush()

        msg = ConversationMessage(
            conversation_history_id=conv.id,
            role="assistant",
            content="Respuesta humana.",
            author_type="human_agent",
            author_user_id=admin.id,
        )
        db_session.add(msg)
        await db_session.commit()
        await db_session.refresh(msg)

        assert msg.author_user is not None
        assert msg.author_user.id == admin.id

    async def test_no_rows_have_null_author_type_after_backfill(
        self, db_session: AsyncSession
    ) -> None:
        """Post-backfill: no ConversationMessage should have author_type=NULL."""
        result = await db_session.execute(
            text("SELECT COUNT(*) FROM conversation_messages WHERE author_type IS NULL")
        )
        count = result.scalar()
        assert count == 0, f"Found {count} messages with NULL author_type — backfill incomplete"


# =============================================================================
# T03 — Escalation resolved_by FK
# =============================================================================

class TestEscalationResolvedByFK:
    """T03: Verify resolved_by_user_id FK on Escalation."""

    async def _make_escalation(self, db_session: AsyncSession, **kwargs):
        """Helper: create a minimal Escalation."""
        from database.models import Escalation

        esc = Escalation(
            conversation_id=f"esc-conv-{uuid.uuid4().hex[:8]}",
            reason="Test escalation",
            source="tool_call",
            status="pending",
            **kwargs,
        )
        db_session.add(esc)
        await db_session.flush()
        return esc

    async def test_resolved_by_user_id_nullable(self, db_session: AsyncSession) -> None:
        """resolved_by_user_id defaults to None."""
        esc = await self._make_escalation(db_session)
        await db_session.commit()
        await db_session.refresh(esc)

        assert esc.resolved_by_user_id is None

    async def test_resolved_by_user_id_accepts_valid_admin(
        self, db_session: AsyncSession
    ) -> None:
        """resolved_by_user_id can point to an existing AdminUser."""
        from database.models import AdminUser

        admin = AdminUser(
            username=f"resolver-{uuid.uuid4().hex[:6]}",
            password_hash="$2b$12$test",
            role="agent",
        )
        db_session.add(admin)
        await db_session.flush()

        esc = await self._make_escalation(db_session, resolved_by_user_id=admin.id)
        await db_session.commit()
        await db_session.refresh(esc)

        assert esc.resolved_by_user_id == admin.id

    async def test_resolved_by_string_preserved(self, db_session: AsyncSession) -> None:
        """Legacy resolved_by string column is still writable."""
        esc = await self._make_escalation(db_session, resolved_by="Ana García")
        await db_session.commit()
        await db_session.refresh(esc)

        assert esc.resolved_by == "Ana García"

    async def test_resolved_by_user_relationship_loads(
        self, db_session: AsyncSession
    ) -> None:
        """resolved_by_user relationship loads the AdminUser."""
        from database.models import AdminUser

        admin = AdminUser(
            username=f"resolverel-{uuid.uuid4().hex[:6]}",
            password_hash="$2b$12$test",
            role="agent",
        )
        db_session.add(admin)
        await db_session.flush()

        esc = await self._make_escalation(db_session, resolved_by_user_id=admin.id)
        await db_session.commit()
        await db_session.refresh(esc)

        assert esc.resolved_by_user is not None
        assert esc.resolved_by_user.id == admin.id

    async def test_backfill_matched_rows_have_user_id(
        self, db_session: AsyncSession
    ) -> None:
        """Backfill: escalations with matching admin username get resolved_by_user_id."""
        from database.models import AdminUser, Escalation
        from sqlalchemy import select

        username = f"backfill-{uuid.uuid4().hex[:6]}"
        admin = AdminUser(
            username=username,
            password_hash="$2b$12$test",
            role="agent",
        )
        db_session.add(admin)
        await db_session.flush()

        esc = Escalation(
            conversation_id=f"backfill-conv-{uuid.uuid4().hex[:8]}",
            reason="Backfill test",
            source="tool_call",
            status="resolved",
            resolved_by=username,
        )
        db_session.add(esc)
        await db_session.commit()

        # Simulate backfill logic (what the migration does)
        await db_session.execute(
            text("""
                UPDATE escalations e
                SET resolved_by_user_id = au.id
                FROM admin_users au
                WHERE e.resolved_by IS NOT NULL
                  AND e.resolved_by_user_id IS NULL
                  AND (
                      LOWER(au.username) = LOWER(e.resolved_by)
                      OR LOWER(au.display_name) = LOWER(e.resolved_by)
                  )
            """)
        )
        await db_session.commit()

        result = await db_session.execute(
            select(Escalation).where(Escalation.id == esc.id)
        )
        esc_refreshed = result.scalar_one()
        assert esc_refreshed.resolved_by_user_id == admin.id
