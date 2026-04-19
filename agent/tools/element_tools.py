"""
MSI Automotive - Element Tools for LangGraph Agent.

Thin wrapper tools around ElementService and VariantInterpretationService.
All pure business logic lives in the service layer:
- agent.services.element_service   — catalog queries, code normalization
- agent.services.variant_interpretation_service — variant matching helpers

This module owns only:
- @tool-decorated wrappers (one per exported tool)
- Tool-specific orchestration (parallel fetches, response formatting)
- Re-exports of service helpers for backward-compatible imports

Services MUST NOT import from agent/tools/ — one-way dependency only.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog
from langchain_core.tools import tool

from agent.services.element_service import (
    get_element_service,
    get_or_fetch_category_id,
    normalize_element_code,
    normalize_element_codes,
    validate_element_codes as _validate_element_codes_svc,
)
from agent.services.tarifa_service import get_tarifa_service
from agent.services.variant_interpretation_service import (
    AMBIGUITY_THRESHOLD,
    VariantInterpretationResult,
    _BARE_LETTER_RE,
    _apply_single_resolution_to_pending,
    _build_single_variant_result,
    _extract_element_fragment,
    _has_domain_vocabulary,
    _has_domain_vocabulary_from_variants,
    _normalize_to_canonical_letter,
    interpret_variant_allocations,
    validate_and_apply_allocations,
)
from agent.state.conversation_state import PendingVariantGroup
from langchain_core.runnables import RunnableConfig

from agent.state.helpers import (
    get_tool_state,
    normalize_pending_variants,
)
from agent.tools.schemas import (
    CalcularTarifaConElementosInput,
    IdentificarYResolverElementosInput,
    ListarElementosInput,
    ObtenerDocumentacionElementoInput,
    SeleccionarVariantePorRespuestaInput,
)
from agent.utils.validation import validate_category_slug
from shared.config import get_settings

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal alias for backward compat with tests that mock the old path
# ---------------------------------------------------------------------------


async def _validate_element_codes(
    categoria_vehiculo: str,
    codigos_elementos: list[str],
    confianzas: dict[str, float] | None = None,
) -> dict:
    """Backward-compat shim — delegates to element_service.validate_element_codes."""
    return await _validate_element_codes_svc(
        categoria_vehiculo=categoria_vehiculo,
        codigos_elementos=codigos_elementos,
        confianzas=confianzas,
    )


async def _noop_coro(value: Any) -> Any:
    """Trivial awaitable that returns a fixed value — used as a no-op placeholder in gather calls."""
    return value


# ---------------------------------------------------------------------------
# Pure helpers (testable without DB/services)
# ---------------------------------------------------------------------------


def _build_element_image_dict(
    elem: dict[str, Any],
    img: dict[str, Any],
    img_status: str,
) -> dict[str, Any]:
    """Build the image entry for the `element_images` list in ``calcular_tarifa_con_elementos``.

    Caption normalization rules (AC-5.1 – AC-5.4):
    - ``elemento``: always the DB-normalized element name (``elem["name"]``), never the
      raw image description or any user-supplied text.
    - ``descripcion`` (Chatwoot caption): normalized element name enriched with visual
      guidance when available.  Guidance priority: ``user_instruction`` > ``title``.
      When neither is present, caption equals the normalized name only — no error text,
      no placeholder.

    Args:
        elem:      Element record from the DB (must have ``"name"``, ``"code"``).
        img:       Image record from ``element_service.get_element_with_images``.
        img_status: Pre-computed status string (``"active"`` / ``"placeholder"``).

    Returns:
        Dict ready to be appended to ``element_images``.
    """
    normalized_name: str = elem["name"]

    # Visual guidance: prefer user_instruction, fall back to title, then name-only.
    guidance: str = (img.get("user_instruction") or "").strip()
    if not guidance:
        guidance = (img.get("title") or "").strip()

    if guidance:
        caption = f"{normalized_name} — {guidance}"
    else:
        caption = normalized_name

    return {
        "url": img["image_url"],
        "tipo": img["image_type"],
        "elemento": normalized_name,
        "element_code": elem["code"],
        "descripcion": caption,
        "status": img_status,
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool(args_schema=ListarElementosInput)
async def listar_elementos(categoria_vehiculo: str) -> dict[str, Any]:
    """
    Lista todos los elementos homologables disponibles para una categoría de vehículo.

    Usa esta herramienta cuando el usuario pregunte qué elementos puede homologar
    o necesite ver el catálogo de elementos disponibles.

    IMPORTANTE: Usa el slug de categoría correcto:
    - "motos-part" para motocicletas de particulares
    - "aseicars-prof" para autocaravanas de profesionales

    Args:
        categoria_vehiculo: Slug de la categoría (ej: "motos-part", "aseicars-prof")

    Returns:
        Lista formateada de elementos con códigos, nombres y keywords.
    """
    categoria_vehiculo = categoria_vehiculo.lower().strip()

    try:
        validate_category_slug(categoria_vehiculo)
    except ValueError as e:
        logger.error("listar_elementos_invalid_slug", error=str(e))
        return {"error": str(e)}

    element_service = get_element_service()

    category_id = await get_or_fetch_category_id(categoria_vehiculo)
    if not category_id:
        tarifa_service = get_tarifa_service()
        categories = await tarifa_service.get_active_categories()
        available = ", ".join(c["slug"] for c in categories)
        return {
            "error": f"Categoría '{categoria_vehiculo}' no encontrada. Categorías disponibles: {available}"
        }

    elements = await element_service.get_elements_by_category(
        category_id, is_active=True
    )
    if not elements:
        return {
            "error": f"No hay elementos configurados para la categoría '{categoria_vehiculo}'."
        }

    lines = [f"ELEMENTOS HOMOLOGABLES PARA {categoria_vehiculo.upper()}:", ""]
    for elem in elements:
        lines.append(f"- {elem['name']}")
    lines.append("")
    lines.append(f"Total: {len(elements)} elementos disponibles.")
    return {"elementos": "\n".join(lines)}


LETTER_TO_POSITION: dict[str, int] = {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}


@tool(args_schema=SeleccionarVariantePorRespuestaInput)
async def seleccionar_variante_por_respuesta(
    categoria_vehiculo: str,
    codigo_elemento_base: str,
    respuesta_usuario: str,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """
    Mapea la respuesta del usuario a un código de variante específico.

    USA ESTA TOOL después de preguntar al usuario sobre la variante que necesita.
    La herramienta analiza la respuesta y determina qué variante corresponde.

    Soporta:
    - Selección única: "delantera" → SUSPENSION_DEL
    - Multi-selección: "ambos", "todos" → TODAS las variantes
    - Distribución multi-unidad: "2 delanteras y 1 trasera" → asignación por cantidad

    Args:
        categoria_vehiculo: Slug de la categoría (ej: "motos-part", "aseicars-prof")
        codigo_elemento_base: Código del elemento base (ej: "BOLA_REMOLQUE")
        respuesta_usuario: Texto de respuesta del usuario (ej: "sí, aumenta MMR", "ambos", "delantera", "2 delanteras y 1 trasera")

    Returns:
        JSON con UNO de estos formatos:

        Selección única:
        {"selected_variant": "BOLA_CON_MMR", "confidence": 0.95, "name": "..."}

        Multi-selección (usuario quiere todas):
        {"selected_variants": ["INTERMITENTES_DEL", "INTERMITENTES_TRAS"], "mode": "multi_select", "names": [...]}

        Distribución multi-unidad:
        {"selected_variant": "SUSPENSION_DEL", "confidence": 0.9, "applied_allocations": [...], "resolution_status": "resolved", "pending_count": 0}

    Si confidence < 0.7, pregunta al usuario de forma más específica.
    """
    categoria_vehiculo = categoria_vehiculo.lower().strip()
    try:
        validate_category_slug(categoria_vehiculo)
    except ValueError as e:
        logger.error("seleccionar_variante_invalid_slug", error=str(e))
        return {"error": str(e)}

    element_service = get_element_service()

    category_id = await get_or_fetch_category_id(categoria_vehiculo)
    if not category_id:
        return {"error": f"Categoría '{categoria_vehiculo}' no encontrada"}

    codigo_normalizado = codigo_elemento_base.upper().strip()

    variants = await element_service.get_element_variants(
        element_code=codigo_normalizado,
        category_id=category_id,
    )

    # Fuzzy fallback if no variants found with provided code
    if not variants:
        all_elements = await element_service.get_elements_by_category(
            category_id, is_active=True
        )
        from agent.utils.text_utils import normalize_text

        search_term = normalize_text(codigo_elemento_base)
        best_match_elem = None
        for elem in all_elements:
            if elem.get("parent_element_id"):
                continue
            if (
                search_term in normalize_text(elem["name"])
                or normalize_text(elem["name"]) in search_term
                or search_term in normalize_text(elem["code"])
            ):
                best_match_elem = elem
                break

        if best_match_elem:
            logger.info(
                "seleccionar_variante_fuzzy_match",
                original=codigo_elemento_base,
                matched=best_match_elem["code"],
            )
            codigo_normalizado = best_match_elem["code"]
            variants = await element_service.get_element_variants(
                element_code=codigo_normalizado,
                category_id=category_id,
            )

    if not variants:
        all_elements = await element_service.get_elements_by_category(
            category_id, is_active=True
        )
        base_elements = [e for e in all_elements if not e.get("parent_element_id")]
        available_codes = ", ".join(e["code"] for e in base_elements[:10])
        return {
            "error": f"No se encontraron variantes para '{codigo_elemento_base}'",
            "hint": f"Elementos base disponibles: {available_codes}",
            "instrucciones": "Verifica que el código sea correcto. Usa identificar_y_resolver_elementos para obtener los códigos.",
        }

    from agent.utils.text_utils import normalize_text

    respuesta_lower = respuesta_usuario.lower().strip()
    respuesta_normalized = normalize_text(respuesta_usuario)

    # Data-driven multi-select check
    base_element = await element_service.get_element_by_code(
        element_code=codigo_elemento_base.upper(),
        category_id=category_id,
    )
    multi_select_kw = (
        base_element.get("multi_select_keywords", []) if base_element else []
    )
    if multi_select_kw:
        for kw in multi_select_kw:
            kw_normalized = normalize_text(kw)
            if (
                kw_normalized in respuesta_normalized
                or respuesta_normalized in kw_normalized
            ):
                return {
                    "selected_variants": [v["code"] for v in variants],
                    "mode": "multi_select",
                    "matched_keyword": kw,
                    "names": [v["name"] for v in variants],
                    "instrucciones": (
                        f"El usuario quiere TODAS las variantes. "
                        f"Usa todos los códigos: {[v['code'] for v in variants]} "
                        f"en calcular_tarifa_con_elementos."
                    ),
                }

    # Resolve pending variant state for multi-unit awareness
    state = get_tool_state(config)
    mode_context = state.get("mode_context", {})
    raw_pending = mode_context.get("pending_variants", [])
    normalized_pending = normalize_pending_variants(raw_pending)

    current_pending: PendingVariantGroup | None = None
    current_pending_idx: int = -1
    for idx, pv in enumerate(normalized_pending):
        if pv.get("codigo_base", "").upper() == codigo_normalizado:
            current_pending = pv
            current_pending_idx = idx
            break

    cantidad_pendiente = (
        current_pending.get("cantidad_pendiente", 1) if current_pending else 1
    )
    is_multi_unit = cantidad_pendiente > 1
    llm_variant_interpretation_enabled = (
        get_settings().ENABLE_LLM_VARIANT_INTERPRETATION
    )

    # Extract relevant fragment from combined response
    respuesta_para_matching = _extract_element_fragment(
        respuesta=respuesta_usuario,
        codigo_elemento_base=codigo_normalizado,
        base_element=base_element,
        current_pending=current_pending,
        variants=variants,
        current_pending_idx=current_pending_idx,
        total_pending_count=len(normalized_pending),
    )
    if respuesta_para_matching != respuesta_usuario.strip():
        logger.debug(
            "seleccionar_variante_fragment_extracted",
            original=respuesta_usuario,
            fragment=respuesta_para_matching,
            codigo_base=codigo_normalizado,
        )

    # Positional matching via variant_position field
    respuesta_stripped = respuesta_para_matching.lower().strip()
    canonical = _normalize_to_canonical_letter(respuesta_stripped)
    lookup_key = canonical if canonical is not None else respuesta_stripped
    if not is_multi_unit and lookup_key in LETTER_TO_POSITION:
        target_position = LETTER_TO_POSITION[lookup_key]
        positional_match = next(
            (v for v in variants if v.get("variant_position") == target_position), None
        )
        if positional_match:
            logger.info(
                "seleccionar_variante_positional_match",
                user_response=respuesta_usuario,
                position=target_position,
                matched_code=positional_match["code"],
            )
            result = _build_single_variant_result(
                positional_match, codigo_elemento_base, 0.95, "variant_position"
            )
            result = _apply_single_resolution_to_pending(
                result,
                positional_match,
                current_pending,
                current_pending_idx,
                normalized_pending,
            )
            # Normalize _state_update key (apply_single_resolution_to_pending already uses _state_update)
            return result

    # Keyword-based matching (deterministic)
    fragment_normalized = normalize_text(respuesta_para_matching)
    best_match = None
    best_score = 0.0
    for variant in variants:
        score = 0.0
        variant_code_lower = (variant.get("variant_code") or "").lower()
        keywords = variant.get("keywords", [])

        for kw in keywords:
            kw_normalized = normalize_text(kw)
            if kw_normalized in fragment_normalized:
                score += 0.8
            elif " " in kw:
                kw_words = set(kw_normalized.split())
                resp_words = set(fragment_normalized.split())
                overlap = len(kw_words & resp_words)
                if overlap > 0:
                    score += 0.4 * (overlap / len(kw_words))

        if variant_code_lower:
            variant_code_normalized = normalize_text(
                variant_code_lower.replace("_", " ")
            )
            if variant_code_normalized in fragment_normalized:
                score += 0.7

        name_words = [
            w for w in normalize_text(variant["name"].lower()).split() if len(w) > 3
        ]
        matching_words = sum(1 for word in name_words if word in fragment_normalized)
        if matching_words > 0 and name_words:
            score += 0.3 * (matching_words / len(name_words))

        if score > best_score:
            best_score = score
            best_match = variant

    # Single fast-path for high-confidence keyword match
    if (
        best_match
        and best_score >= 0.5
        and (not is_multi_unit or not llm_variant_interpretation_enabled)
    ):
        if is_multi_unit and not llm_variant_interpretation_enabled:
            logger.info(
                "seleccionar_variante_keyword_only_fallback",
                codigo_base=codigo_normalizado,
                cantidad_pendiente=cantidad_pendiente,
            )
        logger.info(
            "seleccionar_variante_single_fast_path",
            matched_code=best_match["code"],
            confidence=round(best_score, 2),
        )
        result = _build_single_variant_result(
            best_match, codigo_elemento_base, best_score, "keyword"
        )
        result = _apply_single_resolution_to_pending(
            result, best_match, current_pending, current_pending_idx, normalized_pending
        )
        return result

    # Multi-unit or low-confidence → LLM interpretation service
    if (
        llm_variant_interpretation_enabled
        and current_pending
        and (is_multi_unit or best_score < 0.5)
    ):
        # Early ambiguity exit (ADR-006)
        if (
            not is_multi_unit
            and best_score < AMBIGUITY_THRESHOLD
            and not _has_domain_vocabulary_from_variants(respuesta_usuario, variants)
        ):
            logger.info(
                "seleccionar_variante_early_ambiguity_exit",
                keyword_score=round(best_score, 2),
            )
            return {
                "needs_clarification": True,
                "clarification_reason": "La respuesta no contiene vocabulario específico de la variante.",
                "pregunta": current_pending.get("pregunta", ""),
                "opciones_disponibles": [v.get("name", "") for v in variants],
            }

        logger.info(
            "seleccionar_variante_llm_interpretation",
            codigo_base=codigo_normalizado,
            cantidad_pendiente=cantidad_pendiente,
        )
        interpretation: VariantInterpretationResult = (
            await interpret_variant_allocations(
                user_message=respuesta_usuario,
                pending_variant=current_pending,
                conversation_context=None,
            )
        )

        if interpretation.needs_clarification:
            return {
                "error": "No se pudo determinar la variante con certeza.",
                "needs_clarification": True,
                "clarification_reason": interpretation.clarification_reason,
                "sugerencia": interpretation.clarification_reason
                or "Pregunta al usuario de forma más específica.",
                "opciones_disponibles": [f"- {v['name']}" for v in variants],
            }

        opciones = current_pending.get("opciones", [])
        option_to_code_map: dict[str, str] = {}
        for i, opcion in enumerate(opciones):
            if i < len(variants):
                option_to_code_map[opcion] = variants[i]["code"]

        updated_pending, apply_errors = validate_and_apply_allocations(
            current_pending,
            interpretation.allocations,
            dry_run=False,
            option_to_code_map=option_to_code_map,
        )
        if apply_errors:
            logger.warning("seleccionar_variante_apply_errors", errors=apply_errors)
            return {
                "error": "No se pudieron aplicar las asignaciones.",
                "apply_errors": apply_errors,
                "sugerencia": "Pregunta al usuario de forma más específica.",
                "opciones_disponibles": [f"- {v['name']}" for v in variants],
            }

        new_pending_list = list(normalized_pending)
        new_pending_list[current_pending_idx] = updated_pending

        unresolved_count = sum(
            1 for pv in new_pending_list if pv.get("status") != "resolved"
        )

        first_alloc = (
            interpretation.allocations[0] if interpretation.allocations else None
        )
        first_variant_code = first_alloc.variant_code if first_alloc else None

        resolved_db_code = None
        resolved_db_name = None
        if first_variant_code:
            from agent.utils.text_utils import normalize_text as _nt

            alloc_norm = _nt(first_variant_code)
            for v in variants:
                v_name_norm = _nt(v["name"])
                v_code_norm = _nt(v.get("variant_code", ""))
                if (
                    (len(alloc_norm) > 2 and alloc_norm in v_name_norm)
                    or v_name_norm in alloc_norm
                    or alloc_norm == v_code_norm
                ):
                    resolved_db_code = v["code"]
                    resolved_db_name = v["name"]
                    break

        # Bare-letter guard
        selected_variant_code = resolved_db_code or first_variant_code
        if selected_variant_code and _BARE_LETTER_RE.match(
            selected_variant_code.strip()
        ):
            letter = selected_variant_code.strip().lower()
            target_position = LETTER_TO_POSITION.get(letter)
            positional_fallback = (
                next(
                    (
                        v
                        for v in variants
                        if v.get("variant_position") == target_position
                    ),
                    None,
                )
                if target_position
                else None
            )
            if positional_fallback:
                avg_confidence = sum(
                    a.confidence for a in interpretation.allocations
                ) / max(len(interpretation.allocations), 1)
                if avg_confidence < 0.3 and not _has_domain_vocabulary(
                    respuesta_usuario
                ):
                    logger.warning(
                        "seleccionar_variante_bare_letter_low_confidence",
                        bare_letter=letter,
                        avg_confidence=round(avg_confidence, 2),
                    )
                    return {
                        "error": "No se pudo determinar la variante con certeza.",
                        "needs_clarification": True,
                        "clarification_reason": "La respuesta no fue suficientemente clara para seleccionar la variante con seguridad.",
                        "sugerencia": "Pregunta al usuario de forma más específica.",
                        "opciones_disponibles": [f"- {v['name']}" for v in variants],
                    }
                logger.info(
                    "seleccionar_variante_bare_letter_mapped",
                    bare_letter=letter,
                    resolved_code=positional_fallback["code"],
                )
                resolved_db_code = positional_fallback["code"]
                resolved_db_name = positional_fallback["name"]
                selected_variant_code = resolved_db_code
            else:
                logger.warning(
                    "seleccionar_variante_bare_letter_rejected", bare_letter=letter
                )
                return {
                    "error": "No se pudo determinar la variante con certeza.",
                    "needs_clarification": True,
                    "clarification_reason": f"La interpretación resultó en '{selected_variant_code}' que no corresponde a ninguna variante conocida.",
                    "sugerencia": "Pregunta al usuario de forma más específica.",
                    "opciones_disponibles": [f"- {v['name']}" for v in variants],
                }

        response_data: dict[str, Any] = {
            "selected_variant": selected_variant_code,
            "confidence": round(
                sum(a.confidence for a in interpretation.allocations)
                / max(len(interpretation.allocations), 1),
                2,
            ),
            "name": resolved_db_name or (first_variant_code or ""),
            "applied_allocations": [
                {
                    "variant_code": a.variant_code,
                    "quantity": a.quantity,
                    "confidence": round(a.confidence, 2),
                }
                for a in interpretation.allocations
            ],
            "resolution_status": updated_pending.get("status", "pending"),
            "pending_count": unresolved_count,
            "instrucciones": (
                f"Todas las variantes de '{codigo_elemento_base}' están resueltas. Puedes proceder a calcular tarifa."
                if updated_pending.get("status") == "resolved"
                else f"Faltan {updated_pending.get('cantidad_pendiente', 0)} unidades por resolver de '{codigo_elemento_base}'. Pregunta al usuario."
            ),
            "_state_update": {
                "pending_variants": [dict(pv) for pv in new_pending_list],
            },
        }
        logger.info(
            "seleccionar_variante_multi_unit_resolved",
            codigo_base=codigo_normalizado,
            resolution_status=updated_pending.get("status"),
        )
        return response_data

    # Fallback: no match
    if not best_match or best_score < 0.5:
        return {
            "error": "No se pudo determinar la variante con certeza.",
            "sugerencia": "Pregunta al usuario de forma más específica.",
            "opciones_disponibles": [f"- {v['name']}" for v in variants],
        }

    result = _build_single_variant_result(
        best_match, codigo_elemento_base, best_score, "keyword"
    )
    return result


@tool(args_schema=CalcularTarifaConElementosInput)
async def calcular_tarifa_con_elementos(
    categoria_vehiculo: str,
    codigos_elementos: list[str],
    skip_validation: bool = False,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """
    Calcula el precio de homologación basándose en elementos específicos del catálogo.

    ⚠️ IMPORTANTE:
    - USA EXACTAMENTE los códigos retornados por `identificar_elementos`
    - NO inventes códigos nuevos
    - DEBES llamar `validar_elementos` ANTES de esta herramienta (o usar skip_validation=True si ya validaste)

    Esta herramienta valida que los elementos existan y busca la tarifa que los cubra.
    La tarifa seleccionada es la más económica que incluye TODOS los elementos especificados.

    Args:
        categoria_vehiculo: Slug de la categoría (ej: "motos-part", "aseicars-prof")
        codigos_elementos: Lista de códigos EXACTOS retornados por identificar_elementos
                          Ejemplo: ["ESCAPE", "MANILLAR"] (NO uses variaciones)
        skip_validation: Si True, omite la validación previa de códigos (usar cuando ya se validó
                        previamente con validar_elementos o identificar_y_resolver_elementos).
                        Default: False

    REFACTOR-001 Note: This tool sets precio_comunicado=True via _state_update,
    signaling that a price has been calculated and will be communicated to the user
    in the LLM's response. The flag is automatically applied by the mode handler.

    Returns:
        Tarifa seleccionada, precio, elementos incluidos y advertencias.
        Los precios son SIN IVA.
    """
    # Diagnostic: soft-warn on pending variants (stale ContextVar is OK — parent guard is the real defense)
    state = get_tool_state(config)
    if state:
        mode_context = state.get("mode_context", {})
        raw_pending = mode_context.get("pending_variants", [])
        if raw_pending:
            norm_pending = normalize_pending_variants(raw_pending)
            unresolved = [pv for pv in norm_pending if pv.get("status") != "resolved"]
            if unresolved:
                logger.warning(
                    "tariff_calc_with_pending_variants_soft_warning",
                    pending_count=len(unresolved),
                    codigos_solicitados=codigos_elementos,
                    note="ContextVar may be stale snapshot from checkpoint. parent_codes guard is the real defense.",
                )

    categoria_vehiculo = categoria_vehiculo.lower().strip()
    try:
        validate_category_slug(categoria_vehiculo)
    except ValueError as e:
        logger.error("calcular_tarifa_invalid_slug", error=str(e))
        return {"success": False, "error": str(e)}

    tarifa_service = get_tarifa_service()
    element_service = get_element_service()

    if not skip_validation:
        validation = await _validate_element_codes(
            categoria_vehiculo=categoria_vehiculo,
            codigos_elementos=codigos_elementos,
        )
        if not validation["valid"]:
            return {
                "success": False,
                "error": (
                    f"❌ ERROR: No puedo calcular tarifa con códigos inválidos.\n\n"
                    f"{validation['message']}\n\n"
                    f"Debes usar `identificar_elementos` primero para obtener códigos válidos."
                ),
            }

    logger.info(
        "calcular_tarifa_start", category=categoria_vehiculo, codes=codigos_elementos
    )

    category_id = await get_or_fetch_category_id(categoria_vehiculo)
    if not category_id:
        categories = await tarifa_service.get_active_categories()
        available = ", ".join(c["slug"] for c in categories)
        return {
            "success": False,
            "error": f"Categoría '{categoria_vehiculo}' no encontrada. Disponibles: {available}",
        }

    if not codigos_elementos:
        return {
            "success": False,
            "error": "Debes especificar al menos un código de elemento.",
        }

    elements = await element_service.get_elements_by_category(
        category_id, is_active=True
    )
    element_by_code = {e["code"]: e for e in elements}
    valid_codes_set = set(element_by_code.keys())

    normalized_codes, corrections, truly_invalid = normalize_element_codes(
        codigos_elementos, valid_codes_set
    )
    if corrections:
        logger.info("calcular_tarifa_auto_corrected_codes", corrections=corrections)

    valid_elements = [
        element_by_code[code] for code in normalized_codes if code in element_by_code
    ]
    invalid_codes = [
        code for code in normalized_codes if code not in element_by_code
    ] + truly_invalid

    if invalid_codes:
        available_codes = ", ".join(sorted(element_by_code.keys()))
        return {
            "success": False,
            "error": (
                f"Error: Códigos no encontrados: {', '.join(invalid_codes)}\n\n"
                f"Códigos válidos para {categoria_vehiculo}: {available_codes}\n\n"
                "Usa `identificar_elementos` para obtener los códigos correctos."
            ),
        }

    if not valid_elements:
        return {"success": False, "error": "No se encontraron elementos válidos."}

    # Unconditional parent-code guard
    element_by_id: dict[str, dict[str, Any]] = {e["id"]: e for e in elements}
    parent_to_children: dict[str, list[dict[str, str]]] = {}
    for el in elements:
        parent_id = el.get("parent_element_id")
        if parent_id and parent_id in element_by_id:
            parent_code = element_by_id[parent_id]["code"]
            parent_to_children.setdefault(parent_code, []).append(
                {"code": el["code"], "name": el["name"]}
            )

    parent_codes_found: list[dict[str, Any]] = []
    remaining_valid: list[dict[str, Any]] = []
    for elem in valid_elements:
        if elem["code"] in parent_to_children:
            children = parent_to_children[elem["code"]]
            parent_codes_found.append(
                {
                    "code": elem["code"],
                    "name": elem["name"],
                    "children": children,
                    "variant_codes": [c["code"] for c in children],
                    "question_hint": elem.get("question_hint")
                    or f"¿Qué tipo de {elem['name'].lower()}?",
                }
            )
        else:
            remaining_valid.append(elem)

    if parent_codes_found:
        logger.warning(
            "tariff_blocked_parent_codes",
            parent_codes=[p["code"] for p in parent_codes_found],
        )
        lines_err = ["=== ERROR: ELEMENTOS SIN VARIANTE ESPECIFICADA ===", ""]
        lines_err.append(
            "Los siguientes elementos requieren que especifiques la variante:"
        )
        lines_err.append("")
        for parent in parent_codes_found:
            lines_err.append(f"❌ '{parent['name']}' tiene variantes disponibles:")
            for child in parent["children"]:
                lines_err.append(f"   • {child['name']} ({child['code']})")
            lines_err.append(f"   Pregunta sugerida: {parent['question_hint']}")
            lines_err.append("")
        lines_err += [
            "⚠️ ACCIÓN OBLIGATORIA:",
            "1. Pregunta al usuario qué variante específica necesita",
            "2. Usa el código de la VARIANTE (no del elemento base)",
            "3. Vuelve a llamar calcular_tarifa_con_elementos con los códigos correctos",
            "",
            "IMPORTANTE: Los elementos padre NO son homologables directamente.",
            "Solo se pueden homologar las variantes específicas.",
        ]
        return {
            "success": False,
            "status": "ERROR_VARIANTE_REQUERIDA",
            "message": "\n".join(lines_err),
            "parent_elements_rejected": parent_codes_found,
            "_state_update": {
                "shared_context": {"precio_comunicado": False},
            },
        }

    client_type = state.get("client_type", "particular") if state else "particular"
    description = ", ".join(e["name"] for e in valid_elements)

    result = await tarifa_service.select_tariff_by_rules(
        category_slug=categoria_vehiculo,
        elements_description=description,
        element_count=len(valid_elements),
        element_codes=[code.upper() for code in codigos_elementos],
    )
    if "error" in result:
        return {"success": False, "error": result["error"]}

    # Collect per-element warnings
    element_count = len(valid_elements)
    existing_warning_codes = {w.get("code") for w in result.get("warnings", [])}
    element_warnings_grouped: dict[str, list[dict]] = {}
    total_element_warnings = 0

    for elem in valid_elements:
        elem_warnings = await element_service.get_element_warnings(elem["id"])
        active_warnings_for_elem = []
        for ew in elem_warnings:
            if ew["code"] in existing_warning_codes:
                continue
            show_condition = ew.get("show_condition", "always")
            threshold = ew.get("threshold_quantity")
            should_show = False
            if show_condition == "always":
                should_show = True
            elif show_condition == "on_exceed_max" and threshold is not None:
                should_show = element_count > threshold
            elif show_condition == "on_below_min" and threshold is not None:
                should_show = element_count < threshold
            else:
                should_show = True
            if should_show:
                warning_data = {
                    "code": ew["code"],
                    "message": ew["message"],
                    "severity": ew["severity"],
                    "element_code": elem["code"],
                    "element_name": elem["name"],
                }
                active_warnings_for_elem.append(warning_data)
                result.setdefault("warnings", []).append(warning_data)
                existing_warning_codes.add(ew["code"])
        if active_warnings_for_elem:
            element_warnings_grouped[elem["code"]] = active_warnings_for_elem
            total_element_warnings += len(active_warnings_for_elem)

    logger.info(
        "calcular_tarifa_warnings_collected",
        element_count=element_count,
        warning_count=total_element_warnings,
    )

    # Base documentation + images
    category_data = await tarifa_service.get_category_data(categoria_vehiculo)
    base_documentation = []
    base_images = []
    if category_data and category_data.get("base_documentation"):
        for base_doc in category_data["base_documentation"]:
            base_documentation.append(
                {
                    "descripcion": base_doc["description"],
                    "imagen_url": base_doc.get("image_url"),
                }
            )
            if base_doc.get("image_url"):
                base_images.append(
                    {
                        "url": base_doc["image_url"],
                        "tipo": "base",
                        "element_code": "_BASE_DOCS",
                        "descripcion": base_doc["description"],
                        "status": "active",
                    }
                )

    element_documentation = []
    element_images = []
    for elem in valid_elements:
        elem_details = await element_service.get_element_with_images(elem["id"])
        elem_doc = {"codigo": elem["code"], "nombre": elem["name"], "imagenes": []}
        if elem_details and elem_details.get("images"):
            for img in elem_details["images"]:
                img_status = img.get("status", "placeholder")
                img_info = {
                    "url": img["image_url"],
                    "tipo": img["image_type"],
                    "titulo": img.get("title", ""),
                    "descripcion": img.get("description", ""),
                    "requerida": img.get("is_required", False),
                    "instruccion_usuario": img.get("user_instruction", ""),
                    "status": img_status,
                }
                elem_doc["imagenes"].append(img_info)
                element_images.append(
                    _build_element_image_dict(elem, img, img_status)
                )
        element_documentation.append(elem_doc)

    # Build response text
    lines = [
        f"TARIFA RECOMENDADA: {result['tier_name']}",
        f"Precio: {result['price']} EUR (IVA no incluido)",
        "",
    ]
    if result.get("conditions"):
        lines.append(f"Condiciones: {result['conditions']}")
        lines.append("")
    lines.append(f"Elementos incluidos ({len(valid_elements)}):")
    for elem in valid_elements:
        lines.append(f"- {elem['name']}")
    lines.append("")

    if result.get("warnings"):
        lines.append("ADVERTENCIAS:")
        if element_warnings_grouped:
            for elem_code, elem_warns in element_warnings_grouped.items():
                elem_name = next(
                    (e["name"] for e in valid_elements if e["code"] == elem_code),
                    elem_code,
                )
                lines.append(f"\n  {elem_name}:")
                for w in elem_warns:
                    icon = (
                        "🔴"
                        if w.get("severity") == "error"
                        else "⚠️"
                        if w.get("severity") == "warning"
                        else "ℹ️"
                    )
                    lines.append(f"    {icon} {w['message']}")
        general_warnings = [w for w in result["warnings"] if not w.get("element_code")]
        if general_warnings:
            if element_warnings_grouped:
                lines.append("\n  General:")
            for w in general_warnings:
                icon = (
                    "🔴"
                    if w.get("severity") == "error"
                    else "⚠️"
                    if w.get("severity") == "warning"
                    else "ℹ️"
                )
                prefix = "    " if element_warnings_grouped else "  "
                lines.append(f"{prefix}{icon} {w['message']}")
        lines.append("")

    validation_result = result.get("element_validation", {})
    if not validation_result.get("valid", True) and validation_result.get(
        "missing_elements"
    ):
        lines += ["", "⚠️ ADVERTENCIA - ELEMENTOS NO INCLUIDOS EN TARIFA:"]
        for code in validation_result["missing_elements"]:
            lines.append(f"  • {code}")
        lines += [
            "",
            "Estos elementos pueden requerir tarifa adicional o",
            "una combinación diferente de elementos.",
            "",
        ]

    if result.get("additional_services"):
        lines.append("Servicios adicionales disponibles:")
        for s in result["additional_services"][:3]:
            lines.append(f"- {s['name']}: {s['price']} EUR")
        if len(result.get("additional_services", [])) > 3:
            lines.append(f"  ... y {len(result['additional_services']) - 3} mas")
        lines.append("")

    lines += ["DOCUMENTACION REQUERIDA:", ""]
    if base_documentation:
        lines.append("Documentacion base obligatoria:")
        for doc in base_documentation:
            lines.append(f"  - {doc['descripcion']}")
        lines.append("")
    if element_documentation:
        lines.append("Documentacion por elemento:")
        for elem_doc in element_documentation:
            if elem_doc["imagenes"]:
                lines.append(f"  {elem_doc['nombre']}:")
                for img in elem_doc["imagenes"]:
                    desc = (
                        img.get("descripcion")
                        or img.get("titulo")
                        or "Foto del elemento"
                    )
                    lines.append(f"    - (Guía interna, reformula en lenguaje sencillo) {desc}")
            else:
                lines.append(
                    f"  {elem_doc['nombre']}: Foto del elemento con matricula visible"
                )
        lines.append("")

    user_instructions = []
    for elem_doc in element_documentation:
        for img in elem_doc.get("imagenes", []):
            if img.get("requerida") and img.get("instruccion_usuario"):
                user_instructions.append(
                    {
                        "elemento": elem_doc["nombre"],
                        "instruccion": img["instruccion_usuario"],
                    }
                )
    if user_instructions:
        lines.append(
            "INSTRUCCIONES PARA EL USUARIO (datos oficiales de la DB, NO inventes):"
        )
        for instr in user_instructions:
            lines.append(f"  [{instr['elemento']}]: {instr['instruccion']}")
        lines += [
            "",
            "Cuando el usuario pregunte que fotos necesita, usa EXACTAMENTE estas instrucciones.",
            "",
        ]

    active_images = [
        img for img in (base_images + element_images) if img.get("status") == "active"
    ]
    active_base_images = [img for img in base_images if img.get("status") == "active"]
    active_element_images = [
        img for img in element_images if img.get("status") == "active"
    ]
    elements_without_images = [
        elem_doc["nombre"]
        for elem_doc in element_documentation
        if not [
            img for img in elem_doc.get("imagenes", []) if img.get("status") == "active"
        ]
    ]

    if active_images:
        lines.append(
            f"IMAGENES DE EJEMPLO DISPONIBLES: {len(active_images)}"
        )
        lines.append(f"  - Base (ficha técnica, permiso): {len(active_base_images)}")
        lines.append(f"  - Elementos específicos: {len(active_element_images)}")
        lines.append(
            "INSTRUCCIÓN: Si el usuario PIDIÓ VER FOTOS → llama "
            "enviar_imagenes_ejemplo(tipo='presupuesto') en este mismo turno. "
            "Tu ai_response DEBE incluir el precio (ej: 'El presupuesto es de X€ +IVA') "
            "porque el usuario NO lo ha visto aún. "
            "Si el usuario pidió PRESUPUESTO o no pidió fotos → comunica el precio "
            "y ofrece: '¿Quieres ver fotos de ejemplo (A) o abrimos el expediente (B)?'"
        )
        if elements_without_images:
            lines.append("")
            lines.append(
                f"⚠️ ELEMENTOS SIN IMAGENES DE EJEMPLO: {', '.join(elements_without_images)}"
            )
            lines.append(
                "  Para estos elementos, describe la documentación requerida sin prometer fotos de ejemplo."
            )
        lines.append("")
    elif base_images or element_images:
        lines += [
            "IMAGENES DE EJEMPLO: No disponibles en este momento (pendientes de configuracion).",
            "NO prometas imagenes al usuario. Describele la documentacion usando SOLO los datos de arriba.",
            "",
        ]

    text_response = "\n".join(lines)
    response = {
        "texto": text_response,
        "datos": {
            "tier_id": result["tier_id"],
            "tier_name": result["tier_name"],
            "price": float(result["price"]),
            "elements": [e["name"] for e in valid_elements],
            "element_codes": codigos_elementos,
            "warnings": [
                {
                    "message": w["message"],
                    "severity": w.get("severity", "info"),
                    "element_code": w.get("element_code"),
                    "element_name": w.get("element_name"),
                }
                for w in result.get("warnings", [])
            ],
        },
        "_documentacion": {
            "base": base_documentation,
            "elementos": element_documentation,
        },
        "imagenes_ejemplo": base_images + element_images,
        "_state_update": {
            "shared_context": {
                # precio_comunicado NOT set here — the tariff is calculated but
                # the LLM hasn't told the user yet. The LLM must include the price
                # in its response. precio_comunicado=True is set by the mode node
                # AFTER the LLM generates a response that exits the tool loop.
                # T-06: imagenes_enviadas NOT reset — delta filtering handles new elements.
            },
        },
    }

    # Fire-and-forget DraftQuote write
    state_for_draft = get_tool_state(config)
    conv_id_for_draft = state_for_draft.get("conversation_id")
    if conv_id_for_draft:
        await _fire_and_forget_draft_quote(
            conversation_id=str(conv_id_for_draft),
            category_slug=categoria_vehiculo,
            elements=list(codigos_elementos),
            tier_id=str(result.get("tier_id")) if result.get("tier_id") else None,
            precio_final=result["price"],
        )

    return response


async def _fire_and_forget_draft_quote(
    conversation_id: str,
    category_slug: str,
    elements: list[str],
    tier_id: str | None,
    precio_final: Any,
) -> None:
    """Write a DraftQuote to DB. Catches ALL exceptions so errors never propagate."""
    from decimal import Decimal as _Decimal
    from database.connection import get_async_session
    from agent.tools.draft_quote_service import _upsert_draft_quote

    try:
        price = _Decimal(str(precio_final))
        async with get_async_session() as session:
            await _upsert_draft_quote(
                session=session,
                conversation_id=conversation_id,
                category_slug=category_slug,
                elements=elements,
                tier_id=tier_id,
                precio_final=price,
            )
            await session.commit()
    except Exception as exc:
        logger.warning(
            "draft_quote_write_failed", conversation_id=conversation_id, error=str(exc)
        )


@tool(args_schema=ObtenerDocumentacionElementoInput)
async def obtener_documentacion_elemento(
    categoria_vehiculo: str,
    codigo_elemento: str,
) -> dict[str, Any]:
    """
    Obtiene la documentación necesaria para homologar un elemento específico (sin URLs de imágenes).

    Usa esta herramienta cuando el usuario pregunte qué fotos o documentos necesita
    para homologar un elemento concreto. Las imágenes de ejemplo se envían por separado
    vía enviar_imagenes_ejemplo después de calcular el presupuesto.

    Args:
        categoria_vehiculo: Slug de la categoría (ej: "motos-part", "aseicars-prof")
        codigo_elemento: Código del elemento (ej: "ESCAPE", "ESC_MEC")

    Returns:
        Dictionary with:
        - "texto": Text description of required documentation
    """
    categoria_vehiculo = categoria_vehiculo.lower().strip()
    try:
        validate_category_slug(categoria_vehiculo)
    except ValueError as e:
        logger.error("obtener_documentacion_invalid_slug", error=str(e))
        return {"texto": f"Error: {str(e)}"}

    element_service = get_element_service()

    category_id = await get_or_fetch_category_id(categoria_vehiculo)
    if not category_id:
        return {
            "texto": f"Categoría '{categoria_vehiculo}' no encontrada.",
        }

    elements = await element_service.get_elements_by_category(
        category_id, is_active=True
    )
    element_by_code = {e["code"]: e for e in elements}

    code_upper = codigo_elemento.upper()
    if code_upper not in element_by_code:
        available_codes = ", ".join(sorted(element_by_code.keys()))
        return {
            "texto": f"Elemento '{codigo_elemento}' no encontrado.\nCódigos válidos: {available_codes}",
        }

    element = element_by_code[code_upper]
    element_details = await element_service.get_element_with_images(element["id"])
    if not element_details:
        return {
            "texto": f"No se encontró información para el elemento {code_upper}.",
        }

    lines = [
        f"DOCUMENTACION PARA {element_details['name'].upper()} ({code_upper}):",
        "",
    ]

    if element_details.get("images"):
        required_docs = [
            img for img in element_details["images"] if img.get("is_required")
        ]
        example_docs = [
            img for img in element_details["images"] if not img.get("is_required")
        ]

        if required_docs:
            lines.append("Documentos requeridos:")
            for doc in required_docs:
                lines.append(f"- {doc['title']}")
                if doc.get("description"):
                    lines.append(f"  {doc['description']}")
            lines.append("")
        if example_docs:
            lines.append("Fotos de ejemplo:")
            for doc in example_docs:
                lines.append(f"- {doc['title']}")
                if doc.get("description"):
                    lines.append(f"  {doc['description']}")
            lines.append("")
    else:
        lines += [
            "No hay documentacion especifica configurada para este elemento.",
            "Documentacion general requerida:",
            "- Foto del elemento con matricula visible",
            "- Certificado o placa del fabricante (si aplica)",
        ]

    warnings = await element_service.get_element_warnings(element["id"])
    if warnings:
        lines.append("")
        lines.append("ADVERTENCIAS:")
        for w in warnings:
            lines.append(f"- {w['message']}")

    tarifa_service = get_tarifa_service()
    category_data = await tarifa_service.get_category_data(categoria_vehiculo)
    if category_data and category_data.get("base_documentation"):
        lines.append("")
        lines.append("Documentacion base obligatoria:")
        for base_doc in category_data["base_documentation"]:
            lines.append(f"- {base_doc['description']}")

    return {"texto": "\n".join(lines)}


@tool(args_schema=IdentificarYResolverElementosInput)
async def identificar_y_resolver_elementos(
    categoria_vehiculo: str,
    descripcion: str,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """
    Identifica elementos Y detecta variantes en UNA sola llamada.

    Esta herramienta CONSOLIDA las funciones de:
    - identificar_elementos()
    - verificar_si_tiene_variantes() para cada elemento

    Usa esta herramienta como PRIMER PASO cuando el usuario describe qué quiere homologar.
    Es más eficiente que llamar a identificar_elementos + verificar_si_tiene_variantes por separado.

    IMPORTANTE: Usa el slug de categoría correcto según el tipo de cliente:
    - "motos-part" para motocicletas de PARTICULARES
    - "motos-prof" para motocicletas de PROFESIONALES (si existe)
    - "aseicars-part" para autocaravanas de PARTICULARES
    - "aseicars-prof" para autocaravanas de PROFESIONALES

    El sufijo DEBE coincidir con el client_type del estado:
    - client_type="particular" → usa "-part"
    - client_type="professional" → usa "-prof"

    Args:
        categoria_vehiculo: Slug de la categoría (ej: "motos-part", "aseicars-prof")
        descripcion: Descripción del usuario con elementos a homologar.
                    Ejemplo: "quiero homologar el escape y el manillar"

    Returns:
        JSON con:
        - elementos_listos: elementos SIN variantes (listos para calcular tarifa)
        - elementos_con_variantes: elementos QUE REQUIEREN clarificación del usuario
        - preguntas_variantes: preguntas a hacer al usuario para resolver variantes
        - terminos_no_reconocidos: términos que no coincidieron con ningún elemento

    Flujo simplificado:
    1. Llama a identificar_y_resolver_elementos()
       → Si hay elementos_con_variantes: pregunta al usuario y espera respuesta
       → Si todos están listos: llama a calcular_tarifa_con_elementos()
    2. Cuando el usuario responde sobre una variante:
       → Usa seleccionar_variante_por_respuesta() (NO vuelvas a llamar identificar_y_resolver_elementos)
    3. Una vez resueltas todas las variantes:
       → Llama a calcular_tarifa_con_elementos() con skip_validation=True
    """
    categoria_vehiculo = categoria_vehiculo.lower().strip()

    # Category/client_type cross-check
    state = get_tool_state(config)
    client_type = state.get("client_type", "particular")
    expected_suffix = "-part" if client_type == "particular" else "-prof"
    opposite_suffix = "-prof" if client_type == "particular" else "-part"

    if categoria_vehiculo.endswith(opposite_suffix):
        corrected_slug = categoria_vehiculo.replace(opposite_suffix, expected_suffix)
        corrected_id = await get_or_fetch_category_id(corrected_slug)
        logger.warning(
            "category_client_type_mismatch",
            categoria_recibida=categoria_vehiculo,
            client_type=client_type,
            corrected_slug=corrected_slug if corrected_id else None,
        )
        if corrected_id:
            return {
                "error": f"CATEGORÍA INCORRECTA: El cliente es '{client_type}', debes usar '{corrected_slug}' en lugar de '{categoria_vehiculo}'.",
                "categoria_correcta": corrected_slug,
                "accion_requerida": f"Vuelve a llamar esta herramienta con categoria_vehiculo='{corrected_slug}'",
                "elementos_listos": [],
                "elementos_con_variantes": [],
                "_state_update": {
                    "shared_context": {
                        "precio_comunicado": False,
                        "imagenes_enviadas": False,
                        "imagenes_enviadas_codigos": [],  # T-05: dual-write reset
                    },
                },
            }

    try:
        validate_category_slug(categoria_vehiculo)
    except ValueError as e:
        logger.error("identificar_invalid_slug", error=str(e))
        return {"error": str(e), "elementos_listos": [], "elementos_con_variantes": []}

    element_service = get_element_service()
    tarifa_service = get_tarifa_service()

    category_id = await get_or_fetch_category_id(categoria_vehiculo)
    if not category_id:
        try:
            raw_categories = await tarifa_service.get_active_categories(
                client_type=client_type
            )
            available_categories = [
                {"slug": c["slug"], "name": c["name"]} for c in raw_categories
            ]
        except Exception as _cat_err:
            logger.warning("get_active_categories_failed", error=str(_cat_err))
            available_categories = []
        return {
            "error": "category_not_found",
            "categoria_usada": categoria_vehiculo,
            "available_categories": available_categories,
            "sugerencia": "Usa listar_categorias() para ver todas las opciones disponibles o elige una de available_categories.",
            "elementos_listos": [],
            "elementos_con_variantes": [],
        }

    elements = await element_service.get_elements_by_category(
        category_id, is_active=True
    )
    if not elements:
        return {
            "error": f"No hay elementos configurados para la categoría '{categoria_vehiculo}'",
            "elementos_listos": [],
            "elementos_con_variantes": [],
        }

    identified_result = await element_service.match_elements_with_unmatched(
        description=descripcion,
        category_id=category_id,
        only_base_elements=True,
    )
    matches = identified_result.get("matches", [])
    matched_elements = [elem_dict for elem_dict, _confidence in matches]
    unmatched_terms = identified_result.get("unmatched_terms", [])
    ambiguous_candidates = identified_result.get("ambiguous_candidates", [])
    quantities = identified_result.get("quantities", {})

    logger.info(
        "identificar_elementos_result",
        category=categoria_vehiculo,
        matched_count=len(matched_elements),
        unmatched_terms=unmatched_terms,
    )

    elementos_listos = []
    elementos_con_variantes = []
    preguntas_variantes = []

    valid_elements = [e for e in matched_elements if e.get("code")]

    variant_coros = [
        element_service.get_element_variants(
            element_code=e["code"], category_id=category_id
        )
        for e in valid_elements
    ]
    variant_results = (
        await asyncio.gather(*variant_coros, return_exceptions=True)
        if variant_coros
        else []
    )

    elements_with_variants = []
    for elem, variants in zip(valid_elements, variant_results):
        if isinstance(variants, Exception):
            logger.warning(
                "variant_fetch_failed", code=elem["code"], error=str(variants)
            )
            elementos_listos.append(
                {
                    "codigo": elem["code"],
                    "nombre": elem.get("name"),
                    "cantidad": quantities.get(elem["code"], 1),
                }
            )
        elif variants:
            elements_with_variants.append((elem, variants))
        else:
            elementos_listos.append(
                {
                    "codigo": elem["code"],
                    "nombre": elem.get("name"),
                    "cantidad": quantities.get(elem["code"], 1),
                }
            )

    if elements_with_variants:
        base_coros = [
            element_service.get_element_by_code(
                element_code=elem["code"], category_id=category_id
            )
            for elem, _ in elements_with_variants
        ]
        base_results = await asyncio.gather(*base_coros, return_exceptions=True)

        for (elem, variants), base_element in zip(elements_with_variants, base_results):
            if isinstance(base_element, Exception):
                logger.warning("base_element_fetch_failed", code=elem["code"])
                base_element = None

            question_hint = (
                base_element.get("question_hint")
                if base_element and base_element.get("question_hint")
                else f"¿Qué tipo de {elem.get('name', elem['code']).lower()}?"
            )
            elementos_con_variantes.append(
                {
                    "codigo_base": elem["code"],
                    "nombre": elem.get("name"),
                    "variantes": [
                        {"codigo": v["code"], "nombre": v["name"]} for v in variants
                    ],
                }
            )
            preguntas_variantes.append(
                {
                    "codigo_base": elem["code"],
                    "pregunta": question_hint,
                    "opciones": [
                        f"{chr(64 + v['variant_position'])} - {v['name']}"
                        if v.get("variant_position") is not None
                        else v["name"]
                        for v in variants
                    ],
                }
            )

    # ── Documentation enrichment (T-05) ──────────────────────────────────────
    # Build per-element documentacion dict when all elements are ready.
    # When variants are pending we can't show docs — emit empty dict.
    documentacion: dict[str, dict[str, Any]] = {}
    if elementos_listos and not elementos_con_variantes:
        # Build code → element mapping from valid_elements (already fetched above)
        element_by_code: dict[str, dict[str, Any]] = {
            e["code"]: e for e in valid_elements
        }

        # Parallel: fetch images + warnings for each ready element
        listos_codes = [e["codigo"] for e in elementos_listos if e.get("codigo")]
        doc_image_coros = []
        doc_warning_coros = []
        for code in listos_codes:
            elem = element_by_code.get(code)
            if elem and elem.get("id"):
                doc_image_coros.append(
                    element_service.get_element_with_images(str(elem["id"]))
                )
                doc_warning_coros.append(
                    element_service.get_element_warnings(str(elem["id"]))
                )
            else:
                doc_image_coros.append(_noop_coro(None))
                doc_warning_coros.append(_noop_coro([]))

        image_results, warning_results = await asyncio.gather(
            asyncio.gather(*doc_image_coros, return_exceptions=True),
            asyncio.gather(*doc_warning_coros, return_exceptions=True),
        ) if doc_image_coros else ([], [])

        for code, img_data, warn_data in zip(listos_codes, image_results, warning_results):
            if isinstance(img_data, Exception):
                logger.warning("doc_enrich_images_failed", code=code, error=str(img_data))
                img_data = None
            if isinstance(warn_data, Exception):
                logger.warning("doc_enrich_warnings_failed", code=code, error=str(warn_data))
                warn_data = []

            docs_requeridos: list[str] = []
            active_images = []
            if img_data and isinstance(img_data, dict):
                for img in (img_data.get("images") or []):
                    if img.get("is_required"):
                        doc_text = img.get("title", "")
                        if img.get("description"):
                            doc_text += f" — {img['description']}"
                        docs_requeridos.append(doc_text)
                active_images = [
                    img for img in (img_data.get("images") or [])
                    if img.get("status", "placeholder") == "active"
                ]

            advertencias = []
            if warn_data and isinstance(warn_data, list):
                advertencias = [w["message"] for w in warn_data if w.get("message")]

            documentacion[code] = {
                "docs_requeridos": docs_requeridos or ["Foto del elemento con matrícula visible"],
                "advertencias": advertencias,
                "num_imagenes_ejemplo": len(active_images),
            }

    # Fetch base documentation for the category (common to all homologations)
    documentacion_base: list[str] = []
    if elementos_listos and not elementos_con_variantes:
        tarifa_svc = get_tarifa_service()
        category_data = await tarifa_svc.get_category_data(categoria_vehiculo)
        if category_data and category_data.get("base_documentation"):
            documentacion_base = [
                doc["description"] for doc in category_data["base_documentation"]
                if doc.get("description")
            ]

    # Filter documentacion_base when adding to existing elements (already shown)
    existing_codes = state.get("mode_context", {}).get("element_codes", [])
    include_base_docs = not existing_codes  # Only include on first identification

    response: dict[str, Any] = {
        "elementos_listos": elementos_listos,
        "elementos_con_variantes": elementos_con_variantes,
        "preguntas_variantes": preguntas_variantes,
        "terminos_no_reconocidos": unmatched_terms,
        "categoria_slug": categoria_vehiculo,
        "documentacion": documentacion,
    }
    if include_base_docs:
        response["documentacion_base"] = documentacion_base

    # Embedded instructions removed — system prompt handles routing.
    # Tool results return DATA only, not competing instructions.
    # Variant-only hint kept minimal (no routing instructions).
    if elementos_con_variantes:
        response["tiene_variantes_pendientes"] = True

    if ambiguous_candidates and len(ambiguous_candidates) > 1:
        response["ambiguedad"] = {
            "mensaje": "Múltiples elementos tienen puntuación similar. Pregunta al usuario cuál necesita.",
            "candidatos": [c["name"] for c in ambiguous_candidates],
        }

    # Reset pricing/image state on re-identification (REFACTOR-001)
    # Cross-mode keys go into shared_context; mode-private keys stay flat.
    response["_state_update"] = {
        "shared_context": {
            "precio_comunicado": False,
            "imagenes_enviadas": False,
            "imagenes_enviadas_codigos": [],  # T-05: dual-write reset
        },
        "imagenes_envio_intent_creado": False,  # mode-private key stays flat
    }

    response_json = json.dumps(response, ensure_ascii=False, indent=2)
    logger.info(
        "identificar_elementos_final",
        category=categoria_vehiculo,
        listos=len(elementos_listos),
        con_variantes=len(elementos_con_variantes),
        response_preview=response_json[:500]
        if len(response_json) > 500
        else response_json,
    )

    return response


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

ELEMENT_TOOLS = [
    listar_elementos,
    identificar_y_resolver_elementos,
    seleccionar_variante_por_respuesta,
    calcular_tarifa_con_elementos,
    obtener_documentacion_elemento,
]


def get_element_tools() -> list:
    """Get all element-related tools for the agent."""
    return ELEMENT_TOOLS


__all__ = [
    "listar_elementos",
    "identificar_y_resolver_elementos",
    "seleccionar_variante_por_respuesta",
    "calcular_tarifa_con_elementos",
    "obtener_documentacion_elemento",
    "get_element_tools",
    "ELEMENT_TOOLS",
    # Re-exports for backward-compatible imports
    "get_or_fetch_category_id",
    "normalize_element_code",
    "normalize_element_codes",
]
