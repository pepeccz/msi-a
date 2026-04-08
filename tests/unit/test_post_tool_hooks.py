"""
Unit tests for presupuesto_post_tool_hook wiring fix (fix-extract-context-dead-code).

TDD: Tests written FIRST (RED), then implementation (GREEN).

Placed in tests/unit/ so that tests/unit/conftest.py stubs for
langgraph.checkpoint.redis are in effect before agent.* imports.

Spec scenarios covered:
  S1  — identificar, no variants → element_codes + categoria_slug populated
  S2  — identificar, variants → pending_variants LIST (not bool)
  S3  — seleccionar_variante → element_codes accumulated
  S4  — calcular_tarifa success → precio_comunicado + price_authority_confirmed
  S5  — enviar_imagenes → imagenes_enviadas set
  S6  — _extract_tool_args_from_messages happy path (AIMessage present)
  S7  — _extract_tool_args_from_messages graceful fallback when no AIMessage
  S8  — variant_pending bool NOT written to updates (dead code removed)
  S9  — _extract_tool_args_from_messages match by tool_name, last AIMessage wins
  S10 — calcular_tarifa success populates elementos_confirmados + tarifa_calculada
  S11 — Exception in _extract_context_from_tool does not propagate (warning logged)
"""

from __future__ import annotations

import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(
    tool_name: str,
    tool_args: dict,
    tool_call_id: str = "call_001",
    mode_context: dict | None = None,
) -> dict:
    """
    Build a minimal hook_state that mirrors what post_tool_node passes.

    Includes an AIMessage with a tool_calls entry so _extract_tool_args_from_messages
    can find the args.
    """
    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "id": tool_call_id,
                "name": tool_name,
                "args": tool_args,
                "type": "tool_call",
            }
        ],
    )
    return {
        "messages": [
            HumanMessage(content="Hola"),
            ai_msg,
        ],
        "_mode_context": mode_context or {},
        "_conversation_id": "test-conv-001",
    }


def _identificar_result(
    *,
    elementos_listos: list[dict] | None = None,
    elementos_con_variantes: list[dict] | None = None,
    preguntas_variantes: list[dict] | None = None,
    categoria_slug: str = "motos-part",
) -> dict:
    """Build a result dict for identificar_y_resolver_elementos."""
    result: dict = {"success": True, "categoria_slug": categoria_slug}
    if elementos_listos is not None:
        result["elementos_listos"] = elementos_listos
    if elementos_con_variantes is not None:
        result["elementos_con_variantes"] = elementos_con_variantes
    if preguntas_variantes is not None:
        result["preguntas_variantes"] = preguntas_variantes
    # Add _state_update so post_tool_node would have called the hook
    result["_state_update"] = {"precio_comunicado": False}
    return result


def _calcular_result(
    precio_final: float = 410.0,
    element_codes: list[str] | None = None,
    success: bool = True,
) -> dict:
    """Build a result dict for calcular_tarifa_con_elementos."""
    datos = {
        "price": precio_final,
        "elements": ["Escape", "Escape original"],
        "element_codes": element_codes or ["ESCAPE", "ESCAPE_ORIGINAL"],
        "tier_name": "Proyecto Básico",
    }
    return {
        "success": success,
        "precio_final": precio_final,
        "datos": datos,
        "_state_update": {
            "precio_comunicado": True,
            "imagenes_enviadas": False,
        },
    }


# ===========================================================================
# GROUP 1 — _extract_tool_args_from_messages helper
# ===========================================================================


