"""
Unit tests for message_persistence_service.py.

Tests the fix for conversation_id type mismatch (str | int → str cast).
Verifies:
- Integer conversation_id saves correctly
- String conversation_id saves correctly
- Long string conversation_id saves correctly
- Messages save to both ConversationHistory and ConversationMessage
- Image count updates correctly
"""

import pytest
import pytest_asyncio
import uuid
from datetime import datetime, UTC
from sqlalchemy import select, String, DateTime, Integer, Boolean, BigInteger, Column
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.dialects.postgresql import UUID as UUID_TYPE
from unittest.mock import patch

from api.services.message_persistence_service import (
    get_or_create_conversation_history,
    save_user_message,
    save_assistant_message,
    update_message_image_count,
)

# Create minimal models for testing (without JSONB fields)
TestBase = declarative_base()

class TestConversationHistory(TestBase):
    """Minimal ConversationHistory for testing."""
    __tablename__ = "conversation_history"
    
    id = Column(UUID_TYPE(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(String, unique=True, nullable=False)
    user_id = Column(UUID_TYPE(as_uuid=True), nullable=True)
    message_count = Column(Integer, default=0)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_message_at = Column(DateTime(timezone=True), nullable=True)


class TestConversationMessage(TestBase):
    """Minimal ConversationMessage for testing."""
    __tablename__ = "conversation_messages"
    
    id = Column(UUID_TYPE(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_history_id = Column(UUID_TYPE(as_uuid=True), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(String, nullable=False)
    chatwoot_message_id = Column(BigInteger, nullable=True)
    has_images = Column(Boolean, default=False)
    image_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


@pytest_asyncio.fixture(scope="function")
async def in_memory_engine():
    """Create SQLite in-memory engine for unit tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    
    # Create only test tables (no JSONB)
    async with engine.begin() as conn:
        await conn.run_sync(TestBase.metadata.create_all)
    
    yield engine
    
    # Cleanup
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def in_memory_session(in_memory_engine):
    """Provide in-memory session for unit tests."""
    TestingSessionLocal = sessionmaker(
        in_memory_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    
    async with TestingSessionLocal() as session:
        # Patch get_async_session to use in-memory session
        with patch("api.services.message_persistence_service.get_async_session") as mock_get_session:
            # Patch database models to use test models
            with patch("api.services.message_persistence_service.ConversationHistory", TestConversationHistory):
                with patch("api.services.message_persistence_service.ConversationMessage", TestConversationMessage):
                    # Return a context manager mock
                    from unittest.mock import AsyncMock
                    ctx_manager = AsyncMock()
                    ctx_manager.__aenter__.return_value = session
                    ctx_manager.__aexit__.return_value = None
                    mock_get_session.return_value = ctx_manager
                    
                    yield session


@pytest.mark.asyncio
async def test_conversation_id_int_saves_correctly(in_memory_session):
    """Test that integer conversation_id is handled correctly."""
    # Integer conversation_id (common from Chatwoot webhooks)
    conversation_id = 888
    user_id_str = str(uuid.uuid4())
    
    # Create conversation history
    conv_history_id = await get_or_create_conversation_history(
        conversation_id=conversation_id,
        user_id=user_id_str,
    )
    
    assert conv_history_id is not None
    assert isinstance(conv_history_id, uuid.UUID)
    
    # Verify in database (should be stored as string "888")
    result = await in_memory_session.execute(
        select(TestConversationHistory).where(
            TestConversationHistory.conversation_id == "888"
        )
    )
    conv_history = result.scalar_one_or_none()
    
    assert conv_history is not None
    assert conv_history.conversation_id == "888"
    assert conv_history.user_id == uuid.UUID(user_id_str)
    assert conv_history.message_count == 0


@pytest.mark.asyncio
async def test_conversation_id_string_saves_correctly(in_memory_session):
    """Test that string conversation_id is handled correctly."""
    # String conversation_id (already converted)
    conversation_id = "777"
    
    # Create conversation history
    conv_history_id = await get_or_create_conversation_history(
        conversation_id=conversation_id,
        user_id=None,  # No user_id
    )
    
    assert conv_history_id is not None
    
    # Verify in database
    result = await in_memory_session.execute(
        select(TestConversationHistory).where(
            TestConversationHistory.conversation_id == "777"
        )
    )
    conv_history = result.scalar_one_or_none()
    
    assert conv_history is not None
    assert conv_history.conversation_id == "777"
    assert conv_history.user_id is None


@pytest.mark.asyncio
async def test_conversation_id_string_long_saves_correctly(in_memory_session):
    """Test that long string conversation_id (non-numeric) saves correctly."""
    # Long alphanumeric conversation_id
    conversation_id = "abc123xyz789"
    
    # Create conversation history
    conv_history_id = await get_or_create_conversation_history(
        conversation_id=conversation_id,
        user_id=None,
    )
    
    assert conv_history_id is not None
    
    # Verify in database
    result = await in_memory_session.execute(
        select(TestConversationHistory).where(
            TestConversationHistory.conversation_id == "abc123xyz789"
        )
    )
    conv_history = result.scalar_one_or_none()
    
    assert conv_history is not None
    assert conv_history.conversation_id == "abc123xyz789"


@pytest.mark.asyncio
async def test_messages_save_to_both_tables(in_memory_session):
    """Test that messages save to both ConversationHistory and ConversationMessage."""
    conversation_id = 999
    
    # Save user message
    await save_user_message(
        conversation_id=conversation_id,
        content="Hola, necesito información sobre escapes",
        chatwoot_message_id=12345,
        has_images=False,
        image_count=0,
        user_id=None,
    )
    
    # Verify ConversationHistory created
    result = await in_memory_session.execute(
        select(TestConversationHistory).where(
            TestConversationHistory.conversation_id == "999"
        )
    )
    conv_history = result.scalar_one_or_none()
    assert conv_history is not None
    
    # Verify ConversationMessage created
    result = await in_memory_session.execute(
        select(TestConversationMessage).where(
            TestConversationMessage.conversation_history_id == conv_history.id
        )
    )
    messages = result.scalars().all()
    
    assert len(messages) == 1
    message = messages[0]
    assert message.role == "user"
    assert message.content == "Hola, necesito información sobre escapes"
    assert message.chatwoot_message_id == 12345
    assert message.has_images is False
    assert message.image_count == 0


@pytest.mark.asyncio
async def test_assistant_message_saves_correctly(in_memory_session):
    """Test that assistant message saves correctly."""
    conversation_id = 1000
    
    # Save assistant message
    await save_assistant_message(
        conversation_id=conversation_id,
        content="El presupuesto para escape es de 60€ + IVA.",
        has_images=False,
        image_count=0,
    )
    
    # Verify ConversationHistory created
    result = await in_memory_session.execute(
        select(TestConversationHistory).where(
            TestConversationHistory.conversation_id == "1000"
        )
    )
    conv_history = result.scalar_one_or_none()
    assert conv_history is not None
    
    # Verify ConversationMessage created
    result = await in_memory_session.execute(
        select(TestConversationMessage).where(
            TestConversationMessage.conversation_history_id == conv_history.id
        ).where(
            TestConversationMessage.role == "assistant"
        )
    )
    message = result.scalar_one_or_none()
    
    assert message is not None
    assert message.content == "El presupuesto para escape es de 60€ + IVA."
    assert message.has_images is False
    assert message.image_count == 0
    assert message.chatwoot_message_id is None


@pytest.mark.asyncio
async def test_image_count_updates_correctly(in_memory_session):
    """Test that image_count updates correctly on existing messages."""
    conversation_id = 1001
    
    # Save user message without images initially
    await save_user_message(
        conversation_id=conversation_id,
        content="Te envío las fotos",
        has_images=False,
        image_count=0,
    )
    
    # Update image count (simulating async upload after message)
    await update_message_image_count(
        conversation_id=conversation_id,
        role="user",
        image_count=3,
    )
    
    # Verify image count updated
    result = await in_memory_session.execute(
        select(TestConversationHistory).where(
            TestConversationHistory.conversation_id == "1001"
        )
    )
    conv_history = result.scalar_one_or_none()
    assert conv_history is not None
    
    result = await in_memory_session.execute(
        select(TestConversationMessage).where(
            TestConversationMessage.conversation_history_id == conv_history.id
        ).where(
            TestConversationMessage.role == "user"
        ).order_by(TestConversationMessage.created_at.desc())
    )
    message = result.scalar_one_or_none()
    
    assert message is not None
    assert message.has_images is True
    assert message.image_count == 3


@pytest.mark.asyncio
async def test_multiple_messages_in_conversation(in_memory_session):
    """Test multiple messages in the same conversation."""
    conversation_id = 1002
    
    # User message 1
    await save_user_message(
        conversation_id=conversation_id,
        content="Quiero homologar un escape",
        has_images=False,
        image_count=0,
    )
    
    # Assistant message 1
    await save_assistant_message(
        conversation_id=conversation_id,
        content="¿Es para moto o coche?",
        has_images=False,
        image_count=0,
    )
    
    # User message 2
    await save_user_message(
        conversation_id=conversation_id,
        content="Para moto",
        has_images=False,
        image_count=0,
    )
    
    # Assistant message 2 with images
    await save_assistant_message(
        conversation_id=conversation_id,
        content="El presupuesto es 60€. Te envío ejemplos:",
        has_images=True,
        image_count=2,
    )
    
    # Verify ConversationHistory
    result = await in_memory_session.execute(
        select(TestConversationHistory).where(
            TestConversationHistory.conversation_id == "1002"
        )
    )
    conv_history = result.scalar_one_or_none()
    assert conv_history is not None
    
    # Verify all 4 messages exist
    result = await in_memory_session.execute(
        select(TestConversationMessage).where(
            TestConversationMessage.conversation_history_id == conv_history.id
        ).order_by(TestConversationMessage.created_at)
    )
    messages = result.scalars().all()
    
    assert len(messages) == 4
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"
    assert messages[2].role == "user"
    assert messages[3].role == "assistant"
    assert messages[3].has_images is True
    assert messages[3].image_count == 2


@pytest.mark.asyncio
async def test_idempotent_conversation_history_creation(in_memory_session):
    """Test that calling get_or_create multiple times returns same ID."""
    conversation_id = 1003
    user_id_str = str(uuid.uuid4())
    
    # First call - creates
    conv_id_1 = await get_or_create_conversation_history(
        conversation_id=conversation_id,
        user_id=user_id_str,
    )
    
    # Second call - retrieves existing
    conv_id_2 = await get_or_create_conversation_history(
        conversation_id=conversation_id,
        user_id=user_id_str,
    )
    
    # Third call - retrieves existing
    conv_id_3 = await get_or_create_conversation_history(
        conversation_id=conversation_id,
        user_id=user_id_str,
    )
    
    # All should be the same UUID
    assert conv_id_1 == conv_id_2 == conv_id_3
    
    # Verify only one record in database
    result = await in_memory_session.execute(
        select(TestConversationHistory).where(
            TestConversationHistory.conversation_id == "1003"
        )
    )
    records = result.scalars().all()
    assert len(records) == 1


@pytest.mark.asyncio
async def test_update_image_count_nonexistent_conversation(in_memory_session):
    """Test that updating image count on nonexistent conversation doesn't crash."""
    # Should log warning but not raise exception (fire-and-forget)
    await update_message_image_count(
        conversation_id="nonexistent_9999",
        role="user",
        image_count=5,
    )
    
    # Verify no records created
    result = await in_memory_session.execute(
        select(TestConversationHistory).where(
            TestConversationHistory.conversation_id == "nonexistent_9999"
        )
    )
    conv_history = result.scalar_one_or_none()
    assert conv_history is None


@pytest.mark.asyncio
async def test_conversation_id_edge_cases(in_memory_session):
    """Test edge cases for conversation_id types."""
    # Test case 1: Very large integer
    large_int = 999999999
    conv_id_1 = await get_or_create_conversation_history(
        conversation_id=large_int,
        user_id=None,
    )
    assert conv_id_1 is not None
    
    # Test case 2: String with special characters (should be valid)
    special_string = "conv-abc-123"
    conv_id_2 = await get_or_create_conversation_history(
        conversation_id=special_string,
        user_id=None,
    )
    assert conv_id_2 is not None
    
    # Test case 3: Zero as integer
    zero_int = 0
    conv_id_3 = await get_or_create_conversation_history(
        conversation_id=zero_int,
        user_id=None,
    )
    assert conv_id_3 is not None
    
    # Verify all stored as strings
    result = await in_memory_session.execute(
        select(TestConversationHistory).where(
            TestConversationHistory.conversation_id.in_(["999999999", "conv-abc-123", "0"])
        )
    )
    records = result.scalars().all()
    assert len(records) == 3
