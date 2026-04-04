"""
Variant Interpretation Service.

Interprets user responses to variant questions for multi-element quantity allocation.
Uses LLM extraction (local-first with cloud escalation) to parse natural language
responses like "2 delanteras y 1 trasera" into structured allocations.

This service is self-contained — it does not import from tools or modes.
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog
from pydantic import BaseModel, Field, field_validator

from agent.state.conversation_state import PendingVariantGroup, VariantResolution
from shared.config import get_settings
from shared.llm_router import LLMResponse, ModelTier, TaskType, get_llm_router

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Pydantic Response Schemas (Task 2.2)
# ---------------------------------------------------------------------------


class VariantAllocation(BaseModel):
    """A single allocation of quantity to a specific variant option."""

    variant_code: str = Field(
        ...,
        description="Must match one of the option codes/labels from the variant question.",
    )
    quantity: int = Field(
        ...,
        ge=1,
        description="How many units are assigned to this variant.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in this allocation (0.0 = guess, 1.0 = certain).",
    )
    position: int | None = Field(
        None,
        ge=1,
        le=5,
        description=(
            "Ordinal position (1=A, 2=B…5=E) if user gave a positional reference. "
            "When set, DB lookup prefers variant_position over code string match."
        ),
    )


class VariantInterpretationResult(BaseModel):
    """Result of interpreting a user's variant allocation response."""

    allocations: list[VariantAllocation] = Field(default_factory=list)
    needs_clarification: bool = Field(
        False,
        description="True if the user's response could not be reliably interpreted.",
    )
    clarification_reason: str | None = Field(
        None,
        description="Human-readable reason why clarification is needed (in Spanish).",
    )
    raw_response: str | None = Field(
        None,
        description="Raw LLM response for debugging purposes.",
    )

    @field_validator("allocations")
    @classmethod
    def allocations_must_have_items_unless_clarification(
        cls,
        v: list[VariantAllocation],
        info: Any,
    ) -> list[VariantAllocation]:
        """Allow empty allocations only when clarification is needed."""
        # info.data may not have 'needs_clarification' yet during construction,
        # so we validate at the model level instead.
        return v


# ---------------------------------------------------------------------------
# Extraction Prompt (Generic — no hardcoded element names)
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT = """Eres un extractor de datos. El usuario está respondiendo a una pregunta sobre variantes de un elemento de homologación vehicular.

PREGUNTA QUE SE LE HIZO:
{pregunta}

OPCIONES DISPONIBLES:
{opciones_formatted}

CANTIDAD TOTAL A ASIGNAR: {cantidad_pendiente}
{context_section}
RESPUESTA DEL USUARIO:
"{user_message}"

INSTRUCCIONES:
1. Interpreta la respuesta del usuario y determina cuántas unidades asigna a cada opción.
2. La suma de las cantidades DEBE ser exactamente {cantidad_pendiente}.
3. Si el usuario solo menciona UNA opción sin cantidad, asigna TODAS las {cantidad_pendiente} unidades a esa opción.
4. Si el usuario da cantidades parciales que no suman {cantidad_pendiente}, marca confidence baja.
5. Si la respuesta es ambigua o no se puede interpretar, indica que se necesita aclaración.

Responde SOLO con JSON (sin markdown, sin ```):
{{"allocations": [{{"variant_code": "nombre_opcion", "quantity": N, "confidence": 0.0-1.0}}], "needs_clarification": false, "clarification_reason": null}}

Si necesitas aclaración:
{{"allocations": [], "needs_clarification": true, "clarification_reason": "razón en español"}}"""


# ---------------------------------------------------------------------------
# Core Service Functions (Tasks 2.1, 2.3, 2.4)
# ---------------------------------------------------------------------------


