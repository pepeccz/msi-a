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
) -> str:
    """Build canonical instructions for a newly opened expediente.

    The 6-phase overview is now delivered by entry_router as a standalone
    AIMessage (T3a/T3b).  The LLM always receives instructions to start
    directly with phase 1 content — there is no ``intro_already_sent`` branch.

    Layer C (Batch 3): warm opener whitelist + descriptions-from-gate instruction
    + invitation to ask for example images.
    """
    return (
        "EXPEDIENTE RECIÉN ABIERTO — INSTRUCCIONES PARA TU PRIMER MENSAJE AL USUARIO.\n\n"
        f"{prefilled_context}"
        "El sistema YA envió al usuario el resumen de las 6 fases automáticamente como mensaje aparte.\n"
        "Tu mensaje debe ser cálido, claro y explicar qué fotos necesitás para empezar. NO repitas el resumen de fases.\n\n"
        "IDIOMA: castellano de España — tuteo ESTRICTO. \"tienes\" no \"tenés\", \"envíame\" no \"enviame/mandame\", \"mira\" no \"mirá\", \"pídemelo\" no \"pedímelo\", \"llama\" no \"llamá\", \"usa\" no \"usá\". PROHIBIDO voseo en TODO el mensaje.\n\n"
        "ESTRUCTURA OBLIGATORIA DEL MENSAJE (respeta el orden):\n\n"
        "1. OPENER cálido — empieza con una de estas frases (elige la más natural):\n"
        "     • \"Excelente, te he abierto un expediente en nuestro sistema para gestionar tu homologación.\"\n"
        "     • \"¡Perfecto! Ya tienes tu expediente abierto en nuestro sistema.\"\n"
        "     • \"Genial, acabo de abrir tu expediente de homologación.\"\n\n"
        f"2. TRANSICIÓN fija: \"Ahora necesito que me envíes las siguientes imágenes:\"\n\n"
        f"3. LISTA NUMERADA de fotos del primer elemento ({first_element_display}, 1/{total_elements}):\n"
        "   - LLAMA primero enviar_imagenes_ejemplo(tipo=\"elemento\","
        f" codigo_elemento=\"{first_element_display}\") — te devuelve INSTRUCCIONES DE FOTOS con descripciones literales.\n"
        "   - Presenta UNA foto por línea, numeradas. Transcribe la descripción LITERAL de la tool.\n"
        "   - A continuación de cada descripción, añade en la MISMA línea un motivo breve (≤10 palabras) entre paréntesis explicando para qué se usa (ej.: \"(para comprobar la fijación)\"). No inventes descripciones, solo el motivo.\n\n"
        "4. CIERRE fijo (una línea en blanco antes, copia literal):\n"
        "     \"Si quieres que te envíe imágenes de ejemplo de cómo debe quedar cada una, pídemelo. Si no, envíame tus fotos y espera a que las procese. ¡Gracias!\"\n\n"
        "PROHIBIDO en este mensaje:\n"
        "  • Abrir con frases burocráticas o declarativas tipo 'expediente abierto/creado'.\n"
        "  • Repetir el listado de 6 fases (ya se envió aparte).\n"
        "  • Inventar descripciones de fotos — salen de enviar_imagenes_ejemplo.\n"
        "  • Cerrar con \"Envíamelas como foto o como PDF\" — usa el CIERRE fijo de arriba.\n"
        "  • Usar voseo (tenés, dale, querés, pedímelos, envialo, etc.).\n\n"
        "FLUJO COMPLETO DEL ELEMENTO (para los turnos siguientes):\n"
        "  a) Usuario envía fotos → confirmar_fotos_elemento()\n"
        "  b) guardar_datos_elemento() para los datos técnicos\n"
        "  c) completar_elemento_actual() para pasar al siguiente\n\n"
        f"ELEMENTO ACTUAL: {first_element_display} | TOTAL ELEMENTOS: {total_elements}\n"
        "RECORDATORIOS DUROS:\n"
        "  • NO llames iniciar_expediente() — el expediente ya existe.\n"
        "  • NUNCA digas que el expediente está completo sin llamar finalizar_expediente() primero.\n"
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
