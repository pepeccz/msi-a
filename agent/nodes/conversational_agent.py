"""
MSI Automotive - Conversational agent node.

This node handles generating AI responses using OpenRouter LLM with tool support.
"""

import json
import logging
from datetime import datetime, UTC
from typing import Any

from langchain_openai import ChatOpenAI

from agent.graphs.conversation_flow import SYSTEM_PROMPT
from agent.state.helpers import (
    add_message,
    format_messages_for_llm,
    set_current_state,
    clear_current_state,
)
from agent.state.schemas import ConversationState
from agent.tools import get_all_tools
from shared.config import get_settings

logger = logging.getLogger(__name__)

# Maximum tool call iterations to prevent infinite loops
MAX_TOOL_ITERATIONS = 5


def get_llm(with_tools: bool = True) -> ChatOpenAI:
    """
    Get configured LLM instance.

    Args:
        with_tools: Whether to bind tools to the LLM

    Returns:
        Configured ChatOpenAI instance
    """
    settings = get_settings()

    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        openai_api_key=settings.OPENROUTER_API_KEY,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.7,
        max_tokens=1500,
        default_headers={
            "HTTP-Referer": settings.SITE_URL,
            "X-Title": settings.SITE_NAME,
        },
    )

    if with_tools:
        tools = get_all_tools()
        llm = llm.bind_tools(tools)

    return llm


async def execute_tool_call(
    tool_call: dict,
    state: ConversationState | None = None,
) -> dict[str, Any]:
    """
    Execute a tool call and return the result.

    Args:
        tool_call: Tool call dict with name and args
        state: Current conversation state (needed for tools like escalar_a_humano)

    Returns:
        Dict with tool result (may include images for documentation, or
        escalation_triggered flag for escalation tools)
    """
    from agent.tools import (
        # General tools
        listar_categorias,
        listar_tarifas,
        obtener_servicios_adicionales,
        escalar_a_humano,
        # Element tools
        listar_elementos,
        identificar_elementos,
        validar_elementos,
        calcular_tarifa_con_elementos,
        obtener_documentacion_elemento,
        # Case tools
        iniciar_expediente,
        actualizar_datos_expediente,
        actualizar_datos_taller,
        procesar_imagen_expediente,
        continuar_a_datos_personales,
        finalizar_expediente,
        cancelar_expediente,
        obtener_estado_expediente,
        # Vehicle tools
        identificar_tipo_vehiculo,
    )

    tool_name = tool_call.get("name")
    tool_args = tool_call.get("args", {})

    logger.info(f"Executing tool: {tool_name} with args: {tool_args}")

    tool_map = {
        # General tools
        "listar_categorias": listar_categorias,
        "listar_tarifas": listar_tarifas,
        "obtener_servicios_adicionales": obtener_servicios_adicionales,
        "escalar_a_humano": escalar_a_humano,
        # Element tools
        "listar_elementos": listar_elementos,
        "identificar_elementos": identificar_elementos,
        "validar_elementos": validar_elementos,
        "calcular_tarifa_con_elementos": calcular_tarifa_con_elementos,
        "obtener_documentacion_elemento": obtener_documentacion_elemento,
        # Case tools
        "iniciar_expediente": iniciar_expediente,
        "actualizar_datos_expediente": actualizar_datos_expediente,
        "actualizar_datos_taller": actualizar_datos_taller,
        "procesar_imagen_expediente": procesar_imagen_expediente,
        "continuar_a_datos_personales": continuar_a_datos_personales,
        "finalizar_expediente": finalizar_expediente,
        "cancelar_expediente": cancelar_expediente,
        "obtener_estado_expediente": obtener_estado_expediente,
        # Vehicle tools
        "identificar_tipo_vehiculo": identificar_tipo_vehiculo,
    }

    tool_func = tool_map.get(tool_name)
    if not tool_func:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        # Set current state in context so tools can access conversation_id, etc.
        if state:
            set_current_state(dict(state))

        result = await tool_func.ainvoke(tool_args)

        # obtener_documentacion returns a dict with "texto" and "imagenes"
        # escalar_a_humano returns a dict with "result" and "escalation_triggered"
        if isinstance(result, dict):
            return result
        else:
            return {"result": result}

    except Exception as e:
        logger.error(f"Tool execution error: {e}", exc_info=True)
        return {"error": str(e)}
    finally:
        # Always clear state after tool execution
        clear_current_state()


