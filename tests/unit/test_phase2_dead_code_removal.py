"""
Phase 2 dead code removal tests.

Batch 1 — presupuesto_mode + base_mode dead code (Tasks 1.1–1.5)
Batch 2 — _shared.py Taller Guard + Claim-Gate deletion (Tasks 2.1–2.4)
Batch 3 — _shared.py Transition Closure deletion (Tasks 3.1–3.4)
Batch 4 — system-message role fix + expediente_mode cleanup (Tasks 4.1–4.4)
Batch 5 — Prompt hardening: taller vocabulary prohibition + step-number mapping (Tasks 5.1–5.5)

Each class/test documents what SHOULD NOT exist after the deletion, and verifies
the expected post-deletion state.  All tests are written BEFORE the production
changes — they FAIL now and PASS once the code is deleted/fixed.
"""

from __future__ import annotations

import importlib
import inspect
import pathlib
import types
import warnings
from typing import Any

import pytest


# ===========================================================================
# Batch 1 — presupuesto_mode + base_mode dead code
# ===========================================================================


class TestBatch11PresupuestoDeadCode:
    """Task 1.1: _check_ab_intent_mismatch and _AB_PATTERNS must be gone."""

    def test_check_ab_intent_mismatch_not_in_module(self) -> None:
        """_check_ab_intent_mismatch must NOT be a name in presupuesto_mode."""
        import agent.modes.presupuesto_mode as pm

        assert not hasattr(pm, "_check_ab_intent_mismatch"), (
            "_check_ab_intent_mismatch still exists in presupuesto_mode — "
            "it should have been deleted (task 1.2)"
        )

    def test_ab_patterns_not_in_module(self) -> None:
        """_AB_PATTERNS must NOT be a name in presupuesto_mode."""
        import agent.modes.presupuesto_mode as pm

        assert not hasattr(pm, "_AB_PATTERNS"), (
            "_AB_PATTERNS still exists in presupuesto_mode — "
            "it should have been deleted (task 1.2)"
        )

    def test_module_still_importable(self) -> None:
        """presupuesto_mode must still import without error after deletion."""
        import agent.modes.presupuesto_mode as pm  # noqa: F401

        assert pm is not None

    def test_presupuesto_mode_node_class_present(self) -> None:
        """PresupuestoModeNode must still be importable — no collateral damage."""
        from agent.modes.presupuesto_mode import PresupuestoModeNode  # noqa: F401

        assert PresupuestoModeNode is not None


class TestBatch13ValidateResponseConstraintsDeprecated:
    """Task 1.3 (updated): _validate_response_constraints must be fully deleted."""

    def test_validate_response_constraints_still_present(self) -> None:
        """_validate_response_constraints must NOT exist — it was deleted in Phase 2."""
        from agent.modes.base_mode import BaseModeNode

        assert not hasattr(BaseModeNode, "_validate_response_constraints"), (
            "_validate_response_constraints still exists in BaseModeNode — "
            "it must be fully deleted (rewrite-loop-engine Phase 2, task 2.4)"
        )

    def test_validate_response_constraints_docstring_has_deprecated(self) -> None:
        """_validate_response_constraints must not be accessible on BaseModeNode."""
        from agent.modes.base_mode import BaseModeNode

        # After deletion, the method must not exist at all.
        # Previously this test checked for a deprecation marker; now the method
        # is gone entirely (rewrite-loop-engine Phase 2, task 2.4).
        assert not hasattr(BaseModeNode, "_validate_response_constraints"), (
            "_validate_response_constraints still present on BaseModeNode — "
            "delete it entirely (rewrite-loop-engine Phase 2, task 2.4)"
        )


# ===========================================================================
# Batch 2 — _shared.py Taller Guard + Claim-Gate deletion
# ===========================================================================


