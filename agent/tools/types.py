"""Typed contracts for agent tool return values and _internal_flags.

Two state-update channels co-exist during the refactor:

1. ``_internal_flags`` (legacy) — tools that have not yet been migrated still
   return this key.  ``generic_loop._apply_internal_flags()`` reads it.

2. ``_state_update`` (canonical, new) — thin-wrapper tools introduced in the
   refactor return this key instead.  ``_apply_state_updates()`` in
   generic_loop.py reads it first, then falls back to ``_internal_flags``.

``ToolStateUpdate`` is the comprehensive TypedDict that covers ALL keys from
BOTH channels.  Static-analysis tools and future tests can use it to verify
that tool return values match what generic_loop.py and the mode nodes expect.
"""

from __future__ import annotations

from typing import Any, TypedDict


class PricingFlags(TypedDict, total=False):
    precio_comunicado: bool
    imagenes_enviadas: bool
    # waiting_for_image_choice removed — dead flag (Spec 4 / AD-2)
    imagenes_envio_intent_creado: bool


class ImageFlags(TypedDict, total=False):
    imagenes_enviadas: bool
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
    expediente_intro_sent: bool
    datos_updated: bool
    confirmed_fields: list[str]
    can_narrate_completion: bool


class TransitionFlags(TypedDict, total=False):
    _transition_to: str
    _chain_next_mode: bool


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

    Tools that have been refactored to thin wrappers return this dict under
    the ``_state_update`` key instead of the legacy ``_internal_flags`` key.

    ``generic_loop._apply_state_updates()`` reads ``_state_update`` first and
    falls back to ``_internal_flags`` for backward compatibility.
    """

    # ── Pricing / LLM ────────────────────────────────────────────────────────
    precio_comunicado: bool
    """True once the LLM has communicated the price to the user."""

    imagenes_enviadas: bool
    """True once example images have been sent for the current quote."""

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

    expediente_intro_sent: bool
    """Alias for intro_already_sent (legacy key — prefer intro_already_sent)."""

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

    _chain_next_mode: bool
    """If True, the mode runner chains to _transition_to without a new turn."""

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
