"""Canonical expediente onboarding builders.

Shared source of truth for expediente opening and re-entry copy so direct
starts, auto-created expediente flows, and recoveries stay aligned.
"""

from __future__ import annotations

from agent.services.expediente_constants import phase_overview_lines


def _build_intro_message() -> str:
    """Build the canonical intro message from the shared step labels."""
    lines = phase_overview_lines()
    return (
        "He abierto tu expediente de homologación. Tiene 6 fases:\n\n"
        + "\n".join(lines)
        + "\n\nEmpezamos por el paso 1."
    )


EXPEDIENTE_INTRO_MESSAGE: str = _build_intro_message()


def build_expediente_opening_overview() -> str:
    """Return the canonical expediente phase overview."""
    return EXPEDIENTE_INTRO_MESSAGE


def build_expediente_intro_confirmation() -> dict[str, bool]:
    """Return mode_context updates after the intro was delivered."""
    return {"expediente_intro_sent": True}


def build_new_expediente_case_instructions(
    *,
    first_element_display: str,
    total_elements: int,
    prefilled_context: str = "",
    element_photo_instructions: str = "",
    intro_already_sent: bool,
    auto_created: bool,
) -> str:
    """Build canonical instructions for a newly opened expediente."""
    intro_block = (
        "El sistema va a enviar al usuario el resumen de las 6 fases automáticamente.\n"
        f"Empieza directamente pidiendo las fotos del primer elemento: **{first_element_display}**.\n\n"
        if intro_already_sent
        else (
            "COMUNICA al usuario exactamente este mensaje de bienvenida (sin parafrasear):\n\n"
            f"{build_expediente_opening_overview()}\n\n"
            f"Vamos con el primero: **{first_element_display}**.\n\n"
        )
    )
    created_label = "EXPEDIENTE CREADO AUTOMÁTICAMENTE" if auto_created else "EXPEDIENTE CREADO"

    return (
        f"{created_label}.\n\n"
        f"{prefilled_context}"
        f"EMPEZAMOS con el primer elemento: {first_element_display} ({1}/{total_elements}).\n\n"
        f"{intro_block}"
        "INSTRUCCIONES OBLIGATORIAS:\n"
        "1. Pregunta al usuario si quiere ver imágenes de ejemplo del elemento\n"
        "2. SOLO usa enviar_imagenes_ejemplo() si el usuario las pide\n"
        "3. Pide al usuario que envíe las fotos del elemento\n"
        "4. Cuando diga 'listo', usa confirmar_fotos_elemento()\n"
        "5. Luego recoge los datos técnicos con guardar_datos_elemento()\n"
        "6. Usa completar_elemento_actual() para pasar al siguiente\n\n"
        f"ELEMENTO ACTUAL: {first_element_display}\n"
        f"TOTAL ELEMENTOS: {total_elements}\n"
        "IMPORTANTE: El expediente ya está creado. NO llames a iniciar_expediente(). Empieza directamente.\n"
        "RECUERDA: NUNCA digas que el expediente está completo sin llamar a finalizar_expediente()."
        f"{element_photo_instructions}"
    )


def build_resume_expediente_case_instructions(
    *,
    elementos_str: str,
    progress_desc: str,
    resume_phase_label: str,
    created_at_str: str,
) -> str:
    """Build canonical instructions for resumed/recovered expediente entry."""
    return (
        "RETOMANDO EXPEDIENTE - INSTRUCCIONES PARA EL AGENTE\n\n"
        "Este usuario tenía un expediente de homologación abierto que se interrumpió.\n\n"
        f"RESUMEN DEL PROCESO:\n{build_expediente_opening_overview()}\n\n"
        f"DATOS DEL EXPEDIENTE ANTERIOR:\n"
        f"  - Elementos: {elementos_str}\n"
        f"  - Progreso: {progress_desc}\n"
        f"  - Fase donde quedó: {resume_phase_label}\n"
        f"  - Iniciado: {created_at_str}\n\n"
        "DEBES hacer lo siguiente en tu respuesta:\n"
        "1. Saluda al usuario de forma natural y breve\n"
        "2. Explica que encontraste su expediente de homologación anterior\n"
        "3. Indícale los elementos y el progreso\n"
        "4. Ofrécele DOS opciones:\n"
        "   A) Continuar donde lo dejó\n"
        "   B) Empezar de cero (si quiere, cancela el anterior con cancelar_expediente())\n\n"
        "NO empieces a recolectar datos hasta que el usuario confirme que quiere continuar.\n"
        f"Si confirma continuar, reanuda directamente en la fase: {resume_phase_label} (sin crear un expediente nuevo)."
    )
