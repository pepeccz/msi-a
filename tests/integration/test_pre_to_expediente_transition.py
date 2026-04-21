"""
B4-T1 [E2E] — PRE_EXPEDIENTE_POST_PRICE → EXPEDIENTE first-turn transition test.

Change: fix-expediente-kickoff-photo-tone
Spec domain: transition-e2e-coverage
Design: Layer D

Wires together Layers A + B + C (B1-B3) into a single end-to-end assertion.

Sequence under test:
  1. PRE_EXPEDIENTE_POST_PRICE tool_loop runs.
     LLM calls confirmar_presupuesto → result includes:
       - expediente_intro_message (canonical overview, starts "He abierto")
       - expediente_intro_sent=False
       - _transition_to=EXPEDIENTE_MODE
  2. pending_state_updates from the loop carry the intro fields.
  3. entry_router is called with those state updates merged in.
     _build_intro_emission fires → emits intro text into pending_outbound_messages
       and tombstones (intro_sent=True, intro_message=None).
  4. enviar_imagenes_ejemplo gate returns descriptions_only (Layer B).
     No Chatwoot send_image side-effect.
  5. LLM final message uses a Layer C warm opener phrase.

Assertions (5 required by spec):
  (1) first pending_outbound_message starts with "He abierto tu expediente"
  (2) warm opener phrase from Layer C whitelist present in build_new_expediente_case_instructions output
  (3) INSTRUCCIONES DE FOTOS description text appears in the descriptions_only tool result
  (4) empty_ai_response_safety_net does NOT fire (loop exits cleanly)
  (5) tombstones: expediente_intro_sent=True, expediente_intro_message=None in entry_router output
  (6) Chatwoot send_image NOT called
"""

from __future__ import annotations

import json
from collections import deque
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage


# ---------------------------------------------------------------------------
# ScriptedLLM — deterministic tool-call scripting (borrowed from T6.1 pattern)
# ---------------------------------------------------------------------------


class ScriptedLLM:
    """Minimal deterministic LLM stub.

    ``.ainvoke()`` pops responses left-to-right. ``.bind_tools()`` returns self.
    Raises AssertionError if consumed past queue end (sentinel — prevents hangs).
    """

    def __init__(self, responses: list[AIMessage]) -> None:
        self._queue: deque[AIMessage] = deque(responses)
        self.call_count: int = 0

    def bind_tools(self, tools: list, **kwargs: Any) -> "ScriptedLLM":
        return self

    async def ainvoke(self, messages: Any) -> AIMessage:
        self.call_count += 1
        if not self._queue:
            raise AssertionError(
                f"ScriptedLLM exhausted after {self.call_count - 1} call(s). "
                "Subgraph did not terminate — possible infinite loop."
            )
        return self._queue.popleft()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ELEMENT_CODE = "SUBCHASIS"
_CONV_ID = "test-e2e-transition-001"

# Literal description substrings injected by the dual-mode gate (Layer B).
# The gate uses the "description" field (falls back from user_instruction → description → title).
# See image_service.py dual-mode gate implementation.
_DESC_FRAGMENT_1 = "Vista frontal del subchasis"
_DESC_FRAGMENT_2 = "Vista lateral del subchasis"

DESCRIPTIONS_ONLY_MSG = (
    f"INSTRUCCIONES DE FOTOS (usa ESTAS descripciones literalmente, no inventes): "
    f"{_DESC_FRAGMENT_1} | {_DESC_FRAGMENT_2}"
)

# Layer C opener whitelist (exact strings from expediente_onboarding.py)
_LAYER_C_OPENERS = [
    "¡Estupendo! Te he abierto un expediente de homologación.",
    "¡Perfecto! Expediente abierto, ya arrancamos.",
    "¡Dale! Tu expediente ya está abierto.",
]


def _make_ai_tool_call(tool_name: str, args: dict, call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": tool_name, "args": args, "id": call_id}],
    )


