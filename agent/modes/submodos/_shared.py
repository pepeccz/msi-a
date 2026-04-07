"""
Shared helpers extracted from expediente_mode.py (Phase A refactor).

Categories:
  1. Sub-mode constants (COLLECT_*, REVIEW_SUMMARY)
  2. Regex aliases (_PHOTO_COMPLETION_INTENT_RE)
  3. Step-map helpers (SUB_MODE_STEP, _SUBMODE_STEP_MAP, etc.)
  4. Taller domain guard constants/regex
  5. Element 7-state machine (ELEMENT_STATE_*, ELEMENT_STATES,
     _get_element_state, _set_element_state, _initialize_element_states)
   6. Progress/prefix helpers (EXPEDIENTE_STEP_PREFIX, _inject_step_prefix,
     _progress_prefix, _load_base_doc_descriptions)
  8. Anti-anticipation guard flag (_ANTI_ANTICIPATION_GUARD_ENABLED)
  9. Claim-gate regexes and _gate_response_claims
  10. Anti-repetition helpers (_check_anti_repetition, _store_turn_hash)
  11. Context-hydration (_hydrate_case_context_from_db,
      _resolve_element_display_names, _initialize_element_states)
  12. Field/retry helpers (_extract_field_keys_from_tool_result,
      _reset_validation_retry_state)
    13. Formatting helpers (_format_base_docs_kickoff,
      _build_element_photo_instructions)
  15. Transition update helpers (_build_transition_marker, _set_transition_updates)
      NOTE: _build_*_closure(), _TRANSITION_MATRIX, _ClosureBuilder removed
            (zero callers outside this file).
  16. Tool registry functions (_get_*_tools, _get_all_expediente_tools)
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, UTC
from typing import TYPE_CHECKING, Any

import structlog
from agent.services.expediente_constants import (
    CERT_SUPPLEMENT_EUR,
    STEP_LABELS,
    TOTAL_STEPS,
    step_prefix,
)

if TYPE_CHECKING:
    from database.models import Case, User
from agent.modes.expediente_guardrails import (
    CertaintyEnvelope,
    ClaimClass,
    evaluate_claim_eligibility,
    log_guardrail_triggered,
)
from agent.services.expediente_onboarding import (
    EXPEDIENTE_INTRO_MESSAGE,
    build_expediente_intro_confirmation,
    build_new_expediente_case_instructions,
    build_expediente_opening_overview,
    build_resume_expediente_case_instructions,
)
from agent.utils.expediente_types import CollectionStep
from agent.utils.validation import PHOTO_COMPLETION_INTENT_RE
from database.connection import get_async_session

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# __all__ — explicitly list all symbols so `from _shared import *` works for
# both public and private (underscore-prefixed) names.
# ---------------------------------------------------------------------------
__all__ = [
    # Sub-mode constants
    "MAX_TOOL_ITERATIONS",
    "COLLECT_ELEMENT_DATA",
    "COLLECT_BASE_DOCS",
    "COLLECT_PERSONAL",
    "COLLECT_VEHICLE",
    "COLLECT_WORKSHOP",
    "REVIEW_SUMMARY",
    # Regex aliases
    "_PHOTO_COMPLETION_INTENT_RE",
    # Step-map helpers
    "SUB_MODE_STEP",
    "_SUB_MODE_TO_COLLECTION_STEP",
    "_POST_BASE_DOCS_SUB_MODES",
    "_SUBMODE_STEP_MAP",
    # Context-hydration
    "_hydrate_case_context_from_db",
    # Element 7-state machine
    "ELEMENT_STATE_AWAITING_PHOTOS",
    "ELEMENT_STATE_PHOTOS_RECEIVED",
    "ELEMENT_STATE_CONFIRMING_PHOTOS",
    "ELEMENT_STATE_RETRY_PHOTOS",
    "ELEMENT_STATE_PHOTOS_CONFIRMED",
    "ELEMENT_STATE_DATA_COLLECTION",
    "ELEMENT_STATE_ELEMENT_COMPLETE",
    "ELEMENT_STATES",
    "_get_element_state",
    "_set_element_state",
    "_initialize_element_states",
    # Progress/prefix helpers
    "EXPEDIENTE_STEP_PREFIX",
    "_ANTI_ANTICIPATION_GUARD_ENABLED",
    "_inject_step_prefix",
    "_load_base_doc_descriptions",
    "_progress_prefix",
    # Anti-repetition helpers
    "_check_anti_repetition",
    "_store_turn_hash",
    # Display name resolution
    "_resolve_element_display_names",
    # Field/retry helpers
    "_extract_field_keys_from_tool_result",
    "_reset_validation_retry_state",
    # Formatting helpers
    "_format_base_docs_kickoff",
    "_build_element_photo_instructions",
    # Transition update helpers (closures deleted — zero external callers)
    "_build_transition_marker",
    "_set_transition_updates",
    # Tool registry functions
    "_get_element_data_tools",
    "_get_base_docs_tools",
    "_get_personal_tools",
    "_get_vehicle_tools",
    "_get_workshop_tools",
    "_get_review_tools",
    "_get_all_expediente_tools",
]

# ---------------------------------------------------------------------------
# 1. Sub-mode constants
# ---------------------------------------------------------------------------

# Max tool call iterations per turn
MAX_TOOL_ITERATIONS = 10

# Sub-mode constants (matching v1 CollectionStep names for easy tool recycling)
COLLECT_ELEMENT_DATA = "collect_element_data"
COLLECT_BASE_DOCS = "collect_base_docs"
COLLECT_PERSONAL = "collect_personal"
COLLECT_VEHICLE = "collect_vehicle"
COLLECT_WORKSHOP = "collect_workshop"
REVIEW_SUMMARY = "review_summary"

# ---------------------------------------------------------------------------
# 2. Regex aliases
# ---------------------------------------------------------------------------

# Photo-completion intent regex — canonical definition lives in
# agent/utils/validation.PHOTO_COMPLETION_INTENT_RE (imported above).
# Local alias for backward-compat with existing references in this file.
_PHOTO_COMPLETION_INTENT_RE = PHOTO_COMPLETION_INTENT_RE

# ---------------------------------------------------------------------------
# 3. Step-map helpers
# ---------------------------------------------------------------------------

# Sub-mode to step mapping for progress indicator — imported from canonical source.
# ``SUB_MODE_STEP`` is kept as an alias so that any internal references continue to
# work without a large-scale rename.  The single source of truth lives in
# ``agent.services.expediente_constants.STEP_LABELS``.
SUB_MODE_STEP = STEP_LABELS

_SUB_MODE_TO_COLLECTION_STEP: dict[str, str] = {
    COLLECT_ELEMENT_DATA: CollectionStep.COLLECT_ELEMENT_DATA.value,
    COLLECT_BASE_DOCS: CollectionStep.COLLECT_BASE_DOCS.value,
    COLLECT_PERSONAL: CollectionStep.COLLECT_PERSONAL.value,
    COLLECT_VEHICLE: CollectionStep.COLLECT_VEHICLE.value,
    COLLECT_WORKSHOP: CollectionStep.COLLECT_WORKSHOP.value,
    REVIEW_SUMMARY: CollectionStep.REVIEW_SUMMARY.value,
}

_POST_BASE_DOCS_SUB_MODES: frozenset[str] = frozenset(
    {
        COLLECT_PERSONAL,
        COLLECT_VEHICLE,
        COLLECT_WORKSHOP,
        REVIEW_SUMMARY,
    }
)

# Maps sub-mode names to their "Paso X/6" step number for the phase
# truthfulness guard (Fix C).  Derived from STEP_LABELS so there is a
# single source of truth — any change to the canonical order in
# agent.services.expediente_constants is automatically reflected here.
_SUBMODE_STEP_MAP: dict[str, int] = {
    sub_mode: entry[0] for sub_mode, entry in STEP_LABELS.items()
}

# ---------------------------------------------------------------------------
# 5. Context-hydration helper
# ---------------------------------------------------------------------------


async def _hydrate_case_context_from_db(
    case: "Case",
    user: "User | None",
    inferred_sub_mode: str,
) -> dict[str, Any]:
    """Hydrate persisted expediente data into mode_context/FSM-compatible keys."""
    try:
        personal_data: dict[str, str | None] = {}
        if user and any(
            [
                user.first_name,
                user.nif_cif,
                user.email,
                user.domicilio_calle,
            ]
        ):
            personal_data = {
                "nombre": user.first_name,
                "apellidos": user.last_name,
                "dni_cif": user.nif_cif,
                "email": user.email,
                "telefono": None,
                "domicilio_calle": user.domicilio_calle,
                "domicilio_localidad": user.domicilio_localidad,
                "domicilio_provincia": user.domicilio_provincia,
                "domicilio_cp": user.domicilio_cp,
                "itv_nombre": None,
            }

        vehicle_data_raw: dict[str, str | None] = {
            "marca": case.vehiculo_marca,
            "modelo": case.vehiculo_modelo,
            "anio": str(case.vehiculo_anio) if case.vehiculo_anio is not None else None,
            "matricula": case.vehiculo_matricula,
            "bastidor": case.vehiculo_bastidor,
        }
        vehicle_data = vehicle_data_raw if any(vehicle_data_raw.values()) else {}

        taller_propio = case.taller_propio
        taller_data: dict[str, str | None] | None = None
        if taller_propio is True:
            taller_data_raw = {
                "nombre": case.taller_nombre,
                "responsable": case.taller_responsable,
                "domicilio": case.taller_domicilio,
                "provincia": case.taller_provincia,
                "ciudad": case.taller_ciudad,
                "telefono": case.taller_telefono,
                "registro_industrial": case.taller_registro_industrial,
                "actividad": case.taller_actividad,
            }
            if any(taller_data_raw.values()):
                taller_data = taller_data_raw

        base_docs_received = inferred_sub_mode in _POST_BASE_DOCS_SUB_MODES or any(
            image.image_type == "base_documentation" for image in (case.images or [])
        )

        return {
            "personal_data": personal_data,
            "vehicle_data": vehicle_data,
            "taller_propio": taller_propio,
            "taller_data": taller_data,
            "base_docs_received": base_docs_received,
            "fsm_step": _SUB_MODE_TO_COLLECTION_STEP.get(
                inferred_sub_mode,
                CollectionStep.COLLECT_ELEMENT_DATA.value,
            ),
        }
    except Exception as exc:
        logger.warning(
            "hydrate_case_context_from_db_failed",
            case_id=str(getattr(case, "id", "unknown")),
            inferred_sub_mode=inferred_sub_mode,
            error=str(exc),
        )
        return {}


# ---------------------------------------------------------------------------
# 6. Element 7-state machine
# ---------------------------------------------------------------------------
# Canonical states for each element stored in mode_context["element_states"].
# Stored as: { element_code: { "state": <state_str>, "photos_count": int, "data_complete": bool } }

ELEMENT_STATE_AWAITING_PHOTOS = "awaiting_photos"
ELEMENT_STATE_PHOTOS_RECEIVED = "photos_received"
ELEMENT_STATE_CONFIRMING_PHOTOS = "confirming_photos"
ELEMENT_STATE_RETRY_PHOTOS = "retry_photos"
ELEMENT_STATE_PHOTOS_CONFIRMED = "photos_confirmed"
ELEMENT_STATE_DATA_COLLECTION = "data_collection"
ELEMENT_STATE_ELEMENT_COMPLETE = "element_complete"

# All valid element states (for validation)
ELEMENT_STATES: frozenset[str] = frozenset(
    {
        ELEMENT_STATE_AWAITING_PHOTOS,
        ELEMENT_STATE_PHOTOS_RECEIVED,
        ELEMENT_STATE_CONFIRMING_PHOTOS,
        ELEMENT_STATE_RETRY_PHOTOS,
        ELEMENT_STATE_PHOTOS_CONFIRMED,
        ELEMENT_STATE_DATA_COLLECTION,
        ELEMENT_STATE_ELEMENT_COMPLETE,
    }
)


def _get_element_state(
    mode_context: dict[str, Any],
    element_code: str,
) -> str:
    """
    Return the current 7-state machine state for a given element.

    Reads from mode_context["element_states"][element_code]["state"].
    Falls back to deriving state from legacy flags when element_states
    is absent or the element has no entry — preserves backward compatibility
    with checkpoints created before EXPEDIENTE_V2_ENABLED was set.

    Args:
        mode_context: Current mode context dict (read-only).
        element_code: Element code (e.g. "ESCAPE").

    Returns:
        One of the ELEMENT_STATE_* constants (string).
    """
    element_states: dict[str, Any] = mode_context.get("element_states") or {}
    entry = element_states.get(element_code)
    if isinstance(entry, dict) and entry.get("state") in ELEMENT_STATES:
        return entry["state"]

    # Backward-compatible derivation from legacy flags
    element_data_status: dict[str, str] = mode_context.get("element_data_status") or {}
    legacy_status = element_data_status.get(element_code, "pending_photos")
    if legacy_status == "completed":
        return ELEMENT_STATE_ELEMENT_COMPLETE
    if legacy_status == "pending_data":
        return ELEMENT_STATE_DATA_COLLECTION
    # pending_photos or missing → check element_phase for current element
    current_code = (
        (mode_context.get("element_codes") or [])[
            mode_context.get("current_element_index", 0)
        ]
        if mode_context.get("element_codes")
        else None
    )
    if element_code == current_code:
        phase = mode_context.get("element_phase", "photos")
        if phase == "data":
            return ELEMENT_STATE_DATA_COLLECTION
    return ELEMENT_STATE_AWAITING_PHOTOS


def _set_element_state(
    mode_context: dict[str, Any],
    element_code: str,
    state: str,
    *,
    photos_count: int | None = None,
    data_complete: bool | None = None,
) -> None:
    """
    Update the 7-state machine entry for a given element in mode_context.

    Mutates mode_context["element_states"] in-place.  Creates the dict
    and the per-element entry if they do not yet exist.  Only fields
    explicitly provided (non-None) are written — existing values are
    preserved for omitted fields.

    Args:
        mode_context: Current mode context dict (mutated in-place).
        element_code: Element code (e.g. "ESCAPE").
        state: Target state — must be one of ELEMENT_STATE_* constants.
        photos_count: Optional update for photos_count in the entry.
        data_complete: Optional update for data_complete flag in the entry.
    """
    if state not in ELEMENT_STATES:
        logger.warning(
            "invalid_element_state",
            element_code=element_code,
            state=state,
            valid_states=list(ELEMENT_STATES),
        )
        return

    if "element_states" not in mode_context or not isinstance(
        mode_context["element_states"], dict
    ):
        mode_context["element_states"] = {}

    existing: dict[str, Any] = mode_context["element_states"].get(element_code) or {}
    entry: dict[str, Any] = {
        "state": state,
        "photos_count": existing.get("photos_count", 0),
        "data_complete": existing.get("data_complete", False),
    }
    if photos_count is not None:
        entry["photos_count"] = photos_count
    if data_complete is not None:
        entry["data_complete"] = data_complete

    mode_context["element_states"][element_code] = entry
    logger.debug(
        "element_state_updated",
        element_code=element_code,
        state=state,
        photos_count=entry["photos_count"],
        data_complete=entry["data_complete"],
    )


def _initialize_element_states(
    mode_context: dict[str, Any],
    element_codes: list[str],
) -> None:
    """
    Initialize element_states for all elements entering COLLECT_ELEMENT_DATA.

    Called once when the 7-state machine is first activated.  Existing entries
    are preserved — only elements without an entry are initialised to
    "awaiting_photos" to support recovery paths where some elements are
    already complete.

    Args:
        mode_context: Current mode context dict (mutated in-place).
        element_codes: Ordered list of element codes in this expediente.
    """
    if not element_codes:
        return

    if "element_states" not in mode_context or not isinstance(
        mode_context["element_states"], dict
    ):
        mode_context["element_states"] = {}

    # Derive initial state from legacy element_data_status if available.
    # This handles re-entry where some elements may already be completed.
    element_data_status: dict[str, str] = mode_context.get("element_data_status") or {}

    for code in element_codes:
        if code in mode_context["element_states"]:
            continue  # Already initialised — don't overwrite

        legacy_status = element_data_status.get(code, "pending_photos")
        if legacy_status == "completed":
            initial_state = ELEMENT_STATE_ELEMENT_COMPLETE
            data_complete = True
        elif legacy_status == "pending_data":
            initial_state = ELEMENT_STATE_DATA_COLLECTION
            data_complete = False
        else:
            initial_state = ELEMENT_STATE_AWAITING_PHOTOS
            data_complete = False

        mode_context["element_states"][code] = {
            "state": initial_state,
            "photos_count": 0,
            "data_complete": data_complete,
        }

    logger.debug(
        "element_states_initialized",
        element_count=len(element_codes),
        states={c: mode_context["element_states"][c]["state"] for c in element_codes},
    )


# ---------------------------------------------------------------------------
# 8. Progress/prefix helpers
# ---------------------------------------------------------------------------

# Sub-mode to step label map used by _inject_step_prefix (TASK-06)
# Derived from the canonical ``STEP_LABELS`` in ``agent.services.expediente_constants``
# so that labels are defined in exactly one place.
EXPEDIENTE_STEP_PREFIX: dict[str, str] = {key: step_prefix(key) for key in STEP_LABELS}

# ---------------------------------------------------------------------------
# 9. Anti-anticipation guard flag
# ---------------------------------------------------------------------------
# When True, transition closure messages are trimmed to "Pasamos al paso X"
# without describing the next step's requirements.  The receiving sub-mode
# handler is responsible for introducing its own instructions on the next turn.
_ANTI_ANTICIPATION_GUARD_ENABLED: bool = True

# Canonical introductory overview message sent ONCE when EXPEDIENTE_MODE
# is first entered (case just created). Re-exported from the onboarding service.


def _inject_step_prefix(message: str, sub_mode: str) -> str:
    """
    Prepend the '📍 Paso X/6 — [Step Name]' progress prefix to a message.

    Idempotent: if the message already starts with '📍 Paso', it is returned
    unchanged.  Returns the original message unchanged when sub_mode has no
    registered prefix (e.g. unknown or empty string).

    This helper is intentionally module-level so it can be unit-tested
    independently from ExpedienteModeNode.

    Args:
        message: The user-facing bot message string.
        sub_mode: Lower-case sub-mode constant (e.g. "collect_personal").

    Returns:
        Message with prefix prepended, or the original message if prefix
        cannot be determined or message is already prefixed.
    """
    if not message:
        return message

    # Idempotency guard — never double-prefix
    if message.startswith("📍 Paso"):
        return message

    prefix = EXPEDIENTE_STEP_PREFIX.get(sub_mode, "")
    if not prefix:
        return message

    return f"{prefix}\n\n{message}"


async def _load_base_doc_descriptions(
    category_slug: str,
) -> tuple[list[str], dict | None]:
    """
    Load base_doc_descriptions and category_data from DB/cache.

    Uses tarifa_service (Redis-cached, TTL=300s) to avoid redundant DB hits.
    All re-entry paths call this instead of duplicating the try/except block.

    Returns:
        (descriptions, category_data_dict) on success.
        ([], None) on any error — logs a warning, never raises.
    """
    try:
        from agent.services.tarifa_service import get_tarifa_service

        tarifa_service = get_tarifa_service()
        category_data = await tarifa_service.get_category_data(category_slug)
        if category_data and category_data.get("base_documentation"):
            descriptions = [
                bd["description"] for bd in category_data["base_documentation"]
            ]
            return descriptions, category_data
        return [], category_data
    except Exception as e:
        logger.warning(
            "load_base_doc_descriptions_failed",
            category_slug=category_slug,
            error=str(e),
        )
        return [], None


def _progress_prefix(sub_mode: str) -> str:
    """Return deterministic progress prefix for a given sub-mode.

    Delegates to the canonical ``step_prefix()`` helper in
    ``agent.services.expediente_constants`` so labels are defined in one place.
    """
    return step_prefix(sub_mode)


# ---------------------------------------------------------------------------
# 11. Anti-repetition helpers
# ---------------------------------------------------------------------------


def _check_anti_repetition(
    message: str,
    mode_context: dict[str, Any],
) -> str:
    """
    Check if the message is a repeat of a recent assistant turn and reformulate.

    Computes the MD5 hash of the message and compares it against the last 2
    hashes stored in mode_context["_last_agent_turns"] (FIFO list, max 2).
    If a match is found, prepends "Para recordarte: " to the message.

    This check is O(1) — no LLM call required.

    Args:
        message: The final assembled assistant message (post-content generation).
        mode_context: Current mode context dict (read-only in this function).

    Returns:
        Original message if not a repeat; "Para recordarte: " + message otherwise.
    """
    if not message:
        return message

    current_hash = hashlib.md5(message.encode()).hexdigest()
    last_turns: list[str] = mode_context.get("_last_agent_turns") or []

    if current_hash in last_turns:
        return f"Para recordarte: {message}"
    return message


def _store_turn_hash(
    message: str,
    mode_context: dict[str, Any],
) -> None:
    """
    Store the MD5 hash of the sent message in mode_context["_last_agent_turns"].

    Maintains a FIFO list of at most 2 hashes. This function mutates
    mode_context in-place; the caller must persist the updated context.

    Args:
        message: The final message that was sent to the user.
        mode_context: Current mode context dict (mutated in-place).
    """
    if not message:
        return

    current_hash = hashlib.md5(message.encode()).hexdigest()
    last_turns: list[str] = list(mode_context.get("_last_agent_turns") or [])

    last_turns.append(current_hash)
    # Keep at most 2 entries (FIFO)
    if len(last_turns) > 2:
        last_turns = last_turns[-2:]

    mode_context["_last_agent_turns"] = last_turns


# ---------------------------------------------------------------------------
# 12. Display name resolution
# ---------------------------------------------------------------------------


async def _resolve_element_display_names(
    element_codes: list[str],
    category_id: str,
) -> dict[str, str]:
    """
    Batch-resolve element codes to human-readable display names.

    Performs a **single** SELECT query against the ``elements`` table for all
    codes in one round-trip (no N+1 queries).  This is the R1 fix for the
    ID-leak defect: internal element codes (e.g. "PLACA_SOLAR_REGULADOR_INTERIOR")
    MUST NOT surface in any user-facing text.  Call this function once at
    case-creation time and store the result in
    ``mode_context["element_display_names"]``.  Every render site should then
    use ``display_names.get(code, code)`` so that old Redis checkpoints (which
    lack the key) fall back gracefully to the raw code.

    Args:
        element_codes: List of element code strings to resolve
            (e.g. ``["ESCAPE", "MANILLAR"]``).  An empty list causes an
            immediate early-return without touching the database.
        category_id: UUID string of the vehicle category used as an
            additional filter (together with ``is_active``) to avoid
            returning display names from a different category that happens
            to reuse the same code.

    Returns:
        ``dict[str, str]`` mapping ``code → element.name`` for every code
        found in the DB.  Codes not present in the DB are simply absent from
        the returned dict (the caller's ``dict.get(code, code)`` fallback
        handles this transparently).  Returns an empty dict ``{}`` in two
        special cases:

        * ``element_codes`` is empty — early-return, no DB query issued.
        * Any DB/network error occurs — exception is caught, logged at
          WARNING level as ``resolve_element_display_names_failed``, and
          ``{}`` is returned so the caller can continue without crashing.

    Error behavior:
        The function intentionally swallows **all** exceptions.  Callers
        MUST be written to handle ``{}`` as a valid (though degraded) result.
        The raw code is still readable by staff even if the DB is unavailable.
    """
    if not element_codes:
        return {}

    try:
        import uuid as _uuid
        from database.models import Element
        from sqlalchemy import select

        async with get_async_session() as session:
            result = await session.execute(
                select(Element.code, Element.name).where(
                    Element.code.in_(element_codes),
                    Element.category_id == _uuid.UUID(str(category_id)),
                    Element.is_active.is_(True),
                )
            )
            rows = result.all()
            return {row.code: row.name for row in rows}

    except Exception as e:
        logger.warning(
            "resolve_element_display_names_failed",
            element_codes=element_codes,
            category_id=category_id,
            error=str(e),
        )
        return {}


# ---------------------------------------------------------------------------
# 13. Field/retry helpers
# ---------------------------------------------------------------------------


def _extract_field_keys_from_tool_result(
    data: dict[str, Any],
) -> list[dict[str, Any]] | None:
    """
    Extract field_key info from tool results generically.

    Works with any tool that returns field information (confirmar_fotos_elemento,
    obtener_campos_elemento, guardar_datos_elemento).  Returns a compact list
    of dicts with ``field_key``, ``field_label``, ``instruction``, ``example``,
    and ``options`` so the prompt loader can inject them into the system prompt
    without duplicating business logic.

    Looks for fields in these locations (in priority order):
    1. ``data["fields"]`` — list of field dicts from obtener_campos_elemento / batch mode
    2. ``data["current_field"]`` — single field dict from sequential mode
    """
    field_keys: list[dict[str, Any]] = []
    seen: set[str] = set()

    # Source 1: explicit "fields" array (obtener_campos_elemento, batch/hybrid mode)
    fields_list = data.get("fields")
    if isinstance(fields_list, list):
        for f in fields_list:
            if isinstance(f, dict) and "field_key" in f:
                fk = f["field_key"]
                if fk not in seen:
                    seen.add(fk)
                    field_keys.append(
                        {
                            "field_key": fk,
                            "field_label": f.get("field_label", fk),
                            "instruction": f.get("instruction", None),
                            "example": f.get("example", None),
                            "options": f.get("options", None),
                        }
                    )

    # Source 2: sequential mode "current_field"
    current_field = data.get("current_field")
    if isinstance(current_field, dict) and "field_key" in current_field:
        fk = current_field["field_key"]
        if fk not in seen:
            seen.add(fk)
            field_keys.append(
                {
                    "field_key": fk,
                    "field_label": current_field.get("field_label", fk),
                    "instruction": current_field.get("instruction", None),
                    "example": current_field.get("example", None),
                    "options": current_field.get("options", None),
                }
            )

    return field_keys if field_keys else None


def _reset_validation_retry_state(retry_state: dict) -> dict:
    """
    Partial reset of retry_state after a successful tool call.
    Resets validation-specific counters while preserving consecutive_errors
    (which drives the outer escalation logic in BaseModeNode.process()).
    """
    return {
        **retry_state,
        "retry_count": 0,
        "last_validation_context": None,
        "last_error_type": None,
        "last_error_message": None,
    }


# ---------------------------------------------------------------------------
# 14. Formatting helpers
# ---------------------------------------------------------------------------


def _format_base_docs_kickoff(base_documentation: list[dict[str, Any]]) -> str:
    """
    Format base_documentation as a numbered list for the kickoff message.

    base_documentation comes from mode_context["category_data"]["base_documentation"].
    Each item should include a user-facing "description".
    Falls back to a generic message if the list is empty.
    """
    valid: list[str] = []
    for item in base_documentation:
        if not isinstance(item, dict):
            continue
        desc = item.get("description")
        if isinstance(desc, str) and desc.strip():
            valid.append(desc)

    if not valid:
        return "Enviame las fotos de los documentos base del vehiculo."
    lines = [f"{i}. {desc}" for i, desc in enumerate(valid, start=1)]
    return "\n".join(lines)


def _build_element_photo_instructions(tarifa_calculada: Any) -> str:
    """
    Build per-element photo instructions from tarifa_calculada for case_instructions.

    Extracts element photo requirements from ``tarifa_calculada.documentacion.elementos``
    and formats them as imperative instructions for the LLM system prompt.

    Returns an empty string if tarifa_calculada is None, missing, or has no
    photo instruction data — this is fully defensive (no exceptions propagate).

    Args:
        tarifa_calculada: The full tarifa_calculada dict (or JSON string) from mode_context.

    Returns:
        A formatted string block ready to be appended to case_instructions,
        or an empty string when no data is available.
    """
    if tarifa_calculada is None:
        return ""

    try:
        # Normalise to dict (tools may return JSON strings)
        if isinstance(tarifa_calculada, str):
            import json as _json

            try:
                tarifa_calculada = _json.loads(tarifa_calculada)
            except (ValueError, TypeError):
                return ""

        if not isinstance(tarifa_calculada, dict):
            return ""

        doc_elementos = tarifa_calculada.get("documentacion", {}).get("elementos")
        if not isinstance(doc_elementos, list) or not doc_elementos:
            return ""

        lines: list[str] = []
        for elem in doc_elementos:
            if not isinstance(elem, dict):
                continue

            nombre = (
                elem.get("nombre") or elem.get("name") or elem.get("codigo", "Elemento")
            )
            imagenes = elem.get("imagenes", [])

            # Collect user_instruction texts from required/all images
            instructions: list[str] = []
            if isinstance(imagenes, list):
                for img in imagenes:
                    if not isinstance(img, dict):
                        continue
                    instr = img.get("instruccion_usuario") or img.get(
                        "user_instruction", ""
                    )
                    if instr and isinstance(instr, str) and instr.strip():
                        instructions.append(instr.strip())

            if instructions:
                lines.append(f"- {nombre}: {'; '.join(instructions)}")
            else:
                lines.append(f"- {nombre}")

        if not lines:
            return ""

        photo_block = (
            "\n\nINSTRUCCIONES ESPECÍFICAS PARA ESTE EXPEDIENTE:\n\n"
            "Elementos a fotografiar:\n"
            + "\n".join(lines)
            + "\n\nFORMATO: Pide siempre que el cliente envíe las fotos como imagen "
            "(no como documento adjunto)."
        )
        return photo_block

    except Exception:
        # Fully defensive: never propagate exceptions from this helper
        return ""


# ---------------------------------------------------------------------------
# 15. Transition update helpers
# ---------------------------------------------------------------------------
# NOTE: _build_*_closure(), _ClosureBuilder, _TRANSITION_MATRIX and related
# builder functions were removed — they had zero callers outside _shared.py.
# _build_transition_marker and _set_transition_updates are kept because
# expediente_mode.py calls _set_transition_updates at 6 call sites.


def _build_transition_marker(
    *,
    from_sub_mode: str,
    to_sub_mode: str,
    tool_name: str,
) -> dict[str, Any]:
    """Build structured marker for internal expediente handoff continuity."""
    return {
        "from_sub_mode": from_sub_mode,
        "to_sub_mode": to_sub_mode,
        "tool_name": tool_name,
        "requires_kickoff": True,
        "created_at": datetime.now(UTC).isoformat(),
    }


def _set_transition_updates(
    *,
    updates: dict[str, Any],
    from_sub_mode: str,
    to_sub_mode: str,
    tool_name: str,
) -> None:
    """Apply transition fields with legacy + structured marker compatibility."""
    updates["expediente_sub_mode"] = to_sub_mode
    updates["just_transitioned_from"] = from_sub_mode
    updates["expediente_transition_marker"] = _build_transition_marker(
        from_sub_mode=from_sub_mode,
        to_sub_mode=to_sub_mode,
        tool_name=tool_name,
    )


# ---------------------------------------------------------------------------
# 16. Tool registry functions
# ---------------------------------------------------------------------------


def _get_element_data_tools() -> list:
    """Tools for COLLECT_ELEMENT_DATA sub-mode."""
    from agent.tools.element_data_tools import (
        obtener_campos_elemento,
        guardar_datos_elemento,
        confirmar_fotos_elemento,
        completar_elemento_actual,
        obtener_progreso_elementos,
        reenviar_imagenes_elemento,
    )
    from agent.tools.image_tools import enviar_imagenes_ejemplo
    from agent.tools.case_tools import (
        consulta_durante_expediente,
        obtener_estado_expediente,
        cancelar_expediente,
    )
    from agent.tools.shared_tools import escalar_a_humano

    return [
        # Element data collection
        obtener_campos_elemento,
        guardar_datos_elemento,
        confirmar_fotos_elemento,
        completar_elemento_actual,
        obtener_progreso_elementos,
        reenviar_imagenes_elemento,
        # Images
        enviar_imagenes_ejemplo,
        # Case management
        consulta_durante_expediente,
        obtener_estado_expediente,
        cancelar_expediente,
        # Universal
        escalar_a_humano,
    ]


def _get_base_docs_tools() -> list:
    """Tools for COLLECT_BASE_DOCS sub-mode."""
    from agent.tools.element_data_tools import confirmar_documentacion_base
    from agent.tools.image_tools import enviar_imagenes_ejemplo
    from agent.tools.case_tools import (
        consulta_durante_expediente,
        obtener_estado_expediente,
        cancelar_expediente,
    )
    from agent.tools.shared_tools import escalar_a_humano

    return [
        confirmar_documentacion_base,
        enviar_imagenes_ejemplo,
        consulta_durante_expediente,
        obtener_estado_expediente,
        cancelar_expediente,
        escalar_a_humano,
    ]


def _get_personal_tools() -> list:
    """Tools for COLLECT_PERSONAL sub-mode."""
    from agent.tools.case_tools import (
        actualizar_datos_expediente,
        consulta_durante_expediente,
        obtener_estado_expediente,
        cancelar_expediente,
    )
    from agent.tools.shared_tools import escalar_a_humano

    return [
        actualizar_datos_expediente,
        consulta_durante_expediente,
        obtener_estado_expediente,
        cancelar_expediente,
        escalar_a_humano,
    ]


def _get_vehicle_tools() -> list:
    """Tools for COLLECT_VEHICLE sub-mode."""
    from agent.tools.case_tools import (
        actualizar_datos_expediente,
        consulta_durante_expediente,
        obtener_estado_expediente,
        cancelar_expediente,
    )
    from agent.tools.shared_tools import escalar_a_humano

    return [
        actualizar_datos_expediente,
        consulta_durante_expediente,
        obtener_estado_expediente,
        cancelar_expediente,
        escalar_a_humano,
    ]


def _get_workshop_tools() -> list:
    """Tools for COLLECT_WORKSHOP sub-mode."""
    from agent.tools.case_tools import (
        actualizar_datos_taller,
        consulta_durante_expediente,
        obtener_estado_expediente,
        cancelar_expediente,
    )
    from agent.tools.shared_tools import escalar_a_humano

    return [
        actualizar_datos_taller,
        consulta_durante_expediente,
        obtener_estado_expediente,
        cancelar_expediente,
        escalar_a_humano,
    ]


def _get_review_tools() -> list:
    """Tools for REVIEW_SUMMARY sub-mode."""
    from agent.tools.case_tools import (
        finalizar_expediente,
        editar_expediente,
        consulta_durante_expediente,
        obtener_estado_expediente,
    )
    from agent.tools.shared_tools import escalar_a_humano

    return [
        finalizar_expediente,
        editar_expediente,
        consulta_durante_expediente,
        obtener_estado_expediente,
        escalar_a_humano,
    ]


def _get_all_expediente_tools() -> list:
    """Get all expediente tools (for reference)."""
    # Combine all sub-mode tools (removing duplicates)
    all_tools_nested = [
        _get_element_data_tools(),
        _get_base_docs_tools(),
        _get_personal_tools(),
        _get_vehicle_tools(),
        _get_workshop_tools(),
        _get_review_tools(),
    ]

    # Flatten and deduplicate by tool name
    seen_names: set[str] = set()
    all_tools: list = []
    for tool_list in all_tools_nested:
        for tool in tool_list:
            if tool.name not in seen_names:
                seen_names.add(tool.name)
                all_tools.append(tool)

    return all_tools
