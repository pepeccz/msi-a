"""
MSI Automotive - Image Tools for Agent.

Tools for sending example images to users during conversations.
"""

import logging
from contextvars import ContextVar
from typing import Any, Literal

from langchain_core.tools import tool

from agent.services.element_service import get_element_service
from agent.tools.element_tools import get_or_fetch_category_id
from agent.utils.errors import ErrorCategory, handle_tool_errors
from agent.utils.tool_helpers import tool_error_response

logger = logging.getLogger(__name__)

# Fix #6: Use ContextVar instead of global mutable state for async safety.
# Global variables are shared across all concurrent coroutines, which means
# two parallel tool executions could overwrite each other's state.
# ContextVar is isolated per async task, preventing race conditions.
_current_state: ContextVar[dict[str, Any] | None] = ContextVar(
    "image_tools_current_state", default=None
)
_pending_images_result: ContextVar[dict[str, Any] | None] = ContextVar(
    "image_tools_pending_result", default=None
)


def set_current_state_for_image_tools(state: dict[str, Any]) -> None:
    """Set the current state for image tools to access."""
    _current_state.set(state)


def get_pending_images_result() -> dict[str, Any] | None:
    """Get the pending images result after tool execution."""
    result = _pending_images_result.get()
    _pending_images_result.set(None)  # Clear after reading
    return result


def set_pending_images_result(result: dict[str, Any]) -> None:
    """
    Set the pending images result to be sent after tool execution.
    
    Used by tools that need to queue images for sending (e.g., reenviar_imagenes_elemento).
    
    Args:
        result: Dict containing 'images' list and optional 'follow_up_message'
    """
    _pending_images_result.set(result)


def clear_image_tools_state() -> None:
    """Clear the image tools state after processing."""
    _current_state.set(None)
    _pending_images_result.set(None)


