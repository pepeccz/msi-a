"""
Tests for root-expediente-ux fixes.

Fix A: Code-driven kickoff confirmation
  - confirmar_presupuesto returns expediente_kickoff_pending: True
  - expediente_mode injects "Perfecto, abrimos el expediente." prefix (via hook output)

Fix B: Warning state tracking
  - post_tool_hook extracts warning codes after calcular_tarifa
  - format_mode_context shows warnings in EXPEDIENTE_MODE and PRE_EXPEDIENTE_MODE
  - identificar_y_resolver_elementos resets advertencias_comunicadas

All tests are pure unit tests — no DB, no Redis, no LLM, no network.
"""

from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
from langchain_core.messages import AIMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hook_state(
    tool_name: str,
    tool_args: dict,
    mode_context: dict | None = None,
) -> dict:
    """Build a minimal hook state dict as passed by post_tool_node."""
    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call_001",
                "name": tool_name,
                "args": tool_args,
                "type": "tool_call",
            }
        ],
    )
    return {
        "messages": [ai_msg],
        "_mode_context": mode_context or {},
        "_conversation_id": "conv_test",
        "pending_state_updates": {},
    }


# ===========================================================================
# Fix A — confirmar_presupuesto returns expediente_kickoff_pending
# ===========================================================================


class TestConfirmarPresupuestoKickoffFlag:
    """A1: confirmar_presupuesto must include expediente_kickoff_pending: True."""

    @pytest.mark.asyncio
    async def test_kickoff_pending_in_state_update(self):
        """confirmar_presupuesto._state_update contains expediente_kickoff_pending=True."""
        from agent.state.helpers import get_tool_state

        mock_state = {
            "conversation_id": "conv_test",
            "mode_context": {
                "precio_comunicado": True,
                "tarifa_calculada": {"datos": {"price": 410}},
                "element_codes": ["SUBCHASIS"],
                "categoria_slug": "furgonetas-part",
            },
        }

        with patch("agent.tools.transition_tools.get_tool_state", return_value=mock_state):
            from agent.tools.transition_tools import confirmar_presupuesto

            result = await confirmar_presupuesto.ainvoke({})

        assert result["success"] is True
        state_update = result.get("_state_update", {})
        assert state_update.get("expediente_kickoff_pending") is True, (
            "confirmar_presupuesto must set expediente_kickoff_pending=True in _state_update"
        )

    @pytest.mark.asyncio
    async def test_transition_still_present(self):
        """_transition_to: EXPEDIENTE_MODE must still be in _state_update."""
        mock_state = {
            "conversation_id": "conv_test",
            "mode_context": {
                "precio_comunicado": True,
                "tarifa_calculada": {"datos": {"price": 410}},
                "element_codes": ["SUBCHASIS"],
                "categoria_slug": "furgonetas-part",
            },
        }

        with patch("agent.tools.transition_tools.get_tool_state", return_value=mock_state):
            from agent.tools.transition_tools import confirmar_presupuesto

            result = await confirmar_presupuesto.ainvoke({})

        assert result["_state_update"]["_transition_to"] == "EXPEDIENTE_MODE"


# ===========================================================================
# Fix B — Warning code extraction in post_tool_hook
# ===========================================================================


