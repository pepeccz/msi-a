"""
Turn telemetry envelope — unified per-turn observability.

Captures latency breakdown, tool counts, LLM tier usage, constraint
violations, and state warnings for every agent conversation turn.

Always active: emits structured JSON at INFO level after each turn.

Usage in BaseModeNode.process()::

    from agent.services.turn_telemetry import (
        TurnTelemetryEnvelope,
        start_turn,
        complete_turn,
        emit_turn_telemetry,
    )

    envelope = start_turn(conversation_id, mode="PRE_EXPEDIENTE_MODE")
    # ... process message, call tools ...
    envelope.tool_iterations = iteration_count
    envelope.tools_called = list(tools_called)
    complete_turn(envelope)
    emit_turn_telemetry(envelope)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TurnTelemetryEnvelope:
    """
    Per-turn telemetry data envelope.

    Collects timing, tool usage, LLM tier, constraint violations,
    and state contract warnings for a single conversation turn.

    Fields are populated progressively during the turn — only
    ``conversation_id``, ``turn_id``, ``mode``, and ``timestamp_start``
    are set at creation time. All other fields are filled in by the
    mode node or ``complete_turn()``.
    """

    # Identity
    conversation_id: str
    turn_id: str
    mode: str
    sub_mode: str | None = None

    # Timing
    timestamp_start: float = 0.0  # time.monotonic()
    timestamp_end: float | None = None
    latency_ms: float | None = None

    # LLM usage estimates
    prompt_tokens_estimate: int | None = None
    completion_tokens: int | None = None

    # Tool loop
    tool_iterations: int = 0
    tools_called: list[str] = field(default_factory=list)

    # Fallback tracking
    fallback_used: bool = False
    original_tier: str | None = None
    final_tier: str | None = None

    # Quality signals
    constraint_violations: int = 0
    llm_validations_skipped: int = 0
    state_warnings: list[str] = field(default_factory=list)

    # Exit reason
    exit_reason: str | None = (
        None  # no_tool_calls, max_iterations, validation_abort, error
    )
    error: str | None = None


def start_turn(
    conversation_id: str,
    mode: str,
    sub_mode: str | None = None,
) -> TurnTelemetryEnvelope:
    """
    Create a new telemetry envelope for a conversation turn.

    Should be called at the very beginning of ``BaseModeNode.process()``.

    Args:
        conversation_id: Conversation identifier.
        mode: Current mode name (e.g. ``"PRESUPUESTO_MODE"``).
        sub_mode: Optional sub-mode (e.g. ``"collect_personal"``).

    Returns:
        A new ``TurnTelemetryEnvelope`` with start timestamp set.
    """
    return TurnTelemetryEnvelope(
        conversation_id=conversation_id,
        turn_id=str(uuid.uuid4()),
        mode=mode,
        sub_mode=sub_mode,
        timestamp_start=time.monotonic(),
    )


def complete_turn(envelope: TurnTelemetryEnvelope) -> TurnTelemetryEnvelope:
    """
    Finalize timing on a telemetry envelope.

    Calculates ``latency_ms`` from ``timestamp_start`` to now.

    Args:
        envelope: The envelope to complete.

    Returns:
        The same envelope (mutated) with ``timestamp_end`` and ``latency_ms`` set.
    """
    envelope.timestamp_end = time.monotonic()
    envelope.latency_ms = round(
        (envelope.timestamp_end - envelope.timestamp_start) * 1000,
        2,
    )
    return envelope


def emit_turn_telemetry(envelope: TurnTelemetryEnvelope) -> None:
    """
    Log the telemetry envelope as structured JSON.

    Always emits at INFO level (telemetry is always active).

    Args:
        envelope: Completed turn telemetry envelope.
    """
    logger.info(
        "turn_telemetry",
        conversation_id=envelope.conversation_id,
        turn_id=envelope.turn_id,
        mode=envelope.mode,
        sub_mode=envelope.sub_mode,
        latency_ms=envelope.latency_ms,
        prompt_tokens_estimate=envelope.prompt_tokens_estimate,
        completion_tokens=envelope.completion_tokens,
        tool_iterations=envelope.tool_iterations,
        tools_called=envelope.tools_called,
        fallback_used=envelope.fallback_used,
        original_tier=envelope.original_tier,
        final_tier=envelope.final_tier,
        constraint_violations=envelope.constraint_violations,
        llm_validations_skipped=envelope.llm_validations_skipped,
        state_warnings=envelope.state_warnings,
        exit_reason=envelope.exit_reason,
        error=envelope.error,
    )