@tool
@handle_tool_errors(
    error_category=ErrorCategory.DATABASE_ERROR,
    error_code="IMAGE_SEND_FAILED",
    user_message="Lo siento, hubo un problema al preparar las imágenes. ¿Puedes intentarlo de nuevo?",
)
async def enviar_imagenes_ejemplo(
    tipo: Literal["presupuesto", "elemento", "documentacion_base"] = "presupuesto",
    codigo_elemento: str | None = None,
    categoria: str | None = None,
    follow_up_message: str | None = None,
) -> dict[str, Any]:
    """
    Encola imagenes de ejemplo para enviar al usuario.
    
    CUANDO USAR:
    - tipo="presupuesto": Despues de calcular_tarifa_con_elementos, para enviar TODAS 
      las imagenes del presupuesto (base + elementos).
    - tipo="elemento": Cuando el usuario pregunta especificamente por un elemento
      (ej: "como debe ser la foto del escape?")
    - tipo="documentacion_base": Durante COLLECT_BASE_DOCS, para enviar imagenes de ejemplo
      de la documentacion obligatoria (ficha tecnica, permiso, etc.)
    
    PARAMETROS:
    - tipo: "presupuesto" (todas del presupuesto), "elemento" (especificas), o "documentacion_base"
    - codigo_elemento: Requerido si tipo="elemento" (ej: "ESCAPE", "SUBCHASIS")
    - categoria: Requerido si tipo="elemento" o tipo="documentacion_base" (ej: "motos-part", "aseicars-prof")
    - follow_up_message: Mensaje a enviar DESPUES de las imagenes.
      Util para preguntar si quiere abrir expediente despues de mostrar las fotos.
    
    FLUJO DE ENVIO:
    1. Tu mensaje de texto se envia primero
    2. Luego se envian las imagenes (una por una)
    3. Por ultimo se envia el follow_up_message (si lo especificaste)
    
    EJEMPLO PRESUPUESTO:
    Despues de calcular tarifa, llama:
    enviar_imagenes_ejemplo(
        tipo="presupuesto",
        follow_up_message="Te gustaria que te abriera un expediente para gestionar tu homologacion?"
    )
    
    EJEMPLO ELEMENTO ESPECIFICO:
    Si usuario pregunta por fotos del escape:
    enviar_imagenes_ejemplo(
        tipo="elemento",
        codigo_elemento="ESCAPE",
        categoria="motos-part"
    )
    
    EJEMPLO DOCUMENTACION BASE:
    Durante COLLECT_BASE_DOCS, si usuario pide ejemplos:
    enviar_imagenes_ejemplo(
        tipo="documentacion_base",
        categoria="motos-part"
    )
    
    Returns:
        Confirmacion con numero de imagenes encoladas, o mensaje de error/info
    """
    # Get state from ContextVar (async-safe, no globals)
    state = _current_state.get()
    
    conversation_id = state.get("conversation_id", "unknown") if state else "unknown"
    
    logger.info(
        f"[enviar_imagenes_ejemplo] Called | tipo={tipo} | elemento={codigo_elemento} | "
        f"categoria={categoria} | has_follow_up={bool(follow_up_message)}",
        extra={"conversation_id": conversation_id}
    )
    
    # PROTECTION: Check if images were already sent for current quote
    if tipo == "presupuesto" and state:
        if state.get("images_sent_for_current_quote"):
            logger.warning(
                f"[enviar_imagenes_ejemplo] Images already sent for this quote, blocking duplicate | "
                f"conversation_id={conversation_id}",
                extra={"conversation_id": conversation_id}
            )
            return {
                "success": False,
                "message": (
                    "Las imagenes de ejemplo ya fueron enviadas para este presupuesto. "
                    "Si el usuario quiere abrir un expediente, usa iniciar_expediente(). "
                    "NO vuelvas a enviar imagenes."
                ),
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }
    
    images_to_queue: list[dict[str, Any]] = []
    
    if tipo == "presupuesto":
        # Get images from last calculated tarifa
        if not state:
            logger.warning("[enviar_imagenes_ejemplo] No state available")
            return {
                "success": False,
                "message": "Error interno: no hay estado disponible.",
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }
        
        tarifa_actual = state.get("tarifa_actual")
        if not tarifa_actual:
            logger.warning(
                f"[enviar_imagenes_ejemplo] No tarifa_actual in state",
                extra={"conversation_id": conversation_id}
            )
            return {
                "success": False,
                "message": (
                    "No hay presupuesto calculado todavia. "
                    "Primero usa calcular_tarifa_con_elementos para obtener un presupuesto."
                ),
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }
        
        # VALIDACIÓN CRÍTICA: Verificar que precio fue comunicado al usuario
        price_communicated = state.get("price_communicated_to_user", False)
        if not price_communicated:
            price = tarifa_actual.get("datos", {}).get("price", "N/A")
            logger.warning(
                f"[enviar_imagenes_ejemplo] Attempt to send images without communicating price first",
                extra={
                    "conversation_id": conversation_id,
                    "price": price,
                    "price_communicated": price_communicated
                }
            )
            return {
                "success": False,
                "error": "PRICE_NOT_COMMUNICATED",
                "message": (
                    "DEBES mencionar el precio en tu mensaje ANTES de enviar imágenes.\n\n"
                    "Flujo correcto:\n"
                    "1. Tu mensaje: 'El presupuesto es de {price} EUR +IVA...'\n"
                    "2. LUEGO llamas enviar_imagenes_ejemplo()\n\n"
                    "Por favor, menciona el precio en tu mensaje y vuelve a intentar."
                ).format(price=price),
                "price": price,
                "suggestion": f"Di: 'El presupuesto es de {price} EUR +IVA...' y luego envía imágenes.",
                "tool_name": "enviar_imagenes_ejemplo",
            }
        
        imagenes = tarifa_actual.get("imagenes_ejemplo", [])
        if not imagenes:
            logger.info(
                f"[enviar_imagenes_ejemplo] Tarifa has no example images (likely already sent)",
                extra={"conversation_id": conversation_id}
            )
            return {
                "success": False,
                "message": (
                    "Las imagenes de ejemplo ya fueron enviadas anteriormente en esta conversacion. "
                    "NO las envies de nuevo - el usuario ya las vio arriba en el chat. "
                    "Si el usuario acepto abrir expediente, usa iniciar_expediente(). "
                    "Si el usuario pregunta por las fotos, dile que las revise en los mensajes anteriores."
                ),
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }
        
        # Filter: only queue images with status "active" (not placeholder/unavailable)
        images_to_queue = [
            img for img in imagenes
            if img.get("status", "placeholder") == "active"
        ]
        if not images_to_queue:
            logger.info(
                f"[enviar_imagenes_ejemplo] All {len(imagenes)} images are placeholder/unavailable",
                extra={"conversation_id": conversation_id}
            )
            return {
                "success": False,
                "message": (
                    "No hay imagenes de ejemplo disponibles para este presupuesto "
                    "(las imagenes aun no han sido configuradas por el administrador). "
                    "Informa al usuario que las fotos de ejemplo no estan disponibles en este momento, "
                    "pero describele la documentacion necesaria basandote UNICAMENTE en los datos "
                    "del presupuesto calculado (campo 'documentacion'). "
                    "NO inventes requisitos de documentacion."
                ),
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }
        logger.info(
            f"[enviar_imagenes_ejemplo] Queuing {len(images_to_queue)} active images from tarifa "
            f"(filtered from {len(imagenes)} total)",
            extra={"conversation_id": conversation_id}
        )
        
    elif tipo == "elemento":
        if not codigo_elemento:
            return {
                "success": False,
                "message": "Para tipo='elemento' debes especificar el codigo_elemento (ej: 'ESCAPE', 'SUBCHASIS').",
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }
        
        if not categoria:
            return {
                "success": False,
                "message": "Para tipo='elemento' debes especificar la categoria (ej: 'motos-part', 'aseicars-prof').",
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }
        
        # Initialize code_upper early for consistent logging (prevents UnboundLocalError)
        code_upper = codigo_elemento.upper()
        
        # Get element service and find element
        element_service = get_element_service()
        category_id = await get_or_fetch_category_id(categoria)
        
        if not category_id:
            logger.warning(
                f"[enviar_imagenes_ejemplo] Category not found: {categoria}",
                extra={"conversation_id": conversation_id}
            )
            return {
                "success": False,
                "message": f"Categoria '{categoria}' no encontrada en el sistema.",
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }
        
        # Get all elements to find by code
        elements = await element_service.get_elements_by_category(category_id, is_active=True)
        element_by_code = {e["code"].upper(): e for e in elements}
        
        # Use fuzzy matching to auto-correct common LLM errors (ASIDERO → ASIDEROS)
        from agent.tools.element_tools import normalize_element_code
        valid_codes_set = set(element_by_code.keys())
        matched_code, was_corrected = normalize_element_code(codigo_elemento, valid_codes_set)
        
        if matched_code and was_corrected:
            logger.info(
                f"[enviar_imagenes_ejemplo] Auto-corrected element code: '{codigo_elemento}' → '{matched_code}'",
                extra={"conversation_id": conversation_id, "original": codigo_elemento, "corrected": matched_code}
            )
            # Update code_upper to the corrected code for consistent logging
            code_upper = matched_code
        
        if not matched_code:
            logger.warning(
                f"[enviar_imagenes_ejemplo] Element not found: {codigo_elemento} in {categoria}",
                extra={"conversation_id": conversation_id}
            )
            # Suggest similar codes to help LLM self-correct
            available_codes = sorted(element_by_code.keys())
            similar = [c for c in available_codes if any(
                part in c or c in part
                for part in code_upper.replace("_", " ").split()
            )]
            suggestion = f" Codigos similares: {', '.join(similar[:5])}." if similar else ""
            return {
                "success": False,
                "message": (
                    f"Error: El codigo '{codigo_elemento}' no existe en la categoria '{categoria}'.{suggestion} "
                    "Si ya calculaste una tarifa, usa tipo='presupuesto' para enviar las imagenes del presupuesto actual. "
                    "NO escales a humano por este error, reintenta con el codigo correcto."
                ),
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }
        
        element = element_by_code[matched_code]
        # code_upper already set (either original or corrected)
        element_details = await element_service.get_element_with_images(element["id"])
        
        if not element_details:
            logger.warning(
                f"[enviar_imagenes_ejemplo] Could not get element details for {code_upper}",
                extra={"conversation_id": conversation_id}
            )
            return {
                "success": False,
                "message": f"No se pudo obtener informacion del elemento {codigo_elemento}.",
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }
        
        if not element_details.get("images"):
            # No images but element exists - return text info
            description = element_details.get("description") or "Foto del elemento con matricula visible"
            logger.info(
                f"[enviar_imagenes_ejemplo] Element {code_upper} has no images, returning text info",
                extra={"conversation_id": conversation_id}
            )
            return {
                "success": False,
                "message": (
                    f"No tenemos imagenes de ejemplo para '{element_details['name']}'. "
                    f"La documentacion requerida es: {description}"
                ),
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }
        
        # Build images list from element (only active status)
        for img in element_details["images"]:
            if img.get("status", "placeholder") == "active":
                images_to_queue.append({
                    "url": img["image_url"],
                    "tipo": img["image_type"],
                    "elemento": element_details["name"],
                    "descripcion": img.get("description") or img.get("title", ""),
                    "status": "active",
                })

        if not images_to_queue:
            logger.info(
                f"[enviar_imagenes_ejemplo] Element {code_upper} has no active images",
                extra={"conversation_id": conversation_id}
            )
            return {
                "success": False,
                "message": (
                    f"No hay imagenes de ejemplo disponibles para '{element_details['name']}' "
                    "(las imagenes aun no han sido configuradas). "
                    "Informa al usuario que las fotos de ejemplo no estan disponibles en este momento."
                ),
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }

        logger.info(
            f"[enviar_imagenes_ejemplo] Queuing {len(images_to_queue)} active images for element {code_upper}",
            extra={"conversation_id": conversation_id}
        )
    
    elif tipo == "documentacion_base":
        if not categoria:
            return {
                "success": False,
                "message": "Para tipo='documentacion_base' debes especificar la categoria (ej: 'motos-part', 'aseicars-prof').",
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }
        
        # Get base documentation for the category
        from agent.services.tarifa_service import get_tarifa_service
        tarifa_service = get_tarifa_service()
        category_data = await tarifa_service.get_category_data(categoria)
        
        if not category_data:
            logger.warning(
                f"[enviar_imagenes_ejemplo] Category not found: {categoria}",
                extra={"conversation_id": conversation_id}
            )
            return {
                "success": False,
                "message": f"Categoria '{categoria}' no encontrada en el sistema.",
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }
        
        base_documentation = category_data.get("base_documentation", [])
        if not base_documentation:
            logger.info(
                f"[enviar_imagenes_ejemplo] No base documentation defined for category {categoria}",
                extra={"conversation_id": conversation_id}
            )
            return {
                "success": False,
                "message": (
                    f"No hay documentacion base definida para la categoria '{categoria}'. "
                    "Pide al usuario que envie la ficha tecnica y el permiso de circulacion."
                ),
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }
        
        # Build images list from base documentation (only those with image_url)
        docs_with_images = []
        docs_without_images = []
        
        for base_doc in base_documentation:
            if base_doc.get("image_url"):
                images_to_queue.append({
                    "url": base_doc["image_url"],
                    "tipo": "base",
                    "descripcion": base_doc["description"],
                    "status": "active",
                })
                docs_with_images.append(base_doc["description"])
            else:
                docs_without_images.append(base_doc["description"])
        
        if not images_to_queue:
            # No images configured, return text description of required docs
            logger.info(
                f"[enviar_imagenes_ejemplo] No images configured for base docs in {categoria}",
                extra={"conversation_id": conversation_id}
            )
            docs_list = "\n".join(f"- {doc['description']}" for doc in base_documentation)
            return {
                "success": False,
                "message": (
                    f"No hay imagenes de ejemplo disponibles para la documentacion base, "
                    f"pero estos son los documentos requeridos:\n\n{docs_list}\n\n"
                    "Pide al usuario que envie fotos o PDFs de estos documentos."
                ),
                "data": None,
                "tool_name": "enviar_imagenes_ejemplo",
            }
        
        logger.info(
            f"[enviar_imagenes_ejemplo] Queuing {len(images_to_queue)} base documentation images for {categoria}",
            extra={"conversation_id": conversation_id, "category": categoria}
        )
        
        # If some docs don't have images, add note to follow-up message
        if docs_without_images and not follow_up_message:
            docs_list = "\n".join(f"- {doc}" for doc in docs_without_images)
            follow_up_message = (
                f"Tambien necesitaras enviar:\n{docs_list}"
            )
    
    else:
        return {
            "success": False,
            "message": f"Tipo '{tipo}' no valido. Usa 'presupuesto', 'elemento', o 'documentacion_base'.",
            "data": None,
            "tool_name": "enviar_imagenes_ejemplo",
        }
    
    # Build pending images payload
    pending_payload: dict[str, Any] = {
        "images": images_to_queue,
    }
    
    if follow_up_message:
        pending_payload["follow_up_message"] = follow_up_message
        logger.info(
            f"[enviar_imagenes_ejemplo] Including follow_up message",
            extra={"conversation_id": conversation_id}
        )
    
    # Return confirmation
    # NOTE: Images are returned in _pending_images instead of using ContextVar.
    # LangChain's ainvoke() runs tools in a copied context (copy_context() + create_task),
    # so ContextVar.set() inside the tool is invisible to the caller node.
    message = (
        f"OK: {len(images_to_queue)} imagenes encoladas para envio."
        if not follow_up_message
        else f"OK: {len(images_to_queue)} imagenes encoladas. Despues de las imagenes se enviara el mensaje de seguimiento."
    )

    return {
        "success": True,
        "message": message,
        "data": {
            "images_count": len(images_to_queue),
            "has_follow_up": bool(follow_up_message),
        },
        "tool_name": "enviar_imagenes_ejemplo",
        "_pending_images": pending_payload,
    }


# List of all image tools
IMAGE_TOOLS = [enviar_imagenes_ejemplo]


def get_image_tools() -> list:
    """Get all image-related tools."""
    return IMAGE_TOOLS


__all__ = [
    "enviar_imagenes_ejemplo",
    "get_image_tools",
    "IMAGE_TOOLS",
    "set_current_state_for_image_tools",
    "get_pending_images_result",
    "set_pending_images_result",
    "clear_image_tools_state",
]
