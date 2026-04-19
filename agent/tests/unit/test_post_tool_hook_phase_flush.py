"""
Unit tests for pre_expediente_post_tool_hook — phase flush on mid-turn flag changes (Batch C).

Gap A: when a tool call within the agent loop flips a phase-determining flag
(``precio_comunicado``) via ``_state_update.shared_context``, the hook MUST
propagate those changes into ``pending_state_updates["mode_context"]`` so that
the next ``llm_node`` call within the SAME turn resolves the correct phase
(PRICING, not POST_PRICE).

Covers:
- AC-2.2: ``_mode_context`` in loop state after hook reflects updated ``precio_comunicado`` value
- AC-2.1: After tool sets ``precio_comunicado=False``, the next system prompt in the
           same turn resolves PRICING mode file (not POST_PRICE)
- AC-2.3: No spurious invalidation — hook is a no-op when the flag did NOT change

Design note (per design Q2):
The hook propagates the update through ``pending_state_updates["mode_context"]``,
NOT by mutating ``state["_mode_context"]`` in-place (which is read-only in the
LangGraph state machine). The ``llm_node`` already merges
``pending_state_updates["mode_context"]`` before assembling the system prompt
(tool_loop.py:454-458), so this is the correct path.

NOTE — divergence from design wording:
Design Q2 says "mutate state['_mode_context'] in place". The actual mechanism
is ``pending_state_updates["mode_context"]`` (the existing three-layer merge path
already present in the hook). This achieves the same effect: the next ``llm_node``
call sees the updated flag. Direct in-place mutation of ``state["_mode_context"]``
is impossible in LangGraph's state machine — returning it as a top-level key from
``post_tool_node`` is the only legal write path, but that goes into
``pending_state_updates``, not directly to ``state["_mode_context"]``.

The tests assert that ``updates["mode_context"]["precio_comunicado"]`` reflects
the flag from the tool's ``_state_update.shared_context`` — which is what AC-2.2
requires.
"""
from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state_with_mode_context(mode_context: dict) -> dict:
    """Build a minimal ToolLoopState-compatible dict for hook testing."""
    return {
        "_mode_context": mode_context,
        "messages": [],
        "pending_state_updates": {},
        "_conversation_id": "test-conv-001",
        "_mode_name": "PRE_EXPEDIENTE_MODE",
    }


def _make_identificar_result(
    *,
    precio_comunicado: bool = False,
    categoria_slug: str = "motos-part",
    element_codes: list[str] | None = None,
    imagenes_enviadas: bool = False,
) -> dict[str, Any]:
    """
    Build a minimal identificar_y_resolver_elementos result that resets flags.

    Mirrors the actual shape returned by element_tools.py:1634-1640.
    """
    return {
        "success": True,
        "elementos_listos": [{"codigo": c} for c in (element_codes or [])],
        "elementos_con_variantes": [],
        "preguntas_variantes": [],
        "categoria_slug": categoria_slug,
        "_state_update": {
            "shared_context": {
                "precio_comunicado": precio_comunicado,
                "imagenes_enviadas": imagenes_enviadas,
                "imagenes_enviadas_codigos": [],
            },
        },
    }


# ---------------------------------------------------------------------------
# AC-2.2 — Hook propagates precio_comunicado=False into mode_context
# ---------------------------------------------------------------------------


