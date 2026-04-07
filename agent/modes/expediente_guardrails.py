"""
MSI-a — Expediente Certainty Guardrails (Phase 1 Foundation).

This module provides the **certainty envelope** for EXPEDIENTE_MODE: a versioned
contract that gates what can be said (or which transitions are allowed) based on
what tools have actually confirmed.

Architecture:
    - ``CertaintyEnvelope`` — canonical snapshot of what is actually known this turn.
    - ``normalize_tool_payload`` — converts heterogeneous tool outputs
      (case_collection_update, _internal_flags, _context_updates) to a CertaintyEnvelope.
    - ``evaluate_progression_eligibility`` — checks whether a sub-mode transition
      is safe to execute given the current envelope.
    - ``evaluate_claim_eligibility`` — checks whether the LLM can make a specific
      class of claim (e.g. "photos received", "case finalised") in its response.
    - ``log_guardrail_triggered`` — structured log emitter for audit trail.

Design principles:
    - Extend, do NOT redesign. The existing expediente_mode.py architecture
      (_extract_context_from_tool, _set_transition_updates, kickoff guard, tool
      matrix) stays intact. This module plugs into those extension points.
    - Fail-open: when certainty is ambiguous the guardrail logs a warning but
      allows the action. Hard blocks are reserved for cases where tool evidence
      is demonstrably absent.
    - Feature-flagged: the host code will only activate guardrails when
      ``EXPEDIENTE_CERTAINTY_GUARDRAILS_ENABLED=True`` (added to config separately).

Version: 1 (contract version embedded in every envelope for migration safety).
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import Any

import structlog
from agent.utils.expediente_transition_adapter import canonicalize_transition

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Contract version — bump when the envelope schema changes.
# ---------------------------------------------------------------------------
CERTAINTY_CONTRACT_VERSION: int = 1


# ---------------------------------------------------------------------------
# Reason codes (taxonomy of guardrail outcomes)
# ---------------------------------------------------------------------------


class GuardrailReason(str, Enum):
    """Taxonomy of reasons why a guardrail check returns allowed=False.

    String enum so values are JSON-serialisable without extra work.
    """

    # Progression guardrails (sub-mode transitions)
    PROGRESSION_NOT_ALLOWED = "PROGRESSION_NOT_ALLOWED"
    """Tool evidence required for this transition is absent."""

    PROGRESSION_TOOL_NOT_CALLED = "PROGRESSION_TOOL_NOT_CALLED"
    """The triggering tool has not been called this turn."""

    PROGRESSION_TOOL_FAILED = "PROGRESSION_TOOL_FAILED"
    """The triggering tool was called but returned success=False."""

    STALE_STEP_NARRATIVE = "STALE_STEP_NARRATIVE"
    """Post-transition first turn: LLM attempted to narrate the previous step."""

    # Claim guardrails (response content eligibility)
    CLAIM_UNSUPPORTED = "CLAIM_UNSUPPORTED"
    """No tool evidence supports making this claim class."""

    DOCS_NOT_CONFIRMED_BY_TOOL = "DOCS_NOT_CONFIRMED_BY_TOOL"
    """LLM claims docs received but confirmar_documentacion_base() not called."""

    IMAGES_NOT_SENT_BY_TOOL = "IMAGES_NOT_SENT_BY_TOOL"
    """LLM claims images sent but enviar_imagenes_ejemplo() was not called."""

    CASE_NOT_FINALIZED_BY_TOOL = "CASE_NOT_FINALIZED_BY_TOOL"
    """LLM claims case finalised but finalizar_expediente() was not called."""

    COMPLETION_NOT_CONFIRMED_BY_TOOL = "COMPLETION_NOT_CONFIRMED_BY_TOOL"
    """LLM claims element/step complete without calling the confirming tool."""

    DELIVERY_UNCONFIRMED = "DELIVERY_UNCONFIRMED"
    """Delivery outcome has not been confirmed by a tool result."""

    ANTICIPATORY_NARRATION = "ANTICIPATORY_NARRATION"
    """LLM is narrating the next sub-mode's content before it is the active mode."""

    FIELD_NOT_SAVED_BY_TOOL = "FIELD_NOT_SAVED_BY_TOOL"
    """LLM claims field confirmed but guardar_datos_elemento() was not called."""

    # Neutral — guardrail not applicable
    NOT_APPLICABLE = "NOT_APPLICABLE"
    """Guardrail check was a no-op (conditions not met, allowed by default)."""

    # Check passed
    ALLOWED = "ALLOWED"
    """Guardrail check passed — action is permitted."""


