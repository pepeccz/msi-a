"""
Expediente Transition Adapter — Canonicalization Layer.

This module provides a pure function `canonicalize_transition()` that normalizes
ALL expediente sub-mode transition signals from heterogeneous tool payloads into
a single authoritative `CanonicalTransition` dataclass.

Architecture:
    - Multiple signal channels: _context_updates, _internal_flags, fsm_state_update, next_step
    - Legacy aliases: uppercase, Spanish names, abbreviations
    - Canonical output: lowercase, normalized sub-mode names

Usage:
    from agent.utils.expediente_transition_adapter import canonicalize_transition

    result = canonicalize_transition(tool_result)
    if result.target_sub_mode:
        mode_context["expediente_sub_mode"] = result.target_sub_mode

Design Decisions:
    - Pure function: testable, no side effects except structured logging
    - Precedence-based resolution: first non-None canonical value wins
    - Conflict detection: logs when channels disagree for observability
    - Fail-open: unknown values return None rather than raising

Author: MSI-a Team
Date: 2026-03-13
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

# =============================================================================
# Canonical Sub-Mode Constants
# =============================================================================

CANONICAL_SUB_MODES: list[str] = [
    "collect_personal",
    "collect_vehicle",
    "collect_element_data",
    "collect_base_docs",
    "collect_workshop",
    "review_summary",
]

# Legacy sub-mode names that have been observed in the wild.
SUB_MODE_ALIAS_MAP: dict[str, str] = {
    # Uppercase variants (legacy FSM style)
    "COLLECT_PERSONAL": "collect_personal",
    "COLLECT_VEHICLE": "collect_vehicle",
    "COLLECT_ELEMENT_DATA": "collect_element_data",
    "COLLECT_BASE_DOCS": "collect_base_docs",
    "COLLECT_WORKSHOP": "collect_workshop",
    "COLLECT_TALLER": "collect_workshop",
    "REVIEW": "review_summary",
    "REVIEW_SUMMARY": "review_summary",
    # Spanish legacy names
    "datos_personales": "collect_personal",
    "personal_data": "collect_personal",
    "datos_vehiculo": "collect_vehicle",
    "vehicle_data": "collect_vehicle",
    "datos_elemento": "collect_element_data",
    "element_data": "collect_element_data",
    "documentacion_base": "collect_base_docs",
    "base_docs": "collect_base_docs",
    "taller": "collect_workshop",
    "workshop": "collect_workshop",
    "revision": "review_summary",
    "resumen": "review_summary",
    # Abbreviated variants
    "collect_docs": "collect_base_docs",
    "personal": "collect_personal",
    "vehicle": "collect_vehicle",
    "element": "collect_element_data",
    "docs": "collect_base_docs",
    # Legacy special values (map to None — no transition)
    "sub_modo": None,
    "sub_mode": None,
    "current": None,
    "none": None,
    "null": None,
    "": None,
}


# =============================================================================
# Dataclass
# =============================================================================


@dataclass(frozen=True)
class CanonicalTransition:
    """
    Canonical representation of an expediente sub-mode transition.

    Attributes:
        target_sub_mode: The resolved canonical sub-mode (lowercase), or None
                         if no valid transition was detected.
        source_channel: Which signal channel provided the winning value.
        conflicts: List of channel names that disagreed with the winner.
        raw_signals: All extracted signal values before normalization.
    """

    target_sub_mode: Optional[str]
    source_channel: str
    conflicts: List[str]
    raw_signals: Dict[str, Any]


# =============================================================================
# Helper Functions
# =============================================================================


def _normalize_sub_mode(value: Optional[str]) -> Optional[str]:
    """
    Normalize a raw sub-mode value to canonical form.

    Process:
        1. Handle None/empty → return None
        2. Lowercase the input
        3. Look up in SUB_MODE_ALIAS_MAP
        4. If not in map, check if already canonical
        5. Otherwise log warning and return None (fail-open)

    Args:
        value: Raw sub-mode value from any channel.

    Returns:
        Canonical sub-mode string or None if invalid/unknown.
    """
    if value is None:
        return None

    if not isinstance(value, str):
        logger.warning(
            "sub_mode_invalid_type",
            value_type=type(value).__name__,
            value=str(value)[:100],  # Truncate for safety
        )
        return None

    stripped = value.strip()
    if not stripped:
        return None

    lower_value = stripped.lower()

    # Check alias map first (includes both lowercase keys and uppercase variants)
    if stripped in SUB_MODE_ALIAS_MAP:
        return SUB_MODE_ALIAS_MAP[stripped]

    if lower_value in SUB_MODE_ALIAS_MAP:
        return SUB_MODE_ALIAS_MAP[lower_value]

    # Check if already canonical
    if lower_value in CANONICAL_SUB_MODES:
        return lower_value

    # Unknown value — log warning and fail-open
    logger.warning(
        "sub_mode_unknown_value",
        raw_value=value[:100],  # Truncate for safety
        normalized=lower_value,
    )
    return None


def _extract_from_context_updates(tool_result: Dict[str, Any]) -> Optional[str]:
    """Extract sub-mode from _context_updates channel."""
    context_updates = tool_result.get("_context_updates")
    if not isinstance(context_updates, dict):
        return None
    return context_updates.get("expediente_sub_mode")


def _extract_from_internal_flags(tool_result: Dict[str, Any]) -> Optional[str]:
    """Extract sub-mode transition signal from _internal_flags channel."""
    internal_flags = tool_result.get("_internal_flags")
    if not isinstance(internal_flags, dict):
        return None

    # Look for transition signals in internal flags
    for key in ("expediente_sub_mode", "transition_to", "next_sub_mode"):
        value = internal_flags.get(key)
        if value is not None:
            return value

    return None


def _extract_from_fsm_state_update(tool_result: Dict[str, Any]) -> Optional[str]:
    """Extract sub-mode from legacy fsm_state_update channel."""
    fsm_update = tool_result.get("fsm_state_update")
    if not isinstance(fsm_update, dict):
        return None

    # Navigate: fsm_state_update.case_collection.step
    case_collection = fsm_update.get("case_collection")
    if not isinstance(case_collection, dict):
        return None

    return case_collection.get("step")


def _extract_from_next_step(tool_result: Dict[str, Any]) -> Optional[str]:
    """Extract sub-mode from legacy next_step channel."""
    next_step = tool_result.get("next_step")
    if isinstance(next_step, str):
        return next_step
    return None


# =============================================================================
# Main Canonicalization Function
# =============================================================================


def canonicalize_transition(tool_result: Dict[str, Any]) -> CanonicalTransition:
    """
    Canonicalize sub-mode transition signals from a tool result payload.

    Extracts signals from 4 channels (in precedence order):
        1. _context_updates dict → expediente_sub_mode key
        2. _internal_flags dict → transition signals
        3. fsm_state_update dict → case_collection.step
        4. next_step string directly

    Precedence: first non-None normalized value wins. If multiple channels
    have different non-None normalized values, a conflict is detected and
    logged for observability.

    Args:
        tool_result: Raw tool output dict (already parsed from JSON).

    Returns:
        CanonicalTransition with resolved sub-mode and metadata.

    Example:
        >>> result = canonicalize_transition({
        ...     "_context_updates": {"expediente_sub_mode": "collect_base_docs"},
        ...     "success": True,
        ... })
        >>> result.target_sub_mode
        "collect_base_docs"
        >>> result.source_channel
        "_context_updates"
    """
    # Ensure we have a dict to work with
    if not isinstance(tool_result, dict):
        logger.warning(
            "canonicalize_non_dict_input",
            input_type=type(tool_result).__name__,
        )
        return CanonicalTransition(
            target_sub_mode=None,
            source_channel="none",
            conflicts=[],
            raw_signals={"input_type": type(tool_result).__name__},
        )

    # Extract raw signals from all channels
    raw_signals: Dict[str, Any] = {
        "_context_updates": _extract_from_context_updates(tool_result),
        "_internal_flags": _extract_from_internal_flags(tool_result),
        "fsm_state_update": _extract_from_fsm_state_update(tool_result),
        "next_step": _extract_from_next_step(tool_result),
    }

    # Normalize all extracted values
    normalized: Dict[str, Optional[str]] = {
        channel: _normalize_sub_mode(value) for channel, value in raw_signals.items()
    }

    # Find the winner by precedence (first non-None normalized value)
    channels_precedence = [
        "_context_updates",
        "_internal_flags",
        "fsm_state_update",
        "next_step",
    ]

    winner_channel: Optional[str] = None
    winner_value: Optional[str] = None

    for channel in channels_precedence:
        if normalized[channel] is not None:
            winner_channel = channel
            winner_value = normalized[channel]
            break

    # Detect conflicts: other channels with different non-None values
    conflicts: List[str] = []
    if winner_channel is not None:
        for channel in channels_precedence:
            if channel != winner_channel and normalized[channel] is not None:
                if normalized[channel] != winner_value:
                    conflicts.append(channel)

    # Log conflict if detected
    if conflicts:
        logger.warning(
            "transition_signal_conflict",
            winner_channel=winner_channel,
            winner_value=winner_value,
            conflicting_channels=conflicts,
            conflicting_values={ch: normalized[ch] for ch in conflicts},
            raw_signals={k: v for k, v in raw_signals.items() if v is not None},
        )

    # Determine source channel string
    source_channel = winner_channel if winner_channel else "none"

    return CanonicalTransition(
        target_sub_mode=winner_value,
        source_channel=source_channel,
        conflicts=conflicts,
        raw_signals=raw_signals,
    )
