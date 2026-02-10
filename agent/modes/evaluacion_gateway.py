"""
MSI-a - EVALUACION_GATEWAY Node.

Simple yes/no confirmation gateway before starting an expediente.
This is NOT a full LLM-driven mode — it's a lightweight decision node.

Flow:
    1. Present a summary of the confirmed quote
    2. Ask: "¿Quieres iniciar el expediente?"
    3. Parse yes/no response
    4. YES → transition to EXPEDIENTE_MODE
    5. NO  → return to PRESUPUESTO_MODE

Max 2 retries on ambiguous responses before returning to PRESUPUESTO_MODE.
This mode is BLOCKING — user must answer yes or no.
"""

from __future__ import annotations

import re
from datetime import datetime, UTC
from typing import Any

import structlog

from agent.modes.base_mode import BaseModeNode
from agent.state.conversation_state import ConversationState

logger = structlog.get_logger(__name__)

# --- Response patterns ---

YES_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(s[ií]|dale|vale|adelante|perfecto|ok|okey|venga|claro|genial|va|vamos|por supuesto|exacto|afirmativo|correcto)\b", re.IGNORECASE),
    re.compile(r"^(s[ií]|dale|ok|va)$", re.IGNORECASE),  # Short exact matches
]

NO_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(no|todav[ií]a no|mejor no|lo pienso|ahora no|luego|despu[eé]s|nop|nel|nah|paso|cancel)\b", re.IGNORECASE),
    re.compile(r"^no+$", re.IGNORECASE),  # "nooo"
]

# Max ambiguous responses before returning to PRESUPUESTO_MODE
MAX_GATEWAY_RETRIES = 2