class TestBatch21TallerGuardNotInAll:
    """Task 2.1: Taller guard symbols must NOT be in _shared.__all__."""

    def _shared(self) -> types.ModuleType:
        return importlib.import_module("agent.modes.submodos._shared")

    def test_taller_domain_guard_submodes_not_in_all(self) -> None:
        """_TALLER_DOMAIN_GUARD_SUBMODES must NOT be exported from _shared."""
        mod = self._shared()
        assert "_TALLER_DOMAIN_GUARD_SUBMODES" not in mod.__all__, (
            "_TALLER_DOMAIN_GUARD_SUBMODES still in _shared.__all__ — "
            "remove it from __all__ and delete the constant (task 2.2)"
        )

    def test_taller_domain_re_not_in_all(self) -> None:
        """_TALLER_DOMAIN_RE must NOT be exported from _shared."""
        mod = self._shared()
        assert "_TALLER_DOMAIN_RE" not in mod.__all__, (
            "_TALLER_DOMAIN_RE still in _shared.__all__ — "
            "remove it from __all__ and delete the constant (task 2.2)"
        )

    def test_taller_domain_guard_submodes_not_in_module(self) -> None:
        """_TALLER_DOMAIN_GUARD_SUBMODES must NOT exist as attribute in _shared."""
        mod = self._shared()
        assert not hasattr(mod, "_TALLER_DOMAIN_GUARD_SUBMODES"), (
            "_TALLER_DOMAIN_GUARD_SUBMODES still defined in _shared — "
            "delete the constant (task 2.2)"
        )

    def test_taller_domain_re_not_in_module(self) -> None:
        """_TALLER_DOMAIN_RE must NOT exist as attribute in _shared."""
        mod = self._shared()
        assert not hasattr(mod, "_TALLER_DOMAIN_RE"), (
            "_TALLER_DOMAIN_RE still defined in _shared — "
            "delete the constant (task 2.2)"
        )


class TestBatch21ClaimGateNotInAll:
    """Task 2.1: Claim-gate symbols must NOT be in _shared.__all__."""

    def _shared(self) -> types.ModuleType:
        return importlib.import_module("agent.modes.submodos._shared")

    def test_gate_response_claims_not_in_all(self) -> None:
        """_gate_response_claims must NOT be exported from _shared."""
        mod = self._shared()
        assert "_gate_response_claims" not in mod.__all__, (
            "_gate_response_claims still in _shared.__all__ — "
            "remove it from __all__ and delete the function (task 2.3)"
        )

    def test_gate_response_claims_not_in_module(self) -> None:
        """_gate_response_claims must NOT exist as attribute in _shared."""
        mod = self._shared()
        assert not hasattr(mod, "_gate_response_claims"), (
            "_gate_response_claims still defined in _shared — "
            "delete the function (task 2.3)"
        )

    def test_completion_claim_re_not_in_all(self) -> None:
        """_COMPLETION_CLAIM_RE must NOT be exported from _shared."""
        mod = self._shared()
        assert "_COMPLETION_CLAIM_RE" not in mod.__all__, (
            "_COMPLETION_CLAIM_RE still in _shared.__all__ (task 2.3)"
        )

    def test_case_finalized_claim_re_not_in_all(self) -> None:
        """_CASE_FINALIZED_CLAIM_RE must NOT be exported from _shared."""
        mod = self._shared()
        assert "_CASE_FINALIZED_CLAIM_RE" not in mod.__all__, (
            "_CASE_FINALIZED_CLAIM_RE still in _shared.__all__ (task 2.3)"
        )

    def test_images_sent_claim_re_not_in_all(self) -> None:
        """_IMAGES_SENT_CLAIM_RE must NOT be exported from _shared."""
        mod = self._shared()
        assert "_IMAGES_SENT_CLAIM_RE" not in mod.__all__, (
            "_IMAGES_SENT_CLAIM_RE still in _shared.__all__ (task 2.3)"
        )

    def test_images_intent_re_not_in_all(self) -> None:
        """_IMAGES_INTENT_RE must NOT be exported from _shared."""
        mod = self._shared()
        assert "_IMAGES_INTENT_RE" not in mod.__all__, (
            "_IMAGES_INTENT_RE still in _shared.__all__ (task 2.3)"
        )

    def test_docs_received_claim_re_not_in_all(self) -> None:
        """_DOCS_RECEIVED_CLAIM_RE must NOT be exported from _shared."""
        mod = self._shared()
        assert "_DOCS_RECEIVED_CLAIM_RE" not in mod.__all__, (
            "_DOCS_RECEIVED_CLAIM_RE still in _shared.__all__ (task 2.3)"
        )


