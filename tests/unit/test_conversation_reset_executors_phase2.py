"""Phase 2 executor tests for conversation reset pipeline."""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from api.services.conversation_reset_coordinator import ResetExecutionContext
from api.services.conversation_reset_db_executor import ConversationResetDatabaseExecutor
from api.services.conversation_reset_files_executor import ConversationResetFilesExecutor
from api.services.conversation_reset_redis_executor import ConversationResetRedisExecutor
from database.models import (
    Case,
    ConversationHistory,
    LLMUsageMetric,
    ToolCallLog,
)


@pytest.mark.asyncio
async def test_db_executor_deletes_conversation_linked_rows(
    db_session,
    conversation_footprint,
    monkeypatch,
) -> None:
    @asynccontextmanager
    async def _session_override():
        yield db_session

    monkeypatch.setattr(
        "api.services.conversation_reset_db_executor.get_async_session",
        _session_override,
    )

    db_session.add(
        ToolCallLog(
            conversation_id=conversation_footprint.chatwoot_conversation_id,
            tool_name="dummy_tool",
        )
    )
    db_session.add(
        LLMUsageMetric(
            task_type="conversation",
            tier="cloud_standard",
            provider="openrouter",
            model="deepseek/deepseek-chat",
            latency_ms=50,
            success=True,
            conversation_id=conversation_footprint.chatwoot_conversation_id,
        )
    )
    await db_session.commit()

    context = ResetExecutionContext(
        conversation_uuid=conversation_footprint.conversation_uuid,
        conversation_id=conversation_footprint.chatwoot_conversation_id,
    )
    result = await ConversationResetDatabaseExecutor().execute(context)

    assert result.status == "success"
    assert result.details["conversation_history"] == 1
    assert result.details["cases"] >= 1
    assert result.details["case_images"] >= 1
    assert result.details["escalations"] >= 1
    assert result.details["rag_queries"] >= 1
    assert result.details["tool_call_logs"] >= 1
    assert result.details["llm_usage_metrics"] >= 1
    assert context.case_image_filenames

    remaining_conversation = await db_session.get(
        ConversationHistory, conversation_footprint.conversation_uuid
    )
    assert remaining_conversation is None

    case_count = (
        await db_session.execute(
            select(func.count(Case.id)).where(
                Case.conversation_id == conversation_footprint.chatwoot_conversation_id
            )
        )
    ).scalar_one()
    assert case_count == 0


@pytest.mark.asyncio
async def test_redis_executor_cleans_required_key_families(
    conversation_footprint,
    conversation_reset_redis,
) -> None:
    pattern_map = {
        f"checkpoint:{conversation_footprint.chatwoot_conversation_id}:*": [b"k1", b"k2"],
        f"checkpoint_write:{conversation_footprint.chatwoot_conversation_id}:*": [b"k3"],
        f"write_keys_zset:{conversation_footprint.chatwoot_conversation_id}:*": [b"k4"],
        f"checkpoint_latest:{conversation_footprint.chatwoot_conversation_id}:*": [b"k5"],
    }

    async def _scan(cursor: int, match: str, count: int = 200):
        return 0, pattern_map.get(match, [])

    async def _delete(*keys):
        return len(keys)

    conversation_reset_redis.scan.side_effect = _scan
    conversation_reset_redis.delete.side_effect = _delete

    context = ResetExecutionContext(
        conversation_uuid=conversation_footprint.conversation_uuid,
        conversation_id=conversation_footprint.chatwoot_conversation_id,
    )
    result = await ConversationResetRedisExecutor(redis_client=conversation_reset_redis).execute(
        context
    )

    assert result.status == "success"
    assert result.details["checkpoint"] == 2
    assert result.details["checkpoint_write"] == 1
    assert result.details["write_keys_zset"] == 1
    assert result.details["checkpoint_latest"] == 1
    assert result.details["image_batch"] == 1
    assert result.details["image_batch_final"] == 1
    assert result.details["deleted_keys_total"] == 7


@pytest.mark.asyncio
async def test_files_executor_deletes_assets_with_safe_path_handling(tmp_path) -> None:
    case_images_dir = tmp_path / "case_images"
    case_images_dir.mkdir(parents=True, exist_ok=True)

    safe_file = case_images_dir / "image-safe.jpg"
    safe_file.write_bytes(b"content")

    context = ResetExecutionContext(
        conversation_uuid=uuid4(),
        conversation_id="conversation-99",
        case_image_filenames=["image-safe.jpg", "missing.jpg", "../escape.jpg"],
    )

    result = await ConversationResetFilesExecutor(case_images_dir=case_images_dir).execute(context)

    assert result.status == "success"
    assert result.details["requested_files"] == 3
    assert result.details["deleted_files"] == 1
    assert result.details["missing_files"] == 1
    assert result.details["unsafe_paths"] == 1
    assert result.details["failed_files"] == 0
    assert not safe_file.exists()
