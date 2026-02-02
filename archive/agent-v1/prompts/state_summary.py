"""
Dynamic State Summary Generator for MSI-a Agent.

This module generates a concise state summary (~100 tokens) that provides
the LLM with real-time context about the current conversation state.

The summary includes:
- Last calculated price and elements (if any)
- Current expediente info (if active)
- Pending actions (images to collect, data missing, etc.)
- Recent tool call results
"""

import logging
from typing import Any

from agent.fsm.case_collection import (
    CollectionStep,
    get_case_fsm_state,
)

logger = logging.getLogger(__name__)


def _get_phase_display(step_value: str) -> str:
    """Get human-readable phase name."""
    phase_names = {
        CollectionStep.IDLE.value: "Presupuestación",
        CollectionStep.COLLECT_ELEMENT_DATA.value: "Recolección de fotos y datos por elemento",
        CollectionStep.COLLECT_BASE_DOCS.value: "Documentación base del vehículo",
        CollectionStep.COLLECT_PERSONAL.value: "Datos personales",
        CollectionStep.COLLECT_VEHICLE.value: "Datos del vehículo",
        CollectionStep.COLLECT_WORKSHOP.value: "Datos del taller",
        CollectionStep.REVIEW_SUMMARY.value: "Revisión y confirmación",
        CollectionStep.COMPLETED.value: "Expediente completado",
    }
    return phase_names.get(step_value, step_value)


def _format_tariff_summary(tariff_result: dict[str, Any]) -> str:
    """Format last tariff calculation result."""
    parts = []
    
    # Price
    price = tariff_result.get("precio_final") or tariff_result.get("precio")
    if price:
        parts.append(f"ÚLTIMO PRESUPUESTO: {price}€ +IVA")
    
    # Elements
    elements = tariff_result.get("elementos_incluidos") or tariff_result.get("elementos", [])
    if elements:
        element_names = [e.get("nombre", e.get("codigo", "?")) for e in elements]
        parts.append(f"Elementos: {', '.join(element_names)}")
    
    # Warnings
    warnings = tariff_result.get("advertencias", [])
    if warnings:
        parts.append(f"⚠️ Advertencias: {len(warnings)}")
    
    return " | ".join(parts) if parts else ""


def _format_expediente_summary(case_state: dict[str, Any]) -> str:
    """Format active expediente info."""
    parts = []
    
    case_id = case_state.get("case_id")
    if case_id:
        # Show shortened ID
        short_id = case_id[:8] if len(case_id) > 8 else case_id
        parts.append(f"EXPEDIENTE: {short_id}...")
    
    category = case_state.get("category_slug")
    if category:
        parts.append(f"Categoría: {category}")
    
    elements = case_state.get("element_codes", [])
    if elements:
        parts.append(f"Elementos: {', '.join(elements)}")
    
    tariff = case_state.get("tariff_amount")
    if tariff:
        parts.append(f"Tarifa: {tariff}€")
    
    return " | ".join(parts) if parts else ""


def _format_images_summary(case_state: dict[str, Any], session_count: int) -> str:
    """Format images collection status and current element info."""
    parts = []
    
    # Current element info (critical for COLLECT_ELEMENT_DATA)
    element_codes = case_state.get("element_codes", [])
    current_idx = case_state.get("current_element_index", 0)
    element_phase = case_state.get("element_phase", "photos")
    
    if element_codes and current_idx < len(element_codes):
        current_element = element_codes[current_idx]
        total_elements = len(element_codes)
        
        parts.append(f"ELEMENTO ACTUAL: {current_element} ({current_idx + 1}/{total_elements})")
        parts.append(f"FASE DEL ELEMENTO: {element_phase.upper()}")
        
        if element_phase == "data":
            parts.append("⚠️ DEBES seguir las instrucciones del sistema para los campos requeridos")
    
    # Images received
    received = case_state.get("received_images", [])
    received_count = len(received)
    
    if received_count > 0:
        parts.append(f"Imágenes recibidas: {received_count}")
    
    if session_count > 0:
        parts.append(f"({session_count} en esta sesión)")
    
    return " | ".join(parts) if parts else ""