class TestBatch24SharedStillImportable:
    """Task 2.4: _shared must still import cleanly after deletions."""

    def test_shared_module_importable(self) -> None:
        """_shared must be importable without error."""
        from agent.modes.submodos import _shared  # noqa: F401

        assert _shared is not None

    def test_sub_mode_constants_preserved(self) -> None:
        """Core sub-mode constants must remain after taller guard deletion."""
        from agent.modes.submodos._shared import (
            COLLECT_ELEMENT_DATA,
            COLLECT_BASE_DOCS,
            COLLECT_PERSONAL,
            COLLECT_VEHICLE,
            COLLECT_WORKSHOP,
            REVIEW_SUMMARY,
            _SUBMODE_STEP_MAP,
            SUB_MODE_STEP,
        )

        assert COLLECT_ELEMENT_DATA == "collect_element_data"
        assert COLLECT_BASE_DOCS == "collect_base_docs"
        assert COLLECT_PERSONAL == "collect_personal"
        assert COLLECT_VEHICLE == "collect_vehicle"
        assert COLLECT_WORKSHOP == "collect_workshop"
        assert REVIEW_SUMMARY == "review_summary"
        assert isinstance(_SUBMODE_STEP_MAP, dict)
        assert len(_SUBMODE_STEP_MAP) == 6
        assert SUB_MODE_STEP is not None


# ---------------------------------------------------------------------------
# Batch 3.1 [RED] — Closure symbols must NOT exist in _shared after deletion
# ---------------------------------------------------------------------------


class TestBatch31ClosureSymbolsAbsent:
    """Task 3.1: closure / transition-matrix symbols removed from _shared.py."""

    # Symbols to be DELETED (zero callers outside _shared.py)
    DELETED_SYMBOLS = [
        "_build_element_completion_transition_closure",
        "_get_transition_base_documentation",
        "_ClosureBuilder",
        "_build_base_docs_to_personal_closure",
        "_build_personal_to_vehicle_closure",
        "_build_vehicle_to_workshop_closure",
        "_build_workshop_to_review_closure",
        "_TRANSITION_MATRIX",
    ]

    # Symbols to be KEPT (have live callers in expediente_mode.py)
    KEPT_SYMBOLS = [
        "_build_transition_marker",
        "_set_transition_updates",
    ]

    def _get_shared_module(self) -> types.ModuleType:
        return importlib.import_module("agent.modes.submodos._shared")

    def test_deleted_symbols_not_in_module(self) -> None:
        """Deleted closure symbols must not be attributes of the _shared module."""
        mod = self._get_shared_module()
        for sym in self.DELETED_SYMBOLS:
            assert not hasattr(mod, sym), (
                f"Symbol '{sym}' still present in _shared — should have been deleted."
            )

    def test_deleted_symbols_not_in_all(self) -> None:
        """Deleted symbols must not appear in __all__."""
        mod = self._get_shared_module()
        all_exports: list[str] = getattr(mod, "__all__", [])
        for sym in self.DELETED_SYMBOLS:
            assert sym not in all_exports, (
                f"Symbol '{sym}' still listed in _shared.__all__."
            )

    def test_kept_symbols_still_present(self) -> None:
        """_build_transition_marker and _set_transition_updates must remain (live callers)."""
        mod = self._get_shared_module()
        for sym in self.KEPT_SYMBOLS:
            assert hasattr(mod, sym), (
                f"Symbol '{sym}' was removed but has live callers in expediente_mode.py."
            )

    def test_kept_symbols_still_in_all(self) -> None:
        """Kept symbols remain in __all__ so expediente_mode.py imports continue working."""
        mod = self._get_shared_module()
        all_exports: list[str] = getattr(mod, "__all__", [])
        for sym in self.KEPT_SYMBOLS:
            assert sym in all_exports, (
                f"Symbol '{sym}' missing from _shared.__all__ — expediente_mode.py will break."
            )

    def test_shared_py_line_count_reduced_by_closure_deletion(self) -> None:
        """_shared.py line count must drop by ~240 lines after closure deletion.

        Original: 1,580 lines.
        Batch 3 removes ~240 lines of closures → expected <= 1,350.
        Full target (Batch 2 + Batch 3 together): < 1,150.
        Note: Batch 2 deletions (taller guard ~22 + claim-gate ~220) are separate.
        """
        path = pathlib.Path("agent/modes/submodos/_shared.py")
        lines = path.read_text().splitlines()
        assert len(lines) <= 1350, (
            f"_shared.py has {len(lines)} lines — expected <= 1,350 after Batch-3 closure deletion."
        )
        # File must be smaller than the original 1,580 (proves something was deleted)
        assert len(lines) < 1580, (
            f"_shared.py has {len(lines)} lines — same as original 1,580. "
            "Closure deletion did not take effect."
        )

    def test_step_constants_remain(self) -> None:
        """Core step constants required by submodo handlers must still be present."""
        mod = self._get_shared_module()
        required = [
            "COLLECT_ELEMENT_DATA",
            "COLLECT_BASE_DOCS",
            "COLLECT_PERSONAL",
            "COLLECT_VEHICLE",
            "COLLECT_WORKSHOP",
            "REVIEW_SUMMARY",
            "_SUBMODE_STEP_MAP",
            "SUB_MODE_STEP",
            "MAX_TOOL_ITERATIONS",
        ]
        for sym in required:
            assert hasattr(mod, sym), (
                f"Required constant '{sym}' is missing from _shared — must not have been deleted."
            )