async def conversational_agent_node(state: ConversationState) -> dict[str, Any]:
    """
    Generate AI response using LLM with tool support.

    This node:
    1. Prepares conversation context
    2. Calls the LLM via OpenRouter
    3. Processes any tool calls
    4. Returns final response with optional images

    Args:
        state: Current conversation state

    Returns:
        State updates dict with AI response and optional images
    """
    conversation_id = state.get("conversation_id", "unknown")
    messages = state.get("messages", [])
    is_first = state.get("is_first_interaction", False)
    user_name = state.get("user_name")
    client_type = state.get("client_type", "particular")
    error_count = state.get("error_count", 0)

    logger.info(
        f"Generating AI response | conversation_id={conversation_id}",
        extra={
            "conversation_id": conversation_id,
            "message_count": len(messages),
            "is_first": is_first,
            "client_type": client_type,
        },
    )

    try:
        # Get LLM instance with tools
        llm = get_llm(with_tools=True)

        # Prepare system message with context
        system_content = SYSTEM_PROMPT

        # =================================================================
        # Get supported categories dynamically for this client type (cached)
        # =================================================================
        from agent.services.tarifa_service import get_tarifa_service
        tarifa_service = get_tarifa_service()
        supported_categories = await tarifa_service.get_supported_categories_for_client(
            client_type
        )

        # Build dynamic category list for prompt injection
        if supported_categories:
            cat_list_items = []
            for cat in supported_categories:
                desc = cat.get("description", "")
                cat_list_items.append(
                    f"  - **{cat['name']}** (slug: `{cat['slug']}`)"
                    + (f": {desc}" if desc else "")
                )
            cat_list = "\n".join(cat_list_items)
        else:
            cat_list = "  (ninguna categoría disponible actualmente)"

        # =================================================================
        # Add client type context with dynamically injected categories
        # =================================================================
        if client_type == "professional":
            system_content += f"""

## CONTEXTO DEL CLIENTE (MUY IMPORTANTE)
Este cliente es **PROFESIONAL** (taller, empresa de vehículos, etc.).

- **NO preguntes si es particular o profesional** - ya lo sabemos.
- Usa `tipo_cliente: "professional"` en las herramientas (calcular_tarifa, etc.).
- Aplica tarifas para profesionales.

**CATEGORÍAS DE VEHÍCULOS SOPORTADAS PARA ESTE CLIENTE:**
{cat_list}

**IMPORTANTE**: Si el cliente menciona un vehículo que NO esté en la lista anterior:
  - NO llames a `calcular_tarifa`
  - Rechaza educadamente explicando que solo atiendes los tipos listados arriba
  - Ofrece contacto por email (msi@msihomologacion.com) o escalar a agente humano

- Usa un tono profesional pero cercano.
"""
        else:
            system_content += f"""

## CONTEXTO DEL CLIENTE (MUY IMPORTANTE)
Este cliente es **PARTICULAR**.

- **NO preguntes si es particular o profesional** - ya lo sabemos.
- Usa `tipo_cliente: "particular"` en las herramientas (calcular_tarifa, etc.).
- Aplica tarifas estándar para particulares.

**CATEGORÍAS DE VEHÍCULOS SOPORTADAS PARA ESTE CLIENTE:**
{cat_list}

**IMPORTANTE**: Si el cliente menciona un vehículo que NO esté en la lista anterior:
  - NO llames a `calcular_tarifa`
  - Rechaza educadamente explicando que solo atiendes los tipos listados arriba
  - Ofrece contacto por email (msi@msihomologacion.com) o escalar a agente humano

- Usa un tono amable y accesible.
"""

        if user_name:
            system_content += f"\nEl usuario se llama: {user_name}"

        # Format messages for LLM
        llm_messages = [{"role": "system", "content": system_content}]
        llm_messages.extend(format_messages_for_llm(messages))

        # =================================================================
        # Detect and handle images out of context
        # =================================================================
        incoming_attachments = state.get("incoming_attachments", [])
        if incoming_attachments:
            has_image = any(
                att.get("file_type") == "image" for att in incoming_attachments
            )

            if has_image:
                from agent.fsm.case_collection import (
                    is_case_collection_active,
                    get_current_step,
                    CollectionStep,
                )

                fsm_state = state.get("fsm_state")
                is_collecting = is_case_collection_active(fsm_state)
                current_step = get_current_step(fsm_state) if is_collecting else None

                should_inject_context = False
                context_reason = None

                if not is_collecting:
                    should_inject_context = True
                    context_reason = "no_case"
                elif current_step != CollectionStep.COLLECT_IMAGES:
                    should_inject_context = True
                    context_reason = "wrong_phase"

                if should_inject_context:
                    if context_reason == "no_case":
                        context_content = (
                            "IMPORTANTE: El usuario ha enviado una imagen en este mensaje, "
                            "pero NO hay un expediente activo.\n\n"
                            "Debes:\n"
                            "1. Reconocer que viste la imagen\n"
                            "2. Explicar que necesitas abrir un expediente primero para procesarla\n"
                            "3. Ofrecer calcular el presupuesto y abrir el expediente\n\n"
                            "NO intentes llamar a procesar_imagen_expediente sin expediente activo, fallará."
                        )
                    else:
                        context_content = (
                            f"IMPORTANTE: El usuario ha enviado una imagen en este mensaje, "
                            f"pero ya estás en la fase '{current_step.value if current_step else 'desconocida'}', "
                            "NO en la fase de recolección de imágenes.\n\n"
                            "Debes:\n"
                            "1. Agradecer la imagen\n"
                            "2. Explicar que ya pasaste la fase de imágenes\n"
                            "3. Redirigir al usuario al paso actual que estás procesando\n\n"
                            "NO intentes llamar a procesar_imagen_expediente ahora, no es la fase correcta."
                        )

                    # Insert system message BEFORE the last user message
                    context_message = {
                        "role": "system",
                        "content": context_content,
                    }
                    llm_messages.insert(-1, context_message)

                    logger.info(
                        f"Injected image out-of-context warning | "
                        f"is_collecting={is_collecting}, current_step={current_step}, "
                        f"reason={context_reason}",
                        extra={"conversation_id": conversation_id},
                    )

        # Collect images from tool calls
        images_to_send: list[str] = []

        # Track if escalation was triggered by any tool
        escalation_triggered = False
        escalation_id = None

        # Track FSM state updates from case tools
        fsm_state_updates: dict[str, Any] | None = None

        # Tool call loop
        iteration = 0
        while iteration < MAX_TOOL_ITERATIONS:
            iteration += 1

            # Call LLM
            response = await llm.ainvoke(llm_messages)

            # Check for tool calls
            tool_calls = getattr(response, "tool_calls", None)

            if not tool_calls:
                # No more tool calls, we have the final response
                ai_content = response.content
                break

            # Process tool calls
            logger.info(
                f"Processing {len(tool_calls)} tool calls | iteration={iteration}",
                extra={"conversation_id": conversation_id},
            )

            # Add assistant message with tool calls to context
            llm_messages.append({
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["args"]),
                        },
                    }
                    for tc in tool_calls
                ],
            })

            # Execute each tool and add results
            for tool_call in tool_calls:
                tool_result = await execute_tool_call(tool_call, state)

                # Extract images if present (from obtener_documentacion)
                if isinstance(tool_result, dict):
                    # Check for escalation flag from escalar_a_humano or case tools
                    if tool_result.get("escalation_triggered"):
                        escalation_triggered = True
                        escalation_id = tool_result.get("escalation_id")
                        logger.info(
                            f"Escalation triggered by tool | "
                            f"escalation_id={escalation_id} | "
                            f"conversation_id={conversation_id}"
                        )

                    # Check for FSM state updates from case tools
                    if tool_result.get("fsm_state_update"):
                        fsm_state_updates = tool_result["fsm_state_update"]
                        logger.info(
                            f"FSM state updated by tool | "
                            f"conversation_id={conversation_id}",
                            extra={
                                "conversation_id": conversation_id,
                                "tool_name": tool_call.get("name"),
                            },
                        )

                    if "imagenes" in tool_result:
                        # Normalize images to new format with metadata
                        for img in tool_result["imagenes"]:
                            if isinstance(img, str):
                                # Old format: just URL, convert to dict
                                images_to_send.append({
                                    "url": img,
                                    "tipo": "general",
                                    "descripcion": "",
                                })
                            elif isinstance(img, dict):
                                # New format: already has metadata
                                images_to_send.append(img)
                        tool_content = tool_result.get("texto", str(tool_result))
                    elif "result" in tool_result:
                        tool_content = tool_result["result"]
                    elif "error" in tool_result:
                        tool_content = f"Error: {tool_result['error']}"
                    else:
                        tool_content = str(tool_result)
                else:
                    tool_content = str(tool_result)

                # Add tool result to context
                llm_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": tool_content,
                })
        else:
            # Max iterations reached
            logger.warning(
                f"Max tool iterations reached | conversation_id={conversation_id}"
            )
            ai_content = (
                "Disculpa, tuve que hacer demasiadas consultas. "
                "¿Puedes simplificar tu pregunta?"
            )

        logger.info(
            f"AI response generated | conversation_id={conversation_id}",
            extra={
                "conversation_id": conversation_id,
                "response_length": len(ai_content) if ai_content else 0,
                "images_count": len(images_to_send),
            },
        )

        # Add AI response to history
        updated_messages = add_message(
            messages=messages,
            role="assistant",
            content=ai_content,
        )

        # Prepare response
        result = {
            "messages": updated_messages,
            "total_message_count": state.get("total_message_count", 0) + 1,
            "error_count": 0,  # Reset error count on success
            "updated_at": datetime.now(UTC),
            "last_node": "conversational_agent",
        }

        # Add images if any (to be sent by main.py)
        if images_to_send:
            # Remove duplicates by URL and keep order
            seen_urls: set[str] = set()
            unique_images: list[dict] = []
            for img in images_to_send:
                if isinstance(img, dict):
                    url = img.get("url")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        unique_images.append(img)
            result["pending_images"] = unique_images

        # Add FSM state updates from case tools
        if fsm_state_updates:
            result["fsm_state"] = fsm_state_updates
            logger.info(
                f"FSM state included in result | conversation_id={conversation_id}",
                extra={"conversation_id": conversation_id},
            )

        # Add escalation flags if triggered by tool
        if escalation_triggered:
            result["escalation_triggered"] = True
            result["escalation_reason"] = "user_request"
            if escalation_id:
                result["escalation_id"] = escalation_id
            logger.info(
                f"Returning escalation result | conversation_id={conversation_id}",
                extra={
                    "conversation_id": conversation_id,
                    "escalation_id": escalation_id,
                },
            )

        return result

    except Exception as e:
        logger.error(
            f"Error generating AI response: {e}",
            extra={"conversation_id": conversation_id},
            exc_info=True,
        )

        # Increment error count
        new_error_count = error_count + 1

        # Check if should escalate
        if new_error_count >= 3:
            logger.warning(
                f"Auto-escalating after {new_error_count} errors | "
                f"conversation_id={conversation_id}",
                extra={"conversation_id": conversation_id},
            )

            # CRITICAL: Disable bot in Chatwoot for auto-escalation
            try:
                from shared.chatwoot_client import ChatwootClient
                chatwoot = ChatwootClient()
                conv_id_int = int(conversation_id)
                await chatwoot.update_conversation_attributes(
                    conversation_id=conv_id_int,
                    attributes={"atencion_automatica": False},
                )
                logger.info(
                    f"Bot disabled for auto-escalation | conversation_id={conversation_id}"
                )

                # Add label (best-effort)
                try:
                    await chatwoot.add_labels(conv_id_int, ["escalado", "error-tecnico"])
                except Exception:
                    pass

                # Add private note (best-effort)
                try:
                    note = (
                        f"ESCALACION AUTOMATICA POR ERRORES\n"
                        f"---\n"
                        f"El bot ha fallado {new_error_count} veces consecutivas.\n"
                        f"El bot ha sido desactivado automaticamente.\n"
                        f"Timestamp: {datetime.now(UTC).isoformat()}"
                    )
                    await chatwoot.add_private_note(conv_id_int, note)
                except Exception:
                    pass

            except Exception as disable_error:
                logger.error(
                    f"Failed to disable bot during auto-escalation: {disable_error}",
                    extra={"conversation_id": conversation_id},
                )

            # Save escalation to DB (best-effort)
            try:
                import uuid as uuid_module
                from database.connection import get_async_session
                from database.models import Escalation

                escalation_id = uuid_module.uuid4()
                user_id = state.get("user_id")

                async with get_async_session() as session:
                    escalation = Escalation(
                        id=escalation_id,
                        conversation_id=str(conversation_id),
                        user_id=uuid_module.UUID(str(user_id)) if user_id else None,
                        reason=f"Auto-escalación tras {new_error_count} errores técnicos consecutivos",
                        source="auto_escalation",
                        status="pending",
                        triggered_at=datetime.now(UTC),
                        metadata_={
                            "error_count": new_error_count,
                            "priority": "high",
                        },
                    )
                    session.add(escalation)
                    await session.commit()
                    logger.info(
                        f"Auto-escalation {escalation_id} saved to database",
                        extra={"escalation_id": str(escalation_id)},
                    )
            except Exception as db_error:
                logger.error(
                    f"Failed to save auto-escalation to DB: {db_error}",
                    extra={"conversation_id": conversation_id},
                )

            fallback = (
                "Lo siento, estoy teniendo problemas técnicos. "
                "Un compañero humano te atenderá en breve."
            )
            return {
                "messages": add_message(messages, "assistant", fallback),
                "error_count": new_error_count,
                "escalation_triggered": True,
                "escalation_reason": "consecutive_errors",
                "updated_at": datetime.now(UTC),
                "last_node": "conversational_agent",
            }

        # Return fallback message
        fallback = (
            "Lo siento, tuve un pequeño problema. "
            "¿Puedes repetir tu mensaje?"
        )
        return {
            "messages": add_message(messages, "assistant", fallback),
            "error_count": new_error_count,
            "updated_at": datetime.now(UTC),
            "last_node": "conversational_agent",
        }
