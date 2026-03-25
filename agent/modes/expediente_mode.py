"""
MSI-a - EXPEDIENTE_MODE Node.

Formal case collection mode for homologation expedientes.
This is the most complex mode with 6 sub-modes.

Flow:
    1. COLLECT_ELEMENT_DATA (per element: photos → data)
    2. COLLECT_BASE_DOCS (ficha técnica, permiso, vistas)
    3. COLLECT_PERSONAL (nombre, DNI, email, domicilio, etc.)
    4. COLLECT_VEHICLE (marca, modelo, matrícula, bastidor)
    5. COLLECT_WORKSHOP (optional if taller_propio=True)
    6. REVIEW_SUMMARY (final confirmation)

Architecture:
    - Sub-mode stored in mode_context["expediente_sub_mode"]
    - LLM-driven within each sub-mode (like other modes)
    - Tools recycled from v1 (element_data_tools, case_tools)
    - Digressions BLOCKED (only escalation allowed)

Sub-mode switching:
    Tools like completar_elemento_actual() return updates to
    expediente_sub_mode, causing next invocation to route to new handler.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, UTC
from typing import TYPE_CHECKING, Any, cast

import structlog
from langchain_openai import ChatOpenAI

from agent.modes.base_mode import BaseModeNode
from agent.services.expediente_constants import (
    STEP_LABELS,
    TOTAL_STEPS,
    step_prefix,
)

if TYPE_CHECKING:
    from agent.services.element_state_service import ElementStateService
    from agent.services.intent_classifier import IntentClassifier
    from database.models import Case, User
from agent.modes.presupuesto_mode import _apply_tool_flags
from agent.services.expediente_onboarding import (
    EXPEDIENTE_INTRO_MESSAGE,
    build_expediente_intro_confirmation,
    build_new_expediente_case_instructions,
    build_expediente_opening_overview,
    build_resume_expediente_case_instructions,
)
from agent.services.case_image_batch_service import get_case_image_batch_service
from agent.utils.expediente_transition_adapter import canonicalize_transition
from agent.modes.expediente_guardrails import (
    CertaintyEnvelope,
    ClaimClass,
    normalize_tool_payload,
    evaluate_progression_eligibility,
    evaluate_claim_eligibility,
    evaluate_kickoff_truthfulness,
    log_guardrail_triggered,
    persist_envelope,
    load_envelope,
    build_prompt_certainty_context,
)
from agent.state.conversation_state import ConversationState, create_empty_retry_state
from agent.prompts.loader import assemble_system_prompt
from agent.state.helpers import (
    format_messages_for_llm,
    set_current_state,
    clear_current_state,
)
from agent.tools.image_tools import (
    set_current_state_for_image_tools,
    clear_image_tools_state,
)
from agent.utils.expediente_types import CollectionStep
from agent.utils.validation import PHOTO_COMPLETION_INTENT_RE
from database.connection import get_async_session
from shared.config import get_settings

logger = structlog.get_logger(__name__)

# Max tool call iterations per turn
MAX_TOOL_ITERATIONS = 10

# Sub-mode constants (matching v1 CollectionStep names for easy tool recycling)
COLLECT_ELEMENT_DATA = "collect_element_data"
COLLECT_BASE_DOCS = "collect_base_docs"
COLLECT_PERSONAL = "collect_personal"
COLLECT_VEHICLE = "collect_vehicle"
COLLECT_WORKSHOP = "collect_workshop"
REVIEW_SUMMARY = "review_summary"

# Photo-completion intent regex — canonical definition lives in
# agent/utils/validation.PHOTO_COMPLETION_INTENT_RE (imported above).
# Local alias for backward-compat with existing references in this file.
_PHOTO_COMPLETION_INTENT_RE = PHOTO_COMPLETION_INTENT_RE

# Sub-mode to step mapping for progress indicator — imported from canonical source.
# ``SUB_MODE_STEP`` is kept as an alias so that any internal references continue to
# work without a large-scale rename.  The single source of truth lives in
# ``agent.services.expediente_constants.STEP_LABELS``.
SUB_MODE_STEP = STEP_LABELS

_SUB_MODE_TO_FSM_STEP: dict[str, str] = {
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
            "fsm_step": _SUB_MODE_TO_FSM_STEP.get(
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
# TASK-05: 7-state per-element state machine (EXPEDIENTE_V2_ENABLED only)
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

# ---------------------------------------------------------------------------
# TASK-08: Phase-aware tool allow/block matrix (EXPEDIENTE_V2_ENABLED only)
# ---------------------------------------------------------------------------
# Maps (sub_mode, element_phase) → {"allowed": [...], "blocked": [...]}
# element_phase is None for sub-modes that don't use the per-element phase.
# Used by _is_tool_blocked() to enforce declarative tool access control
# before _execute_and_log_tool() is called in _run_llm_loop.
#
# Safety override: escalar_a_humano is NEVER blocked regardless of matrix
# (enforced inside _is_tool_blocked, not in the matrix itself).
EXPEDIENTE_TOOL_MATRIX: dict[
    tuple[str, str | None],
    dict[str, list[str]],
] = {
    # COLLECT_ELEMENT_DATA — photos phase: only photo-related tools allowed
    ("collect_element_data", "photos"): {
        "allowed": [
            "enviar_imagenes_ejemplo",
            "confirmar_fotos_elemento",
            "reenviar_imagenes_elemento",
            "consulta_durante_expediente",
            "obtener_estado_expediente",
            "cancelar_expediente",
            "escalar_a_humano",
        ],
        "blocked": [
            "guardar_datos_elemento",
            "completar_elemento_actual",
        ],
    },
    # COLLECT_ELEMENT_DATA — data phase: only data-collection tools allowed
    ("collect_element_data", "data"): {
        "allowed": [
            "obtener_campos_elemento",
            "guardar_datos_elemento",
            "completar_elemento_actual",
            "obtener_progreso_elementos",
            "consulta_durante_expediente",
            "obtener_estado_expediente",
            "cancelar_expediente",
            "escalar_a_humano",
        ],
        "blocked": [
            "confirmar_fotos_elemento",
        ],
    },
    # COLLECT_BASE_DOCS: base doc tools only
    ("collect_base_docs", None): {
        "allowed": [
            "confirmar_documentacion_base",
            "enviar_imagenes_ejemplo",
            "consulta_durante_expediente",
            "obtener_estado_expediente",
            "cancelar_expediente",
            "escalar_a_humano",
        ],
        "blocked": [
            "guardar_datos_elemento",
            "completar_elemento_actual",
            "confirmar_fotos_elemento",
        ],
    },
    # COLLECT_PERSONAL: personal data tools only
    ("collect_personal", None): {
        "allowed": [
            "actualizar_datos_expediente",
            "consulta_durante_expediente",
            "obtener_estado_expediente",
            "cancelar_expediente",
            "escalar_a_humano",
        ],
        "blocked": [
            "guardar_datos_elemento",
            "confirmar_fotos_elemento",
        ],
    },
    # COLLECT_VEHICLE: vehicle data tools only
    ("collect_vehicle", None): {
        "allowed": [
            "actualizar_datos_expediente",
            "consulta_durante_expediente",
            "obtener_estado_expediente",
            "cancelar_expediente",
            "escalar_a_humano",
        ],
        "blocked": [
            "guardar_datos_elemento",
            "confirmar_fotos_elemento",
        ],
    },
    # COLLECT_WORKSHOP: workshop tools only
    ("collect_workshop", None): {
        "allowed": [
            "actualizar_datos_taller",
            "consulta_durante_expediente",
            "obtener_estado_expediente",
            "cancelar_expediente",
            "escalar_a_humano",
        ],
        "blocked": [
            "guardar_datos_elemento",
            "confirmar_fotos_elemento",
            "actualizar_datos_expediente",
        ],
    },
    # REVIEW_SUMMARY: only final-step tools; cancel is blocked (too late)
    ("review_summary", None): {
        "allowed": [
            "finalizar_expediente",
            "editar_expediente",
            "obtener_estado_expediente",
            "escalar_a_humano",
        ],
        "blocked": [
            "cancelar_expediente",
            "guardar_datos_elemento",
            "confirmar_fotos_elemento",
        ],
    },
}


def _is_tool_blocked(
    tool_name: str,
    sub_mode: str,
    element_phase: str | None,
) -> bool:
    """
    Check if a tool call is blocked by the phase-aware tool matrix (TASK-08).

    Returns True when the tool should NOT be executed in the current
    (sub_mode, element_phase) combination. Returns False when execution
    is allowed or the matrix has no opinion on this combination.

    Safety override: ``escalar_a_humano`` is NEVER blocked regardless of
    matrix entry — it is a safety valve that must always be reachable.

    Args:
        tool_name: Name of the tool about to be executed (exact @tool name).
        sub_mode: Current expediente sub-mode constant (lower-case), e.g.
            ``"collect_element_data"``, ``"collect_personal"``.
        element_phase: ``"photos"`` or ``"data"`` for collect_element_data;
            ``None`` for all other sub-modes.

    Returns:
        True if blocked, False if allowed.
    """
    # Safety override: escalation is always reachable
    if tool_name == "escalar_a_humano":
        return False

    # Normalise element_phase: only collect_element_data uses it;
    # for all other sub-modes use None as the matrix key.
    _phase: str | None = element_phase if sub_mode == "collect_element_data" else None

    matrix_entry = EXPEDIENTE_TOOL_MATRIX.get((sub_mode, _phase))
    if matrix_entry is None:
        # No matrix opinion → allow (fail-open for unknown combos)
        return False

    blocked_tools: list[str] = matrix_entry.get("blocked", [])
    return tool_name in blocked_tools


# Sub-mode to step label map used by _inject_step_prefix (TASK-06)
# Derived from the canonical ``STEP_LABELS`` in ``agent.services.expediente_constants``
# so that labels are defined in exactly one place.
EXPEDIENTE_STEP_PREFIX: dict[str, str] = {key: step_prefix(key) for key in STEP_LABELS}

# ---------------------------------------------------------------------------
# TASK-10: Anti-anticipation guard + Introductory overview message
# ---------------------------------------------------------------------------
# When True, transition closure messages are trimmed to "Pasamos al paso X"
# without describing the next step's requirements.  The receiving sub-mode
# handler is responsible for introducing its own instructions on the next turn.
_ANTI_ANTICIPATION_GUARD_ENABLED: bool = True

# Canonical introductory overview message sent ONCE when EXPEDIENTE_MODE
# is first entered (case just created). Re-exported from the onboarding service.


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
# TASK-06: Progress prefix injection helper
# ---------------------------------------------------------------------------


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
# Task 3.3: Pre-response claim gate patterns
# ---------------------------------------------------------------------------
# These patterns are intentionally conservative — only exact, high-confidence
# phrases that have no ambiguity in context.  False-positives (blocking valid
# responses) are more harmful than false-negatives (letting one slip through).

# COMPLETION_CLAIM patterns — declares step / expediente as done
_COMPLETION_CLAIM_RE = re.compile(
    r"expediente\s+(?:ya\s+)?(?:est[aá]|ha\s+quedado)\s+(?:complet|list|cerrad)"
    r"|ya\s+hemos\s+(?:terminad|completad)\s+(?:el\s+)?(?:expediente|proceso|paso)"
    r"|todo\s+(?:ya\s+)?(?:est[aá]|queda)\s+(?:complet|list|guardad|registrad)"
    r"|el\s+(?:expediente|proceso|paso)\s+(?:est[aá]|ha\s+quedado)\s+(?:complet|cerrad|terminad)",
    re.IGNORECASE,
)

# CASE_FINALIZED patterns — asserts submission / finalization of the case
_CASE_FINALIZED_CLAIM_RE = re.compile(
    r"expediente\s+(?:ha\s+sido|ha\s+quedado|fue)\s+(?:enviad|registrad|tramitad|finaliz)"
    r"|hemos\s+(?:enviad|tramitad|finaliz)\s+(?:tu\s+)?(?:expediente|caso|solicitud)"
    r"|(?:tu|el|su)\s+caso\s+(?:ha\s+sido|fue)\s+(?:enviad|registrad|tramitad)",
    re.IGNORECASE,
)

# IMAGES_SENT patterns — asserts images were successfully delivered
_IMAGES_SENT_CLAIM_RE = re.compile(
    r"te\s+he\s+(?:enviad|mandad)\s+(?:las?\s+)?(?:im[aá]genes?|fotos?|ejemplos?)"
    r"|acabo\s+de\s+(?:enviar|mandar)\s+(?:las?\s+)?(?:im[aá]genes?|fotos?)",
    re.IGNORECASE,
)

# IMAGES_SENT intent-only replacements — keeps verb in future/intent tense
_IMAGES_INTENT_RE = re.compile(
    r"te\s+he\s+(enviad|mandad)",
    re.IGNORECASE,
)

# DOCS_RECEIVED patterns — asserts docs were received / confirmed
_DOCS_RECEIVED_CLAIM_RE = re.compile(
    r"(?:ya\s+)?(?:he\s+)?(?:recibid|registrad|guardad|confirmad)\s+(?:la\s+)?documentaci[oó]n"
    r"|documentaci[oó]n\s+(?:base\s+)?(?:ya\s+)?(?:recibida|registrada|confirmada|guardada)",
    re.IGNORECASE,
)


def _gate_response_claims(
    ai_response: str,
    turn_envelope: "CertaintyEnvelope",
    sub_mode: str,
    conversation_id: str,
    guardrails_enabled: bool,
) -> tuple[str, int, int]:
    """Apply pre-response claim gate to the final AI response text.

    Checks the final ``ai_response`` for unsupported assertions and rewrites or
    replaces the problematic phrases in-place when the claim cannot be supported
    by the turn's certainty envelope.

    Only active when ``guardrails_enabled=True``; passes through unchanged when
    the flag is off.

    Design principles:
    - Regex-only (no LLM calls): must be fast and deterministic.
    - Surgical rewrites: only the exact unsupported phrase is touched.
    - Fail-open: when uncertain, allow and log rather than block.

    Args:
        ai_response: Final assembled response text (post-LLM, pre-delivery).
        turn_envelope: Current turn's certainty envelope (fully accumulated).
        sub_mode: Current expediente sub-mode (lower-case constant).
        conversation_id: Conversation ID for structured log correlation.
        guardrails_enabled: If False, returns ``(ai_response, 0, 0)`` immediately.

    Returns:
        ``(gated_response, blocked_count, allowed_count)`` where:
        - ``gated_response``: Potentially rewritten response text.
        - ``blocked_count``: Number of claim rewrites applied this call.
        - ``allowed_count``: Number of claims that were evaluated and allowed.
    """
    if not guardrails_enabled or not ai_response:
        return ai_response, 0, 0

    blocked_count = 0
    allowed_count = 0
    response = ai_response

    # ── a. COMPLETION_CLAIM ──────────────────────────────────────────────────
    # Block if the confirming tool for this sub-mode has NOT succeeded this turn.
    _claim_ok_completion, _reason_completion = evaluate_claim_eligibility(
        turn_envelope,
        ClaimClass.COMPLETION_CLAIM,
        sub_mode,
    )
    if not _claim_ok_completion and _COMPLETION_CLAIM_RE.search(response):
        # Append a hedge so the user knows the process is still ongoing.
        _hedge = " Cuando completemos todos los pasos te lo confirmaré."
        # Only append if the hedge is not already there (idempotent).
        if _hedge.strip() not in response:
            response = response + _hedge
        blocked_count += 1
        log_guardrail_triggered(
            reason=_reason_completion,
            sub_mode=sub_mode,
            claim_class=ClaimClass.COMPLETION_CLAIM.value,
            conversation_id=conversation_id,
            allowed=False,
            extra={"rewrite": "hedge_appended", "enforced": True},
        )
        logger.warning(
            "expediente_certainty_guard_triggered",
            claim_class=ClaimClass.COMPLETION_CLAIM.value,
            sub_mode=sub_mode,
            conversation_id=conversation_id,
            reason_code=_reason_completion,
            enforced=True,
        )
    elif _claim_ok_completion and _COMPLETION_CLAIM_RE.search(response):
        allowed_count += 1

    # ── b. CASE_FINALIZED ────────────────────────────────────────────────────
    # Hard-block if finalizar_expediente() did not succeed this turn.
    _claim_ok_final, _reason_final = evaluate_claim_eligibility(
        turn_envelope,
        ClaimClass.CASE_FINALIZED,
        sub_mode,
    )
    if not _claim_ok_final and _CASE_FINALIZED_CLAIM_RE.search(response):
        # Replace with a deterministic bounded message.
        _deterministic = (
            "Cuando confirmes los datos y procedamos a la finalización, "
            "te lo comunicaré."
        )
        response = _CASE_FINALIZED_CLAIM_RE.sub(_deterministic, response)
        blocked_count += 1
        log_guardrail_triggered(
            reason=_reason_final,
            sub_mode=sub_mode,
            claim_class=ClaimClass.CASE_FINALIZED.value,
            conversation_id=conversation_id,
            allowed=False,
            extra={"rewrite": "replaced_deterministic", "enforced": True},
        )
        logger.warning(
            "expediente_premature_finalization_claim_blocked",
            sub_mode=sub_mode,
            conversation_id=conversation_id,
            reason_code=_reason_final,
            enforced=True,
        )
    elif _claim_ok_final and _CASE_FINALIZED_CLAIM_RE.search(response):
        allowed_count += 1

    # ── c. IMAGES_SENT ───────────────────────────────────────────────────────
    # When delivery is "pending" (intent only, not confirmed by transport layer),
    # rewrite past-tense claims to future-intent form.
    _claim_ok_imgs, _reason_imgs = evaluate_claim_eligibility(
        turn_envelope,
        ClaimClass.IMAGES_SENT,
        sub_mode,
    )
    if not _claim_ok_imgs and _IMAGES_SENT_CLAIM_RE.search(response):
        # Rewrite "te he enviado" → "voy a enviarte" etc.
        response = _IMAGES_INTENT_RE.sub(r"voy a enviarte", response)
        blocked_count += 1
        log_guardrail_triggered(
            reason=_reason_imgs,
            sub_mode=sub_mode,
            claim_class=ClaimClass.IMAGES_SENT.value,
            conversation_id=conversation_id,
            allowed=False,
            extra={"rewrite": "intent_rewrite", "enforced": True},
        )
        logger.warning(
            "expediente_certainty_guard_triggered",
            claim_class=ClaimClass.IMAGES_SENT.value,
            sub_mode=sub_mode,
            conversation_id=conversation_id,
            reason_code=_reason_imgs,
            enforced=True,
        )
    elif _claim_ok_imgs and _IMAGES_SENT_CLAIM_RE.search(response):
        allowed_count += 1

    # ── d. DOCS_RECEIVED ─────────────────────────────────────────────────────
    # Add hedging qualifier if docs have not been confirmed by a tool this turn.
    _claim_ok_docs, _reason_docs = evaluate_claim_eligibility(
        turn_envelope,
        ClaimClass.DOCS_RECEIVED,
        sub_mode,
    )
    if not _claim_ok_docs and _DOCS_RECEIVED_CLAIM_RE.search(response):
        # Append a qualifier so the user is not misled.
        _qualifier = " (pendiente de verificación)."
        if _qualifier.strip().rstrip(".") not in response:
            response = _DOCS_RECEIVED_CLAIM_RE.sub(
                lambda m: m.group(0) + _qualifier,
                response,
                count=1,
            )
        blocked_count += 1
        log_guardrail_triggered(
            reason=_reason_docs,
            sub_mode=sub_mode,
            claim_class=ClaimClass.DOCS_RECEIVED.value,
            conversation_id=conversation_id,
            allowed=False,
            extra={"rewrite": "qualifier_appended", "enforced": True},
        )
        logger.warning(
            "expediente_certainty_guard_triggered",
            claim_class=ClaimClass.DOCS_RECEIVED.value,
            sub_mode=sub_mode,
            conversation_id=conversation_id,
            reason_code=_reason_docs,
            enforced=True,
        )
    elif _claim_ok_docs and _DOCS_RECEIVED_CLAIM_RE.search(response):
        allowed_count += 1

    return response, blocked_count, allowed_count


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
# Module-level helpers (used by static methods inside the class)
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


def _get_transition_base_documentation(
    mode_context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Resolve base_documentation for deterministic transition kickoff."""
    category_data = mode_context.get("category_data")
    if isinstance(category_data, dict):
        base_docs = category_data.get("base_documentation")
        if isinstance(base_docs, list):
            return [doc for doc in base_docs if isinstance(doc, dict)]

    # Backward-compatible fallback: build doc entries from legacy descriptions.
    legacy_descs = mode_context.get("base_doc_descriptions")
    if isinstance(legacy_descs, list):
        docs_from_legacy: list[dict[str, Any]] = []
        for desc in legacy_descs:
            if isinstance(desc, str) and desc.strip():
                docs_from_legacy.append({"description": desc})
        return docs_from_legacy

    return []