# ---------------------------------------------------------------------------
# Batch 4.1 [RED] — on_tool_result returns role:"assistant" not "system"
# ---------------------------------------------------------------------------


class TestBatch41PresupuestoRoleAssistant:
    """Task 4.1: on_tool_result inject_messages use role:'assistant' not 'system'."""

    def _inspect_presupuesto_source(self) -> str:
        """Return the raw source of presupuesto_mode.py for pattern checks."""
        path = pathlib.Path("agent/modes/presupuesto_mode.py")
        return path.read_text()

    def test_no_system_role_in_variant_discovery_inject(self) -> None:
        """Line ~673: variant-discovery injection must use role:'assistant', not 'system'."""
        source = self._inspect_presupuesto_source()
        # After fix: "role": "system" should not appear in any inject_messages block
        # We verify by checking the source does NOT contain the exact banned pattern
        # within an inject_messages context.
        # Robust check: count of 'role": "system"' occurrences should be exactly 1
        # (the S4 price-authority injection that must remain — documented in AGENTS.md rule 16).
        system_role_count = source.count('"role": "system"')
        assert system_role_count <= 1, (
            f'Found {system_role_count} occurrences of \'"role": "system"\' in presupuesto_mode.py. '
            "After fix: only the S4 price-authority injection (rule 16) should remain."
        )

    def test_assistant_role_in_variant_discovery_inject(self) -> None:
        """
        T-18 Phase 3 migration: inject_messages fully removed from presupuesto_mode.

        The old behavior: inject_messages with role:'assistant' (protocol corruption).
        The new behavior: state updates via _state_update/_generic_loop_tool_callback.
        This test now verifies the NEW state: no inject_messages at all.

        Updated from original (which checked old log key still present) to reflect
        T-18 migration that removed inject_messages entirely.
        """
        source = self._inspect_presupuesto_source()
        # T-18 migration: presupuesto_variant_discovery_injection log key removed
        assert "presupuesto_variant_discovery_injection" not in source, (
            "Old inject_messages log key should be gone after T-18 migration."
        )
        # T-25 migration: _process_with_generic_loop fully removed.
        # Neither the old nor the intermediate log keys should exist anymore —
        # the entire fallback method was deleted.
        # The new behavior: variant resolution via _state_update channel in tool_loop.
        # No inject_messages keys should exist
        assert "inject_messages" not in source, (
            "inject_messages anti-pattern must be fully removed by T-18."
        )

    def test_no_system_role_in_all_resolved_inject(self) -> None:
        """
        T-18 Phase 3: all-variants-resolved logic no longer uses inject_messages.

        Updated from original (which checked role:'system' not used) to reflect
        T-18 migration that removed inject_messages entirely.
        """
        source = self._inspect_presupuesto_source()
        # T-18 migration: inject_messages fully removed, log key renamed
        assert "presupuesto_variants_all_resolved_injection" not in source or (
            "inject_messages" not in source
        ), "After T-18: either the old log key is gone OR inject_messages is gone."
        # Verify no inject_messages in the fallback path either
        assert "inject_messages" not in source, (
            "inject_messages must be fully removed from presupuesto_mode.py by T-18."
        )


