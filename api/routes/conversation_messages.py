"""
MSI Automotive - Conversation Messages API Routes.

Routes for retrieving individual messages within conversations.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from api.routes.admin import get_current_user
from database.connection import get_async_session
from database.models import AdminUser, ConversationHistory, ConversationMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/conversations")


@router.get("/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: uuid.UUID,
    current_user: AdminUser = Depends(get_current_user),
    limit: int = 100,
    offset: int = 0,
) -> JSONResponse:
    """
    Get all messages for a conversation.
    
    Returns messages ordered by created_at (oldest first) with pagination.
    
    Args:
        conversation_id: Internal UUID of ConversationHistory
        current_user: Authenticated admin user
        limit: Maximum number of messages to return (default 100)
        offset: Offset for pagination (default 0)
    
    Returns:
        JSONResponse with:
        - messages: List of message objects
        - total: Total message count
        - has_more: Whether there are more messages
    """
    async with get_async_session() as session:
        # Verify conversation exists
        conv = await session.get(ConversationHistory, conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Count total messages
        count_query = select(func.count(ConversationMessage.id)).where(
            ConversationMessage.conversation_history_id == conversation_id
        )
        total = await session.scalar(count_query) or 0
        
        # Get messages with pagination
        query = (
            select(ConversationMessage)
            .where(ConversationMessage.conversation_history_id == conversation_id)
            .order_by(ConversationMessage.created_at.asc())  # Oldest first (chat order)
            .offset(offset)
            .limit(limit)
        )
        
        result = await session.execute(query)
        messages = result.scalars().all()
        
        messages_data = [
            {
                "id": str(msg.id),
                "conversation_history_id": str(msg.conversation_history_id),
                "role": msg.role,
                "content": msg.content,
                "chatwoot_message_id": msg.chatwoot_message_id,
                "has_images": msg.has_images,
                "image_count": msg.image_count,
                "created_at": msg.created_at.isoformat(),
            }
            for msg in messages
        ]
        
        return JSONResponse(
            content={
                "messages": messages_data,
                "total": total,
                "has_more": offset + len(messages) < total,
                "conversation_id": conv.conversation_id,  # Chatwoot ID for reference
            }
        )


@router.get("/{conversation_id}/messages/stats")
async def get_conversation_message_stats(
    conversation_id: uuid.UUID,
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Get message statistics for a conversation.
    
    Returns:
        - total_messages: Total message count
        - user_messages: Count of user messages
        - assistant_messages: Count of assistant messages
        - messages_with_images: Count of messages with images
        - first_message_at: Timestamp of first message
        - last_message_at: Timestamp of last message
    """
    async with get_async_session() as session:
        # Verify conversation exists
        conv = await session.get(ConversationHistory, conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Get all messages for stats
        query = select(ConversationMessage).where(
            ConversationMessage.conversation_history_id == conversation_id
        )
        result = await session.execute(query)
        messages = result.scalars().all()
        
        if not messages:
            return JSONResponse(
                content={
                    "total_messages": 0,
                    "user_messages": 0,
                    "assistant_messages": 0,
                    "messages_with_images": 0,
                    "first_message_at": None,
                    "last_message_at": None,
                }
            )
        
        user_count = sum(1 for m in messages if m.role == "user")
        assistant_count = sum(1 for m in messages if m.role == "assistant")
        with_images = sum(1 for m in messages if m.has_images)
        
        return JSONResponse(
            content={
                "total_messages": len(messages),
                "user_messages": user_count,
                "assistant_messages": assistant_count,
                "messages_with_images": with_images,
                "first_message_at": messages[0].created_at.isoformat(),
                "last_message_at": messages[-1].created_at.isoformat(),
            }
        )
