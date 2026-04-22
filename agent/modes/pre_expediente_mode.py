"""
MSI-a - PRE_EXPEDIENTE_MODE Node.

Merged mode: handles informational queries AND exact pricing.
Covers ~100% of pre-expediente traffic (formerly CONSULTA_MODE + PRESUPUESTO_MODE).

Flow:
    Discovery phase (no element_codes yet):
    1. User asks for info or describes what they want to homologate
    2. LLM can answer informational queries (listar_categorias, obtener_documentacion_elemento, etc.)
    3. LLM identifies elements, resolves variants
    4. Transitions to pricing phase automatically (element_codes now populated)

    Pricing phase (element_codes populated, price not yet communicated):
    5. LLM calculates exact price with calcular_tarifa_con_elementos
    6. LLM communicates PRICE + WARNINGS (mandatory before images)

    Post-price phase (precio_comunicado=True):
    7. LLM offers example images (enviar_imagenes_ejemplo)
    8. LLM offers to proceed to EXPEDIENTE_MODE via confirmar_presupuesto

Available tools (10-tool superset):
    - identificar_y_resolver_elementos (element identification + variant detection)
    - seleccionar_variante_por_respuesta (variant resolution)
    - calcular_tarifa_con_elementos (exact tariff calculation)
    - enviar_imagenes_ejemplo (example image sending — gated by tarifa_calculada)
    - confirmar_presupuesto (transition to EXPEDIENTE_MODE — gated by price)
    - listar_categorias (category listing)
    - listar_elementos (element listing)
    - obtener_servicios_adicionales (additional services info)
    - identificar_tipo_vehiculo (vehicle classification)
    - escalar_a_humano (universal escalation)
    NOTE: obtener_documentacion_elemento removed — doc info is now embedded in
          identificar_y_resolver_elementos response (documentacion key, Batch 2)

Dynamic tool filtering (4 gates, Gate 2 removed):
    Gate 1 (variant): unresolved pending_variants → [seleccionar, escalar] only
    Gate 5 (images): tarifa_calculada absent or has no imagenes_ejemplo → remove enviar_imagenes_ejemplo
    Gate 3 (confirmar): NOT (precio_comunicado=True AND tarifa_calculada non-None dict) → remove confirmar_presupuesto
    Gate 4 (calcular): element_codes empty → remove calcular_tarifa_con_elementos
    NOTE: Gate 2 (re-id) removed — additive identification is now supported

Architecture:
    Same LLM-driven loop as PresupuestoModeNode. The system prompt enforces
    the critical rule: PRICE BEFORE IMAGES.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, UTC
from typing import Any, cast

import structlog
from langchain_openai import ChatOpenAI

from langgraph.types import Command

from agent.modes.base_mode import BaseModeNode
from agent.state.conversation_state import ConversationState, create_empty_retry_state, transition_mode
from agent.prompts.loader import assemble_system_prompt
from agent.state.helpers import (
    format_messages_for_llm,
)
from agent.tools.image_tools import (
    clear_image_tools_state,
)
from agent.modes.tool_loop import build_mode_tool_loop, build_tail_loop, ModeLoopConfig
from agent.modes.post_tool_hooks import pre_expediente_post_tool_hook
from agent.prompts.kickoff_markers import is_kickoff_hallucination
from agent.prompts.ctas_catalog import CTAS
from shared.config import get_settings

logger = structlog.get_logger(__name__)

# Max tool call iterations per turn
MAX_TOOL_ITERATIONS = 10

# Minimum confidence score for variant selection to be accepted as context
VARIANT_CONFIDENCE_THRESHOLD: float = 0.7

# Canonical CTA 5 text (post-images call-to-action).
# Defined here as a constant so the enforcement function and tests share the same source of truth.
_CTA_5 = "¿Abrimos expediente o tienes alguna duda?"

# Semantic-equivalence matcher for CTA 5 — tolerates voseo/tuteo drift ("tenés"/"tienes")
# and spacing/casing variance. Matches at any position in the string so that a CTA emitted
# mid-body (with trailing text after it) is still detected and the tail discarded.
# Prevents duplicate-CTA emission when the LLM drifts to tuteo or appends filler after the CTA.
_CTA_5_EQUIVALENT_RE = re.compile(
    r"¿\s*Abrimos\s+expediente\s+o\s+(?:tenés|tienes)\s+alguna\s+duda\s*\?",
    re.IGNORECASE,
)

# L3 tariff-gate guardrail — strip premature CTAs and price-validity footer
# when the turn has no communicated price AND no stored tarifa. Defense-in-depth
# for the prompt-level <tariff_gate> rule in pre_expediente_pricing.md.
_PRICE_NUMERIC_RE = re.compile(r"\d[\d.\s]*€", re.IGNORECASE)

# F2: minimum length below which output guards short-circuit and return the
# original input. Prevents single-paragraph responses with a price keyword
# from being nuked to empty (which would trigger `empty_ai_response_safety_net`
# with a generic-error template). Below CTA-estado-4 length (~80 chars) so it
# preserves any plausibly salvageable content.
_GUARD_SHORT_CIRCUIT_THRESHOLD = 30
_FOOTER_PRICE_VALIDITY_RE = re.compile(
    r"_?\s*Precios\s+v[aá]lidos\s+por\s+30\s+d[ií]as\.?\s*_?",
    re.IGNORECASE,
)


def _strip_premature_price_artifacts(
    ai_response: str,
    precio_comunicado: bool,
    tarifa_calculada: Any,
) -> str:
    """Remove price sentences, CTA 3/4/5 and price-validity footer when no price was communicated.

    Semantics-preserving wrapper around guard_no_premature_price (T-6 refactor, AD-8).
    Delegates sentence-level price stripping to the guard, then strips CTAs and footer.

    Prompt-level <tariff_gate> (L2/L3 in pre_expediente_pricing.md) forbids
    emitting these artifacts without a calculated tariff. This is the hard
    red-net: if the LLM ignores the prompt and emits them anyway, strip them.

    No-op when price was communicated OR tariff exists in context OR the
    response contains a numeric price literal (e.g. "*410€ +IVA*").
    """
    if precio_comunicado or tarifa_calculada:
        return ai_response
    if _PRICE_NUMERIC_RE.search(ai_response):
        return ai_response
    # Delegate sentence-level price stripping to the state-grounded guard (AD-8).
    mc = {"precio_comunicado": precio_comunicado, "tarifa_calculada": tarifa_calculada}
    cleaned = guard_no_premature_price(ai_response, mc)
    # Strip premature CTAs and price-validity footer (existing L3 tariff-gate behaviour).
    for cta_literal in (CTAS[3], CTAS[4], CTAS[5]):
        cleaned = cleaned.replace(cta_literal, "")
    cleaned = _CTA_5_EQUIVALENT_RE.sub("", cleaned)
    cleaned = _FOOTER_PRICE_VALIDITY_RE.sub("", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).rstrip()


def _should_force_tool_choice(mc: dict) -> str | None:
    """Return "required" iff all four POST_PRICE + CTA 5 preconditions hold.

    Used as the ``get_tool_choice`` lambda in ModeLoopConfig for PRE_EXPEDIENTE_MODE.
    Forces the LLM to call a tool (not emit free text) when the user has just
    received CTA 5 ("¿Abrimos expediente o tienes alguna duda?") — preventing
    the silent-no-tool-call failure mode on the deepseek-chat cloud path.

    Conditions (ALL must be true to return "required"):
        - ``precio_comunicado`` is True
        - ``tarifa_calculada`` is truthy (non-None, non-empty)
        - ``imagenes_enviadas_codigos`` is truthy (non-empty list)
        - ``last_cta_emitted == "cta_5"``

    Design D2 (SDD tool-choice-required-post-price):
        Evaluates 4 equivalent proof conditions to infer POST_PRICE + CTA 5
        without reading any phase enum. Lambda scope is PRE_EXPEDIENTE-local.

    Args:
        mc: Current mode_context dict for this turn.

    Returns:
        ``"required"`` if all conditions hold; ``None`` otherwise.
    """
    if (
        mc.get("precio_comunicado") is True
        and bool(mc.get("tarifa_calculada"))
        and bool(mc.get("imagenes_enviadas_codigos"))
        and mc.get("last_cta_emitted") == "cta_5"
    ):
        logger.info(
            "tool_choice_forced_required",
            precio_comunicado=True,
            tarifa_calculada_present=bool(mc.get("tarifa_calculada")),
            imagenes_count=len(mc.get("imagenes_enviadas_codigos") or []),
            last_cta_emitted=mc.get("last_cta_emitted"),
        )
        return "required"
    return None


def _should_self_heal_tariff_gate(
    mc: dict,
    ai_response: str,
    tools_called: list[str],
) -> bool:
    """Detect the tariff-gate red-net scenario and return True when self-heal should fire.

    Spec references: S1 (trigger), S2–S5 (guards), AD-6 (idempotency flag).

    The tariff-gate scenario (S1) occurs when identificar_y_resolver_elementos succeeds
    but the LLM returns a text-only response, skipping the mandatory calcular_tarifa_con_elementos
    call. This function gates the self-heal retry so it fires exactly once per turn (AD-6).

    Guard mapping:
        S2 — tarifa_calculada truthy or calcular already called → False (already calculated)
        S3 — identificar not in tools_called → False (off-topic turn, not a post-ID slip)
        S4 — precio_comunicado truthy → False (price already told to user, no need to recalc)
        S5 — categoria_slug or element_codes missing → False + WARNING logged (data missing)
        S1 — all guards passed → True (fire the tail-loop self-heal)

    Returns True only when ALL of the following conditions are satisfied:
        - tarifa_calculada is falsy (price not yet calculated)  [S2 guard]
        - precio_comunicado is falsy (price not yet communicated)  [S4 guard]
        - "calcular_tarifa_con_elementos" NOT in tools_called  [S2 guard]
        - "identificar_y_resolver_elementos" in tools_called  [S1 trigger: just identified]
        - mc["categoria_slug"] is truthy  [S5 guard — log WARNING if missing]
        - mc["element_codes"] is truthy  [S5 guard — log WARNING if missing]

    Note: the AD-6 idempotency flag (_tariff_self_heal_fired) is maintained by the
    caller (_process_with_tool_loop), NOT inside this function. This keeps the detector
    pure and independently testable.
    """
    # S2: calcular already called this turn → no-op
    if mc.get("tarifa_calculada"):
        return False
    # S4: price already communicated → no-op
    if mc.get("precio_comunicado"):
        return False
    # S2: calcular was explicitly called → no-op
    if "calcular_tarifa_con_elementos" in tools_called:
        return False
    # S3: identificar not called this turn → off-topic, no-op
    if "identificar_y_resolver_elementos" not in tools_called:
        return False

    # S1 trigger conditions met — check required data fields (S5 guards)
    if not mc.get("categoria_slug"):
        logger.warning(
            "tariff_gate_self_heal_skipped_missing_categoria",
            element_codes=mc.get("element_codes"),
            tools_called=tools_called,
        )
        return False
    if not mc.get("element_codes"):
        logger.warning(
            "tariff_gate_self_heal_skipped_missing_codes",
            categoria_slug=mc.get("categoria_slug"),
            tools_called=tools_called,
        )
        return False

    return True


def _propagate_post_self_heal_state(
    updated_context: dict,
    shared_context: dict,
    tools_called: list[str],
) -> tuple[dict, dict, list[str], bool]:
    """Force-propagate `precio_comunicado` and `tools_called` after a successful
    tariff-gate self-heal tail loop.

    Spec: sdd/fix-pricing-gate-self-heal-loop — "Post-Self-Heal State
    Propagation Contract". Decouples the `precio_comunicado` flip (and the
    downstream output-guard activation) from tail-loop telemetry races where
    the synthetic `calcular_tarifa_con_elementos` call may not survive the
    `tools_called` reducer round-trip.

    Returns the (possibly mutated) updated_context, shared_context,
    tools_called, and a `propagated` flag for telemetry.

    No-op when `updated_context["tarifa_calculada"]` is falsy — i.e. the
    self-heal tail loop did not produce a tariff (degraded fallback path).
    """
    if not updated_context.get("tarifa_calculada"):
        return updated_context, shared_context, tools_called, False
    new_mc = {**updated_context, "precio_comunicado": True}
    new_sc = {**shared_context, "precio_comunicado": True}
    new_tools = (
        tools_called
        if "calcular_tarifa_con_elementos" in tools_called
        else list(tools_called) + ["calcular_tarifa_con_elementos"]
    )
    return new_mc, new_sc, new_tools, True


def _build_synthetic_tariff_tool_call(
    categoria_slug: str,
    element_codes: list[str],
) -> "AIMessage":
    """Build a synthetic AIMessage that carries a pre-formed calcular_tarifa_con_elementos
    tool call, as required by AD-3.

    The synthetic call is injected into the tail-loop message history so the tool node
    executes the tariff calculation without an additional LLM round-trip.

    Args:
        categoria_slug: Vehicle category slug, sourced from mode_context["categoria_slug"].
        element_codes: List of element codes, sourced from mode_context["element_codes"].

    Returns:
        An AIMessage with content="" and a single tool_call dict whose id is prefixed
        with "call_self_heal_tariff_" for easy identification in telemetry / tests.
    """
    from langchain_core.messages import AIMessage as _AIMessage

    synthetic_call_id = f"call_self_heal_tariff_{uuid.uuid4().hex[:12]}"
    return _AIMessage(
        content="",
        tool_calls=[
            {
                "name": "calcular_tarifa_con_elementos",
                "args": {
                    "categoria_vehiculo": categoria_slug,
                    "codigos_elementos": element_codes,
                    "skip_validation": True,
                },
                "id": synthetic_call_id,
                "type": "tool_call",
            }
        ],
    )


# ---------------------------------------------------------------------------
# Output guard pipeline — R-1: image send truth (AD-2, AD-3, AD-4, AD-5, AD-7)
# ---------------------------------------------------------------------------

# Keyword frozensets for image-truth guard (spec S1-1..S1-5, design AD-3)
IMAGE_OUTCOME_KEYWORDS: frozenset[str] = frozenset({
    "imagen", "imágenes", "foto", "fotos", "envío", "enviar", "ejemplo", "ejemplos",
})
NEGATIVE_OUTCOME_KEYWORDS: frozenset[str] = frozenset({
    "problema", "error", "fallo", "fallido", "técnico",
    "no he podido", "no pude", "no pudo", "no se han podido", "no se pudieron",
})

# Canonical replacement appended after stripping offending paragraph (AD-5)
_CANONICAL_IMAGE_CORRECTION = "Ya tienes los ejemplos arriba."

# Keyword frozenset for premature-price guard (spec S2-1..S2-3, design AD-3)
PRICE_KEYWORDS: frozenset[str] = frozenset({
    "€", "euros", "precio", "presupuesto", "coste",
})

# Pattern list for premature-transition-claim guard (spec S3-1..S3-2, design AD-3)
TRANSITION_CLAIM_PATTERNS: list[str] = [
    "vamos a abrir",
    "ya tienes el expediente abierto",
    "abrimos expediente",
    "empezar a recoger datos",
    "hemos abierto el expediente",
    "vamos a empezar a recoger",
]


def _reset_reprice_flag_if_set(
    updated_context: dict,
    result_dict: dict,
) -> tuple[dict, dict]:
    """Write tombstone (None) for reprice_allowed_this_turn at turn boundary.

    Spec R9-S9.2. The flag is turn-scoped and must NOT leak to the next turn.
    We use None (tombstone per ADR-010) — NOT False — so merge_dicts cannot
    resurrect a stale True value from the Redis checkpoint.

    Called at the end of _process_message, after the AD-9 guard pipeline
    completes, before returning result_dict.

    Args:
        updated_context: The mode_context dict being assembled for this turn.
        result_dict: The result dict being returned from _process_message.

    Returns:
        (updated_context, result_dict) — both mutated in place and returned.
    """
    if updated_context.get("reprice_allowed_this_turn"):
        updated_context["reprice_allowed_this_turn"] = None
        sc = result_dict.get("shared_context") or {}
        sc["reprice_allowed_this_turn"] = None
        result_dict["shared_context"] = sc
    return updated_context, result_dict


def _log_guard_fired(
    node_logger: object,
    guard_name: str,
    conversation_id: str,
    mc_keys: dict,
    original: str,
    overridden: str,
    *,
    reason: str = "guard_fired",
    scope: str | None = None,
    precio_comunicado: bool | None = None,
    reprice_allowed_this_turn: bool | None = None,
    original_len: int | None = None,
    final_len: int | None = None,
    stripped_paragraph_count: int | None = None,
) -> None:
    """Emit structured telemetry when a guard activates (AD-7, AD-Y5).

    Centralises the guard_fired log call so each guard has a single call site.
    Emits the R12-required 8 fields when provided via keyword arguments.
    Falls back to mc_keys dict for backwards-compatible call sites.

    Required by spec R12: guard_name, reason, scope, precio_comunicado,
    reprice_allowed_this_turn, original_len, final_len, stripped_paragraph_count.
    """
    try:
        node_logger.warning(  # type: ignore[union-attr]
            "guard_fired",
            guard_name=guard_name,
            reason=reason,
            scope=scope if scope is not None else mc_keys.get("scope"),
            precio_comunicado=(
                precio_comunicado
                if precio_comunicado is not None
                else mc_keys.get("precio_comunicado")
            ),
            reprice_allowed_this_turn=(
                reprice_allowed_this_turn
                if reprice_allowed_this_turn is not None
                else mc_keys.get("reprice_allowed_this_turn")
            ),
            original_len=original_len if original_len is not None else len(original),
            final_len=final_len if final_len is not None else len(overridden),
            stripped_paragraph_count=(
                stripped_paragraph_count
                if stripped_paragraph_count is not None
                else mc_keys.get("dropped_count", 0)
            ),
            conversation_id=conversation_id,
            mode_context_snapshot=mc_keys,
            original_excerpt=original[:200],
            overridden_excerpt=overridden[:200],
        )
    except Exception:
        pass  # telemetry must never crash the guard


def _paragraph_has_both_keyword_sets(paragraph: str) -> bool:
    """Return True if the paragraph contains keywords from BOTH guard sets (AD-3, AD-4)."""
    p_lower = paragraph.lower()
    has_image = any(kw in p_lower for kw in IMAGE_OUTCOME_KEYWORDS)
    has_negative = any(kw in p_lower for kw in NEGATIVE_OUTCOME_KEYWORDS)
    return has_image and has_negative


def guard_image_send_truth(
    text: str,
    mc: dict,
    *,
    node_logger: object | None = None,
    conversation_id: str = "",
) -> str:
    """Strip hallucinated image-failure paragraphs when images are confirmed sent.

    Guard R-1 (spec S1-1..S1-5, design AD-2, AD-3, AD-4, AD-5).

    Activation conditions (ALL must hold):
        - imagenes_enviadas_codigos is non-empty (images confirmed delivered)
        - At least one paragraph co-locates an image keyword AND a negative keyword

    Behaviour:
        - Paragraph-level scan (split on double newline).
        - Strips offending paragraph(s).
        - Appends canonical correction phrase once at the end.
        - No-op if conditions not met.

    Args:
        text: Outbound LLM response text.
        mc: mode_context snapshot (read-only).
        node_logger: Instance logger for telemetry (optional — no-op if None).
        conversation_id: For telemetry correlation.

    Returns:
        Cleaned text string.
    """
    # Guard condition: images must be confirmed sent (AD-2)
    if not mc.get("imagenes_enviadas_codigos"):
        return text

    paragraphs = text.split("\n\n")
    clean_paragraphs: list[str] = []
    fired = False

    for para in paragraphs:
        if _paragraph_has_both_keyword_sets(para):
            fired = True
            # Strip this paragraph — do not add to clean output
            continue
        clean_paragraphs.append(para)

    if not fired:
        return text

    # Rebuild text without offending paragraphs, append canonical phrase
    cleaned = "\n\n".join(clean_paragraphs).strip()
    result = f"{cleaned}\n\n{_CANONICAL_IMAGE_CORRECTION}" if cleaned else _CANONICAL_IMAGE_CORRECTION

    # Telemetry (AD-7)
    if node_logger is not None:
        _log_guard_fired(
            node_logger=node_logger,
            guard_name="image_send_truth",
            conversation_id=conversation_id,
            mc_keys={"imagenes_enviadas_codigos": mc.get("imagenes_enviadas_codigos")},
            original=text,
            overridden=result,
        )

    return result


# ---------------------------------------------------------------------------
# R-5 guard: guard_no_reprice_post_price
# ---------------------------------------------------------------------------

import re as _re

# Patterns that mark a paragraph as a "budget re-narration" attempt.
# Each tuple is (pattern, description) for telemetry.
_REPRICE_PATTERNS: list[tuple[_re.Pattern, str]] = [
    # Price numeric with currency symbol or EUR abbreviation
    (_re.compile(r"\b\d+[\.,]?\d*\s*€|\bEUR\b", _re.IGNORECASE), "currency"),
    # Warning emoji at start of a line
    (_re.compile(r"⚠️"), "warning_emoji"),
    # Documentation headers
    (_re.compile(r"^\*?Documentaci[óo]n\s+(general|del|del\s|base|por)\b", _re.MULTILINE | _re.IGNORECASE), "doc_header"),
    # Plain "Documentación:" without qualifier (catches "*Documentación:*" etc.)
    (_re.compile(r"^\*?Documentaci[óo]n:\s*\*?$", _re.MULTILINE | _re.IGNORECASE), "doc_header_plain"),
    # Footer
    (_re.compile(r"_Precios válidos por 30 días\._?", _re.IGNORECASE), "footer"),
]


def _r5_should_fire(mc: dict) -> bool:
    """Predicate: returns True iff R-5 gate conditions are met (spec R8).

    Conditions (ALL must hold):
        - precio_comunicado=True  → we are in POST_PRICE territory
        - reprice_allowed_this_turn is falsy → not an explicit reprice turn
          (set to True by calcular_tarifa_con_elementos when precio_comunicado=True)

    Dropped from R1 (too narrow):
        - delivery_intent_created (missed free-text and elemento turns)
        - delivery_scope (scope is irrelevant to stripping)
        - tarifa_calculada (precio_comunicado is the authoritative POST_PRICE signal)
    """
    return bool(mc.get("precio_comunicado")) and not bool(
        mc.get("reprice_allowed_this_turn")
    )


def guard_no_reprice_post_price(
    text: str,
    mc: dict,
    *,
    node_logger: object | None = None,
    conversation_id: str = "",
) -> str:
    """Strip budget re-narration from POST_PRICE responses.

    Guard R-5 (spec R8, design AD-Y1). Fires when the LLM re-emits the full
    pricing narration (price + warnings + documentation + footer) after the
    price was already communicated to the user in a prior turn.

    Activation conditions (all must hold via _r5_should_fire):
        - precio_comunicado=True — we are in POST_PRICE territory
        - reprice_allowed_this_turn is falsy — not an explicit reprice turn

    Behaviour:
        - Paragraph-level scan (split on double newline).
        - Strips any paragraph that matches any _REPRICE_PATTERNS entry.
        - Preserves paragraphs that match none of the patterns.
        - If result is empty, returns empty string (CTA-5 enforcer will append CTA).

    Args:
        text: Outbound LLM response text.
        mc: mode_context snapshot (read-only).
        node_logger: Instance logger for telemetry (optional).
        conversation_id: For telemetry correlation.

    Returns:
        Cleaned text string (may be empty if all paragraphs were stripped).
    """
    if not _r5_should_fire(mc):
        return text

    paragraphs = text.split("\n\n")
    clean_paragraphs: list[str] = []
    dropped: list[str] = []

    for para in paragraphs:
        offending = False
        for pattern, _label in _REPRICE_PATTERNS:
            if pattern.search(para):
                offending = True
                dropped.append(_label)
                break
        if not offending:
            clean_paragraphs.append(para)

    if not dropped:
        # Nothing was stripped — text was already clean
        return text

    cleaned = "\n\n".join(p for p in clean_paragraphs if p.strip())

    if node_logger is not None:
        _log_guard_fired(
            node_logger=node_logger,
            guard_name="no_reprice_post_price",
            conversation_id=conversation_id,
            mc_keys={
                "precio_comunicado": mc.get("precio_comunicado"),
                "reprice_allowed_this_turn": mc.get("reprice_allowed_this_turn"),
                "scope": mc.get("delivery_scope"),
                "dropped_count": len(dropped),
            },
            original=text,
            overridden=cleaned,
            # R12 standardized fields (AD-Y5)
            reason="post_price_reprice",
            scope=mc.get("delivery_scope"),
            precio_comunicado=bool(mc.get("precio_comunicado")),
            reprice_allowed_this_turn=bool(mc.get("reprice_allowed_this_turn")),
            original_len=len(text),
            final_len=len(cleaned),
            stripped_paragraph_count=len(dropped),
        )

    return cleaned


# ---------------------------------------------------------------------------
# Phase B helpers: ToolMessage compaction on precio_comunicado flip (R6)
# ---------------------------------------------------------------------------


def _compact_tarifa_toolmessage(
    original_msg: object,
    *,
    precio: float,
    element_codes: list[str],
) -> object:
    """Build a compact replacement for a calcular_tarifa_con_elementos ToolMessage.

    The replacement preserves tool_call_id (critical for AIMessage → ToolMessage binding)
    and produces a compact JSON payload (≤ 200 chars) with ya_comunicado=true.

    Args:
        original_msg: The original LangGraph ToolMessage to replace.
        precio: The final price (EUR, IVA excluded).
        element_codes: List of element codes in the tariff.

    Returns:
        A new ToolMessage with compact content and same tool_call_id.
    """
    import json as _json
    from langchain_core.messages import ToolMessage

    compact_payload = _json.dumps(
        {
            "success": True,
            "precio": precio,
            "elementos": element_codes,
            "ya_comunicado": True,
            "note": "Narración comunicada — no re-narrar.",
        },
        ensure_ascii=False,
    )

    return ToolMessage(
        content=compact_payload[:200],  # hard cap at 200 chars
        tool_call_id=getattr(original_msg, "tool_call_id", "unknown"),
        name="calcular_tarifa_con_elementos",
        id=getattr(original_msg, "id", None),
    )


def _find_and_compact_tarifa_message(
    messages: list,
    *,
    precio: float,
    element_codes: list[str],
) -> object | None:
    """Walk messages backwards to find the most recent calcular_tarifa ToolMessage.

    Returns a compact replacement ToolMessage (same id → add_messages reducer replaces it),
    or None if no such message is found.
    """
    from langchain_core.messages import ToolMessage

    for msg in reversed(messages):
        if not isinstance(msg, ToolMessage):
            continue
        name = getattr(msg, "name", None)
        if name == "calcular_tarifa_con_elementos":
            return _compact_tarifa_toolmessage(msg, precio=precio, element_codes=element_codes)

    return None


# ---------------------------------------------------------------------------
# AD-Y3: Idempotent start-of-turn Phase B compaction (spec R10)
# ---------------------------------------------------------------------------


def _should_compact_this_turn(mc: dict, sc: dict) -> bool:
    """Predicate: True when start-of-turn Phase B compaction should run.

    Conditions:
        - precio_comunicado=True (POST_PRICE territory)
        - reprice_allowed_this_turn is falsy (not a reprice turn)

    On a reprice turn the flag is set by calcular_tarifa_con_elementos DURING
    the tool loop — it cannot be True here at start-of-turn, so this check is
    belt-and-suspenders for future defence-in-depth.

    Args:
        mc: mode_context dict (read-only).
        sc: shared_context dict (read-only).

    Returns:
        True if compaction should run this turn.
    """
    precio = bool(mc.get("precio_comunicado") or sc.get("precio_comunicado"))
    reprice = bool(
        mc.get("reprice_allowed_this_turn") or sc.get("reprice_allowed_this_turn")
    )
    return precio and not reprice


def _compact_stale_tarifa_messages(
    messages: list,
    *,
    node_logger: object | None = None,
    conversation_id: str = "",
) -> list:
    """Scan messages for verbose calcular_tarifa ToolMessages and compact them.

    Idempotent: messages already compact (≤200 chars AND no '€') are skipped.
    Compact replacements preserve tool_call_id for LangGraph add_messages reducer.

    Spec R10 (AD-Y3 scanner). Reuses _compact_tarifa_toolmessage for replacement.
    Caller injects the list into result_dict["messages"] to trigger reducer swap.

    Emits _log_guard_fired per replacement when node_logger is provided (spec R12).

    Args:
        messages: Current state.messages list.
        node_logger: Optional structlog logger for R12 telemetry.
        conversation_id: Used in telemetry log entries.

    Returns:
        List of compact replacement ToolMessages (may be empty if nothing to compact).
    """
    from langchain_core.messages import ToolMessage

    replacements: list = []
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        if getattr(msg, "name", None) != "calcular_tarifa_con_elementos":
            continue
        content: str = getattr(msg, "content", "") or ""
        # Already compact — idempotent predicate: ≤200 chars AND no €
        if len(content) <= 200 and "€" not in content:
            continue
        # Compact it — we use price=0.0 / elements=[] since the point is to
        # suppress re-narration, not re-surface exact data (spec AC-10.1).
        compact_msg = _compact_tarifa_toolmessage(msg, precio=0.0, element_codes=[])
        replacements.append(compact_msg)
        # R12 telemetry: emit structured log on each compaction (spec R10, AD-Y3).
        if node_logger is not None:
            compact_content: str = getattr(compact_msg, "content", "") or ""
            _log_guard_fired(
                node_logger=node_logger,
                guard_name="guard_phase_b_compaction_idempotent",
                conversation_id=conversation_id,
                mc_keys={},
                original=content,
                overridden=compact_content,
                reason="stale_tarifa_message_compacted",
                scope="post_price",
                precio_comunicado=True,
                reprice_allowed_this_turn=False,
                original_len=len(content),
                final_len=len(compact_content),
                stripped_paragraph_count=0,
            )
    return replacements


# ---------------------------------------------------------------------------
# AD-Y4: Conversational regurgitation guard (spec R11)
# ---------------------------------------------------------------------------

import re as _re2  # noqa: E402 — re already imported above; alias to avoid shadowing

# Pre-compiled signal patterns for the conversational regurgitation guard.
# Each pattern matches one class of budget content. ≥2 distinct class hits → replace.
_SIGNAL_CURRENCY = _re.compile(r"\d+\s*€")
_SIGNAL_WARNING = _re.compile(r"⚠️")
_SIGNAL_DOC_GEN = _re.compile(r"Documentaci[óo]n\s+general", _re.IGNORECASE)
_SIGNAL_DOC_DEL = _re.compile(r"Documentaci[óo]n\s+del\b", _re.IGNORECASE)
_SIGNAL_FOTO_BULLET = _re.compile(r"^- Foto\b", _re.MULTILINE)

_CONV_SIGNALS: list[tuple] = [
    (_SIGNAL_CURRENCY, "currency"),
    (_SIGNAL_WARNING, "warning_emoji"),
    (_SIGNAL_DOC_GEN, "doc_general"),
    (_SIGNAL_DOC_DEL, "doc_del"),
    (_SIGNAL_FOTO_BULLET, "foto_bullet"),
]

# Canonical replacement string — literal CTA_5 resolved at module load time.
_REPLACEMENT_CONV_STRIP = f"Ya te comuniqué el presupuesto arriba. {_CTA_5}"


def guard_no_reprice_without_tool(
    text: str,
    mc: dict,
    tools_called_this_turn: list[str],
    *,
    node_logger: object | None = None,
    conversation_id: str = "",
) -> str:
    """Replace LLM budget regurgitation when no tool was called in POST_PRICE.

    Guard R-11 (spec R11, design AD-Y4). Fires when:
        - precio_comunicado=True (POST_PRICE territory)
        - tools_called_this_turn is empty (no tool fired this turn)
        - reprice_allowed_this_turn is falsy (not an explicit reprice)
        - ≥2 distinct budget signal patterns found in text

    When fired, replaces the ENTIRE text with _REPLACEMENT_CONV_STRIP
    ("Ya te comuniqué el presupuesto arriba. {CTA_5}"). Unlike R-5 which
    strips paragraphs, this guard replaces wholesale — it catches free-text
    regurgitations where the LLM composes the budget from memory.

    Args:
        text: Outbound LLM response text.
        mc: mode_context snapshot (read-only).
        tools_called_this_turn: Tool names invoked this turn.
        node_logger: Instance logger for telemetry (optional).
        conversation_id: For telemetry correlation.

    Returns:
        _REPLACEMENT_CONV_STRIP if guard fires, else original text unchanged.
    """
    # Gate conditions — bail fast if any is not met
    if not mc.get("precio_comunicado"):
        return text
    if tools_called_this_turn:
        return text
    if mc.get("reprice_allowed_this_turn"):
        return text

    # Count distinct signal classes that match
    hits = sum(1 for pat, _ in _CONV_SIGNALS if pat.search(text))
    if hits < 2:
        return text

    # Telemetry (R12 standardized, AD-Y5)
    if node_logger is not None:
        _log_guard_fired(
            node_logger=node_logger,
            guard_name="no_reprice_without_tool",
            conversation_id=conversation_id,
            mc_keys={
                "precio_comunicado": mc.get("precio_comunicado"),
                "reprice_allowed_this_turn": mc.get("reprice_allowed_this_turn"),
                "scope": None,
                "signal_hits": hits,
            },
            original=text,
            overridden=_REPLACEMENT_CONV_STRIP,
            reason="conversational_reprice",
            scope=None,
            precio_comunicado=bool(mc.get("precio_comunicado")),
            reprice_allowed_this_turn=bool(mc.get("reprice_allowed_this_turn")),
            original_len=len(text),
            final_len=len(_REPLACEMENT_CONV_STRIP),
            stripped_paragraph_count=hits,
        )

    return _REPLACEMENT_CONV_STRIP


def guard_no_premature_price(
    text: str,
    mc: dict,
    *,
    node_logger: object | None = None,
    conversation_id: str = "",
) -> str:
    """Strip price-mentioning sentences when no tariff has been calculated yet.

    Guard R-2 (spec S2-1..S2-3, design AD-2, AD-3, AD-5).

    Activation conditions (ALL must hold):
        - precio_comunicado is falsy (price not yet communicated to user)
        - tarifa_calculada is falsy (no stored tariff in context)

    Behaviour:
        - Sentence-level scan (split on '. ').
        - Strips any sentence containing a PRICE_KEYWORDS token.
        - No canonical replacement appended (AD-5).
        - No-op if conditions not met.

    Args:
        text: Outbound LLM response text.
        mc: mode_context snapshot (read-only).
        node_logger: Instance logger for telemetry (optional — no-op if None).
        conversation_id: For telemetry correlation.

    Returns:
        Cleaned text string.
    """
    # Guard condition: only strip when price NOT yet communicated AND tariff absent
    if mc.get("precio_comunicado") or mc.get("tarifa_calculada"):
        return text

    sentences = text.split(". ")
    clean_sentences: list[str] = []
    fired = False

    for sentence in sentences:
        s_lower = sentence.lower()
        if any(kw in s_lower for kw in PRICE_KEYWORDS):
            fired = True
            # Strip this sentence — do not add to clean output
            continue
        clean_sentences.append(sentence)

    if not fired:
        return text

    result = ". ".join(clean_sentences).strip()
    # Remove trailing period if the last kept sentence already ends with "."
    # and the join added an extra one — let ". ".join handle joining naturally.

    # F2: short-circuit when stripping would yield near-empty output AND the
    # original was non-empty.
    if len(result) < _GUARD_SHORT_CIRCUIT_THRESHOLD and text.strip():
        if node_logger is not None:
            node_logger.warning(  # type: ignore[union-attr]
                "guard_short_circuit_empty_result",
                guard_name="premature_price",
                conversation_id=conversation_id,
                original_length=len(text),
                cleaned_length=len(result),
                threshold=_GUARD_SHORT_CIRCUIT_THRESHOLD,
            )
        return text

    # Telemetry (AD-7)
    if node_logger is not None:
        _log_guard_fired(
            node_logger=node_logger,
            guard_name="premature_price",
            conversation_id=conversation_id,
            mc_keys={
                "precio_comunicado": mc.get("precio_comunicado"),
                "tarifa_calculada": bool(mc.get("tarifa_calculada")),
            },
            original=text,
            overridden=result,
        )

    return result


def guard_no_premature_transition_claim(
    text: str,
    mc: dict,
    pending_updates: dict,
    *,
    node_logger: object | None = None,
    conversation_id: str = "",
) -> str:
    """Strip sentences that claim a mode transition occurred when none is pending.

    Guard R-3 (spec S3-1..S3-2, design AD-2, AD-3, AD-5).

    Activation conditions (ALL must hold):
        - _transition_to is NOT present in pending_updates for this turn
        - At least one sentence matches a TRANSITION_CLAIM_PATTERNS entry

    Behaviour:
        - Sentence-level scan (split on '. ').
        - Strips any sentence matching a transition-claim pattern (case-insensitive).
        - No canonical replacement appended (AD-5).
        - No-op if _transition_to is set (S3-2: transition is legitimate).

    Args:
        text: Outbound LLM response text.
        mc: mode_context snapshot (read-only, unused by this guard but kept for interface parity).
        pending_updates: Tool _state_update dict for the current turn.
        node_logger: Instance logger for telemetry (optional — no-op if None).
        conversation_id: For telemetry correlation.

    Returns:
        Cleaned text string.
    """
    # Guard condition: only strip when NO transition is actually pending (AD-2)
    if "_transition_to" in pending_updates:
        return text

    sentences = text.split(". ")
    clean_sentences: list[str] = []
    fired = False

    for sentence in sentences:
        s_lower = sentence.lower()
        if any(pattern in s_lower for pattern in TRANSITION_CLAIM_PATTERNS):
            fired = True
            # Strip this sentence — do not add to clean output
            continue
        clean_sentences.append(sentence)

    if not fired:
        return text

    result = ". ".join(clean_sentences).strip()

    # Telemetry (AD-7)
    if node_logger is not None:
        _log_guard_fired(
            node_logger=node_logger,
            guard_name="premature_transition_claim",
            conversation_id=conversation_id,
            mc_keys={"_transition_to": pending_updates.get("_transition_to")},
            original=text,
            overridden=result,
        )

    return result


# ---------------------------------------------------------------------------
# CTA policy allow-lists per phase (AD-9, spec S4-1..S4-3)
# ---------------------------------------------------------------------------
# Sentence-level markers for non-CTA-5 closing questions that the LLM may
# emit. These are matched case-insensitively inside each sentence fragment.
# Keep the list NARROW — prefer false negatives over false positives.
_WRONG_CTA_PATTERNS: list[str] = [
    "¿tienes alguna pregunta",
    "¿tienes alguna duda",
    "¿quieres que te ayude",
    "¿te interesa alguno",
    "¿te muestro ejemplos",
    "¿te enseño ejemplos",
    "¿quieres que procedamos",
    "¿listo para continuar",
    "¿empezamos",
]


def guard_cta_policy(
    text: str,
    mc: dict,
    phase: str,
    *,
    node_logger: object | None = None,
    conversation_id: str = "",
) -> str:
    """Strip CTAs that are incompatible with the current PRE_EXPEDIENTE phase.

    Guard R-4 (spec S4-1..S4-3, design AD-5, AD-9).

    Phase policy (per spec):
        PRE_EXPEDIENTE_DISCOVERY  → no CTA allowed; strip ANY CTA equivalent.
        PRE_EXPEDIENTE_PRICING    → confirm-budget-or-questions CTA allowed;
                                    CTA 5 ("¿Abrimos expediente…") NOT allowed.
        PRE_EXPEDIENTE_POST_PRICE → ONLY CTA 5 allowed; all others stripped.

    Behaviour:
        - Sentence-level scan (split on '. ').
        - Strip sentences that match a CTA pattern not permitted for this phase.
        - No canonical replacement appended here (AD-5); _enforce_cta5_if_needed
          runs downstream and appends CTA 5 when needed (AD-9 ordering).
        - No-op when no disallowed CTA is detected.

    Args:
        text: Outbound LLM response text.
        mc: mode_context snapshot (read-only; unused — phase passed explicitly).
        phase: PRE_EXPEDIENTE_DISCOVERY | PRE_EXPEDIENTE_PRICING |
               PRE_EXPEDIENTE_POST_PRICE
        node_logger: Instance logger for telemetry (optional).
        conversation_id: For telemetry correlation.

    Returns:
        Cleaned text string.
    """
    sentences = text.split(". ")
    clean_sentences: list[str] = []
    fired = False

    for sentence in sentences:
        s_lower = sentence.lower()

        if phase == "PRE_EXPEDIENTE_POST_PRICE":
            # Allow CTA 5 only; strip all other CTA variants
            is_cta5 = bool(_CTA_5_EQUIVALENT_RE.search(sentence))
            if not is_cta5 and any(pat in s_lower for pat in _WRONG_CTA_PATTERNS):
                fired = True
                continue

        elif phase == "PRE_EXPEDIENTE_PRICING":
            # Strip CTA 5 only (too early for "¿Abrimos expediente?")
            if _CTA_5_EQUIVALENT_RE.search(sentence):
                fired = True
                continue

        else:
            # DISCOVERY: strip CTA 5 AND all known wrong-CTA patterns
            if _CTA_5_EQUIVALENT_RE.search(sentence) or any(
                pat in s_lower for pat in _WRONG_CTA_PATTERNS
            ):
                fired = True
                continue

        clean_sentences.append(sentence)

    if not fired:
        return text

    result = ". ".join(clean_sentences).strip()

    # Telemetry (AD-7)
    if node_logger is not None:
        _log_guard_fired(
            node_logger=node_logger,
            guard_name="cta_policy",
            conversation_id=conversation_id,
            mc_keys={"phase": phase},
            original=text,
            overridden=result,
        )

    return result


def _enforce_cta5_if_needed(
    ai_response: str,
    precio_comunicado: bool,
    imagenes_enviadas_codigos: list | None,
) -> str:
    """Deterministic CTA 5 enforcement — escenario 7.bis / regla 9.

    Post-tool-loop hook called before returning the turn's ai_response.
    Guarantees that, when both preconditions are met, the response ends with
    the canonical CTA 5 literal.

    Preconditions (BOTH must be true to activate enforcement):
        - precio_comunicado is True
        - imagenes_enviadas_codigos is a non-empty list

    Behaviour:
        - LLM text is empty or whitespace only → emit CTA 5 as sole content.
        - LLM text already ends with canonical CTA 5 → passthrough (no-op).
        - LLM text ends with a semantically equivalent CTA (e.g. tuteo variant
          "¿Abrimos expediente o tienes alguna duda?") → NORMALIZE the tail to
          the canonical voseo form without duplicating. This prevents the
          double-CTA emission seen when the LLM drifts to tuteo.
        - LLM text present without any CTA variant → append canonical CTA 5.
        - Preconditions not met → return ai_response unchanged.

    Args:
        ai_response: Raw text produced by the LLM this turn.
        precio_comunicado: Whether the price was communicated to the client.
        imagenes_enviadas_codigos: Codes of images sent so far (non-empty = images were sent).

    Returns:
        The (possibly modified) response string.
    """
    # Guard: preconditions
    if not precio_comunicado or not imagenes_enviadas_codigos:
        return ai_response

    stripped = ai_response.strip()

    # Case 3: empty / whitespace only → CTA 5 as sole content
    if not stripped:
        return _CTA_5

    # Case 2a: already ends with canonical CTA 5 → no-op
    if stripped.endswith(_CTA_5):
        return ai_response

    # Case 2b: CTA matched anywhere in text (tuteo drift, spacing, casing, mid-body) →
    # discard everything from match.start() onward and append canonical CTA. Preserves prefix.
    match = _CTA_5_EQUIVALENT_RE.search(stripped)
    if match:
        prefix = stripped[: match.start()].rstrip()
        if prefix:
            return f"{prefix}\n\n{_CTA_5}"
        return _CTA_5

    # Case 1: useful text without any CTA variant → append with newline separator
    return f"{stripped}\n\n{_CTA_5}"


def _apply_tool_flags(
    mode_context: dict,
    tool_result: dict | str,
    logger: Any,
) -> None:
    """
    Apply _internal_flags from tool result to mode_context.

    This is the NEW pattern for explicit state management:
    - Tools declare state changes in their return value
    - Mode applies those changes atomically
    - Changes are persisted via ConversationState

    BUG FIX: _execute_and_log_tool returns JSON STRING, not dict.
    This function now accepts both STRING and DICT for robustness.

    Args:
        mode_context: Current mode context (will be modified in-place)
        tool_result: Tool return value with optional _internal_flags
                     Can be STRING (JSON) or DICT
        logger: Logger instance for debugging
    """
    # BUG FIX: Parse JSON string if needed
    if isinstance(tool_result, str):
        try:
            tool_result = json.loads(tool_result)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(
                "apply_tool_flags_invalid_json",
                error=str(e),
                result_preview=tool_result[:100] if tool_result else "",
            )
            return

    # Type guard after parsing
    if not isinstance(tool_result, dict):
        logger.warning(
            "apply_tool_flags_invalid_type",
            type=type(tool_result).__name__,
        )
        return

    # Dual-reader: prefer _state_update (new canonical key), fall back to _internal_flags
    flags = tool_result.get("_state_update") or tool_result.get("_internal_flags", {})
    if not flags:
        logger.debug(
            "apply_tool_flags_no_flags",
            conversation_id=mode_context.get("conversation_id"),
        )
        return

    logger.info(
        "applying_tool_flags",
        flags=list(flags.keys()),
        values={k: v for k, v in flags.items()},
        conversation_id=mode_context.get("conversation_id"),
    )

    # Separate transition signal from context flags
    transition_to = flags.pop("_transition_to", None)
    if transition_to:
        mode_context["_transition_to"] = transition_to
        logger.info(
            "transition_signal_received",
            target=transition_to,
            conversation_id=mode_context.get("conversation_id"),
        )

    # Apply remaining flags to mode_context
    mode_context.update(flags)


def _reset_validation_retry_state(retry_state: dict) -> dict:
    """
    Partial reset of retry_state after a successful tool call.
    Resets validation-specific counters while preserving consecutive_errors
    (which drives the outer escalation logic in BaseModeNode.process()).
    """
    return {
        **retry_state,
        "retry_count": 0,
        "last_validation_context": None,
        "last_error_type": None,
        "last_error_message": None,
    }


def _parse_tool_result(
    result: str | dict[str, Any], tool_name: str = ""
) -> dict[str, Any]:
    """
    Safely coerce a raw tool result into a dict without raising.

    ``_execute_and_log_tool()`` in BaseModeNode returns a JSON **string**.
    Downstream code that needs a dict must go through this helper so that
    plain-text error payloads (returned by failing tools) never propagate
    as uncaught ``JSONDecodeError`` at the PRE_EXPEDIENTE mode boundary.

    Args:
        result:    Raw tool output — either a JSON string or an already-parsed dict.
        tool_name: Optional tool name used for structured logging only.

    Returns:
        Parsed dict in all cases:
        - Valid JSON string  → parsed dict.
        - Plain-text string  → ``{"success": False, "error": text, "raw_message": text,
                                   "result_format": "plain_text"}``.
        - Empty string       → ``{"success": False, "error": "empty_result",
                                   "message": "No se pudo obtener respuesta del servicio",
                                   "result_format": "plain_text"}``.
        - Already a dict     → returned as-is.
        - Unexpected type    → ``{"success": False, "error": "unexpected_type"}``.
    """
    # Already a dict — nothing to do.
    if isinstance(result, dict):
        return result

    if not isinstance(result, str):
        logger.warning(
            "parse_tool_result_unexpected_type",
            tool=tool_name,
            received_type=type(result).__name__,
        )
        return {
            "success": False,
            "error": "unexpected_type",
            "result_format": "plain_text",
        }

    # Empty string guard.
    if not result.strip():
        logger.warning(
            "parse_tool_result_empty_string",
            tool=tool_name,
        )
        return {
            "success": False,
            "error": "empty_result",
            "message": "No se pudo obtener respuesta del servicio",
            "result_format": "plain_text",
        }

    # Happy path: try JSON.
    try:
        parsed = json.loads(result)
        if isinstance(parsed, dict):
            return parsed
        # JSON parsed but not a dict (e.g. a bare list or number) — treat as error.
        logger.warning(
            "parse_tool_result_non_dict_json",
            tool=tool_name,
            parsed_type=type(parsed).__name__,
        )
        return {
            "success": False,
            "error": "non_dict_json",
            "raw_message": result,
            "result_format": "plain_text",
        }
    except json.JSONDecodeError:
        logger.warning(
            "parse_tool_result_json_decode_error",
            tool=tool_name,
            result_preview=result[:120],
        )
        return {
            "success": False,
            "error": result,
            "raw_message": result,
            "result_format": "plain_text",
        }


# ---------------------------------------------------------------------------
# Variant state helpers
# ---------------------------------------------------------------------------


def _has_unresolved_variants(mode_context: dict) -> bool:
    """
    Return True when ``mode_context`` contains at least one pending variant
    whose status is not yet ``"resolved"``.

    Used to decide whether to enforce ``tool_choice="required"`` so the LLM
    cannot emit free text while a variant question is active.

    Reused at:
    - Initial LLM build (line ~481): first call to ``_get_llm``.
    - Mid-loop tool rebind (line ~901): after ``get_tools()`` changes tool set.

    Args:
        mode_context: Current mode context dict (may be ``None`` or empty).

    Returns:
        ``True`` if any variant entry has ``status != "resolved"``.
        ``False`` when the list is empty, absent, or all variants are resolved.
    """
    pending = (mode_context or {}).get("pending_variants") or []
    return any(v.get("status") != "resolved" for v in pending if isinstance(v, dict))


class PreExpedienteModeNode(BaseModeNode):
    """
    PRE_EXPEDIENTE_MODE: Merged informational + pricing mode.

    Covers ~100% of pre-expediente traffic (formerly CONSULTA_MODE + PRESUPUESTO_MODE).
    Entry point for both informational queries and pricing requests.

    Uses the LLM with the full 11-tool superset to:
    - Answer informational queries (catalog, documentation, vehicle classification)
    - Identify elements from free-text descriptions
    - Resolve variant ambiguities
    - Calculate tariff IMMEDIATELY (no "estimación" step)
    - Communicate price + warnings (MANDATORY before images)
    - Offer 2 clear options:
      A) View documentation/images (then ask about opening case)
      B) Open case directly (transition to EXPEDIENTE_MODE)

    Critical rules:
    - PRICE must be communicated BEFORE sending images
    - After price, offer 2 options (not just one)
    - NO concept of "estimación" vs "precio exacto" (always exact)
    - identifies_disclosure: EU AI Act (first interaction disclosure) handled here
    """

    # Increased from default 1500 to prevent truncation with large system prompts.
    _default_max_tokens: int = 3000

    def __init__(self) -> None:
        super().__init__("PRE_EXPEDIENTE_MODE")
        self._tools: list | None = None

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    async def _process_message(
        self,
        message: str,
        state: ConversationState,
    ) -> dict[str, Any]:
        """
        Process a user message in PRE_EXPEDIENTE_MODE.

        Always uses the ToolNode subgraph engine (generic_llm_loop deleted in T-25).
        """
        return await self._process_with_tool_loop(message, state)

    # ------------------------------------------------------------------
    # New ToolNode subgraph path (T-18)
    # ------------------------------------------------------------------

    async def _process_with_tool_loop(
        self,
        message: str,
        state: ConversationState,
    ) -> dict[str, Any]:
        """
        Process using the new build_mode_tool_loop() subgraph engine (AD-1, T-18).

        Replaces:
        - generic_loop tool callback (domain logic → pre_expediente_post_tool_hook)
        - message injection anti-pattern (fake AIMessage → state updates)
        - rebind_tools (mid-loop tool switching → get_tools(mode_context) filtering)
        - _apply_tool_flags (in-place mutation → _state_update via ToolMessages)

        This path:
        1. Builds ModeLoopConfig with pre_expediente-specific settings.
        2. Invokes the compiled subgraph.
        3. Merges pending_state_updates into mode_context.
        4. Propagates transition signals and pending_images to caller.
        """
        from langchain_core.messages import HumanMessage

        conversation_id = str(state.get("conversation_id", "unknown"))
        mode_context = dict(state.get("mode_context") or {})
        messages = list(state.get("messages", []))

        # Enrich mode_context with runtime flags
        mode_context["_client_type"] = state.get("client_type", "particular")
        mode_context["_is_first_interaction"] = state.get("is_first_interaction", False)

        # Load DraftQuote on resume (same as presupuesto path)
        await _load_active_draft_quote_into_context(conversation_id, mode_context)

        # Build client context for the prompt
        client_context = self._build_client_context(state)

        # AD-Y3 start-of-turn Phase B compaction (spec R10).
        # Scans for verbose calcular_tarifa ToolMessages and replaces them with
        # compact versions before the LLM sees the history. Idempotent — messages
        # already compact (≤200 chars, no €) are skipped automatically.
        # Skip on reprice turns: predicate checks reprice_allowed_this_turn which
        # is reset by the prior turn's tombstone, so on a fresh reprice turn it is
        # None/False — compaction runs on stale old messages only (safe by design).
        _sc_for_compaction = dict(state.get("shared_context") or {})
        if _should_compact_this_turn(mode_context, _sc_for_compaction):
            _compact_replacements = _compact_stale_tarifa_messages(
                messages,
                node_logger=self._logger,
                conversation_id=conversation_id,
            )
            if _compact_replacements:
                # We'll inject into result_dict later; track them here
                _compaction_replacements_early = _compact_replacements
            else:
                _compaction_replacements_early = []
        else:
            _compaction_replacements_early = []

        # Capture mode_context snapshot for closure (variant filtering etc.)
        _mode_context_snapshot = dict(mode_context)

        def _get_tools_with_filtering(ctx: dict) -> list:
            """
            Return tool list for this turn, applying the 4-gate priority system.

            Priority-ordered gate system for PRE_EXPEDIENTE_MODE:

            Gate 1 (highest priority): Variant gate
                When unresolved variants exist, ONLY variant tools are available.
                This prevents the LLM from calling any other tool while a
                variant question is pending.

            Gate 5: enviar_imagenes_ejemplo requires calculated tariff with images
                Only available when tarifa_calculada is a non-empty dict with imagenes_ejemplo.
                Prevents the LLM from calling enviar_imagenes before a tariff is calculated.

            Gate 3: confirmar_presupuesto availability
                Only available when price has been communicated AND tariff exists.
                Defense-in-depth: the tool itself has a code-level guard too.

            Gate 4: calcular_tarifa_con_elementos efficiency
                Excluded when no elements identified (would fail gracefully anyway).

            NOTE: Gate 2 (re-identification prevention) was removed to support
                additive identification (adding elements to an existing quote).
            """
            # ── GATE 1 (highest priority): Variant gate ──
            pending = (ctx or {}).get("pending_variants") or []
            unresolved = [v for v in pending if v.get("status") != "resolved"]
            if unresolved:
                # Restrict to variant resolution tools only
                from agent.tools.element_tools import seleccionar_variante_por_respuesta
                from agent.tools.shared_tools import escalar_a_humano

                return [seleccionar_variante_por_respuesta, escalar_a_humano]

            # ── No variant gate: build full tool set ──
            tools = list(_get_pre_expediente_tools())  # all 11 tools

            # ── GATE 5: enviar_imagenes_ejemplo requires calculated tariff with images ──
            # Only available when tarifa_calculada is a non-empty dict with imagenes_ejemplo.
            # Prevents the LLM from calling enviar_imagenes before a tariff is calculated.
            tarifa_calculada = (ctx or {}).get("tarifa_calculada")
            has_tarifa_with_images = (
                isinstance(tarifa_calculada, dict)
                and bool(tarifa_calculada)
                and bool(tarifa_calculada.get("imagenes_ejemplo"))
            )
            if not has_tarifa_with_images:
                from agent.tools.image_tools import enviar_imagenes_ejemplo
                tools = [t for t in tools if t is not enviar_imagenes_ejemplo]

            # ── GATE 3: confirmar_presupuesto availability ──
            # Only available when price has been communicated AND tariff exists.
            # Defense-in-depth: the tool itself has a code-level guard too.
            precio_comunicado = bool((ctx or {}).get("precio_comunicado"))
            has_tarifa = isinstance(tarifa_calculada, dict) and bool(tarifa_calculada)
            has_elements = bool((ctx or {}).get("element_codes"))

            if not (precio_comunicado and has_tarifa):
                from agent.tools.transition_tools import confirmar_presupuesto
                tools = [t for t in tools if t is not confirmar_presupuesto]

            # ── GATE 4: calcular_tarifa_con_elementos efficiency ──
            # Excluded when no elements identified (would fail anyway, saves tokens).
            if not has_elements:
                from agent.tools.element_tools import calcular_tarifa_con_elementos
                tools = [t for t in tools if t is not calcular_tarifa_con_elementos]

            return tools

        # Build ModeLoopConfig
        # get_tool_choice: forces tool_choice="required" when POST_PRICE + CTA 5 conditions hold.
        # Design D2 (tool-choice-required-post-price SDD): lambda evaluates 4 proof conditions
        # to infer POST_PRICE + CTA 5 without reading any phase enum.
        config = ModeLoopConfig(
            mode_name="PRE_EXPEDIENTE_MODE",
            get_tools=_get_tools_with_filtering,
            get_system_prompt=lambda loop_state: assemble_system_prompt(
                mode="PRE_EXPEDIENTE_MODE",
                mode_context=loop_state.get("_mode_context", mode_context),
                client_context=client_context,
            ),
            post_tool_hook=pre_expediente_post_tool_hook,
            max_iterations=MAX_TOOL_ITERATIONS,
            max_tokens=self._default_max_tokens,
            get_tool_choice=lambda mc: _should_force_tool_choice(mc),
        )

        # Compile the subgraph
        loop_result_obj = build_mode_tool_loop(config)

        # Format conversation history
        llm_history = list(format_messages_for_llm(
            messages,
            conversation_summary=state.get("conversation_summary"),
        ))

        # Build initial ToolLoopState
        initial_state = {
            "messages": llm_history
            + [HumanMessage(content=f"<USER_MESSAGE>\n{message}\n</USER_MESSAGE>")],
            "_mode_context": mode_context,
            "_conversation_id": conversation_id,
            "_mode_name": "PRE_EXPEDIENTE_MODE",
        }

        try:
            # Invoke the subgraph — pass recursion_limit so LangGraph enforces it
            loop_result = await loop_result_obj.graph.ainvoke(
                initial_state,
                config={"recursion_limit": loop_result_obj.recursion_limit},
            )
        finally:
            clear_image_tools_state()
            try:
                from agent.tools.draft_quote_service import _deactivate_draft_quote

                await _deactivate_draft_quote(conversation_id=conversation_id)
            except Exception as e:
                logger.warning("draft_quote_deactivation_failed", error=str(e))

        # Extract result fields
        ai_response = loop_result.get("ai_response", "")
        exit_reason = loop_result.get("exit_reason", "response")
        tools_called = loop_result.get("tools_called", [])
        pending_updates = dict(loop_result.get("pending_state_updates") or {})

        # Merge pending_state_updates into mode_context
        # pending_updates may contain nested mode_context key — merge carefully
        # shared_context is cross-mode: extract BEFORE merging into mode_context
        shared_context_update = pending_updates.pop("shared_context", None)
        nested_mc = pending_updates.pop("mode_context", None)
        updated_context = {**mode_context, **pending_updates}
        if isinstance(nested_mc, dict):
            updated_context.update(nested_mc)

        self._logger.info(
            "pre_expediente_tool_loop_response",
            exit_reason=exit_reason,
            tools_called=tools_called,
            response_length=len(ai_response),
            conversation_id=conversation_id,
        )

        result_dict: dict[str, Any] = {
            "ai_response": ai_response,
            "mode_context": updated_context,
        }

        # AD-Y3: inject start-of-turn compaction replacements (if any).
        # add_messages reducer replaces messages by id — tool_call_id preserved.
        if _compaction_replacements_early:
            result_dict.setdefault("messages", [])
            result_dict["messages"].extend(_compaction_replacements_early)

        # Propagate shared_context update to top-level (cross-mode, merge_dicts handles it)
        if shared_context_update and isinstance(shared_context_update, dict):
            result_dict["shared_context"] = shared_context_update

        # Propagate mode transition signal to top-level state
        # pending_mode_transition in mode_context → current_mode at root
        _transition_target = updated_context.pop("pending_mode_transition", None)
        if _transition_target:
            result_dict["current_mode"] = _transition_target
            updated_context["pending_mode_transition"] = None  # TOMBSTONE
            self._logger.info(
                "pre_expediente_mode_transition_tool_loop",
                target=_transition_target,
                conversation_id=conversation_id,
            )

        # Also check _transition_to from _state_update (legacy key from tools)
        _legacy_transition = updated_context.pop("_transition_to", None)
        if _legacy_transition and "current_mode" not in result_dict:
            result_dict["current_mode"] = _legacy_transition
            updated_context["_transition_to"] = None  # TOMBSTONE

        # Bubble up pending images if any
        pending_images = pending_updates.get("_pending_images") or updated_context.pop(
            "_pending_images", None
        )
        if pending_images:
            result_dict["pending_images"] = pending_images

        # ── CAPA 2b: Tariff-gate red-net self-heal ───────────────────────────
        # Spec S1: When identificar_y_resolver_elementos succeeds but the LLM
        # returns text-only (skipping calcular_tarifa_con_elementos), fire a
        # synthetic tail loop that forces the tariff calculation immediately.
        #
        # Guard: _tariff_self_heal_fired prevents a second retry even if the
        # tail loop itself fails to call calcular (degraded fallback — pass through).
        # AD-5: build_tail_loop topology: START → custom_tool_node → post_tool_node → llm_node → END
        # AD-3: synthetic AIMessage carries a pre-formed calcular_tarifa tool_call.
        _tariff_self_heal_fired = False
        if _should_self_heal_tariff_gate(updated_context, ai_response, tools_called):
            _tariff_self_heal_fired = True
            _element_codes = list(updated_context.get("element_codes") or [])
            _categoria_slug = updated_context.get("categoria_slug", "")

            # Build synthetic AIMessage via helper (AD-3)
            _synthetic_msg = _build_synthetic_tariff_tool_call(_categoria_slug, _element_codes)
            _synthetic_call_id = _synthetic_msg.tool_calls[0]["id"]

            self._logger.warning(
                "pre_expediente_tariff_gate_self_heal_fired",
                conversation_id=conversation_id,
                element_codes=_element_codes,
                categoria_slug=_categoria_slug,
                discarded_text_preview=ai_response[:1000],
                discarded_text_length=len(ai_response),
                tools_called_first_loop=tools_called,
                synthetic_call_id=_synthetic_call_id,
            )

            # Build retry state: messages from main loop with the DISCARDED AIMessage
            # (the one that caused the self-heal to fire: text-only, no tool_calls)
            # scrubbed from history, then append the synthetic tool_call AIMessage.
            #
            # Rationale: if the discarded text-only AIMessage stays in history, the
            # second LLM call in the tail loop sees it and builds on top of its
            # narrative (confirmations, generic CTAs, half-budgets) instead of
            # emitting the full first-turn budget from texto_narrativo. Scrubbing
            # removes the distractor so the LLM sees: user message → tool result →
            # respond fresh.
            from langchain_core.messages import AIMessage as _AIMessage

            _raw_msgs = list(loop_result.get("messages", []))
            if (
                _raw_msgs
                and isinstance(_raw_msgs[-1], _AIMessage)
                and not getattr(_raw_msgs[-1], "tool_calls", None)
            ):
                _scrubbed = _raw_msgs[:-1]
                self._logger.info(
                    "pre_expediente_tariff_gate_self_heal_scrubbed_discarded_msg",
                    conversation_id=conversation_id,
                    scrubbed_content_length=len(
                        getattr(_raw_msgs[-1], "content", "") or ""
                    ),
                )
            else:
                _scrubbed = _raw_msgs

            _retry_state = {
                **initial_state,
                "messages": _scrubbed + [_synthetic_msg],
            }

            # Build and invoke tail loop
            _tail_loop_obj = build_tail_loop(config)
            loop_result = await _tail_loop_obj.graph.ainvoke(
                _retry_state,
                config={"recursion_limit": _tail_loop_obj.recursion_limit},
            )

            # Re-extract result fields from tail loop
            ai_response = loop_result.get("ai_response", "")
            tools_called = loop_result.get("tools_called", [])
            pending_updates = dict(loop_result.get("pending_state_updates") or {})

            # Re-merge pending_state_updates
            shared_context_update_tail = pending_updates.pop("shared_context", None)
            nested_mc_tail = pending_updates.pop("mode_context", None)
            updated_context = {**updated_context, **pending_updates}
            if isinstance(nested_mc_tail, dict):
                updated_context.update(nested_mc_tail)
            if shared_context_update_tail and isinstance(shared_context_update_tail, dict):
                existing_sc = result_dict.get("shared_context") or {}
                existing_sc.update(shared_context_update_tail)
                result_dict["shared_context"] = existing_sc

            # F1: force-propagate precio_comunicado when self-heal succeeded.
            # Spec: sdd/fix-pricing-gate-self-heal-loop — "Post-Self-Heal State
            # Propagation Contract".
            (
                updated_context,
                _propagated_sc,
                tools_called,
                _f1_fired,
            ) = _propagate_post_self_heal_state(
                updated_context=updated_context,
                shared_context=result_dict.get("shared_context") or {},
                tools_called=tools_called,
            )
            if _f1_fired:
                result_dict["shared_context"] = _propagated_sc
                self._logger.info(
                    "pre_expediente_tariff_gate_self_heal_propagated",
                    conversation_id=conversation_id,
                    tools_called_after=tools_called,
                )

            # Update result_dict with tail-loop output
            result_dict["ai_response"] = ai_response
            result_dict["mode_context"] = updated_context

        # ── CAPA 3: Hallucinated-transition self-heal ─────────────────────────
        # Invariant: this block runs AFTER _transition_to propagation (lines above)
        # and BEFORE the CTA 5 gate (below). The CTA gate reads
        # result_dict.get("current_mode") to decide whether to skip enforcement;
        # therefore this block MUST write result_dict["current_mode"] BEFORE the gate.
        #
        # When the LLM emits a kickoff declaration WITHOUT calling confirmar_presupuesto,
        # the mode stays stuck in PRE_EXPEDIENTE. This block detects that condition and
        # applies the same synthetic _state_update that confirmar_presupuesto would have
        # returned, routing through result_dict["current_mode"] (canonical post-propagation
        # channel) and updated_context (mode_context fields).
        #
        # Preconditions (all must be True to fire):
        #   1. No real transition already in result_dict (current_mode falsy)
        #   2. confirmar_presupuesto NOT in tools_called this turn
        #   3. ai_response matches KICKOFF_MARKER_RE (EOS-anchored, last 200 chars)
        #   4. precio_comunicado=True in updated_context
        #   5. tarifa_calculada non-empty in updated_context
        #
        # If markers are present but preconditions 4-5 fail (price not communicated yet),
        # a diagnostic WARNING is emitted without mutating state.
        _has_real_transition = bool(result_dict.get("current_mode"))
        _tool_was_called = "confirmar_presupuesto" in tools_called
        _has_kickoff_marker = is_kickoff_hallucination(ai_response)

        if not _has_real_transition and not _tool_was_called and _has_kickoff_marker:
            _precio_ok = bool(updated_context.get("precio_comunicado"))
            _tarifa_ok = bool(updated_context.get("tarifa_calculada"))

            if _precio_ok and _tarifa_ok:
                # Fire: apply synthetic transition equivalent to confirmar_presupuesto return
                self._logger.warning(
                    "pre_expediente_hallucinated_kickoff_self_heal",
                    conversation_id=conversation_id,
                    tools_called=tools_called,
                    ai_response_tail=ai_response[-120:],
                )
                result_dict["current_mode"] = "EXPEDIENTE_MODE"
                updated_context["expediente_kickoff_pending"] = True
                sc = result_dict.get("shared_context") or {}
                sc["warnings_acknowledged"] = True
                result_dict["shared_context"] = sc
            else:
                # Marker detected but preconditions not satisfied — diagnostic only
                self._logger.warning(
                    "pre_expediente_hallucinated_kickoff_self_heal_preconditions_not_met",
                    conversation_id=conversation_id,
                    tools_called=tools_called,
                    reason="self_heal_preconditions_not_met",
                    precio_comunicado=updated_context.get("precio_comunicado"),
                    tarifa_present=bool(updated_context.get("tarifa_calculada")),
                    ai_response_tail=ai_response[-120:],
                )
        # ── end Capa 3 ────────────────────────────────────────────────────────

        # Mark precio_comunicado=True AFTER the LLM generates its response,
        # but ONLY if calcular_tarifa was called THIS turn. The tariff tool
        # no longer sets this flag — it only populates tarifa_calculada.
        # We check tools_called to avoid false positives when the LLM
        # answers a random question with a stale tarifa in context.
        _tarifa_called_this_turn = "calcular_tarifa_con_elementos" in tools_called
        if (
            _tarifa_called_this_turn
            and updated_context.get("tarifa_calculada")
            and not updated_context.get("precio_comunicado")
        ):
            updated_context["precio_comunicado"] = True
            sc = result_dict.get("shared_context") or {}
            sc["precio_comunicado"] = True
            result_dict["shared_context"] = sc

            # Phase B — compact the calcular_tarifa ToolMessage on price flip.
            # Replaces the full narration (which the LLM would re-read in future turns)
            # with a compact JSON payload. Reads precio and element_codes from tarifa_calculada.
            _tarifa_data = updated_context.get("tarifa_calculada") or {}
            _precio = _tarifa_data.get("price") or _tarifa_data.get("precio_final") or 0.0
            _elem_codes = list(updated_context.get("element_codes") or [])
            _msgs = state.get("messages") or []
            _compact_msg = _find_and_compact_tarifa_message(
                messages=_msgs,
                precio=float(_precio),
                element_codes=_elem_codes,
            )
            if _compact_msg is not None:
                result_dict.setdefault("messages", [])
                result_dict["messages"].append(_compact_msg)

        # --- last_cta_emitted per-turn lifecycle (D4, tool-choice-required-post-price SDD) ---
        # Default-clear to None at the START of CTA 5 gate processing.
        # This ensures the flag lives exactly one turn: a stale "cta_5" from the
        # prior turn is never carried forward unless CTA 5 is re-emitted THIS turn.
        # The overwrite below sets it back to "cta_5" only when the gate fires.
        updated_context["last_cta_emitted"] = None

        # ── AD-9 Output Guard Pipeline ─────────────────────────────────────────
        # Ordered pipeline (design AD-9). Each guard is a pure function; guards
        # only fire outside a mode-transition turn (current_mode would be set).
        # Skip all guards when this turn emits a mode transition — asking
        # "¿Abrimos expediente?" right before EXPEDIENTE_MODE confuses the user.

        if not result_dict.get("current_mode"):
            _cid = state.get("conversation_id", "")

            # Step 1 — R-3: strip premature transition claims
            result_dict["ai_response"] = guard_no_premature_transition_claim(
                text=result_dict["ai_response"],
                mc=updated_context,
                pending_updates=pending_updates,
                node_logger=self._logger,
                conversation_id=_cid,
            )

            # Step 2 — R-2: strip premature price sentences + CTA/footer artifacts.
            # _strip_premature_price_artifacts is a semantics-preserving wrapper
            # around guard_no_premature_price (AD-8) that also strips the CTA/footer
            # artifact set from the old L3 tariff-gate red-net.
            result_dict["ai_response"] = _strip_premature_price_artifacts(
                ai_response=result_dict["ai_response"],
                precio_comunicado=bool(updated_context.get("precio_comunicado")),
                tarifa_calculada=updated_context.get("tarifa_calculada"),
            )

            # Step 3 — R-1: strip hallucinated image-failure paragraphs.
            # guard_image_send_truth replaces the old _strip_false_image_failure_phrasing
            # (regex-based) with a state-grounded, paragraph-level guard (AD-2, AD-3).
            result_dict["ai_response"] = guard_image_send_truth(
                text=result_dict["ai_response"],
                mc=updated_context,
                node_logger=self._logger,
                conversation_id=_cid,
            )

            # Step 3.5 — R-8/R-5: strip budget re-narration in POST_PRICE turns.
            # Fires only when precio_comunicado=True AND reprice_allowed_this_turn
            # is not True. Protects against the LLM echoing the full price narration
            # in POST_PRICE territory; paragraph-level, strips matching paragraphs.
            result_dict["ai_response"] = guard_no_reprice_post_price(
                text=result_dict["ai_response"],
                mc=updated_context,
                node_logger=self._logger,
                conversation_id=_cid,
            )

            # Step 3.6 — R-11: conversational regurgitation guard (no tool fired).
            # Fires only when precio_comunicado=True AND no tool called AND not a
            # reprice turn AND LLM output contains ≥2 distinct budget signals.
            # Replaces the ENTIRE ai_response with the "ya te comuniqué" canned message.
            # Runs AFTER R-5 (Step 3.5) so paragraph-stripping gets first pass when
            # a tool DID fire; this step catches the free-text "no-tool" case.
            result_dict["ai_response"] = guard_no_reprice_without_tool(
                text=result_dict["ai_response"],
                mc=updated_context,
                tools_called_this_turn=tools_called,
                node_logger=self._logger,
                conversation_id=_cid,
            )

            # Step 4 — R-4: strip CTAs incompatible with the current phase.
            # Phase is inferred from updated_context (same logic as prompt loader).
            if updated_context.get("precio_comunicado"):
                _phase = "PRE_EXPEDIENTE_POST_PRICE"
            elif updated_context.get("element_codes"):
                _phase = "PRE_EXPEDIENTE_PRICING"
            else:
                _phase = "PRE_EXPEDIENTE_DISCOVERY"

            result_dict["ai_response"] = guard_cta_policy(
                text=result_dict["ai_response"],
                mc=updated_context,
                phase=_phase,
                node_logger=self._logger,
                conversation_id=_cid,
            )

            # Step 5 — Enforce CTA 5 deterministically (escenario 7.bis / regla 9).
            # _enforce_cta5_if_needed is a pure function: appends if missing,
            # normalises tuteo drift, no-ops if already present.
            result_dict["ai_response"] = _enforce_cta5_if_needed(
                ai_response=result_dict["ai_response"],
                precio_comunicado=bool(updated_context.get("precio_comunicado")),
                imagenes_enviadas_codigos=updated_context.get("imagenes_enviadas_codigos") or [],
            )
            # Set last_cta_emitted flag when CTA 5 was appended/enforced.
            # Covers all three enforcement branches (append / normalize tuteo / emit-alone)
            # because _enforce_cta5_if_needed guarantees result ends with _CTA_5 when it fires.
            if result_dict["ai_response"].endswith(_CTA_5):
                updated_context["last_cta_emitted"] = "cta_5"

        # Step 6 — voseo_to_tuteo is applied in main.py via strip_markdown_for_whatsapp.
        # ── end AD-9 pipeline ──────────────────────────────────────────────────

        # AD-Y2 reset: reprice_allowed_this_turn is turn-scoped — must not leak.
        # Spec R9-S9.2. Write tombstone (None) per ADR-010 so merge_dicts does not
        # resurrect a stale True from the Redis checkpoint in the next turn.
        updated_context, result_dict = _reset_reprice_flag_if_set(
            updated_context, result_dict
        )

        return result_dict

    def get_tools(self, mode_context: dict | None = None) -> list:
        """Return tools available in PRE_EXPEDIENTE_MODE.

        R4 — Structural tool restriction:
        When pending_variants is non-empty, restrict to variant-resolution tools only.
        This is a temporary, narrow restriction lifted immediately once all variants resolve.
        Structurally prevents re-identification while a variant question is active.
        """
        pending = (mode_context or {}).get("pending_variants") or []
        unresolved = [v for v in pending if v.get("status") != "resolved"]
        if unresolved:
            # Restrict: only variant resolution + universal escalation tool
            from agent.tools.element_tools import seleccionar_variante_por_respuesta
            from agent.tools.shared_tools import escalar_a_humano

            return [seleccionar_variante_por_respuesta, escalar_a_humano]
        # Full toolset — cache for reuse
        if self._tools is None:
            self._tools = _get_pre_expediente_tools()
        return self._tools

    # ------------------------------------------------------------------
    # LLM helpers — delegated to BaseModeNode
    # ------------------------------------------------------------------
    # _get_llm() and _invoke_with_fallback() are inherited from BaseModeNode.
    # _default_max_tokens = 3000 overrides the base default (1500) so that
    # PRE_EXPEDIENTE responses are never truncated with large system prompts.

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    # _execute_tool inherited from BaseModeNode

    # ------------------------------------------------------------------
    # Context extraction from tool results
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_context_from_tool(
        tool_name: str,
        tool_args: dict[str, Any],
        result: str,
        current_element_codes: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Extract mode context updates from a tool call and its result.

        Same logic as PresupuestoModeNode, plus:
        - Tracks precio_comunicado for price-before-images enforcement
        - Tracks presupuesto_completado when price is calculated

        Args:
            current_element_codes: Current element_codes from mode_context, used to
                accumulate codes across multiple seleccionar_variante_por_respuesta
                calls in the same turn (fixes blocked_stale_budget_scope bug).
        """
        updates: dict[str, Any] = {}

        try:
            data = json.loads(result) if isinstance(result, str) else result
        except (json.JSONDecodeError, TypeError):
            return updates

        if not isinstance(data, dict):
            return updates

        if tool_name == "identificar_y_resolver_elementos":
            # Skip context extraction on error results — failed tool calls
            # produce no valid context and would corrupt mode_context with
            # wrong values (e.g. categoria_slug from the failed request).
            if data.get("error"):
                return updates

            # IMPORTANT: Clear previous identification/pricing data
            # With merge_dicts reducer, we must explicitly clear obsolete fields
            # to prevent stale data from previous queries confusing the LLM
            updates["tarifa_calculada"] = None
            # REFACTOR-001: Flag resets (precio_comunicado, imagenes_enviadas)
            # now handled by _internal_flags in tool return value

            listos = data.get("elementos_listos", [])
            variantes = data.get("elementos_con_variantes", [])
            preguntas = data.get("preguntas_variantes", [])

            # Codes from elementos_listos are always valid (no variant needed)
            ready_codes = [e.get("codigo") for e in listos if e.get("codigo")]

            if listos and not variantes:
                updates["elemento_confirmado"] = listos[0] if len(listos) == 1 else None
                # T-09: Additive merge — re-identification extends codes, doesn't replace
                existing_codes = set(current_element_codes or [])
                updates["element_codes"] = list(existing_codes | set(ready_codes))
                # REFACTOR-001: Removed variante_resuelta - derived from len(pending_variants) == 0
                updates["elemento_tentativo"] = None  # Clear tentative
                updates["pending_variants"] = []  # Clear variant questions
            elif variantes:
                updates["elemento_tentativo"] = variantes[0]
                # REFACTOR-001: Removed variante_resuelta - derived from len(pending_variants) == 0
                updates["pending_variants"] = preguntas
                updates["elemento_confirmado"] = None  # Clear confirmed
                # T-09: Additive merge for partial codes (elements without variants)
                # Previously this cleared element_codes entirely (RC-2a), which
                # dropped elements that had no variants (e.g. PLACA_SOLAR) when
                # other elements did have variants (e.g. TOLDO_LAT).
                existing_codes = set(current_element_codes or [])
                updates["element_codes"] = list(existing_codes | set(ready_codes))

            # Read from tool result first (robust), fallback to tool_args
            updates["categoria_slug"] = (
                data.get("categoria_slug")
                or tool_args.get("categoria_vehiculo")
                or tool_args.get("categoria")
            )

        elif tool_name == "seleccionar_variante_por_respuesta":
            # Detect successful selection — tool returns "selected_variant" (single)
            # or "selected_variants" (multi-select), NOT "success" or "codigo"
            has_selection = bool(
                data.get("selected_variant")
                or data.get("selected_variants")
                or data.get("success")  # forward compat
                or data.get("codigo")  # legacy compat
            )
            confidence = data.get("confidence", 1.0)
            is_confident = confidence >= VARIANT_CONFIDENCE_THRESHOLD or data.get("mode") == "multi_select"

            if has_selection and not data.get("error") and is_confident:
                # ══════════════════════════════════════════════════════════
                # FIX: Incremental pending_variants update (no premature clear)
                # If the tool returned updated pending_variants via _internal_flags,
                # use that. Otherwise, for legacy single-selection, check if all
                # entries are resolved before clearing.
                # ══════════════════════════════════════════════════════════
                from agent.state.helpers import normalize_pending_variants

                # Dual-reader: prefer _state_update (new canonical), fall back to _internal_flags
                tool_flags = data.get("_state_update") or data.get(
                    "_internal_flags", {}
                )
                tool_pending = tool_flags.get("pending_variants")

                if tool_pending is not None:
                    # Tool provided authoritative updated state — use it directly
                    normalized = normalize_pending_variants(tool_pending)
                    all_resolved = all(
                        pv.get("status") == "resolved" for pv in normalized
                    )
                    if all_resolved:
                        updates["pending_variants"] = []
                    else:
                        updates["pending_variants"] = [dict(pv) for pv in normalized]
                else:
                    # Legacy path: single variant resolved without enriched state.
                    # DO NOT blanket-clear all pending_variants — other elements
                    # may still have unresolved variants in a multi-element scenario.
                    # The modern tool always provides _internal_flags.pending_variants,
                    # so this path only fires for truly legacy callers.
                    # Leaving pending_variants UNSET here preserves the existing
                    # mode_context entries. The calcular_tarifa_con_elementos tool
                    # has its own guard that blocks calculation if unresolved
                    # variants remain.
                    pass

                # Single variant selection
                code = (
                    data.get("selected_variant")
                    or data.get("codigo")
                    or data.get("code")
                )
                if code:
                    updates["elemento_confirmado"] = {
                        "code": code,
                        "name": data.get("name") or data.get("nombre", code),
                    }
                    # FIX: Accumulate codes across multiple seleccionar_variante calls
                    # in the same turn. Previously `= [code]` would overwrite the list
                    # on each call, leaving only the last resolved variant in
                    # mode_context["element_codes"]. This caused the guardrail in
                    # enviar_imagenes_ejemplo to fire (blocked_stale_budget_scope)
                    # because mode_context had 1 code but tarifa_calculada had 2+.
                    existing = list(current_element_codes or [])
                    if code not in existing:
                        existing.append(code)
                    updates["element_codes"] = existing

                # Multi-select variant selection
                elif data.get("selected_variants"):
                    codes = data["selected_variants"]
                    updates["element_codes"] = codes
                    names = data.get("names", codes)
                    updates["elemento_confirmado"] = {
                        "code": codes[0],
                        "name": names[0] if names else codes[0],
                    }
            # If "error" in response, do NOT clear pending_variants — keep blocking calcular_tarifa

        elif tool_name == "calcular_tarifa_con_elementos":
            # Skip context extraction on error — don't store error dicts as tarifa
            if data.get("error") or data.get("success") is False:
                return updates

            # Handle nested structure: tool returns {texto, datos: {price, ...}, ...}
            # REFACTOR-001: Removed precio_calculado redundant field - use tarifa_calculada directly
            updates["tarifa_calculada"] = (
                data  # Store full response including imagenes_ejemplo
            )
            # NOTE: precio_comunicado and imagenes_enviadas flags are managed
            # in _process_message to avoid accessing mode_context in static method
            # NOTE: NO longer propagate to root state (_tarifa_actual removed)
            # Tools access tarifa_calculada directly from mode_context

            # RC-2b: Sync element_codes from tarifa result (authoritative source).
            # Only applied on success and when datos.element_codes is non-empty.
            if data.get("success") is not False:
                _datos = data.get("datos", {})
                if isinstance(_datos, dict):
                    _tarifa_codes = _datos.get("element_codes", [])
                    if _tarifa_codes:
                        updates["element_codes"] = _tarifa_codes
                        logger.debug(
                            "element_codes_synced_from_tarifa",
                            count=len(_tarifa_codes),
                            codes=_tarifa_codes,
                        )

            # ── Populate elementos_confirmados for rich variant handoff to EXPEDIENTE ──
            # Build a list of {code, name, variant_of} from the tariff response.
            # This data survives the PRE_EXPEDIENTE → EXPEDIENTE transition via
            # shared_context (WS4) so EXPEDIENTE knows exactly which elements
            # (including variant detail) were priced.
            if data.get("success") is not False:
                elementos: list[dict[str, Any]] = []
                datos = data.get("datos", {})
                if isinstance(datos, dict):
                    element_names = datos.get("elements", [])
                    element_codes = datos.get("element_codes", [])
                    # Zip codes and names together for rich entries
                    for idx, code in enumerate(element_codes):
                        name = element_names[idx] if idx < len(element_names) else code
                        elementos.append(
                            {
                                "code": code,
                                "name": name,
                                "variant_of": None,  # Not available in tariff response
                            }
                        )

                # Fallback: derive from element_codes if datos lacked detail
                if not elementos:
                    codes = (
                        datos.get("element_codes", [])
                        if isinstance(datos, dict)
                        else []
                    ) or data.get("element_codes", [])
                    if not codes:
                        # Last resort: try from mode_context via current_element_codes
                        codes = current_element_codes or []
                    elementos = [
                        {"code": c, "name": c, "variant_of": None} for c in codes
                    ]

                if elementos:
                    updates["elementos_confirmados"] = elementos
                    logger.info(
                        "elementos_confirmados_populated",
                        count=len(elementos),
                        codes=[e["code"] for e in elementos],
                    )

        elif tool_name == "identificar_tipo_vehiculo":
            # Skip context extraction on error
            if data.get("error"):
                return updates

            categoria = data.get("categoria_sugerida") or data.get("category_slug")
            if categoria:
                updates["categoria_slug"] = categoria
            marca = data.get("marca")
            modelo = data.get("modelo")
            if marca or modelo:
                updates["vehiculo"] = {
                    "marca": marca or "desconocida",
                    "modelo": modelo or "desconocido",
                }

        elif tool_name == "enviar_imagenes_ejemplo":
            pass  # Flag managed by _internal_flags (REFACTOR-001)

        return updates

    @staticmethod
    def _extract_pending_images(result: str) -> dict[str, Any] | None:
        """
        Extract pending images payload from enviar_imagenes_ejemplo result.

        The tool returns _pending_images in its result dict which contains
        the actual image URLs to send via Chatwoot.
        """
        try:
            data = json.loads(result) if isinstance(result, str) else result
        except (json.JSONDecodeError, TypeError):
            return None

        if not isinstance(data, dict):
            return None

        return data.get("_pending_images")

    # ------------------------------------------------------------------
    # Client context builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_client_context(state: ConversationState) -> str:
        """Build the client-specific context string for the prompt."""
        parts: list[str] = []

        client_type = state.get("client_type", "particular")
        type_display = "PROFESIONAL" if client_type == "professional" else "PARTICULAR"
        parts.append(f"Cliente: **{type_display}**")
        parts.append(f'Usa tipo_cliente: "{client_type}" en herramientas.')

        user_name = state.get("user_name")
        if user_name:
            parts.append(f"Nombre: {user_name}")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Message conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ai_message_to_dict(response: Any) -> dict[str, Any]:
        """Convert an LLM AIMessage to a dict for the messages list."""
        msg: dict[str, Any] = {
            "role": "assistant",
            "content": response.content or "",
        }
        if hasattr(response, "tool_calls") and response.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "name": tc["name"],
                    "args": tc["args"],
                }
                for tc in response.tool_calls
            ]
        return msg

    @staticmethod
    def _log_token_usage(response: Any, conversation_id: str) -> None:
        """Log token usage from LLM response metadata."""
        usage = getattr(response, "usage_metadata", None)
        if usage:
            logger.debug(
                "llm_token_usage",
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                conversation_id=conversation_id,
            )


