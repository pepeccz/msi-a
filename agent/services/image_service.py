"""
MSI Automotive — Image Service.

Business logic for queueing example images across the three delivery scopes:
- ``presupuesto``: images attached to a calculated tariff in mode_context
- ``elemento``: images for a single element (by code + category)
- ``documentacion_base``: example images for mandatory base documentation

This service is PURE — it performs DB lookups and returns plain dicts.
It does NOT modify ContextVars, set _pending_images, or talk to Chatwoot.
All side-effects live in the tool layer (``image_tools.py``).

Dependency rules:
- Services MUST NOT import from ``agent/tools/``.
- Import path for category lookup: ``agent.services.element_service``
  (``get_or_fetch_category_id`` lives there after the T2.2a move; while it
  is still being migrated the import is resolved at call time to avoid a
  circular-import during the transition window).
"""

from __future__ import annotations

import logging
from typing import Any, Literal

logger = logging.getLogger(__name__)


class ImageService:
    """
    Service that builds image payloads for the enviar_imagenes_ejemplo tool.

    All methods return a plain ``dict`` with at minimum::

        {
            "success": bool,
            "message": str,
            "images_to_queue": list[dict] | None,   # only when success=True
            "follow_up_message": str | None,        # pass-through / sanitised
        }
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def queue_example_images(
        self,
        *,
        tipo: Literal["presupuesto", "elemento", "documentacion_base"] | str,
        codigo_elemento: str | None,
        categoria: str | None,
        follow_up_message: str | None,
        state_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Determine which images should be queued based on *tipo*.

        Args:
            tipo: Delivery scope — ``presupuesto`` | ``elemento`` |
                  ``documentacion_base``.
            codigo_elemento: Required for ``tipo='elemento'``.
            categoria: Required for ``tipo='elemento'`` and
                       ``tipo='documentacion_base'``.
            follow_up_message: Optional text to send after the images.
            state_context: Current ConversationState dict (read-only).

        Returns:
            Result dict.  ``success=True`` includes ``images_to_queue``.
            ``success=False`` includes an error ``message`` for the LLM.
        """
        conversation_id = (
            state_context.get("conversation_id", "unknown")
            if state_context
            else "unknown"
        )

        logger.info(
            "[ImageService.queue_example_images] tipo=%s elemento=%s categoria=%s",
            tipo,
            codigo_elemento,
            categoria,
            extra={"conversation_id": conversation_id},
        )

        if tipo == "presupuesto":
            return await self._queue_presupuesto(
                state_context=state_context,
                follow_up_message=follow_up_message,
                conversation_id=conversation_id,
            )
        elif tipo == "elemento":
            return await self._queue_elemento(
                codigo_elemento=codigo_elemento,
                categoria=categoria,
                follow_up_message=follow_up_message,
                state_context=state_context,
                conversation_id=conversation_id,
            )
        elif tipo == "documentacion_base":
            return await self._queue_documentacion_base(
                categoria=categoria,
                follow_up_message=follow_up_message,
                state_context=state_context,
                conversation_id=conversation_id,
            )
        else:
            return self._error(
                f"Tipo '{tipo}' no valido. Usa 'presupuesto', 'elemento', o 'documentacion_base'."
            )

    # ------------------------------------------------------------------
    # tipo="presupuesto"
    # ------------------------------------------------------------------

    async def _queue_presupuesto(
        self,
        *,
        state_context: dict[str, Any],
        follow_up_message: str | None,
        conversation_id: str,
    ) -> dict[str, Any]:
        """Build the presupuesto image payload."""
        if not state_context:
            return self._error("Error interno: no hay estado disponible.")

        mode_context = state_context.get("mode_context", {})

        # Guard: already sent
        if mode_context.get("imagenes_enviadas"):
            logger.warning(
                "[ImageService] Images already sent for this quote | conv=%s",
                conversation_id,
            )
            return self._error(
                "Las imagenes de ejemplo ya fueron enviadas para este presupuesto. "
                "Si el usuario quiere abrir un expediente, usa iniciar_expediente(). "
                "NO vuelvas a enviar imagenes."
            )

        # Guard: wrong mode
        if state_context.get("current_mode") == "EXPEDIENTE_MODE":
            logger.warning(
                "[ImageService] blocked_in_expediente_mode | conv=%s", conversation_id
            )
            return self._error(
                "El precio ya fue comunicado durante el presupuesto y las imágenes de ejemplo "
                "ya fueron enviadas. Estás en EXPEDIENTE_MODE: usa iniciar_expediente() para "
                "crear el expediente de homologación, o tipo='elemento' con codigo_elemento "
                "para fotos de un elemento específico. No uses tipo='presupuesto' en esta fase."
            )

        # Guard: price not communicated
        if not mode_context.get("precio_comunicado"):
            logger.warning(
                "[ImageService] blocked_without_price_communication | conv=%s",
                conversation_id,
            )
            return self._error(
                "Aun no se ha comunicado el precio del presupuesto actual. "
                "Primero comunica el precio y luego envia imagenes de ejemplo."
            )

        # Guard: no tarifa_calculada
        tarifa_calculada = mode_context.get("tarifa_calculada")
        if not tarifa_calculada:
            logger.warning(
                "[ImageService] No tarifa_calculada in mode_context | conv=%s",
                conversation_id,
            )
            return self._error(
                "⚠️ CRITICAL INSTRUCTION FOR LLM ⚠️\n"
                "No hay presupuesto calculado todavia.\n\n"
                "DO NOT generate fake URLs or image links.\n"
                "DO NOT list URLs like 'storage.chatwoot.com/...' or any other invented links.\n\n"
                "Instead, tell the user:\n"
                "'Primero necesito calcular el presupuesto para poder mostrarte las fotos de ejemplo. "
                "¿Me confirmas los elementos que quieres homologar?'"
            )

        # Guard: stale budget scope
        current_codes_raw = mode_context.get("element_codes", [])
        tarifa_codes_raw = (tarifa_calculada.get("datos") or {}).get("element_codes") or []
        current_codes = {str(c).upper() for c in current_codes_raw if c}
        tarifa_codes = {str(c).upper() for c in tarifa_codes_raw if c}
        if current_codes and tarifa_codes and not tarifa_codes.issubset(current_codes):
            logger.warning(
                "[ImageService] blocked_stale_budget_scope | conv=%s current=%s tarifa=%s",
                conversation_id,
                sorted(current_codes),
                sorted(tarifa_codes),
            )
            return self._error(
                "Los elementos del presupuesto no coinciden con el estado actual de la conversacion. "
                "Esto puede ser un desajuste temporal. "
                "Reintenta esta llamada. Si el problema persiste, informa al usuario de un "
                "problema tecnico temporal y ofrece continuar con el expediente."
            )

        imagenes = tarifa_calculada.get("imagenes_ejemplo", [])
        if not imagenes:
            return self._error(
                "No hay imagenes de ejemplo disponibles para estos elementos. "
                "Informa al usuario de que no se dispone de fotos de ejemplo para esta combinacion "
                "y ofrece continuar con el expediente directamente."
            )

        # Filter active images only
        images_to_queue = [
            img for img in imagenes if img.get("status", "placeholder") == "active"
        ]
        if not images_to_queue:
            logger.info(
                "[ImageService] All %d images are placeholder/unavailable | conv=%s",
                len(imagenes),
                conversation_id,
            )
            return self._error(
                "⚠️ CRITICAL INSTRUCTION FOR LLM ⚠️\n"
                "No hay imagenes de ejemplo disponibles para esta homologacion "
                "(las imagenes aun no han sido configuradas por el administrador).\n\n"
                "DO NOT generate fake URLs or image links.\n"
                "DO NOT list URLs like 'storage.chatwoot.com/...' or any other invented links.\n\n"
                "Instead, tell the user:\n"
                "'En este momento no tengo fotos de ejemplo disponibles para esta homologación, "
                "pero puedo explicarte qué documentación necesitarás basándome en el presupuesto. "
                "¿Te parece?'\n\n"
                "Then describe the required documentation using ONLY the data from the 'documentacion' "
                "field in the calculated tariff. DO NOT invent documentation requirements."
            )

        logger.info(
            "[ImageService] Queuing %d active presupuesto images | conv=%s",
            len(images_to_queue),
            conversation_id,
        )
        return self._success(images_to_queue, follow_up_message)

    # ------------------------------------------------------------------
    # tipo="elemento"
    # ------------------------------------------------------------------

    async def _queue_elemento(
        self,
        *,
        codigo_elemento: str | None,
        categoria: str | None,
        follow_up_message: str | None,
        state_context: dict[str, Any],
        conversation_id: str,
    ) -> dict[str, Any]:
        """Build the elemento image payload."""
        if not codigo_elemento:
            return self._error(
                "Para tipo='elemento' debes especificar el codigo_elemento (ej: 'ESCAPE', 'SUBCHASIS')."
            )
        if not categoria:
            return self._error(
                "Para tipo='elemento' debes especificar la categoria (ej: 'motos-part', 'aseicars-prof')."
            )

        # Override categoria from state in EXPEDIENTE_MODE
        if state_context and state_context.get("current_mode") == "EXPEDIENTE_MODE":
            state_cat = state_context.get("mode_context", {}).get("categoria_slug")
            if state_cat and state_cat != categoria:
                logger.warning(
                    "[ImageService] imagen_categoria_override | llm=%s → state=%s | conv=%s",
                    categoria,
                    state_cat,
                    conversation_id,
                )
                categoria = state_cat

        # Intra-turn dedup is handled at the tool level (uses module-level set).
        # The service does not manage per-turn dedup state.

        # Resolve category ID
        from agent.services.element_service import get_or_fetch_category_id

        category_id = await get_or_fetch_category_id(categoria)
        if not category_id:
            logger.warning(
                "[ImageService] Category not found: %s | conv=%s",
                categoria,
                conversation_id,
            )
            return self._error(
                f"Categoria '{categoria}' no encontrada en el sistema."
            )

        # Get elements
        from agent.services.element_service import (
            get_element_service,
            normalize_element_code,
        )

        element_service = get_element_service()
        elements = await element_service.get_elements_by_category(
            category_id, is_active=True
        )
        element_by_code = {e["code"].upper(): e for e in elements}
        valid_codes_set = set(element_by_code.keys())

        # Normalize / auto-correct code
        matched_code, was_corrected = normalize_element_code(
            codigo_elemento, valid_codes_set
        )
        if matched_code and was_corrected:
            logger.info(
                "[ImageService] Auto-corrected code '%s' → '%s' | conv=%s",
                codigo_elemento,
                matched_code,
                conversation_id,
            )

        if not matched_code:
            available_codes = sorted(element_by_code.keys())
            valid_codes_list = available_codes[:20]
            truncated = len(available_codes) > 20
            codes_display = ", ".join(valid_codes_list)
            if truncated:
                codes_display += (
                    f" ... ({len(available_codes)} codigos en total, mostrando los primeros 20)"
                )
            return {
                "success": False,
                "message": (
                    f"Error: El codigo '{codigo_elemento}' no es un codigo valido en la categoria '{categoria}'. "
                    f"Los codigos validos son: [{codes_display}]. "
                    "DEBES usar uno de estos codigos EXACTOS. "
                    "NO escales a humano por este error, reintenta con un codigo de la lista anterior."
                ),
                "valid_codes": valid_codes_list,
                "images_to_queue": None,
                "follow_up_message": None,
            }

        element = element_by_code[matched_code]
        element_details = await element_service.get_element_with_images(element["id"])

        if not element_details:
            return self._error(
                f"No se pudo obtener informacion del elemento {codigo_elemento}."
            )

        if not element_details.get("images"):
            description = (
                element_details.get("description") or "Foto del elemento con matricula visible"
            )
            element_name = element_details.get("name", codigo_elemento)
            return self._error(
                f"⚠️ CRITICAL INSTRUCTION FOR LLM ⚠️\n"
                f"No hay imagenes de ejemplo disponibles para '{element_name}' "
                f"(las imagenes aun no han sido configuradas).\n\n"
                f"DO NOT generate fake URLs or image links.\n"
                f"DO NOT list URLs like 'storage.chatwoot.com/...' or any other invented links.\n\n"
                f"Instead, tell the user:\n"
                f"'En este momento no tengo fotos de ejemplo disponibles para {element_name}, "
                f"pero puedo explicarte qué documentación necesitarás: {description}. "
                f"¿Tienes alguna duda?'"
            )

        # Build image list (active only)
        images_to_queue = [
            {
                "url": img["image_url"],
                "tipo": img["image_type"],
                "elemento": element_details["name"],
                "descripcion": img.get("description") or img.get("title", ""),
                "instruccion_usuario": img.get("user_instruction", ""),
                "status": "active",
            }
            for img in element_details["images"]
            if img.get("status", "placeholder") == "active"
        ]

        if not images_to_queue:
            element_name = element_details.get("name", matched_code)
            return self._error(
                f"⚠️ CRITICAL INSTRUCTION FOR LLM ⚠️\n"
                f"No hay imagenes de ejemplo disponibles para '{element_name}' "
                f"(las imagenes aun no han sido configuradas).\n\n"
                f"DO NOT generate fake URLs or image links.\n"
                f"DO NOT list URLs like 'storage.chatwoot.com/...' or any other invented links.\n\n"
                f"Instead, tell the user:\n"
                f"'En este momento no tengo fotos de ejemplo disponibles para {element_name}, "
                f"pero puedo explicarte qué documentación necesitarás. ¿Te parece?'"
            )

        logger.info(
            "[ImageService] Queuing %d active elemento images for %s | conv=%s",
            len(images_to_queue),
            matched_code,
            conversation_id,
        )
        return self._success(images_to_queue, follow_up_message)

    # ------------------------------------------------------------------
    # tipo="documentacion_base"
    # ------------------------------------------------------------------

    async def _queue_documentacion_base(
        self,
        *,
        categoria: str | None,
        follow_up_message: str | None,
        state_context: dict[str, Any],
        conversation_id: str,
    ) -> dict[str, Any]:
        """Build the documentacion_base image payload."""
        if not categoria:
            return self._error(
                "Para tipo='documentacion_base' debes especificar la categoria "
                "(ej: 'motos-part', 'aseicars-prof')."
            )

        # Guard: only valid in COLLECT_BASE_DOCS phase
        from agent.utils.expediente_types import CollectionStep

        if state_context:
            _mc = state_context.get("mode_context", {})
            _step_val = _mc.get("expediente_sub_mode", CollectionStep.IDLE.value)
            try:
                current_step = CollectionStep(_step_val)
            except ValueError:
                current_step = CollectionStep.IDLE

            if current_step != CollectionStep.COLLECT_BASE_DOCS:
                logger.warning(
                    "[ImageService] tipo='documentacion_base' called from wrong phase '%s' | conv=%s",
                    current_step.value,
                    conversation_id,
                )
                return {
                    "success": False,
                    "message": (
                        "No puedes enviar imágenes de documentación base fuera de la fase de recolección."
                    ),
                    "guidance": (
                        f"Estás en '{current_step.value}'. "
                        "Solo puedes enviar documentación base durante COLLECT_BASE_DOCS."
                    ),
                    "images_to_queue": None,
                    "follow_up_message": None,
                }

        # Sanitize follow_up_message: expediente is already open in this phase
        if follow_up_message and "expediente" in follow_up_message.lower():
            logger.warning(
                "[ImageService] Blocking inappropriate follow_up_message in COLLECT_BASE_DOCS | conv=%s",
                conversation_id,
            )
            follow_up_message = None

        from agent.services.tarifa_service import get_tarifa_service

        tarifa_service = get_tarifa_service()
        category_data = await tarifa_service.get_category_data(categoria)

        if not category_data:
            return self._error(
                f"Categoria '{categoria}' no encontrada en el sistema."
            )

        base_documentation = category_data.get("base_documentation", [])
        if not base_documentation:
            return self._error(
                f"No hay documentacion base definida para la categoria '{categoria}'. "
                "Pide al usuario que envie la ficha tecnica y el permiso de circulacion."
            )

        images_to_queue: list[dict[str, Any]] = []
        docs_without_images: list[str] = []

        for base_doc in base_documentation:
            if base_doc.get("image_url"):
                images_to_queue.append(
                    {
                        "url": base_doc["image_url"],
                        "tipo": "base",
                        "descripcion": base_doc["description"],
                        "status": "active",
                    }
                )
            else:
                docs_without_images.append(base_doc["description"])

        if not images_to_queue:
            docs_list = "\n".join(f"- {doc['description']}" for doc in base_documentation)
            return self._error(
                f"No hay imagenes de ejemplo disponibles para la documentacion base, "
                f"pero estos son los documentos requeridos:\n\n{docs_list}\n\n"
                "Pide al usuario que envie fotos o PDFs de estos documentos."
            )

        # Append text about docs that have no images to the follow_up
        if docs_without_images and not follow_up_message:
            docs_list = "\n".join(f"- {doc}" for doc in docs_without_images)
            follow_up_message = f"Tambien necesitaras enviar:\n{docs_list}"

        logger.info(
            "[ImageService] Queuing %d base_documentation images for %s | conv=%s",
            len(images_to_queue),
            categoria,
            conversation_id,
        )
        return self._success(images_to_queue, follow_up_message)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _error(message: str, **extra: Any) -> dict[str, Any]:
        return {
            "success": False,
            "message": message,
            "images_to_queue": None,
            "follow_up_message": None,
            **extra,
        }

    @staticmethod
    def _success(
        images_to_queue: list[dict[str, Any]],
        follow_up_message: str | None,
    ) -> dict[str, Any]:
        return {
            "success": True,
            "message": "",
            "images_to_queue": images_to_queue,
            "follow_up_message": follow_up_message,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_image_service: ImageService | None = None


def get_image_service() -> ImageService:
    """Get or create the ImageService singleton."""
    global _image_service
    if _image_service is None:
        _image_service = ImageService()
    return _image_service