class TestPostToolHookWarningExtraction:
    """B1: pre_expediente_post_tool_hook extracts warning codes after calcular_tarifa."""

    @pytest.mark.asyncio
    async def test_warnings_extracted_from_calcular_tarifa(self):
        """Warnings list → advertencias_comunicadas in mode_context."""
        from agent.modes.post_tool_hooks import pre_expediente_post_tool_hook

        result_dict = {
            "success": True,
            "datos": {"price": 410},
            "warnings": [
                {"code": "SUBCHASIS_REQUIRES_SPECIALIST", "message": "Requiere especialista"},
                {"code": "CERT_REQUIRED", "message": "Certificado requerido"},
            ],
        }
        state = _make_hook_state(
            "calcular_tarifa_con_elementos",
            {"element_codes": ["SUBCHASIS"]},
            mode_context={"precio_comunicado": False},
        )

        # Patch at source module (imported locally inside hook function)
        mock_node = MagicMock()
        mock_node._extract_context_from_tool = MagicMock(return_value={})
        with patch(
            "agent.modes.pre_expediente_mode.PreExpedienteModeNode",
            mock_node,
        ):
            updates = await pre_expediente_post_tool_hook(
                "calcular_tarifa_con_elementos", result_dict, state
            )

        mc = updates.get("mode_context", {})
        assert "advertencias_comunicadas" in mc, "advertencias_comunicadas must be in mode_context"
        adv = mc["advertencias_comunicadas"]
        assert "SUBCHASIS_REQUIRES_SPECIALIST" in adv
        assert "CERT_REQUIRED" in adv

    @pytest.mark.asyncio
    async def test_warnings_also_in_shared_context(self):
        """Warning codes must also be propagated to shared_context."""
        from agent.modes.post_tool_hooks import pre_expediente_post_tool_hook

        result_dict = {
            "success": True,
            "datos": {"price": 410},
            "warnings": [
                {"code": "CERT_REQUIRED", "message": "Certificado requerido"},
            ],
        }
        state = _make_hook_state(
            "calcular_tarifa_con_elementos",
            {"element_codes": ["SUBCHASIS"]},
            mode_context={"precio_comunicado": False},
        )

        mock_node = MagicMock()
        mock_node._extract_context_from_tool = MagicMock(return_value={})
        with patch(
            "agent.modes.pre_expediente_mode.PreExpedienteModeNode",
            mock_node,
        ):
            updates = await pre_expediente_post_tool_hook(
                "calcular_tarifa_con_elementos", result_dict, state
            )

        sc = updates.get("shared_context", {})
        assert "advertencias_comunicadas" in sc, "advertencias_comunicadas must be in shared_context"

    @pytest.mark.asyncio
    async def test_no_warnings_no_key_injected(self):
        """If no warnings, advertencias_comunicadas is not injected."""
        from agent.modes.post_tool_hooks import pre_expediente_post_tool_hook

        result_dict = {
            "success": True,
            "datos": {"price": 410},
            "warnings": [],
        }
        state = _make_hook_state(
            "calcular_tarifa_con_elementos",
            {"element_codes": ["SUBCHASIS"]},
        )

        mock_node = MagicMock()
        mock_node._extract_context_from_tool = MagicMock(return_value={})
        with patch(
            "agent.modes.pre_expediente_mode.PreExpedienteModeNode",
            mock_node,
        ):
            updates = await pre_expediente_post_tool_hook(
                "calcular_tarifa_con_elementos", result_dict, state
            )

        mc = updates.get("mode_context", {})
        assert mc.get("advertencias_comunicadas") is None or "advertencias_comunicadas" not in mc

    @pytest.mark.asyncio
    async def test_identificar_resets_advertencias(self):
        """identificar_y_resolver_elementos resets advertencias_comunicadas to []."""
        from agent.modes.post_tool_hooks import pre_expediente_post_tool_hook

        result_dict = {
            "success": True,
            "element_codes": ["TOLDO_GALIBO"],
            "elementos_confirmados": [{"code": "TOLDO_GALIBO"}],
        }
        state = _make_hook_state(
            "identificar_y_resolver_elementos",
            {"descripcion": "toldo galibo"},
            mode_context={"advertencias_comunicadas": ["CERT_REQUIRED"]},
        )

        mock_node = MagicMock()
        mock_node._extract_context_from_tool = MagicMock(
            return_value={"element_codes": ["TOLDO_GALIBO"]}
        )
        with patch(
            "agent.modes.pre_expediente_mode.PreExpedienteModeNode",
            mock_node,
        ):
            updates = await pre_expediente_post_tool_hook(
                "identificar_y_resolver_elementos", result_dict, state
            )

        mc = updates.get("mode_context", {})
        assert mc.get("advertencias_comunicadas") == [], (
            "advertencias_comunicadas must be reset to [] when identificar changes elements"
        )


