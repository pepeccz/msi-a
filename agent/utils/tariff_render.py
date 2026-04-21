"""Deterministic tariff summary renderer for the safety-net path.

When `BaseModeNode.handle` exits with an empty `ai_response` BUT
`mode_context["tarifa_calculada"]` is populated (typically post-self-heal
tail loop), the safety net renders this deterministic price summary
instead of the generic error template — so the user receives the price
they were entitled to receive.

Castilian tuteo only (per commit 415963c). Pure function — no I/O.
"""
from __future__ import annotations

from typing import Any

from agent.prompts.ctas_catalog import CTAS

_VALIDITY_FOOTER = "_Precios válidos por 30 días._"
_SEVERITY_ICONS: dict[str, str] = {
    "error": "🔴",
    "warning": "⚠️",
    "info": "ℹ️",
}


def _coerce_price(raw: Any) -> str | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value.is_integer():
        return f"{int(value)}"
    return f"{value:.2f}".rstrip("0").rstrip(".")


def render_tariff_summary_from_state(mode_context: dict) -> str:
    """Render a user-facing price summary from `mode_context["tarifa_calculada"]`.

    Returns an empty string when the payload is missing or malformed — the
    caller is responsible for falling back to the generic template.

    Output structure (Castilian tuteo):

        *<tier_name>: <price>€ +IVA*

        Elementos incluidos:
        - <elem name>
        ...

        ⚠️ <warning message>
        ...

        _Precios válidos por 30 días._

        ¿Te enseño ejemplos de las fotos que necesitaremos o abrimos el expediente directamente?
    """
    tarifa = mode_context.get("tarifa_calculada") if mode_context else None
    if not isinstance(tarifa, dict):
        return ""

    datos = tarifa.get("datos")
    if not isinstance(datos, dict):
        return ""

    price_str = _coerce_price(datos.get("price"))
    if price_str is None:
        return ""

    tier_name = datos.get("tier_name") or "Tarifa"
    elements = datos.get("elements") or []
    warnings = datos.get("warnings") or []

    lines: list[str] = [f"*{tier_name}: {price_str}€ +IVA*", ""]

    if elements:
        lines.append("Elementos incluidos:")
        for elem_name in elements:
            lines.append(f"- {elem_name}")
        lines.append("")

    if warnings:
        for warn in warnings:
            if not isinstance(warn, dict):
                continue
            message = warn.get("message")
            if not message:
                continue
            severity = (warn.get("severity") or "warning").lower()
            icon = _SEVERITY_ICONS.get(severity, "⚠️")
            lines.append(f"{icon} {message}")
        lines.append("")

    lines.append(_VALIDITY_FOOTER)
    lines.append("")
    lines.append(CTAS[4])

    return "\n".join(lines).rstrip()
