"""
MSI Automotive - Conversational agent node.

This node handles generating AI responses using OpenRouter LLM with tool support.
"""

import json
import logging
import time as time_module
from datetime import datetime, UTC
from typing import Any

from langchain_openai import ChatOpenAI

from agent.graphs.conversation_flow import wrap_with_security_delimiters
from agent.prompts.loader import assemble_system_prompt, get_prompt_stats
from agent.prompts.state_summary import generate_state_summary_v2
from agent.services.constraint_service import get_constraints_for_category, validate_response
from agent.services.token_tracking import record_token_usage
from agent.services.tool_logging_service import log_tool_call, classify_result
from agent.state.helpers import (
    add_message,
    format_messages_for_llm,
    set_current_state,
    clear_current_state,
)
from agent.state.schemas import ConversationState
from agent.tools import get_all_tools
from agent.tools.image_tools import (
    set_current_state_for_image_tools,
    get_pending_images_result,
    clear_image_tools_state,
)
from shared.config import get_settings

logger = logging.getLogger(__name__)

# Maximum tool call iterations to prevent infinite loops
MAX_TOOL_ITERATIONS = 12  # Increased from 5 to support variant workflows


async def get_case_image_count(case_id: str) -> int:
    """
    Get the count of images for a case from the database.
    
    This is used instead of FSM state because images are saved silently
    by main.py and don't update the FSM state.
    """
    try:
        from sqlalchemy import func, select
        from database.connection import get_async_session
        from database.models import CaseImage
        import uuid
        
        async with get_async_session() as session:
            result = await session.execute(
                select(func.count()).select_from(CaseImage).where(
                    CaseImage.case_id == uuid.UUID(case_id)
                )
            )
            return result.scalar() or 0
    except Exception as e:
        logger.warning(f"Failed to get case image count: {e}")
        return 0


async def get_user_existing_data(user_id: str | None) -> dict[str, Any] | None:
    """
    Get user's existing personal data from previous expedientes.
    
    This is used to offer data recycling during COLLECT_PERSONAL phase.
    
    Args:
        user_id: UUID of the user
        
    Returns:
        Dict with user data fields or None if no data found
    """
    if not user_id:
        return None
        
    try:
        from sqlalchemy import select
        from database.connection import get_async_session
        from database.models import User
        import uuid
        
        async with get_async_session() as session:
            result = await session.execute(
                select(User).where(User.id == uuid.UUID(str(user_id)))
            )
            user = result.scalar_one_or_none()
            
            if not user:
                return None
            
            # Check if user has any meaningful data
            has_data = any([
                user.first_name,
                user.last_name,
                user.nif_cif,
                user.email,
                user.domicilio_calle,
            ])
            
            if not has_data:
                return None
            
            return {
                "first_name": user.first_name,
                "last_name": user.last_name,
                "nif_cif": user.nif_cif,
                "email": user.email,
                "domicilio_calle": user.domicilio_calle,
                "domicilio_localidad": user.domicilio_localidad,
                "domicilio_provincia": user.domicilio_provincia,
                "domicilio_cp": user.domicilio_cp,
            }
    except Exception as e:
        logger.warning(f"Failed to get user existing data: {e}")
        return None