# ---------------------------------------------------------------------------
# Tool registry for PRE_EXPEDIENTE_MODE
# ---------------------------------------------------------------------------


def _get_pre_expediente_tools() -> list:
    """
    Get the 10-tool superset for PRE_EXPEDIENTE_MODE.

    Merges tools from former CONSULTA_MODE and PRESUPUESTO_MODE:
    - All element identification + pricing + image tools from PRESUPUESTO
    - obtener_servicios_adicionales from CONSULTA (informational)

    Dynamic filtering in _get_tools_with_filtering() further restricts
    the active set based on conversation phase (gates 1, 3, 4, 5).
    NOTE: obtener_documentacion_elemento removed (T-04). Doc info is now
    embedded in identificar_y_resolver_elementos response (Batch 2, T-05).
    """
    from agent.tools.element_tools import (
        identificar_y_resolver_elementos,
        seleccionar_variante_por_respuesta,
        calcular_tarifa_con_elementos,
        listar_elementos,
    )
    from agent.tools.tarifa_tools import listar_categorias, obtener_servicios_adicionales
    from agent.tools.vehicle_tools import identificar_tipo_vehiculo
    from agent.tools.image_tools import enviar_imagenes_ejemplo
    from agent.tools.transition_tools import confirmar_presupuesto
    from agent.tools.shared_tools import escalar_a_humano

    return [
        # Element identification & resolution
        identificar_y_resolver_elementos,
        seleccionar_variante_por_respuesta,
        # Exact pricing
        calcular_tarifa_con_elementos,
        # Example images (after price communication)
        enviar_imagenes_ejemplo,
        # Transition to EXPEDIENTE_MODE (confirm quote → open case)
        confirmar_presupuesto,
        # Catalog browsing
        listar_categorias,
        listar_elementos,
        # Additional services (from CONSULTA_MODE)
        obtener_servicios_adicionales,
        # Vehicle classification
        identificar_tipo_vehiculo,
        # Universal
        escalar_a_humano,
    ]