class TestExtractToolArgsFromMessages:
    """Unit tests for _extract_tool_args_from_messages helper function."""

    def test_happy_path_returns_args_for_matching_tool(self):
        """
        S6 — Happy path: AIMessage with tool_calls present, tool_name matches.
        The function must return the args dict for that tool call.
        """
        from agent.modes.post_tool_hooks import _extract_tool_args_from_messages

        expected_args = {"categoria_vehiculo": "motos-part", "elementos": ["escape"]}
        ai_msg = AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_abc",
                    "name": "identificar_y_resolver_elementos",
                    "args": expected_args,
                    "type": "tool_call",
                }
            ],
        )
        state = {"messages": [HumanMessage(content="Hola"), ai_msg]}

        result = _extract_tool_args_from_messages(
            state, "identificar_y_resolver_elementos"
        )

        assert result == expected_args, f"Expected {expected_args}, got {result}"

    def test_no_aimessage_returns_empty_dict(self):
        """
        S7 — No AIMessage in state → fallback to empty dict, no exception raised.
        """
        from agent.modes.post_tool_hooks import _extract_tool_args_from_messages

        state = {"messages": [HumanMessage(content="¿Qué precio tiene?")]}

        result = _extract_tool_args_from_messages(
            state, "identificar_y_resolver_elementos"
        )

        assert result == {}, "With no AIMessage, must return {} gracefully"

    def test_tool_name_mismatch_returns_empty_dict(self):
        """
        S9 — AIMessage present but tool_name doesn't match any tool_call.name.
        Must return {} (no match, no exception).
        """
        from agent.modes.post_tool_hooks import _extract_tool_args_from_messages

        ai_msg = AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_x",
                    "name": "calcular_tarifa_con_elementos",
                    "args": {"categoria": "motos-part"},
                    "type": "tool_call",
                }
            ],
        )
        state = {"messages": [ai_msg]}

        # Asking for a DIFFERENT tool name → no match
        result = _extract_tool_args_from_messages(
            state, "identificar_y_resolver_elementos"
        )

        assert result == {}, (
            "When tool_name doesn't match any tool_call, must return {}"
        )

    def test_finds_last_aimessage_when_multiple_messages(self):
        """
        S9 variant: Multiple messages including ToolMessages and HumanMessages.
        Must walk backwards and find the LAST AIMessage.
        """
        from agent.modes.post_tool_hooks import _extract_tool_args_from_messages

        # First AIMessage (older) — should NOT be used
        first_ai_msg = AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_old",
                    "name": "identificar_y_resolver_elementos",
                    "args": {"categoria_vehiculo": "aseicars"},
                    "type": "tool_call",
                }
            ],
        )
        # Latest AIMessage — should be used
        last_ai_msg = AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_new",
                    "name": "identificar_y_resolver_elementos",
                    "args": {"categoria_vehiculo": "motos-part"},
                    "type": "tool_call",
                }
            ],
        )
        state = {
            "messages": [
                HumanMessage(content="Quiero homologar"),
                first_ai_msg,
                ToolMessage(content="{}", tool_call_id="call_old"),
                HumanMessage(content="Motos"),
                last_ai_msg,
            ]
        }

        result = _extract_tool_args_from_messages(
            state, "identificar_y_resolver_elementos"
        )

        assert result == {"categoria_vehiculo": "motos-part"}, (
            f"Must use the LAST AIMessage's args, got: {result}"
        )

    def test_empty_messages_returns_empty_dict(self):
        """Edge case: messages list is empty → {} gracefully."""
        from agent.modes.post_tool_hooks import _extract_tool_args_from_messages

        result = _extract_tool_args_from_messages({"messages": []}, "any_tool")
        assert result == {}

    def test_missing_messages_key_returns_empty_dict(self):
        """Edge case: state has no 'messages' key → {} gracefully."""
        from agent.modes.post_tool_hooks import _extract_tool_args_from_messages

        result = _extract_tool_args_from_messages({}, "any_tool")
        assert result == {}


# ===========================================================================
# GROUP 2 — identificar_y_resolver_elementos, no variants
# ===========================================================================