def get_llm(
    with_tools: bool = True,
    tools: list[Any] | None = None,
) -> ChatOpenAI:
    """
    Get configured LLM instance.

    Args:
        with_tools: Whether to bind tools to the LLM
        tools: Optional specific list of tools to bind. If None and with_tools=True,
               uses all tools (legacy behavior). Pass contextual tools for optimization.

    Returns:
        Configured ChatOpenAI instance
    """
    settings = get_settings()

    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        openai_api_key=settings.OPENROUTER_API_KEY,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.3,
        max_tokens=1500,
        default_headers={
            "HTTP-Referer": settings.SITE_URL,
            "X-Title": settings.SITE_NAME,
        },
    )

    if with_tools:
        if tools is not None:
            # Use provided contextual tools (optimized)
            llm = llm.bind_tools(tools)
        else:
            # Legacy behavior: bind all tools
            llm = llm.bind_tools(get_all_tools())

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
        identificar_y_resolver_elementos,
        seleccionar_variante_por_respuesta,
        calcular_tarifa_con_elementos,
        obtener_documentacion_elemento,
        # Case tools
        # NOTE: procesar_imagen* tools removed - images handled by main.py batching
        iniciar_expediente,
        actualizar_datos_expediente,
        actualizar_datos_taller,
        finalizar_expediente,
        cancelar_expediente,
        obtener_estado_expediente,
        # Vehicle tools
        identificar_tipo_vehiculo,
        # Image tools
        enviar_imagenes_ejemplo,
        # Element data collection tools
        obtener_campos_elemento,
        guardar_datos_elemento,
        confirmar_fotos_elemento,
        completar_elemento_actual,
        obtener_progreso_elementos,
        confirmar_documentacion_base,
        reenviar_imagenes_elemento,
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
        "identificar_y_resolver_elementos": identificar_y_resolver_elementos,
        "seleccionar_variante_por_respuesta": seleccionar_variante_por_respuesta,
        "calcular_tarifa_con_elementos": calcular_tarifa_con_elementos,
        "obtener_documentacion_elemento": obtener_documentacion_elemento,
        # Case tools (procesar_imagen* removed - handled by main.py batching)
        "iniciar_expediente": iniciar_expediente,
        "actualizar_datos_expediente": actualizar_datos_expediente,
        "actualizar_datos_taller": actualizar_datos_taller,
        "finalizar_expediente": finalizar_expediente,
        "cancelar_expediente": cancelar_expediente,
        "obtener_estado_expediente": obtener_estado_expediente,
        # Vehicle tools
        "identificar_tipo_vehiculo": identificar_tipo_vehiculo,
        # Image tools
        "enviar_imagenes_ejemplo": enviar_imagenes_ejemplo,
        # Element data collection tools
        "obtener_campos_elemento": obtener_campos_elemento,
        "guardar_datos_elemento": guardar_datos_elemento,
        "confirmar_fotos_elemento": confirmar_fotos_elemento,
        "completar_elemento_actual": completar_elemento_actual,
        "obtener_progreso_elementos": obtener_progreso_elementos,
        "confirmar_documentacion_base": confirmar_documentacion_base,
        "reenviar_imagenes_elemento": reenviar_imagenes_elemento,
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


