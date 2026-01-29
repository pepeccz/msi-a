"""
MSI Automotive - Image Tools for Agent.

Tools for sending example images to users during conversations.
"""

import logging
from typing import Any, Literal

from langchain_core.tools import tool

from agent.services.element_service import get_element_service
from agent.tools.element_tools import get_or_fetch_category_id

logger = logging.getLogger(__name__)

# Global variable to store state reference (set by conversational_agent before tool execution)
_current_state: dict[str, Any] | None = None
_pending_images_result: dict[str, Any] | None = None


def set_current_state_for_image_tools(state: dict[str, Any]) -> None:
    """Set the current state for image tools to access."""
    global _current_state
    _current_state = state


def get_pending_images_result() -> dict[str, Any] | None:
    """Get the pending images result after tool execution."""
    global _pending_images_result
    result = _pending_images_result
    _pending_images_result = None  # Clear after reading
    return result


def set_pending_images_result(result: dict[str, Any]) -> None:
    """
    Set the pending images result to be sent after tool execution.
    
    Used by tools that need to queue images for sending (e.g., reenviar_imagenes_elemento).
    
    Args:
        result: Dict containing 'images' list and optional 'follow_up_message'
    """
    global _pending_images_result
    _pending_images_result = result


def clear_image_tools_state() -> None:
    """Clear the image tools state after processing."""
    global _current_state, _pending_images_result
    _current_state = None
    _pending_images_result = None