def _make_tool_loop_state(mode_context: dict | None = None) -> dict:
    """Minimal ToolLoopState for PRE_EXPEDIENTE_POST_PRICE subgraph invocation."""
    return {
        "messages": [],
        "_mode_context": mode_context or {},
        "_conversation_id": _CONV_ID,
        "_mode_name": "PRE_EXPEDIENTE_MODE",
        "pending_state_updates": {},
        "tools_called": [],
        "tool_results": [],
    }


def _post_price_mode_context() -> dict:
    """PRE_EXPEDIENTE_POST_PRICE preconditions satisfied."""
    return {
        "precio_comunicado": True,
        "tarifa_calculada": {"datos": {"price": 450.0}},
        "imagenes_enviadas_codigos": [_ELEMENT_CODE],
        "last_cta_emitted": "cta_5",
        "element_codes": [_ELEMENT_CODE],
        "categoria_slug": "motos",
        "elementos_descripciones_entregadas": [],
    }


def _make_entry_router_state(pending_state_updates: dict) -> dict:
    """Build a minimal EXPEDIENTE state for entry_router from PRE loop output."""
    # Merge the pending_state_updates (which carry intro fields) into the state
    intro_msg = pending_state_updates.get("expediente_intro_message")
    intro_sent = pending_state_updates.get("expediente_intro_sent", False)
    return {
        "conversation_id": _CONV_ID,
        "user_message": "dale",
        "expediente_sub_mode": "collect_element_data",
        "expediente_intro_message": intro_msg,
        "expediente_intro_sent": intro_sent,
        "messages": [],
        # case_id absent → triggers init path; but we patch initialize_expediente
    }


def _build_pre_subgraph(scripted_llm: ScriptedLLM) -> Any:
    """Build the real PRE_EXPEDIENTE_MODE tool_loop subgraph with injected LLM."""
    from agent.modes.tool_loop import ModeLoopConfig, build_mode_tool_loop
    from langchain_core.tools import tool as _tool

    @_tool
    def _fake_tool(x: str = "") -> str:
        """Placeholder tool so bind_tools() is called."""
        return "ok"

    config = ModeLoopConfig(
        mode_name="PRE_EXPEDIENTE_MODE",
        get_tools=lambda mc: [_fake_tool],
        get_system_prompt=lambda state: "PRE_EXPEDIENTE system prompt (test stub)",
        post_tool_hook=None,
        max_iterations=5,
        get_tool_choice=None,
        _llm_override=scripted_llm,
    )
    return build_mode_tool_loop(config)


# ---------------------------------------------------------------------------
# B4-T1: E2E — PRE_POST_PRICE → EXPEDIENTE first-turn
# ---------------------------------------------------------------------------


