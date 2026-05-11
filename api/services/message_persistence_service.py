"""
MSI Automotive - Message Persistence Service.

Service for persisting conversation messages to PostgreSQL.
Stores individual user and assistant messages with optional metadata.
"""

__all__ = [
    "get_or_create_conversation_history",
    "save_user_message",
    "save_assistant_message",
    "update_message_image_count",
]

import logging
import uuid
from datetime import datetime, UTC

from sqlalchemy import select

from database.connection import get_async_session
from database.models import ConversationHistory, ConversationMessage

logger = logging.getLogger(__name__)


async def get_or_create_conversation_history(
    conversation_id: str | int,
    user_id: str | None = None,
) -> uuid.UUID:
    """
    Get existing ConversationHistory ID or create a new one.
    
    Args:
        conversation_id: Chatwoot conversation ID (string or int, will be converted to string)
        user_id: User UUID string (optional)
    
    Returns:
        UUID of the ConversationHistory record
    """
    # Ensure conversation_id is always string (Chatwoot can send int or string)
    conversation_id_str = str(conversation_id)
    
    async with get_async_session() as session:
        # Try to find existing
        result = await session.execute(
            select(ConversationHistory).where(
                ConversationHistory.conversation_id == conversation_id_str
            )
        )
        conv_history = result.scalar_one_or_none()
        
        if conv_history:
            return conv_history.id
        
        # Create new
        conv_history = ConversationHistory(
            conversation_id=conversation_id_str,
            user_id=uuid.UUID(user_id) if user_id else None,
            started_at=datetime.now(UTC),
            message_count=0,
        )
        session.add(conv_history)
        await session.commit()
        await session.refresh(conv_history)
        
        logger.info(
            f"Created new ConversationHistory | conversation_id={conversation_id_str} | id={conv_history.id}",
            extra={"conversation_id": conversation_id_str},
        )
        
        return conv_history.id


async def save_user_message(
    conversation_id: str | int,
    content: str,
    chatwoot_message_id: int | None = None,
    has_images: bool = False,
    image_count: int = 0,
    user_id: str | None = None,
) -> None:
    """
    Save incoming user message to PostgreSQL.

    Idempotent when chatwoot_message_id is provided: if a record with that ID
    already exists (persisted by the webhook handler), the INSERT is skipped.
    When chatwoot_message_id is None there is no dedup key, so the INSERT always
    runs (defensive fallback for callers that lack the Chatwoot ID).

    Args:
        conversation_id: Chatwoot conversation ID (string or int, will be converted to string)
        content: Message text content
        chatwoot_message_id: Chatwoot message ID for deduplication
        has_images: Whether user sent images
        image_count: Number of images attached
        user_id: User UUID string (for creating conversation if needed)
    """
    try:
        conv_history_id = await get_or_create_conversation_history(
            conversation_id, user_id
        )

        async with get_async_session() as session:
            if chatwoot_message_id is not None:
                existing = await session.execute(
                    select(ConversationMessage).where(
                        ConversationMessage.chatwoot_message_id == chatwoot_message_id
                    )
                )
                if existing.scalar_one_or_none() is not None:
                    logger.debug(
                        "save_user_message skipped — already persisted by webhook",
                        extra={
                            "conversation_id": str(conversation_id),
                            "chatwoot_message_id": chatwoot_message_id,
                        },
                    )
                    return

            message = ConversationMessage(
                conversation_history_id=conv_history_id,
                role="user",
                author_type="user",
                author_user_id=None,
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
    conversation_id: str | int,
    content: str,
    has_images: bool = False,
    image_count: int = 0,
) -> None:
    """
    Save agent response to PostgreSQL.
    
    Args:
        conversation_id: Chatwoot conversation ID (string or int, will be converted to string)
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
                author_type="bot",
                author_user_id=None,
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
    conversation_id: str | int,
    role: str,
    image_count: int,
) -> None:
    """
    Update image count on the most recent message of a specific role.
    
    Used when images are uploaded after the text message is saved.
    
    Args:
        conversation_id: Chatwoot conversation ID (string or int, will be converted to string)
        role: "user" or "assistant"
        image_count: Number of images to add
    """
    # Ensure conversation_id is always string
    conversation_id_str = str(conversation_id)
    
    try:
        async with get_async_session() as session:
            # Find conversation history
            conv_result = await session.execute(
                select(ConversationHistory).where(
                    ConversationHistory.conversation_id == conversation_id_str
                )
            )
            conv_history = conv_result.scalar_one_or_none()
            
            if not conv_history:
                logger.warning(
                    f"Cannot update image count - conversation not found | "
                    f"conversation_id={conversation_id_str}"
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
                    f"Updated message image count | conversation_id={conversation_id_str} | "
                    f"role={role} | count={message.image_count}",
                    extra={"conversation_id": conversation_id_str},
                )
    
    except Exception as e:
        logger.error(
            f"Failed to update message image count | conversation_id={conversation_id_str}: {e}",
            extra={"conversation_id": conversation_id_str},
            exc_info=True,
        )