class TestIdentificarNoVariants:
    """
    S1 — After identificar_y_resolver_elementos with elementos_listos,
    mode_context must contain element_codes (list) and categoria_slug.
    """

    @pytest.mark.asyncio
    async def test_element_codes_populated_no_variants(self):
        """
        S1 — identificar returns elementos_listos → element_codes list populated.
        element_codes must be a non-empty list containing the element codes.
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        tool_args = {"categoria_vehiculo": "motos-part", "elementos": ["escape"]}
        result_dict = _identificar_result(
            elementos_listos=[
                {"codigo": "ESCAPE", "nombre": "Escape", "tipo": "elemento"}
            ],
            categoria_slug="motos-part",
        )
        state = _make_state(
            "identificar_y_resolver_elementos", tool_args, mode_context={}
        )

        updates = await presupuesto_post_tool_hook(
            "identificar_y_resolver_elementos", result_dict, state
        )

        mc = updates.get("mode_context", {})
        assert isinstance(mc.get("element_codes"), list), "element_codes must be a list"
        assert len(mc["element_codes"]) > 0, (
            "element_codes must be non-empty after identificar with elementos_listos"
        )
        assert "ESCAPE" in mc["element_codes"], (
            f"'ESCAPE' must be in element_codes, got: {mc['element_codes']}"
        )

    @pytest.mark.asyncio
    async def test_categoria_slug_populated_no_variants(self):
        """
        S1 — identificar returns categoria_slug in result → mode_context has it set.
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        tool_args = {"categoria_vehiculo": "motos-part"}
        result_dict = _identificar_result(
            elementos_listos=[{"codigo": "MANILLAR", "nombre": "Manillar"}],
            categoria_slug="motos-part",
        )
        state = _make_state(
            "identificar_y_resolver_elementos", tool_args, mode_context={}
        )

        updates = await presupuesto_post_tool_hook(
            "identificar_y_resolver_elementos", result_dict, state
        )

        mc = updates.get("mode_context", {})
        assert mc.get("categoria_slug") == "motos-part", (
            f"categoria_slug must be 'motos-part', got: {mc.get('categoria_slug')!r}"
        )

    @pytest.mark.asyncio
    async def test_pending_variants_empty_list_no_variants(self):
        """
        S1 — After clean identificar (no variants), pending_variants must be [].
        It must NOT be a bool and NOT be absent.
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        result_dict = _identificar_result(
            elementos_listos=[{"codigo": "ESCAPE", "nombre": "Escape"}],
        )
        state = _make_state("identificar_y_resolver_elementos", {}, mode_context={})

        updates = await presupuesto_post_tool_hook(
            "identificar_y_resolver_elementos", result_dict, state
        )

        mc = updates.get("mode_context", {})
        pending = mc.get("pending_variants")
        assert isinstance(pending, list), (
            f"pending_variants must be a list, got {type(pending).__name__}: {pending!r}"
        )
        assert pending == [], (
            f"pending_variants must be [] when no variants, got: {pending!r}"
        )

    @pytest.mark.asyncio
    async def test_variant_pending_bool_not_written(self):
        """
        S8 — variant_pending bool MUST NOT appear in updates dict (dead code removed).
        The old hook wrote 'variant_pending: False' here — this must be gone.
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        result_dict = _identificar_result(
            elementos_listos=[{"codigo": "ESCAPE", "nombre": "Escape"}],
        )
        state = _make_state("identificar_y_resolver_elementos", {}, mode_context={})

        updates = await presupuesto_post_tool_hook(
            "identificar_y_resolver_elementos", result_dict, state
        )

        assert "variant_pending" not in updates, (
            "variant_pending bool must NOT be written to updates (dead code removed)"
        )


# ===========================================================================
# GROUP 3 — identificar_y_resolver_elementos with variants
# ===========================================================================


