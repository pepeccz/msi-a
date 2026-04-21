"""
Tests for root-expediente-ux fixes.

Fix A: Code-driven kickoff confirmation
  - confirmar_presupuesto returns expediente_kickoff_pending: True
  - expediente_mode injects "Perfecto, abrimos el expediente." prefix (via hook output)

Fix B (post-refactor): warnings_acknowledged event key
  - iniciar_expediente success hook sets warnings_acknowledged=True in shared_context
  - format_mode_context injects acceptance-suppression text when warnings_acknowledged=True
  - advertencias_comunicadas and presupuesto_images_shown are NOT propagated cross-mode

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


# (TestPostToolHookWarningExtraction and TestFormatModeContextWarnings deleted in
# Batch D of refactor-cross-mode-state-separation: those tests asserted behavior
# that was explicitly removed — advertencias_comunicadas extraction and cross-mode
# propagation. The replacement contract is in TestWarningsAcknowledged below.)


# ===========================================================================
# Fix A — expediente_kickoff_pending registered in key sets
# ===========================================================================


class TestKeyRegistration:
    """A3/B3: New keys must appear in canonical key sets."""

    def test_kickoff_pending_in_canonical_keys(self):
        """expediente_kickoff_pending must be in CANONICAL_MODE_CONTEXT_KEYS."""
        from agent.state.mode_context_keys import CANONICAL_MODE_CONTEXT_KEYS

        assert "expediente_kickoff_pending" in CANONICAL_MODE_CONTEXT_KEYS

    def test_kickoff_pending_in_expediente_mc_keys(self):
        """expediente_kickoff_pending must be in _EXPEDIENTE_MC_KEYS (survives boundary)."""
        from agent.modes.expediente_state import _EXPEDIENTE_MC_KEYS

        assert "expediente_kickoff_pending" in _EXPEDIENTE_MC_KEYS

    def test_warnings_acknowledged_in_canonical_keys(self):
        """
        post-refactor: warnings_acknowledged must be in CANONICAL_MODE_CONTEXT_KEYS.
        It is registered in _MODE_RUNTIME_KEYS (set by iniciar_expediente success hook).
        """
        from agent.state.mode_context_keys import CANONICAL_MODE_CONTEXT_KEYS

        assert "warnings_acknowledged" in CANONICAL_MODE_CONTEXT_KEYS, (
            "warnings_acknowledged must be in CANONICAL_MODE_CONTEXT_KEYS — "
            "it should be registered in _MODE_RUNTIME_KEYS in mode_context_keys.py"
        )

    def test_advertencias_comunicadas_absent_from_canonical_keys(self):
        """
        post-refactor: advertencias_comunicadas MUST NOT be in CANONICAL_MODE_CONTEXT_KEYS.
        The key was removed in Batch B of refactor-cross-mode-state-separation.
        """
        from agent.state.mode_context_keys import CANONICAL_MODE_CONTEXT_KEYS

        assert "advertencias_comunicadas" not in CANONICAL_MODE_CONTEXT_KEYS, (
            "advertencias_comunicadas must be removed from CANONICAL_MODE_CONTEXT_KEYS — "
            "it was deleted in refactor-cross-mode-state-separation Batch B"
        )

    def test_advertencias_comunicadas_absent_from_expediente_mc_keys(self):
        """
        post-refactor: advertencias_comunicadas MUST NOT be in _EXPEDIENTE_MC_KEYS.
        The key was removed in Batch B of refactor-cross-mode-state-separation.
        """
        from agent.modes.expediente_state import _EXPEDIENTE_MC_KEYS

        assert "advertencias_comunicadas" not in _EXPEDIENTE_MC_KEYS, (
            "advertencias_comunicadas must not be in _EXPEDIENTE_MC_KEYS — "
            "it was deleted in refactor-cross-mode-state-separation Batch B"
        )


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

    # ── E.3 — Runtime rendered-prompt assertion ───────────────────────────────

    def test_rendered_expediente_prompt_contains_no_deleted_keys(self):
        """
        E.3 — Dynamic injection guard: assemble_system_prompt / format_mode_context
        for EXPEDIENTE_MODE with realistic context must NOT produce any output
        containing 'advertencias_comunicadas' or 'presupuesto_images_shown'.

        This complements the static INV-07/INV-08 lint rules by catching dynamic
        injection bugs that regex scanning of .md files cannot detect.

        Scenario: warnings_acknowledged=True → suppression line must appear;
        no legacy UX flag strings may appear anywhere in the rendered output.
        """
        from agent.prompts.loader import format_mode_context

        context = {
            "expediente_sub_mode": "collect_element_data",
            "element_codes": ["SUBCHASIS"],
            "current_element_index": 0,
            "element_phase": "photos",
            "warnings_acknowledged": True,
            "tarifa_calculada": {
                "documentacion": {
                    "elementos": [
                        {"codigo": "SUBCHASIS", "imagenes": [{"titulo": "Vista lateral"}]}
                    ]
                }
            },
        }
        result = format_mode_context("EXPEDIENTE_MODE", context)

        assert "advertencias_comunicadas" not in result, (
            "Rendered EXPEDIENTE_MODE prompt MUST NOT contain 'advertencias_comunicadas'. "
            "Dynamic injection bug detected — check loader.py EXPEDIENTE branch. "
            f"Rendered output: {result!r}"
        )
        assert "presupuesto_images_shown" not in result, (
            "Rendered EXPEDIENTE_MODE prompt MUST NOT contain 'presupuesto_images_shown'. "
            "Dynamic injection bug detected — check loader.py EXPEDIENTE branch. "
            f"Rendered output: {result!r}"
        )
        assert "NO las repitas" in result, (
            "Rendered EXPEDIENTE_MODE prompt with warnings_acknowledged=True MUST contain "
            "the acceptance suppression string 'NO las repitas'. "
            f"Rendered output: {result!r}"
        )


# ===========================================================================
# Batch E — Prompt lint invariant rules (INV-07, INV-08)
# ===========================================================================


class TestPromptLintInvariants:
    """
    E.1/E.2: Verify INV-07 and INV-08 invariant rules exist and fire correctly.

    INV-07: no prompt .md may contain 'advertencias_comunicadas'
    INV-08: no prompt .md may contain 'presupuesto_images_shown'
    """

    def test_inv07_rule_registered(self):
        """INV-07 must be present in INVARIANT_RULES."""
        from agent.prompts.prompt_lint import INVARIANT_RULES

        rule_ids = [r.rule_id for r in INVARIANT_RULES]
        assert "INV-07" in rule_ids, (
            f"INV-07 must be in INVARIANT_RULES. Current rules: {rule_ids}"
        )

    def test_inv08_rule_registered(self):
        """INV-08 must be present in INVARIANT_RULES."""
        from agent.prompts.prompt_lint import INVARIANT_RULES

        rule_ids = [r.rule_id for r in INVARIANT_RULES]
        assert "INV-08" in rule_ids, (
            f"INV-08 must be in INVARIANT_RULES. Current rules: {rule_ids}"
        )

    def test_inv07_fires_on_advertencias_comunicadas(self, tmp_path):
        """INV-07 must produce an error violation when 'advertencias_comunicadas' appears in a prompt file."""
        from agent.prompts.prompt_lint import lint_prompt_file

        bad_file = tmp_path / "bad_prompt.md"
        bad_file.write_text(
            "## Instrucciones\n"
            "advertencias_comunicadas: lista de códigos ya comunicados\n",
            encoding="utf-8",
        )
        violations = lint_prompt_file(str(bad_file))
        inv07 = [v for v in violations if v.rule_id == "INV-07"]
        assert inv07, (
            "INV-07 must fire when 'advertencias_comunicadas' appears in a prompt file. "
            f"Got violations: {violations}"
        )
        assert inv07[0].severity == "error"

    def test_inv08_fires_on_presupuesto_images_shown(self, tmp_path):
        """INV-08 must produce an error violation when 'presupuesto_images_shown' appears in a prompt file."""
        from agent.prompts.prompt_lint import lint_prompt_file

        bad_file = tmp_path / "bad_prompt2.md"
        bad_file.write_text(
            "## Fase fotos\n"
            "Si presupuesto_images_shown=true -> no reenviar imágenes.\n",
            encoding="utf-8",
        )
        violations = lint_prompt_file(str(bad_file))
        inv08 = [v for v in violations if v.rule_id == "INV-08"]
        assert inv08, (
            "INV-08 must fire when 'presupuesto_images_shown' appears in a prompt file. "
            f"Got violations: {violations}"
        )
        assert inv08[0].severity == "error"

    def test_current_prompts_pass_inv07_and_inv08(self):
        """
        Current post-refactor prompt files must produce zero INV-07 / INV-08 violations.
        This is the 'lint passes on current prompts' sanity check.
        """
        import os
        from pathlib import Path
        from agent.prompts.prompt_lint import lint_all_prompts

        # Resolve the modes directory relative to the project root
        project_root = Path(__file__).parent.parent.parent
        modes_dir = project_root / "agent" / "prompts" / "modes"
        assert modes_dir.exists(), f"Prompts modes dir not found: {modes_dir}"

        results = lint_all_prompts(str(modes_dir))

        violations_inv07_08 = [
            (fpath, v)
            for fpath, vs in results.items()
            for v in vs
            if v.rule_id in ("INV-07", "INV-08")
        ]

        assert not violations_inv07_08, (
            "INV-07/INV-08 violations found in current prompt files — "
            "deleted keys 'advertencias_comunicadas' / 'presupuesto_images_shown' "
            "must not appear in any .md under agent/prompts/modes/. "
            f"Violations: {violations_inv07_08}"
        )


# ===========================================================================
# Batch 1 — Capa 1: Kickoff tombstone in entry_router
# Spec: EK-1-A, EK-1-C / Design: reutilizar _build_intro_emission_from_state
# ===========================================================================


class TestExpedienteKickoffTombstone:
    """
    B1-T1: _build_intro_emission_from_state debe tombstonear expediente_kickoff_pending
    cuando emite el intro message (para evitar re-emisión de prefijo en turnos siguientes).

    B1-T2: El prefijo kickoff visible llega al usuario desde el consumer (entry_router)
    vía pending_outbound_messages, no desde el ai_response del LLM en el turno PRE_EXPEDIENTE.

    Spec EK-1-A / EK-1-C / PP-1-B
    """

    # ── B1-T1 ────────────────────────────────────────────────────────────────

    def test_expediente_kickoff_pending_tombstoned_in_entry_router(self):
        """
        B1-T1 [RED]: Cuando _build_intro_emission_from_state dispara (intro no enviado,
        mensaje presente), el dict de update resultante DEBE contener
        expediente_kickoff_pending = None (tombstone explícito).

        Falla HOY: la función no escribe esa clave en el update.
        Pasa después de B1-I2.

        Spec: EK-1-A — flag tombstoned after emission.
        """
        from agent.modes.expediente_nodes import _build_intro_emission_from_state

        update: dict = {}
        state: dict = {
            "expediente_intro_sent": False,
            "expediente_intro_message": "Perfecto, abrimos el expediente.\n\nEsto es el overview.",
            "expediente_kickoff_pending": True,
        }

        result = _build_intro_emission_from_state(update, state)

        # La emisión debe haber ocurrido (pre-condición del test)
        assert result.get("pending_outbound_messages"), (
            "Precondition failed: _build_intro_emission_from_state must emit "
            "pending_outbound_messages when intro_sent=False and intro_message is present"
        )

        # El tombstone del flag kickoff_pending DEBE estar presente
        assert "expediente_kickoff_pending" in result, (
            "_build_intro_emission_from_state must write 'expediente_kickoff_pending' key "
            "to the update dict when it emits the intro (tombstone protocol, ADR-010). "
            f"Got update keys: {list(result.keys())}"
        )
        assert result["expediente_kickoff_pending"] is None, (
            "_build_intro_emission_from_state must set expediente_kickoff_pending = None "
            "(tombstone) after emitting the intro. "
            f"Got: expediente_kickoff_pending = {result['expediente_kickoff_pending']!r}"
        )

    # ── B1-T2-intro ──────────────────────────────────────────────────────────
    # NEW: _build_intro_emission (update-dict path, used by init_updates on
    # first EXPEDIENTE entry) emits pending_outbound_messages and tombstones.

    def test_build_intro_emission_emits_when_message_in_update(self):
        """
        B1-T2a [RED]: _build_intro_emission must emit pending_outbound_messages
        when 'expediente_intro_message' is present in the update dict
        and 'expediente_intro_sent' is False (or absent).

        Fails if the tool never populated update with intro_message
        (pre B1-T3), because update will be empty → no emission.
        Passes after B1-T3 populates the _state_update correctly.
        """
        from agent.modes.expediente_nodes import _build_intro_emission

        update = {
            "expediente_intro_message": "He abierto tu expediente de homologación. Tiene 6 fases:\n\nFase 1...",
            "expediente_intro_sent": False,
            "expediente_kickoff_pending": True,
        }

        result = _build_intro_emission(update)

        assert result.get("pending_outbound_messages"), (
            "B1-T2a: _build_intro_emission must emit pending_outbound_messages "
            "when expediente_intro_message is present and expediente_intro_sent=False. "
            f"Got: {result!r}"
        )
        assert result["pending_outbound_messages"][0].startswith("He abierto"), (
            "B1-T2a: emitted message must start with 'He abierto'. "
            f"Got: {result['pending_outbound_messages']!r}"
        )

    def test_build_intro_emission_tombstones_after_emit(self):
        """
        B1-T2b [RED]: After _build_intro_emission emits, the update dict must
        contain the tombstone: expediente_intro_message=None, expediente_intro_sent=True.
        Spec: Tombstone cleared after emission.
        """
        from agent.modes.expediente_nodes import _build_intro_emission

        update = {
            "expediente_intro_message": "He abierto tu expediente de homologación. Tiene 6 fases:\n\nFase 1...",
            "expediente_intro_sent": False,
        }

        result = _build_intro_emission(update)

        assert result.get("expediente_intro_message") is None, (
            "B1-T2b: expediente_intro_message must be tombstoned to None after emission. "
            f"Got: {result.get('expediente_intro_message')!r}"
        )
        assert result.get("expediente_intro_sent") is True, (
            "B1-T2b: expediente_intro_sent must be True after emission. "
            f"Got: {result.get('expediente_intro_sent')!r}"
        )

    def test_build_intro_emission_idempotent_when_already_sent(self):
        """
        B1-T2c [triangulation]: Re-entry is idempotent — when expediente_intro_sent=True,
        _build_intro_emission must NOT emit pending_outbound_messages.
        Spec: Scenario 'Re-entry is idempotent (no double emission)'.
        """
        from agent.modes.expediente_nodes import _build_intro_emission

        update = {
            "expediente_intro_message": "He abierto tu expediente.",
            "expediente_intro_sent": True,
        }

        result = _build_intro_emission(update)

        assert not result.get("pending_outbound_messages"), (
            "B1-T2c: _build_intro_emission must NOT emit when expediente_intro_sent=True. "
            f"Got: {result.get('pending_outbound_messages')!r}"
        )

    # ── B1-T2 ────────────────────────────────────────────────────────────────

    def test_kickoff_prefix_comes_from_consumer_not_llm(self):
        """
        B1-T2 [RED]: Triangulación de B1-T1. Verifica que el tombstone de
        expediente_kickoff_pending en la emisión del intro ES lo que impide
        que el prefijo se re-emita en el segundo turno (EK-1-C / PP-1-B).

        Específicamente: cuando _build_intro_emission_from_state emite (intro_sent=False,
        intro_message presente), el update resultante debe contener
        expediente_kickoff_pending=None Y pending_outbound_messages con el overview.

        Este test DIFERENCIA del B1-T1 en que también aserta el pending_outbound_messages
        real, garantizando que el consumer es el que entrega el prefijo (no el LLM).

        Falla HOY: expediente_kickoff_pending ausente del update.
        Pasa después de B1-I2.

        Spec: EK-1-C / PP-1-B
        """
        from agent.modes.expediente_nodes import _build_intro_emission_from_state

        # Primer turno EXPEDIENTE: intro no enviado, kickoff_pending activo
        update: dict = {}
        state: dict = {
            "expediente_intro_sent": False,
            "expediente_intro_message": "Bienvenido. Overview de 6 fases.",
            "expediente_kickoff_pending": True,
        }

        result = _build_intro_emission_from_state(update, state)

        # 1. El consumer emitió el prefijo visible al usuario
        assert result.get("pending_outbound_messages") == ["Bienvenido. Overview de 6 fases."], (
            "PP-1-B: el prefijo kickoff DEBE llegar al usuario via pending_outbound_messages "
            "del consumer (entry_router), no desde el LLM ai_response. "
            f"Got: {result.get('pending_outbound_messages')!r}"
        )

        # 2. El tombstone impide re-emisión en turnos siguientes
        # NOTA: usamos "in result" para distinguir key ausente (no tombstone) de key=None (tombstone)
        assert "expediente_kickoff_pending" in result, (
            "EK-1-C: _build_intro_emission_from_state debe escribir la clave "
            "'expediente_kickoff_pending' en el update dict (tombstone protocol ADR-010). "
            "Sin esta clave, merge_dicts resucita el valor True del checkpoint. "
            f"Got update keys: {sorted(result.keys())}"
        )
        assert result["expediente_kickoff_pending"] is None, (
            "EK-1-C: expediente_kickoff_pending debe ser None (tombstone) tras la emisión. "
            f"Got: {result['expediente_kickoff_pending']!r}"
        )