class TestPrecioComunicadoFlushOnIdentificar:
    """
    AC-2.2: when ``identificar_y_resolver_elementos`` returns
    ``_state_update.shared_context.precio_comunicado=False`` and the current
    ``_mode_context.precio_comunicado=True``, the hook MUST reflect the
    updated value in ``updates["mode_context"]["precio_comunicado"]``.
    """

    async def test_precio_comunicado_set_to_false_after_re_identification(self):
        """
        GIVEN _mode_context.precio_comunicado=True (POST_PRICE turn-start snapshot)
        WHEN identificar_y_resolver_elementos returns _state_update.shared_context.precio_comunicado=False
        THEN updates["mode_context"]["precio_comunicado"] MUST equal False.

        This is AC-2.2: the hook output must reflect the fresh flag so that the
        next llm_node call (which merges pending_state_updates["mode_context"])
        operates under the correct phase (PRICING, not POST_PRICE).
        """
        from agent.modes.post_tool_hooks import pre_expediente_post_tool_hook

        mode_context = {
            "precio_comunicado": True,
            "tarifa_calculada": {"precio_final": 350},
            "element_codes": ["LUNA_DEL"],
            "categoria_slug": "motos-part",
        }
        state = _make_state_with_mode_context(mode_context)
        result_dict = _make_identificar_result(
            precio_comunicado=False,
            element_codes=["LUNA_DEL", "PARABRISAS"],
            categoria_slug="motos-part",
        )

        updates = await pre_expediente_post_tool_hook(
            "identificar_y_resolver_elementos", result_dict, state
        )

        mc = updates.get("mode_context", {})
        assert mc.get("precio_comunicado") is False, (
            "After identificar_y_resolver_elementos resets precio_comunicado=False, "
            "hook must propagate that into mode_context so next llm_node resolves "
            "PRICING phase (not POST_PRICE). AC-2.2."
        )

    async def test_precio_comunicado_false_to_false_is_idempotent(self):
        """
        GIVEN _mode_context.precio_comunicado=False (PRICING turn-start snapshot)
        WHEN identificar_y_resolver_elementos returns precio_comunicado=False
        THEN updates["mode_context"]["precio_comunicado"] MUST still be False.

        Triangulation: confirms the flush also works when the flag was already
        False — no spurious side effects.
        """
        from agent.modes.post_tool_hooks import pre_expediente_post_tool_hook

        mode_context = {
            "precio_comunicado": False,
            "element_codes": ["LUNA_DEL"],
            "categoria_slug": "motos-part",
        }
        state = _make_state_with_mode_context(mode_context)
        result_dict = _make_identificar_result(
            precio_comunicado=False,
            element_codes=["LUNA_DEL", "PARABRISAS"],
            categoria_slug="motos-part",
        )

        updates = await pre_expediente_post_tool_hook(
            "identificar_y_resolver_elementos", result_dict, state
        )

        mc = updates.get("mode_context", {})
        assert mc.get("precio_comunicado") is False, (
            "When precio_comunicado was already False, mode_context must still "
            "be False after hook — idempotent behavior. AC-2.2."
        )


# ---------------------------------------------------------------------------
# AC-2.1 — Next system prompt resolves PRICING mode file (not POST_PRICE)
# ---------------------------------------------------------------------------


class TestSystemPromptResolvesCorrectPhaseAfterFlush:
    """
    AC-2.1: after the hook reflects precio_comunicado=False in the mode_context,
    calling format_mode_context with that context must produce a PRICING prompt
    (contains 'DEBES comunicarlo'), NOT a POST_PRICE prompt (would have 'ya comunicado').
    """

    async def test_format_mode_context_with_updated_mc_resolves_pricing(self):
        """
        GIVEN _mode_context.precio_comunicado=True at turn start
        WHEN identificar_y_resolver_elementos resets precio_comunicado=False
        AND the hook's updated mode_context is fed to format_mode_context
        THEN the resulting prompt MUST contain 'DEBES comunicarlo' (PRICING)
        AND MUST NOT contain 'ya comunicado' (POST_PRICE).

        This verifies AC-2.1 end-to-end within the unit boundary:
        hook output → format_mode_context input → PRICING instructions present.
        """
        from agent.modes.post_tool_hooks import pre_expediente_post_tool_hook
        from agent.prompts.loader import format_mode_context

        # Turn-start snapshot has POST_PRICE state
        mode_context = {
            "precio_comunicado": True,
            "tarifa_calculada": {"precio_final": 350},
            "element_codes": ["LUNA_DEL"],
            "categoria_slug": "motos-part",
        }
        state = _make_state_with_mode_context(mode_context)
        result_dict = _make_identificar_result(
            precio_comunicado=False,
            element_codes=["LUNA_DEL", "PARABRISAS"],
            categoria_slug="motos-part",
        )

        updates = await pre_expediente_post_tool_hook(
            "identificar_y_resolver_elementos", result_dict, state
        )

        # The hook's mode_context output should have precio_comunicado=False.
        # Inject a tarifa so format_mode_context exercises the price branch
        # (simulating that calcular_tarifa will run after re-identification).
        updated_mc = updates.get("mode_context", {})
        updated_mc_with_tarifa = {
            **updated_mc,
            "tarifa_calculada": {"precio_final": 480},
        }

        prompt = format_mode_context("PRE_EXPEDIENTE_MODE", updated_mc_with_tarifa)

        assert "DEBES comunicarlo" in prompt, (
            "After hook propagates precio_comunicado=False, format_mode_context "
            "must emit the PRICING instruction 'DEBES comunicarlo al usuario'. AC-2.1."
        )
        assert "ya comunicado" not in prompt.lower(), (
            "After hook propagates precio_comunicado=False, format_mode_context "
            "must NOT emit the POST_PRICE 'ya comunicado' marker. AC-2.1."
        )


