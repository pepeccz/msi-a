"""
MSI Automotive - Tool Call Logging Service.

Provides persistent logging of agent tool invocations to PostgreSQL.
Unlike Redis checkpointer (24h TTL), these logs persist indefinitely
for post-hoc debugging and conversation analysis.
"""

import logging
import uuid
from datetime import datetime, UTC
from typing import Any

from database.connection import get_async_session
from database.models import ToolCallLog

logger = logging.getLogger(__name__)


async def log_tool_call(
    conversation_id: str,
    tool_name: str,
    parameters: dict[str, Any] | None = None,
    result_summary: str | None = None,
    result_type: str = "success",
    error_message: str | None = None,
    execution_time_ms: int | None = None,
    iteration: int = 0,
) -> None:
    """
    Persist a tool call record to PostgreSQL.

    This is a fire-and-forget operation: errors are logged but never
    propagate to the caller, ensuring tool logging never blocks the agent.

    Args:
        conversation_id: Chatwoot conversation ID.
        tool_name: Name of the tool that was called.
        parameters: Tool call parameters (will be sanitized of sensitive data).
        result_summary: Truncated summary of the tool result (max 500 chars).
        result_type: Outcome classification: "success", "error", "blocked".
        error_message: Full error message if result_type is "error".
        execution_time_ms: Execution time in milliseconds.
        iteration: Tool loop iteration number.
    """
    try:
        # Sanitize parameters (remove potentially large or sensitive data)
        safe_params = _sanitize_parameters(parameters) if parameters else None

        # Truncate result_summary
        if result_summary and len(result_summary) > 500:
            result_summary = result_summary[:497] + "..."

        async with get_async_session() as session:
            log_entry = ToolCallLog(
                id=uuid.uuid4(),
                conversation_id=str(conversation_id),
                tool_name=tool_name,
                parameters=safe_params,
                result_summary=result_summary,
                result_type=result_type,
                error_message=error_message,
                execution_time_ms=execution_time_ms,
                iteration=iteration,
                timestamp=datetime.now(UTC),
            )
            session.add(log_entry)
            await session.commit()

    except Exception as e:
        # Never let logging errors propagate to the agent
        logger.error(
            f"Failed to log tool call: {e}",
            extra={
                "conversation_id": conversation_id,
                "tool_name": tool_name,
            },
        )


def classify_result(result_text: str) -> str:
    """
    Classify a tool result as success, error, or blocked.

    Args:
        result_text: The string result returned by the tool.

    Returns:
        One of: "success", "error", "blocked".
    """
    if not result_text:
        return "success"

    lower = result_text.lower()

    # PRIORITY 1: Check for explicit success indicators in JSON responses
    # These take precedence over keyword matching
    success_indicators = [
        "'success': true",
        '"success": true',
        "success': true",  # Sometimes quotes vary
    ]
    if any(s in lower for s in success_indicators):
        return "success"

    # Check for blocking patterns (duplicate prevention, etc.)
    blocked_patterns = [
        "ya fueron enviadas",
        "no vuelvas a enviar",
        "ya fue enviada",
        "bloqueando duplicado",
    ]
    if any(p in lower for p in blocked_patterns):
        return "blocked"

    # Check for explicit failure indicators
    failure_indicators = [
        "'success': false",
        '"success": false',
        "success': false",
    ]
    if any(f in lower for f in failure_indicators):
        return "error"

    # Check for error patterns (more specific to avoid false positives)
    error_patterns = [
        '"error":',  # JSON error field
        "'error':",  # JSON error field variant
        "error interno",
        "no hay presupuesto",
        "no se pudo",
        "no encontr",
        "no hay estado",
        "categoria no encontrada",
        "no se reconocieron",
        "códigos de elementos no válidos",
    ]
    if any(p in lower for p in error_patterns):
        return "error"

    return "success"


def _sanitize_parameters(params: dict[str, Any]) -> dict[str, Any]:
    """
    Remove potentially sensitive or excessively large data from parameters.

    Truncates string values > 200 chars, removes any keys containing
    'password', 'token', 'secret', or 'key'.
    """
    sanitized = {}
    sensitive_keys = {"password", "token", "secret", "key", "api_key"}

    for k, v in params.items():
        if k.lower() in sensitive_keys:
            sanitized[k] = "[REDACTED]"
        elif isinstance(v, str) and len(v) > 200:
            sanitized[k] = v[:197] + "..."
        elif isinstance(v, dict):
            sanitized[k] = _sanitize_parameters(v)
        elif isinstance(v, list) and len(v) > 10:
            sanitized[k] = f"[list of {len(v)} items]"
        else:
            sanitized[k] = v

    return sanitized
