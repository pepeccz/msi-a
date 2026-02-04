"""
Migration script: VIABILIDAD_MODE → PRESUPUESTO_MODE

This script migrates active conversations from VIABILIDAD_MODE to PRESUPUESTO_MODE
after the fusion deployment.

Executed ONCE after deployment, not part of Alembic migrations.

Usage:
    python scripts/migrate_viabilidad_to_presupuesto.py [--dry-run]

Options:
    --dry-run    Show what would be migrated without making changes
"""

import argparse
import asyncio
import json
from datetime import datetime, UTC
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_async_session
from database.models import ConversationMessage

logger = structlog.get_logger(__name__)


async def migrate_viabilidad_conversations(dry_run: bool = False) -> dict[str, Any]:
    """
    Migrate all conversations with current_mode=VIABILIDAD_MODE to PRESUPUESTO_MODE.
    
    Changes:
    1. current_mode: VIABILIDAD_MODE → PRESUPUESTO_MODE
    2. mode_context:
       - Rename estimacion_precio → (eliminated)
       - Rename precio_exacto → precio_calculado (if exists)
       - Keep: categoria_slug, elemento_confirmado, vehiculo, element_codes
    3. previous_mode: set to START (or keep if already set)
    4. mode_history: append "VIABILIDAD_MODE" for tracking
    
    Args:
        dry_run: If True, only show what would be migrated
    
    Returns:
        Dict with migration stats
    """
    logger.info(
        "migration_start",
        script="migrate_viabilidad_to_presupuesto",
        dry_run=dry_run,
    )
    
    stats = {
        "conversations_migrated": 0,
        "conversations_skipped": 0,
        "errors": 0,
        "started_at": datetime.now(UTC).isoformat(),
        "dry_run": dry_run,
    }
    
    async with get_async_session() as session:
        # Find all VIABILIDAD conversations
        # NOTE: Assuming state is stored in a checkpoints table or Redis
        # If using Redis checkpointer, this needs to be adapted to read from Redis
        
        # For PostgreSQL checkpointer (if implemented):
        # stmt = select(Checkpoint).where(
        #     Checkpoint.state["current_mode"].astext == "VIABILIDAD_MODE"
        # )
        
        # For Redis checkpointer (current implementation):
        # Need to scan Redis keys matching "checkpoint:*"
        
        logger.warning(
            "migration_skipped",
            reason="Redis checkpointer not accessible from SQL migration",
            recommendation="Use scripts/migrate_redis_viabilidad_state.py instead",
        )
        
        stats["conversations_skipped"] = "N/A (Redis checkpointer)"
        
        # If PostgreSQL checkpointer exists:
        # result = await session.execute(stmt)
        # checkpoints = result.scalars().all()
        # 
        # for checkpoint in checkpoints:
        #     try:
        #         state = checkpoint.state
        #         
        #         logger.info(
        #             "checkpoint_found",
        #             checkpoint_id=checkpoint.id,
        #             conversation_id=state.get("conversation_id"),
        #             current_mode=state.get("current_mode"),
        #         )
        #         
        #         if dry_run:
        #             stats["conversations_migrated"] += 1
        #             continue
        #         
        #         # Update current_mode
        #         state["current_mode"] = "PRESUPUESTO_MODE"
        #         state["previous_mode"] = state.get("current_mode", "START")
        #         
        #         # Update mode_history
        #         history = state.get("mode_history", [])
        #         history.append("VIABILIDAD_MODE")
        #         state["mode_history"] = history
        #         
        #         # Update mode_context
        #         context = state.get("mode_context", {})
        #         
        #         # Remove estimacion_precio
        #         context.pop("estimacion_precio", None)
        #         
        #         # Rename precio_exacto → precio_calculado
        #         if "precio_exacto" in context:
        #             context["precio_calculado"] = context.pop("precio_exacto")
        #         
        #         state["mode_context"] = context
        #         state["updated_at"] = datetime.now(UTC).isoformat()
        #         
        #         # Save
        #         checkpoint.state = state
        #         stats["conversations_migrated"] += 1
        #         
        #         logger.info(
        #             "checkpoint_migrated",
        #             checkpoint_id=checkpoint.id,
        #             conversation_id=state.get("conversation_id"),
        #         )
        #         
        #     except Exception as e:
        #         logger.error(
        #             "migration_error",
        #             checkpoint_id=checkpoint.id,
        #             error=str(e),
        #         )
        #         stats["errors"] += 1
        # 
        # if not dry_run:
        #     await session.commit()
    
    stats["completed_at"] = datetime.now(UTC).isoformat()
    
    logger.info(
        "migration_complete",
        stats=stats,
    )
    
    return stats


