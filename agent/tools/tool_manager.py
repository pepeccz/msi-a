"""
MSI Automotive - Contextual Tool Manager.

This module provides phase-aware tool selection to reduce token usage.
Instead of sending all 27 tools on every LLM call (~4,400 tokens),
we only send the tools relevant to the current FSM phase (~800-1,500 tokens).

Token savings: ~2,500-3,600 tokens per call (57-82% reduction in tool tokens).
"""

import logging
from typing import Any

from agent.fsm.case_collection import CollectionStep

logger = logging.getLogger(__name__)

# =============================================================================
# TOOL DEFINITIONS BY PHASE
# =============================================================================

# Tools that are ALWAYS available regardless of phase
UNIVERSAL_TOOLS = [
    "escalar_a_humano",  # User can always request human help
]

# Tools available during quotation (no active case)
IDLE_TOOLS = [
    # Element identification and pricing
    "identificar_y_resolver_elementos",
    "seleccionar_variante_por_respuesta",
    "calcular_tarifa_con_elementos",
    # Information tools
    "listar_categorias",
    "listar_tarifas",
    "listar_elementos",
    "obtener_servicios_adicionales",
    "obtener_documentacion_elemento",
    # Vehicle identification
    "identificar_tipo_vehiculo",
    # Image examples
    "enviar_imagenes_ejemplo",
    # Start a new case
    "iniciar_expediente",
]

# Tools for collecting element photos and technical data
COLLECT_ELEMENT_DATA_TOOLS = [
    "confirmar_fotos_elemento",
    "guardar_datos_elemento",
    "completar_elemento_actual",
    "obtener_progreso_elementos",
    "obtener_campos_elemento",
    "reenviar_imagenes_elemento",
    # Can send example images for current element
    "enviar_imagenes_ejemplo",
    # Handle off-topic queries
    "consulta_durante_expediente",
    # Case status
    "obtener_estado_expediente",
    "cancelar_expediente",
]

# Tools for collecting base vehicle documents (ficha técnica, permiso)
COLLECT_BASE_DOCS_TOOLS = [
    "confirmar_documentacion_base",
    "enviar_imagenes_ejemplo",  # Allow sending example images of required docs
    # Handle off-topic queries
    "consulta_durante_expediente",
    # Case status
    "obtener_estado_expediente",
    "cancelar_expediente",
]

# Tools for collecting personal data
COLLECT_PERSONAL_TOOLS = [
    "actualizar_datos_expediente",  # Only for datos_personales
    # Handle off-topic queries
    "consulta_durante_expediente",
    # Case status
    "obtener_estado_expediente",
    "cancelar_expediente",
]

# Tools for collecting vehicle data
COLLECT_VEHICLE_TOOLS = [
    "actualizar_datos_expediente",  # Only for datos_vehiculo
    # Handle off-topic queries
    "consulta_durante_expediente",
    # Case status
    "obtener_estado_expediente",
    "cancelar_expediente",
]

# Tools for collecting workshop data
COLLECT_WORKSHOP_TOOLS = [
    "actualizar_datos_taller",
    # Handle off-topic queries
    "consulta_durante_expediente",
    # Case status
    "obtener_estado_expediente",
    "cancelar_expediente",
]

# Tools for final review
REVIEW_SUMMARY_TOOLS = [
    "finalizar_expediente",
    "editar_expediente",  # Allow user to go back and edit sections
    # Handle off-topic queries
    "consulta_durante_expediente",
    # Case status (can't cancel at this point, but can view)
    "obtener_estado_expediente",
]

# Mapping from CollectionStep to tool lists
TOOLS_BY_PHASE: dict[CollectionStep, list[str]] = {
    CollectionStep.IDLE: IDLE_TOOLS,
    CollectionStep.COLLECT_ELEMENT_DATA: COLLECT_ELEMENT_DATA_TOOLS,
    CollectionStep.COLLECT_BASE_DOCS: COLLECT_BASE_DOCS_TOOLS,
    CollectionStep.COLLECT_PERSONAL: COLLECT_PERSONAL_TOOLS,
    CollectionStep.COLLECT_VEHICLE: COLLECT_VEHICLE_TOOLS,
    CollectionStep.COLLECT_WORKSHOP: COLLECT_WORKSHOP_TOOLS,
    CollectionStep.REVIEW_SUMMARY: REVIEW_SUMMARY_TOOLS,
    CollectionStep.COMPLETED: REVIEW_SUMMARY_TOOLS,  # Same as review
}