class TestIdentificarWithVariants:
    """
    S2 — After identificar_y_resolver_elementos with preguntas_variantes,
    mode_context must contain pending_variants as a LIST (not a bool).
    """

    @pytest.mark.asyncio
    async def test_pending_variants_is_list_not_bool(self):
        """
        S2 — Core: pending_variants must be a non-empty LIST, NOT a bool True.
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        preguntas = [
            {
                "codigo_base": "SUSPENSION",
                "pregunta": "¿Delantera o trasera?",
                "opciones": ["Delantera", "Trasera"],
                "status": "pending",
            }
        ]
        result_dict = _identificar_result(
            elementos_con_variantes=[{"codigo_base": "SUSPENSION"}],
            preguntas_variantes=preguntas,
        )
        state = _make_state("identificar_y_resolver_elementos", {}, mode_context={})

        updates = await presupuesto_post_tool_hook(
            "identificar_y_resolver_elementos", result_dict, state
        )

        mc = updates.get("mode_context", {})
        pending = mc.get("pending_variants")

        # MUST be a list, not a bool
        assert isinstance(pending, list), (
            f"pending_variants must be a list (not bool), got: {type(pending).__name__}: {pending!r}"
        )
        assert len(pending) > 0, (
            "pending_variants must be non-empty when variants detected"
        )

    @pytest.mark.asyncio
    async def test_pending_variants_contains_variant_dicts(self):
        """
        S2 — pending_variants list must contain the variant question dicts.
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        preguntas = [
            {
                "codigo_base": "SUSPENSION",
                "pregunta": "¿Delantera o trasera?",
                "opciones": ["Delantera", "Trasera"],
                "status": "pending",
            }
        ]
        result_dict = _identificar_result(
            elementos_con_variantes=[{"codigo_base": "SUSPENSION"}],
            preguntas_variantes=preguntas,
        )
        state = _make_state("identificar_y_resolver_elementos", {}, mode_context={})

        updates = await presupuesto_post_tool_hook(
            "identificar_y_resolver_elementos", result_dict, state
        )

        mc = updates.get("mode_context", {})
        pending = mc.get("pending_variants", [])

        # Each entry should be a dict with variant question data
        assert all(isinstance(v, dict) for v in pending), (
            "All pending_variants entries must be dicts"
        )
        assert any(v.get("codigo_base") == "SUSPENSION" for v in pending), (
            f"Expected SUSPENSION variant in pending_variants, got: {pending}"
        )

    @pytest.mark.asyncio
    async def test_element_codes_cleared_when_variants_detected(self):
        """
        S2 — When variants are detected, element_codes must be [] (cleared).
        No resolved codes yet.
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        preguntas = [
            {
                "codigo_base": "SUSPENSION",
                "pregunta": "¿Delantera o trasera?",
                "opciones": ["Delantera", "Trasera"],
                "status": "pending",
            }
        ]
        result_dict = _identificar_result(
            elementos_con_variantes=[{"codigo_base": "SUSPENSION"}],
            preguntas_variantes=preguntas,
        )
        state = _make_state(
            "identificar_y_resolver_elementos",
            {},
            mode_context={"element_codes": ["STALE_CODE"]},
        )

        updates = await presupuesto_post_tool_hook(
            "identificar_y_resolver_elementos", result_dict, state
        )

        mc = updates.get("mode_context", {})
        assert mc.get("element_codes") == [], (
            f"element_codes must be [] when variants detected, got: {mc.get('element_codes')!r}"
        )

    @pytest.mark.asyncio
    async def test_variant_pending_bool_not_written_when_variants(self):
        """
        S8 — variant_pending bool MUST NOT appear in updates (removed dead code).
        Old hook wrote 'variant_pending: True' for the variants case — must be gone.
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        preguntas = [
            {
                "codigo_base": "SUSPENSION",
                "pregunta": "?",
                "opciones": [],
                "status": "pending",
            }
        ]
        result_dict = _identificar_result(
            elementos_con_variantes=[{"codigo_base": "SUSPENSION"}],
            preguntas_variantes=preguntas,
        )
        state = _make_state("identificar_y_resolver_elementos", {}, mode_context={})

        updates = await presupuesto_post_tool_hook(
            "identificar_y_resolver_elementos", result_dict, state
        )

        assert "variant_pending" not in updates, (
            "variant_pending bool must NOT be written to root updates"
        )