async def interpret_variant_allocations(
    user_message: str,
    pending_variant: PendingVariantGroup,
    conversation_context: str | None = None,
) -> VariantInterpretationResult:
    """
    Interpret a user's natural language response to a variant question.

    Strategy:
    1. Try local extraction (TaskType.EXTRACTION → Tier 1 fast).
    2. If confidence < 0.6 OR parse/validation fails → escalate to cloud.
    3. If cloud also fails → return needs_clarification=True.

    Never loops more than once: local → cloud → clarification.

    Args:
        user_message: The user's raw message text.
        pending_variant: The pending variant group being resolved.
        conversation_context: Optional recent conversation context for disambiguation.

    Returns:
        VariantInterpretationResult with allocations or clarification request.
    """
    settings = get_settings()
    codigo_base = pending_variant.get("codigo_base", "UNKNOWN")
    cantidad_pendiente = pending_variant.get("cantidad_pendiente", 1)

    if not settings.ENABLE_LLM_VARIANT_INTERPRETATION:
        reason = "Interpretación automática de variantes desactivada por configuración"
        logger.info(
            "variant_interpretation_clarification_needed",
            element=codigo_base,
            reason=reason,
        )
        return VariantInterpretationResult(
            allocations=[],
            needs_clarification=True,
            clarification_reason=reason,
            raw_response=None,
        )

    router = get_llm_router()
    prompt = _build_extraction_prompt(user_message, pending_variant, conversation_context)

    messages = [{"role": "user", "content": prompt}]

    # --- Step 1: Local extraction (Tier 1 fast) ---
    logger.info(
        "variant_interpretation_started",
        element=codigo_base,
        quantity=cantidad_pendiente,
        local_cloud="local",
    )

    local_response = await router.invoke(
        task_type=TaskType.EXTRACTION,
        messages=messages,
        temperature=0.1,
        max_tokens=500,
    )

    if local_response.success:
        result = _parse_llm_response(local_response, pending_variant)
        if result is not None and not result.needs_clarification:
            # Validate allocations against pending state
            _, errors = validate_and_apply_allocations(
                pending_variant,
                result.allocations,
                dry_run=True,
            )
            avg_confidence = _average_confidence(result.allocations)

            if not errors and avg_confidence >= 0.6:
                logger.info(
                    "variant_interpretation_local_success",
                    codigo_base=codigo_base,
                    allocations_count=len(result.allocations),
                    avg_confidence=round(avg_confidence, 2),
                    tier=local_response.tier.value,
                )
                logger.info(
                    "variant_interpretation_completed",
                    element=codigo_base,
                    allocations_count=len(result.allocations),
                    confidence_avg=round(avg_confidence, 2),
                    turns_to_complete=1,
                )
                return result

            # Low confidence or validation errors → escalate
            escalation_reason = (
                f"validation_errors={errors}" if errors
                else f"low_confidence={avg_confidence:.2f}"
            )
            logger.info(
                "variant_interpretation_escalated",
                element=codigo_base,
                reason=escalation_reason,
                from_tier=local_response.tier.value,
                to_tier=ModelTier.CLOUD_STANDARD.value,
            )
        elif result is not None and result.needs_clarification:
            # Local LLM explicitly says it needs clarification — still try cloud
            logger.info(
                "variant_interpretation_local_needs_clarification",
                codigo_base=codigo_base,
                reason=result.clarification_reason,
            )
        else:
            logger.warning(
                "variant_interpretation_local_parse_failed",
                codigo_base=codigo_base,
                raw_content=local_response.content[:200],
            )
    else:
        logger.warning(
            "variant_interpretation_local_call_failed",
            codigo_base=codigo_base,
            error=local_response.error,
        )

    # --- Step 2: Cloud escalation (Tier 3) ---
    logger.info(
        "variant_interpretation_started",
        element=codigo_base,
        quantity=cantidad_pendiente,
        local_cloud="cloud",
    )

    cloud_response = await router.invoke(
        task_type=TaskType.EXTRACTION,
        messages=messages,
        temperature=0.1,
        max_tokens=500,
        force_tier=ModelTier.CLOUD_STANDARD,
    )

    if cloud_response.success:
        result = _parse_llm_response(cloud_response, pending_variant)
        if result is not None and not result.needs_clarification:
            _, errors = validate_and_apply_allocations(
                pending_variant,
                result.allocations,
                dry_run=True,
            )
            if not errors:
                avg_confidence = _average_confidence(result.allocations)
                if avg_confidence < 0.6:
                    logger.warning(
                        "variant_interpretation_cloud_low_confidence",
                        codigo_base=codigo_base,
                        avg_confidence=round(avg_confidence, 2),
                        tier=cloud_response.tier.value,
                    )
                    return VariantInterpretationResult(
                        allocations=[],
                        needs_clarification=True,
                        clarification_reason=(
                            "La interpretación automática no tiene suficiente "
                            "certeza. Pregunta al usuario de forma más específica."
                        ),
                        raw_response=cloud_response.content,
                    )
                logger.info(
                    "variant_interpretation_cloud_success",
                    codigo_base=codigo_base,
                    allocations_count=len(result.allocations),
                    avg_confidence=round(avg_confidence, 2),
                    tier=cloud_response.tier.value,
                )
                logger.info(
                    "variant_interpretation_completed",
                    element=codigo_base,
                    allocations_count=len(result.allocations),
                    confidence_avg=round(avg_confidence, 2),
                    turns_to_complete=2,
                )
                return result

            logger.warning(
                "variant_interpretation_cloud_validation_failed",
                codigo_base=codigo_base,
                errors=errors,
            )
        elif result is not None and result.needs_clarification:
            reason = result.clarification_reason or "LLM requested clarification"
            logger.info(
                "variant_interpretation_clarification_needed",
                element=codigo_base,
                reason=reason,
            )
            return result

    # --- Step 3: Give up → clarification ---
    final_reason = (
        "No he podido interpretar tu respuesta. "
        "Por favor, indica cuántas unidades quieres de cada opción "
        f"({', '.join(pending_variant.get('opciones', []))})."
    )
    logger.info(
        "variant_interpretation_clarification_needed",
        element=codigo_base,
        reason=final_reason,
    )
    logger.warning(
        "variant_interpretation_failed_needs_clarification",
        codigo_base=codigo_base,
        user_message=user_message[:100],
    )

    return VariantInterpretationResult(
        allocations=[],
        needs_clarification=True,
        clarification_reason=final_reason,
        raw_response=cloud_response.content if cloud_response.success else None,
    )


