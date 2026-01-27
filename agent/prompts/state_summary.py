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


def generate_state_summary(
    fsm_state: dict[str, Any] | None,
    last_tariff_result: dict[str, Any] | None = None,
    images_received_count: int = 0,
    pending_varintes: list[dict[str, Any]] | None = None,
    user_existing_data: dict[str, Any] | None = None,
) -> str:
    """
    Generate a concise state summary for the LLM.
    
    Args:
        fsm_state: Full FSM state dict
        last_tariff_result: Result from last calcular_tarifa_con_elementos call
        images_received_count: Number of images received in current session
        pending_variants: List of pending variant questions
        user_existing_data: User's existing personal data from previous cases
        
    Returns:
        State summary string (~100 tokens)
    """
    parts = []
    
    # Get case collection state
    case_state = get_case_fsm_state(fsm_state)
    current_step = case_state.get("step", CollectionStep.IDLE.value)
    
    # 1. Current phase indicator (HIGHLY visible for expedientes)
    if current_step not in (CollectionStep.IDLE.value, CollectionStep.CONFIRM_START.value):
        # Make current step HIGHLY visible during active expediente
        parts.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        parts.append(f"⚠️  PASO ACTUAL DEL EXPEDIENTE: {current_step.upper()}")
        parts.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        parts.append("")
    
    phase_display = _get_phase_display(current_step)
    parts.append(f"FASE: {phase_display}")
    
    # 2. Last tariff info (if calculated)
    if last_tariff_result:
        tariff_summary = _format_tariff_summary(last_tariff_result)
        if tariff_summary:
            parts.append(tariff_summary)
    
    # 3. Expediente info (if active)
    if current_step not in (CollectionStep.IDLE.value, CollectionStep.CONFIRM_START.value):
        expediente_summary = _format_expediente_summary(case_state)
        if expediente_summary:
            parts.append(expediente_summary)
    
    # 4. Images/Element status (if in collection phases)
    if current_step in (
        CollectionStep.COLLECT_ELEMENT_DATA.value,
        CollectionStep.COLLECT_BASE_DOCS.value,
    ):
        images_summary = _format_images_summary(case_state, images_received_count)
        if images_summary:
            parts.append(images_summary)
    
    # 5. Pending variants (if any)
    if pending_varintes:
        variants_summary = _format_variants_summary(pending_varintes)
        if variants_summary:
            parts.append(variants_summary)
    
    # 6. User existing data (for COLLECT_PERSONAL phase)
    if current_step == CollectionStep.COLLECT_PERSONAL.value and user_existing_data:
        existing_data_summary = _format_user_existing_data(user_existing_data)
        if existing_data_summary:
            parts.append(existing_data_summary)
    
    # 7. Data collection status
    if current_step in (
        CollectionStep.COLLECT_PERSONAL.value,
        CollectionStep.COLLECT_VEHICLE.value,
        CollectionStep.COLLECT_WORKSHOP.value,
    ):
        data_summary = _format_data_collection_status(case_state, current_step)
        if data_summary:
            parts.append(data_summary)
    
    return "\n".join(parts) if parts else "Sin estado activo."


def _get_phase_display(step_value: str) -> str:
    """Get human-readable phase name."""
    phase_names = {
        CollectionStep.IDLE.value: "Presupuestación",
        CollectionStep.CONFIRM_START.value: "Confirmación de expediente",
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
    """Format pending variant questions."""
    if not pending_variants:
        return ""
    
    codes = [v.get("codigo_base", "?") for v in pending_variants]
    return f"VARIANTES PENDIENTES: {', '.join(codes)}"


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
