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
from agent.state.helpers import add_message, format_messages_for_llm
from agent.state.schemas import ConversationState
from agent.tools import get_tarifa_tools
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
        tools = get_tarifa_tools()
        llm = llm.bind_tools(tools)

    return llm


async def execute_tool_call(tool_call: dict) -> dict[str, Any]:
    """
    Execute a tool call and return the result.

    Args:
        tool_call: Tool call dict with name and args

    Returns:
        Dict with tool result (may include images for documentation)
    """
    from agent.tools import (
        listar_categorias,
        calcular_tarifa,
        obtener_documentacion,
        listar_tarifas,
        obtener_servicios_adicionales,
        escalar_a_humano,
    )

    tool_name = tool_call.get("name")
    tool_args = tool_call.get("args", {})

    logger.info(f"Executing tool: {tool_name} with args: {tool_args}")

    tool_map = {
        "listar_categorias": listar_categorias,
        "calcular_tarifa": calcular_tarifa,
        "obtener_documentacion": obtener_documentacion,
        "listar_tarifas": listar_tarifas,
        "obtener_servicios_adicionales": obtener_servicios_adicionales,
        "escalar_a_humano": escalar_a_humano,
    }

    tool_func = tool_map.get(tool_name)
    if not tool_func:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        result = await tool_func.ainvoke(tool_args)

        # obtener_documentacion returns a dict with "texto" and "imagenes"
        if isinstance(result, dict):
            return result
        else:
            return {"result": result}

    except Exception as e:
        logger.error(f"Tool execution error: {e}", exc_info=True)
        return {"error": str(e)}


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

        # Add client type context
        if client_type == "professional":
            system_content += """

## CONTEXTO DEL CLIENTE (MUY IMPORTANTE)
Este cliente es **PROFESIONAL** (taller, empresa de vehículos, etc.).
- **NO preguntes si es particular o profesional** - ya lo sabemos.
- Usa `tipo_cliente: "professional"` en las herramientas (calcular_tarifa, etc.).
- Aplica tarifas para profesionales.
- Usa un tono profesional pero cercano.
"""
        else:
            system_content += """

## CONTEXTO DEL CLIENTE (MUY IMPORTANTE)
Este cliente es **PARTICULAR**.
- **NO preguntes si es particular o profesional** - ya lo sabemos.
- Usa `tipo_cliente: "particular"` en las herramientas (calcular_tarifa, etc.).
- Aplica tarifas estándar para particulares.
- Usa un tono amable y accesible.
"""

        if user_name:
            system_content += f"\nEl usuario se llama: {user_name}"

        # Format messages for LLM
        llm_messages = [{"role": "system", "content": system_content}]
        llm_messages.extend(format_messages_for_llm(messages))

        # Collect images from tool calls
        images_to_send: list[str] = []

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
                tool_result = await execute_tool_call(tool_call)

                # Extract images if present (from obtener_documentacion)
                if isinstance(tool_result, dict):
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
