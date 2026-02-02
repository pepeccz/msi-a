"""
MSI-a - Mode Transition Rules.

Source of truth for which transitions are allowed between modes.
This module encodes the transition matrix from docs/arquitectura-v2/07-transiciones-grafo.md.

Rules:
- Allowed transitions are explicit (whitelist)
- Anything not listed is PROHIBITED
- Escalation is allowed from ANY mode
- Each mode defines its timeout and nudge behaviour
"""

from __future__ import annotations

import structlog
from typing import Any

from agent.state.conversation_state import ConversationMode

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Transition matrix (whitelist)
# ---------------------------------------------------------------------------

# {source_mode: [allowed_target_modes]}
ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    "START": [
        "CONSULTA_MODE",
        "VIABILIDAD_MODE",
        "PRESUPUESTO_MODE",
    ],
    "CONSULTA_MODE": [
        "VIABILIDAD_MODE",
        "PRESUPUESTO_MODE",
        "ESCALATION",
    ],
    "VIABILIDAD_MODE": [
        "CONSULTA_MODE",
        "PRESUPUESTO_MODE",
        "ESCALATION",
    ],
    "PRESUPUESTO_MODE": [
        "CONSULTA_MODE",
        "VIABILIDAD_MODE",
        "EVALUACION_GATEWAY",
        "ESCALATION",
    ],
    "EVALUACION_GATEWAY": [
        "PRESUPUESTO_MODE",
        "EXPEDIENTE_MODE",
        "ESCALATION",
    ],
    "EXPEDIENTE_MODE": [
        "PRESUPUESTO_MODE",  # Only from REVISION sub-mode to modify elements
        "ESCALATION",
    ],
    "ESCALATION": [],  # Terminal
    "COMPLETED": [],     # Terminal
}


# ---------------------------------------------------------------------------
# Context preservation rules
# ---------------------------------------------------------------------------

# When transitioning FROM a mode, which keys to carry to the next mode
CONTEXT_PRESERVE_RULES: dict[str, dict[str, list[str]]] = {
    # From VIABILIDAD to PRESUPUESTO: carry element info
    "VIABILIDAD_MODE": {
        "PRESUPUESTO_MODE": [
            "categoria_slug",
            "elemento_confirmado",
            "vehiculo",
            "estimacion_precio",
        ],
    },
    # From PRESUPUESTO to EVALUACION_GATEWAY: carry quote data
    "PRESUPUESTO_MODE": {
        "EVALUACION_GATEWAY": [
            "elementos_confirmados",
            "element_codes",
            "tarifa_calculada",
            "categoria_slug",
        ],
    },
    # From EVALUACION_GATEWAY to EXPEDIENTE: carry confirmed quote
    "EVALUACION_GATEWAY": {
        "EXPEDIENTE_MODE": [
            "elementos_confirmados",
            "element_codes",
            "tarifa_calculada",
            "categoria_slug",
        ],
    },
}


# ---------------------------------------------------------------------------
# Mode properties
# ---------------------------------------------------------------------------

class ModeProperties:
    """Static properties for a conversation mode."""

    __slots__ = (
        "name", "blocking", "allows_digression",
        "timeout_seconds", "nudge_message",
    )

    def __init__(
        self,
        name: str,
        *,
        blocking: bool = False,
        allows_digression: bool = True,
        timeout_seconds: int = 600,
        nudge_message: str = "¿Sigues ahí? Respondé cualquier cosa para continuar.",
    ):
        self.name = name
        self.blocking = blocking
        self.allows_digression = allows_digression
        self.timeout_seconds = timeout_seconds
        self.nudge_message = nudge_message