def _build_element_completion_transition_closure(
    *,
    from_sub_mode: str,
    to_sub_mode: str,
    tool_name: str,
    tool_data: dict[str, Any] | None,
    base_documentation: list[dict[str, Any]] | None = None,
) -> str | None:
    """Return explicit same-turn closure with actionable base-doc kickoff.

    This is the LEGACY entry-point kept for backward-compatibility.  It only
    handles the element_data → base_docs transition.  For all other handoffs,
    use :func:`_build_transition_closure` (which internally delegates here for
    this specific pair).

    The kickoff list is built from base_documentation sourced from category_data,
    so descriptions are always accurate and up-to-date — never hardcoded.
    """
    if from_sub_mode != COLLECT_ELEMENT_DATA or to_sub_mode != COLLECT_BASE_DOCS:
        return None

    if tool_name not in ("confirmar_fotos_elemento", "completar_elemento_actual"):
        return None

    data = tool_data if isinstance(tool_data, dict) else {}
    if not data.get("all_elements_complete"):
        return None

    prefix = _progress_prefix(COLLECT_BASE_DOCS)
    # TASK-10 anti-anticipation: when guard is enabled, do NOT list base-doc
    # requirements in the same turn as the element completion signal.
    # The COLLECT_BASE_DOCS handler will describe its requirements on the next turn.
    if _ANTI_ANTICIPATION_GUARD_ENABLED:
        body = (
            "Perfecto, con esto cerramos los elementos. "
            "Pasamos al paso 2: necesito fotos legibles de:\n\n"
            "- Ficha técnica del vehículo (ambas caras)\n"
            "- Permiso de circulación (ambas caras)\n"
            "- DNI/NIE del titular (ambas caras)\n"
            "- 4 fotos del vehículo (frontal, trasera, lateral izquierda, lateral derecha)"
        )
        cta = "Envíamelas como imagen de WhatsApp cuando las tengas."
        return f"{prefix}\n\n📍 {body}\n\n{cta}"
    # Legacy behaviour (guard disabled): include full base-doc list
    docs_list = _format_base_docs_kickoff(base_documentation or [])
    existing_message = (
        "Perfecto, con esto cerramos la parte de los elementos. "
        "Ahora necesito que me envies fotos de la documentacion base del vehiculo:\n\n"
        f"{docs_list}"
    )
    return f"{prefix}\n\n{existing_message}"


# ---------------------------------------------------------------------------
# Transition matrix: (from_sub_mode, to_sub_mode) → (triggering_tools, builder)
# ---------------------------------------------------------------------------

# Type alias: a closure builder receives tool_data and extra keyword kwargs,
# and returns the final user-facing closure string.
_ClosureBuilder = Any  # Callable[[dict[str,Any]], str]


def _build_base_docs_to_personal_closure(
    tool_data: dict[str, Any],
    **_kwargs: Any,
) -> str:
    """Closure for base_docs → personal transition.

    TASK-10 anti-anticipation: do NOT describe the next step's requirements
    here.  The COLLECT_PERSONAL handler will introduce them on the next turn.
    """
    if _ANTI_ANTICIPATION_GUARD_ENABLED:
        prefix = _progress_prefix(COLLECT_PERSONAL)
        # Task 2.2: Avoid phrasing that matches _DOCS_RECEIVED_CLAIM_RE
        # ("recibid|registrad|guardad|confirmad" + "documentación").
        # "verificada" is not in that regex, so the claim gate stays clean.
        body = (
            "Perfecto, documentación base verificada. "
            "Pasamos al paso 3: necesito tus datos personales:\n\n"
            "- Nombre completo y apellidos\n"
            "- DNI/CIF\n"
            "- Email\n"
            "- Dirección completa (calle, localidad, provincia, código postal)\n"
            "- Nombre de la ITV"
        )
        cta = "Puedes enviarme todo junto o ir de uno en uno."
        return f"{prefix}\n\n📍 {body}\n\n{cta}"
    # Legacy behaviour (guard disabled)
    prefix = _progress_prefix(COLLECT_PERSONAL)
    existing_message = (
        "Perfecto, con esto cerramos la documentacion base. "
        "Ahora necesito tus datos personales para el expediente: "
        "nombre completo, apellidos, DNI/CIF, email, domicilio completo e ITV."
    )
    return f"{prefix}\n\n{existing_message}"


def _build_personal_to_vehicle_closure(
    tool_data: dict[str, Any],
    **_kwargs: Any,
) -> str:
    """Closure for personal → vehicle transition.

    TASK-10 anti-anticipation: do NOT list vehicle fields here.
    The COLLECT_VEHICLE handler will ask for them on the next turn.
    """
    if _ANTI_ANTICIPATION_GUARD_ENABLED:
        prefix = _progress_prefix(COLLECT_VEHICLE)
        body = (
            "Perfecto, datos personales registrados. "
            "Pasamos al paso 4: necesito los datos del vehículo:\n\n"
            "- Marca\n"
            "- Modelo\n"
            "- Año de primera matriculación\n"
            "- Matrícula\n"
            "- Número de bastidor (VIN, 17 caracteres)"
        )
        cta = "¿Tienes la documentación del vehículo a mano?"
        return f"{prefix}\n\n📍 {body}\n\n{cta}"
    # Legacy behaviour (guard disabled)
    prefix = _progress_prefix(COLLECT_VEHICLE)
    existing_message = (
        "Perfecto, datos personales registrados. "
        "Ahora necesito los datos del vehículo: "
        "marca, modelo, año de fabricación, matrícula y número de bastidor (VIN)."
    )
    return f"{prefix}\n\n{existing_message}"


def _build_vehicle_to_workshop_closure(
    tool_data: dict[str, Any],
    **_kwargs: Any,
) -> str:
    """Closure for vehicle → workshop transition.

    TASK-10 anti-anticipation: do NOT describe workshop options or pricing here.
    The COLLECT_WORKSHOP handler will present the choice on the next turn.
    """
    if _ANTI_ANTICIPATION_GUARD_ENABLED:
        prefix = _progress_prefix(COLLECT_WORKSHOP)
        # Workshop binary question — body IS the CTA (no separate CTA line).
        # mode_context.get("taller_propio") is typically None at closure time,
        # so always use the generic binary question variant.
        body = (
            "Perfecto, datos del vehículo registrados. "
            "Pasamos al paso 5: para la ITV necesitamos un certificado del taller de instalación.\n\n"
            "¿Prefieres que MSI lo gestione por 85€ +IVA, o tienes taller propio registrado?"
        )
        return f"{prefix}\n\n📍 {body}"
    # Legacy behaviour (guard disabled)
    prefix = _progress_prefix(COLLECT_WORKSHOP)
    existing_message = (
        "Perfecto, datos del vehiculo registrados. "
        "Para la ITV necesitamos un certificado del taller. "
        "¿Prefieres que MSI gestione el certificado por 85 EUR +IVA, "
        "o tienes taller propio registrado?"
    )
    return f"{prefix}\n\n{existing_message}"


def _build_workshop_to_review_closure(
    tool_data: dict[str, Any],
    **_kwargs: Any,
) -> str:
    """Closure for workshop → review_summary transition.

    TASK-10 anti-anticipation: do NOT describe review content here.
    The REVIEW_SUMMARY handler will present the full summary on the next turn.
    """
    if _ANTI_ANTICIPATION_GUARD_ENABLED:
        prefix = _progress_prefix(REVIEW_SUMMARY)
        # Review is tool-first — announcement only, NO field list or CTA.
        return f"{prefix}\n\n📍 Perfecto, información del taller registrada. Pasamos al paso 6: revisión final del expediente."
    # Legacy behaviour (guard disabled)
    prefix = _progress_prefix(REVIEW_SUMMARY)
    existing_message = (
        "Perfecto, datos del taller registrados. "
        "Te presento el resumen completo del expediente para que confirmes que todo es correcto."
    )
    return f"{prefix}\n\n{existing_message}"


# Transition matrix: maps (from, to) → (set[triggering tool names], builder fn)
# The builder receives `tool_data` dict and any extra kwargs (e.g. base_documentation).
_TRANSITION_MATRIX: dict[
    tuple[str, str],
    tuple[frozenset[str], Any],
] = {
    # element_data → base_docs: delegate to existing legacy builder
    (COLLECT_ELEMENT_DATA, COLLECT_BASE_DOCS): (
        frozenset({"confirmar_fotos_elemento", "completar_elemento_actual"}),
        None,  # None → use legacy _build_element_completion_transition_closure
    ),
    # base_docs → personal
    (COLLECT_BASE_DOCS, COLLECT_PERSONAL): (
        frozenset({"confirmar_documentacion_base"}),
        _build_base_docs_to_personal_closure,
    ),
    # personal → vehicle
    (COLLECT_PERSONAL, COLLECT_VEHICLE): (
        frozenset({"actualizar_datos_expediente"}),
        _build_personal_to_vehicle_closure,
    ),
    # vehicle → workshop
    (COLLECT_VEHICLE, COLLECT_WORKSHOP): (
        frozenset({"actualizar_datos_expediente"}),
        _build_vehicle_to_workshop_closure,
    ),
    # workshop → review_summary
    (COLLECT_WORKSHOP, REVIEW_SUMMARY): (
        frozenset({"actualizar_datos_taller"}),
        _build_workshop_to_review_closure,
    ),
}


def _build_transition_closure(
    *,
    from_sub_mode: str,
    to_sub_mode: str,
    tool_name: str,
    tool_data: dict[str, Any] | None,
    base_documentation: list[dict[str, Any]] | None = None,
) -> str | None:
    """Return a deterministic same-turn closure string for a committed sub-mode transition.

    Covers all expediente handoffs defined in ``_TRANSITION_MATRIX``.  Returns
    ``None`` when the (from, to) pair is not in the matrix or the triggering tool
    is not authorised for that transition (safety guard — prevents spurious
    closure on incidental tool calls).

    The element_data → base_docs pair delegates to the existing legacy function
    :func:`_build_element_completion_transition_closure` so its ``all_elements_complete``
    signal check and dynamic base_documentation list are preserved.

    Args:
        from_sub_mode: Source sub-mode (lower-case constant, e.g. ``collect_base_docs``).
        to_sub_mode: Destination sub-mode (lower-case constant).
        tool_name: The tool that triggered the transition.
        tool_data: Parsed tool result dict (may be None if parse failed).
        base_documentation: Optional list of base-doc dicts (only used for
            the element_data → base_docs pair).

    Returns:
        User-facing closure string, or None if this pair is not handled.
    """
    matrix_entry = _TRANSITION_MATRIX.get((from_sub_mode, to_sub_mode))
    if matrix_entry is None:
        return None

    allowed_tools, builder = matrix_entry
    if tool_name not in allowed_tools:
        return None

    data = tool_data if isinstance(tool_data, dict) else {}

    # element_data → base_docs: delegate to legacy function (preserves all_elements_complete check)
    if builder is None:
        return _build_element_completion_transition_closure(
            from_sub_mode=from_sub_mode,
            to_sub_mode=to_sub_mode,
            tool_name=tool_name,
            tool_data=tool_data,
            base_documentation=base_documentation,
        )

    # Other transitions: tool must have reported success
    if not data.get("success"):
        return None

    return builder(data, base_documentation=base_documentation)


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


