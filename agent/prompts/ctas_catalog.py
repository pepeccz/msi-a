"""Canonical CTAs for PRE_EXPEDIENTE phases. Import-only module.

Single source of truth for all 5 CTA literals used across discovery,
pricing, and post-price prompt phases.
"""
from __future__ import annotations

from types import MappingProxyType

_CTAS_RAW: dict[int, str] = {
    1: "¿Quieres que te ayude con alguna homologación?",
    2: "¿Te interesa alguno? Puedo darte el precio exacto.",
    3: "¿Te muestro ejemplos de cómo deben ser las fotos o te calculo el presupuesto?",
    4: "¿Te enseño ejemplos de las fotos que necesitaremos o abrimos el expediente directamente?",
    5: "¿Abrimos expediente o tienes alguna duda?",
}

CTAS: MappingProxyType[int, str] = MappingProxyType(_CTAS_RAW)


def get_cta(n: int) -> str:
    """Return the canonical CTA literal for state N (1–5).

    Raises KeyError if the key is not in the catalog (fail-fast — catalog is trusted).
    """
    return CTAS[n]