# ---------------------------------------------------------------------------
# Claim class enum
# ---------------------------------------------------------------------------


class ClaimClass(str, Enum):
    """Classes of claims the LLM might make in a response.

    Used by ``evaluate_claim_eligibility`` to determine what tool evidence
    is required before the claim can be included in a response.
    """

    NEXT_STEP_DESCRIPTION = "NEXT_STEP_DESCRIPTION"
    """Describing requirements / tasks belonging to the *next* sub-mode."""

    COMPLETION_CLAIM = "COMPLETION_CLAIM"
    """Declaring an element, phase, or the entire expediente as complete."""

    DOCS_RECEIVED = "DOCS_RECEIVED"
    """Stating that documents have been received / confirmed."""

    IMAGES_SENT = "IMAGES_SENT"
    """Stating that example images have been sent to the user."""

    CASE_FINALIZED = "CASE_FINALIZED"
    """Stating that the expediente has been submitted / finalised."""

    FIELD_CONFIRMED = "FIELD_CONFIRMED"
    """Stating that a specific data field has been saved / confirmed."""


# ---------------------------------------------------------------------------
# CertaintyEnvelope — canonical certainty snapshot
# ---------------------------------------------------------------------------


@dataclass
class CertaintyEnvelope:
    """Canonical snapshot of what is *actually* known this turn.

    Populated by ``normalize_tool_payload``. The host mode node persists the
    envelope as ``mode_context["certainty_envelope"]`` (serialised to dict via
    ``to_dict()``) so it survives the Redis checkpoint.

    All fields default to the most conservative value (nothing confirmed) to
    ensure new fields are safe until explicitly set.
    """

    # Contract identity
    version: int = CERTAINTY_CONTRACT_VERSION
    sub_mode: str = ""
    """The sub-mode in which this envelope was produced (lower-case constant)."""

    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    # Tool call evidence — what actually happened this turn
    tools_called: list[str] = field(default_factory=list)
    """Names of every tool called during this turn (may span multiple iterations)."""

    tools_succeeded: list[str] = field(default_factory=list)
    """Subset of tools_called that returned success=True."""

    tools_failed: list[str] = field(default_factory=list)
    """Subset of tools_called that returned success=False."""

    # Certainty flags — set from successful tool evidence
    photos_confirmed: bool = False
    """confirmar_fotos_elemento returned success=True this turn."""

    docs_confirmed: bool = False
    """confirmar_documentacion_base returned success=True this turn."""

    images_sent: bool = False
    """enviar_imagenes_ejemplo returned success=True (or status!='failure')."""

    case_finalized: bool = False
    """finalizar_expediente returned success=True this turn."""

    all_elements_complete: bool = False
    """completar_elemento_actual or confirmar_fotos_elemento returned all_elements_complete=True."""

    field_saved: bool = False
    """guardar_datos_elemento returned success=True this turn."""

    # Transition readiness
    transition_triggered: bool = False
    """A sub-mode transition signal was produced this turn."""

    transition_target: str | None = None
    """Target sub-mode of the pending transition (lower-case constant)."""

    # Post-transition context
    is_first_destination_turn: bool = False
    """True when this turn is the first in the destination after a transition."""

    allowed_transition_claims: bool = True
    """Whether the LLM can narrate the new step in this turn.

    Set to False when ``is_first_destination_turn=True`` and the transition
    closure was already sent — the LLM must only produce an actionable kickoff,
    not re-describe the previous step.
    """

    blocked_claim_reason: str | None = None
    """Human-readable reason injected into the prompt when a claim is blocked."""

    # Kickoff guard
    kickoff_required: bool = False
    """True when the destination sub-mode's actionable kickoff must be in this response."""

    # Raw payload for debugging
    source_tool_names: list[str] = field(default_factory=list)
    """All tool names seen during normalisation (may differ from tools_called)."""

    def to_dict(self) -> dict[str, Any]:
        """Serialise envelope to a plain dict for Redis persistence."""
        return {
            "version": self.version,
            "sub_mode": self.sub_mode,
            "created_at": self.created_at,
            "tools_called": self.tools_called,
            "tools_succeeded": self.tools_succeeded,
            "tools_failed": self.tools_failed,
            "photos_confirmed": self.photos_confirmed,
            "docs_confirmed": self.docs_confirmed,
            "images_sent": self.images_sent,
            "case_finalized": self.case_finalized,
            "all_elements_complete": self.all_elements_complete,
            "field_saved": self.field_saved,
            "transition_triggered": self.transition_triggered,
            "transition_target": self.transition_target,
            "is_first_destination_turn": self.is_first_destination_turn,
            "allowed_transition_claims": self.allowed_transition_claims,
            "blocked_claim_reason": self.blocked_claim_reason,
            "kickoff_required": self.kickoff_required,
            "source_tool_names": self.source_tool_names,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CertaintyEnvelope":
        """Deserialise from a plain dict (loaded from Redis checkpoint)."""
        return cls(
            version=data.get("version", CERTAINTY_CONTRACT_VERSION),
            sub_mode=data.get("sub_mode", ""),
            created_at=data.get("created_at", datetime.now(UTC).isoformat()),
            tools_called=data.get("tools_called", []),
            tools_succeeded=data.get("tools_succeeded", []),
            tools_failed=data.get("tools_failed", []),
            photos_confirmed=bool(data.get("photos_confirmed", False)),
            docs_confirmed=bool(data.get("docs_confirmed", False)),
            images_sent=bool(data.get("images_sent", False)),
            case_finalized=bool(data.get("case_finalized", False)),
            all_elements_complete=bool(data.get("all_elements_complete", False)),
            field_saved=bool(data.get("field_saved", False)),
            transition_triggered=bool(data.get("transition_triggered", False)),
            transition_target=data.get("transition_target"),
            is_first_destination_turn=bool(
                data.get("is_first_destination_turn", False)
            ),
            allowed_transition_claims=bool(data.get("allowed_transition_claims", True)),
            blocked_claim_reason=data.get("blocked_claim_reason"),
            kickoff_required=bool(data.get("kickoff_required", False)),
            source_tool_names=data.get("source_tool_names", []),
        )

    @classmethod
    def empty(cls, sub_mode: str = "") -> "CertaintyEnvelope":
        """Return a conservative all-false envelope (nothing confirmed)."""
        return cls(sub_mode=sub_mode)


# ---------------------------------------------------------------------------
# Legacy payload normaliser
# ---------------------------------------------------------------------------


def normalize_tool_payload(
    tool_name: str,
    raw_result: str | dict[str, Any],
    current_sub_mode: str,
    existing_envelope: CertaintyEnvelope | None = None,
) -> CertaintyEnvelope:
    """Convert a heterogeneous tool result to a CertaintyEnvelope.

    Handles all three payload shapes produced by the current tool inventory:

    1. Canonical shape (new tools): ``_internal_flags`` + ``_context_updates``
    2. FSM compat shape (v1 recycled tools): ``case_collection_update.case_collection``
    3. Legacy shape: flat dict with well-known keys
       (``all_elements_complete``, ``photos_confirmed``, ``success``, …)

    The function is additive: it starts from an existing envelope (if provided)
    and merges the new tool evidence.  This allows the caller to accumulate
    evidence across multiple tool calls in a single turn.

    Args:
        tool_name: Name of the tool that produced this result.
        raw_result: Tool return value (JSON string or already-parsed dict).
        current_sub_mode: Lower-case expediente sub-mode constant.
        existing_envelope: Envelope to merge into (defaults to empty).

    Returns:
        Updated CertaintyEnvelope (always a fresh object, never mutated).
    """
    envelope = existing_envelope or CertaintyEnvelope.empty(sub_mode=current_sub_mode)

    # Parse raw result to dict
    if isinstance(raw_result, str):
        try:
            data: dict[str, Any] = json.loads(raw_result)
        except (json.JSONDecodeError, ValueError):
            data = {"_parse_failed": True}
    elif isinstance(raw_result, dict):
        data = raw_result
    else:
        data = {}

    if not isinstance(data, dict):
        data = {}

    # Track all tool names seen
    source_names = list(envelope.source_tool_names)
    if tool_name not in source_names:
        source_names.append(tool_name)

    # Track call/success/failure lists
    tools_called = list(envelope.tools_called)
    tools_succeeded = list(envelope.tools_succeeded)
    tools_failed = list(envelope.tools_failed)

    if tool_name not in tools_called:
        tools_called.append(tool_name)

    success_val = data.get("success", False)
    if success_val:
        if tool_name not in tools_succeeded:
            tools_succeeded.append(tool_name)
    else:
        if tool_name not in tools_failed:
            tools_failed.append(tool_name)

    # -----------------------------------------------------------------------
    # Layer 0: _state_update (canonical — Wave-4 refactored tools)
    # -----------------------------------------------------------------------
    state_update: dict[str, Any] = {}
    if "_state_update" in data and isinstance(data["_state_update"], dict):
        state_update = data["_state_update"]

    # -----------------------------------------------------------------------
    # Layer 1: _internal_flags (legacy — tools not yet migrated to _state_update)
    # -----------------------------------------------------------------------
    flags: dict[str, Any] = {}
    if "_internal_flags" in data and isinstance(data["_internal_flags"], dict):
        flags = data["_internal_flags"]

    # -----------------------------------------------------------------------
    # Layer 2: _context_updates (standard contract from tool_context_contract.py)
    # -----------------------------------------------------------------------
    ctx_updates: dict[str, Any] = {}
    if "_context_updates" in data and isinstance(data["_context_updates"], dict):
        ctx_updates = data["_context_updates"]

    # -----------------------------------------------------------------------
    # Layer 3: case_collection_update.case_collection (v1 tools)
    # -----------------------------------------------------------------------
    fsm_data: dict[str, Any] = {}
    if "case_collection_update" in data and isinstance(
        data["case_collection_update"], dict
    ):
        cc = data["case_collection_update"].get("case_collection", {})
        if isinstance(cc, dict):
            fsm_data = cc
    elif "case_collection" in data and isinstance(data["case_collection"], dict):
        fsm_data = data["case_collection"]

    # -----------------------------------------------------------------------
    # Derive certainty flags from payload evidence
    # -----------------------------------------------------------------------

    # photos_confirmed
    photos_confirmed = envelope.photos_confirmed or (
        tool_name == "confirmar_fotos_elemento"
        and bool(success_val)
        and bool(data.get("photos_confirmed", False))
    )

    # docs_confirmed
    docs_confirmed = envelope.docs_confirmed or (
        tool_name == "confirmar_documentacion_base" and bool(success_val)
    )

    # images_sent — enviar_imagenes_ejemplo signals success or partial
    images_sent = envelope.images_sent or bool(
        state_update.get("imagenes_enviadas", False)
        or flags.get("imagenes_enviadas", False)
        or (
            tool_name == "enviar_imagenes_ejemplo"
            and data.get("status") not in ("failure", None, "")
        )
    )

    # case_finalized
    case_finalized = envelope.case_finalized or bool(
        state_update.get("case_finalized", False)
        or flags.get("case_finalized", False)
        or (tool_name == "finalizar_expediente" and bool(success_val))
    )

    # all_elements_complete
    all_elements_complete = envelope.all_elements_complete or bool(
        data.get("all_elements_complete", False)
        or fsm_data.get("all_elements_complete", False)
        or ctx_updates.get("all_elements_complete", False)
        or state_update.get("all_elements_complete", False)
    )

    # field_saved
    field_saved = envelope.field_saved or (
        tool_name == "guardar_datos_elemento" and bool(success_val)
    )

    # ===================================================================
    # ADAPTER INTEGRATION: Canonical transition canonicalization (Task 4.1)
    # ===================================================================
    # Normalize heterogeneous transition signals into canonical sub-mode values.
    # Always active (ENABLE_CANONICAL_TRANSITION_ADAPTER was always True).
    transition = canonicalize_transition(data)

    if transition.target_sub_mode is not None:
        new_sub_mode = transition.target_sub_mode
        transition_triggered = True
        transition_target = transition.target_sub_mode
        logger.info(
            "guardrail_transition_canonicalized",
            target=transition.target_sub_mode,
            source=transition.source_channel,
            conflicts=transition.conflicts,
            tool_name=tool_name,
        )
    else:
        # No canonical transition detected
        new_sub_mode = None
        transition_triggered = envelope.transition_triggered
        transition_target = envelope.transition_target
    # ===================================================================

    return CertaintyEnvelope(
        version=CERTAINTY_CONTRACT_VERSION,
        sub_mode=current_sub_mode,
        created_at=envelope.created_at,  # Preserve original creation time
        tools_called=tools_called,
        tools_succeeded=tools_succeeded,
        tools_failed=tools_failed,
        photos_confirmed=photos_confirmed,
        docs_confirmed=docs_confirmed,
        images_sent=images_sent,
        case_finalized=case_finalized,
        all_elements_complete=all_elements_complete,
        field_saved=field_saved,
        transition_triggered=transition_triggered,
        transition_target=transition_target,
        is_first_destination_turn=envelope.is_first_destination_turn,
        allowed_transition_claims=envelope.allowed_transition_claims,
        blocked_claim_reason=envelope.blocked_claim_reason,
        kickoff_required=envelope.kickoff_required,
        source_tool_names=source_names,
    )


# ---------------------------------------------------------------------------
# Evaluators
# ---------------------------------------------------------------------------


def evaluate_progression_eligibility(
    envelope: CertaintyEnvelope,
    sub_mode: str,
) -> tuple[bool, str]:
    """Gate a sub-mode transition: is the proposed progression safe?

    Called BEFORE ``_set_transition_updates()`` writes the new sub-mode to
    ``mode_context``.  When this returns ``(False, reason)``, the caller should
    log a guardrail event and suppress the transition.

    Transition rules by (from → to):
    - collect_element_data → collect_base_docs:
        Requires all_elements_complete=True in the envelope.
    - collect_base_docs → collect_personal:
        Requires docs_confirmed=True (confirmar_documentacion_base succeeded).
    - collect_personal → collect_vehicle:
        Requires a successful actualizar_datos_expediente call in this turn.
    - collect_vehicle → collect_workshop:
        Requires a successful actualizar_datos_expediente call in this turn.
    - collect_workshop → review_summary:
        Requires a successful actualizar_datos_taller call in this turn.
    - Any → Any (default):
        Requires the triggering tool to have succeeded.

    Args:
        envelope: Current turn's certainty envelope.
        sub_mode: Target sub-mode (lower-case constant, e.g. "collect_base_docs").

    Returns:
        (allowed: bool, reason: str) — reason is a GuardrailReason value string.
    """
    current = envelope.sub_mode

    # -----------------------------------------------------------------------
    # Specific transition rules
    # -----------------------------------------------------------------------

    if current == "collect_element_data" and sub_mode == "collect_base_docs":
        if not envelope.all_elements_complete:
            return False, GuardrailReason.PROGRESSION_NOT_ALLOWED.value
        return True, GuardrailReason.ALLOWED.value

    if current == "collect_base_docs" and sub_mode == "collect_personal":
        if not envelope.docs_confirmed:
            return False, GuardrailReason.DOCS_NOT_CONFIRMED_BY_TOOL.value
        return True, GuardrailReason.ALLOWED.value

    if current == "collect_personal" and sub_mode == "collect_vehicle":
        # Requires successful actualizar_datos_expediente
        if "actualizar_datos_expediente" not in envelope.tools_succeeded:
            return False, GuardrailReason.PROGRESSION_TOOL_NOT_CALLED.value
        return True, GuardrailReason.ALLOWED.value

    if current == "collect_vehicle" and sub_mode == "collect_workshop":
        if "actualizar_datos_expediente" not in envelope.tools_succeeded:
            return False, GuardrailReason.PROGRESSION_TOOL_NOT_CALLED.value
        return True, GuardrailReason.ALLOWED.value

    if current == "collect_workshop" and sub_mode == "review_summary":
        if "actualizar_datos_taller" not in envelope.tools_succeeded:
            return False, GuardrailReason.PROGRESSION_TOOL_NOT_CALLED.value
        return True, GuardrailReason.ALLOWED.value

    # -----------------------------------------------------------------------
    # Default: any transition from review_summary requires a finalizing tool
    # -----------------------------------------------------------------------
    if current == "review_summary" and sub_mode not in ("review_summary",):
        # Edits back to earlier steps are allowed if editar_expediente succeeded
        if "editar_expediente" in envelope.tools_succeeded:
            return True, GuardrailReason.ALLOWED.value
        # Finalization
        if sub_mode == "completed" and envelope.case_finalized:
            return True, GuardrailReason.ALLOWED.value
        # Fallback: any successful tool in this turn allows the transition
        if envelope.tools_succeeded:
            return True, GuardrailReason.ALLOWED.value
        return False, GuardrailReason.PROGRESSION_NOT_ALLOWED.value

    # -----------------------------------------------------------------------
    # Generic fallback: if transition_triggered but no evidence → warn, allow
    # (fail-open for unknown combinations to avoid blocking valid paths)
    # -----------------------------------------------------------------------
    return True, GuardrailReason.ALLOWED.value


def evaluate_claim_eligibility(
    envelope: CertaintyEnvelope,
    claim_class: ClaimClass,
    sub_mode: str,
) -> tuple[bool, str]:
    """Gate a claim class: can the LLM make this type of statement?

    Called during response assembly (post-LLM, pre-delivery). When this
    returns ``(False, reason)``, the caller should inject a system reprompt
    forcing the LLM to retract or rephrase the claim.

    Args:
        envelope: Current turn's certainty envelope.
        claim_class: The type of claim to evaluate.
        sub_mode: Current sub-mode context (lower-case constant).

    Returns:
        (allowed: bool, reason: str) — reason is a GuardrailReason value string.
    """
    if claim_class == ClaimClass.DOCS_RECEIVED:
        # Task 2.3: Scope this gate to collect_base_docs only.
        # In other sub-modes the agent may legitimately refer back to previously
        # confirmed docs; blocking that reference produces false positives.
        # Outside collect_base_docs the claim is either irrelevant or already
        # covered by envelope.docs_confirmed from a prior turn.
        if sub_mode == "collect_base_docs" and not envelope.docs_confirmed:
            return False, GuardrailReason.DOCS_NOT_CONFIRMED_BY_TOOL.value
        return True, GuardrailReason.ALLOWED.value

    if claim_class == ClaimClass.IMAGES_SENT:
        if not envelope.images_sent:
            return False, GuardrailReason.IMAGES_NOT_SENT_BY_TOOL.value
        return True, GuardrailReason.ALLOWED.value

    if claim_class == ClaimClass.CASE_FINALIZED:
        # Task 2.3: Scope this hard-block to review_summary only.
        # finalizar_expediente() can only succeed from review_summary, so
        # blocking the claim in earlier sub-modes would always fire (envelope
        # is fresh each turn) and potentially hide legitimate closure text.
        if sub_mode == "review_summary" and not envelope.case_finalized:
            return False, GuardrailReason.CASE_NOT_FINALIZED_BY_TOOL.value
        return True, GuardrailReason.ALLOWED.value

    if claim_class == ClaimClass.COMPLETION_CLAIM:
        # Allow completion claims only if the confirming tool succeeded
        confirming_tools_by_sub_mode: dict[str, set[str]] = {
            "collect_element_data": {
                "completar_elemento_actual",
                "confirmar_fotos_elemento",
            },
            "collect_base_docs": {"confirmar_documentacion_base"},
            "collect_personal": {"actualizar_datos_expediente"},
            "collect_vehicle": {"actualizar_datos_expediente"},
            "collect_workshop": {"actualizar_datos_taller"},
            "review_summary": {"finalizar_expediente"},
        }
        required = confirming_tools_by_sub_mode.get(sub_mode, set())
        if required and not required.intersection(set(envelope.tools_succeeded)):
            return False, GuardrailReason.COMPLETION_NOT_CONFIRMED_BY_TOOL.value
        return True, GuardrailReason.ALLOWED.value

    if claim_class == ClaimClass.FIELD_CONFIRMED:
        if not envelope.field_saved:
            return False, GuardrailReason.FIELD_NOT_SAVED_BY_TOOL.value
        return True, GuardrailReason.ALLOWED.value

    if claim_class == ClaimClass.NEXT_STEP_DESCRIPTION:
        # Blocked when this is the first destination turn after a transition
        # AND the anti-anticipation guard is ON (managed by the caller).
        if (
            envelope.is_first_destination_turn
            and not envelope.allowed_transition_claims
        ):
            return False, GuardrailReason.ANTICIPATORY_NARRATION.value
        return True, GuardrailReason.ALLOWED.value

    # Unknown claim class — fail-open, log a warning
    logger.warning(
        "evaluate_claim_eligibility_unknown_class",
        claim_class=str(claim_class),
        sub_mode=sub_mode,
    )
    return True, GuardrailReason.NOT_APPLICABLE.value


# ---------------------------------------------------------------------------
# Kickoff truthfulness guard
# ---------------------------------------------------------------------------


def evaluate_kickoff_truthfulness(
    envelope: CertaintyEnvelope,
    sub_mode: str,
) -> tuple[bool, str]:
    """Check whether the kickoff guard should fire on a post-transition first turn.

    .. deprecated::
        This function is no longer called by any production code path.
        Step-number truthfulness is now enforced exclusively via prompt rules in
        ``agent/prompts/core/10_expediente_universal.md``.
        The function is retained here for import-safety only and will be removed
        in a future cleanup pass.

    This extends the existing ``_is_actionable_kickoff_response`` check.
    Returns (is_truthful, reason):
    - is_truthful=False means the kickoff response references stale-step content
      (e.g. narrating the PREVIOUS sub-mode's task when we're in the new one).

    Currently this is a conservative guard: it only blocks when
    ``is_first_destination_turn=True`` AND ``allowed_transition_claims=False``.
    The actual narrative content check is left to the existing kickoff regex
    (``_is_actionable_kickoff_response``).

    Args:
        envelope: Current turn's certainty envelope.
        sub_mode: Current (destination) sub-mode.

    Returns:
        (is_truthful: bool, reason: str)
    """
    warnings.warn(
        "evaluate_kickoff_truthfulness is deprecated and has no production callers. "
        "Step-number discipline is enforced by prompts/core/10_expediente_universal.md. "
        "Remove this function in the next cleanup pass.",
        DeprecationWarning,
        stacklevel=2,
    )
    if envelope.is_first_destination_turn and not envelope.allowed_transition_claims:
        return False, GuardrailReason.STALE_STEP_NARRATIVE.value
    return True, GuardrailReason.ALLOWED.value


# ---------------------------------------------------------------------------
# Structured log helper
# ---------------------------------------------------------------------------


def log_guardrail_triggered(
    *,
    reason: str,
    sub_mode: str,
    claim_class: str | None = None,
    tool_name: str | None = None,
    conversation_id: str | None = None,
    allowed: bool = False,
    extra: dict[str, Any] | None = None,
) -> None:
    """Emit a structured ``expediente_certainty_guard_triggered`` event.

    All guardrail outcomes (both blocks AND passes) are logged so that
    dashboards can compute block-rate by reason/sub-mode over time.

    Args:
        reason: GuardrailReason value string.
        sub_mode: Current expediente sub-mode.
        claim_class: ClaimClass value string (if applicable).
        tool_name: Tool that triggered the check (if applicable).
        conversation_id: Conversation ID for correlation.
        allowed: True when the check passed (reason=ALLOWED).
        extra: Additional fields to merge into the log event.
    """
    event: dict[str, Any] = {
        "guardrail_reason": reason,
        "sub_mode": sub_mode,
        "allowed": allowed,
    }
    if claim_class is not None:
        event["claim_class"] = claim_class
    if tool_name is not None:
        event["tool_name"] = tool_name
    if conversation_id is not None:
        event["conversation_id"] = conversation_id
    if extra:
        event.update(extra)

    if allowed:
        logger.debug("expediente_certainty_guard_triggered", **event)
    else:
        logger.warning("expediente_certainty_guard_triggered", **event)


# ---------------------------------------------------------------------------
# Mode context helpers
# ---------------------------------------------------------------------------


def persist_envelope(mode_context: dict[str, Any], envelope: CertaintyEnvelope) -> None:
    """Serialise the envelope into mode_context for Redis persistence.

    Call this at the end of each turn after accumulating all tool evidence.
    The key ``certainty_envelope`` is reserved for this module — do NOT write
    to it from other modules.
    """
    mode_context["certainty_envelope"] = envelope.to_dict()


def load_envelope(mode_context: dict[str, Any], sub_mode: str) -> CertaintyEnvelope:
    """Load the previous turn's envelope from mode_context, or return empty.

    Call this at the beginning of each turn to restore persisted certainty state.

    Note: The loaded envelope represents the PREVIOUS turn's confirmed state.
    It is intentionally separate from the CURRENT turn's accumulation (which
    starts fresh via ``CertaintyEnvelope.empty()``).

    Args:
        mode_context: Current mode context dict.
        sub_mode: Current sub-mode (used to initialise if no envelope found).

    Returns:
        Loaded envelope (from dict) or empty envelope.
    """
    raw = mode_context.get("certainty_envelope")
    if isinstance(raw, dict):
        try:
            return CertaintyEnvelope.from_dict(raw)
        except Exception as exc:
            logger.warning(
                "certainty_envelope_load_failed",
                error=str(exc),
                sub_mode=sub_mode,
            )
    return CertaintyEnvelope.empty(sub_mode=sub_mode)


def build_prompt_certainty_context(
    envelope: CertaintyEnvelope,
) -> dict[str, Any]:
    """Extract safe certainty fields for prompt injection.

    Returns a flat dict with only the fields the prompt loader needs.
    This deliberately hides internal envelope details to keep the prompt
    surface minimal.

    Returns:
        {
            "certainty_sub_mode": str,
            "certainty_allowed_transition_claims": bool,
            "certainty_blocked_claim_reason": str | None,
            "certainty_kickoff_required": bool,
        }
    """
    return {
        "certainty_sub_mode": envelope.sub_mode,
        "certainty_allowed_transition_claims": envelope.allowed_transition_claims,
        "certainty_blocked_claim_reason": envelope.blocked_claim_reason,
        "certainty_kickoff_required": envelope.kickoff_required,
    }