class EvaluacionGatewayNode(BaseModeNode):
    """
    EVALUACION_GATEWAY: Simple yes/no confirmation before expediente.

    This is deliberately NOT an LLM-driven node. It uses pattern matching
    to parse the user's response. This keeps it fast, cheap, and predictable.
    """

    def __init__(self) -> None:
        super().__init__("EVALUACION_GATEWAY")

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    async def _process_message(
        self,
        message: str,
        state: ConversationState,
    ) -> dict[str, Any]:
        """
        Process user response in EVALUACION_GATEWAY.

        First invocation (no gateway context): present the confirmation prompt.
        Subsequent invocations: parse the yes/no response.
        """
        mode_context = dict(state.get("mode_context", {}))
        gateway_attempts = mode_context.get("gateway_attempts", 0)

        # First invocation: present the question
        if not mode_context.get("gateway_question_asked"):
            return self._present_confirmation(state, mode_context)

        # Parse response
        user_answer = self._classify_response(message)

        if user_answer == "yes":
            return self._handle_yes(state, mode_context)
        elif user_answer == "no":
            return self._handle_no(state, mode_context)
        else:
            return self._handle_ambiguous(
                message, state, mode_context, gateway_attempts,
            )

    def get_tools(self) -> list:
        """EVALUACION_GATEWAY has no tools — it's pattern-based."""
        return []

    # ------------------------------------------------------------------
    # Response classification
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_response(message: str) -> str:
        """Classify user response as 'yes', 'no', or 'ambiguous'."""
        text = message.strip()

        # Check yes patterns first
        for pattern in YES_PATTERNS:
            if pattern.search(text):
                return "yes"

        # Check no patterns
        for pattern in NO_PATTERNS:
            if pattern.search(text):
                return "no"

        return "ambiguous"

    # ------------------------------------------------------------------
    # Response handlers
    # ------------------------------------------------------------------

    def _present_confirmation(
        self,
        state: ConversationState,
        mode_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Present the confirmation question with quote summary."""
        precio = mode_context.get("precio_exacto")

        # Fallback: extract from tarifa_calculada (PRESUPUESTO stores it there)
        if not precio:
            tarifa = mode_context.get("tarifa_calculada")
            if isinstance(tarifa, dict):
                datos = tarifa.get("datos", {})
                precio = datos.get("price")
            elif isinstance(tarifa, str):
                import json
                try:
                    tarifa_parsed = json.loads(tarifa)
                    datos = tarifa_parsed.get("datos", {})
                    precio = datos.get("price")
                except (json.JSONDecodeError, TypeError):
                    pass

        element_codes = mode_context.get("element_codes", [])

        # Build summary
        parts: list[str] = []

        if precio:
            parts.append(f"**Presupuesto confirmado: {precio} EUR +IVA**")

        if element_codes:
            codes_str = ", ".join(element_codes)
            parts.append(f"Elementos: {codes_str}")

        parts.append("")
        parts.append(
            "Para gestionar la homologación necesitaré recopilar "
            "algunos datos y documentación. "
            "¿Quieres que iniciemos el expediente?"
        )

        updated_context = {
            **mode_context,
            "gateway_question_asked": True,
            "gateway_attempts": 0,
        }

        self._logger.info(
            "gateway_question_presented",
            precio=precio,
            elements_count=len(element_codes),
        )

        return {
            "ai_response": "\n".join(parts),
            "mode_context": updated_context,
        }

    def _handle_yes(
        self,
        state: ConversationState,
        mode_context: dict[str, Any],
    ) -> dict[str, Any]:
        """User confirmed — transition to EXPEDIENTE_MODE."""
        self._logger.info("gateway_confirmed")

        # Preserve critical context for EXPEDIENTE_MODE
        updated_context = {
            **mode_context,
            "gateway_confirmed": True,
            "gateway_question_asked": False,  # Reset for potential re-entry
            "gateway_attempts": 0,
        }

        return {
            "ai_response": (
                "¡Perfecto! Vamos a iniciar el expediente. "
                "Te voy a ir pidiendo la información paso a paso."
            ),
            "mode_context": updated_context,
            "current_mode": "EXPEDIENTE_MODE",
        }

    def _handle_no(
        self,
        state: ConversationState,
        mode_context: dict[str, Any],
    ) -> dict[str, Any]:
        """User declined — return to PRESUPUESTO_MODE."""
        self._logger.info("gateway_declined")

        updated_context = {
            **mode_context,
            "gateway_confirmed": False,
            "gateway_question_asked": False,
            "gateway_attempts": 0,
        }

        return {
            "ai_response": (
                "Sin problema. El presupuesto queda guardado "
                "por si lo Quieres retomar más adelante. "
                "¿Hay algo más en lo que te pueda ayudar?"
            ),
            "mode_context": updated_context,
            "current_mode": "PRESUPUESTO_MODE",
        }

    def _handle_ambiguous(
        self,
        message: str,
        state: ConversationState,
        mode_context: dict[str, Any],
        attempts: int,
    ) -> dict[str, Any]:
        """User response was ambiguous — reprompt or give up."""
        attempts += 1

        self._logger.info(
            "gateway_ambiguous",
            attempt=attempts,
            message_preview=message[:60],
        )

        if attempts >= MAX_GATEWAY_RETRIES:
            # Give up — return to PRESUPUESTO_MODE
            self._logger.warning(
                "gateway_max_retries",
                attempts=attempts,
            )

            updated_context = {
                **mode_context,
                "gateway_question_asked": False,
                "gateway_attempts": 0,
            }

            return {
                "ai_response": (
                    "Entiendo que todavía no estás seguro. "
                    "No hay problema, el presupuesto queda guardado. "
                    "Cuando quieras iniciar el expediente, avisame."
                ),
                "mode_context": updated_context,
                "current_mode": "PRESUPUESTO_MODE",
            }

        # Reprompt
        updated_context = {
            **mode_context,
            "gateway_attempts": attempts,
        }

        return {
            "ai_response": (
                "Necesito una respuesta clara para continuar: "
                "¿Quieres iniciar el expediente de homologación? "
                "Responde **sí** o **no**."
            ),
            "mode_context": updated_context,
        }