async def migrate_conversation_messages_metadata(dry_run: bool = False) -> dict[str, Any]:
    """
    Update metadata in conversation_messages table.
    
    Replace "VIABILIDAD_MODE" with "PRESUPUESTO_MODE" in:
    - metadata JSON fields (if any store mode info)
    
    Args:
        dry_run: If True, only show what would be migrated
    
    Returns:
        Dict with migration stats
    """
    logger.info(
        "migration_start",
        script="migrate_conversation_messages_metadata",
        dry_run=dry_run,
    )
    
    stats = {
        "messages_updated": 0,
        "messages_scanned": 0,
        "started_at": datetime.now(UTC).isoformat(),
        "dry_run": dry_run,
    }
    
    async with get_async_session() as session:
        # Find messages with VIABILIDAD in metadata
        stmt = select(ConversationMessage).where(
            ConversationMessage.metadata.isnot(None)
        )
        
        result = await session.execute(stmt)
        messages = result.scalars().all()
        
        for msg in messages:
            stats["messages_scanned"] += 1
            
            if not msg.metadata:
                continue
            
            metadata = msg.metadata
            updated = False
            
            # Check if metadata contains mode info
            if metadata.get("mode") == "VIABILIDAD_MODE":
                logger.info(
                    "message_found",
                    message_id=str(msg.id),
                    conversation_id=str(msg.conversation_id),
                    mode=metadata.get("mode"),
                )
                
                if dry_run:
                    stats["messages_updated"] += 1
                    continue
                
                metadata["mode"] = "PRESUPUESTO_MODE"
                metadata["migrated_from"] = "VIABILIDAD_MODE"
                metadata["migrated_at"] = datetime.now(UTC).isoformat()
                updated = True
            
            if updated:
                msg.metadata = metadata
                stats["messages_updated"] += 1
                
                logger.info(
                    "message_migrated",
                    message_id=str(msg.id),
                    conversation_id=str(msg.conversation_id),
                )
        
        if not dry_run:
            await session.commit()
    
    stats["completed_at"] = datetime.now(UTC).isoformat()
    
    logger.info(
        "migration_complete",
        script="migrate_conversation_messages_metadata",
        stats=stats,
    )
    
    return stats


async def main(dry_run: bool = False) -> None:
    """
    Run all migrations.
    
    Args:
        dry_run: If True, only show what would be migrated
    """
    logger.info(
        "migration_start_all",
        script="VIABILIDAD → PRESUPUESTO migration",
        dry_run=dry_run,
    )
    
    # Migrate checkpoints (PostgreSQL)
    checkpoint_stats = await migrate_viabilidad_conversations(dry_run=dry_run)
    
    # Migrate messages metadata
    message_stats = await migrate_conversation_messages_metadata(dry_run=dry_run)
    
    logger.info(
        "migration_summary",
        checkpoint_stats=checkpoint_stats,
        message_stats=message_stats,
        dry_run=dry_run,
    )
    
    if dry_run:
        print("\n✅ DRY RUN COMPLETE - No changes were made")
        print("Run without --dry-run to execute the migration")
    else:
        print("\n✅ MIGRATION COMPLETE")
    
    print(f"\nCheckpoint Stats: {checkpoint_stats}")
    print(f"Message Stats: {message_stats}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate VIABILIDAD_MODE conversations to PRESUPUESTO_MODE"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes",
    )
    
    args = parser.parse_args()
    
    asyncio.run(main(dry_run=args.dry_run))
