"""Typed contracts for agent tool return values and _internal_flags."""

from __future__ import annotations

from typing import Any, TypedDict


class PricingFlags(TypedDict, total=False):
    precio_comunicado: bool
    imagenes_enviadas: bool
    waiting_for_image_choice: bool
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