def get_tool_names_for_phase(phase: CollectionStep) -> list[str]:
    """
    Get the list of tool names allowed for a given FSM phase.
    
    Args:
        phase: Current CollectionStep
        
    Returns:
        List of tool names (strings) that should be available
    """
    phase_tools = TOOLS_BY_PHASE.get(phase, IDLE_TOOLS)
    
    # Combine phase-specific tools with universal tools (deduplicated)
    all_tool_names = list(set(phase_tools + UNIVERSAL_TOOLS))
    
    return all_tool_names


def get_tools_for_phase(phase: CollectionStep, all_tools: list[Any]) -> list[Any]:
    """
    Filter tools to only those relevant for the current phase.
    
    This is the main entry point for contextual tool injection.
    
    Args:
        phase: Current CollectionStep
        all_tools: Complete list of all available tools
        
    Returns:
        Filtered list of tools for the current phase
    """
    allowed_names = get_tool_names_for_phase(phase)
    
    # Build name-to-tool mapping
    tool_map = {}
    for tool in all_tools:
        # Handle both langchain tools and plain functions
        name = getattr(tool, "name", None) or getattr(tool, "__name__", None)
        if name:
            tool_map[name] = tool
    
    # Filter tools by allowed names
    filtered_tools = []
    for name in allowed_names:
        if name in tool_map:
            filtered_tools.append(tool_map[name])
        else:
            # Tool not found in provided list - log warning but don't fail
            logger.debug(
                f"Tool '{name}' specified for phase {phase.value} but not found in tool list"
            )
    
    logger.info(
        f"Contextual tools selected | phase={phase.value} | "
        f"tools={len(filtered_tools)}/{len(all_tools)} | "
        f"names={[t.name for t in filtered_tools[:5]]}{'...' if len(filtered_tools) > 5 else ''}",
    )
    
    return filtered_tools


def get_phase_from_fsm_state(fsm_state: dict[str, Any] | None) -> CollectionStep:
    """
    Extract the current CollectionStep from FSM state.
    
    Args:
        fsm_state: Full FSM state dict from conversation state
        
    Returns:
        Current CollectionStep (defaults to IDLE if not found)
    """
    if not fsm_state:
        return CollectionStep.IDLE
    
    case_state = fsm_state.get("case_collection", {})
    step_value = case_state.get("step", CollectionStep.IDLE.value)
    
    try:
        return CollectionStep(step_value)
    except ValueError:
        logger.warning(f"Unknown FSM step value: {step_value}, defaulting to IDLE")
        return CollectionStep.IDLE


# =============================================================================
# STATISTICS AND DEBUGGING
# =============================================================================

def get_tool_stats() -> dict[str, Any]:
    """
    Get statistics about tool distribution across phases.
    
    Useful for debugging and token usage analysis.
    
    Returns:
        Dict with tool counts per phase and estimated token savings
    """
    stats = {
        "phases": {},
        "total_unique_tools": 0,
        "estimated_tokens_per_tool": 150,  # Conservative estimate
    }
    
    all_tools: set[str] = set()
    
    for phase, tools in TOOLS_BY_PHASE.items():
        phase_tools = list(set(tools + UNIVERSAL_TOOLS))
        stats["phases"][phase.value] = {
            "tool_count": len(phase_tools),
            "tools": phase_tools,
        }
        all_tools.update(phase_tools)
    
    stats["total_unique_tools"] = len(all_tools)
    
    # Calculate estimated savings
    # Full tools: 27 tools * 150 tokens = 4,050 tokens
    # Average contextual: ~8 tools * 150 tokens = 1,200 tokens
    # Savings: ~2,850 tokens per call
    full_tokens = stats["total_unique_tools"] * stats["estimated_tokens_per_tool"]
    
    avg_tools = sum(
        len(phase["tools"]) for phase in stats["phases"].values()
    ) / len(stats["phases"])
    avg_tokens = int(avg_tools * stats["estimated_tokens_per_tool"])
    
    stats["full_tools_tokens"] = full_tokens
    stats["avg_contextual_tokens"] = avg_tokens
    stats["estimated_savings"] = full_tokens - avg_tokens
    stats["savings_percentage"] = round(
        (full_tokens - avg_tokens) / full_tokens * 100, 1
    )
    
    return stats
