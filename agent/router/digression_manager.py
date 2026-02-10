"""
MSI-a - Digression Manager (Option B: Parallel Listener).

Detects when a user message in a focused mode (PRESUPUESTO, EXPEDIENTE) is
actually an off-topic question that should be handled by another mode.

Design:
- Only checks messages in "focused" modes (where digression is NOT allowed)
- Permissive modes (CONSULTA, VIABILIDAD) handle everything themselves
- Uses lightweight keyword analysis first, LLM only when ambiguous
- Does NOT process the message - only decides WHERE it should go

Integration with LangGraph:
- Called as a pre-processing step in the router node
- Returns a DigressionResult that the router uses to redirect
- The original mode's context is saved (via transition_mode)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

import structlog

from agent.router.mode_transitions import get_mode_properties

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class DigressionType(str, Enum):
    """Categories of detected digressions."""

    CONSULTA_GENERAL = "consulta_general"          # "¿Cuánto tarda?"
    VIABILIDAD_OTRO = "viabilidad_otro"            # "¿Se puede otro elemento?"
    ESCALACION = "escalacion"                      # "Quiero hablar con alguien"
    NOT_A_DIGRESSION = "not_a_digression"


@dataclass
class DigressionResult:
    """Outcome of the digression check."""

    is_digression: bool
    digression_type: DigressionType
    target_mode: str | None = None
    original_mode: str | None = None  # Where we were
    context_to_preserve: list[str] | None = None  # Keys to carry


# Patterns that strongly indicate digression in focused modes
_DIGRESSION_PATTERNS: list[tuple[re.Pattern[str], DigressionType, str]] = [
    # Escalation (always a digression)
    (re.compile(r"\b(persona|humano|agente|hablar con alguien)\b", re.I),
     DigressionType.ESCALACION, "ESCALATION"),

    # General consultation
    (re.compile(r"\b(qué es|cómo funciona|para qué sirve|es obligatorio|cuánto tarda)\b", re.I),
     DigressionType.CONSULTA_GENERAL, "CONSULTA_MODE"),

    # Viability of a DIFFERENT element (while in presupuesto/expediente)
    (re.compile(r"\b(se puede|es posible|está permitido)\s+(también|además)\b", re.I),
     DigressionType.VIABILIDAD_OTRO, "PRESUPUESTO_MODE"),
]

# Patterns that are NOT digressions in focused modes
# (they look like off-topic but are actually in-context)
_IN_CONTEXT_PATTERNS: list[re.Pattern[str]] = [
    # Asking about docs needed for current process
    re.compile(r"\b(qué (fotos?|documentos?|datos?)\s+(necesito|faltan|me piden))\b", re.I),
    # Asking about current price / quote
    re.compile(r"\b(cuánto (era|sale|cuesta)\s+(eso|esto|el presupuesto))\b", re.I),
    # Process-related questions
    re.compile(r"\b(cuándo\s+(termina|se completa|estará listo))\b", re.I),
]


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class DigressionManager:
    """
    Detect off-topic messages in focused modes.

    Only active when:
    - current_mode is NOT permissive (i.e., not CONSULTA or VIABILIDAD)
    - current_mode allows_digression is False

    Architecture: Parallel listener in LangGraph
    - Runs BEFORE the mode node processes the message
    - If digression detected → redirect to appropriate mode
    - If not digression → let mode node handle normally
    """

    async def check(
        self,
        message: str,
        current_mode: str,
        mode_context: dict[str, Any] | None = None,
    ) -> DigressionResult:
        """
        Check if a message is a digression from the current mode.

        Args:
            message: User message text.
            current_mode: Current conversation mode.
            mode_context: Current mode's context data.

        Returns:
            DigressionResult indicating if and where to redirect.
        """
        properties = get_mode_properties(current_mode)

        # Permissive modes handle everything internally
        if properties.allows_digression:
            return DigressionResult(
                is_digression=False,
                digression_type=DigressionType.NOT_A_DIGRESSION,
            )

        # START mode: no digression check needed
        if current_mode == "START":
            return DigressionResult(
                is_digression=False,
                digression_type=DigressionType.NOT_A_DIGRESSION,
            )

        # Check if it's explicitly in-context first
        if self._is_in_context(message, current_mode):
            return DigressionResult(
                is_digression=False,
                digression_type=DigressionType.NOT_A_DIGRESSION,
            )

        # Check digression patterns
        return self._check_patterns(message, current_mode)

    # -- Pattern matching ------------------------------------------------

    def _check_patterns(self, message: str, current_mode: str) -> DigressionResult:
        """Check message against known digression patterns."""
        for pattern, dig_type, target_mode in _DIGRESSION_PATTERNS:
            if pattern.search(message):
                logger.info(
                    "digression_detected",
                    type=dig_type.value,
                    target=target_mode,
                    current_mode=current_mode,
                    message_preview=message[:80],
                )
                return DigressionResult(
                    is_digression=True,
                    digression_type=dig_type,
                    target_mode=target_mode,
                    original_mode=current_mode,
                    context_to_preserve=self._get_preserve_keys(current_mode),
                )

        # No pattern matched → not a digression
        return DigressionResult(
            is_digression=False,
            digression_type=DigressionType.NOT_A_DIGRESSION,
        )

    def _is_in_context(self, message: str, current_mode: str) -> bool:
        """Check if the message is actually in-context for the current mode."""
        for pattern in _IN_CONTEXT_PATTERNS:
            if pattern.search(message):
                return True
        return False

    @staticmethod
    def _get_preserve_keys(mode: str) -> list[str]:
        """Keys to preserve when temporarily leaving a mode."""
        if mode == "PRESUPUESTO_MODE":
            return [
                "elementos_confirmados", "element_codes",
                "tarifa_calculada", "categoria_slug",
            ]
        if mode == "EXPEDIENTE_MODE":
            return [
                "case_id", "sub_modo", "datos_personales",
                "datos_vehiculo", "element_codes",
            ]
        return []


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_manager: DigressionManager | None = None


def get_digression_manager() -> DigressionManager:
    global _manager
    if _manager is None:
        _manager = DigressionManager()
    return _manager