def _get_phase_instructions(phase: str) -> str | None:
    """
    Get instructions for a specific FSM phase to inject after phase transition.
    
    This helps the LLM understand what to do when the FSM changes phase
    mid-conversation (e.g., after iniciar_expediente changes to collect_images).
    
    Args:
        phase: The FSM phase name (e.g., "collect_images", "collect_personal")
        
    Returns:
        Instructions string or None if no special instructions needed
    """
    phase_instructions = {
        "collect_images": (
            "NUEVA FASE: RECOLECCIÓN DE IMÁGENES\n\n"
            "INSTRUCCIONES OBLIGATORIAS:\n"
            "1. Pide al usuario que envíe las fotos del elemento actual\n"
            "2. NO pidas datos personales todavía - primero van las FOTOS\n"
            "3. SOLO usa enviar_imagenes_ejemplo() si el usuario PIDE ver ejemplos\n"
            "4. Cuando el usuario diga 'listo' o similar, usa confirmar_fotos_elemento()\n\n"
            "EJEMPLO DE RESPUESTA:\n"
            "\"¡Perfecto! Ya tengo tu expediente creado. Ahora envíame las fotos "
            "del elemento. Si necesitas ver ejemplos de qué fotos necesito, dímelo. "
            "Cuando hayas terminado, escribe 'listo'.\""
        ),
        "collect_personal": (
            "NUEVA FASE: RECOLECCIÓN DE DATOS PERSONALES\n\n"
            "INSTRUCCIONES:\n"
            "1. Pide al usuario sus datos personales (nombre, DNI, email, dirección, ITV)\n"
            "2. Si el usuario ya tiene datos guardados, muéstralos y pregunta si son correctos\n"
            "3. Usa actualizar_datos_expediente() para guardar los datos"
        ),
        "collect_vehicle": (
            "NUEVA FASE: RECOLECCIÓN DE DATOS DEL VEHÍCULO\n\n"
            "INSTRUCCIONES:\n"
            "1. Pide al usuario los datos del vehículo (marca, modelo, matrícula, año)\n"
            "2. Usa actualizar_datos_expediente() para guardar los datos"
        ),
        "collect_workshop": (
            "NUEVA FASE: SELECCIÓN DE TALLER\n\n"
            "INSTRUCCIONES OBLIGATORIAS:\n"
            "1. Pregunta al usuario: '¿Quieres que MSI aporte el certificado del taller "
            "(coste adicional de 85€), o usarás tu propio taller?'\n"
            "2. SIEMPRE menciona el coste de 85€ del certificado MSI\n"
            "3. Si elige MSI: llama actualizar_datos_taller(taller_propio=False)\n"
            "4. Si tiene taller propio: pide TODOS los datos (nombre, responsable, domicilio, "
            "provincia, ciudad, telefono, registro_industrial, actividad) y llama "
            "actualizar_datos_taller(taller_propio=True, datos_taller={...})\n"
            "5. NO inventes que guardaste datos sin llamar a la herramienta\n\n"
            "CRÍTICO: Sin llamar a actualizar_datos_taller(), los datos NO se guardan."
        ),
    }
    
    return phase_instructions.get(phase)


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
        # =================================================================
        # Get contextual tools based on FSM phase (token optimization)
        # Reduces tool tokens from ~4,400 to ~800-1,500 per call
        # =================================================================
        from agent.tools.tool_manager import get_tools_for_phase, get_phase_from_fsm_state
        
        fsm_state = state.get("fsm_state")
        current_phase = get_phase_from_fsm_state(fsm_state)
        all_tools = get_all_tools()
        contextual_tools = get_tools_for_phase(current_phase, all_tools)
        
        # Log token savings from contextual tools
        tools_saved = len(all_tools) - len(contextual_tools)
        estimated_tokens_saved = tools_saved * 150  # ~150 tokens per tool
        logger.info(
            f"Contextual tools loaded | phase={current_phase.value} | "
            f"tools={len(contextual_tools)}/{len(all_tools)} | "
            f"~{estimated_tokens_saved} tokens saved",
            extra={
                "conversation_id": conversation_id,
                "phase": current_phase.value,
                "contextual_tools": len(contextual_tools),
                "all_tools": len(all_tools),
                "estimated_tokens_saved": estimated_tokens_saved,
            },
        )
        
        # Get LLM instance with contextual tools (reduced token usage)
        llm = get_llm(with_tools=True, tools=contextual_tools)

        # =================================================================
        # Get supported categories dynamically for this client type (cached)
        # =================================================================
        from agent.services.tarifa_service import get_tarifa_service
        tarifa_service = get_tarifa_service()
        supported_categories = await tarifa_service.get_supported_categories_for_client(
            client_type or "particular"
        )

        # =================================================================
        # Build dynamic client context for prompt injection
        # =================================================================
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
        # Get user existing data from DB (for name priority and data recycling)
        # =================================================================
        user_id = state.get("user_id")
        user_existing_data: dict[str, Any] | None = await get_user_existing_data(user_id)
        
        # Determine display name: DB name takes priority over WhatsApp name
        display_name = user_name  # Default to WhatsApp name
        if user_existing_data:
            db_first = user_existing_data.get("first_name", "")
            db_last = user_existing_data.get("last_name", "")
            db_full_name = f"{db_first} {db_last}".strip()
            if db_full_name:
                display_name = db_full_name
                logger.info(
                    f"Using DB name '{db_full_name}' instead of WhatsApp name '{user_name}'",
                    extra={"conversation_id": conversation_id},
                )

        # Build client context string
        client_type_display = "PROFESIONAL" if client_type == "professional" else "PARTICULAR"
        client_context = f"""Este cliente es **{client_type_display}**.

- **NO preguntes si es particular o profesional** - ya lo sabemos.
- Usa `tipo_cliente: "{client_type or 'particular'}"` en las herramientas.

**CATEGORÍAS DE VEHÍCULOS SOPORTADAS:**
{cat_list}

**IMPORTANTE**: Si el vehículo NO está en la lista:
  - Rechaza educadamente explicando que solo atiendes los tipos listados
  - Ofrece contacto por email (msi@msihomologacion.com) o escalar a humano
"""
        if display_name:
            client_context += f"\nEl usuario se llama: {display_name}"

        # =================================================================
        # FSM state already obtained above for contextual tools
        # =================================================================
        # fsm_state is already set from get_phase_from_fsm_state
        
        # Get last tariff result for state summary
        tarifa_actual: dict[str, Any] | None = state.get("tarifa_actual")
        
        # Get image count if in case collection
        images_received_count = 0
        if fsm_state and fsm_state.get("case_collection"):
            case_state = fsm_state["case_collection"]
            case_id = case_state.get("case_id")
            if case_id:
                images_received_count = await get_case_image_count(case_id)
        
        # Check if we need user data for COLLECT_PERSONAL phase
        from agent.fsm.case_collection import CollectionStep, get_case_fsm_state
        case_fsm_state = get_case_fsm_state(fsm_state)
        current_step = case_fsm_state.get("step", CollectionStep.IDLE.value)
        
        # Only pass user_existing_data to state_summary if in COLLECT_PERSONAL
        user_data_for_summary = user_existing_data if current_step == CollectionStep.COLLECT_PERSONAL.value else None
        if user_data_for_summary:
            logger.info(
                f"User has existing data for recycling | conversation_id={conversation_id}",
                extra={"conversation_id": conversation_id, "has_data": True},
            )
        
        # Generate dynamic state summary (v2 - minimal mode for reduced tokens)
        state_summary = generate_state_summary_v2(
            fsm_state=fsm_state,
            mode="minimal",
            last_tariff_result=tarifa_actual,
            user_existing_data=user_data_for_summary,
        )
        
        # =================================================================
        # Assemble dynamic system prompt (CORE + PHASE + CONTEXT + SUMMARY)
        # This is the key optimization - only includes relevant phase content
        # =================================================================
        dynamic_prompt = assemble_system_prompt(
            fsm_state=fsm_state,
            state_summary=state_summary,
            client_context=client_context,
        )
        
        # Wrap with security delimiters
        system_content = wrap_with_security_delimiters(dynamic_prompt)
        
        # Log prompt stats for monitoring
        prompt_stats = get_prompt_stats(fsm_state)
        logger.info(
            f"Dynamic prompt assembled | phase={prompt_stats['current_phase']} | "
            f"~{prompt_stats['total_tokens_estimate']} tokens",
            extra={
                "conversation_id": conversation_id,
                "prompt_stats": prompt_stats,
            },
        )

        # Format messages for LLM
        llm_messages = [{"role": "system", "content": system_content}]
        llm_messages.extend(format_messages_for_llm(messages))

        # =================================================================
        # Handle images outside of element/base-docs collection phases
        # NOTE: During COLLECT_ELEMENT_DATA and COLLECT_BASE_DOCS, images are
        # handled by the FSM. This section only handles out-of-context images.
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

                # Only inject warning if NOT in image collection phases
                # Images are expected in COLLECT_ELEMENT_DATA (photos phase) and COLLECT_BASE_DOCS
                image_collection_steps = {
                    CollectionStep.COLLECT_ELEMENT_DATA,
                    CollectionStep.COLLECT_BASE_DOCS,
                }
                if not is_collecting or current_step not in image_collection_steps:
                    if not is_collecting:
                        context_content = (
                            "IMPORTANTE: El usuario ha enviado una imagen, pero NO hay expediente activo.\n\n"
                            "Responde BREVEMENTE (1-2 frases): indica que para procesar imagenes "
                            "primero necesita iniciar un expediente de homologacion. "
                            "Pregunta en que puedes ayudarle."
                        )
                    else:
                        context_content = (
                            f"IMPORTANTE: El usuario ha enviado una imagen, pero estas en fase "
                            f"'{current_step.value if current_step else 'desconocida'}', no en recoleccion de imagenes.\n\n"
                            "Responde BREVEMENTE: indica que no es el momento de enviar imagenes "
                            "y continua con el paso actual del expediente."
                        )

                    # Insert system message BEFORE the last user message
                    context_message = {
                        "role": "system",
                        "content": context_content,
                    }
                    llm_messages.insert(-1, context_message)

                    logger.info(
                        f"Image received outside image collection phase | "
                        f"is_collecting={is_collecting}, current_step={current_step}",
                        extra={"conversation_id": conversation_id},
                    )

        # Collect images from tool calls (now only from enviar_imagenes_ejemplo)
        images_to_send: list[dict[str, Any]] = []
        follow_up_message: str | None = None

        # Track if escalation was triggered by any tool
        escalation_triggered = False
        escalation_id = None

        # Track FSM state updates from case tools
        fsm_state_updates: dict[str, Any] | None = None
        
        # NOTE: tarifa_actual is already extracted above for state_summary generation
        # It's reused here for enviar_imagenes_ejemplo tool
        
        # Track calculated price for safety injection (in case LLM forgets to mention it)
        calculated_price: float | None = None
        calculated_elements: list[str] = []
        calculated_element_names: list[str] = []  # Readable names for user-facing messages

        # Track which tools were called this turn (for constraint validation)
        tools_called_this_turn: set[str] = set()
        MAX_VALIDATION_RETRIES = 2
        validation_retries = 0

        # Tool call loop
        iteration = 0
        while iteration < MAX_TOOL_ITERATIONS:
            iteration += 1

            # Call LLM
            response = await llm.ainvoke(llm_messages)

            # Track token usage (non-blocking, errors are logged but don't break flow)
            usage_metadata = getattr(response, "usage_metadata", None)
            if usage_metadata:
                await record_token_usage(
                    input_tokens=usage_metadata.get("input_tokens", 0),
                    output_tokens=usage_metadata.get("output_tokens", 0),
                )

            # Check for tool calls
            tool_calls = getattr(response, "tool_calls", None)

            if not tool_calls:
                # No more tool calls, we have the final response
                ai_content = response.content

                # === CONSTRAINT VALIDATION LAYER ===
                # Check LLM response against DB-driven constraints to prevent hallucinations
                if ai_content and validation_retries < MAX_VALIDATION_RETRIES:
                    category_slug = state.get("context", {}).get("category_slug") if isinstance(state.get("context"), dict) else None
                    try:
                        constraints = await get_constraints_for_category(category_slug)
                        if constraints:
                            is_valid, error_injection = validate_response(
                                ai_content, 
                                tools_called_this_turn, 
                                constraints,
                                fsm_state=state.get("fsm_state"),
                            )
                            if not is_valid and error_injection:
                                validation_retries += 1
                                logger.warning(
                                    f"Constraint violation detected (retry {validation_retries}/{MAX_VALIDATION_RETRIES}) | "
                                    f"conversation_id={conversation_id} | tools_called={tools_called_this_turn}",
                                    extra={"conversation_id": conversation_id},
                                )
                                # Inject correction and retry LLM call
                                llm_messages.append({
                                    "role": "user",
                                    "content": f"[SYSTEM VALIDATION ERROR]: {error_injection}",
                                })
                                continue  # Re-enter the while loop for retry
                    except Exception as e:
                        # Never block the agent on constraint validation errors
                        logger.error(
                            f"Constraint validation error (non-blocking): {e}",
                            extra={"conversation_id": conversation_id},
                        )

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
                # Set up state for image tools (includes tarifa_actual)
                state_for_tools = {**state, "tarifa_actual": tarifa_actual}
                set_current_state_for_image_tools(state_for_tools)
                
                # Execute tool with timing
                tool_start_time = time_module.monotonic()
                tool_result = await execute_tool_call(tool_call, state)
                tool_exec_ms = int((time_module.monotonic() - tool_start_time) * 1000)
                
                # Track tool name for constraint validation
                tool_name = tool_call.get("name")
                if tool_name:
                    tools_called_this_turn.add(tool_name)

                # Log tool call to PostgreSQL (fire-and-forget)
                tool_result_str = str(tool_result) if tool_result else ""
                await log_tool_call(
                    conversation_id=conversation_id,
                    tool_name=tool_name or "unknown",
                    parameters=tool_call.get("args", {}),
                    result_summary=tool_result_str[:500],
                    result_type=classify_result(tool_result_str),
                    execution_time_ms=tool_exec_ms,
                    iteration=iteration,
                )
                
                # Check for pending images from enviar_imagenes_ejemplo
                if tool_name == "enviar_imagenes_ejemplo":
                    pending_result = get_pending_images_result()
                    if pending_result:
                        if pending_result.get("images"):
                            images_to_send.extend(pending_result["images"])
                            logger.info(
                                f"[enviar_imagenes_ejemplo] Queued {len(pending_result['images'])} images",
                                extra={"conversation_id": conversation_id}
                            )
                            # Clear images from tarifa_actual to prevent duplicate sends
                            if tarifa_actual and tarifa_actual.get("imagenes_ejemplo"):
                                tarifa_actual["imagenes_ejemplo"] = []
                                logger.info(
                                    f"[enviar_imagenes_ejemplo] Cleared tarifa_actual images to prevent duplicates",
                                    extra={"conversation_id": conversation_id}
                                )
                            # Set flag to prevent duplicate image sends
                            state["images_sent_for_current_quote"] = True
                            logger.info(
                                f"[enviar_imagenes_ejemplo] Set images_sent_for_current_quote=True",
                                extra={"conversation_id": conversation_id}
                            )
                        if pending_result.get("follow_up_message"):
                            follow_up_message = pending_result["follow_up_message"]
                            logger.info(
                                f"[enviar_imagenes_ejemplo] Set follow_up_message",
                                extra={"conversation_id": conversation_id}
                            )

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

                    # Special handling for calcular_tarifa_con_elementos JSON response
                    if tool_name == "calcular_tarifa_con_elementos":
                        try:
                            # Extract JSON from {"result": "...json..."} wrapper if present
                            if isinstance(tool_result, dict) and "result" in tool_result:
                                result_str = tool_result["result"]
                                parsed = json.loads(result_str) if isinstance(result_str, str) else result_str
                            else:
                                parsed = json.loads(tool_result) if isinstance(tool_result, str) else tool_result
                            
                            if isinstance(parsed, dict) and "texto" in parsed:
                                # Extract structured data for LLM
                                tool_content = parsed["texto"]

                                # Add internal data for later use by iniciar_expediente
                                if "datos" in parsed:
                                    tool_content += f"\n\n[DATOS INTERNOS - Para iniciar_expediente]:\n"
                                    tool_content += f"tier_id={parsed['datos']['tier_id']}\n"
                                    tool_content += f"tarifa_calculada={parsed['datos']['price']}"

                                # Store tarifa_actual for enviar_imagenes_ejemplo tool
                                # Images are NO LONGER auto-sent - LLM must call enviar_imagenes_ejemplo
                                if "datos" in parsed:
                                    tarifa_actual = {
                                        "tier_id": parsed["datos"].get("tier_id"),
                                        "tier_name": parsed["datos"].get("tier_name"),
                                        "price": parsed["datos"].get("price"),
                                        "element_codes": parsed["datos"].get("element_codes", []),
                                        "imagenes_ejemplo": parsed.get("imagenes_ejemplo", []),
                                    }
                                    img_count = len(tarifa_actual["imagenes_ejemplo"])
                                    logger.info(
                                        f"[calcular_tarifa] Stored tarifa_actual with {img_count} images for enviar_imagenes_ejemplo",
                                        extra={"conversation_id": conversation_id}
                                    )
                                    # Reset image sent flag for new quote
                                    state["images_sent_for_current_quote"] = False
                                    
                                    # Get price for explicit instruction
                                    price = parsed["datos"].get("price", 0)
                                    
                                    # Store price for safety injection later (local variable)
                                    calculated_price = price
                                    calculated_elements = parsed["datos"].get("element_codes", [])
                                    calculated_element_names = parsed["datos"].get("elements", [])  # Readable names for user
                                    
                                    # Get warnings for explicit instruction
                                    warnings_list = parsed["datos"].get("warnings", [])
                                    warnings_text = ""
                                    if warnings_list:
                                        warnings_text = "\n\nADVERTENCIAS QUE DEBES MENCIONAR:\n"
                                        for w in warnings_list:
                                            warnings_text += f"- {w['message']}\n"
                                    
                                    # Build VERY explicit instruction to include price AND warnings
                                    tool_content += f"""

=== INSTRUCCION CRITICA - LEE ESTO ===
PRECIO CALCULADO: {price}€ +IVA
{warnings_text}
**OBLIGATORIO - Tu respuesta DEBE incluir EN ESTE ORDEN**:
1. PRIMERO: "El presupuesto es de {price}€ +IVA (No se incluye el certificado del taller de montaje)"
2. SEGUNDO: Las ADVERTENCIAS listadas arriba (si las hay) - usa "Ten en cuenta:" y listalas
3. TERCERO: Pregunta si quiere ver fotos de ejemplo

NO omitas las advertencias. Son informacion IMPORTANTE para el cliente.
NO envies imagenes sin mencionar el precio y advertencias primero.

[IMAGENES]: {img_count} disponibles.
Despues de dar el precio y advertencias, llama: enviar_imagenes_ejemplo(tipo='presupuesto', follow_up_message='¿Quieres que abra un expediente para gestionar tu homologacion?')
"""
                            else:
                                tool_content = str(tool_result)
                        except (json.JSONDecodeError, KeyError, TypeError):
                            # Backward compatibility: if not JSON, use as-is
                            tool_content = str(tool_result)
                    elif tool_name == "identificar_y_resolver_elementos":
                        # Format JSON response for clear LLM understanding
                        try:
                            # Get the result JSON string
                            result_str = tool_result.get("result", tool_result) if isinstance(tool_result, dict) else tool_result
                            parsed = json.loads(result_str) if isinstance(result_str, str) else result_str

                            # Build clear message for LLM
                            lines = []

                            # Elementos listos (sin variantes)
                            elementos_listos = parsed.get("elementos_listos", [])
                            if elementos_listos:
                                names = [e.get("nombre", e.get("codigo")) for e in elementos_listos]
                                lines.append(f"ELEMENTOS IDENTIFICADOS (listos): {', '.join(names)}")
                                codes = [e.get("codigo") for e in elementos_listos]
                                lines.append(f"Códigos: {codes}")

                            # Elementos con variantes (requieren clarificación)
                            elementos_con_variantes = parsed.get("elementos_con_variantes", [])
                            if elementos_con_variantes:
                                lines.append("")
                                lines.append("ELEMENTOS QUE REQUIEREN CLARIFICACIÓN:")
                                for elem in elementos_con_variantes:
                                    variantes = [v.get("nombre") for v in elem.get("variantes", [])]
                                    lines.append(f"  • {elem.get('nombre')} - Opciones: {', '.join(variantes)}")

                            # Preguntas sugeridas
                            preguntas = parsed.get("preguntas_variantes", [])
                            if preguntas:
                                lines.append("")
                                lines.append("PREGUNTAS A HACER AL USUARIO:")
                                for p in preguntas:
                                    lines.append(f"  → {p.get('pregunta')}")

                            # Términos no reconocidos
                            no_reconocidos = parsed.get("terminos_no_reconocidos", [])
                            if no_reconocidos:
                                lines.append("")
                                lines.append(f"TÉRMINOS NO RECONOCIDOS: {', '.join(no_reconocidos)}")
                                lines.append("Pregunta al usuario qué quiere decir con estos términos.")

                            # Instrucciones (si las hay)
                            if parsed.get("instrucciones"):
                                lines.append("")
                                lines.append(f"SIGUIENTE PASO: {parsed['instrucciones']}")
                                if elementos_con_variantes:
                                    lines.append("")
                                    lines.append("⚠️ IMPORTANTE: Responde SOLO con la(s) pregunta(s) de variantes. NO menciones imágenes, documentación ni elementos listos.")

                            # Si no hay elementos listos ni con variantes
                            if not elementos_listos and not elementos_con_variantes:
                                if parsed.get("mensaje"):
                                    lines.append(parsed["mensaje"])
                                else:
                                    lines.append("No se identificaron elementos. Pregunta al usuario más detalles.")

                            tool_content = "\n".join(lines)

                        except (json.JSONDecodeError, KeyError, TypeError) as e:
                            logger.warning(f"Error parsing identificar_y_resolver_elementos response: {e}")
                            result_str = tool_result.get("result", tool_result) if isinstance(tool_result, dict) else tool_result
                            tool_content = str(result_str)
                    elif "imagenes" in tool_result:
                        # Images are available but NOT auto-sent
                        # LLM should call enviar_imagenes_ejemplo if it wants to send them
                        img_count = len(tool_result["imagenes"])
                        tool_content = tool_result.get("texto", str(tool_result))
                        if img_count > 0:
                            tool_content += f"\n\n[IMAGENES DISPONIBLES]: {img_count} imagenes. Usa enviar_imagenes_ejemplo(tipo='elemento', ...) si quieres enviarlas."
                    elif tool_result.get("success") is False or "error" in tool_result:
                        # ERROR CASE: Tool failed - inject mandatory instructions
                        # This handles both:
                        # - Tools returning {"success": False, "message": "...", "error": "..."}
                        # - Tools returning {"success": False, "error": "..."} (legacy)
                        error_msg = tool_result.get("error", tool_result.get("message", "Error desconocido"))
                        current_step = tool_result.get("current_step", "desconocido")
                        
                        tool_content = (
                            f"ERROR DE HERRAMIENTA: {error_msg}\n\n"
                            f"INSTRUCCIÓN OBLIGATORIA: La herramienta '{tool_name}' FALLÓ.\n"
                            f"- NO digas al usuario que la acción fue exitosa\n"
                            f"- NO continúes con el siguiente paso\n"
                            f"- Explica el problema al usuario\n"
                            f"- Sigue las instrucciones del error\n"
                        )
                        if current_step and current_step != "desconocido":
                            tool_content += f"\nPaso actual del expediente: {current_step}"
                        
                        # If there's a message with guidance, include it
                        if "message" in tool_result and tool_result["message"] != error_msg:
                            tool_content += f"\n\n{tool_result['message']}"
                        
                        logger.warning(
                            f"Tool error | tool={tool_name} | error={error_msg} | "
                            f"step={current_step} | conversation_id={conversation_id}",
                            extra={
                                "conversation_id": conversation_id,
                                "tool_name": tool_name,
                                "error": error_msg,
                                "current_step": current_step,
                            },
                        )
                    elif "message" in tool_result:
                        # SUCCESS CASE: Case tools with message field
                        tool_content = tool_result["message"]
                        logger.info(
                            f"Case tool returned message | tool={tool_name} | "
                            f"success={tool_result.get('success')} | "
                            f"conversation_id={conversation_id}",
                            extra={"conversation_id": conversation_id, "tool_name": tool_name},
                        )
                    elif "result" in tool_result:
                        tool_content = tool_result["result"]
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
                
                # If FSM state changed, inject phase-specific instructions
                if fsm_state_updates and fsm_state_updates.get("case_collection"):
                    new_step = fsm_state_updates["case_collection"].get("step")
                    if new_step:
                        phase_instructions = _get_phase_instructions(new_step)
                        if phase_instructions:
                            llm_messages.append({
                                "role": "user",
                                "content": f"[SISTEMA - CAMBIO DE FASE]\n{phase_instructions}",
                            })
                            logger.info(
                                f"Injected phase instructions for {new_step} | conversation_id={conversation_id}",
                                extra={"conversation_id": conversation_id, "new_phase": new_step},
                            )
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
        
        # Safety check: Inject price if calculated but not mentioned in response
        if calculated_price is not None and ai_content:
            # Check if the response mentions the price (looking for number + €)
            price_str = str(int(calculated_price)) if calculated_price == int(calculated_price) else str(calculated_price)
            price_mentioned = (
                f"{price_str}€" in ai_content or 
                f"{price_str} €" in ai_content or
                f"{price_str}EUR" in ai_content or
                "presupuesto" in ai_content.lower() and "€" in ai_content
            )
            
            if not price_mentioned and images_to_send:
                # Price was calculated but NOT mentioned - inject it
                logger.warning(
                    f"Price {calculated_price}€ calculated but not in response - injecting",
                    extra={"conversation_id": conversation_id, "price": calculated_price}
                )
                elements_text = ", ".join(calculated_element_names) if calculated_element_names else "los elementos solicitados"
                price_prefix = f"El presupuesto para homologar {elements_text} es de {int(calculated_price)}€ +IVA.\n\n"
                ai_content = price_prefix + ai_content

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

        # Add tarifa_actual for persistence (used by enviar_imagenes_ejemplo)
        if tarifa_actual:
            result["tarifa_actual"] = tarifa_actual

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
            
            # Build pending_images with optional follow_up_message
            pending_payload: dict[str, Any] = {"images": unique_images}
            if follow_up_message:
                pending_payload["follow_up_message"] = follow_up_message
            result["pending_images"] = pending_payload

        # Clean up image tools state
        clear_image_tools_state()

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