def validate_and_apply_allocations(
    pending: PendingVariantGroup,
    allocations: list[VariantAllocation],
    *,
    dry_run: bool = False,
    option_to_code_map: dict[str, str] | None = None,
) -> tuple[PendingVariantGroup, list[str]]:
    """
    Validate allocations against pending state and optionally apply them.

    Validation rules:
    - Sum of allocation quantities must equal cantidad_pendiente.
    - Each variant_code must match an option in pending.opciones (fuzzy).
    - No duplicate variant_codes.

    If valid and dry_run=False:
    - Append to resoluciones.
    - Recalculate cantidad_resuelta, cantidad_pendiente, status.

    If invalid: return errors and do NOT modify pending state.

    Args:
        pending: The pending variant group to validate against.
        allocations: List of allocations to validate/apply.
        dry_run: If True, only validate without modifying pending.
        option_to_code_map: Maps option text to element code for storage.

    Returns:
        Tuple of (updated_or_original pending group, list of error strings).
    """
    errors: list[str] = []
    cantidad_pendiente = pending.get("cantidad_pendiente", 1)
    opciones = pending.get("opciones", [])

    if not allocations:
        errors.append("No allocations provided.")
        return pending, errors

    # Check for duplicate variant_codes
    codes_seen: set[str] = set()
    for alloc in allocations:
        code_lower = alloc.variant_code.lower().strip()
        if code_lower in codes_seen:
            errors.append(f"Duplicate variant_code: '{alloc.variant_code}'.")
        codes_seen.add(code_lower)

    # Validate each allocation against opciones
    resolved_codes: list[tuple[VariantAllocation, str]] = []
    for alloc in allocations:
        matched_option = _fuzzy_match_option(alloc.variant_code, opciones)
        if matched_option is None:
            errors.append(
                f"variant_code '{alloc.variant_code}' does not match any option: {opciones}."
            )
        else:
            resolved_codes.append((alloc, matched_option))

    # Validate quantity sum
    total_allocated = sum(a.quantity for a in allocations)
    allow_sequential_single_unit = (
        total_allocated < cantidad_pendiente
        and len(allocations) == 1
        and allocations[0].quantity == 1
    )

    if total_allocated != cantidad_pendiente and not allow_sequential_single_unit:
        errors.append(
            f"Sum of quantities ({total_allocated}) != cantidad_pendiente ({cantidad_pendiente})."
        )

    if errors:
        return pending, errors

    # --- Apply allocations ---
    if dry_run:
        return pending, []

    # Build updated pending group (immutable pattern — return new dict)
    existing_resoluciones: list[VariantResolution] = list(
        pending.get("resoluciones", [])
    )
    for alloc, matched_option in resolved_codes:
        stored_code = matched_option
        if option_to_code_map:
            stored_code = option_to_code_map.get(matched_option, matched_option)
        existing_resoluciones.append(
            VariantResolution(
                variant_code=stored_code,
                quantity=alloc.quantity,
                confidence=alloc.confidence,
                source="user_explicit",
            )
        )

    nueva_resuelta = pending.get("cantidad_resuelta", 0) + total_allocated
    nueva_total = pending.get("cantidad_total", 1)
    nueva_pendiente = nueva_total - nueva_resuelta

    if nueva_resuelta >= nueva_total:
        new_status = "resolved"
    elif nueva_resuelta > 0:
        new_status = "partial"
    else:
        new_status = "pending"

    updated = PendingVariantGroup(
        pending_id=pending.get("pending_id", "UNKNOWN"),
        codigo_base=pending.get("codigo_base", "UNKNOWN"),
        pregunta=pending.get("pregunta", ""),
        opciones=opciones,
        cantidad_total=nueva_total,
        cantidad_resuelta=nueva_resuelta,
        cantidad_pendiente=nueva_pendiente,
        resoluciones=existing_resoluciones,
        status=new_status,
    )

    logger.info(
        "variant_allocations_applied",
        pending_id=updated.get("pending_id"),
        codigo_base=updated.get("codigo_base"),
        cantidad_resuelta=nueva_resuelta,
        cantidad_pendiente=nueva_pendiente,
        status=new_status,
    )

    return updated, []


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------