MODE_PROPERTIES: dict[str, ModeProperties] = {
    "CONSULTA_MODE": ModeProperties(
        "CONSULTA_MODE",
        blocking=False,
        allows_digression=True,
        timeout_seconds=600,      # 10 min
        nudge_message="¿Sigues ahí? ¿Te puedo ayudar con algo más?",
    ),
    "VIABILIDAD_MODE": ModeProperties(
        "VIABILIDAD_MODE",
        blocking=False,
        allows_digression=True,
        timeout_seconds=900,      # 15 min
        nudge_message="¿Querés que busque un presupuesto detallado?",
    ),
    "PRESUPUESTO_MODE": ModeProperties(
        "PRESUPUESTO_MODE",
        blocking=False,
        allows_digression=False,
        timeout_seconds=1200,     # 20 min
        nudge_message="¿Te gustaría que guarde este presupuesto y vuelvas luego?",
    ),
    "EVALUACION_GATEWAY": ModeProperties(
        "EVALUACION_GATEWAY",
        blocking=True,
        allows_digression=False,
        timeout_seconds=300,      # 5 min
        nudge_message="¿Confirmás que querés iniciar el expediente?",
    ),
    "EXPEDIENTE_MODE": ModeProperties(
        "EXPEDIENTE_MODE",
        blocking=True,
        allows_digression=False,
        timeout_seconds=1800,     # 30 min per sub-mode
        nudge_message="¿Estás teniendo dificultades? Puedo conectarte con un agente.",
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_transition_allowed(source: str, target: str) -> bool:
    """
    Check if a mode transition is allowed.

    Escalation is always allowed from any mode.

    Args:
        source: Current mode name.
        target: Target mode name.

    Returns:
        True if the transition is in the whitelist.
    """
    if target == "ESCALATION":
        return True

    allowed = ALLOWED_TRANSITIONS.get(source, [])
    return target in allowed


def get_preserve_keys(source: str, target: str) -> list[str]:
    """
    Get context keys to preserve when transitioning between modes.

    Args:
        source: Current mode.
        target: Target mode.

    Returns:
        List of context keys to carry over.
    """
    rules = CONTEXT_PRESERVE_RULES.get(source, {})
    return rules.get(target, [])


def get_mode_properties(mode: str) -> ModeProperties:
    """
    Get static properties for a mode.

    Returns default (non-blocking, permissive) for unknown modes.
    """
    return MODE_PROPERTIES.get(
        mode,
        ModeProperties(mode, blocking=False, allows_digression=True),
    )


def validate_transition(source: str, target: str) -> tuple[bool, str]:
    """
    Validate a transition and return a reason if prohibited.

    Args:
        source: Current mode.
        target: Target mode.

    Returns:
        Tuple of (is_allowed, reason_if_prohibited).
    """
    if is_transition_allowed(source, target):
        return True, ""

    # Build a helpful reason
    reason_map = {
        ("CONSULTA_MODE", "EXPEDIENTE_MODE"): "No se puede ir a expediente sin presupuesto",
        ("CONSULTA_MODE", "EVALUACION_GATEWAY"): "No hay presupuesto calculado",
        ("VIABILIDAD_MODE", "EXPEDIENTE_MODE"): "Falta presupuesto detallado",
        ("VIABILIDAD_MODE", "EVALUACION_GATEWAY"): "Falta cálculo exacto",
        ("PRESUPUESTO_MODE", "EXPEDIENTE_MODE"): "Debe pasar por EVALUACION_GATEWAY",
        ("EVALUACION_GATEWAY", "CONSULTA_MODE"): "Ya tiene presupuesto, debe decidir sí/no",
        ("EVALUACION_GATEWAY", "VIABILIDAD_MODE"): "Retroceso excesivo",
        ("EXPEDIENTE_MODE", "CONSULTA_MODE"): "Perdería datos del caso",
        ("EXPEDIENTE_MODE", "VIABILIDAD_MODE"): "Contexto incompatible",
    }

    reason = reason_map.get(
        (source, target),
        f"Transición {source} → {target} no está permitida",
    )

    logger.warning(
        "transition_prohibited",
        source=source,
        target=target,
        reason=reason,
    )

    return False, reason