# ===========================================================================
# GROUP 4 — seleccionar_variante_por_respuesta
# ===========================================================================


class TestSeleccionarVariante:
    """
    S3 — After seleccionar_variante_por_respuesta resolves a variant,
    element_codes must be accumulated (not overwritten).
    """

    @pytest.mark.asyncio
    async def test_element_codes_accumulated(self):
        """
        S3 — When variant resolves, new code is ADDED to existing element_codes
        (not replaced). Current codes come from mode_context.
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        result_dict = {
            "success": True,
            "selected_variant": "SUSPENSION_DELANTERA",
            "name": "Suspensión delantera",
            "_state_update": {},
        }
        state = _make_state(
            "seleccionar_variante_por_respuesta",
            {"codigo_base": "SUSPENSION", "respuesta": "delantera"},
            # Prior codes already in mode_context
            mode_context={"element_codes": ["ESCAPE"]},
        )

        updates = await presupuesto_post_tool_hook(
            "seleccionar_variante_por_respuesta", result_dict, state
        )

        mc = updates.get("mode_context", {})
        codes = mc.get("element_codes", [])

        assert isinstance(codes, list), "element_codes must be a list"
        assert "SUSPENSION_DELANTERA" in codes, (
            f"Resolved code must be in element_codes, got: {codes}"
        )
        # Accumulation: prior code must still be there
        assert "ESCAPE" in codes, (
            f"Prior element code 'ESCAPE' must be preserved in accumulation, got: {codes}"
        )

    @pytest.mark.asyncio
    async def test_elemento_confirmado_set(self):
        """
        S3 — elemento_confirmado must be set with code and name after resolution.
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        result_dict = {
            "success": True,
            "selected_variant": "SUSPENSION_TRASERA",
            "name": "Suspensión trasera",
            "_state_update": {},
        }
        state = _make_state(
            "seleccionar_variante_por_respuesta",
            {"codigo_base": "SUSPENSION"},
            mode_context={},
        )

        updates = await presupuesto_post_tool_hook(
            "seleccionar_variante_por_respuesta", result_dict, state
        )

        mc = updates.get("mode_context", {})
        ec = mc.get("elemento_confirmado")

        assert isinstance(ec, dict), f"elemento_confirmado must be a dict, got: {ec!r}"
        assert ec.get("code") == "SUSPENSION_TRASERA", (
            f"elemento_confirmado.code must be 'SUSPENSION_TRASERA', got: {ec!r}"
        )


# ===========================================================================
# GROUP 5 — calcular_tarifa_con_elementos
# ===========================================================================


