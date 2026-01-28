#!/usr/bin/env python3
"""
Check for duplicate conversation_id in conversation_history table.

This script should be run BEFORE applying the migration that adds
a unique constraint to conversation_history.conversation_id.

Usage:
    python -m scripts.check_conversation_duplicates

If duplicates are found, the script will:
1. List all duplicate conversation_ids with their counts
2. Show details of the duplicate records
3. Optionally clean up duplicates (keeping the most recent)

Exit codes:
    0: No duplicates found (safe to add constraint)
    1: Duplicates found (need cleanup before constraint)
    2: Error occurred
"""

import asyncio
import sys
from datetime import datetime

from sqlalchemy import text

from database.connection import get_async_session


async def check_duplicates() -> tuple[bool, list[dict]]:
    """
    Check for duplicate conversation_id values.
    
    Returns:
        Tuple of (has_duplicates, list of duplicate info dicts)
    """
    async with get_async_session() as session:
        # Find duplicates
        result = await session.execute(text("""
            SELECT 
                conversation_id, 
                COUNT(*) as count,
                MIN(started_at) as first_started,
                MAX(started_at) as last_started
            FROM conversation_history
            GROUP BY conversation_id
            HAVING COUNT(*) > 1
            ORDER BY count DESC
        """))
        
        duplicates = []
        for row in result.fetchall():
            duplicates.append({
                "conversation_id": row[0],
                "count": row[1],
                "first_started": row[2],
                "last_started": row[3],
            })
        
        return len(duplicates) > 0, duplicates


async def get_duplicate_details(conversation_id: str) -> list[dict]:
    """Get details of all records for a duplicate conversation_id."""
    async with get_async_session() as session:
        result = await session.execute(text("""
            SELECT 
                id,
                conversation_id,
                user_id,
                started_at,
                message_count,
                created_at
            FROM conversation_history
            WHERE conversation_id = :conv_id
            ORDER BY started_at DESC
        """), {"conv_id": conversation_id})
        
        records = []
        for row in result.fetchall():
            records.append({
                "id": str(row[0]),
                "conversation_id": row[1],
                "user_id": str(row[2]) if row[2] else None,
                "started_at": row[3],
                "message_count": row[4],
                "created_at": row[5],
            })
        
        return records


async def cleanup_duplicates(dry_run: bool = True) -> int:
    """
    Clean up duplicate conversation_history records.
    
    Keeps the record with the highest message_count (or most recent if tied).
    
    Args:
        dry_run: If True, only show what would be deleted without actually deleting.
        
    Returns:
        Number of records deleted (or would be deleted in dry_run mode)
    """
    async with get_async_session() as session:
        # This query deletes duplicates, keeping the one with highest message_count
        # (or most recent started_at if tied)
        delete_query = text("""
            DELETE FROM conversation_history ch1
            USING conversation_history ch2
            WHERE ch1.conversation_id = ch2.conversation_id
              AND ch1.id != ch2.id
              AND (
                  ch1.message_count < ch2.message_count
                  OR (ch1.message_count = ch2.message_count AND ch1.started_at < ch2.started_at)
                  OR (ch1.message_count = ch2.message_count AND ch1.started_at = ch2.started_at AND ch1.id < ch2.id)
              )
        """)
        
        if dry_run:
            # Count what would be deleted
            count_query = text("""
                SELECT COUNT(*) FROM conversation_history ch1
                WHERE EXISTS (
                    SELECT 1 FROM conversation_history ch2
                    WHERE ch1.conversation_id = ch2.conversation_id
                      AND ch1.id != ch2.id
                      AND (
                          ch1.message_count < ch2.message_count
                          OR (ch1.message_count = ch2.message_count AND ch1.started_at < ch2.started_at)
                          OR (ch1.message_count = ch2.message_count AND ch1.started_at = ch2.started_at AND ch1.id < ch2.id)
                      )
                )
            """)
            result = await session.execute(count_query)
            return result.scalar() or 0
        else:
            result = await session.execute(delete_query)
            await session.commit()
            return result.rowcount


async def main():
    """Main entry point."""
    print("=" * 60)
    print("Conversation History Duplicate Checker")
    print("=" * 60)
    print()
    
    try:
        has_duplicates, duplicates = await check_duplicates()
        
        if not has_duplicates:
            print("✅ SUCCESS: No duplicate conversation_ids found!")
            print()
            print("It is safe to add the unique constraint:")
            print("  alembic upgrade head")
            print()
            return 0
        
        print(f"⚠️  WARNING: Found {len(duplicates)} duplicate conversation_ids!")
        print()
        
        total_extra_records = sum(d["count"] - 1 for d in duplicates)
        print(f"Total extra records to clean: {total_extra_records}")
        print()
        
        print("Duplicate details:")
        print("-" * 60)
        
        for dup in duplicates[:10]:  # Show first 10
            print(f"\nConversation ID: {dup['conversation_id']}")
            print(f"  Count: {dup['count']} records")
            print(f"  First: {dup['first_started']}")
            print(f"  Last:  {dup['last_started']}")
            
            # Get detailed records
            details = await get_duplicate_details(dup["conversation_id"])
            for i, record in enumerate(details):
                marker = "KEEP" if i == 0 else "DELETE"
                print(f"    [{marker}] id={record['id'][:8]}... "
                      f"msg_count={record['message_count']} "
                      f"started={record['started_at']}")
        
        if len(duplicates) > 10:
            print(f"\n... and {len(duplicates) - 10} more duplicates")
        
        print()
        print("-" * 60)
        
        # Show cleanup preview
        would_delete = await cleanup_duplicates(dry_run=True)
        print(f"\nCleanup would delete {would_delete} records.")
        print()
        print("To clean up duplicates, run:")
        print("  python -m scripts.check_conversation_duplicates --cleanup")
        print()
        
        # Check for --cleanup argument
        if len(sys.argv) > 1 and sys.argv[1] == "--cleanup":
            print("🔧 Running cleanup...")
            deleted = await cleanup_duplicates(dry_run=False)
            print(f"✅ Deleted {deleted} duplicate records.")
            print()
            
            # Verify
            has_duplicates, _ = await check_duplicates()
            if not has_duplicates:
                print("✅ All duplicates cleaned! Safe to add constraint.")
                return 0
            else:
                print("⚠️  Some duplicates remain. Please investigate.")
                return 1
        
        return 1
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