@tool
async def enviar_imagenes_ejemplo(
    tipo: Literal["presupuesto", "elemento"] = "presupuesto",
    codigo_elemento: str | None = None,
    categoria: str | None = None,
    follow_up_message: str | None = None,
) -> str:
    """
    Encola imagenes de ejemplo para enviar al usuario.
    
    CUANDO USAR:
    - tipo="presupuesto": Despues de calcular_tarifa_con_elementos, para enviar TODAS 
      las imagenes del presupuesto (base + elementos).
    - tipo="elemento": Cuando el usuario pregunta especificamente por un elemento
      (ej: "como debe ser la foto del escape?")
    
    PARAMETROS:
    - tipo: "presupuesto" (todas las del presupuesto) o "elemento" (especificas)
    - codigo_elemento: Requerido si tipo="elemento" (ej: "ESCAPE", "SUBCHASIS")
    - categoria: Requerido si tipo="elemento" (ej: "motos-part", "aseicars-prof")
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
    
    Returns:
        Confirmacion con numero de imagenes encoladas, o mensaje de error/info
    """
    global _current_state, _pending_images_result
    
    conversation_id = _current_state.get("conversation_id", "unknown") if _current_state else "unknown"
    
    logger.info(
        f"[enviar_imagenes_ejemplo] Called | tipo={tipo} | elemento={codigo_elemento} | "
        f"categoria={categoria} | has_follow_up={bool(follow_up_message)}",
        extra={"conversation_id": conversation_id}
    )
    
    # PROTECTION: Check if images were already sent for current quote
    if tipo == "presupuesto" and _current_state:
        if _current_state.get("images_sent_for_current_quote"):
            logger.warning(
                f"[enviar_imagenes_ejemplo] Images already sent for this quote, blocking duplicate | "
                f"conversation_id={conversation_id}",
                extra={"conversation_id": conversation_id}
            )
            return (
                "Las imagenes de ejemplo ya fueron enviadas para este presupuesto. "
                "Si el usuario quiere abrir un expediente, usa iniciar_expediente(). "
                "NO vuelvas a enviar imagenes."
            )
    
    images_to_queue: list[dict[str, Any]] = []
    
    if tipo == "presupuesto":
        # Get images from last calculated tarifa
        if not _current_state:
            logger.warning("[enviar_imagenes_ejemplo] No state available")
            return "Error interno: no hay estado disponible."
        
        tarifa_actual = _current_state.get("tarifa_actual")
        if not tarifa_actual:
            logger.warning(
                f"[enviar_imagenes_ejemplo] No tarifa_actual in state",
                extra={"conversation_id": conversation_id}
            )
            return (
                "No hay presupuesto calculado todavia. "
                "Primero usa calcular_tarifa_con_elementos para obtener un presupuesto."
            )
        
        imagenes = tarifa_actual.get("imagenes_ejemplo", [])
        if not imagenes:
            logger.info(
                f"[enviar_imagenes_ejemplo] Tarifa has no example images (likely already sent)",
                extra={"conversation_id": conversation_id}
            )
            return (
                "Las imagenes de ejemplo ya fueron enviadas anteriormente en esta conversacion. "
                "NO las envies de nuevo - el usuario ya las vio arriba en el chat. "
                "Si el usuario acepto abrir expediente, usa iniciar_expediente(). "
                "Si el usuario pregunta por las fotos, dile que las revise en los mensajes anteriores."
            )
        
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
            return (
                "No hay imagenes de ejemplo disponibles para este presupuesto "
                "(las imagenes aun no han sido configuradas por el administrador). "
                "Informa al usuario que las fotos de ejemplo no estan disponibles en este momento, "
                "pero describele la documentacion necesaria basandote UNICAMENTE en los datos "
                "del presupuesto calculado (campo 'documentacion'). "
                "NO inventes requisitos de documentacion."
            )
        logger.info(
            f"[enviar_imagenes_ejemplo] Queuing {len(images_to_queue)} active images from tarifa "
            f"(filtered from {len(imagenes)} total)",
            extra={"conversation_id": conversation_id}
        )
        
    elif tipo == "elemento":
        if not codigo_elemento:
            return "Para tipo='elemento' debes especificar el codigo_elemento (ej: 'ESCAPE', 'SUBCHASIS')."
        
        if not categoria:
            return "Para tipo='elemento' debes especificar la categoria (ej: 'motos-part', 'aseicars-prof')."
        
        # Get element service and find element
        element_service = get_element_service()
        category_id = await get_or_fetch_category_id(categoria)
        
        if not category_id:
            logger.warning(
                f"[enviar_imagenes_ejemplo] Category not found: {categoria}",
                extra={"conversation_id": conversation_id}
            )
            return f"Categoria '{categoria}' no encontrada en el sistema."
        
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
        
        if not matched_code:
            logger.warning(
                f"[enviar_imagenes_ejemplo] Element not found: {codigo_elemento} in {categoria}",
                extra={"conversation_id": conversation_id}
            )
            # Suggest similar codes to help LLM self-correct
            available_codes = sorted(element_by_code.keys())
            code_upper = codigo_elemento.upper()
            similar = [c for c in available_codes if any(
                part in c or c in part
                for part in code_upper.replace("_", " ").split()
            )]
            suggestion = f" Codigos similares: {', '.join(similar[:5])}." if similar else ""
            return (
                f"Error: El codigo '{codigo_elemento}' no existe en la categoria '{categoria}'.{suggestion} "
                "Si ya calculaste una tarifa, usa tipo='presupuesto' para enviar las imagenes del presupuesto actual. "
                "NO escales a humano por este error, reintenta con el codigo correcto."
            )
        
        element = element_by_code[matched_code]
        element_details = await element_service.get_element_with_images(element["id"])
        
        if not element_details:
            logger.warning(
                f"[enviar_imagenes_ejemplo] Could not get element details for {code_upper}",
                extra={"conversation_id": conversation_id}
            )
            return f"No se pudo obtener informacion del elemento {codigo_elemento}."
        
        if not element_details.get("images"):
            # No images but element exists - return text info
            description = element_details.get("description") or "Foto del elemento con matricula visible"
            logger.info(
                f"[enviar_imagenes_ejemplo] Element {code_upper} has no images, returning text info",
                extra={"conversation_id": conversation_id}
            )
            return (
                f"No tenemos imagenes de ejemplo para '{element_details['name']}'. "
                f"La documentacion requerida es: {description}"
            )
        
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
            return (
                f"No hay imagenes de ejemplo disponibles para '{element_details['name']}' "
                "(las imagenes aun no han sido configuradas). "
                "Informa al usuario que las fotos de ejemplo no estan disponibles en este momento."
            )

        logger.info(
            f"[enviar_imagenes_ejemplo] Queuing {len(images_to_queue)} active images for element {code_upper}",
            extra={"conversation_id": conversation_id}
        )
    
    else:
        return f"Tipo '{tipo}' no valido. Usa 'presupuesto' o 'elemento'."
    
    # Build pending images payload
    _pending_images_result = {
        "images": images_to_queue,
    }
    
    if follow_up_message:
        _pending_images_result["follow_up_message"] = follow_up_message
        logger.info(
            f"[enviar_imagenes_ejemplo] Including follow_up message",
            extra={"conversation_id": conversation_id}
        )
    
    # Return confirmation
    if follow_up_message:
        return f"OK: {len(images_to_queue)} imagenes encoladas. Despues de las imagenes se enviara el mensaje de seguimiento."
    else:
        return f"OK: {len(images_to_queue)} imagenes encoladas para envio."


# List of all image tools
IMAGE_TOOLS = [enviar_imagenes_ejemplo]


def get_image_tools() -> list:
    """Get all image-related tools."""
    return IMAGE_TOOLS