# ---------------------------------------------------------------------------
# AC-2.3 — No spurious invalidation when flag did NOT change
# ---------------------------------------------------------------------------


class TestNoSpuriousFlushWhenFlagUnchanged:
    """
    AC-2.3: the hook must be a no-op on the precio_comunicado field when the
    tool result does NOT flip it. Avoids disrupting turns where no re-identification
    happened and POST_PRICE state is legitimately still active.
    """

    async def test_no_invalidation_when_tool_does_not_reset_precio_comunicado(self):
        """
        GIVEN _mode_context.precio_comunicado=True (legitimate POST_PRICE state)
        WHEN a tool runs that does NOT include precio_comunicado in its _state_update
        THEN updates["mode_context"]["precio_comunicado"] MUST still be True.

        This prevents spurious phase drops on unrelated tool calls (e.g.
        enviar_imagenes_ejemplo, confirmar_presupuesto) that don't touch the flag.
        AC-2.3.
        """
        from agent.modes.post_tool_hooks import pre_expediente_post_tool_hook

        mode_context = {
            "precio_comunicado": True,
            "tarifa_calculada": {"precio_final": 350},
            "element_codes": ["LUNA_DEL"],
            "categoria_slug": "motos-part",
        }
        state = _make_state_with_mode_context(mode_context)

        # A tool result with NO precio_comunicado in _state_update
        result_dict = {
            "success": True,
            "_state_update": {
                "shared_context": {
                    "imagenes_enviadas": True,
                    "imagenes_enviadas_codigos": ["LUNA_DEL"],
                }
            },
            "_pending_images": [],
        }

        updates = await pre_expediente_post_tool_hook(
            "enviar_imagenes_ejemplo", result_dict, state
        )

        mc = updates.get("mode_context", {})
        assert mc.get("precio_comunicado") is True, (
            "When tool does NOT reset precio_comunicado, the hook must preserve "
            "the existing True value in mode_context. No spurious phase drop. AC-2.3."
        )

    async def test_no_invalidation_for_unrelated_tool_calcular_tarifa(self):
        """
        GIVEN _mode_context.precio_comunicado=False (PRICING state)
        WHEN calcular_tarifa_con_elementos runs successfully (without touching precio_comunicado)
        THEN updates["mode_context"]["precio_comunicado"] MUST remain False.

        Triangulation: different tool, same no-spurious-invalidation guarantee.
        AC-2.3.
        """
        from agent.modes.post_tool_hooks import pre_expediente_post_tool_hook

        mode_context = {
            "precio_comunicado": False,
            "element_codes": ["LUNA_DEL"],
            "categoria_slug": "motos-part",
        }
        state = _make_state_with_mode_context(mode_context)

        # calcular_tarifa result — does NOT set precio_comunicado (flag is set later
        # by _process_message after LLM generates its response)
        result_dict = {
            "success": True,
            "texto": "Presupuesto calculado: 350€ + IVA",
            "datos": {"price": 350, "element_codes": ["LUNA_DEL"]},
            "_state_update": {
                "tarifa_calculada": {"price": 350},
            },
        }

        updates = await pre_expediente_post_tool_hook(
            "calcular_tarifa_con_elementos", result_dict, state
        )

        mc = updates.get("mode_context", {})
        assert mc.get("precio_comunicado") is False, (
            "calcular_tarifa_con_elementos does not set precio_comunicado "
            "(that is done post-LLM-response in _process_message). Hook must "
            "preserve False. AC-2.3."
        )