def _format_variants_summary(pending_variants: list[dict[str, Any]]) -> str:
    """Format pending variant questions with clear instructions for LLM."""
    if not pending_variants:
        return ""
    
    parts = ["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
    parts.append("⚠️  VARIANTES PENDIENTES - ACCIÓN REQUERIDA")
    parts.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    parts.append("")
    
    for variant_info in pending_variants:
        codigo_base = variant_info.get("codigo_base", "?")
        pregunta = variant_info.get("pregunta", f"¿Qué tipo de {codigo_base}?")
        opciones = variant_info.get("opciones", [])
        
        parts.append(f"Elemento: {codigo_base}")
        parts.append(f"Pregunta: {pregunta}")
        if opciones:
            parts.append(f"Opciones: {', '.join(opciones)}")
        parts.append("")
    
    parts.append("⚠️ INSTRUCCIÓN OBLIGATORIA:")
    parts.append("Si el usuario responde a la pregunta de variante,")
    parts.append(f"USA seleccionar_variante_por_respuesta(categoria_vehiculo, codigo_elemento_base, respuesta_usuario)")
    parts.append("NO vuelvas a llamar identificar_y_resolver_elementos()")
    parts.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    return "\n".join(parts)


def _format_data_collection_status(case_state: dict[str, Any], current_step: str) -> str:
    """Format data collection status for current phase."""
    parts = []
    
    if current_step == CollectionStep.COLLECT_PERSONAL.value:
        personal = case_state.get("personal_data", {})
        filled = [k for k, v in personal.items() if v]
        missing = [k for k, v in personal.items() if not v]
        
        if filled:
            parts.append(f"Datos personales: {len(filled)} campos completados")
        if missing:
            # Show up to 3 missing
            missing_display = missing[:3]
            parts.append(f"Faltan: {', '.join(missing_display)}")
    
    elif current_step == CollectionStep.COLLECT_VEHICLE.value:
        vehicle = case_state.get("vehicle_data", {})
        filled = [k for k, v in vehicle.items() if v]
        missing = [k for k, v in vehicle.items() if not v and k != "bastidor"]  # bastidor is optional
        
        if filled:
            parts.append(f"Datos vehículo: {len(filled)} campos completados")
        if missing:
            parts.append(f"Faltan: {', '.join(missing)}")
    
    elif current_step == CollectionStep.COLLECT_WORKSHOP.value:
        taller_propio = case_state.get("taller_propio")
        
        if taller_propio is None:
            parts.append("Pendiente: pregunta MSI vs taller propio")
        elif taller_propio:
            taller = case_state.get("taller_data", {})
            filled = [k for k, v in (taller or {}).items() if v]
            parts.append(f"Taller propio: {len(filled)} datos recogidos")
        else:
            parts.append("Taller: MSI aporta certificado")
    
    return " | ".join(parts) if parts else ""


def _format_user_existing_data(user_data: dict[str, Any]) -> str:
    """Format user's existing personal data from previous cases."""
    parts = []
    
    # Check if we have any meaningful data
    has_data = any([
        user_data.get("first_name"),
        user_data.get("last_name"),
        user_data.get("nif_cif"),
        user_data.get("email"),
        user_data.get("domicilio_calle"),
    ])
    
    if not has_data:
        return ""
    
    # Make it very explicit that LLM MUST show these to user
    parts.append("=" * 50)
    parts.append("ACCION REQUERIDA: MOSTRAR DATOS EXISTENTES AL USUARIO")
    parts.append("=" * 50)
    parts.append("El usuario ya tiene datos guardados. DEBES:")
    parts.append("1. Mostrarle estos datos")
    parts.append("2. Preguntarle si son correctos")
    parts.append("3. Solo pedir los que faltan")
    parts.append("")
    parts.append("DATOS GUARDADOS:")
    
    # Track what we have and what's missing
    missing = []
    
    # Name
    first_name = user_data.get("first_name", "")
    last_name = user_data.get("last_name", "")
    full_name = f"{first_name} {last_name}".strip()
    if full_name:
        parts.append(f"- Nombre: {full_name} [OK]")
    else:
        missing.append("nombre y apellidos")
    
    # Document
    nif_cif = user_data.get("nif_cif")
    if nif_cif:
        parts.append(f"- DNI/CIF: {nif_cif} [OK]")
    else:
        missing.append("DNI/CIF")
    
    # Email
    email = user_data.get("email")
    if email:
        parts.append(f"- Email: {email} [OK]")
    else:
        missing.append("email")
    
    # Address
    calle = user_data.get("domicilio_calle", "")
    localidad = user_data.get("domicilio_localidad", "")
    provincia = user_data.get("domicilio_provincia", "")
    cp = user_data.get("domicilio_cp", "")
    
    address_parts = [p for p in [calle, cp, localidad, provincia] if p]
    if address_parts:
        parts.append(f"- Domicilio: {', '.join(address_parts)} [OK]")
    else:
        missing.append("domicilio completo")
    
    # ITV is always missing from user table (it's per-case)
    missing.append("ITV donde pasara la inspeccion")
    
    if missing:
        parts.append("")
        parts.append(f"DATOS QUE FALTAN: {', '.join(missing)}")
    
    parts.append("=" * 50)
    
    return "\n".join(parts)


def generate_minimal_summary(
    current_price: float | None = None,
    current_elements: list[str] | None = None,
    current_phase: str = "idle",
) -> str:
    """
    Generate a minimal state summary for simple cases.
    
    Use this when you don't have full FSM state but need basic context.
    
    Args:
        current_price: Last calculated price
        current_elements: List of element codes
        current_phase: Current phase name
        
    Returns:
        Minimal state summary string
    """
    parts = []
    
    parts.append(f"FASE: {current_phase}")
    
    if current_price:
        parts.append(f"PRECIO: {current_price}€ +IVA")
    
    if current_elements:
        parts.append(f"ELEMENTOS: {', '.join(current_elements)}")
    
    return " | ".join(parts) if parts else "Sin estado activo."


# =============================================================================
# NEW: Mode-based State Summary (v2)
# =============================================================================

def generate_state_summary_v2(
    fsm_state: dict[str, Any] | None,
    mode: str = "minimal",
    last_tariff_result: dict[str, Any] | None = None,
    user_existing_data: dict[str, Any] | None = None,
    pending_variants: list[dict[str, Any]] | None = None,
) -> str:
    """
    Generate state summary with configurable verbosity.
    
    Modes:
        - minimal: Ultra-compact (~30-50 tokens) - DEFAULT for production
        - standard: Useful context for LLM (~100 tokens)
        - debug: Full detail (~300 tokens) - for development
    
    Args:
        fsm_state: Full FSM state dict
        mode: "minimal", "standard", or "debug"
        last_tariff_result: Last tariff calculation result
        user_existing_data: User's existing personal data
        pending_variants: Pending variant questions from identificar_y_resolver_elementos
    
    Returns:
        State summary string
    """
    if mode == "minimal":
        return _generate_minimal_summary_v2(fsm_state, user_existing_data, pending_variants)
    else:
        # standard and debug modes both use the standard summary
        return _generate_standard_summary(fsm_state, last_tariff_result, user_existing_data, pending_variants)


def _generate_minimal_summary_v2(
    fsm_state: dict[str, Any] | None,
    user_existing_data: dict[str, Any] | None = None,
    pending_variants: list[dict[str, Any]] | None = None,
) -> str:
    """
    Generate ultra-minimal summary - only critical context.
    
    Target: ~30-50 tokens (down from ~100)
    
    Only shows info when LLM NEEDS it to make decisions:
    - PENDING_VARIANTS: CRITICAL - shows variant questions with instructions
    - COLLECT_ELEMENT_DATA: current element + phase (critical for tool choice)
    - COLLECT_PERSONAL: hint about existing data (critical for UX)
    - Other phases: nothing (phase prompt already has instructions)
    """
    parts = []
    
    # PENDING VARIANTS: Highest priority - show with clear instructions
    if pending_variants:
        variants_summary = _format_variants_summary(pending_variants)
        if variants_summary:
            parts.append(variants_summary)
    
    if not fsm_state:
        return "\n\n".join(parts) if parts else ""
    
    case_state = get_case_fsm_state(fsm_state)
    step = case_state.get("step", CollectionStep.IDLE.value)
    
    # IDLE: only show if there are pending variants
    if step == CollectionStep.IDLE.value:
        return "\n\n".join(parts) if parts else ""
    
    # COLLECT_ELEMENT_DATA: Need to know current element and phase
    if step == CollectionStep.COLLECT_ELEMENT_DATA.value:
        codes = case_state.get("element_codes", [])
        idx = case_state.get("current_element_index", 0)
        phase = case_state.get("element_phase", "photos")
        
        if codes and idx < len(codes):
            # Ultra-compact format
            parts.append(f"[{codes[idx]} ({idx+1}/{len(codes)}) {phase}]")
    
    # COLLECT_PERSONAL: Hint if user has existing data
    elif step == CollectionStep.COLLECT_PERSONAL.value and user_existing_data:
        has_data = any([
            user_existing_data.get("first_name"),
            user_existing_data.get("nif_cif"),
        ])
        if has_data:
            parts.append("[Usuario tiene datos guardados]")
    
    # Other phases: minimal phase indicator only if really needed
    # Most phases don't need it - the phase prompt is enough
    
    return "\n\n".join(parts) if parts else ""


def _generate_standard_summary(
    fsm_state: dict[str, Any] | None,
    last_tariff_result: dict[str, Any] | None = None,
    user_existing_data: dict[str, Any] | None = None,
    pending_variants: list[dict[str, Any]] | None = None,
) -> str:
    """
    Generate standard summary - useful context without verbosity.
    
    Target: ~100 tokens
    
    Shows pending variants with high priority.
    """
    parts = []
    
    # PENDING VARIANTS: Highest priority
    if pending_variants:
        variants_summary = _format_variants_summary(pending_variants)
        if variants_summary:
            parts.append(variants_summary)
    
    if not fsm_state:
        return "\n\n".join(parts) if parts else ""
    
    case_state = get_case_fsm_state(fsm_state)
    step = case_state.get("step", CollectionStep.IDLE.value)
    
    # Phase with display name
    phase_display = _get_phase_display(step)
    parts.append(f"FASE: {phase_display}")
    
    # Tariff info (if available)
    if last_tariff_result:
        price = last_tariff_result.get("precio_final") or last_tariff_result.get("precio")
        if price:
            parts.append(f"PRECIO: {price}E +IVA")
    
    # Element info
    if step == CollectionStep.COLLECT_ELEMENT_DATA.value:
        codes = case_state.get("element_codes", [])
        idx = case_state.get("current_element_index", 0)
        phase = case_state.get("element_phase", "photos")
        
        if codes and idx < len(codes):
            parts.append(f"ELEMENTO: {codes[idx]} ({idx+1}/{len(codes)}) | Subfase: {phase}")
    
    # User existing data hint (only in COLLECT_PERSONAL)
    if step == CollectionStep.COLLECT_PERSONAL.value and user_existing_data:
        has_data = any([
            user_existing_data.get("first_name"),
            user_existing_data.get("nif_cif"),
            user_existing_data.get("email"),
        ])
        if has_data:
            parts.append("NOTA: Usuario tiene datos guardados - mostrar y confirmar")
    
    return "\n\n".join(parts) if parts else ""


# Default mode for production
DEFAULT_SUMMARY_MODE = "minimal"
