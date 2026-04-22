"""
Tests for root-expediente-ux fixes.

Fix A: Code-driven kickoff confirmation (deprecated — intro is now LLM-generated)

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


# (TestPostToolHookWarningExtraction and TestFormatModeContextWarnings deleted in
# Batch D of refactor-cross-mode-state-separation: those tests asserted behavior
# that was explicitly removed — advertencias_comunicadas extraction and cross-mode
# propagation. The replacement contract is in TestWarningsAcknowledged below.)


# ===========================================================================
# Key registration tests
# ===========================================================================


class TestKeyRegistration:
    """Canonical key set registration tests."""

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


