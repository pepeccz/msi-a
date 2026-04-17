"""Cross-mode shared context models for the conversation agent."""
from __future__ import annotations
from typing import Any, TypedDict


class SharedContext(TypedDict, total=False):
    """Data that persists across ALL mode transitions. Never wiped by transition_mode()."""

    element_codes: list[str]
    tarifa_calculada: dict[str, Any] | None
    categoria_slug: str | None
    precio_comunicado: bool
    imagenes_enviadas: bool
    imagenes_enviadas_codigos: list[str]
    vehiculo: dict[str, str] | None
    elementos_confirmados: list[dict[str, Any]]
    presupuesto_images_shown: bool
    warnings_acknowledged: bool