class ExpedienteModeNode(BaseModeNode):
    """
    EXPEDIENTE_MODE: Formal case data collection.

    This mode orchestrates 6 sub-modes, each responsible for collecting
    specific data:
    - COLLECT_ELEMENT_DATA: Photos + technical data per element
    - COLLECT_BASE_DOCS: Base vehicle documents
    - COLLECT_PERSONAL: Personal data (nombre, DNI, email, etc.)
    - COLLECT_VEHICLE: Vehicle data (marca, modelo, matrícula)
    - COLLECT_WORKSHOP: Workshop data (if taller_propio=True)
    - REVIEW_SUMMARY: Final confirmation before submission

    Sub-mode routing happens automatically via tool returns that update
    expediente_sub_mode in mode_context.
    """

    def __init__(self) -> None:
        super().__init__("EXPEDIENTE_MODE")
        self._tools_cache: dict[str, list] = {}  # Tools per sub-mode
        # V2: lazy singletons — initialised on first use to avoid import-time
        # circular deps and so EXPEDIENTE_V2_ENABLED is already loaded.
        self._element_state_svc: ElementStateService | None = None
        self._intent_classifier_svc: IntentClassifier | None = None

    def _get_element_state_svc(self) -> ElementStateService | None:
        """Return ElementStateService singleton when EXPEDIENTE_V2_ENABLED, else None."""
        if not get_settings().EXPEDIENTE_V2_ENABLED:
            return None
        if self._element_state_svc is None:
            from agent.services.element_state_service import get_element_state_service

            self._element_state_svc = get_element_state_service()
        return self._element_state_svc

    def _get_intent_classifier_svc(self) -> IntentClassifier | None:
        """Return IntentClassifier singleton when EXPEDIENTE_V2_ENABLED, else None."""
        if not get_settings().EXPEDIENTE_V2_ENABLED:
            return None
        if self._intent_classifier_svc is None:
            from agent.services.intent_classifier import get_intent_classifier

            self._intent_classifier_svc = get_intent_classifier()
        return self._intent_classifier_svc

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    async def _process_message(
        self,
        message: str,
        state: ConversationState,
    ) -> dict[str, Any]:
        """
        Process a user message in EXPEDIENTE_MODE.

        Routes to appropriate sub-mode handler based on expediente_sub_mode.
        """
        conversation_id = state.get("conversation_id", "unknown")
        mode_context = dict(state.get("mode_context", {}))

        # Initialize mode_context from DB if empty (first entry to EXPEDIENTE_MODE)
        if not mode_context.get("case_id"):
            mode_context = await self._initialize_mode_context(
                conversation_id,
                mode_context,
                state,
            )

        # Determine current sub-mode
        sub_mode = mode_context.get("expediente_sub_mode", COLLECT_ELEMENT_DATA)

        # Reconcile element_phase with DB if case_id exists (safety net)
        case_id = mode_context.get("case_id")
        if case_id and mode_context.get("element_phase") == "photos":
            # Check if DB says photos are already done for current element
            current_el_code = mode_context.get("current_element_code")
            if current_el_code:
                try:
                    from database.connection import get_async_session
                    from database.models import CaseElementData
                    from sqlalchemy import select
                    import uuid as _uuid

                    async with get_async_session() as session:
                        result = await session.execute(
                            select(CaseElementData.status)
                            .where(CaseElementData.case_id == _uuid.UUID(str(case_id)))
                            .where(CaseElementData.element_code == current_el_code)
                        )
                        db_status = result.scalar_one_or_none()
                        if db_status == "pending_data":
                            mode_context["element_phase"] = "data"
                            logger.warning(
                                "state_reconciled_from_db",
                                field="element_phase",
                                stale_value="photos",
                                corrected_value="data",
                                case_id=case_id,
                                element_code=current_el_code,
                            )
                except Exception as e:
                    # Non-critical — if reconciliation fails, continue with existing state
                    logger.debug("state_reconciliation_skipped", error=str(e))

        self._logger.info(
            "expediente_processing",
            sub_mode=sub_mode,
            message_preview=message[:60],
        )

        # ── TASK-10: Introductory overview message injection ────────────────
        # When EXPEDIENTE_V2_ENABLED=True and _auto_create_case() stored the
        # canonical intro message in mode_context["expediente_intro_message"],
        # consume it here (first turn only) by prepending it to the sub-mode
        # handler's response.  The key is cleared after reading so it never
        # appears twice, even if the checkpoint is replayed.
        _raw_intro_msg = mode_context.pop("expediente_intro_message", None)
        _intro_msg: str | None = (
            cast(str | None, _raw_intro_msg)
            if isinstance(_raw_intro_msg, str)
            else None
        )
        expediente_intro_sent = bool(mode_context.get("expediente_intro_sent", False))
        raw_current_element_index: Any = mode_context.get("current_element_index", 0)
        if isinstance(raw_current_element_index, int):
            current_element_index = raw_current_element_index
        elif (
            isinstance(raw_current_element_index, str)
            and raw_current_element_index.isdigit()
        ):
            current_element_index = int(raw_current_element_index)
        else:
            current_element_index = 0

        # Route to sub-mode handler
        if sub_mode == COLLECT_ELEMENT_DATA:
            _handler_result = await self._handle_element_data(
                message, state, mode_context
            )
            if _intro_msg:
                intro_confirmation = build_expediente_intro_confirmation()
                # Prepend intro message to the first element-data response.
                _existing_resp = _handler_result.get("ai_response", "")
                _handler_result["ai_response"] = (
                    f"{_intro_msg}\n\n{_existing_resp}"
                    if _existing_resp
                    else _intro_msg
                )
                mode_context.update(intro_confirmation)
                handler_mode_context = _handler_result.get("mode_context")
                if not isinstance(handler_mode_context, dict):
                    handler_mode_context = mode_context
                _handler_result["mode_context"] = {
                    **handler_mode_context,
                    **intro_confirmation,
                }
                self._logger.info(
                    "expediente_intro_message_injected",
                    conversation_id=conversation_id,
                    sub_mode=sub_mode,
                )
            elif current_element_index == 0 and not expediente_intro_sent:
                safety_intro = build_expediente_opening_overview()
                _existing_resp = _handler_result.get("ai_response", "")
                _handler_result["ai_response"] = (
                    f"{safety_intro}\n\n{_existing_resp}"
                    if _existing_resp
                    else safety_intro
                )
                intro_confirmation = build_expediente_intro_confirmation()
                mode_context.update(intro_confirmation)
                handler_mode_context = _handler_result.get("mode_context")
                if not isinstance(handler_mode_context, dict):
                    handler_mode_context = mode_context
                _handler_result["mode_context"] = {
                    **handler_mode_context,
                    **intro_confirmation,
                }
                self._logger.warning(
                    "expediente_intro_safety_net_triggered",
                    conversation_id=conversation_id,
                    sub_mode=sub_mode,
                    current_element_index=current_element_index,
                )
            return _handler_result
        elif sub_mode == COLLECT_BASE_DOCS:
            return await self._handle_base_docs(message, state, mode_context)
        elif sub_mode == COLLECT_PERSONAL:
            return await self._handle_personal(message, state, mode_context)
        elif sub_mode == COLLECT_VEHICLE:
            return await self._handle_vehicle(message, state, mode_context)
        elif sub_mode == COLLECT_WORKSHOP:
            return await self._handle_workshop(message, state, mode_context)
        elif sub_mode == REVIEW_SUMMARY:
            return await self._handle_review(message, state, mode_context)
        else:
            # Unknown sub-mode — reset to start
            self._logger.error(
                "unknown_sub_mode",
                sub_mode=sub_mode,
            )
            return {
                "ai_response": (
                    "Hubo un error en el flujo del expediente. "
                    "Vamos a reiniciar desde el principio."
                ),
                "mode_context": {
                    **mode_context,
                    "expediente_sub_mode": COLLECT_ELEMENT_DATA,
                },
            }

    def get_tools(self) -> list:
        """
        Return tools available in EXPEDIENTE_MODE.

        Tools vary by sub-mode, but this method returns ALL tools
        (the sub-mode handlers will filter appropriately).
        """
        # Return all expediente tools (sub-mode handlers filter)
        return _get_all_expediente_tools()

    # ------------------------------------------------------------------
    # Mode context initialization
    # ------------------------------------------------------------------

    async def _initialize_mode_context(
        self,
        conversation_id: str,
        current_context: dict[str, Any],
        state: ConversationState | None = None,
    ) -> dict[str, Any]:
        """
        Initialize mode_context from DB when entering EXPEDIENTE_MODE.

        This loads the active case data for v1 tools compatibility.
        V1 tools expect case_id, category_id, element_codes, etc. in the FSM state,
        which we store in mode_context.

        Handles two entry paths:
        1. Normal entry (from PRESUPUESTO_MODE confirmation) — queries by conversation_id
        2. Recovery entry (from preprocess_node after checkpoint expiry) — uses
           ``pending_recovery_case`` already injected into mode_context by preprocess_node.
           In this case, the LLM is guided to offer the user a warm resume greeting.

        Args:
            conversation_id: Conversation ID (new thread after checkpoint expiry)
            current_context: Current mode_context (may contain pending_recovery_case)
            state: Full conversation state (for user_id access before ContextVar is set)

        Returns:
            Initialized mode_context with case data
        """
        # ── Recovery path: orphaned expediente detected by preprocess_node ──────
        # preprocess_node injected pending_recovery_case when it found an active
        # Case in PostgreSQL belonging to this user but from a different conversation
        # thread (i.e. the Redis checkpoint expired).
        pending_recovery = current_context.get("pending_recovery_case")
        if pending_recovery and isinstance(pending_recovery, dict):
            return await self._build_recovery_context(
                conversation_id=conversation_id,
                recovery_data=pending_recovery,
                current_context=current_context,
            )

        # ── Normal path: query by conversation_id ──────────────────────────────
        from database.connection import get_async_session
        from database.models import Case

        try:
            async with get_async_session() as session:
                from sqlalchemy import select

                # Find active case for this conversation
                result = await session.execute(
                    select(Case)
                    .where(Case.conversation_id == conversation_id)
                    .where(
                        Case.status.in_(["collecting", "pending_review", "in_progress"])
                    )
                    .order_by(Case.created_at.desc())
                )
                case = result.scalar_one_or_none()

                if not case:
                    logger.warning(
                        "no_active_case_for_expediente_attempting_auto_create",
                        conversation_id=conversation_id,
                    )
                    # Auto-create case from mode_context data
                    # (carried from PRESUPUESTO → EVAL_GATEWAY → EXPEDIENTE
                    # via CONTEXT_PRESERVE_RULES in mode_transitions.py)
                    return await self._auto_create_case(
                        conversation_id,
                        current_context,
                        state,
                    )

                # Resolve category_slug from relationship (Case has no
                # category_slug column — only category_id FK).
                category_slug = (
                    case.category.slug
                    if case.category
                    else current_context.get("categoria_slug", "")
                )
                codes = case.element_codes or []

                from sqlalchemy import select as sa_select
                from database.models import CaseElementData

                # ── Reconcile element progress from DB ──────────────────────
                # When re-entering EXPEDIENTE_MODE (e.g. after reconnect or
                # restart), rebuild element_data_status and current_element_index
                # from persisted CaseElementData records instead of resetting
                # everything to 0/pending. This prevents the agent from asking
                # for photos that were already confirmed.
                ced_result = await session.execute(
                    sa_select(CaseElementData).where(CaseElementData.case_id == case.id)
                )
                ced_rows = list(ced_result.scalars().all())
                ced_by_code: dict[str, str] = {
                    row.element_code: row.status for row in ced_rows
                }

                if ced_by_code:
                    # Rebuild element_data_status honoring persisted statuses
                    reconciled_status: dict[str, str] = {}
                    first_incomplete_idx: int = len(codes)  # Default: all done
                    first_incomplete_phase: str = "photos"

                    for idx, code in enumerate(codes):
                        db_status = ced_by_code.get(code)
                        if db_status == "completed":
                            reconciled_status[code] = "completed"
                        elif db_status == "pending_data":
                            reconciled_status[code] = "pending_data"
                            if first_incomplete_idx == len(codes):
                                first_incomplete_idx = idx
                                first_incomplete_phase = "data"
                        else:
                            # pending_photos or not in DB yet
                            reconciled_status[code] = "pending_photos"
                            if first_incomplete_idx == len(codes):
                                first_incomplete_idx = idx
                                first_incomplete_phase = "photos"

                    reconciled_index = (
                        min(first_incomplete_idx, len(codes) - 1) if codes else 0
                    )
                    reconciled_phase = first_incomplete_phase

                    # Determine if all elements are already completed
                    all_elements_done = (
                        all(v == "completed" for v in reconciled_status.values())
                        if reconciled_status
                        else False
                    )
                else:
                    # No DB records yet — start fresh
                    reconciled_status = {code: "pending" for code in codes}
                    reconciled_index = 0
                    reconciled_phase = "photos"
                    all_elements_done = False

                # ── V2: Override reconciled values from ElementStateService ────
                # When EXPEDIENTE_V2_ENABLED, the service is the authoritative
                # source of truth for element completion.  Override the dict-based
                # reconciliation above with DB-authoritative values.
                _ess_v2 = self._get_element_state_svc()
                if _ess_v2 is not None and codes:
                    try:
                        all_elements_done = await _ess_v2.is_all_elements_complete(
                            str(case.id), codes
                        )
                        _current_el_code_v2 = await _ess_v2.get_current_element(
                            str(case.id), codes
                        )
                        if (
                            _current_el_code_v2 is not None
                            and _current_el_code_v2 in codes
                        ):
                            reconciled_index = codes.index(_current_el_code_v2)
                            # Derive phase from DB status
                            _el_state_v2 = await _ess_v2.get_element_state(
                                str(case.id), _current_el_code_v2
                            )
                            if _el_state_v2 is not None:
                                _db_status_v2 = ced_by_code.get(
                                    _current_el_code_v2, "pending_photos"
                                )
                                reconciled_phase = (
                                    "data"
                                    if _db_status_v2 == "pending_data"
                                    else "photos"
                                )
                        elif all_elements_done:
                            reconciled_index = len(codes) - 1
                        logger.info(
                            "reconciled_from_element_state_service",
                            case_id=str(case.id),
                            all_elements_done=all_elements_done,
                            current_element=_current_el_code_v2,
                            reconciled_index=reconciled_index,
                            reconciled_phase=reconciled_phase,
                        )
                    except Exception as _ess_err:
                        logger.warning(
                            "element_state_service_reconcile_failed",
                            case_id=str(case.id),
                            error=str(_ess_err),
                        )
                        # Fallback: keep dict-based values computed above

                logger.info(
                    "reconciled_element_progress_from_db",
                    case_id=str(case.id),
                    total_elements=len(codes),
                    completed=sum(
                        1 for v in reconciled_status.values() if v == "completed"
                    ),
                    current_index=reconciled_index,
                    all_done=all_elements_done,
                )

                # Determine correct sub_mode based on reconciled element state
                # Prefer sub_mode already in context (set by previous turns),
                # but if all elements are done and context says collect_element_data,
                # advance to collect_base_docs automatically.
                persisted_sub_mode = current_context.get(
                    "expediente_sub_mode", COLLECT_ELEMENT_DATA
                )
                if all_elements_done and persisted_sub_mode == COLLECT_ELEMENT_DATA:
                    reconciled_sub_mode = COLLECT_BASE_DOCS
                    logger.info(
                        "auto_advanced_sub_mode_all_elements_done",
                        case_id=str(case.id),
                        from_sub_mode=COLLECT_ELEMENT_DATA,
                        to_sub_mode=COLLECT_BASE_DOCS,
                    )
                else:
                    reconciled_sub_mode = persisted_sub_mode

                # Load base doc descriptions from DB/cache for this category
                (
                    base_doc_descriptions,
                    loaded_category_data,
                ) = await _load_base_doc_descriptions(category_slug)
                hydrated_context = await _hydrate_case_context_from_db(
                    case,
                    case.user,
                    reconciled_sub_mode,
                )

                # Build FSM state so element_data_tools can work on
                # the first turn after re-entering EXPEDIENTE_MODE.
                existing_fsm_state = {
                    "case_collection": {
                        "step": hydrated_context.get(
                            "fsm_step", CollectionStep.COLLECT_ELEMENT_DATA.value
                        ),
                        "case_id": str(case.id),
                        "category_slug": category_slug,
                        "category_id": str(case.category_id)
                        if case.category_id
                        else None,
                        "element_codes": codes,
                        "current_element_index": reconciled_index,
                        "element_phase": reconciled_phase,
                        "element_data_status": reconciled_status,
                        "base_docs_received": hydrated_context.get(
                            "base_docs_received", False
                        ),
                        "base_doc_descriptions": base_doc_descriptions,
                        "received_images": [],
                        "tariff_tier_id": str(case.tariff_tier_id)
                        if case.tariff_tier_id
                        else None,
                        "tariff_amount": float(case.tariff_amount)
                        if case.tariff_amount
                        else None,
                        "taller_propio": hydrated_context.get("taller_propio"),
                        "taller_data": hydrated_context.get("taller_data"),
                        "retry_count": 0,
                    }
                }

                # P2.4: Resolve display names — prefer elementos_confirmados
                # from current_context (rich variant data from presupuesto),
                # fall back to DB query for backward compatibility.
                _ctx_confirmed: list[dict[str, Any]] | None = current_context.get(
                    "elementos_confirmados"
                )
                _init_display_names: dict[str, str] = {}
                if _ctx_confirmed and isinstance(_ctx_confirmed, list):
                    _init_display_names = {
                        elem.get("code", ""): elem.get("name") or elem.get("code", "")
                        for elem in _ctx_confirmed
                        if isinstance(elem, dict) and elem.get("code")
                    }
                # Supplement/fallback: DB query for any codes not in confirmed data
                _missing_init = [c for c in codes if c not in _init_display_names]
                if _missing_init:
                    _category_id_str = str(case.category_id) if case.category_id else ""
                    _db_display_names = await _resolve_element_display_names(
                        _missing_init, _category_id_str
                    )
                    _init_display_names.update(_db_display_names)

                # Initialize context with case data
                initialized_context = {
                    **current_context,
                    "case_id": str(case.id),
                    "category_id": str(case.category_id) if case.category_id else None,
                    "category_slug": category_slug,
                    "element_codes": codes,
                    # P2.4: display names from elementos_confirmados + DB fallback
                    "element_display_names": _init_display_names,
                    "current_element_index": reconciled_index,
                    "element_phase": reconciled_phase,
                    "element_data_status": reconciled_status,
                    "base_docs_received": hydrated_context.get(
                        "base_docs_received", False
                    ),
                    "base_doc_descriptions": base_doc_descriptions,
                    "category_data": loaded_category_data
                    or current_context.get("category_data"),
                    "personal_data": hydrated_context.get("personal_data", {}),
                    "vehicle_data": hydrated_context.get("vehicle_data", {}),
                    "taller_propio": hydrated_context.get("taller_propio"),
                    "taller_data": hydrated_context.get("taller_data"),
                    "tariff_tier_id": str(case.tariff_tier_id)
                    if case.tariff_tier_id
                    else None,
                    "tariff_amount": float(case.tariff_amount)
                    if case.tariff_amount
                    else None,
                    "received_images": [],
                    "expediente_intro_sent": current_context.get(
                        "expediente_intro_sent", True
                    ),
                    "_fsm_state_init": existing_fsm_state,
                    "expediente_sub_mode": reconciled_sub_mode,
                }

                logger.info(
                    "initialized_mode_context_from_db",
                    case_id=str(case.id),
                    element_count=len(codes),
                    category_slug=category_slug,
                    has_display_names=bool(_init_display_names),
                )

                return initialized_context

        except Exception as e:
            logger.error(
                "failed_to_initialize_mode_context",
                error=str(e),
                conversation_id=conversation_id,
                exc_info=True,
            )
            return current_context

    # ------------------------------------------------------------------
    # Auto-create case when entering EXPEDIENTE without an existing Case
    # ------------------------------------------------------------------

    async def _auto_create_case(
        self,
        conversation_id: str,
        current_context: dict[str, Any],
        state: ConversationState | None = None,
    ) -> dict[str, Any]:
        """
        Auto-create a Case when entering EXPEDIENTE_MODE without one.

        Uses data preserved in mode_context from PRESUPUESTO → EVAL_GATEWAY
        transition (via CONTEXT_PRESERVE_RULES in mode_transitions.py).

        This method produces the SAME initialization as ``iniciar_expediente``
        in ``case_tools.py``, including:
        - CaseElementData rows per element
        - base_doc_descriptions from tarifa_service
        - Proper element_data_status via initialize_element_data_status()
        - Imperative instructions for the LLM in case_instructions

        Required keys in current_context:
        - categoria_slug: str (from PRESUPUESTO_MODE)
        - element_codes: list[str] (from PRESUPUESTO_MODE)

        Optional keys:
        - tarifa_calculada: dict (from calcular_tarifa_con_elementos)

        Args:
            conversation_id: Conversation ID
            current_context: Current mode_context with preserved data
            state: Full conversation state (user_id read from here, NOT ContextVar)
        """
        import uuid
        from agent.services.case_helpers import get_or_create_active_case
        from agent.tools.case_tools import (
            _get_category_id_by_slug,
        )

        categoria_slug = current_context.get("categoria_slug")

        # -----------------------------------------------------------------------
        # P2.4: Read elementos_confirmados as PRIMARY source for element codes
        # and display names.  elementos_confirmados is populated by
        # presupuesto_mode._extract_context_from_tool when calcular_tarifa
        # succeeds, and preserved across PRESUPUESTO → EXPEDIENTE transitions
        # by mode_transitions.py.
        # Falls back to element_codes for backward compatibility with old
        # Redis checkpoints that lack elementos_confirmados.
        # -----------------------------------------------------------------------
        elementos_confirmados: list[dict[str, Any]] | None = current_context.get(
            "elementos_confirmados"
        )
        _confirmed_display_names: dict[str, str] | None = None
        if elementos_confirmados and isinstance(elementos_confirmados, list):
            # Derive element_codes from the rich variant data
            element_codes = [
                elem.get("code", "")
                for elem in elementos_confirmados
                if isinstance(elem, dict) and elem.get("code")
            ]
            # Pre-build display names from the rich data (avoids DB query later)
            _confirmed_display_names = {
                elem.get("code", ""): elem.get("name") or elem.get("code", "")
                for elem in elementos_confirmados
                if isinstance(elem, dict) and elem.get("code")
            }
            logger.info(
                "using_elementos_confirmados_for_element_codes",
                element_count=len(element_codes),
                has_display_names=bool(_confirmed_display_names),
                source="elementos_confirmados",
            )
        else:
            # Backward compatibility: fall back to element_codes list
            element_codes = current_context.get("element_codes", [])
            if not elementos_confirmados:
                logger.debug(
                    "elementos_confirmados_not_available_using_element_codes",
                    element_count=len(element_codes),
                    source="element_codes",
                )

        if not categoria_slug or not element_codes:
            logger.error(
                "cannot_auto_create_case_missing_data",
                conversation_id=conversation_id,
                has_categoria=bool(categoria_slug),
                has_elements=bool(element_codes),
                context_keys=list(current_context.keys()),
            )
            return current_context

        # -----------------------------------------------------------------------
        # Extract state-level data (user_id, client_type) from the state param.
        # NOTE: ContextVar is NOT set yet at this point — state is the raw dict.
        # -----------------------------------------------------------------------
        state_dict_safe = dict(state) if state else {}
        client_type_safe: str | None = cast(
            str | None, state_dict_safe.get("client_type")
        )
        user_id_safe = state_dict_safe.get("user_id")
        user_id_safe_str = str(user_id_safe) if user_id_safe is not None else None

        # Get category ID from slug (needed for both resume and creation paths)
        category_id = await _get_category_id_by_slug(categoria_slug)
        if not category_id:
            logger.error(
                "auto_create_case_category_not_found",
                categoria_slug=categoria_slug,
            )
            return current_context

        # Extract tariff data if available
        tarifa_calculada = current_context.get("tarifa_calculada")
        tarifa_amount = None
        tier_id = None

        if tarifa_calculada:
            if isinstance(tarifa_calculada, str):
                try:
                    tarifa_calculada = json.loads(tarifa_calculada)
                except (ValueError, TypeError):
                    pass
            if isinstance(tarifa_calculada, dict):
                datos = tarifa_calculada.get("datos", {})
                tarifa_amount = datos.get("price")
                tier_id = datos.get("tier_id")

        # -----------------------------------------------------------------------
        # Delegate to the shared idempotent helper.
        # It handles: duplicate detection (partial unique index for particulars),
        # race conditions (INSERT ON CONFLICT DO NOTHING), and creation.
        # -----------------------------------------------------------------------
        try:
            case, created = await get_or_create_active_case(
                user_id=user_id_safe_str,
                conversation_id=conversation_id,
                category_id=category_id,
                element_codes=element_codes,
                tariff_tier_id=tier_id,
                tariff_amount=tarifa_amount,
                client_type=client_type_safe,
            )
        except RuntimeError:
            logger.error(
                "auto_create_case_helper_failed",
                conversation_id=conversation_id,
                exc_info=True,
            )
            return current_context

        # -----------------------------------------------------------------------
        # Path A: Existing case was found (created=False)
        # -----------------------------------------------------------------------
        if not created:
            logger.info(
                "auto_create_case_found_existing",
                case_id=str(case.id),
                conversation_id=conversation_id,
                same_conversation=case.conversation_id == conversation_id,
                client_type=client_type_safe,
            )

            # ------------------------------------------------------------------
            # For PARTICULARES: if the existing case belongs to a DIFFERENT
            # conversation, this means they started a new quote but already have
            # an open expediente elsewhere. Block the creation and surface the
            # conflict so the LLM can inform the user.
            # ------------------------------------------------------------------
            if (
                client_type_safe != "professional"
                and case.conversation_id != conversation_id
            ):
                created_at_str = (
                    case.created_at.strftime("%d/%m/%Y a las %H:%M")
                    if case.created_at
                    else "fecha desconocida"
                )
                status_desc = {
                    "collecting": "en proceso de recolección de datos",
                    "pending_images": "pendiente de imágenes",
                }.get(case.status, case.status)

                logger.warning(
                    "auto_create_case_blocked_particular",
                    existing_case_id=str(case.id),
                    existing_conversation_id=case.conversation_id,
                    new_conversation_id=conversation_id,
                    client_type=client_type_safe,
                )

                # Inject blocking message as case_instructions so the LLM
                # reads it and informs the user without creating a new case.
                # NOTE: case_id is NOT exposed to the LLM — internal use only.
                block_instructions = (
                    "⚠️ EXPEDIENTE BLOQUEADO — NO CREAR EXPEDIENTE NUEVO\n\n"
                    "El usuario ya tiene un expediente activo:\n"
                    f"- Estado: {status_desc}\n"
                    f"- Creado: {created_at_str}\n\n"
                    "Los particulares solo pueden tener UN expediente activo a la vez.\n\n"
                    "DEBES informar al usuario y ofrecerle DOS opciones:\n"
                    "1. Retomar el expediente activo (retomar donde lo dejó)\n"
                    "2. Cancelar el expediente actual con cancelar_expediente() "
                    "y luego iniciar uno nuevo.\n\n"
                    "NO llames a iniciar_expediente() ni crees nada nuevo. "
                    "NO preguntes datos personales ni de vehículo. "
                    "Primero resuelve el conflicto con el usuario."
                )

                return {
                    **current_context,
                    "case_instructions": block_instructions,
                    "blocked_existing_case_id": str(case.id),
                    "expediente_sub_mode": COLLECT_ELEMENT_DATA,
                }

            # ------------------------------------------------------------------
            # Same conversation (or professional): resume the existing case
            # ------------------------------------------------------------------
            codes = case.element_codes or element_codes
            category_id_str = str(case.category_id) if case.category_id else None
            tier_id_str = str(case.tariff_tier_id) if case.tariff_tier_id else None
            tariff_amount_val = (
                float(case.tariff_amount) if case.tariff_amount else None
            )

            # Load base doc descriptions from DB/cache for this category
            (
                resume_base_doc_descriptions,
                resume_category_data,
            ) = await _load_base_doc_descriptions(categoria_slug)
            resume_sub_mode = current_context.get(
                "expediente_sub_mode",
                COLLECT_ELEMENT_DATA,
            )
            hydrated_context = await _hydrate_case_context_from_db(
                case,
                case.user,
                resume_sub_mode,
            )

            # Build FSM state for existing case so tools work immediately
            existing_fsm = {
                "case_collection": {
                    "step": hydrated_context.get(
                        "fsm_step", CollectionStep.COLLECT_ELEMENT_DATA.value
                    ),
                    "case_id": str(case.id),
                    "category_slug": categoria_slug,
                    "category_id": category_id_str,
                    "element_codes": codes,
                    "current_element_index": 0,
                    "element_phase": "photos",
                    "element_data_status": {code: "pending" for code in codes},
                    "base_docs_received": hydrated_context.get(
                        "base_docs_received", False
                    ),
                    "base_doc_descriptions": resume_base_doc_descriptions,
                    "received_images": [],
                    "tariff_tier_id": tier_id_str,
                    "tariff_amount": tariff_amount_val,
                    "taller_propio": hydrated_context.get("taller_propio"),
                    "taller_data": hydrated_context.get("taller_data"),
                    "retry_count": 0,
                }
            }

            return {
                **current_context,
                "case_id": str(case.id),
                "category_id": category_id_str,
                "category_slug": categoria_slug,
                "element_codes": codes,
                "current_element_index": 0,
                "element_phase": "photos",
                "element_data_status": {code: "pending" for code in codes},
                "base_docs_received": hydrated_context.get("base_docs_received", False),
                "base_doc_descriptions": resume_base_doc_descriptions,
                "category_data": resume_category_data
                or current_context.get("category_data"),
                "personal_data": hydrated_context.get("personal_data", {}),
                "vehicle_data": hydrated_context.get("vehicle_data", {}),
                "taller_propio": hydrated_context.get("taller_propio"),
                "taller_data": hydrated_context.get("taller_data"),
                "tariff_tier_id": tier_id_str,
                "tariff_amount": tariff_amount_val,
                "received_images": [],
                "expediente_intro_sent": current_context.get(
                    "expediente_intro_sent", True
                ),
                "_fsm_state_init": existing_fsm,
                "expediente_sub_mode": resume_sub_mode,
            }

        # -----------------------------------------------------------------------
        # Path B: New case was created (created=True)
        # -----------------------------------------------------------------------
        case_id = case.id

        # Get base documentation descriptions for this category
        base_doc_descriptions: list[str] = []
        category_data: dict[str, Any] | None = None
        try:
            from agent.services.tarifa_service import get_tarifa_service

            tarifa_service = get_tarifa_service()
            category_data = await tarifa_service.get_category_data(categoria_slug)
            if category_data and category_data.get("base_documentation"):
                base_doc_descriptions = [
                    bd["description"] for bd in category_data["base_documentation"]
                ]
        except Exception as e:
            logger.warning(
                "auto_create_case_base_docs_failed",
                error=str(e),
                categoria_slug=categoria_slug,
            )

        # Pre-populate personal data from existing user profile
        from agent.tools.case_tools import _load_user_data_for_fsm

        prefilled_personal_data = await _load_user_data_for_fsm(user_id_safe_str) or {}

        # NOTE: We intentionally do NOT inject phone here. The WhatsApp number
        # is authoritative and already stored in User.phone. Including it in
        # prefilled_personal_data causes the LLM to label it as "Teléfono" in the
        # prefilled summary, which confuses the LLM when the user sends their data
        # as a comma-separated list (e.g., "Pepe, 623226544, pepe@...") — the LLM
        # sees the phone already logged and misidentifies the next number as phone
        # instead of DNI, then asks for the DNI separately.

        first_element = element_codes[0] if element_codes else None

        # R1 + P2.4: Resolve element codes → human-readable display names.
        # PRIMARY: Use _confirmed_display_names from elementos_confirmados
        # (populated earlier in this method from the rich variant handoff data).
        # FALLBACK: Batch DB query via _resolve_element_display_names().
        # This ensures variant-resolved names (e.g. "Suspensión delantera"
        # instead of "SUSPENSION") are used when available from presupuesto.
        if _confirmed_display_names:
            element_display_names = _confirmed_display_names
            # Supplement with DB names for any codes not in confirmed data
            # (defensive: shouldn't happen but ensures no gaps)
            missing_codes = [c for c in element_codes if c not in element_display_names]
            if missing_codes:
                db_names = await _resolve_element_display_names(
                    missing_codes, category_id
                )
                element_display_names.update(db_names)
        else:
            # Backward compat: full DB resolution (original R1 path)
            element_display_names = await _resolve_element_display_names(
                element_codes, category_id
            )
        first_element_display = (
            element_display_names.get(first_element, first_element)
            if first_element
            else None
        )

        logger.info(
            "auto_created_case_for_expediente",
            case_id=str(case_id),
            conversation_id=conversation_id,
            element_count=len(element_codes),
            categoria_slug=categoria_slug,
            has_base_docs=len(base_doc_descriptions) > 0,
        )

        # Build FSM state for tool compatibility
        # Tools read state["fsm_state"]["case_collection"]
        initial_fsm_state = {
            "case_collection": {
                "step": "collect_element_data",
                "case_id": str(case_id),
                "category_slug": categoria_slug,
                "category_id": category_id,
                "element_codes": element_codes,
                "current_element_index": 0,
                "element_phase": "photos",
                "element_data_status": {code: "pending" for code in element_codes},
                "base_docs_received": False,
                "base_doc_descriptions": base_doc_descriptions,
                "received_images": [],
                "tariff_tier_id": tier_id,
                "tariff_amount": tarifa_amount,
                "taller_propio": None,
                "taller_data": None,
                "retry_count": 0,
            }
        }

        # Build pre-filled data context for LLM
        prefilled_context = ""
        if prefilled_personal_data:
            filled_fields = {k: v for k, v in prefilled_personal_data.items() if v}
            if filled_fields:
                field_labels = {
                    "nombre": "Nombre",
                    "apellidos": "Apellidos",
                    "dni_cif": "DNI/CIF",
                    "email": "Email",
                    # "telefono" intentionally omitted — already in User.phone from WhatsApp
                    "domicilio_calle": "Calle",
                    "domicilio_localidad": "Localidad",
                    "domicilio_provincia": "Provincia",
                    "domicilio_cp": "CP",
                }
                filled_summary = ", ".join(
                    f"{field_labels.get(k, k)}: {v}"
                    for k, v in filled_fields.items()
                    if k != "itv_nombre"
                )
                prefilled_context = (
                    f"\nDATOS PERSONALES YA REGISTRADOS DEL USUARIO:\n"
                    f"  {filled_summary}\n"
                    f"Cuando llegues a COLLECT_PERSONAL, presenta estos datos al usuario "
                    f"y pregunta si son correctos antes de pedir nuevos.\n"
                )

        # Build per-element photo instructions from tarifa_calculada
        # NOTE: We inject instructions for HOW to ask for photos (user-instruction text
        # from the DB), NOT example image captions from enviar_imagenes_ejemplo().
        # enviar_imagenes_ejemplo() captions should remain the source of truth for
        # example photos — what's injected here is the instructional text only,
        # to guide the LLM in each element's photo-request phrasing.
        element_photo_instructions = _build_element_photo_instructions(
            current_context.get("tarifa_calculada"),
        )

        # TASK-10: Build introductory overview message.
        # When EXPEDIENTE_V2_ENABLED=True the canonical EXPEDIENTE_INTRO_MESSAGE
        # is stored in mode_context["expediente_intro_message"] and prepended
        # verbatim to the first LLM response in _process_message — emitted
        # exactly once, never paraphrased by the LLM.
        # When V2 is disabled, embed the intro in the LLM instruction as before.
        _v2_for_intro = get_settings().EXPEDIENTE_V2_ENABLED
        _expediente_intro_msg: str | None = (
            EXPEDIENTE_INTRO_MESSAGE if _v2_for_intro else None
        )

        case_instructions = build_new_expediente_case_instructions(
            first_element_display=first_element_display or "elemento",
            total_elements=len(element_codes),
            prefilled_context=prefilled_context,
            element_photo_instructions=element_photo_instructions,
            intro_already_sent=_v2_for_intro,
            auto_created=True,
        )

        result_ctx: dict[str, Any] = {
            **current_context,
            "case_id": str(case_id),
            "category_id": category_id,
            "category_slug": categoria_slug,
            "element_codes": element_codes,
            # R1 + P2.4: human-readable display names for element codes.
            # dict[str, str] mapping code → display name.
            # PRIMARY source: elementos_confirmados rich variant data (from presupuesto).
            # FALLBACK: DB query via _resolve_element_display_names().
            # Falls back to {} if neither source available (non-blocking).
            "element_display_names": element_display_names,
            "current_element_index": 0,
            "element_phase": "photos",
            "element_data_status": {code: "pending" for code in element_codes},
            "base_docs_received": False,
            "base_doc_descriptions": base_doc_descriptions,
            "category_data": category_data,
            "personal_data": prefilled_personal_data,
            "vehicle_data": {},
            "taller_propio": None,
            "taller_data": None,
            "tariff_tier_id": tier_id,
            "tariff_amount": float(tarifa_amount) if tarifa_amount else None,
            "received_images": [],
            # Always mark intro as sent when creating a new expediente.
            # - If V2 enabled: intro sent via expediente_intro_message prepend
            # - If V2 disabled: intro sent via LLM instructions (case_instructions)
            # In both cases, the safety net should NOT fire.
            "expediente_intro_sent": True,
            "case_instructions": case_instructions,
            # Carry FSM state so _run_llm_loop can inject it into
            # the ContextVar BEFORE tools execute.  Without this,
            # element_data_tools fail with "case_collection not found".
            "_fsm_state_init": initial_fsm_state,
            "expediente_sub_mode": current_context.get(
                "expediente_sub_mode",
                COLLECT_ELEMENT_DATA,
            ),
        }
        # TASK-10: Carry intro message for V2 (consumed once in _process_message)
        if _expediente_intro_msg:
            result_ctx["expediente_intro_message"] = _expediente_intro_msg
        if get_settings().EXPEDIENTE_V2_ENABLED and element_codes:
            await get_case_image_batch_service().open_for_scope(
                case_id=str(case_id),
                expediente_sub_mode=COLLECT_ELEMENT_DATA,
                element_code=element_codes[0],
                opened_at=datetime.now(UTC),
            )
        return result_ctx

    # ------------------------------------------------------------------
    # Orphaned expediente recovery (checkpoint-expired cases)
    # ------------------------------------------------------------------

    async def _build_recovery_context(
        self,
        conversation_id: str,
        recovery_data: dict[str, Any],
        current_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build mode_context for an orphaned expediente that was detected by
        preprocess_node after the Redis checkpoint expired.

        The recovery_data dict (injected by preprocess_node) already contains
        all DB data we need: case_id, element_codes, element_data_status, etc.

        This method:
        1. Builds the FSM state so element_data_tools work on the first turn.
        2. Crafts a warm ``case_instructions`` message that guides the LLM to
           offer the user a choice: resume the existing expediente or start fresh.
        3. Updates the case's conversation_id in DB so future images are
           attributed to the correct case even from the new Chatwoot thread.

        Args:
            conversation_id: New conversation ID (post-checkpoint expiry)
            recovery_data: Dict from _try_recover_orphaned_expediente()
            current_context: Current mode_context (typically empty at this point)

        Returns:
            Initialized mode_context ready for the first LLM turn.
        """
        case_id = recovery_data.get("case_id", "")
        category_slug = recovery_data.get("category_slug") or ""
        category_id = recovery_data.get("category_id")
        element_codes = recovery_data.get("element_codes") or []
        element_data_status = recovery_data.get("element_data_status") or {}
        tariff_tier_id = recovery_data.get("tariff_tier_id")
        tariff_amount = recovery_data.get("tariff_amount")
        inferred_sub_mode = recovery_data.get("inferred_sub_mode", COLLECT_ELEMENT_DATA)
        created_at_str = recovery_data.get("created_at_str", "fecha desconocida")

        # Load base doc descriptions from DB/cache for this category
        (
            recovery_base_doc_descriptions,
            recovery_category_data,
        ) = await _load_base_doc_descriptions(category_slug)

        # Map element_data_status from DB (sparse, only elements with CaseElementData)
        # to full status dict covering all element_codes.
        full_status: dict[str, str] = {}
        for code in element_codes:
            full_status[code] = element_data_status.get(code, "pending_photos")

        # Determine current_element_index: first element not yet "completed"
        current_index = 0
        current_phase = "photos"
        for idx, code in enumerate(element_codes):
            s = full_status.get(code, "pending_photos")
            if s != "completed":
                current_index = idx
                current_phase = "data" if s == "pending_data" else "photos"
                break

        # Describe progress for the LLM's resume greeting
        completed_count = sum(1 for s in full_status.values() if s == "completed")
        total_count = len(element_codes)
        # R1: resolve element codes to human-readable names for the recovery message.
        # category_id comes from recovery_data; falls back to {} on error.
        _recovery_display_names = await _resolve_element_display_names(
            [c for c in element_codes if isinstance(c, str)],
            str(category_id) if category_id else "",
        )
        _resolved_elements = [
            _recovery_display_names.get(str(code), str(code))
            for code in element_codes
            if code is not None
        ]
        elementos_str = (
            ", ".join(_resolved_elements) if _resolved_elements else "desconocidos"
        )
        progress_desc = f"{completed_count}/{total_count} elementos completados"

        # Determine what phase to resume (human-readable for LLM)
        sub_mode_labels = {
            COLLECT_ELEMENT_DATA: "Fotos y datos de elementos",
            COLLECT_BASE_DOCS: "Documentación base del vehículo",
            COLLECT_PERSONAL: "Datos personales",
            COLLECT_VEHICLE: "Datos del vehículo",
            COLLECT_WORKSHOP: "Certificado del taller",
            REVIEW_SUMMARY: "Revisión final",
        }
        resume_phase_label = sub_mode_labels.get(inferred_sub_mode, inferred_sub_mode)

        hydrated_context: dict[str, Any] = {}

        # Update conversation_id in DB (best-effort) so image assignments
        # from the new thread are linked to the correct case.
        try:
            import uuid as _uuid
            from database.connection import get_async_session
            from database.models import Case

            async with get_async_session() as session:
                case_obj = await session.get(Case, _uuid.UUID(case_id))
                if case_obj:
                    hydrated_context = await _hydrate_case_context_from_db(
                        case_obj,
                        case_obj.user,
                        inferred_sub_mode,
                    )
                if case_obj and case_obj.conversation_id != conversation_id:
                    old_conv_id = case_obj.conversation_id
                    case_obj.conversation_id = conversation_id
                    await session.commit()
                    logger.info(
                        "recovery_updated_case_conversation_id",
                        case_id=case_id,
                        old_conversation_id=old_conv_id,
                        new_conversation_id=conversation_id,
                    )
        except Exception as e:
            logger.warning(
                "recovery_failed_to_update_conversation_id",
                case_id=case_id,
                conversation_id=conversation_id,
                error=str(e),
            )

        # Build FSM state for tool compatibility (tools read state["fsm_state"])
        recovered_fsm = {
            "case_collection": {
                "step": hydrated_context.get(
                    "fsm_step", CollectionStep.COLLECT_ELEMENT_DATA.value
                ),
                "case_id": case_id,
                "category_slug": category_slug,
                "category_id": category_id,
                "element_codes": element_codes,
                "current_element_index": current_index,
                "element_phase": current_phase,
                "element_data_status": full_status,
                "base_docs_received": hydrated_context.get("base_docs_received", False),
                "base_doc_descriptions": recovery_base_doc_descriptions,
                "received_images": [],
                "tariff_tier_id": tariff_tier_id,
                "tariff_amount": tariff_amount,
                "taller_propio": hydrated_context.get("taller_propio"),
                "taller_data": hydrated_context.get("taller_data"),
                "retry_count": 0,
            }
        }

        # Craft a warm recovery instruction for the LLM.
        # The LLM will greet the user, explain the situation, and offer two options.
        # This is injected as <CASE_CONTEXT> into the system prompt.
        case_instructions = (
            build_resume_expediente_case_instructions(
                elementos_str=elementos_str,
                progress_desc=progress_desc,
                resume_phase_label=resume_phase_label or inferred_sub_mode,
                created_at_str=created_at_str,
            )
            + "\nIMPORTANTE: El expediente YA EXISTE en la base de datos. "
            "NO llames a iniciar_expediente()."
        )

        logger.info(
            "built_recovery_context_for_expediente",
            case_id=case_id,
            conversation_id=conversation_id,
            inferred_sub_mode=inferred_sub_mode,
            progress=progress_desc,
            element_count=total_count,
        )

        return {
            **current_context,
            "case_id": case_id,
            "category_id": category_id,
            "category_slug": category_slug,
            "element_codes": element_codes,
            # R1: human-readable display names resolved from DB (code → element.name).
            # Used by loader.py to display "ELEMENTO ACTUAL" with human name.
            "element_display_names": _recovery_display_names,
            "current_element_index": current_index,
            "element_phase": current_phase,
            "element_data_status": full_status,
            "base_docs_received": hydrated_context.get("base_docs_received", False),
            "base_doc_descriptions": recovery_base_doc_descriptions,
            "category_data": recovery_category_data,
            "personal_data": hydrated_context.get("personal_data", {}),
            "vehicle_data": hydrated_context.get("vehicle_data", {}),
            "taller_propio": hydrated_context.get("taller_propio"),
            "taller_data": hydrated_context.get("taller_data"),
            "tariff_tier_id": tariff_tier_id,
            "tariff_amount": tariff_amount,
            "received_images": [],
            "expediente_intro_sent": current_context.get("expediente_intro_sent", True),
            "case_instructions": case_instructions,
            "_fsm_state_init": recovered_fsm,
            "expediente_sub_mode": inferred_sub_mode,
            # Clear the recovery signal so it doesn't re-trigger on next turns
            "pending_recovery_case": None,
        }

    # ------------------------------------------------------------------
    # Sub-mode handlers
    # ------------------------------------------------------------------

    async def _handle_element_data(
        self,
        message: str,
        state: ConversationState,
        mode_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Handle COLLECT_ELEMENT_DATA sub-mode.

        Per-element flow:
        1. Send example images (enviar_imagenes_ejemplo)
        2. User sends photos → confirmar_fotos_elemento()
        3. Ask for technical data → guardar_datos_elemento()
        4. completar_elemento_actual() → next element or COLLECT_BASE_DOCS
        """
        # Reset intra-turn dedup set for element example images.
        from agent.tools.image_tools import _clear_element_images_sent_this_turn

        _clear_element_images_sent_this_turn()

        conversation_id = state.get("conversation_id", "unknown")

        # TASK-05: Initialize per-element 7-state machine when EXPEDIENTE_V2_ENABLED.
        # Called on every turn but _initialize_element_states() is idempotent —
        # it only creates entries for elements that don't have one yet.
        _v2_settings = get_settings()
        if _v2_settings.EXPEDIENTE_V2_ENABLED:
            _el_codes: list[str] = mode_context.get("element_codes") or []
            if _el_codes:
                _initialize_element_states(mode_context, _el_codes)
                logger.debug(
                    "element_states_ready",
                    conversation_id=conversation_id,
                    element_count=len(_el_codes),
                )

        # Layer A: deterministic guard for photo completion intent.
        # If the user says "listo" / "ya" / "enviadas" etc. while element_phase=="photos",
        # call confirmar_fotos_elemento() directly before the LLM loop runs.
        # mode_context is updated in-place so the LLM sees the advanced phase.
        _guard_fired = await self._guard_photo_completion_intent(
            user_message=message,
            mode_context=mode_context,
            state=cast(dict[str, Any], state),
            conversation_id=conversation_id,
        )
        if _guard_fired:
            # Signal to the LLM loop that confirmar_fotos_elemento was already called
            # deterministically. This prevents the constraint validator from incorrectly
            # flagging narration of the photo confirmation step as a constraint violation.
            mode_context["_guard_photo_fired_this_turn"] = True

        # ── V2: Pre-populate collection context for prompt injection ─────────
        # When EXPEDIENTE_V2_ENABLED, fetch a fresh CollectionContext from the
        # DB before the LLM loop runs.  This context is stored in mode_context
        # under "v2_collection_context" so that assemble_system_prompt() can
        # replace the {COLLECTION_CONTEXT} placeholder in
        # expediente_documentacion_elementos.md with live data.
        if _v2_settings.EXPEDIENTE_V2_ENABLED:
            _case_id_v2: str | None = mode_context.get("case_id")
            _el_codes_v2: list[str] = mode_context.get("element_codes") or []
            _cat_id_v2: str | None = mode_context.get("category_id")
            if _case_id_v2 and _el_codes_v2:
                try:
                    from agent.services.element_state_service import (
                        get_element_state_service as _get_ess_handle,
                    )

                    _ess_handle = _get_ess_handle()
                    _collection_ctx = await _ess_handle.get_collection_context(
                        _case_id_v2, _el_codes_v2, _cat_id_v2
                    )
                    mode_context["v2_collection_context"] = _collection_ctx.to_dict()
                    logger.debug(
                        "element_data_collection_context_populated",
                        conversation_id=conversation_id,
                        current_element=(
                            (_collection_ctx.current_element or {}).get("code")
                        ),
                        completed=_collection_ctx.progress.get("completed", 0),
                        total=_collection_ctx.progress.get("total", 0),
                    )
                except Exception as _ctx_err:
                    # Non-fatal: prompt will show fallback placeholder text
                    logger.warning(
                        "element_data_collection_context_failed",
                        conversation_id=conversation_id,
                        error=str(_ctx_err),
                    )

        tools = _get_element_data_tools()
        return await self._run_llm_loop(
            message=message,
            state=state,
            mode_context=mode_context,
            tools=tools,
            sub_mode_name="COLLECT_ELEMENT_DATA",
        )

    async def _handle_base_docs(
        self,
        message: str,
        state: ConversationState,
        mode_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Handle COLLECT_BASE_DOCS sub-mode.

        User sends base documentation (ficha técnica, permiso, vistas).
        Tool: confirmar_documentacion_base()
        """
        tools = _get_base_docs_tools()
        return await self._run_llm_loop(
            message=message,
            state=state,
            mode_context=mode_context,
            tools=tools,
            sub_mode_name="COLLECT_BASE_DOCS",
        )

    async def _handle_personal(
        self,
        message: str,
        state: ConversationState,
        mode_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Handle COLLECT_PERSONAL sub-mode.

        Collect personal data: nombre, apellidos, email, teléfono,
        DNI/CIF, domicilio, ITV.

        Tool: actualizar_datos_expediente(datos_personales={...})
        """
        tools = _get_personal_tools()
        return await self._run_llm_loop(
            message=message,
            state=state,
            mode_context=mode_context,
            tools=tools,
            sub_mode_name="COLLECT_PERSONAL",
        )

    async def _handle_vehicle(
        self,
        message: str,
        state: ConversationState,
        mode_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Handle COLLECT_VEHICLE sub-mode.

        Collect vehicle data: marca, modelo, año, matrícula, bastidor.

        Tool: actualizar_datos_expediente(datos_vehiculo={...})
        """
        tools = _get_vehicle_tools()
        return await self._run_llm_loop(
            message=message,
            state=state,
            mode_context=mode_context,
            tools=tools,
            sub_mode_name="COLLECT_VEHICLE",
        )

    async def _handle_workshop(
        self,
        message: str,
        state: ConversationState,
        mode_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Handle COLLECT_WORKSHOP sub-mode.

        Ask if user provides own workshop or uses MSI.
        If own workshop: collect workshop data.

        Tool: actualizar_datos_taller()
        """
        tools = _get_workshop_tools()
        return await self._run_llm_loop(
            message=message,
            state=state,
            mode_context=mode_context,
            tools=tools,
            sub_mode_name="COLLECT_WORKSHOP",
        )

    async def _handle_review(
        self,
        message: str,
        state: ConversationState,
        mode_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Handle REVIEW_SUMMARY sub-mode.

        Present summary of all collected data.
        User confirms → finalizar_expediente()
        User rejects → editar_expediente()

        Tools: finalizar_expediente(), editar_expediente()
        """
        tools = _get_review_tools()
        return await self._run_llm_loop(
            message=message,
            state=state,
            mode_context=mode_context,
            tools=tools,
            sub_mode_name="REVIEW_SUMMARY",
        )

    # ------------------------------------------------------------------
    # LLM loop (shared across all sub-modes)
    # ------------------------------------------------------------------

    async def _run_llm_loop(
        self,
        message: str,
        state: ConversationState,
        mode_context: dict[str, Any],
        tools: list,
        sub_mode_name: str,
    ) -> dict[str, Any]:
        """
        Run the LLM tool-calling loop for a sub-mode.

        Same pattern as other modes (viabilidad, presupuesto, consulta).
        """
        conversation_id = state.get("conversation_id", "unknown")
        messages = state.get("messages", [])

        active_transition_marker = self._get_active_transition_marker(
            mode_context,
            sub_mode_name,
        )
        if active_transition_marker:
            self._logger.info(
                "expediente_transition_marker_consumed",
                from_sub_mode=active_transition_marker.get("from_sub_mode"),
                to_sub_mode=active_transition_marker.get("to_sub_mode"),
                tool=active_transition_marker.get("tool_name"),
                sub_mode=sub_mode_name,
                conversation_id=conversation_id,
            )

        # ── 1. Build system prompt ───────────────────────────────────────
        client_context = self._build_client_context(state)

        # ── Certainty guardrails: initialise per-turn envelope ───────────────
        # Initialised here (before prompt assembly) so _guardrails_enabled is
        # available both when building prompt_mode_context and inside the tool loop.
        # We keep a *current-turn* envelope that accumulates evidence from every
        # tool call in this turn.  It starts fresh each turn (conservative: nothing
        # confirmed yet) with the current sub_mode already set.
        _guardrails_settings = get_settings()
        _guardrails_enabled: bool = (
            _guardrails_settings.EXPEDIENTE_CERTAINTY_GUARDRAILS_ENABLED
        )
        _current_sub_mode_lc: str = sub_mode_name.lower()
        # The previous turn's envelope (persisted in mode_context) is loaded for
        # reference but NOT merged into the current turn — each turn starts clean.
        _prev_envelope: CertaintyEnvelope = load_envelope(
            mode_context, _current_sub_mode_lc
        )
        _turn_envelope: CertaintyEnvelope = CertaintyEnvelope.empty(
            sub_mode=_current_sub_mode_lc
        )

        prompt_mode_context = dict(mode_context)
        if active_transition_marker:
            prompt_mode_context["expediente_transition_marker"] = (
                active_transition_marker
            )

        # ── Certainty guardrails: inject previous turn's envelope into prompt ──
        # The *previous* turn's envelope is what the LLM should use for context.
        # The current turn's envelope is built during the tool loop below.
        if _guardrails_enabled:
            _cert_ctx = build_prompt_certainty_context(_prev_envelope)
            prompt_mode_context.update(_cert_ctx)

        # Map sub-mode to prompt key (matching MODE_MODULES in loader.py)
        sub_mode_to_prompt = {
            "COLLECT_ELEMENT_DATA": "EXPEDIENTE_DOCUMENTACION_ELEMENTOS",
            "COLLECT_BASE_DOCS": "EXPEDIENTE_DOCUMENTACION_BASE",
            "COLLECT_PERSONAL": "EXPEDIENTE_DATOS_PERSONALES",
            "COLLECT_VEHICLE": "EXPEDIENTE_DATOS_VEHICULO",
            "COLLECT_WORKSHOP": "EXPEDIENTE_TALLER",
            "REVIEW_SUMMARY": "EXPEDIENTE_REVISION",
        }
        mode_prompt_name = sub_mode_to_prompt.get(
            sub_mode_name, "EXPEDIENTE_DOCUMENTACION_ELEMENTOS"
        )

        system_prompt = assemble_system_prompt(
            mode=mode_prompt_name,
            mode_context=prompt_mode_context,
            client_context=client_context,
        )

        # Inject case_instructions if present (from _auto_create_case)
        # This tells the LLM that the case is already created and what to do
        case_instructions = mode_context.get("case_instructions")
        if case_instructions:
            system_prompt += (
                f"\n\n---\n\n<CASE_CONTEXT>\n{case_instructions}\n</CASE_CONTEXT>"
            )
            # Clear after first use (avoid repeating on every turn)
            mode_context.pop("case_instructions", None)

        # ── 2. Build LLM messages ───────────────────────────────────────
        # Check for images and prepend context if present
        incoming_attachments = state.get("incoming_attachments", [])
        image_count = len(incoming_attachments)
        if image_count > 0:
            image_notice = f"[El usuario ha enviado {image_count} imagen(es) junto con este mensaje]\n\n"
        else:
            image_notice = ""

        llm_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]
        llm_messages.extend(format_messages_for_llm(messages))
        llm_messages.append(
            {
                "role": "user",
                "content": f"<USER_MESSAGE>\n{image_notice}{message}\n</USER_MESSAGE>",
            }
        )

        # ── 3. Configure ContextVars for tool execution ───────────────────
        # CRITICAL: EXPEDIENTE uses 30+ tools that need state via ContextVars.
        # IMPORTANT: Preserve nested structure - tools read from state["mode_context"]
        full_state = dict(cast(dict[str, Any], state))
        full_state["mode_context"] = mode_context  # Preserve nested structure

        # Inject FSM state built by _auto_create_case so that
        # element_data_tools can read state["fsm_state"]["case_collection"].
        # Without this, the first turn after auto-creation fails because
        # the ContextVar has no fsm_state and tools raise KeyError.
        fsm_init = mode_context.pop("_fsm_state_init", None)
        if fsm_init:
            full_state["fsm_state"] = fsm_init
            logger.info(
                "injected_fsm_state_from_auto_create",
                case_id=fsm_init.get("case_collection", {}).get("case_id"),
                conversation_id=conversation_id,
            )

        set_current_state(full_state)
        set_current_state_for_image_tools(full_state)

        # ── 4. Get LLM with tools ───────────────────────────────────────
        llm = self._get_llm(tools)

        # ── 5. Tool calling loop ─────────────────────────────────────────
        # Pre-compile regex for false-completion guard (outside loop for efficiency)
        _FALSE_COMPLETION_RE = re.compile(
            r"expediente\s+(?:est[aá]\s+)?(?:complet|enviad|finaliz|cerrad|tramitad|list)"
            r"|(?:tu|el|su)\s+(?:caso|expediente)\s+(?:ha\s+sido|est[aá])\s+(?:enviad|complet|cerrad|registrad)"
            r"|hemos\s+(?:terminad|completad|finaliz|cerrad)\s+(?:el\s+)?(?:expediente|caso|proceso)"
            r"|ya\s+(?:hemos\s+)?(?:terminad|completad)\s+(?:el\s+)?(?:expediente|proceso)"
            r"|todo\s+(?:est[aá]|listo)\s+(?:completad|guardad|registrad)",
            re.IGNORECASE,
        )
        ai_response = ""
        context_updates: dict[str, Any] = {}
        tools_called: set[str] = set()
        # RC-2: If photo guard fired before the LLM loop, register the tool it called
        # so the constraint validator knows it already ran deterministically this turn.
        if mode_context.pop("_guard_photo_fired_this_turn", False):
            tools_called.add("confirmar_fotos_elemento")
            self._logger.debug(
                "guard_tool_registered_in_tools_called",
                tool="confirmar_fotos_elemento",
                conversation_id=conversation_id,
            )
        pending_images: dict[str, Any] | None = None
        all_applied_flags: dict[str, Any] = {}
        validation_retries = 0
        MAX_VALIDATION_RETRIES = 2
        _case_finalized: bool = (
            False  # FASE 3: set True when case_finalized guard fires
        )

        # Phase 3: Initialize retry state for validation error recovery
        retry_state = state.get("retry_state", create_empty_retry_state())

        # Latency gating: use configurable iteration limit when flag is ON
        settings = get_settings()
        _effective_max_iterations = MAX_TOOL_ITERATIONS
        if settings.ENABLE_LATENCY_GATING:
            _effective_max_iterations = settings.MAX_TOOL_ITERATIONS_EXPEDIENTE
        _loop_hit_max: bool = False

        # ── Init per-turn dedup cache ────────────────────────────────────────
        # Activates the guard in base_mode._execute_and_log_tool() for this turn.
        # Reset to None in the finally block (even on exception) to prevent
        # stale cache entries leaking into the next turn.
        self._tool_dedup_cache = {}

        try:
            for iteration in range(_effective_max_iterations):
                try:
                    response = await llm.ainvoke(llm_messages)
                except Exception as llm_error:
                    response = await self._invoke_with_fallback(
                        llm_messages,
                        tools,
                        llm_error,
                        conversation_id,
                    )

                # Track token usage
                await self._track_token_usage(conversation_id, response)

                # Check for tool calls
                tool_calls = getattr(response, "tool_calls", None)

                if not tool_calls:
                    ai_response = response.content or ""

                    # Empty LLM response retry: if the LLM returned empty
                    # content AND no tool calls (e.g. DeepSeek HTTP 200 with
                    # empty body), retry once with a reprompt instead of
                    # breaking out to the safety-net generic error.
                    if not ai_response and iteration == 0:
                        self._logger.warning(
                            "empty_llm_response_retry",
                            iteration=iteration,
                            conversation_id=conversation_id,
                        )
                        llm_messages.append(
                            {
                                "role": "system",
                                "content": (
                                    "[SYSTEM]: Tu respuesta anterior estuvo vacía. "
                                    "Por favor, responde al mensaje del usuario. "
                                    "Si necesitas información, usa las herramientas disponibles."
                                ),
                            }
                        )
                        continue

                    # ── Guard: false completion detection ───────────────────────
                    # Detect if the LLM declared the expediente as complete/sent
                    # in any sub-mode BEFORE REVIEW_SUMMARY, without having called
                    # finalizar_expediente(). This prevents the agent from lying to
                    # the user about the state of the case.
                    if (
                        ai_response
                        and sub_mode_name != REVIEW_SUMMARY
                        and "finalizar_expediente" not in tools_called
                        and validation_retries < MAX_VALIDATION_RETRIES
                        and _FALSE_COMPLETION_RE.search(str(ai_response))
                    ):
                        validation_retries += 1
                        self._logger.warning(
                            "false_completion_detected",
                            sub_mode=sub_mode_name,
                            retry=validation_retries,
                            conversation_id=conversation_id,
                        )
                        llm_messages.append(
                            {
                                "role": "system",
                                "content": (
                                    "[SISTEMA - ERROR CRÍTICO]: Has declarado que el expediente está completo "
                                    f"pero estamos en el sub-modo '{sub_mode_name}', NO en REVIEW_SUMMARY. "
                                    "NUNCA declares el expediente como completo, enviado o terminado hasta que "
                                    "el usuario haya confirmado el resumen final y hayas llamado a "
                                    "finalizar_expediente(). "
                                    "Continúa recogiendo los datos que corresponden a este sub-modo."
                                ),
                            }
                        )
                        continue

                    # Constraint validation (anti-hallucination)
                    # Task 2.1: Skip constraint validation on kickoff turns where the LLM
                    # correctly asks for data without calling any tool yet.  The sub-modes
                    # collect_base_docs, collect_personal, and collect_vehicle all begin
                    # with a first-ask turn where the agent should ask the user to provide
                    # data/images — no tool call is needed or expected.  Running the
                    # constraint validator on these no-tool turns causes false positives
                    # (e.g. images_narration_blocked firing on "envíame las fotos adjuntas").
                    _KICKOFF_SKIP_SUBMODES = {
                        COLLECT_BASE_DOCS.lower(),
                        COLLECT_PERSONAL.lower(),
                        COLLECT_VEHICLE.lower(),
                    }
                    _is_kickoff_no_tool_turn = (
                        not tools_called
                        and sub_mode_name.lower() in _KICKOFF_SKIP_SUBMODES
                    )
                    if ai_response and validation_retries < MAX_VALIDATION_RETRIES:
                        if _is_kickoff_no_tool_turn:
                            # Kickoff ask: no tools expected, skip constraint check.
                            self._logger.debug(
                                "constraint_validation_skipped_kickoff",
                                sub_mode=sub_mode_name,
                                reason="no_tools_called_on_kickoff_turn",
                            )
                            is_valid, error_injection = True, None
                        else:
                            (
                                is_valid,
                                error_injection,
                            ) = await self._validate_response_constraints(
                                ai_response,
                                list(tools_called),
                                state,
                                current_mode_context=mode_context,  # Phase 1B: use updated context
                                available_tool_names={t.name for t in tools},
                            )

                        if not is_valid and error_injection:
                            validation_retries += 1
                            self._logger.warning(
                                "constraint_retry",
                                retry=validation_retries,
                                max_retries=MAX_VALIDATION_RETRIES,
                                sub_mode=sub_mode_name,
                            )
                            # Phase 4B: Unified role "system" + IMPORTANT instruction
                            llm_messages.append(
                                {
                                    "role": "system",
                                    "content": f"[CONSTRAINT VALIDATION ERROR]: {error_injection}\n\nIMPORTANT: You MUST call the required tools to fix this issue. Do NOT generate explanatory text without tool calls.",
                                }
                            )
                            continue
                    elif ai_response and validation_retries >= MAX_VALIDATION_RETRIES:
                        # Phase 4A: Safety net — don't send hallucinated response
                        self._logger.error(
                            "constraint_retries_exhausted",
                            retries=validation_retries,
                            sub_mode=sub_mode_name,
                            conversation_id=conversation_id,
                        )
                        ai_response = "Disculpa, déjame reformularte la respuesta. ¿Podrías repetirme qué necesitas?"

                    break

                # Execute tool calls
                llm_messages.append(self._ai_message_to_dict(response))

                for tool_call in tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    tool_call_id = tool_call["id"]
                    tools_called.add(tool_name)

                    self._logger.info(
                        "tool_call",
                        tool=tool_name,
                        sub_mode=sub_mode_name,
                        iteration=iteration + 1,
                    )
                    if settings.ENABLE_LATENCY_GATING:
                        logger.info(
                            "tool_loop_iteration",
                            iteration=iteration + 1,
                            max=_effective_max_iterations,
                            mode="EXPEDIENTE",
                            tool_name=tool_name,
                        )

                    # ═══════════════════════════════════════════════════════════
                    # TASK-08: Phase-aware tool matrix enforcement
                    # Check BEFORE executing the tool. When EXPEDIENTE_V2_ENABLED
                    # is True, consult EXPEDIENTE_TOOL_MATRIX and, if the tool is
                    # blocked in the current (sub_mode, element_phase), skip
                    # execution entirely and inject a synthetic tool result.
                    # The LLM sees the blocked response and retries with the
                    # correct tool for the current phase.
                    #
                    # escalar_a_humano is NEVER blocked (safety override enforced
                    # inside _is_tool_blocked).
                    # ═══════════════════════════════════════════════════════════
                    if settings.EXPEDIENTE_V2_ENABLED:
                        _current_sub_mode_key = sub_mode_name.lower()
                        _current_element_phase: str | None = mode_context.get(
                            "element_phase"
                        )
                        _blocked = _is_tool_blocked(
                            tool_name=tool_name,
                            sub_mode=_current_sub_mode_key,
                            element_phase=_current_element_phase,
                        )
                        if _blocked:
                            logger.warning(
                                "tool_blocked_by_matrix",
                                tool=tool_name,
                                sub_mode=_current_sub_mode_key,
                                element_phase=_current_element_phase,
                                conversation_id=conversation_id,
                                iteration=iteration + 1,
                            )
                            # Inject synthetic blocked result — do NOT call the tool
                            _blocked_result = json.dumps(
                                {
                                    "blocked": True,
                                    "success": False,
                                    "message": (
                                        "Esta acción no está disponible en la fase actual. "
                                        f"El tool '{tool_name}' no se puede usar en "
                                        f"sub_mode='{_current_sub_mode_key}', "
                                        f"element_phase='{_current_element_phase}'."
                                    ),
                                }
                            )
                            llm_messages.append(
                                {
                                    "role": "tool",
                                    "content": _blocked_result,
                                    "tool_call_id": tool_call_id,
                                }
                            )
                            continue  # Let LLM see blocked result and retry
                    # ═══════════════════════════════════════════════════════════
                    # End TASK-08 tool matrix enforcement
                    # ═══════════════════════════════════════════════════════════

                    result = await self._execute_and_log_tool(
                        conversation_id=conversation_id,
                        tool_name=tool_name,
                        tool_args=tool_args,
                        tools=tools,
                        iteration=iteration + 1,
                    )

                    # ═══════════════════════════════════════════════════════════
                    # Phase 3: Validation error retry logic
                    # ═══════════════════════════════════════════════════════════
                    is_val_error, error_dict = self._is_validation_error(result)

                    if is_val_error and error_dict:  # Type guard
                        should_retry, retry_state = self._handle_validation_retry(
                            tool_name=tool_name,
                            error_dict=error_dict,
                            retry_state=retry_state,
                            llm_messages=llm_messages,
                        )

                        if should_retry:
                            # Reprompt added to llm_messages, continue LLM loop
                            self._logger.info(
                                "validation_retry_triggered",
                                tool=tool_name,
                                sub_mode=sub_mode_name,
                                retry_count=retry_state.get("retry_count"),
                                conversation_id=conversation_id,
                            )
                            break  # Exit tool loop, go to next iteration
                        else:
                            # Max retries reached - escalate
                            self._logger.warning(
                                "validation_escalation",
                                tool=tool_name,
                                sub_mode=sub_mode_name,
                                retry_count=retry_state.get("retry_count"),
                                conversation_id=conversation_id,
                            )
                            return {
                                "ai_response": self._fallback.get_validation_reprompt(
                                    retry_state, self._policy
                                ),
                                "current_mode": "ESCALATION",
                                "escalation_triggered": True,
                                "escalation_reason": "max_validation_retries",
                                "retry_state": retry_state,
                                "mode_context": mode_context,
                            }
                    # ═══════════════════════════════════════════════════════════
                    # End Phase 3 validation retry logic
                    # ═══════════════════════════════════════════════════════════

                    # S2: Reset validation retry counters after successful tool call
                    # Prevents stale errors from contaminating reprompts in later iterations
                    if retry_state.get("retry_count", 0) > 0:
                        retry_state = _reset_validation_retry_state(retry_state)

                    # REFACTOR-001: Apply tool flags BEFORE extracting context
                    # Parse result for _apply_tool_flags (handles JSON string)
                    # Defensive: some tools (e.g. escalar_a_humano) return plain
                    # text, not JSON — guard against JSONDecodeError.
                    try:
                        result_dict = (
                            json.loads(result) if isinstance(result, str) else result
                        )
                    except (json.JSONDecodeError, ValueError):
                        result_dict = {"raw_text": result}
                    _apply_tool_flags(mode_context, result_dict, self._logger)

                    # ═══════════════════════════════════════════════════════════
                    # Layer B: Coherence interceptor — auto-heal when LLM calls
                    # guardar_datos_elemento or completar_elemento_actual while
                    # element_phase=="photos".
                    #
                    # Case 1 — guardar_datos_elemento:
                    #   This is defense-in-depth for the case where Layer A (the
                    #   pre-loop _guard_photo_completion_intent) did NOT fire because
                    #   the user sent data without saying "listo" (regex miss).
                    #   The guardar tool detects the inconsistency and returns
                    #   guidance=="confirmar_fotos_primero" instead of saving data.
                    #   We intercept that response here and transparently auto-call
                    #   confirmar_fotos_elemento(force=True) before the LLM retries.
                    #
                    # Case 2 — completar_elemento_actual (TASK-09 addition):
                    #   Same issue: LLM may call completar_elemento_actual() while still
                    #   in photos phase, skipping photo confirmation entirely.  We
                    #   intercept and auto-confirm photos first so the element advances
                    #   through the correct state machine transitions.
                    #
                    # Guard against re-entry: if Layer A already fired,
                    # element_phase was advanced to "data" BEFORE _run_llm_loop
                    # started, so mode_context.element_phase != "photos" here and
                    # this block is a no-op.
                    # ═══════════════════════════════════════════════════════════

                    # Determine if Layer B should trigger.
                    _layer_b_should_fire = False
                    _layer_b_trigger_reason = ""
                    # V2: Verify DB element phase before firing to avoid double-fire.
                    # If DB already reports the current element as pending_data/completed,
                    # mode_context["element_phase"] is stale — do not trigger interceptor.
                    _layer_b_db_phase: str = mode_context.get("element_phase", "photos")
                    _layer_b_ess = self._get_element_state_svc()
                    if (
                        _layer_b_ess is not None
                        and mode_context.get("element_phase") == "photos"
                    ):
                        _lb_case_id = mode_context.get("case_id")
                        _lb_el_code = mode_context.get("current_element_code")
                        if _lb_case_id and _lb_el_code:
                            try:
                                _lb_el_state = await _layer_b_ess.get_element_state(
                                    str(_lb_case_id), _lb_el_code
                                )
                                if _lb_el_state is not None:
                                    # DB says photos already confirmed → skip interceptor
                                    _lb_db_status = (
                                        ced_by_code.get(_lb_el_code)
                                        if "ced_by_code" in dir()
                                        else None
                                    )
                                    # Derive from element state directly
                                    _lb_el_state_dict = (
                                        _lb_el_state.to_dict()
                                        if hasattr(_lb_el_state, "to_dict")
                                        else {}
                                    )
                                    _lb_ced_status = _lb_el_state_dict.get(
                                        "status", "pending_photos"
                                    )
                                    if _lb_ced_status in ("pending_data", "completed"):
                                        _layer_b_db_phase = "data"
                                        logger.debug(
                                            "layer_b_db_phase_override",
                                            case_id=_lb_case_id,
                                            element_code=_lb_el_code,
                                            db_status=_lb_ced_status,
                                            skipping_interceptor=True,
                                        )
                            except Exception as _lb_err:
                                logger.debug(
                                    "layer_b_db_check_failed", error=str(_lb_err)
                                )

                    if _layer_b_db_phase == "photos":
                        if (
                            tool_name == "guardar_datos_elemento"
                            and isinstance(result_dict, dict)
                            and result_dict.get("guidance") == "confirmar_fotos_primero"
                        ):
                            _layer_b_should_fire = True
                            _layer_b_trigger_reason = "guardar_while_photos"
                        elif tool_name == "completar_elemento_actual":
                            # TASK-09: LLM called completar without confirming photos first
                            _layer_b_should_fire = True
                            _layer_b_trigger_reason = "completar_while_photos"

                    if _layer_b_should_fire:
                        logger.warning(
                            "photo_coherence_interceptor_triggered",
                            conversation_id=conversation_id,
                            tool_name=tool_name,
                            trigger_reason=_layer_b_trigger_reason,
                            element_code=mode_context.get("current_element_code"),
                            element_index=mode_context.get("current_element_index"),
                        )
                        # Force-call confirmar_fotos_elemento bypassing regex check.
                        # This advances element_phase to "data" in mode_context
                        # (in-place) so the LLM retry sees the correct phase.
                        interceptor_fired = await self._guard_photo_completion_intent(
                            user_message="",
                            mode_context=mode_context,
                            state=cast(dict[str, Any], state),
                            conversation_id=conversation_id,
                            force=True,
                        )
                        # TASK-09: After interceptor auto-confirms photos, update the
                        # state machine to reflect photos_confirmed (if EXPEDIENTE_V2_ENABLED
                        # and _guard_photo_completion_intent didn't already advance to a
                        # terminal state).  The guard sets states internally; we only add
                        # the explicit photos_confirmed marker here when the interceptor
                        # fired but the post-call logic in _guard_photo_completion_intent
                        # left the state as "confirming_photos" (poll still in-flight).
                        # In practice this is a no-op for success paths because
                        # _guard_photo_completion_intent already advances to photos_confirmed
                        # or element_complete.  This is a belt-and-suspenders safety net.
                        if (
                            interceptor_fired
                            and get_settings().EXPEDIENTE_V2_ENABLED
                            and mode_context.get("element_phase") == "data"
                        ):
                            _layer_b_el_code: str | None = mode_context.get(
                                "current_element_code"
                            ) or (
                                (mode_context.get("element_codes") or [None])[
                                    mode_context.get("current_element_index", 0)
                                ]
                                if mode_context.get("element_codes")
                                else None
                            )
                            if _layer_b_el_code:
                                _layer_b_existing = (
                                    (mode_context.get("element_states") or {})
                                    .get(_layer_b_el_code, {})
                                    .get("state")
                                )
                                # Only advance if still at confirming_photos
                                # (guard may have already set photos_confirmed)
                                if _layer_b_existing == ELEMENT_STATE_CONFIRMING_PHOTOS:
                                    _set_element_state(
                                        mode_context,
                                        _layer_b_el_code,
                                        ELEMENT_STATE_PHOTOS_CONFIRMED,
                                    )
                                    logger.debug(
                                        "layer_b_photos_confirmed_state_set",
                                        conversation_id=conversation_id,
                                        element_code=_layer_b_el_code,
                                        trigger_reason=_layer_b_trigger_reason,
                                    )
                        logger.info(
                            "photo_coherence_interceptor_completed",
                            conversation_id=conversation_id,
                            interceptor_fired=interceptor_fired,
                            trigger_reason=_layer_b_trigger_reason,
                            new_element_phase=mode_context.get("element_phase"),
                        )
                    # ═══════════════════════════════════════════════════════════
                    # End Layer B coherence interceptor
                    # ═══════════════════════════════════════════════════════════

                    # Track all applied flags for final authority
                    parsed_flags = (
                        result_dict.get("_internal_flags", {})
                        if isinstance(result_dict, dict)
                        else {}
                    )
                    all_applied_flags.update(parsed_flags)

                    # ═══════════════════════════════════════════════════════════
                    # FASE 3: Early-exit guard for case_finalized
                    # When finalizar_expediente() succeeds it returns
                    # _internal_flags: {"case_finalized": True}.  The moment we
                    # detect that flag we MUST stop the tool loop and use the
                    # tool's own message as the final user-facing response.
                    #
                    # This prevents the LLM from continuing to call other tools
                    # (e.g. escalar_a_humano) after finalization, which would
                    # overwrite the correct Chatwoot labels and confuse the user.
                    #
                    # Defensive: we check EVERY tool result in the batch, not
                    # just the last one.  If any tool carries this flag (unlikely
                    # for non-finalizar tools, but defensive programming),
                    # we honour it and stop immediately.
                    #
                    # The guard does NOT fire on failure paths because
                    # finalizar_expediente() only sets case_finalized on
                    # success=True; error paths return success=False with no flag.
                    # ═══════════════════════════════════════════════════════════
                    if parsed_flags.get("case_finalized") is True:
                        finalization_message = ""
                        if isinstance(result_dict, dict):
                            finalization_message = result_dict.get(
                                "message", ""
                            ) or result_dict.get("texto", "")
                        if finalization_message:
                            ai_response = finalization_message
                        _case_finalized = True
                        logger.info(
                            "expediente_case_finalized_guard_triggered",
                            case_finalized=True,
                            tool_name=tool_name,
                            conversation_id=conversation_id,
                        )
                        break  # Exit inner tool loop — finalization is terminal

                    # Extract context from tool results
                    tool_context = self._extract_context_from_tool(
                        tool_name,
                        tool_args,
                        result,
                        mode_context,
                    )

                    # ── Certainty guardrails: accumulate envelope + gate transitions ──
                    if _guardrails_enabled:
                        _turn_envelope = normalize_tool_payload(
                            tool_name=tool_name,
                            raw_result=result,
                            current_sub_mode=_current_sub_mode_lc,
                            existing_envelope=_turn_envelope,
                        )
                        # If _extract_context_from_tool signalled a transition,
                        # check whether the envelope supports it.  If not, remove
                        # the transition keys from tool_context so the transition
                        # is suppressed this turn.
                        _proposed_target: str | None = tool_context.get(
                            "expediente_sub_mode"
                        )
                        if _proposed_target:
                            _prog_allowed, _prog_reason = (
                                evaluate_progression_eligibility(
                                    _turn_envelope, _proposed_target
                                )
                            )
                            log_guardrail_triggered(
                                reason=_prog_reason,
                                sub_mode=_current_sub_mode_lc,
                                tool_name=tool_name,
                                conversation_id=conversation_id,
                                allowed=_prog_allowed,
                                extra={"transition_target": _proposed_target},
                            )
                            if not _prog_allowed:
                                # Suppress the transition — remove all transition keys
                                for _tkey in (
                                    "expediente_sub_mode",
                                    "just_transitioned_from",
                                    "expediente_transition_marker",
                                ):
                                    tool_context.pop(_tkey, None)
                                logger.warning(
                                    "expediente_transition_suppressed_by_guardrail",
                                    reason=_prog_reason,
                                    proposed_target=_proposed_target,
                                    sub_mode=_current_sub_mode_lc,
                                    tool_name=tool_name,
                                    conversation_id=conversation_id,
                                )

                    context_updates.update(tool_context)

                    # TASK-05: Update per-element 7-state machine in _run_llm_loop.
                    # Fired AFTER _extract_context_from_tool so that mode_context
                    # is already partially updated (element_phase, element_code, etc.).
                    # Only active when EXPEDIENTE_V2_ENABLED=True.
                    if (
                        settings.EXPEDIENTE_V2_ENABLED
                        and sub_mode_name == "COLLECT_ELEMENT_DATA"
                    ):
                        # Merge pending context_updates into a temporary view so helpers
                        # see the latest element_phase / element_code values.
                        _v2_ctx = {**mode_context, **context_updates}
                        _v2_el_code: str | None = _v2_ctx.get(
                            "current_element_code"
                        ) or (
                            (_v2_ctx.get("element_codes") or [None])[
                                _v2_ctx.get("current_element_index", 0)
                            ]
                            if _v2_ctx.get("element_codes")
                            else None
                        )
                        if _v2_el_code:
                            if tool_name == "confirmar_fotos_elemento":
                                _v2_count_raw = (
                                    result_dict.get("photos_count", 0)
                                    if isinstance(result_dict, dict)
                                    else 0
                                )
                                _v2_count: int = (
                                    _v2_count_raw
                                    if isinstance(_v2_count_raw, int)
                                    else 0
                                )
                                if (
                                    result_dict.get("all_elements_complete")
                                    if isinstance(result_dict, dict)
                                    else False
                                ):
                                    # No data fields — element fully done immediately
                                    _set_element_state(
                                        mode_context,
                                        _v2_el_code,
                                        ELEMENT_STATE_ELEMENT_COMPLETE,
                                        data_complete=True,
                                    )
                                elif _v2_ctx.get("element_phase") == "data":
                                    # Photos successfully verified → moving to data
                                    _set_element_state(
                                        mode_context,
                                        _v2_el_code,
                                        ELEMENT_STATE_PHOTOS_CONFIRMED,
                                        photos_count=_v2_count,
                                    )
                                else:
                                    # Polling in progress
                                    _set_element_state(
                                        mode_context,
                                        _v2_el_code,
                                        ELEMENT_STATE_CONFIRMING_PHOTOS,
                                    )
                            elif tool_name == "obtener_campos_elemento":
                                if _v2_ctx.get("element_phase") == "data":
                                    # Now actively collecting field data
                                    _set_element_state(
                                        mode_context,
                                        _v2_el_code,
                                        ELEMENT_STATE_DATA_COLLECTION,
                                    )
                            elif tool_name == "guardar_datos_elemento":
                                if _v2_ctx.get("element_phase") == "data":
                                    # Still in data collection
                                    _set_element_state(
                                        mode_context,
                                        _v2_el_code,
                                        ELEMENT_STATE_DATA_COLLECTION,
                                    )
                            elif tool_name == "completar_elemento_actual":
                                if isinstance(result_dict, dict) and result_dict.get(
                                    "success"
                                ):
                                    # Element fully complete
                                    _set_element_state(
                                        mode_context,
                                        _v2_el_code,
                                        ELEMENT_STATE_ELEMENT_COMPLETE,
                                        data_complete=True,
                                    )

                    # Extract pending images from enviar_imagenes_ejemplo
                    if tool_name == "enviar_imagenes_ejemplo":
                        images_data = self._extract_pending_images(result)
                        if images_data:
                            pending_images = images_data

                    # Re-inject ContextVar after each tool call
                    # This ensures tools read updated state in subsequent iterations
                    mode_context.update(context_updates)
                    updated_state = dict(state)
                    updated_state["mode_context"] = mode_context
                    set_current_state(updated_state)
                    set_current_state_for_image_tools(updated_state)

                    llm_messages.append(
                        {
                            "role": "tool",
                            "content": result,
                            "tool_call_id": tool_call_id,
                        }
                    )

                    # ═══════════════════════════════════════════════════════════
                    # PHASE F-3: Fast-path break on sub-mode transition
                    # When a tool signals a change to expediente_sub_mode,
                    # stop the LLM loop immediately. The neutral tool message
                    # IS the response — the new sub-mode handles the next turn.
                    # This prevents the LLM from anticipating the next sub-mode's
                    # content in the same turn as the transition tool call.
                    #
                    # NOTE: We read `context_updates` (not mode_context) because
                    # mode_context was already mutated above (line 1245). The
                    # context_updates dict captures what the tool *just* changed,
                    # so checking it directly avoids a stale-value false-negative.
                    # ═══════════════════════════════════════════════════════════
                    new_sub_mode = context_updates.get("expediente_sub_mode")
                    if new_sub_mode and new_sub_mode != sub_mode_name.lower():
                        _base_docs = _get_transition_base_documentation(mode_context)
                        # Phase 3.2: Use generalised transition matrix when flag is ON;
                        # fall back to legacy element-only closure when flag is OFF.
                        if settings.ENABLE_SAME_TURN_TRANSITION_CLOSURE:
                            deterministic_closure = _build_transition_closure(
                                from_sub_mode=sub_mode_name.lower(),
                                to_sub_mode=new_sub_mode,
                                tool_name=tool_name,
                                tool_data=result_dict
                                if isinstance(result_dict, dict)
                                else None,
                                base_documentation=_base_docs,
                            )
                        else:
                            deterministic_closure = (
                                _build_element_completion_transition_closure(
                                    from_sub_mode=sub_mode_name.lower(),
                                    to_sub_mode=new_sub_mode,
                                    tool_name=tool_name,
                                    tool_data=result_dict
                                    if isinstance(result_dict, dict)
                                    else None,
                                    base_documentation=_base_docs,
                                )
                            )
                        closing_message = deterministic_closure or ""
                        if not closing_message and isinstance(result_dict, dict):
                            closing_message = result_dict.get("message", "")
                        if closing_message:
                            ai_response = closing_message
                        # Mark that the closure already delivered field-level
                        # kickoff content so the next sub-mode prompt skips the
                        # duplicate introductory question.
                        if deterministic_closure and new_sub_mode != REVIEW_SUMMARY:
                            mode_context["kickoff_question_injected"] = True
                        # Observability: trace closure emission for transition diagnostics
                        self._logger.info(
                            "expediente_transition_closure_emitted",
                            from_sub_mode=sub_mode_name,
                            to_sub_mode=new_sub_mode,
                            tool=tool_name,
                            has_deterministic_closure=bool(deterministic_closure),
                            iteration=iteration + 1,
                            conversation_id=conversation_id,
                        )
                        break  # Exit inner tool loop — LLM should NOT iterate further

                    # ═══════════════════════════════════════════════════════════
                    # PHASE 1A: Fast-path break on transition signal
                    # When a tool signals _transition_to, stop immediately.
                    # The tool's message IS the response — no extra LLM iteration.
                    # ═══════════════════════════════════════════════════════════
                    if mode_context.get("_transition_to"):
                        transition_message = ""
                        if isinstance(result_dict, dict):
                            transition_message = result_dict.get(
                                "message", ""
                            ) or result_dict.get("texto", "")
                        if transition_message:
                            ai_response = transition_message
                        self._logger.info(
                            "transition_fast_path_break",
                            target=mode_context["_transition_to"],
                            tool=tool_name,
                            has_message=bool(transition_message),
                            sub_mode=sub_mode_name,
                            conversation_id=conversation_id,
                        )
                        break  # Exit inner tool loop

                # Fast-path: also break outer iteration loop on transition
                if mode_context.get("_transition_to"):
                    break

                # FASE 3: Break outer iteration loop when case_finalized guard fired
                if _case_finalized:
                    break

                # Fast-path: break outer iteration loop on sub-mode transition
                # context_updates has the new sub_mode from the tool; sub_mode_name
                # is the UPPER-CASED version of the current sub-mode (before transition).
                _new_sub = context_updates.get("expediente_sub_mode")
                if _new_sub and _new_sub != sub_mode_name.lower():
                    break

            else:
                _loop_hit_max = True
                self._logger.warning(
                    "max_tool_iterations",
                    sub_mode=sub_mode_name,
                    iterations=_effective_max_iterations,
                )
                if settings.ENABLE_LATENCY_GATING:
                    logger.info(
                        "tool_loop_complete",
                        iterations=_effective_max_iterations,
                        exit_reason="max_iterations",
                        mode="EXPEDIENTE",
                        sub_mode=sub_mode_name,
                    )
                if not ai_response:
                    ai_response = response.content or (
                        "Disculpa, me ha llevado más tiempo del esperado. "
                        "¿Puedes repetir?"
                    )

            # ═══════════════════════════════════════════════════════════════════
            # GUARD: Auto-complete element when LLM skips completar_elemento_actual
            #
            # Bug scenario:
            #   1. LLM calls guardar_datos_elemento() → all fields saved
            #   2. LLM generates closing text WITHOUT calling completar_elemento_actual()
            #   3. Element stuck in "pending_data" → dead-air, no transition
            #
            # Fix: If guardar_datos_elemento signaled all fields are complete
            # (element_data_all_collected == True) and the LLM did not call
            # completar_elemento_actual in this turn, we call it programmatically.
            # ═══════════════════════════════════════════════════════════════════
            if (
                sub_mode_name == "COLLECT_ELEMENT_DATA"
                and "guardar_datos_elemento" in tools_called
                and "completar_elemento_actual" not in tools_called
                and context_updates.get("element_data_all_collected") is True
                and not context_updates.get(
                    "expediente_sub_mode"
                )  # No transition already set
            ):
                self._logger.warning(
                    "expediente_auto_complete_element_guard_triggered",
                    conversation_id=conversation_id,
                    sub_mode=sub_mode_name,
                    tools_called_this_turn=list(tools_called),
                    element_code=mode_context.get("current_element_code")
                    or (
                        mode_context.get("element_codes", [None])[
                            mode_context.get("current_element_index", 0)
                        ]
                        if mode_context.get("element_codes")
                        else None
                    ),
                )

                try:
                    # Execute the tool programmatically (same path as LLM-driven)
                    # Note: completar_elemento_actual is dispatched by name via
                    # _execute_and_log_tool, which finds it in the `tools` list.
                    guard_result = await self._execute_and_log_tool(
                        conversation_id=conversation_id,
                        tool_name="completar_elemento_actual",
                        tool_args={},
                        tools=tools,
                        iteration=MAX_TOOL_ITERATIONS + 1,  # Distinguishable iteration
                    )

                    tools_called.add("completar_elemento_actual")

                    # Parse result (same pattern as main loop)
                    try:
                        guard_result_dict = (
                            json.loads(guard_result)
                            if isinstance(guard_result, str)
                            else guard_result
                        )
                    except (json.JSONDecodeError, ValueError):
                        guard_result_dict = {"raw_text": guard_result}

                    # Apply tool flags
                    _apply_tool_flags(mode_context, guard_result_dict, self._logger)
                    if isinstance(guard_result_dict, dict):
                        parsed_flags = guard_result_dict.get("_internal_flags", {})
                        all_applied_flags.update(parsed_flags)

                    # Extract context updates (drives sub-mode transition)
                    guard_context = self._extract_context_from_tool(
                        "completar_elemento_actual",
                        {},
                        guard_result,
                        mode_context,
                    )
                    context_updates.update(guard_context)

                    # Re-inject ContextVar with updated state
                    mode_context.update(guard_context)
                    updated_state = dict(state)
                    updated_state["mode_context"] = mode_context
                    set_current_state(updated_state)
                    set_current_state_for_image_tools(updated_state)

                    # Handle sub-mode transition (same logic as PHASE F-3 fast-path)
                    new_sub_mode = guard_context.get("expediente_sub_mode")
                    if new_sub_mode and new_sub_mode != sub_mode_name.lower():
                        _base_docs = _get_transition_base_documentation(mode_context)
                        # Phase 3.2: Use generalised matrix when flag is ON (guard path)
                        if settings.ENABLE_SAME_TURN_TRANSITION_CLOSURE:
                            deterministic_closure = _build_transition_closure(
                                from_sub_mode=sub_mode_name.lower(),
                                to_sub_mode=new_sub_mode,
                                tool_name="completar_elemento_actual",
                                tool_data=guard_result_dict
                                if isinstance(guard_result_dict, dict)
                                else None,
                                base_documentation=_base_docs,
                            )
                        else:
                            deterministic_closure = (
                                _build_element_completion_transition_closure(
                                    from_sub_mode=sub_mode_name.lower(),
                                    to_sub_mode=new_sub_mode,
                                    tool_name="completar_elemento_actual",
                                    tool_data=guard_result_dict
                                    if isinstance(guard_result_dict, dict)
                                    else None,
                                    base_documentation=_base_docs,
                                )
                            )
                        if deterministic_closure:
                            ai_response = deterministic_closure
                            # Mark kickoff injection so sub-mode prompt skips
                            # duplicate question (skip for review — tool-first).
                            if new_sub_mode != REVIEW_SUMMARY:
                                mode_context["kickoff_question_injected"] = True
                        elif isinstance(guard_result_dict, dict):
                            ai_response = (
                                guard_result_dict.get("message", "") or ai_response
                            )
                    elif isinstance(guard_result_dict, dict) and guard_result_dict.get(
                        "success"
                    ):
                        # Element complete but more elements remaining — use tool message
                        tool_msg = guard_result_dict.get("message", "")
                        if tool_msg:
                            ai_response = tool_msg

                    self._logger.info(
                        "expediente_auto_complete_element_guard_completed",
                        conversation_id=conversation_id,
                        guard_success=isinstance(guard_result_dict, dict)
                        and guard_result_dict.get("success", False),
                        triggered_transition=bool(
                            guard_context.get("expediente_sub_mode")
                        ),
                        all_elements_complete=isinstance(guard_result_dict, dict)
                        and guard_result_dict.get("all_elements_complete", False),
                    )

                except Exception as guard_error:
                    # Non-fatal: log and continue with existing response
                    self._logger.error(
                        "expediente_auto_complete_element_guard_failed",
                        error=str(guard_error),
                        conversation_id=conversation_id,
                        exc_info=True,
                    )

            # Log tool loop completion for latency telemetry
            if settings.ENABLE_LATENCY_GATING and not _loop_hit_max:
                logger.info(
                    "tool_loop_complete",
                    iterations=iteration + 1 if tools_called else 0,
                    exit_reason="no_tool_calls" if not tools_called else "break",
                    mode="EXPEDIENTE",
                    sub_mode=sub_mode_name,
                )

            # ── 6. Build state updates ───────────────────────────────────────
            # Merge context: mode_context is base, context_updates adds structural data,
            # all_applied_flags has FINAL AUTHORITY over boolean flags
            transitioned_this_turn = bool(context_updates.get("expediente_sub_mode"))

            # ── Bug 1 fix: same-turn transition marker ────────────────────────
            # active_transition_marker is read at the START of _run_llm_loop (before
            # tools execute) — it only sees markers set on PRIOR turns.  When a tool
            # (e.g. confirmar_fotos_elemento) sets a new transition marker THIS turn,
            # it ends up in context_updates["expediente_transition_marker"], NOT in
            # mode_context.  effective_transition_marker merges both so the kickoff
            # guard fires on the originating turn, not one turn too late.
            effective_transition_marker: dict[str, Any] | None = (
                active_transition_marker
            )
            if effective_transition_marker is None:
                _same_turn_marker = context_updates.get("expediente_transition_marker")
                if isinstance(_same_turn_marker, dict) and _same_turn_marker.get(
                    "requires_kickoff"
                ):
                    effective_transition_marker = _same_turn_marker

            ai_response_text: str = str(ai_response or "")

            # ── Certainty guardrails: finalise envelope + inject into prompt context ──
            if _guardrails_enabled:
                # Mark first-destination-turn flag when a kickoff marker is active and
                # no further transition happened this turn.
                if effective_transition_marker and not transitioned_this_turn:
                    _turn_envelope = CertaintyEnvelope(
                        **{
                            **_turn_envelope.to_dict(),
                            "is_first_destination_turn": True,
                            # Anti-anticipation: if the existing response is not
                            # actionable, block transition claims in the prompt.
                            "allowed_transition_claims": self._is_actionable_kickoff_response(
                                ai_response_text
                            ),
                            "kickoff_required": not self._is_actionable_kickoff_response(
                                ai_response_text
                            ),
                        }
                    )

                # Persist envelope so loader.py and next turn can read it.
                persist_envelope(mode_context, _turn_envelope)

                # Extend kickoff guard with truthfulness check.
                if effective_transition_marker and not transitioned_this_turn:
                    _truth_ok, _truth_reason = evaluate_kickoff_truthfulness(
                        _turn_envelope, _current_sub_mode_lc
                    )
                    log_guardrail_triggered(
                        reason=_truth_reason,
                        sub_mode=_current_sub_mode_lc,
                        conversation_id=conversation_id,
                        allowed=_truth_ok,
                    )

                    # ── Task 3.2: Claim eligibility gate for NEXT_STEP_DESCRIPTION ──
                    # When this is the first destination turn after a transition and
                    # the LLM response is not yet actionable (kickoff guard is about
                    # to fire), also evaluate whether a NEXT_STEP_DESCRIPTION claim
                    # is permitted.  This creates a structured audit trail so the
                    # guardrail dashboard can track same-turn anticipatory narration.
                    if not self._is_actionable_kickoff_response(ai_response_text):
                        _claim_ok, _claim_reason = evaluate_claim_eligibility(
                            _turn_envelope,
                            ClaimClass.NEXT_STEP_DESCRIPTION,
                            _current_sub_mode_lc,
                        )
                        log_guardrail_triggered(
                            reason=_claim_reason,
                            sub_mode=_current_sub_mode_lc,
                            claim_class=ClaimClass.NEXT_STEP_DESCRIPTION.value,
                            conversation_id=conversation_id,
                            allowed=_claim_ok,
                        )
                        # Task 3.4: Emit dedicated blocked event for dashboards.
                        if not _claim_ok:
                            logger.warning(
                                "expediente_next_step_narration_blocked",
                                conversation_id=conversation_id,
                                sub_mode=_current_sub_mode_lc,
                                reason_code=_claim_reason,
                                from_sub_mode=effective_transition_marker.get(
                                    "from_sub_mode"
                                ),
                                to_sub_mode=effective_transition_marker.get(
                                    "to_sub_mode"
                                ),
                                enforced=True,
                            )

            # Kickoff guard fires when: (1) we just transitioned to a new sub-mode AND
            # (2) the LLM response is not actionable (no question/CTA).
            # The `transitioned_this_turn` condition was removed because it suppressed
            # the kickoff exactly when needed — on the transition turn itself.
            # Bug 1 fix: uses effective_transition_marker (not active_transition_marker)
            # so the guard also fires when the marker was set THIS turn by a tool call.
            if effective_transition_marker and not self._is_actionable_kickoff_response(
                ai_response_text
            ):
                ai_response = self._build_transition_kickoff_message(
                    sub_mode_name=sub_mode_name,
                    mode_context=mode_context,
                )
                self._logger.warning(
                    "expediente_transition_kickoff_guard_triggered",
                    from_sub_mode=effective_transition_marker.get("from_sub_mode"),
                    to_sub_mode=effective_transition_marker.get("to_sub_mode"),
                    sub_mode=sub_mode_name,
                    tools_called=list(tools_called),
                    conversation_id=conversation_id,
                )

            updated_context = {**mode_context, **context_updates}
            # _internal_flags always win over stale context_updates values
            for key, value in all_applied_flags.items():
                if key.startswith("_"):
                    continue  # Skip internal keys like _transition_to
                updated_context[key] = value

            # ── TASK-07: Anti-repetition guard (MD5 hash of last 2 assistant turns) ──
            # Step 2 of final-response assembly: check for repeat BEFORE progress prefix.
            # If the new message matches either of the last 2 stored hashes, prepend
            # "Para recordarte: " so the user knows it is intentional, not a bug.
            # Feature-flagged: only active when EXPEDIENTE_V2_ENABLED=True.
            _final_response_str = str(ai_response or "")
            if settings.EXPEDIENTE_V2_ENABLED and _final_response_str:
                _final_response_str = _check_anti_repetition(
                    _final_response_str, mode_context
                )
                ai_response = _final_response_str

            # ── TASK-06: Inject deterministic progress prefix on final user-facing response ──
            # Only active when EXPEDIENTE_V2_ENABLED=True.  Uses _inject_step_prefix()
            # which is idempotent (never double-prefixes) and skips empty messages.
            # Applied to the terminal user-facing response — not to tool call turns.
            _current_sub_mode = mode_context.get(
                "expediente_sub_mode", sub_mode_name.lower()
            )
            if settings.EXPEDIENTE_V2_ENABLED:
                ai_response = _inject_step_prefix(
                    str(ai_response or ""), _current_sub_mode
                )

            # ── TASK-07: Store MD5 of the final sent message (post-prefix) ──
            # Step 4: Hash stored AFTER progress prefix injection — we track the exact
            # bytes the user sees so future comparisons are accurate.
            # updated_context is built just below; store into mode_context in-place so
            # the mutation is captured when we merge into updated_context next.
            if settings.EXPEDIENTE_V2_ENABLED:
                _store_turn_hash(str(ai_response or ""), mode_context)
                # Propagate mutation to updated_context (built before _store_turn_hash ran)
                updated_context["_last_agent_turns"] = mode_context.get(
                    "_last_agent_turns", []
                )

            # ── Task 3.3: Pre-response claim gate ────────────────────────────
            # AFTER the LLM/tool loop and all post-processing guards, but BEFORE
            # ai_response is returned, run a final regex-based claim gate.
            # This is the last line of defence against unsupported assertions in
            # the assembled response.  Only active when guardrails are enabled.
            #
            # We accumulate evaluation counters here so Task 3.4 turn-summary
            # log can include them.
            _gate_blocked: int = 0
            _gate_allowed: int = 0
            if _guardrails_enabled and ai_response:
                _gated_response, _gate_blocked, _gate_allowed = _gate_response_claims(
                    ai_response=str(ai_response),
                    turn_envelope=_turn_envelope,
                    sub_mode=_current_sub_mode_lc,
                    conversation_id=conversation_id,
                    guardrails_enabled=True,
                )
                if _gated_response != str(ai_response):
                    self._logger.info(
                        "expediente_claim_gate_rewrite",
                        sub_mode=_current_sub_mode_lc,
                        conversation_id=conversation_id,
                        blocked_count=_gate_blocked,
                        original_length=len(str(ai_response)),
                        rewritten_length=len(_gated_response),
                    )
                ai_response = _gated_response

            # ── Task 3.4: Turn-summary observability ─────────────────────────
            # Emit one structured log per expediente turn when guardrails are ON.
            # Aggregates all guardrail evaluations performed this turn (from tool
            # loop + pre-response gate) so dashboards can compute block-rate
            # without joining multiple events.
            if _guardrails_enabled:
                # Count progression evaluations that happened during the tool loop.
                # We proxy via tools_called to avoid double-tracking; each tool
                # that was normalised had its progression eligibility checked once.
                _total_evaluations = len(tools_called) + _gate_blocked + _gate_allowed
                logger.info(
                    "expediente_certainty_turn_summary",
                    conversation_id=conversation_id,
                    sub_mode=_current_sub_mode_lc,
                    tools_called_count=len(tools_called),
                    total_evaluations=_total_evaluations,
                    blocked_count=_gate_blocked,
                    allowed_count=_gate_allowed,
                    case_id=mode_context.get("case_id"),
                )

            result_dict: dict[str, Any] = {
                "ai_response": ai_response,
                "mode_context": updated_context,
                "retry_state": retry_state,  # Phase 3: Persist retry state
            }

            # Propagate mode transition if signaled by a tool
            transition_target = updated_context.pop("_transition_to", None)
            if transition_target:
                from agent.router.mode_transitions import (
                    validate_transition,
                    get_preserve_keys,
                )
                from agent.state.conversation_state import transition_mode

                allowed, reason = validate_transition(self.mode_name, transition_target)
                if allowed:
                    preserve = get_preserve_keys(self.mode_name, transition_target)
                    transition_updates = transition_mode(
                        state,
                        transition_target,
                        preserve_keys=preserve,
                    )
                    # Merge transition updates, but keep our ai_response
                    saved_response = result_dict["ai_response"]
                    result_dict.update(transition_updates)
                    result_dict["ai_response"] = saved_response
                    self._logger.info(
                        "mode_transition_from_tool",
                        target=transition_target,
                        sub_mode=sub_mode_name,
                        conversation_id=conversation_id,
                    )
                else:
                    self._logger.warning(
                        "mode_transition_blocked",
                        target=transition_target,
                        reason=reason,
                        sub_mode=sub_mode_name,
                        conversation_id=conversation_id,
                    )

            # Bubble up pending images
            if pending_images:
                result_dict["pending_images"] = pending_images
                # Persist follow_up text so LLM sees it next turn (Bug A fix)
                follow_up = pending_images.get("follow_up_message")
                if follow_up:
                    updated_context["last_follow_up_sent"] = follow_up

            self._logger.info(
                "expediente_sub_mode_response",
                sub_mode=sub_mode_name,
                response_length=len(ai_response),
                tools_called=list(tools_called),
                has_pending_images=pending_images is not None,
            )

            # Clear transition marker once the destination turn consumed it.
            # Keep it only when a new transition is set in this same turn.
            if (
                active_transition_marker
                and "expediente_transition_marker" not in context_updates
            ):
                updated_context.pop("expediente_transition_marker", None)
                updated_context.pop("just_transitioned_from", None)
                self._logger.info(
                    "expediente_transition_marker_cleared",
                    from_sub_mode=active_transition_marker.get("from_sub_mode"),
                    to_sub_mode=active_transition_marker.get("to_sub_mode"),
                    sub_mode=sub_mode_name,
                    conversation_id=conversation_id,
                )

            return result_dict

        finally:
            # ── 7. Cleanup ContextVars ──────────────────────────────────────
            # CRITICAL: Always clear state to prevent leakage to other conversations
            clear_current_state()
            clear_image_tools_state()
            # ── Deactivate per-turn dedup cache ────────────────────────────
            self._tool_dedup_cache = None

    # ------------------------------------------------------------------
    # Context extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_context_from_tool(
        tool_name: str,
        tool_args: dict[str, Any],
        result: str,
        current_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Extract mode context updates from tool results.

        Key updates:
        - Sub-mode transitions (expediente_sub_mode)
        - Element collection progress
        - Case completion status
        """
        updates: dict[str, Any] = {}

        try:
            data = json.loads(result) if isinstance(result, str) else result
        except (json.JSONDecodeError, TypeError):
            return updates

        if not isinstance(data, dict):
            return updates

        # Standard contract: tools can declare mode_context updates via _context_updates
        # This is the preferred mechanism for new tools (see tool_context_contract.py)
        if "_context_updates" in data:
            ctx_updates = data["_context_updates"]
            if isinstance(ctx_updates, dict):
                updates.update(ctx_updates)
                logger.debug(
                    "applied_context_updates_contract",
                    tool_name=tool_name,
                    keys=list(ctx_updates.keys()),
                )

        # Detect sub-mode transitions from tool metadata
        if tool_name in ("completar_elemento_actual", "confirmar_fotos_elemento"):
            # Both tools can signal that all elements are done (e.g. last element
            # has no required fields → confirmar_fotos_elemento completes it directly
            # without going through completar_elemento_actual).
            if data.get("all_elements_complete"):
                _set_transition_updates(
                    updates=updates,
                    from_sub_mode=COLLECT_ELEMENT_DATA,
                    to_sub_mode=COLLECT_BASE_DOCS,
                    tool_name=tool_name,
                )

        elif tool_name == "confirmar_documentacion_base":
            # Only advance when success=True AND not already_confirmed AND not
            # escalated.  When escalated=True the tool handed off to a human
            # agent — advancing the sub-mode would skip the base-docs phase
            # that still needs human review.
            if (
                data.get("success")
                and not data.get("already_confirmed")
                and not data.get("escalated")
            ):
                _set_transition_updates(
                    updates=updates,
                    from_sub_mode=COLLECT_BASE_DOCS,
                    to_sub_mode=COLLECT_PERSONAL,
                    tool_name=tool_name,
                )

        elif tool_name == "actualizar_datos_expediente":
            # Detect transition by next_step in result (not by "seccion" param which doesn't exist)
            if data.get("success"):
                next_step = data.get("next_step")
                if next_step == "collect_vehicle":
                    _set_transition_updates(
                        updates=updates,
                        from_sub_mode=COLLECT_PERSONAL,
                        to_sub_mode=COLLECT_VEHICLE,
                        tool_name=tool_name,
                    )
                elif next_step == "collect_workshop":
                    _set_transition_updates(
                        updates=updates,
                        from_sub_mode=COLLECT_VEHICLE,
                        to_sub_mode=COLLECT_WORKSHOP,
                        tool_name=tool_name,
                    )

        elif tool_name == "actualizar_datos_taller":
            if data.get("success"):
                next_step = data.get("next_step")
                if next_step is None:
                    pass
                elif next_step == "collect_workshop":
                    # Still collecting workshop data (taller_propio=True, need details)
                    pass  # Stay in COLLECT_WORKSHOP, don't transition
                else:
                    _set_transition_updates(
                        updates=updates,
                        from_sub_mode=COLLECT_WORKSHOP,
                        to_sub_mode=REVIEW_SUMMARY,
                        tool_name=tool_name,
                    )

        elif tool_name == "finalizar_expediente":
            if data.get("success"):
                # Mark as completed — transition to COMPLETED mode
                updates["expediente_completed"] = True
                updates["_transition_to"] = "COMPLETED"

        elif tool_name == "iniciar_expediente":
            if data.get("success"):
                # Propagate intro_already_sent flag from _internal_flags to
                # mode_context so that subsequent calls to
                # build_new_expediente_case_instructions() know the intro was
                # already delivered via expediente_intro_message.
                flags = data.get("_internal_flags", {})
                if isinstance(flags, dict) and flags.get("intro_already_sent"):
                    updates["intro_already_sent"] = True

        elif tool_name == "cancelar_expediente":
            if data.get("success"):
                updates["expediente_cancelled"] = True
                updates["_transition_to"] = "PRESUPUESTO_MODE"

        elif tool_name == "editar_expediente":
            # User wants to edit a section from REVIEW_SUMMARY — route back to that sub-mode
            if data.get("success"):
                next_step = data.get("next_step")
                _STEP_TO_SUBMODE = {
                    "collect_personal": COLLECT_PERSONAL,
                    "collect_vehicle": COLLECT_VEHICLE,
                    "collect_workshop": COLLECT_WORKSHOP,
                    "collect_base_docs": COLLECT_BASE_DOCS,
                    "collect_element_data": COLLECT_ELEMENT_DATA,
                }
                if next_step in _STEP_TO_SUBMODE:
                    _set_transition_updates(
                        updates=updates,
                        from_sub_mode=REVIEW_SUMMARY,
                        to_sub_mode=_STEP_TO_SUBMODE[next_step],
                        tool_name=tool_name,
                    )
                    updates["editing_from_review"] = True

        # Track element progress
        if tool_name in (
            "confirmar_fotos_elemento",
            "guardar_datos_elemento",
            "completar_elemento_actual",
        ):
            if "current_element_index" in data:
                updates["current_element_index"] = data["current_element_index"]
            if "element_phase" in data:
                updates["element_phase"] = data["element_phase"]

        # Extract field_keys from tool results so they can be injected into the
        # system prompt.  This prevents the LLM from guessing/abbreviating keys.
        if tool_name in ("confirmar_fotos_elemento", "obtener_campos_elemento"):
            field_keys = _extract_field_keys_from_tool_result(data)
            if field_keys:
                updates["current_element_field_keys"] = field_keys
        elif tool_name == "guardar_datos_elemento":
            # After saving, update field_keys with remaining (missing) fields
            # so the prompt stays current for the next turn.
            field_keys = _extract_field_keys_from_tool_result(data)
            if field_keys:
                updates["current_element_field_keys"] = field_keys

            # If all required fields are collected, signal the LLM to call
            # completar_elemento_actual() immediately.  Without this, the LLM
            # might generate a confirmation message and skip the tool call,
            # leaving the element stuck in "pending_data" forever.
            if (
                data.get("all_required_collected")
                and data.get("action") == "ELEMENT_DATA_COMPLETE"
            ):
                updates["element_data_all_collected"] = True
                # Clear stale field_keys — there's nothing left to ask
                updates["current_element_field_keys"] = None
                logger.info(
                    "element_data_complete_signal_set",
                    element_code=data.get("element_code"),
                )
            else:
                # Ensure the flag is cleared if data is still incomplete
                updates["element_data_all_collected"] = False
        elif tool_name == "completar_elemento_actual":
            # Element done — clear stale field_keys and completion signal so they
            # don't leak to next element
            updates["current_element_field_keys"] = None
            updates["element_data_all_collected"] = False

        # FSM compatibility: v1 tools return state updates via fsm_compat layer.
        # Tools wrap updates in: {"fsm_state_update": {"case_collection": {actual_updates}}}
        # We need to unwrap BOTH levels to extract the actual state changes.
        #
        # Level 1: data["fsm_state_update"]["case_collection"] (standard v1 tool pattern)
        # Level 2: data["case_collection"] (direct — fallback if tool returns flat)
        if "fsm_state_update" in data:
            fsm_update = data["fsm_state_update"]
            if isinstance(fsm_update, dict):
                case_coll = fsm_update.get("case_collection", {})
                if isinstance(case_coll, dict) and case_coll:
                    updates.update(case_coll)
                    logger.debug(
                        "applied_fsm_state_update_to_mode_context",
                        tool_name=tool_name,
                        fsm_keys=list(case_coll.keys()),
                    )
        elif "case_collection" in data:
            fsm_updates = data["case_collection"]
            if isinstance(fsm_updates, dict):
                updates.update(fsm_updates)
                logger.debug(
                    "applied_case_collection_to_mode_context",
                    tool_name=tool_name,
                    fsm_keys=list(fsm_updates.keys()),
                )

        if isinstance(data.get("expediente_intro_message"), str):
            updates["expediente_intro_message"] = data["expediente_intro_message"]
        if isinstance(data.get("expediente_intro_sent"), bool):
            updates["expediente_intro_sent"] = data["expediente_intro_sent"]

        marker = updates.get("expediente_transition_marker")
        if isinstance(marker, dict):
            logger.info(
                "expediente_transition_marker_set",
                from_sub_mode=marker.get("from_sub_mode"),
                to_sub_mode=marker.get("to_sub_mode"),
                tool=marker.get("tool_name"),
                requires_kickoff=marker.get("requires_kickoff"),
            )

        # ===================================================================
        # ADAPTER INTEGRATION: Canonical transition canonicalization (Task 3.1)
        # ===================================================================
        # Normalize heterogeneous transition signals into canonical sub-mode values.
        # This is additive: existing extraction logic runs first, then adapter
        # may override if it finds a different canonical value from any channel.
        from shared.config import get_settings

        settings = get_settings()
        if settings.ENABLE_CANONICAL_TRANSITION_ADAPTER:
            # Build tool_result from available data (the parsed result dict)
            tool_result = data if isinstance(data, dict) else {}

            transition = canonicalize_transition(tool_result)

            if transition.target_sub_mode is not None:
                # Adapter found a canonical transition — apply it
                updates["expediente_sub_mode"] = transition.target_sub_mode
                logger.info(
                    "expediente_transition_canonicalized",
                    target=transition.target_sub_mode,
                    source=transition.source_channel,
                    conflicts=transition.conflicts,
                    tool_name=tool_name,
                )
        # ===================================================================

        return updates

    @staticmethod
    def _extract_pending_images(result: str) -> dict[str, Any] | None:
        """Extract pending images from enviar_imagenes_ejemplo result."""
        try:
            data = json.loads(result) if isinstance(result, str) else result
        except (json.JSONDecodeError, TypeError):
            return None

        if not isinstance(data, dict):
            return None

        return data.get("_pending_images")

    @staticmethod
    def _get_active_transition_marker(
        mode_context: dict[str, Any],
        sub_mode_name: str,
    ) -> dict[str, Any] | None:
        """Return marker when current turn is destination post-transition turn."""
        current_sub_mode = sub_mode_name.lower()

        marker = mode_context.get("expediente_transition_marker")
        if isinstance(marker, dict):
            marker_to = marker.get("to_sub_mode")
            if marker_to == current_sub_mode and marker.get("requires_kickoff"):
                return marker
            return None

        # Backward compatibility for contexts that only have legacy marker.
        legacy_from = mode_context.get("just_transitioned_from")
        if legacy_from:
            return {
                "from_sub_mode": legacy_from,
                "to_sub_mode": current_sub_mode,
                "tool_name": "legacy_marker",
                "requires_kickoff": True,
            }

        return None

    @staticmethod
    def _is_actionable_kickoff_response(response_text: str) -> bool:
        """Heuristic to detect whether first destination turn is actionable."""
        if not response_text:
            return False

        text = response_text.strip().lower()
        if not text:
            return False

        if "?" in text:
            return True

        actionable_cues = (
            "enviame",
            "envíame",
            "necesito",
            "indica",
            "indicame",
            "indícame",
            "dime",
            "confirma",
            "comparte",
            "facilita",
            "pasa",
        )
        return any(cue in text for cue in actionable_cues)

    @staticmethod
    def _build_transition_kickoff_message(
        *,
        sub_mode_name: str,
        mode_context: dict[str, Any],
    ) -> str:
        """Fallback destination kickoff to prevent dead-air after transition."""
        # Map UPPER_CASE sub_mode_name to lower-case constant for prefix lookup
        sub_mode_lower = sub_mode_name.lower()
        prefix = _progress_prefix(sub_mode_lower)

        if sub_mode_name == "COLLECT_BASE_DOCS":
            body = (
                "Perfecto. Para continuar necesito que me envies fotos legibles de la ficha tecnica, "
                "permiso de circulacion y DNI del titular (ambas caras)."
            )
            cta = "¿Tienes los documentos a mano para enviarlos?"
            return f"{prefix}\n\n{body}\n\n{cta}"

        if sub_mode_name == "COLLECT_PERSONAL":
            body = (
                "Perfecto. Ahora necesito tus datos personales para el expediente: nombre, apellidos, "
                "DNI/CIF, email, domicilio completo e ITV."
            )
            cta = "¿Tienes todo listo para empezar?"
            return f"{prefix}\n\n{body}\n\n{cta}"

        if sub_mode_name == "COLLECT_VEHICLE":
            body = "Perfecto. Ahora necesito los datos del vehiculo: marca, modelo, ano, matricula y bastidor (VIN)."
            cta = "¿Tienes la documentacion del vehiculo a mano?"
            return f"{prefix}\n\n{body}\n\n{cta}"

        if sub_mode_name == "COLLECT_WORKSHOP":
            # Keep workshop messaging coherent with explicit decision state.
            if mode_context.get("taller_propio") is False:
                body = (
                    "Perfecto. Confirmame si quieres que MSI gestione el certificado de taller por 85 EUR +IVA "
                    "para continuar con el expediente."
                )
            else:
                body = (
                    "Para la ITV necesitamos el certificado del taller. ¿Prefieres que MSI lo gestione por 85 EUR +IVA "
                    "o tienes taller propio registrado?"
                )
            cta = "¿Como prefieres proceder?"
            return f"{prefix}\n\n{body}\n\n{cta}"

        if sub_mode_name == "REVIEW_SUMMARY":
            # Terminal step — no CTA, just the informational message
            body = "Perfecto. Te presento el resumen del expediente en este paso y luego me confirmas si esta todo correcto."
            return f"{prefix}\n\n{body}"

        # Fallback for unknown sub-modes
        default_message = "Perfecto, seguimos con el siguiente paso del expediente."
        if prefix:
            return f"{prefix}\n\n{default_message}"
        return default_message

    # ------------------------------------------------------------------
    # LLM helpers — delegated to BaseModeNode
    # ------------------------------------------------------------------
    # _get_llm() and _invoke_with_fallback() are inherited from BaseModeNode.
    # EXPEDIENTE uses the default _default_max_tokens = 1500.

    # _execute_tool inherited from BaseModeNode

    @staticmethod
    def _build_client_context(state: ConversationState) -> str:
        """Build client-specific context string for the prompt."""
        parts: list[str] = []

        client_type = state.get("client_type", "particular")
        type_display = "PROFESIONAL" if client_type == "professional" else "PARTICULAR"
        parts.append(f"Cliente: **{type_display}**")

        user_name = state.get("user_name")
        if user_name:
            parts.append(f"Nombre: {user_name}")

        return "\n".join(parts)

    @staticmethod
    def _ai_message_to_dict(response: Any) -> dict[str, Any]:
        """Convert an LLM AIMessage to a dict for the messages list."""
        msg: dict[str, Any] = {
            "role": "assistant",
            "content": response.content or "",
        }
        if hasattr(response, "tool_calls") and response.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "name": tc["name"],
                    "args": tc["args"],
                }
                for tc in response.tool_calls
            ]
        return msg

    @staticmethod
    def _log_token_usage(response: Any, conversation_id: str) -> None:
        """Log token usage from LLM response metadata."""
        usage = getattr(response, "usage_metadata", None)
        if usage:
            logger.debug(
                "llm_token_usage",
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                conversation_id=conversation_id,
            )

    # ------------------------------------------------------------------
    # Layer A: deterministic pre-loop guard — photo completion intent
    # ------------------------------------------------------------------

    async def _guard_photo_completion_intent(
        self,
        user_message: str,
        mode_context: dict[str, Any],
        state: dict[str, Any],
        conversation_id: str,
        force: bool = False,
    ) -> bool:
        """
        Deterministic pre-loop guard for photo-completion intent.

        Fires only when BOTH conditions hold (unless ``force=True``):
        1. Current element_phase is "photos" (waiting for user to confirm photos).
        2. User message matches ``_PHOTO_COMPLETION_INTENT_RE`` (e.g. "listo",
           "ya", "enviadas", "hechas", …).

        When it fires, calls ``confirmar_fotos_elemento`` directly with
        ``usuario_confirma=True`` — without going through the LLM — and
        updates ``mode_context`` in-place so the subsequent ``_run_llm_loop``
        sees the advanced phase and avoids re-asking for photos.

        Args:
            user_message: Raw user text for regex matching.
            mode_context: Mutable mode context dict (updated in-place on fire).
            state: Full conversation state (needed to set ContextVars for tool).
            conversation_id: For structured logging.
            force: When True, skip the regex check and go straight to calling
                ``confirmar_fotos_elemento``. Used by the Layer B coherence
                interceptor when the LLM already called ``guardar_datos_elemento``
                while ``element_phase=="photos"`` — the guardar tool's error
                response signals the intent without the user having said "listo".

        Returns:
            True if the guard fired (phase advanced), False if it was a no-op.
        """
        # Condition 1: only fire when waiting for photo confirmation
        if mode_context.get("element_phase") != "photos":
            return False

        # Condition 2: user message must signal photo completion (skipped when force=True)
        # V2: Use IntentClassifier to distinguish COMPLETION_SIGNAL from REJECTION,
        # which fixes the "no es necesario" bug where the regex matched rejection phrases.
        if not force:
            _ic_v2 = self._get_intent_classifier_svc()
            if _ic_v2 is not None:
                # Build classification context from current element state
                from agent.services.intent_classifier import ClassificationContext

                _ic_element_code = mode_context.get("current_element_code") or ""
                _ic_pending_fields: list[str] = []
                _el_states: dict[str, Any] = mode_context.get("element_states") or {}
                _el_entry = _el_states.get(_ic_element_code, {})
                # Use display_name from 7-state dict if available
                _ic_element_name: str = _el_entry.get("display_name", _ic_element_code)

                # Extract last agent message for context
                _messages_hist = (
                    state.get("messages", []) if isinstance(state, dict) else []
                )
                _last_agent_msg: str = ""
                for _m in reversed(_messages_hist):
                    if isinstance(_m, dict) and _m.get("role") == "assistant":
                        _last_agent_msg = _m.get("content", "")[:200]
                        break
                    elif hasattr(_m, "type") and getattr(_m, "type") == "ai":
                        _last_agent_msg = str(getattr(_m, "content", ""))[:200]
                        break

                _has_images = bool(
                    isinstance(state, dict) and state.get("incoming_attachments")
                )

                _ic_ctx = ClassificationContext(
                    current_phase="photos",
                    current_element_name=_ic_element_name,
                    pending_fields=_ic_pending_fields,
                    last_agent_message=_last_agent_msg,
                )
                try:
                    _ic_result = await _ic_v2.classify(
                        user_message, _ic_ctx, _has_images
                    )
                    from agent.services.intent_classifier import UserIntent

                    if _ic_result.intent == UserIntent.REJECTION:
                        # User explicitly rejected / said "not needed" — do NOT fire guard
                        logger.info(
                            "photo_guard_skipped_rejection_intent",
                            conversation_id=conversation_id,
                            intent=_ic_result.intent.value,
                            confidence=_ic_result.confidence,
                            message_preview=user_message[:60],
                        )
                        return False
                    elif _ic_result.intent != UserIntent.COMPLETION_SIGNAL:
                        # Not a completion signal — fall through to regex as final arbiter
                        if not _PHOTO_COMPLETION_INTENT_RE.search(user_message):
                            return False
                except Exception as _ic_err:
                    logger.warning(
                        "photo_guard_intent_classifier_failed",
                        conversation_id=conversation_id,
                        error=str(_ic_err),
                    )
                    # Fallback to regex on error
                    if not _PHOTO_COMPLETION_INTENT_RE.search(user_message):
                        return False
            else:
                # V1 path: regex only
                if not _PHOTO_COMPLETION_INTENT_RE.search(user_message):
                    return False

        logger.info(
            "photo_guard_triggered",
            conversation_id=conversation_id,
            element_code=mode_context.get("current_element_code"),
            element_index=mode_context.get("current_element_index"),
            message_preview=user_message[:60],
        )

        try:
            # Set ContextVars so the tool can read state (same pattern as _run_llm_loop)
            full_state = dict(state)
            full_state["mode_context"] = mode_context
            set_current_state(full_state)
            set_current_state_for_image_tools(full_state)

            # TASK-09 Layer A hardening: Set element state to "confirming_photos" BEFORE
            # calling confirmar_fotos_elemento so the state machine reflects the intent
            # immediately (even if the tool is still polling).  Layer A's post-call
            # logic below will advance to the final state once the tool returns.
            # Backward-compatible: only runs when EXPEDIENTE_V2_ENABLED=True.
            if get_settings().EXPEDIENTE_V2_ENABLED:
                _pre_call_el_code: str | None = mode_context.get(
                    "current_element_code"
                ) or (
                    (mode_context.get("element_codes") or [None])[
                        mode_context.get("current_element_index", 0)
                    ]
                    if mode_context.get("element_codes")
                    else None
                )
                if _pre_call_el_code:
                    _set_element_state(
                        mode_context,
                        _pre_call_el_code,
                        ELEMENT_STATE_CONFIRMING_PHOTOS,
                    )
                    logger.debug(
                        "photo_guard_pre_call_state_set",
                        conversation_id=conversation_id,
                        element_code=_pre_call_el_code,
                        state=ELEMENT_STATE_CONFIRMING_PHOTOS,
                    )

            # Import and call the tool directly (bypasses LLM)
            from agent.tools.element_data_tools import confirmar_fotos_elemento

            guard_result = await confirmar_fotos_elemento.ainvoke(
                {"usuario_confirma": True}
            )

            # Parse result (tool may return dict or JSON string)
            try:
                guard_result_dict: dict[str, Any] = (
                    json.loads(guard_result)
                    if isinstance(guard_result, str)
                    else guard_result
                )
            except (json.JSONDecodeError, ValueError):
                guard_result_dict = {}

            if not isinstance(guard_result_dict, dict):
                guard_result_dict = {}

            # Apply tool flags to mode_context in-place
            _apply_tool_flags(mode_context, guard_result_dict, self._logger)

            # Extract context updates (phase advance, sub-mode transition, etc.)
            guard_context = self._extract_context_from_tool(
                "confirmar_fotos_elemento",
                {"usuario_confirma": True},
                guard_result
                if isinstance(guard_result, str)
                else json.dumps(guard_result_dict),
                mode_context,
            )
            mode_context.update(guard_context)

            # TASK-05 + TASK-09: Update per-element 7-state machine when EXPEDIENTE_V2_ENABLED.
            # After confirmar_fotos_elemento fires and mode_context is updated:
            # - new element_phase == "data" → photos confirmed → advance to photos_confirmed
            # - all_elements_complete → element is fully done (no data fields)
            # - else → still in confirming state (poll in-flight; pre-call already set it)
            if get_settings().EXPEDIENTE_V2_ENABLED:
                _guard_el_code: str | None = mode_context.get(
                    "current_element_code"
                ) or (
                    (mode_context.get("element_codes") or [None])[
                        mode_context.get("current_element_index", 0)
                    ]
                    if mode_context.get("element_codes")
                    else None
                )
                if _guard_el_code:
                    _raw_photos_count = guard_result_dict.get("photos_count", 0)
                    _guard_photos_count: int = (
                        _raw_photos_count if isinstance(_raw_photos_count, int) else 0
                    )
                    if _guard_photos_count == 0 and not guard_result_dict.get(
                        "success"
                    ):
                        # Phase-1 poll found 0 photos (retry path)
                        _set_element_state(
                            mode_context,
                            _guard_el_code,
                            ELEMENT_STATE_RETRY_PHOTOS,
                        )
                    elif guard_result_dict.get("all_elements_complete"):
                        # confirmar_fotos_elemento completed the last element (no data fields)
                        _set_element_state(
                            mode_context,
                            _guard_el_code,
                            ELEMENT_STATE_ELEMENT_COMPLETE,
                            data_complete=True,
                        )
                    elif mode_context.get("element_phase") == "data":
                        # Photos confirmed — advancing to data collection
                        _set_element_state(
                            mode_context,
                            _guard_el_code,
                            ELEMENT_STATE_PHOTOS_CONFIRMED,
                            photos_count=_guard_photos_count,
                        )
                    else:
                        # Poll in progress (confirming_photos)
                        _set_element_state(
                            mode_context,
                            _guard_el_code,
                            ELEMENT_STATE_CONFIRMING_PHOTOS,
                        )

            logger.info(
                "photo_guard_completed",
                conversation_id=conversation_id,
                tool_success=guard_result_dict.get("success", False),
                new_element_phase=mode_context.get("element_phase"),
                triggered_transition=bool(guard_context.get("expediente_sub_mode")),
                all_elements_complete=guard_result_dict.get(
                    "all_elements_complete", False
                ),
            )

            return True

        except Exception as guard_error:
            # Non-fatal: log warning and let LLM loop handle it normally
            self._logger.warning(
                "photo_guard_failed",
                conversation_id=conversation_id,
                error=str(guard_error),
                exc_info=True,
            )
            return False


# ---------------------------------------------------------------------------
# Tool registries per sub-mode
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