# ===========================================================================
# Fix B — format_mode_context injects warning list
# ===========================================================================


class TestFormatModeContextWarnings:
    """B2: format_mode_context shows advertencias_comunicadas in EXPEDIENTE and PRE_EXPEDIENTE."""

    def test_expediente_mode_shows_warnings(self):
        """EXPEDIENTE_MODE: advertencias_comunicadas appears in context string."""
        from agent.prompts.loader import format_mode_context

        context = {
            "expediente_sub_mode": "collect_element_data",
            "element_codes": ["SUBCHASIS"],
            "current_element_index": 0,
            "element_phase": "photos",
            "advertencias_comunicadas": ["SUBCHASIS_REQUIRES_SPECIALIST", "CERT_REQUIRED"],
        }
        result = format_mode_context("EXPEDIENTE_MODE", context)

        assert "Advertencias YA comunicadas" in result, (
            "format_mode_context must inject advertencias_comunicadas in EXPEDIENTE_MODE"
        )
        assert "SUBCHASIS_REQUIRES_SPECIALIST" in result
        assert "CERT_REQUIRED" in result

    def test_pre_expediente_mode_shows_warnings(self):
        """PRE_EXPEDIENTE_MODE: advertencias_comunicadas appears in context string."""
        from agent.prompts.loader import format_mode_context

        context = {
            "precio_comunicado": True,
            "element_codes": ["SUBCHASIS"],
            "categoria_slug": "furgonetas-part",
            "advertencias_comunicadas": ["CERT_REQUIRED"],
        }
        result = format_mode_context("PRE_EXPEDIENTE_MODE", context)

        assert "Advertencias YA comunicadas" in result, (
            "format_mode_context must inject advertencias_comunicadas in PRE_EXPEDIENTE_MODE"
        )
        assert "CERT_REQUIRED" in result

    def test_empty_warnings_not_shown(self):
        """Empty advertencias_comunicadas list → no injection."""
        from agent.prompts.loader import format_mode_context

        context = {
            "expediente_sub_mode": "collect_element_data",
            "element_codes": ["SUBCHASIS"],
            "current_element_index": 0,
            "element_phase": "photos",
            "advertencias_comunicadas": [],
        }
        result = format_mode_context("EXPEDIENTE_MODE", context)

        assert "Advertencias YA comunicadas" not in result

    def test_missing_warnings_not_shown(self):
        """advertencias_comunicadas absent → no injection."""
        from agent.prompts.loader import format_mode_context

        context = {
            "expediente_sub_mode": "collect_element_data",
            "element_codes": ["SUBCHASIS"],
            "current_element_index": 0,
            "element_phase": "photos",
        }
        result = format_mode_context("EXPEDIENTE_MODE", context)

        assert "Advertencias YA comunicadas" not in result


# ===========================================================================
# Fix A — expediente_kickoff_pending registered in key sets
# ===========================================================================


class TestKeyRegistration:
    """A3/B3: Both new keys must appear in canonical key sets."""

    def test_kickoff_pending_in_canonical_keys(self):
        """expediente_kickoff_pending must be in CANONICAL_MODE_CONTEXT_KEYS."""
        from agent.state.mode_context_keys import CANONICAL_MODE_CONTEXT_KEYS

        assert "expediente_kickoff_pending" in CANONICAL_MODE_CONTEXT_KEYS

    def test_advertencias_comunicadas_in_canonical_keys(self):
        """advertencias_comunicadas must be in CANONICAL_MODE_CONTEXT_KEYS."""
        from agent.state.mode_context_keys import CANONICAL_MODE_CONTEXT_KEYS

        assert "advertencias_comunicadas" in CANONICAL_MODE_CONTEXT_KEYS

    def test_kickoff_pending_in_expediente_mc_keys(self):
        """expediente_kickoff_pending must be in _EXPEDIENTE_MC_KEYS (survives boundary)."""
        from agent.modes.expediente_state import _EXPEDIENTE_MC_KEYS

        assert "expediente_kickoff_pending" in _EXPEDIENTE_MC_KEYS

    def test_advertencias_comunicadas_in_expediente_mc_keys(self):
        """advertencias_comunicadas must be in _EXPEDIENTE_MC_KEYS (survives boundary)."""
        from agent.modes.expediente_state import _EXPEDIENTE_MC_KEYS

        assert "advertencias_comunicadas" in _EXPEDIENTE_MC_KEYS