class TestCalcularTarifa:
    """
    S4 — After calcular_tarifa_con_elementos succeeds:
      - price_authority_confirmed = True (root-level)
      - mode_context.precio_comunicado = True
      - mode_context.tarifa_calculada is populated
      - mode_context.imagenes_enviadas = False
      - mode_context.element_codes populated from datos.element_codes
      - mode_context.elementos_confirmados is a list of {code, name, variant_of} dicts
    """

    @pytest.mark.asyncio
    async def test_price_authority_confirmed(self):
        """S4 — price_authority_confirmed root key must be True on success."""
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        result_dict = _calcular_result()
        state = _make_state("calcular_tarifa_con_elementos", {}, mode_context={})

        updates = await presupuesto_post_tool_hook(
            "calcular_tarifa_con_elementos", result_dict, state
        )

        assert updates.get("price_authority_confirmed") is True, (
            "price_authority_confirmed must be True on calcular success"
        )

    @pytest.mark.asyncio
    async def test_precio_comunicado_true(self):
        """
        S4 — mode_context.precio_comunicado must be True after success.
        (Replaces hardcoded line from commit 8a828f1 — now comes from _extract_context.)
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        result_dict = _calcular_result()
        state = _make_state("calcular_tarifa_con_elementos", {}, mode_context={})

        updates = await presupuesto_post_tool_hook(
            "calcular_tarifa_con_elementos", result_dict, state
        )

        mc = updates.get("mode_context", {})
        assert mc.get("precio_comunicado") is True, (
            f"precio_comunicado must be True in mode_context, got: {mc.get('precio_comunicado')!r}"
        )

    @pytest.mark.asyncio
    async def test_imagenes_enviadas_false_on_new_quote(self):
        """
        S4 — mode_context.imagenes_enviadas must be False on new price calculation.
        (Reset for new quote behavior — was hardcoded in 8a828f1, now from extraction.)
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        result_dict = _calcular_result()
        state = _make_state(
            "calcular_tarifa_con_elementos",
            {},
            mode_context={"imagenes_enviadas": True},  # Was True before
        )

        updates = await presupuesto_post_tool_hook(
            "calcular_tarifa_con_elementos", result_dict, state
        )

        mc = updates.get("mode_context", {})
        assert mc.get("imagenes_enviadas") is False, (
            f"imagenes_enviadas must be reset to False on new quote, got: {mc.get('imagenes_enviadas')!r}"
        )

    @pytest.mark.asyncio
    async def test_tarifa_calculada_populated(self):
        """S10 — tarifa_calculada must be populated with the full result dict."""
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        result_dict = _calcular_result(precio_final=410.0)
        state = _make_state("calcular_tarifa_con_elementos", {}, mode_context={})

        updates = await presupuesto_post_tool_hook(
            "calcular_tarifa_con_elementos", result_dict, state
        )

        mc = updates.get("mode_context", {})
        tarifa = mc.get("tarifa_calculada")
        assert tarifa is not None, "tarifa_calculada must be set in mode_context"
        # tarifa_calculada should contain the result data
        assert isinstance(tarifa, dict), (
            f"tarifa_calculada must be a dict, got: {type(tarifa)}"
        )

    @pytest.mark.asyncio
    async def test_element_codes_populated_from_datos(self):
        """
        S4 — element_codes in mode_context populated from datos.element_codes
        when datos is non-empty.
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        result_dict = _calcular_result(element_codes=["ESCAPE", "MANILLAR"])
        state = _make_state("calcular_tarifa_con_elementos", {}, mode_context={})

        updates = await presupuesto_post_tool_hook(
            "calcular_tarifa_con_elementos", result_dict, state
        )

        mc = updates.get("mode_context", {})
        codes = mc.get("element_codes", [])
        assert "ESCAPE" in codes, (
            f"element_codes from datos must include 'ESCAPE', got: {codes}"
        )
        assert "MANILLAR" in codes, (
            f"element_codes from datos must include 'MANILLAR', got: {codes}"
        )

    @pytest.mark.asyncio
    async def test_elementos_confirmados_populated(self):
        """S10 — elementos_confirmados must be a non-empty list of dicts."""
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        result_dict = _calcular_result(element_codes=["ESCAPE", "MANILLAR"])
        state = _make_state("calcular_tarifa_con_elementos", {}, mode_context={})

        updates = await presupuesto_post_tool_hook(
            "calcular_tarifa_con_elementos", result_dict, state
        )

        mc = updates.get("mode_context", {})
        confirmados = mc.get("elementos_confirmados")
        assert isinstance(confirmados, list), (
            f"elementos_confirmados must be a list, got: {type(confirmados)}"
        )
        assert len(confirmados) > 0, (
            "elementos_confirmados must be non-empty after calcular success"
        )
        # Each entry should be a dict with 'code' key
        assert all(isinstance(e, dict) for e in confirmados), (
            "All elementos_confirmados entries must be dicts"
        )
        assert all("code" in e for e in confirmados), (
            "All elementos_confirmados entries must have 'code' key"
        )


# ===========================================================================
# GROUP 6 — enviar_imagenes_ejemplo
# ===========================================================================


class TestEnviarImagenes:
    """S5 — After enviar_imagenes_ejemplo, imagenes_enviadas must be True."""

    @pytest.mark.asyncio
    async def test_imagenes_enviadas_set_true(self):
        """S5 — imagenes_enviadas root key must be True after enviar_imagenes."""
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        pending_images = {"urls": ["https://example.com/img1.jpg"], "caption": "Escape"}
        result_dict = {
            "success": True,
            "_pending_images": pending_images,
            "_state_update": {"imagenes_enviadas": True},
        }
        state = _make_state("enviar_imagenes_ejemplo", {}, mode_context={})

        updates = await presupuesto_post_tool_hook(
            "enviar_imagenes_ejemplo", result_dict, state
        )

        assert updates.get("imagenes_enviadas") is True, (
            f"imagenes_enviadas root key must be True, got: {updates.get('imagenes_enviadas')!r}"
        )

    @pytest.mark.asyncio
    async def test_pending_images_captured(self):
        """S5 — _pending_images dict must be captured in updates."""
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        pending_images = {"urls": ["https://example.com/img.jpg"]}
        result_dict = {
            "success": True,
            "_pending_images": pending_images,
            "_state_update": {"imagenes_enviadas": True},
        }
        state = _make_state("enviar_imagenes_ejemplo", {}, mode_context={})

        updates = await presupuesto_post_tool_hook(
            "enviar_imagenes_ejemplo", result_dict, state
        )

        assert updates.get("_pending_images") == pending_images, (
            f"_pending_images must be captured, got: {updates.get('_pending_images')!r}"
        )


# ===========================================================================
# GROUP 7 — Merge order (hook wins over structural on conflict)
# ===========================================================================


class TestMergeOrder:
    """
    The three-layer merge order: base mode_context → structural extraction → hook.
    Hook-specific overrides win on conflict.
    """

    @pytest.mark.asyncio
    async def test_base_mode_context_preserved_for_unrelated_keys(self):
        """
        Unrelated keys in base mode_context (e.g., _is_first_interaction) must
        survive in the merged result.
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        result_dict = _calcular_result()
        state = _make_state(
            "calcular_tarifa_con_elementos",
            {},
            mode_context={
                "some_existing_key": "should_survive",
                "_is_first_interaction": False,
            },
        )

        updates = await presupuesto_post_tool_hook(
            "calcular_tarifa_con_elementos", result_dict, state
        )

        mc = updates.get("mode_context", {})
        assert mc.get("some_existing_key") == "should_survive", (
            "Unrelated keys from base mode_context must survive the merge"
        )

    @pytest.mark.asyncio
    async def test_exception_in_extract_context_does_not_propagate(self):
        """
        S11 — If _extract_context_from_tool raises, the hook must NOT propagate
        the exception. It should log a warning and return partial updates.

        The import is inside the hook function, so we patch at the source module.
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        result_dict = _calcular_result()
        state = _make_state("calcular_tarifa_con_elementos", {}, mode_context={})

        with patch(
            "agent.modes.presupuesto_mode.PresupuestoModeNode._extract_context_from_tool",
            side_effect=RuntimeError("intentional test error"),
        ):
            # Must NOT raise
            updates = await presupuesto_post_tool_hook(
                "calcular_tarifa_con_elementos", result_dict, state
            )

        # Hook should still return something (partial updates)
        assert isinstance(updates, dict), (
            "Hook must return a dict even when _extract_context_from_tool raises"
        )
        # Hook-specific logic should still work despite extraction failure
        assert updates.get("price_authority_confirmed") is True, (
            "price_authority_confirmed must still be set even when extraction fails"
        )