# ---------------------------------------------------------------------------
# Batch 4.3 [RED] — expediente_mode must not reference evaluate_kickoff_truthfulness
# ---------------------------------------------------------------------------


class TestBatch43ExpedienteModeCleanup:
    """Task 4.3: evaluate_kickoff_truthfulness removed from expediente_mode.py."""

    def _get_expediente_source(self) -> str:
        path = pathlib.Path("agent/modes/expediente_mode.py")
        return path.read_text()

    def test_no_evaluate_kickoff_truthfulness_in_source(self) -> None:
        """expediente_mode.py must not contain 'evaluate_kickoff_truthfulness'."""
        source = self._get_expediente_source()
        assert "evaluate_kickoff_truthfulness" not in source, (
            "Found 'evaluate_kickoff_truthfulness' in expediente_mode.py — "
            "import and all call sites must be removed."
        )

    def test_expediente_mode_imports_succeed(self) -> None:
        """expediente_mode must import without errors after cleanup."""
        import importlib

        mod = importlib.import_module("agent.modes.expediente_mode")
        assert mod is not None

    def test_evaluate_kickoff_still_in_guardrails(self) -> None:
        """expediente_guardrails.py must NOT exist — it was fully deleted in Phase 2."""
        guardrails_path = pathlib.Path("agent/modes/expediente_guardrails.py")
        assert not guardrails_path.exists(), (
            "expediente_guardrails.py still exists — it must be fully deleted "
            "(rewrite-loop-engine Phase 2, task 2.1)"
        )

    def test_guardrails_function_is_deprecated(self) -> None:
        """expediente_guardrails module must not be importable — file was deleted."""
        import importlib

        try:
            importlib.import_module("agent.modes.expediente_guardrails")
            # If import succeeded, the file still exists — that's a failure
            assert False, (  # noqa: B011
                "agent.modes.expediente_guardrails is still importable — "
                "the file must be deleted (rewrite-loop-engine Phase 2, task 2.1)"
            )
        except (ImportError, ModuleNotFoundError):
            # Expected: module does not exist after deletion
            pass


# ===========================================================================
# Batch 5 — Prompt hardening: taller vocabulary + step-number mapping
# ===========================================================================

_PROMPTS_ROOT = pathlib.Path("agent/prompts")
_CORE_PROMPTS = _PROMPTS_ROOT / "core"
_MODE_PROMPTS = _PROMPTS_ROOT / "modes"


