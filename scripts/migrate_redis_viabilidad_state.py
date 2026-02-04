"""
Redis checkpoint migration: VIABILIDAD_MODE → PRESUPUESTO_MODE

Scans Redis checkpoints and updates in-place.

Usage:
    python scripts/migrate_redis_viabilidad_state.py [--dry-run]

Options:
    --dry-run    Show what would be migrated without making changes
"""

import argparse
import asyncio
import json
from datetime import datetime, UTC
from typing import Any

import structlog
from shared.redis_client import get_redis_client
from shared.config import get_settings

logger = structlog.get_logger(__name__)


async def migrate_redis_checkpoints(dry_run: bool = False) -> dict[str, Any]:
    """
    Migrate Redis checkpoints from VIABILIDAD to PRESUPUESTO.
    
    Scans all checkpoint:* keys in Redis and updates those with:
    - current_mode = "VIABILIDAD_MODE"
    
    Changes:
    1. current_mode: VIABILIDAD_MODE → PRESUPUESTO_MODE
    2. previous_mode: Set to START (or keep existing)
    3. mode_history: Append "VIABILIDAD_MODE" for tracking
    4. mode_context:
       - Remove estimacion_precio (obsolete concept)
       - Rename precio_exacto → precio_calculado (if exists)
       - Keep: categoria_slug, elemento_confirmado, vehiculo, element_codes
    
    Args:
        dry_run: If True, only show what would be migrated
    
    Returns:
        Dict with migration stats
    """
    logger.info(
        "migration_start",
        script="migrate_redis_viabilidad_state",
        dry_run=dry_run,
    )
    
    settings = get_settings()
    redis = get_redis_client()
    
    stats = {
        "scanned": 0,
        "migrated": 0,
        "skipped": 0,
        "errors": 0,
        "started_at": datetime.now(UTC).isoformat(),
        "dry_run": dry_run,
    }
    
    # Scan for checkpoint keys
    cursor = 0
    batch = 0
    
    while True:
        batch += 1
        cursor, keys = await redis.scan(cursor, match="checkpoint:*", count=100)
        
        logger.info(
            "scan_batch",
            batch=batch,
            keys_found=len(keys),
            cursor=cursor,
        )
        
        for key in keys:
            stats["scanned"] += 1
            
            try:
                # Get checkpoint data
                data = await redis.get(key)
                if not data:
                    stats["skipped"] += 1
                    logger.debug("checkpoint_empty", key=key.decode() if isinstance(key, bytes) else key)
                    continue
                
                # Decode if bytes
                if isinstance(data, bytes):
                    data = data.decode('utf-8')
                
                state = json.loads(data)
                
                # Check if VIABILIDAD_MODE
                current_mode = state.get("current_mode")
                
                if current_mode != "VIABILIDAD_MODE":
                    stats["skipped"] += 1
                    logger.debug(
                        "checkpoint_skipped",
                        key=key.decode() if isinstance(key, bytes) else key,
                        current_mode=current_mode,
                    )
                    continue
                
                # Found a VIABILIDAD checkpoint
                conversation_id = state.get("conversation_id", "unknown")
                
                logger.info(
                    "checkpoint_found_viabilidad",
                    key=key.decode() if isinstance(key, bytes) else key,
                    conversation_id=conversation_id,
                    mode_context=state.get("mode_context", {}),
                )
                
                if dry_run:
                    stats["migrated"] += 1
                    logger.info(
                        "checkpoint_would_migrate",
                        key=key.decode() if isinstance(key, bytes) else key,
                        conversation_id=conversation_id,
                    )
                    continue
                
                # Perform migration
                # 1. Update current_mode
                state["current_mode"] = "PRESUPUESTO_MODE"
                
                # 2. Update previous_mode (keep existing or set to START)
                if not state.get("previous_mode"):
                    state["previous_mode"] = "START"
                
                # 3. Update mode_history
                history = state.get("mode_history", [])
                history.append("VIABILIDAD_MODE")
                state["mode_history"] = history
                
                # 4. Update mode_context
                context = state.get("mode_context", {})
                
                # Remove estimacion_precio (obsolete)
                if "estimacion_precio" in context:
                    removed_estimacion = context.pop("estimacion_precio")
                    logger.info(
                        "context_removed_estimacion",
                        key=key.decode() if isinstance(key, bytes) else key,
                        estimacion_precio=removed_estimacion,
                    )
                
                # Rename precio_exacto → precio_calculado
                if "precio_exacto" in context:
                    context["precio_calculado"] = context.pop("precio_exacto")
                    logger.info(
                        "context_renamed_precio",
                        key=key.decode() if isinstance(key, bytes) else key,
                        precio_calculado=context["precio_calculado"],
                    )
                
                state["mode_context"] = context
                state["updated_at"] = datetime.now(UTC).isoformat()
                state["migrated_from"] = "VIABILIDAD_MODE"
                state["migrated_at"] = datetime.now(UTC).isoformat()
                
                # Save back to Redis
                await redis.set(key, json.dumps(state))
                
                stats["migrated"] += 1
                
                logger.info(
                    "checkpoint_migrated",
                    key=key.decode() if isinstance(key, bytes) else key,
                    conversation_id=conversation_id,
                    new_mode="PRESUPUESTO_MODE",
                )
                
            except json.JSONDecodeError as e:
                stats["errors"] += 1
                logger.error(
                    "checkpoint_decode_error",
                    key=key.decode() if isinstance(key, bytes) else key,
                    error=str(e),
                )
            except Exception as e:
                stats["errors"] += 1
                logger.error(
                    "checkpoint_migration_error",
                    key=key.decode() if isinstance(key, bytes) else key,
                    error=str(e),
                    error_type=type(e).__name__,
                )
        
        if cursor == 0:
            break
    
    stats["completed_at"] = datetime.now(UTC).isoformat()
    
    logger.info("migration_complete", stats=stats)
    
    return stats


async def main(dry_run: bool = False) -> None:
    """
    Run Redis checkpoint migration.
    
    Args:
        dry_run: If True, only show what would be migrated
    """
    logger.info(
        "migration_start_main",
        script="Redis VIABILIDAD → PRESUPUESTO migration",
        dry_run=dry_run,
    )
    
    stats = await migrate_redis_checkpoints(dry_run=dry_run)
    
    # Print summary
    print("\n" + "=" * 80)
    if dry_run:
        print("✅ DRY RUN COMPLETE - No changes were made")
        print("=" * 80)
        print("\nRun without --dry-run to execute the migration")
    else:
        print("✅ MIGRATION COMPLETE")
        print("=" * 80)
    
    print(f"\nStatistics:")
    print(f"  - Checkpoints scanned:  {stats['scanned']}")
    print(f"  - Checkpoints migrated: {stats['migrated']}")
    print(f"  - Checkpoints skipped:  {stats['skipped']}")
    print(f"  - Errors:               {stats['errors']}")
    print(f"  - Started at:           {stats['started_at']}")
    print(f"  - Completed at:         {stats['completed_at']}")
    
    if stats['errors'] > 0:
        print(f"\n⚠️  WARNING: {stats['errors']} errors occurred during migration")
        print("   Check logs for details")
    
    if stats['migrated'] == 0 and not dry_run:
        print("\nℹ️  No VIABILIDAD_MODE checkpoints found to migrate")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate Redis VIABILIDAD_MODE checkpoints to PRESUPUESTO_MODE"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes",
    )
    
    args = parser.parse_args()
    
    asyncio.run(main(dry_run=args.dry_run))