def _build_extraction_prompt(
    user_message: str,
    pending_variant: PendingVariantGroup,
    conversation_context: str | None,
) -> str:
    """Build the extraction prompt from the pending variant state."""
    opciones = pending_variant.get("opciones", [])
    opciones_formatted = "\n".join(f"  - {opt}" for opt in opciones)

    context_section = ""
    if conversation_context:
        context_section = f"CONTEXTO DE LA CONVERSACIÓN:\n{conversation_context[:500]}\n\n"

    return _EXTRACTION_PROMPT.format(
        pregunta=pending_variant.get("pregunta", ""),
        opciones_formatted=opciones_formatted,
        cantidad_pendiente=pending_variant.get("cantidad_pendiente", 1),
        context_section=context_section,
        user_message=user_message,
    )


def _parse_llm_response(
    response: LLMResponse,
    pending_variant: PendingVariantGroup,
) -> VariantInterpretationResult | None:
    """
    Parse the LLM response into a VariantInterpretationResult.

    Handles common LLM output quirks: markdown fences, trailing commas, etc.

    Args:
        response: The raw LLM response.
        pending_variant: The pending variant (for context in error messages).

    Returns:
        Parsed result or None if parsing fails completely.
    """
    content = response.content.strip()

    # Strip markdown code fences if present
    if content.startswith("```"):
        lines = content.split("\n")
        # Remove first line (```json or ```) and last line (```)
        end_idx = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == "```":
                end_idx = i
                break
        content = "\n".join(lines[1:end_idx]).strip()
        # Remove optional "json" prefix on first line
        if content.startswith("json"):
            content = content[4:].strip()

    # Remove trailing commas before closing braces/brackets (common LLM mistake)
    content = re.sub(r",\s*([\]}])", r"\1", content)

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        logger.warning(
            "variant_interpretation_json_parse_failed",
            codigo_base=pending_variant.get("codigo_base"),
            error=str(e),
            raw_content=content[:300],
        )
        return None

    # Handle the case where LLM returns needs_clarification
    if data.get("needs_clarification"):
        return VariantInterpretationResult(
            allocations=[],
            needs_clarification=True,
            clarification_reason=data.get("clarification_reason"),
            raw_response=content,
        )

    # Parse allocations
    raw_allocations = data.get("allocations", [])
    if not isinstance(raw_allocations, list):
        logger.warning(
            "variant_interpretation_invalid_allocations_type",
            codigo_base=pending_variant.get("codigo_base"),
            type_received=type(raw_allocations).__name__,
        )
        return None

    # Guard: reject any allocation with quantity <= 0 before Pydantic construction.
    # This catches LLMs that return 0 or 0.0 for a variant they couldn't resolve
    # (a known failure pattern). Treat as parsing failure so the caller escalates
    # to cloud or requests clarification rather than silently accepting bad data.
    for raw_alloc in raw_allocations:
        if not isinstance(raw_alloc, dict):
            continue
        raw_qty = raw_alloc.get("quantity")
        try:
            qty_value = float(raw_qty) if raw_qty is not None else 0.0
        except (ValueError, TypeError):
            qty_value = 0.0
        if qty_value <= 0:
            logger.warning(
                "variant_allocation_invalid_quantity",
                codigo_base=pending_variant.get("codigo_base"),
                variant_code=raw_alloc.get("variant_code"),
                quantity=raw_qty,
                reason="quantity must be > 0; treating as parse failure",
            )
            return None

    try:
        allocations = [
            VariantAllocation(
                variant_code=str(a.get("variant_code", "")),
                quantity=int(a.get("quantity", 0)),
                confidence=float(a.get("confidence", 0.5)),
            )
            for a in raw_allocations
            if isinstance(a, dict)
        ]
    except (ValueError, TypeError) as e:
        logger.warning(
            "variant_interpretation_allocation_parse_error",
            codigo_base=pending_variant.get("codigo_base"),
            error=str(e),
        )
        return None

    if not allocations:
        return None

    return VariantInterpretationResult(
        allocations=allocations,
        needs_clarification=False,
        clarification_reason=None,
        raw_response=content,
    )


def _fuzzy_match_option(variant_code: str, opciones: list[str]) -> str | None:
    """
    Match a variant_code against the available options using fuzzy matching.

    Tries (in order):
    1. Exact match (case-insensitive).
    2. Substring containment (either direction).
    3. Normalized comparison (strip accents, lowercase).

    Args:
        variant_code: The code from the LLM allocation.
        opciones: Available option strings.

    Returns:
        The matched option string, or None if no match.
    """
    code_lower = variant_code.lower().strip()
    code_normalized = _normalize_text(code_lower)

    for opcion in opciones:
        opcion_lower = opcion.lower().strip()
        opcion_normalized = _normalize_text(opcion_lower)

        # Exact match
        if code_lower == opcion_lower or code_normalized == opcion_normalized:
            return opcion

        # Substring containment (either direction)
        if code_normalized in opcion_normalized or opcion_normalized in code_normalized:
            return opcion

    return None


def _normalize_text(text: str) -> str:
    """Strip accents and normalize text for comparison."""
    import unicodedata

    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def _average_confidence(allocations: list[VariantAllocation]) -> float:
    """Calculate the average confidence across allocations."""
    if not allocations:
        return 0.0
    return sum(a.confidence for a in allocations) / len(allocations)