class TestBatch51TallerVocabularyProhibition:
    """Task 5.1: expediente_datos_personales.md and expediente_datos_vehiculo.md must
    contain an explicit taller vocabulary prohibition sentence."""

    # The exact canonical phrase added by tasks 5.2 / 5.3
    _PROHIBITION = (
        "NO menciones talleres, certificados de montaje, 85€, ni instalaciones."
    )

    def _read_prompt(self, filename: str) -> str:
        path = _MODE_PROMPTS / filename
        assert path.exists(), f"Prompt file not found: {path}"
        return path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # expediente_datos_personales.md
    # ------------------------------------------------------------------

    def test_datos_personales_contains_taller_prohibition(self) -> None:
        """expediente_datos_personales.md must explicitly prohibit taller vocabulary."""
        content = self._read_prompt("expediente_datos_personales.md")
        assert self._PROHIBITION in content, (
            f"expediente_datos_personales.md is missing the taller vocabulary prohibition.\n"
            f"Expected to find:\n  {self._PROHIBITION!r}\n"
            "Add it to the 'Dominio restringido' rule (task 5.2)."
        )

    def test_datos_personales_prohibition_is_in_reglas_criticas(self) -> None:
        """The prohibition must appear inside the 'Reglas CRITICAS' section."""
        content = self._read_prompt("expediente_datos_personales.md")
        criticas_start = content.find("## Reglas CRITICAS")
        assert criticas_start != -1, (
            "Section '## Reglas CRITICAS' not found in expediente_datos_personales.md"
        )
        criticas_section = content[criticas_start:]
        assert self._PROHIBITION in criticas_section, (
            "The taller prohibition must be inside '## Reglas CRITICAS', not elsewhere in the file."
        )

    # ------------------------------------------------------------------
    # expediente_datos_vehiculo.md
    # ------------------------------------------------------------------

    def test_datos_vehiculo_contains_taller_prohibition(self) -> None:
        """expediente_datos_vehiculo.md must explicitly prohibit taller vocabulary."""
        content = self._read_prompt("expediente_datos_vehiculo.md")
        assert self._PROHIBITION in content, (
            f"expediente_datos_vehiculo.md is missing the taller vocabulary prohibition.\n"
            f"Expected to find:\n  {self._PROHIBITION!r}\n"
            "Add it to the 'Dominio restringido' rule (task 5.3)."
        )

    def test_datos_vehiculo_prohibition_is_in_reglas_criticas(self) -> None:
        """The prohibition must appear inside the 'Reglas CRITICAS' section."""
        content = self._read_prompt("expediente_datos_vehiculo.md")
        criticas_start = content.find("## Reglas CRITICAS")
        assert criticas_start != -1, (
            "Section '## Reglas CRITICAS' not found in expediente_datos_vehiculo.md"
        )
        criticas_section = content[criticas_start:]
        assert self._PROHIBITION in criticas_section, (
            "The taller prohibition must be inside '## Reglas CRITICAS', not elsewhere in the file."
        )


class TestBatch51StepNumberMapping:
    """Task 5.1: 10_expediente_universal.md must contain an explicit step-number mapping rule."""

    # Key sub-strings that together constitute the canonical step mapping
    _STEP_PAIRS = [
        ("Paso 1", "Elementos"),
        ("Paso 2", "Docs base"),
        ("Paso 3", "Datos personales"),
        ("Paso 4", "Datos vehículo"),
        ("Paso 5", "Taller"),
        ("Paso 6", "Revisión"),
    ]
    # The tool-confirmation clause
    _TOOL_CLAUSE = "sin llamada a herramienta que confirme completitud"

    def _read_universal(self) -> str:
        path = _CORE_PROMPTS / "10_expediente_universal.md"
        assert path.exists(), f"Core prompt not found: {path}"
        return path.read_text(encoding="utf-8")

    def test_step_mapping_all_pairs_present(self) -> None:
        """10_expediente_universal.md must contain all six step-number→name pairs."""
        content = self._read_universal()
        for step_label, step_name in self._STEP_PAIRS:
            assert step_label in content, (
                f"Missing step label '{step_label}' in 10_expediente_universal.md (task 5.4)."
            )
            assert step_name in content, (
                f"Missing step name '{step_name}' in 10_expediente_universal.md (task 5.4)."
            )

    def test_step_mapping_tool_confirmation_clause_present(self) -> None:
        """10_expediente_universal.md must prohibit advancement language without tool confirmation."""
        content = self._read_universal()
        assert self._TOOL_CLAUSE in content, (
            f"Missing tool-confirmation clause in 10_expediente_universal.md.\n"
            f"Expected to find: {self._TOOL_CLAUSE!r}\n"
            "Add the full step-mapping rule (task 5.4)."
        )
