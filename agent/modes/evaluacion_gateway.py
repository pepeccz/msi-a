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
from agent.state.conversation_state import ConversationState, transition_mode
from agent.router.mode_transitions import get_preserve_keys

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

        # ALWAYS try to classify the response first
        # (The confirmation question may have been presented by PRESUPUESTO_MODE
        # in the previous turn when transitioning here)
        user_answer = self._classify_response(message)

        if user_answer == "yes":
            return self._handle_yes(state, mode_context)
        elif user_answer == "no":
            return self._handle_no(state, mode_context)

        # Ambiguous response: present question if first time, or handle retry
        if not mode_context.get("gateway_question_asked"):
            return self._present_confirmation(state, mode_context)
        
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
        # Extract price from tarifa_calculada (set by PRESUPUESTO_MODE)
        precio = None
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
        """User confirmed — transition to EXPEDIENTE_MODE via transition_mode()."""
        self._logger.info("gateway_confirmed")

        preserve = get_preserve_keys("EVALUACION_GATEWAY", "EXPEDIENTE_MODE")
        updates = transition_mode(state, "EXPEDIENTE_MODE", preserve_keys=preserve)

        # Build the 6-step overview message
        steps_overview = (
            "1️⃣ Fotos y datos de los elementos\n"
            "2️⃣ Documentación base del vehículo\n"
            "3️⃣ Datos personales\n"
            "4️⃣ Datos del vehículo\n"
            "5️⃣ Certificado del taller\n"
            "6️⃣ Revisión final"
        )

        # Try to extract the first element name from tarifa_calculada
        first_element_name: str | None = None
        try:
            tarifa = mode_context.get("tarifa_calculada")
            if isinstance(tarifa, str):
                import json
                try:
                    tarifa = json.loads(tarifa)
                except (json.JSONDecodeError, ValueError):
                    tarifa = None
            if isinstance(tarifa, dict):
                # Try documentacion.elementos first (full structure)
                doc_elementos = tarifa.get("documentacion", {}).get("elementos", [])
                if doc_elementos and isinstance(doc_elementos, list):
                    first_el = doc_elementos[0]
                    if isinstance(first_el, dict):
                        first_element_name = (
                            first_el.get("nombre")
                            or first_el.get("name")
                        )
                # Fallback: datos.elements list
                if not first_element_name:
                    datos = tarifa.get("datos", {})
                    elements_list = datos.get("elements", [])
                    if elements_list and isinstance(elements_list, list):
                        first_element_name = str(elements_list[0])
        except Exception:
            # Defensive: never let element lookup crash the gateway transition
            first_element_name = None

        # Build closing line (with or without element name)
        if first_element_name:
            closing = (
                f"Empezamos con las fotos y datos de tu *{first_element_name}*. "
                "Te iré pidiendo todo paso a paso, ¡sin agobios! 📸"
            )
        else:
            closing = (
                "Empezamos por las fotos y datos de tus elementos. "
                "Te iré pidiendo todo paso a paso, ¡sin agobios! 📸"
            )

        updates["ai_response"] = (
            "¡Perfecto! Voy a abrir tu expediente. El proceso tiene 6 pasos:\n\n"
            f"{steps_overview}\n\n"
            f"{closing}"
        )

        return updates

    def _handle_no(
        self,
        state: ConversationState,
        mode_context: dict[str, Any],
    ) -> dict[str, Any]:
        """User declined — return to PRESUPUESTO_MODE via transition_mode()."""
        self._logger.info("gateway_declined")

        preserve = get_preserve_keys("EVALUACION_GATEWAY", "PRESUPUESTO_MODE")
        updates = transition_mode(state, "PRESUPUESTO_MODE", preserve_keys=preserve)

        updates["ai_response"] = (
            "Sin problema. El presupuesto queda guardado "
            "por si lo quieres retomar más adelante. "
            "¿Hay algo más en lo que te pueda ayudar?"
        )

        return updates

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
            # Give up — return to PRESUPUESTO_MODE via transition_mode()
            self._logger.warning(
                "gateway_max_retries",
                attempts=attempts,
            )

            preserve = get_preserve_keys("EVALUACION_GATEWAY", "PRESUPUESTO_MODE")
            updates = transition_mode(state, "PRESUPUESTO_MODE", preserve_keys=preserve)

            updates["ai_response"] = (
                "Entiendo que todavía no estás seguro. "
                "No hay problema, el presupuesto queda guardado. "
                "Cuando quieras iniciar el expediente, avisame."
            )

            return updates

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