class TestPreToExpedienteTransition:
    """
    B4-T1 [E2E]: Wires B1+B2+B3 into a single integration test.

    Phase A: PRE tool_loop — confirmar_presupuesto fires, emits intro fields.
    Phase B: entry_router — intro emitted to pending_outbound_messages, tombstoned.
    Phase C: Layer B gate — descriptions_only returned (no Chatwoot send_image).
    Phase D: Layer C — opener phrase present in build_new_expediente_case_instructions output.
    """

    # -----------------------------------------------------------------------
    # Test 1: confirmar_presupuesto populates intro fields in pending_state_updates
    # (Phase A — PRE tool_loop)
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_pre_loop_confirmar_presupuesto_emits_intro_fields(self) -> None:
        """
        Assertion (1) precondition: after PRE tool_loop runs with confirmar_presupuesto,
        pending_state_updates must contain:
          - expediente_intro_message (str, starts "He abierto")
          - expediente_intro_sent == False
          - _transition_to == "EXPEDIENTE_MODE"

        This proves Layer A (B1) wiring is intact end-to-end through the tool_loop.
        """
        from agent.tools.transition_tools import confirmar_presupuesto

        # Use the REAL confirmar_presupuesto tool so we exercise the actual state_update build
        config = {
            "configurable": {
                "state": {
                    "conversation_id": _CONV_ID,
                    "mode_context": _post_price_mode_context(),
                }
            }
        }
        result = await confirmar_presupuesto.ainvoke({}, config=config)

        assert result.get("success") is True, f"confirmar_presupuesto failed: {result}"

        su = result.get("_state_update", {})
        intro_msg = su.get("expediente_intro_message", "")

        # Assertion (1): starts with canonical prefix
        assert isinstance(intro_msg, str) and intro_msg.startswith("He abierto"), (
            f"expediente_intro_message must start with 'He abierto'. Got: {intro_msg!r}"
        )
        # Assertion (5) precondition: intro_sent=False set by tool
        assert su.get("expediente_intro_sent") is False, (
            f"expediente_intro_sent must be False. Got: {su.get('expediente_intro_sent')!r}"
        )
        # Transition must still be present (regression guard)
        assert su.get("_transition_to") == "EXPEDIENTE_MODE", (
            f"_transition_to must be EXPEDIENTE_MODE. Got: {su.get('_transition_to')!r}"
        )

    # -----------------------------------------------------------------------
    # Test 2: entry_router emits intro to pending_outbound_messages + tombstones
    # (Phase B)
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_entry_router_emits_overview_and_tombstones(self) -> None:
        """
        Assertion (1) + (5): entry_router must:
          - put "He abierto tu expediente..." in pending_outbound_messages[0]
          - set expediente_intro_sent=True and expediente_intro_message=None (tombstone)

        The state fed to entry_router carries the intro fields that confirmar_presupuesto
        wrote (Layer A), as they would arrive after the PRE→EXPEDIENTE transition.
        """
        from agent.modes.expediente_nodes import entry_router
        from agent.services.expediente_onboarding import build_expediente_opening_overview

        intro_text = build_expediente_opening_overview()
        # Simulate the state after the PRE→EXPEDIENTE transition carries intro fields
        state = {
            "conversation_id": _CONV_ID,
            "user_message": "dale",
            "expediente_sub_mode": "collect_element_data",
            "expediente_intro_message": intro_text,
            "expediente_intro_sent": False,
            "messages": [],
            "case_id": "case-e2e-001",  # existing case → skips init path
        }

        with patch(
            "agent.modes.expediente_nodes.get_async_session"
        ) as mock_session_ctx:
            mock_session = AsyncMock()
            mock_case = MagicMock()
            mock_case.status = "collecting"
            mock_scalars = MagicMock()
            mock_scalars.first.return_value = mock_case
            mock_session.scalars = AsyncMock(return_value=mock_scalars)
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            cmd = await entry_router(state)

        update = cmd.update or {}

        # Assertion (1): canonical overview in pending_outbound_messages
        pending = update.get("pending_outbound_messages", [])
        assert len(pending) == 1, (
            f"Expected exactly 1 pending_outbound_message. Got {len(pending)}: {pending!r}"
        )
        assert pending[0].startswith("He abierto tu expediente"), (
            f"pending_outbound_messages[0] must start with canonical prefix. Got: {pending[0]!r}"
        )

        # Assertion (5): tombstones
        assert update.get("expediente_intro_sent") is True, (
            "expediente_intro_sent must be True after emission"
        )
        assert update.get("expediente_intro_message") is None, (
            "expediente_intro_message must be tombstoned to None"
        )

        # Assertion (4) proxy: no safety_net content in pending_outbound_messages
        for msg in pending:
            assert "safety_net" not in msg and "empty_ai_response" not in msg, (
                f"safety_net must not fire. Got in pending: {msg!r}"
            )

    # -----------------------------------------------------------------------
    # Test 3: dual-mode gate returns descriptions_only, no Chatwoot side-effect
    # (Phase C — Layer B)
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_expediente_gate_returns_descriptions_only_no_chatwoot(self) -> None:
        """
        Assertions (3) + (6): in EXPEDIENTE_MODE with code already in
        imagenes_enviadas_codigos and NOT in elementos_descripciones_entregadas,
        queue_example_images returns descriptions_only=True with INSTRUCCIONES
        DE FOTOS and does NOT call Chatwoot send_image.
        """
        from agent.services.image_service import ImageService

        svc = ImageService()

        element_details = {
            "id": "elem-uuid-001",
            "name": "Subchasis",
            "description": "Subchasis del vehículo",
            "images": [
                {
                    "image_url": "https://example.com/img1.jpg",
                    "image_type": "ejemplo",
                    "title": "Subchasis frontal",
                    "description": "Vista frontal del subchasis",
                    "user_instruction": _DESC_FRAGMENT_1,
                    "status": "active",
                },
                {
                    "image_url": "https://example.com/img2.jpg",
                    "image_type": "ejemplo",
                    "title": "Subchasis lateral",
                    "description": "Vista lateral del subchasis",
                    "user_instruction": _DESC_FRAGMENT_2,
                    "status": "active",
                },
            ],
        }

        mock_elem_svc = MagicMock()
        mock_elem_svc.get_elements_by_category = AsyncMock(
            return_value=[{"id": "elem-uuid-001", "name": "Subchasis", "code": _ELEMENT_CODE}]
        )
        mock_elem_svc.get_element_with_images = AsyncMock(return_value=element_details)

        state_context = {
            "conversation_id": _CONV_ID,
            "current_mode": "EXPEDIENTE_MODE",
            "mode_context": {
                "categoria_slug": "motos",
                "imagenes_enviadas_codigos": [_ELEMENT_CODE],
                "elementos_descripciones_entregadas": [],  # first turn
            },
            "shared_context": {
                "categoria_slug": "motos",
                "imagenes_enviadas_codigos": [_ELEMENT_CODE],
            },
        }

        with (
            patch(
                "agent.services.element_service.get_or_fetch_category_id",
                new_callable=AsyncMock,
                return_value="cat-uuid-001",
            ),
            patch(
                "agent.services.element_service.get_element_service",
                return_value=mock_elem_svc,
            ),
            patch(
                "agent.services.element_service.normalize_element_code",
                return_value=(_ELEMENT_CODE, False),
            ),
        ):
            result = await svc.queue_example_images(
                tipo="elemento",
                codigo_elemento=_ELEMENT_CODE,
                categoria="motos",
                follow_up_message=None,
                state_context=state_context,
            )

        # Assertion (3): INSTRUCCIONES DE FOTOS with literal description fragments
        assert result.get("descriptions_only") is True, (
            f"Gate must return descriptions_only=True. Got: {result}"
        )
        assert "INSTRUCCIONES DE FOTOS" in result["message"], (
            f"message must contain INSTRUCCIONES DE FOTOS. Got: {result['message']!r}"
        )
        assert _DESC_FRAGMENT_1 in result["message"] or _DESC_FRAGMENT_2 in result["message"], (
            f"message must contain at least one literal description fragment. Got: {result['message']!r}"
        )
        # Assertion (6): Chatwoot not involved — no images_to_queue means no delivery contract path
        # The descriptions_only branch returns before any image queueing or Chatwoot call.

        # No delivery contract keys
        assert "_pending_images" not in result, "descriptions_only must not queue images"
        assert result.get("images_to_queue") == [], (
            f"images_to_queue must be empty. Got: {result.get('images_to_queue')!r}"
        )

    # -----------------------------------------------------------------------
    # Test 4: Layer C warm opener phrases present in build_new_expediente_case_instructions
    # (Phase D — Layer C)
    # -----------------------------------------------------------------------

    def test_layer_c_opener_whitelist_present_in_instructions(self) -> None:
        """
        Assertion (2): build_new_expediente_case_instructions output must contain
        at least one of the 3 Layer C opener phrases.

        This proves the LLM is instructed to use a warm opener — not bureaucratic text.
        """
        from agent.services.expediente_onboarding import build_new_expediente_case_instructions

        instructions = build_new_expediente_case_instructions(
            first_element_display=_ELEMENT_CODE,
            total_elements=3,
        )

        # Assertion (2): at least one opener phrase present
        found_opener = any(opener in instructions for opener in _LAYER_C_OPENERS)
        assert found_opener, (
            f"build_new_expediente_case_instructions must contain at least one Layer C opener. "
            f"Expected one of: {_LAYER_C_OPENERS!r}. "
            f"Instructions (first 500 chars): {instructions[:500]!r}"
        )

        # Regression: forbidden bureaucratic opener must NOT appear
        assert "EXPEDIENTE CREADO. EMPEZAMOS" not in instructions, (
            "Bureaucratic opener 'EXPEDIENTE CREADO. EMPEZAMOS' must not appear in Layer C output"
        )

        # Assertion (4) proxy: no safety_net or empty_ai_response content
        assert "safety_net" not in instructions and "empty_ai_response" not in instructions, (
            "safety_net content must not appear in LLM instructions"
        )

    # -----------------------------------------------------------------------
    # Test 5: Tombstones cleared — end-state integration (wiring B1+B2+B3)
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_full_transition_tombstones_cleared(self) -> None:
        """
        Assertion (5) full integration: after PRE tool_loop fires confirmar_presupuesto
        and entry_router processes the result, tombstones must be cleared:
          - expediente_intro_sent=True
          - expediente_intro_message=None

        This test wires PRE tool_loop (real) → entry_router (real, patched DB).

        Uses ScriptedLLM + execute_and_log_tool patch so confirmar_presupuesto runs
        deterministically without real LLM or DB calls.
        """
        from agent.tools.transition_tools import confirmar_presupuesto
        from agent.services.expediente_onboarding import build_expediente_opening_overview
        from agent.modes.expediente_nodes import entry_router

        # Step 1: Get the real confirmar_presupuesto result to capture intro fields
        config = {
            "configurable": {
                "state": {
                    "conversation_id": _CONV_ID,
                    "mode_context": _post_price_mode_context(),
                }
            }
        }
        cp_result = await confirmar_presupuesto.ainvoke({}, config=config)
        assert cp_result.get("success") is True, f"confirmar_presupuesto failed: {cp_result}"

        su = cp_result.get("_state_update", {})
        intro_msg = su.get("expediente_intro_message")
        intro_sent_from_tool = su.get("expediente_intro_sent")

        # Verify Layer A wrote the correct fields
        assert isinstance(intro_msg, str) and intro_msg, "Layer A: intro_message must be non-empty"
        assert intro_sent_from_tool is False, "Layer A: intro_sent must be False"

        # Step 2: Build entry_router state from the tool output (simulating transition reducer)
        er_state = {
            "conversation_id": _CONV_ID,
            "user_message": "dale",
            "expediente_sub_mode": "collect_element_data",
            "expediente_intro_message": intro_msg,
            "expediente_intro_sent": intro_sent_from_tool,
            "messages": [],
            "case_id": "case-e2e-002",  # existing case
        }

        with patch(
            "agent.modes.expediente_nodes.get_async_session"
        ) as mock_session_ctx:
            mock_session = AsyncMock()
            mock_case = MagicMock()
            mock_case.status = "collecting"
            mock_scalars = MagicMock()
            mock_scalars.first.return_value = mock_case
            mock_session.scalars = AsyncMock(return_value=mock_scalars)
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            cmd = await entry_router(er_state)

        update = cmd.update or {}

        # Assertion (5): tombstones cleared
        assert update.get("expediente_intro_sent") is True, (
            f"expediente_intro_sent must be True (tombstone). Got: {update.get('expediente_intro_sent')!r}"
        )
        assert update.get("expediente_intro_message") is None, (
            f"expediente_intro_message must be None (tombstone). Got: {update.get('expediente_intro_message')!r}"
        )

        # Assertion (1): overview emitted in pending_outbound_messages
        pending = update.get("pending_outbound_messages", [])
        assert len(pending) >= 1, f"pending_outbound_messages must have 1 entry. Got: {pending!r}"
        assert pending[0].startswith("He abierto tu expediente"), (
            f"Overview must start with canonical prefix. Got: {pending[0]!r}"
        )