# ---------------------------------------------------------------------------
# T3.2: Module-level DraftQuote helpers (Phase 3)
#
# These are module-level functions (not class methods) so they can be
# patched in tests without instantiating PreExpedienteModeNode.
# ---------------------------------------------------------------------------


async def _load_active_draft_quote(conversation_id: str):
    """
    Load the active DraftQuote for a conversation from the database.

    Module-level so it can be easily mocked in tests.

    Returns:
        DraftQuote ORM instance, or None if not found.
    """
    from agent.tools.draft_quote_service import (
        _load_active_draft_quote as _svc_load,
    )

    return await _svc_load(conversation_id)


async def _load_active_draft_quote_into_context(
    conversation_id: str,
    mode_context: dict,
) -> None:
    """
    Load the active DraftQuote and inject draft_* keys into mode_context.

    Called at the start of PRE_EXPEDIENTE_MODE processing so the LLM can
    answer "¿cuánto era el presupuesto?" without recalculating.

    If no DraftQuote is found, mode_context is NOT modified.
    Errors are caught silently — never block the agent.

    Args:
        conversation_id: Conversation UUID as string.
        mode_context: Mode context dict (mutated in-place if draft found).
    """
    try:
        draft = await _load_active_draft_quote(conversation_id)
        if draft:
            mode_context["draft_precio"] = str(draft.precio_final)
            mode_context["draft_elements"] = draft.elements
            mode_context["draft_category"] = draft.category_slug
    except Exception as exc:
        logger.warning(
            "draft_quote_load_into_context_failed",
            conversation_id=conversation_id,
            error=str(exc),
        )
