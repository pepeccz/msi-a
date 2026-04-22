"""Typed contracts for agent tool return values and state-update dict.

Two state-update channels co-exist:

1. ``_state_update`` (canonical, ADR-005) — all current tools return this key.
   The ``post_tool_node`` in ``post_tool_hooks.py`` extracts it and merges
   into ``mode_context``.

2. ``_internal_flags`` (legacy fallback) — kept as a read path in
   ``tool_executor`` for backward compatibility with any tool that has not
   been migrated. Do NOT use for new tools.

``ToolStateUpdate`` is the comprehensive TypedDict that covers ALL keys from
BOTH channels — useful for static analysis and tests to verify tool return
shapes match what ``post_tool_node`` expects.
"""

from __future__ import annotations

from typing import Any, TypedDict


class PricingFlags(TypedDict, total=False):
    precio_comunicado: bool
    imagenes_enviadas: bool
    imagenes_enviadas_codigos: list[str]
    # waiting_for_image_choice removed — dead flag (Spec 4 / AD-2)
    imagenes_envio_intent_creado: bool


class ImageFlags(TypedDict, total=False):
    imagenes_enviadas: bool
    imagenes_enviadas_codigos: list[str]
    imagenes_envio_intent_creado: bool
    imagenes_delivery_request_id: str
    imagenes_delivery_outcome: str
    delivery_intent_created: bool
    delivery_scope: str
    delivery_outcome_status: str
    can_narrate_delivery_success: bool


class VariantFlags(TypedDict, total=False):
    pending_variants: list[dict[str, Any]]


class ExpedienteFlags(TypedDict, total=False):
    intro_already_sent: bool
    datos_updated: bool
    confirmed_fields: list[str]
    can_narrate_completion: bool


class TransitionFlags(TypedDict, total=False):
    _transition_to: str


# Union for annotation (static analysis only — runtime type is still plain dict)
InternalFlags = (
    PricingFlags | ImageFlags | VariantFlags | ExpedienteFlags | TransitionFlags
)


class ToolResult(TypedDict, total=False):
    """Preparatory contract for Phase 3. Not enforced at runtime."""

    success: bool
    message: str
    data: Any
    error: str | None
    _internal_flags: InternalFlags


# ---------------------------------------------------------------------------
# ToolStateUpdate — unified contract for _state_update (new canonical channel)
# ---------------------------------------------------------------------------
# Keys are collected from:
#   - _internal_flags sub-types (PricingFlags, ImageFlags, VariantFlags,
#     ExpedienteFlags, TransitionFlags) — all tools use these
#   - context propagation keys (inlined in presupuesto_mode.py fallback) — keys
#     propagated into nested mode_context so tools see fresh values across iterations
#   - case_collection_update / case_collection — legacy FSM channel used by
#     case_tools.py and element_data_tools.py (kept for backward compat)
#
# All keys are optional (total=False) — a single tool will only populate
# the subset relevant to its operation.
# ---------------------------------------------------------------------------


class ToolStateUpdate(TypedDict, total=False):
    """
    Comprehensive state-update contract for the new ``_state_update`` channel.

    Tools return this dict under the ``_state_update`` key. The
    ``post_tool_node`` (``post_tool_hooks.py``) reads it and merges into
    the parent ``mode_context``. Legacy ``_internal_flags`` is a fallback
    read path in ``tool_executor`` for any unmigrated tool.
    """

    # ── Pricing / LLM ────────────────────────────────────────────────────────
    precio_comunicado: bool
    """True once the LLM has communicated the price to the user."""

    imagenes_enviadas: bool
    """True once example images have been sent for the current quote."""

    imagenes_enviadas_codigos: list[str]
    """Per-element tracking: list of element codes (uppercase) plus '_BASE_DOCS' sentinel
    for base documentation images that have been sent. Empty list means no images sent yet.
    This is the source of truth; imagenes_enviadas is a computed bool derivative."""

    # waiting_for_image_choice was removed — dead flag (Spec 4 / AD-2):
    # the flag was never set to True by any code path; its presence in the
    # router's downgrade logic caused permanent suppression of VER_IMAGENES /
    # ABRIR_EXPEDIENTE intents.  Tools that reset it to False are cleaned up.

    imagenes_envio_intent_creado: bool
    """True once the image-delivery intent has been recorded."""

    # ── Image delivery ────────────────────────────────────────────────────────
    imagenes_delivery_request_id: str
    """UUID of the image delivery request created by enviar_imagenes_ejemplo."""

    imagenes_delivery_outcome: str
    """Serialised JSON of the delivery outcome dict."""

    delivery_intent_created: bool
    """True when a delivery intent record has been inserted."""

    delivery_scope: str
    """Scope string of the current image delivery (e.g. 'presupuesto')."""

    delivery_outcome_status: str
    """Status string of the delivery outcome ('intent_created', 'sent', …)."""

    can_narrate_delivery_success: bool
    """True when the LLM is allowed to describe successful image delivery."""

    # ── Variant resolution ────────────────────────────────────────────────────
    pending_variants: list[dict[str, Any]]
    """List of PendingVariantGroup dicts waiting for user clarification."""

    element_codes: list[str]
    """Resolved element codes after variant selection."""

    # ── Expediente / case collection ─────────────────────────────────────────
    intro_already_sent: bool
    """True once the expediente onboarding intro has been sent."""

    datos_updated: bool
    """True after personal / vehicle data has been saved successfully."""

    confirmed_fields: list[str]
    """List of field names confirmed in the current data-collection step."""

    can_narrate_completion: bool
    """True when the LLM can tell the user the step is complete."""

    # ── Presupuesto / pricing context ─────────────────────────────────────────
    tarifa_calculada: Any
    """Serialised tariff dict stored in mode_context after price calculation."""

    price_authority: dict[str, Any]
    """Authority dict written by calcular_tarifa_con_elementos for audit."""

    categoria_slug: str
    """Active category slug propagated from element identification."""

    elemento_confirmado: bool
    """True once the user has confirmed the element identification."""

    # ── Mode transitions ──────────────────────────────────────────────────────
    _transition_to: str
    """Target mode name for an explicit mode transition."""

    # ── Expediente extra flags (case_service) ────────────────────────────────
    taller_updated: bool
    """True after taller decision/data has been saved."""

    case_finalized: bool
    """True once the expediente has been submitted for review."""

    expediente_edited: bool
    """True when the user has triggered an edit of a prior section."""

    edit_target_sub_mode: str
    """Sub-mode name the user is returning to for editing."""

    # ── Legacy FSM (case_collection_update / case_collection) ────────────────
    # These keys are read by expediente_mode.py (expediente_guardrails.py was removed).
    # New tools should NOT add these; they exist for backward compatibility
    # while the migration from FSM → mode_context is in progress.
    case_collection_update: dict[str, Any]
    """Legacy FSM shape: {"case_collection": {...updates...}}."""

    case_collection: dict[str, Any]
    """Flat case-collection state dict (alternative legacy shape)."""
