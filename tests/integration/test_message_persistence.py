"""
Integration test for message persistence functionality.

Tests that messages are correctly saved to PostgreSQL when
processing conversations.
"""

import asyncio
import uuid
import pytest
from datetime import datetime, UTC

from api.services.message_persistence_service import (
    save_user_message,
    save_assistant_message,
    get_or_create_conversation_history,
)
from database.connection import get_async_session
from database.models import ConversationHistory, ConversationMessage


@pytest.mark.asyncio
async def test_save_user_message():
    """Test saving a user message."""
    conversation_id = f"test-conv-{uuid.uuid4()}"
    user_message = "Hola, quiero homologar un escape"
    
    # Save user message
    await save_user_message(
        conversation_id=conversation_id,
        content=user_message,
        has_images=False,
        image_count=0,
    )
    
    # Give it a moment to process
    await asyncio.sleep(0.5)
    
    # Verify it was saved
    async with get_async_session() as session:
        # Get conversation history
        from sqlalchemy import select
        result = await session.execute(
            select(ConversationHistory).where(
                ConversationHistory.conversation_id == conversation_id
            )
        )
        conv_history = result.scalar_one()
        
        # Get messages
        msg_result = await session.execute(
            select(ConversationMessage).where(
                ConversationMessage.conversation_history_id == conv_history.id
            )
        )
        messages = msg_result.scalars().all()
        
        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].content == user_message
        assert messages[0].has_images is False
        assert messages[0].image_count == 0


@pytest.mark.asyncio
async def test_save_assistant_message():
    """Test saving an assistant message."""
    conversation_id = f"test-conv-{uuid.uuid4()}"
    
    # Save assistant message
    assistant_message = "El presupuesto es de 290€ +IVA."
    await save_assistant_message(
        conversation_id=conversation_id,
        content=assistant_message,
        has_images=True,
        image_count=3,
    )
    
    # Give it a moment to process
    await asyncio.sleep(0.5)
    
    # Verify it was saved
    async with get_async_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(ConversationHistory).where(
                ConversationHistory.conversation_id == conversation_id
            )
        )
        conv_history = result.scalar_one()
        
        msg_result = await session.execute(
            select(ConversationMessage).where(
                ConversationMessage.conversation_history_id == conv_history.id
            )
        )
        messages = msg_result.scalars().all()
        
        assert len(messages) == 1
        assert messages[0].role == "assistant"
        assert messages[0].content == assistant_message
        assert messages[0].has_images is True
        assert messages[0].image_count == 3


@pytest.mark.asyncio
async def test_conversation_with_multiple_messages():
    """Test a full conversation with multiple messages."""
    conversation_id = f"test-conv-{uuid.uuid4()}"
    
    # Simulate a conversation
    messages_data = [
        ("user", "Hola"),
        ("assistant", "Hola! ¿En qué puedo ayudarte?"),
        ("user", "Quiero homologar un escape"),
        ("assistant", "Perfecto, ¿qué tipo de vehículo tienes?"),
        ("user", "Una moto"),
    ]
    
    for role, content in messages_data:
        if role == "user":
            await save_user_message(conversation_id, content)
        else:
            await save_assistant_message(conversation_id, content)
        await asyncio.sleep(0.1)  # Small delay between messages
    
    # Give it a moment to process
    await asyncio.sleep(0.5)
    
    # Verify all messages were saved in order
    async with get_async_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(ConversationHistory).where(
                ConversationHistory.conversation_id == conversation_id
            )
        )
        conv_history = result.scalar_one()
        
        msg_result = await session.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_history_id == conv_history.id)
            .order_by(ConversationMessage.created_at)
        )
        messages = msg_result.scalars().all()
        
        assert len(messages) == len(messages_data)
        
        for i, (expected_role, expected_content) in enumerate(messages_data):
            assert messages[i].role == expected_role
            assert messages[i].content == expected_content


@pytest.mark.asyncio
async def test_cascade_delete():
    """Test that messages are deleted when conversation is deleted."""
    conversation_id = f"test-conv-{uuid.uuid4()}"
    
    # Create conversation with messages
    await save_user_message(conversation_id, "Test message 1")
    await save_assistant_message(conversation_id, "Test response 1")
    await asyncio.sleep(0.5)
    
    async with get_async_session() as session:
        from sqlalchemy import select
        
        # Get conversation
        result = await session.execute(
            select(ConversationHistory).where(
                ConversationHistory.conversation_id == conversation_id
            )
        )
        conv_history = result.scalar_one()
        conv_history_id = conv_history.id
        
        # Verify messages exist
        msg_result = await session.execute(
            select(ConversationMessage).where(
                ConversationMessage.conversation_history_id == conv_history_id
            )
        )
        messages_before = msg_result.scalars().all()
        assert len(messages_before) == 2
        
        # Delete conversation
        await session.delete(conv_history)
        await session.commit()
    
    # Verify messages were cascaded deleted
    async with get_async_session() as session:
        from sqlalchemy import select
        msg_result = await session.execute(
            select(ConversationMessage).where(
                ConversationMessage.conversation_history_id == conv_history_id
            )
        )
        messages_after = msg_result.scalars().all()
        assert len(messages_after) == 0


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
