"""
MSI Automotive - Tool Call Logs API routes.

Provides read endpoints for querying persistent tool call logs.
Enables post-hoc debugging of agent conversations by showing
which tools were called, their parameters, results, and timing.
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc

from api.routes.admin import get_current_user
from database.connection import get_async_session
from database.models import AdminUser, ToolCallLog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/tool-logs")


# =============================================================================
# Pydantic Schemas
# =============================================================================


class ToolLogResponse(BaseModel):
    """Schema for a single tool call log entry."""

    id: UUID
    conversation_id: str
    tool_name: str
    parameters: dict | None = None
    result_summary: str | None = None
    result_type: str
    error_message: str | None = None
    execution_time_ms: int | None = None
    iteration: int
    timestamp: str

    class Config:
        from_attributes = True


class ToolLogStats(BaseModel):
    """Aggregated statistics for tool calls."""

    tool_name: str
    total_calls: int
    success_count: int
    error_count: int
    blocked_count: int
    avg_execution_ms: float | None = None


class PaginatedToolLogs(BaseModel):
    """Paginated list of tool logs."""

    items: list[ToolLogResponse]
    total: int
    skip: int
    limit: int


# =============================================================================
# Endpoints
# =============================================================================


@router.get("")
async def list_tool_logs(
    conversation_id: str | None = Query(None, description="Filter by conversation ID"),
    tool_name: str | None = Query(None, description="Filter by tool name"),
    result_type: str | None = Query(None, description="Filter by result: success, error, blocked"),
    date_from: datetime | None = Query(None, description="Start date (ISO format)"),
    date_to: datetime | None = Query(None, description="End date (ISO format)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _: AdminUser = Depends(get_current_user),
) -> PaginatedToolLogs:
    """List tool call logs with filtering and pagination."""
    async with get_async_session() as session:
        # Base query
        query = select(ToolCallLog).order_by(desc(ToolCallLog.timestamp))
        count_query = select(func.count(ToolCallLog.id))

        # Apply filters
        if conversation_id:
            query = query.where(ToolCallLog.conversation_id == conversation_id)
            count_query = count_query.where(ToolCallLog.conversation_id == conversation_id)
        if tool_name:
            query = query.where(ToolCallLog.tool_name == tool_name)
            count_query = count_query.where(ToolCallLog.tool_name == tool_name)
        if result_type:
            query = query.where(ToolCallLog.result_type == result_type)
            count_query = count_query.where(ToolCallLog.result_type == result_type)
        if date_from:
            query = query.where(ToolCallLog.timestamp >= date_from)
            count_query = count_query.where(ToolCallLog.timestamp >= date_from)
        if date_to:
            query = query.where(ToolCallLog.timestamp <= date_to)
            count_query = count_query.where(ToolCallLog.timestamp <= date_to)

        # Get total count
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        # Get paginated results
        query = query.offset(skip).limit(limit)
        result = await session.execute(query)
        logs = result.scalars().all()

        return PaginatedToolLogs(
            items=[
                ToolLogResponse(
                    id=log.id,
                    conversation_id=log.conversation_id,
                    tool_name=log.tool_name,
                    parameters=log.parameters,
                    result_summary=log.result_summary,
                    result_type=log.result_type,
                    error_message=log.error_message,
                    execution_time_ms=log.execution_time_ms,
                    iteration=log.iteration,
                    timestamp=log.timestamp.isoformat(),
                )
                for log in logs
            ],
            total=total,
            skip=skip,
            limit=limit,
        )


@router.get("/conversation/{conversation_id}")
async def get_conversation_tool_logs(
    conversation_id: str,
    _: AdminUser = Depends(get_current_user),
) -> list[ToolLogResponse]:
    """Get all tool logs for a specific conversation, ordered chronologically."""
    async with get_async_session() as session:
        result = await session.execute(
            select(ToolCallLog)
            .where(ToolCallLog.conversation_id == conversation_id)
            .order_by(ToolCallLog.timestamp.asc())
        )
        logs = result.scalars().all()

        return [
            ToolLogResponse(
                id=log.id,
                conversation_id=log.conversation_id,
                tool_name=log.tool_name,
                parameters=log.parameters,
                result_summary=log.result_summary,
                result_type=log.result_type,
                error_message=log.error_message,
                execution_time_ms=log.execution_time_ms,
                iteration=log.iteration,
                timestamp=log.timestamp.isoformat(),
            )
            for log in logs
        ]


@router.get("/stats")
async def get_tool_stats(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    _: AdminUser = Depends(get_current_user),
) -> list[ToolLogStats]:
    """Get aggregated statistics per tool (call counts, error rates, avg timing)."""
    async with get_async_session() as session:
        query = select(
            ToolCallLog.tool_name,
            func.count(ToolCallLog.id).label("total_calls"),
            func.count(ToolCallLog.id).filter(ToolCallLog.result_type == "success").label("success_count"),
            func.count(ToolCallLog.id).filter(ToolCallLog.result_type == "error").label("error_count"),
            func.count(ToolCallLog.id).filter(ToolCallLog.result_type == "blocked").label("blocked_count"),
            func.avg(ToolCallLog.execution_time_ms).label("avg_execution_ms"),
        ).group_by(ToolCallLog.tool_name)

        if date_from:
            query = query.where(ToolCallLog.timestamp >= date_from)
        if date_to:
            query = query.where(ToolCallLog.timestamp <= date_to)

        query = query.order_by(desc("total_calls"))
        result = await session.execute(query)
        rows = result.all()

        return [
            ToolLogStats(
                tool_name=row.tool_name,
                total_calls=row.total_calls,
                success_count=row.success_count,
                error_count=row.error_count,
                blocked_count=row.blocked_count,
                avg_execution_ms=float(row.avg_execution_ms) if row.avg_execution_ms else None,
            )
            for row in rows
        ]


@router.get("/tool-names")
async def get_tool_names(
    _: AdminUser = Depends(get_current_user),
) -> list[str]:
    """Get list of distinct tool names that have been logged."""
    async with get_async_session() as session:
        result = await session.execute(
            select(ToolCallLog.tool_name)
            .distinct()
            .order_by(ToolCallLog.tool_name)
        )
        return [row[0] for row in result.all()]