# ===========================================================================
# Batch A — Failing regression tests (Strict TDD red phase)
# Post-refactor contract: cross-mode state separation + warnings_acknowledged
# ===========================================================================


class TestWarningsAcknowledged:
    """
    Red-phase tests for refactor-cross-mode-state-separation.

    These tests describe the POST-REFACTOR contract and MUST FAIL before
    Batches B-D are applied. Each test documents WHY it fails (current code)
    and WHAT it will assert once implementation is complete.
    """

    # ── A.1 ──────────────────────────────────────────────────────────────────

    def test_cross_mode_keys_contains_only_domain_data(self):
        """
        _cross_mode_keys in expediente_state.py must contain exactly the 6
        post-refactor keys: 5 domain keys + warnings_acknowledged.
        Currently fails because _cross_mode_keys has 9 keys (includes legacy UX flags).
        """
        from agent.modes.expediente_state import parent_to_expediente

        # Inspect the local _cross_mode_keys tuple via the source function.
        # We call parent_to_expediente with known SC keys and check what propagates.
        # The REAL assertion is on the tuple itself — import the module and read it.
        import agent.modes.expediente_state as exp_state_mod
        import inspect

        src = inspect.getsource(exp_state_mod.parent_to_expediente)
        expected_keys = {
            "element_codes",
            "elementos_confirmados",
            "tarifa_calculada",
            "categoria_slug",
            "vehiculo",
            "warnings_acknowledged",
        }
        forbidden_keys = {
            "advertencias_comunicadas",
            "presupuesto_images_shown",
            "precio_comunicado",
            "imagenes_enviadas",
        }

        # Build a state with all old keys present in shared_context
        parent_state = {
            "mode_context": {},
            "shared_context": {
                "element_codes": ["X"],
                "elementos_confirmados": [{"code": "X"}],
                "tarifa_calculada": {"price": 100},
                "categoria_slug": "cat-a",
                "vehiculo": {"marca": "Ford"},
                "advertencias_comunicadas": ["CERT_REQUIRED"],
                "presupuesto_images_shown": True,
                "precio_comunicado": True,
                "imagenes_enviadas": True,
            },
        }
        result = parent_to_expediente(parent_state)

        # Post-refactor: forbidden keys MUST NOT propagate from shared_context
        for key in forbidden_keys:
            assert key not in result, (
                f"_cross_mode_keys must not include '{key}' — it is a legacy UX flag "
                f"that must not propagate from PRE_EXPEDIENTE to EXPEDIENTE. "
                f"Found key in result: {key!r}"
            )

        # Post-refactor: domain keys + warnings_acknowledged MUST propagate
        for key in expected_keys - {"warnings_acknowledged"}:
            assert key in result, (
                f"Domain key '{key}' must still propagate via _cross_mode_keys"
            )

    # ── A.2 ──────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_advertencias_key_absent_after_tarifa_hook(self):
        """
        After calcular_tarifa_con_elementos with warnings, pre_expediente_post_tool_hook
        MUST NOT set shared_context['advertencias_comunicadas'].
        Currently fails because lines 223-227 of post_tool_hooks.py write that key.
        """
        from agent.modes.post_tool_hooks import pre_expediente_post_tool_hook

        result_dict = {
            "success": True,
            "datos": {
                "price": 410,
                "warnings": [
                    {"code": "SUBCHASIS_REQUIRES_SPECIALIST", "message": "Requiere especialista"},
                ],
            },
        }
        state = _make_hook_state(
            "calcular_tarifa_con_elementos",
            {"element_codes": ["SUBCHASIS"]},
            mode_context={"precio_comunicado": False},
        )

        mock_node = MagicMock()
        mock_node._extract_context_from_tool = MagicMock(return_value={})
        with patch("agent.modes.pre_expediente_mode.PreExpedienteModeNode", mock_node):
            updates = await pre_expediente_post_tool_hook(
                "calcular_tarifa_con_elementos", result_dict, state
            )

        sc = updates.get("shared_context", {})
        assert "advertencias_comunicadas" not in sc, (
            "post-refactor: pre_expediente_post_tool_hook must NOT write "
            "'advertencias_comunicadas' to shared_context. "
            f"But found shared_context={sc!r}"
        )

    # ── A.3 ──────────────────────────────────────────────────────────────────

    def test_presupuesto_images_shown_not_in_expediente_prompt(self):
        """
        format_mode_context('EXPEDIENTE_MODE', {'presupuesto_images_shown': True, ...})
        MUST NOT contain the string 'presupuesto_images_shown' in its output.
        Currently fails because loader.py:503-504 injects 'presupuesto_images_shown=true'.
        """
        from agent.prompts.loader import format_mode_context

        context = {
            "expediente_sub_mode": "collect_element_data",
            "element_codes": ["SUBCHASIS"],
            "current_element_index": 0,
            "element_phase": "photos",
            "presupuesto_images_shown": True,
        }
        result = format_mode_context("EXPEDIENTE_MODE", context)

        assert "presupuesto_images_shown" not in result, (
            "post-refactor: loader.py MUST NOT inject 'presupuesto_images_shown' "
            "into EXPEDIENTE_MODE context. "
            f"Found in output: {result!r}"
        )

    # ── A.4 ──────────────────────────────────────────────────────────────────

    def test_warnings_acknowledged_defaults_false(self):
        """
        ExpedienteState TypedDict must have field 'warnings_acknowledged'.
        When absent from a state dict, .get('warnings_acknowledged', False) must be False.
        Currently fails because the field does not exist in ExpedienteState.__annotations__.
        """
        from agent.modes.expediente_state import ExpedienteState

        annotations = ExpedienteState.__annotations__
        assert "warnings_acknowledged" in annotations, (
            "ExpedienteState TypedDict must declare 'warnings_acknowledged: bool'. "
            f"Current annotations keys: {sorted(annotations.keys())}"
        )

        # Verify the default sentinel behavior
        empty_state: ExpedienteState = {}  # type: ignore[assignment]
        assert empty_state.get("warnings_acknowledged", False) is False, (
            "'warnings_acknowledged' must default to False when absent from state dict"
        )

    # ── A.5 ──────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_iniciar_expediente_hook_emits_warnings_acknowledged(self):
        """
        On a successful iniciar_expediente tool result, pre_expediente_post_tool_hook
        MUST set updates['shared_context']['warnings_acknowledged'] == True.
        Currently fails because no such branch exists in the hook.
        """
        from agent.modes.post_tool_hooks import pre_expediente_post_tool_hook

        result_dict = {
            "success": True,
            "case_id": "case-123",
            "message": "Expediente abierto",
        }
        state = _make_hook_state(
            "iniciar_expediente",
            {"categoria_slug": "furgonetas-part"},
            mode_context={"element_codes": ["SUBCHASIS"]},
        )

        mock_node = MagicMock()
        mock_node._extract_context_from_tool = MagicMock(return_value={})
        with patch("agent.modes.pre_expediente_mode.PreExpedienteModeNode", mock_node):
            updates = await pre_expediente_post_tool_hook(
                "iniciar_expediente", result_dict, state
            )

        sc = updates.get("shared_context", {})
        assert sc.get("warnings_acknowledged") is True, (
            "post-refactor: pre_expediente_post_tool_hook must set "
            "shared_context['warnings_acknowledged'] = True on iniciar_expediente success. "
            f"Got shared_context={sc!r}"
        )

    # ── A.6 — Scenario S1 ────────────────────────────────────────────────────

    def test_no_warning_repetition_after_expediente_opens(self):
        """
        Scenario S1: format_mode_context('EXPEDIENTE_MODE', {'warnings_acknowledged': True, ...})
        output MUST contain the acceptance suppression string ('NO las repitas')
        AND MUST NOT contain 'advertencias_comunicadas'.
        Currently fails because loader.py still uses the old advertencias_comunicadas injection.
        """
        from agent.prompts.loader import format_mode_context

        context = {
            "expediente_sub_mode": "collect_element_data",
            "element_codes": ["SUBCHASIS"],
            "current_element_index": 0,
            "element_phase": "photos",
            "warnings_acknowledged": True,
        }
        result = format_mode_context("EXPEDIENTE_MODE", context)

        assert "NO las repitas" in result, (
            "post-refactor: when warnings_acknowledged=True, EXPEDIENTE_MODE context "
            "must include acceptance suppression text ('NO las repitas'). "
            f"Got output: {result!r}"
        )
        assert "advertencias_comunicadas" not in result, (
            "post-refactor: 'advertencias_comunicadas' string must never appear "
            "in EXPEDIENTE_MODE format_mode_context output. "
            f"Found in output: {result!r}"
        )

    # ── A.7 — Scenario S2 ────────────────────────────────────────────────────

    def test_element_phase_photos_when_presupuesto_images_shown(self):
        """
        Scenario S2: format_mode_context('EXPEDIENTE_MODE', {'presupuesto_images_shown': True,
        'element_phase': 'photos', ...}) MUST NOT contain 'presupuesto_images_shown=true'.
        The flag is a PRE_EXPEDIENTE UX flag and must not bleed into EXPEDIENTE context.
        Currently fails because loader.py:503-504 injects it unconditionally.
        """
        from agent.prompts.loader import format_mode_context

        context = {
            "expediente_sub_mode": "collect_element_data",
            "element_codes": ["SUBCHASIS"],
            "current_element_index": 0,
            "element_phase": "photos",
            "presupuesto_images_shown": True,
            "tarifa_calculada": {
                "documentacion": {
                    "elementos": [
                        {"codigo": "SUBCHASIS", "imagenes": [{"titulo": "Vista lateral"}]}
                    ]
                }
            },
        }
        result = format_mode_context("EXPEDIENTE_MODE", context)

        assert "presupuesto_images_shown=true" not in result, (
            "post-refactor: loader.py must NOT inject 'presupuesto_images_shown=true' "
            "into EXPEDIENTE_MODE context. This is a PRE_EXPEDIENTE UX flag. "
            f"Got output: {result!r}"
        )

    # ── A.8 — Scenario S4 ────────────────────────────────────────────────────

    def test_stale_checkpoint_with_legacy_keys_does_not_crash(self):
        """
        Scenario S4: parent_to_expediente with a shared_context containing legacy keys
        ('advertencias_comunicadas', 'presupuesto_images_shown') must NOT raise any exception.
        Stale keys are silently carried (pre-refactor behavior via .get() guards).
        Expected: PASS even before Batch B (existing .get() guards are already safe).
        """
        from agent.modes.expediente_state import parent_to_expediente

        stale_parent_state = {
            "mode_context": {},
            "shared_context": {
                "advertencias_comunicadas": ["OLD_WARNING_CODE"],
                "presupuesto_images_shown": True,
                "element_codes": ["TOLDO"],
                "tarifa_calculada": {"price": 200},
                "categoria_slug": "furgonetas-part",
                "vehiculo": {"marca": "Mercedes"},
                "elementos_confirmados": [{"code": "TOLDO"}],
            },
        }

        # Must not raise any exception
        try:
            result = parent_to_expediente(stale_parent_state)
        except Exception as exc:
            pytest.fail(
                f"parent_to_expediente raised {type(exc).__name__} with stale checkpoint keys: {exc}"
            )

        # Returned dict may contain stale keys silently — no crash is the requirement
        assert isinstance(result, dict), "parent_to_expediente must return a dict"

    # ── A.9 — Scenario S3 ────────────────────────────────────────────────────

    def test_domain_data_propagates_to_expediente(self):
        """
        Scenario S3: parent_to_expediente with shared_context containing the 5 domain keys
        must propagate all 5 into the returned ExpedienteState.
        Expected: PASS even before Batch B (existing loop at lines 278-281 already handles these).
        """
        from agent.modes.expediente_state import parent_to_expediente

        domain_parent_state = {
            "mode_context": {},
            "shared_context": {
                "element_codes": ["TOLDO", "SUBCHASIS"],
                "elementos_confirmados": [{"code": "TOLDO"}, {"code": "SUBCHASIS"}],
                "tarifa_calculada": {"datos": {"price": 850}},
                "categoria_slug": "furgonetas-part",
                "vehiculo": {"marca": "Iveco", "modelo": "Daily"},
            },
        }

        result = parent_to_expediente(domain_parent_state)

        assert result.get("element_codes") == ["TOLDO", "SUBCHASIS"], (
            "element_codes must propagate from shared_context to ExpedienteState"
        )
        assert result.get("elementos_confirmados") == [
            {"code": "TOLDO"}, {"code": "SUBCHASIS"}
        ], "elementos_confirmados must propagate from shared_context to ExpedienteState"
        assert result.get("tarifa_calculada") == {"datos": {"price": 850}}, (
            "tarifa_calculada must propagate from shared_context to ExpedienteState"
        )
        assert result.get("categoria_slug") == "furgonetas-part", (
            "categoria_slug must propagate from shared_context to ExpedienteState"
        )
        assert result.get("vehiculo") == {"marca": "Iveco", "modelo": "Daily"}, (
            "vehiculo must propagate from shared_context to ExpedienteState"
        )

    # ── A.10 — Scenario S5 ───────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_warnings_acknowledged_set_even_without_prior_warnings(self):
        """
        Scenario S5: pre_expediente_post_tool_hook('iniciar_expediente', {'success': True, ...},
        state_without_any_warnings) MUST set shared_context['warnings_acknowledged'] == True
        even when no advertencias_comunicadas was ever set.
        Currently fails because no such branch exists in the hook.
        """
        from agent.modes.post_tool_hooks import pre_expediente_post_tool_hook

        result_dict = {
            "success": True,
            "case_id": "case-456",
            "message": "Expediente abierto sin advertencias previas",
        }
        # State with NO warnings ever set — clean presupuesto flow
        state = _make_hook_state(
            "iniciar_expediente",
            {"categoria_slug": "camiones-part"},
            mode_context={
                "element_codes": ["TOLDO"],
                "precio_comunicado": True,
                "imagenes_enviadas": False,
                # Note: no 'advertencias_comunicadas' key at all
            },
        )

        mock_node = MagicMock()
        mock_node._extract_context_from_tool = MagicMock(return_value={})
        with patch("agent.modes.pre_expediente_mode.PreExpedienteModeNode", mock_node):
            updates = await pre_expediente_post_tool_hook(
                "iniciar_expediente", result_dict, state
            )

        sc = updates.get("shared_context", {})
        assert sc.get("warnings_acknowledged") is True, (
            "post-refactor: warnings_acknowledged must be set True on iniciar_expediente "
            "success even when no prior warnings were shown. "
            f"Got shared_context={sc!r}"
        )
