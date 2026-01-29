"""
MSI Automotive - Message Persistence Service.

Service for persisting conversation messages to PostgreSQL.
Stores individual user and assistant messages with optional metadata.
"""

import logging
import uuid
from datetime import datetime, UTC

from sqlalchemy import select

from database.connection import get_async_session
from database.models import ConversationHistory, ConversationMessage

logger = logging.getLogger(__name__)


async def get_or_create_conversation_history(
    conversation_id: str,
    user_id: str | None = None,
) -> uuid.UUID:
    """
    Get existing ConversationHistory ID or create a new one.
    
    Args:
        conversation_id: Chatwoot conversation ID (string)
        user_id: User UUID string (optional)
    
    Returns:
        UUID of the ConversationHistory record
    """
    async with get_async_session() as session:
        # Try to find existing
        result = await session.execute(
            select(ConversationHistory).where(
                ConversationHistory.conversation_id == conversation_id
            )
        )
        conv_history = result.scalar_one_or_none()
        
        if conv_history:
            return conv_history.id
        
        # Create new
        conv_history = ConversationHistory(
            conversation_id=conversation_id,
            user_id=uuid.UUID(user_id) if user_id else None,
            started_at=datetime.now(UTC),
            message_count=0,
        )
        session.add(conv_history)
        await session.commit()
        await session.refresh(conv_history)
        
        logger.info(
            f"Created new ConversationHistory | conversation_id={conversation_id} | id={conv_history.id}",
            extra={"conversation_id": conversation_id},
        )
        
        return conv_history.id


async def save_user_message(
    conversation_id: str,
    content: str,
    chatwoot_message_id: int | None = None,
    has_images: bool = False,
    image_count: int = 0,
    user_id: str | None = None,
) -> None:
    """
    Save incoming user message to PostgreSQL.
    
    Args:
        conversation_id: Chatwoot conversation ID
        content: Message text content
        chatwoot_message_id: Chatwoot message ID for correlation
        has_images: Whether user sent images
        image_count: Number of images attached
        user_id: User UUID string (for creating conversation if needed)
    """
    try:
        # Get or create ConversationHistory
        conv_history_id = await get_or_create_conversation_history(
            conversation_id, user_id
        )
        
        async with get_async_session() as session:
            message = ConversationMessage(
                conversation_history_id=conv_history_id,
                role="user",
                content=content,
                chatwoot_message_id=chatwoot_message_id,
                has_images=has_images,
                image_count=image_count,
                created_at=datetime.now(UTC),
            )
            session.add(message)
            await session.commit()
            
            logger.debug(
                f"User message saved | conversation_id={conversation_id} | "
                f"message_id={message.id} | length={len(content)} | "
                f"images={image_count}",
                extra={
                    "conversation_id": conversation_id,
                    "message_id": str(message.id),
                    "has_images": has_images,
                },
            )
    
    except Exception as e:
        logger.error(
            f"Failed to save user message | conversation_id={conversation_id}: {e}",
            extra={"conversation_id": conversation_id},
            exc_info=True,
        )
        # Don't raise - this is fire-and-forget to avoid blocking main flow


async def save_assistant_message(
    conversation_id: str,
    content: str,
    has_images: bool = False,
    image_count: int = 0,
) -> None:
    """
    Save agent response to PostgreSQL.
    
    Args:
        conversation_id: Chatwoot conversation ID
        content: Message text content
        has_images: Whether agent sent example images
        image_count: Number of images sent
    """
    try:
        # Get or create ConversationHistory
        conv_history_id = await get_or_create_conversation_history(conversation_id)
        
        async with get_async_session() as session:
            message = ConversationMessage(
                conversation_history_id=conv_history_id,
                role="assistant",
                content=content,
                has_images=has_images,
                image_count=image_count,
                created_at=datetime.now(UTC),
            )
            session.add(message)
            await session.commit()
            
            logger.debug(
                f"Assistant message saved | conversation_id={conversation_id} | "
                f"message_id={message.id} | length={len(content)} | "
                f"images={image_count}",
                extra={
                    "conversation_id": conversation_id,
                    "message_id": str(message.id),
                    "has_images": has_images,
                },
            )
    
    except Exception as e:
        logger.error(
            f"Failed to save assistant message | conversation_id={conversation_id}: {e}",
            extra={"conversation_id": conversation_id},
            exc_info=True,
        )
        # Don't raise - this is fire-and-forget to avoid blocking main flow


async def update_message_image_count(
    conversation_id: str,
    role: str,
    image_count: int,
) -> None:
    """
    Update image count on the most recent message of a specific role.
    
    Used when images are uploaded after the text message is saved.
    
    Args:
        conversation_id: Chatwoot conversation ID
        role: "user" or "assistant"
        image_count: Number of images to add
    """
    try:
        async with get_async_session() as session:
            # Find conversation history
            conv_result = await session.execute(
                select(ConversationHistory).where(
                    ConversationHistory.conversation_id == conversation_id
                )
            )
            conv_history = conv_result.scalar_one_or_none()
            
            if not conv_history:
                logger.warning(
                    f"Cannot update image count - conversation not found | "
                    f"conversation_id={conversation_id}"
                )
                return
            
            # Find most recent message with this role
            msg_result = await session.execute(
                select(ConversationMessage)
                .where(ConversationMessage.conversation_history_id == conv_history.id)
                .where(ConversationMessage.role == role)
                .order_by(ConversationMessage.created_at.desc())
                .limit(1)
            )
            message = msg_result.scalar_one_or_none()
            
            if message:
                message.has_images = True
                message.image_count += image_count
                await session.commit()
                
                logger.debug(
                    f"Updated message image count | conversation_id={conversation_id} | "
                    f"role={role} | count={message.image_count}",
                    extra={"conversation_id": conversation_id},
                )
    
    except Exception as e:
        logger.error(
            f"Failed to update message image count | conversation_id={conversation_id}: {e}",
            extra={"conversation_id": conversation_id},
            exc_info=True,
        )
