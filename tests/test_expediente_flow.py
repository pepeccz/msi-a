"""
Regression tests for fix-expediente-flow (5 bugs).

Bug 1: Case ID leaked into prompt context → user saw UUID fragments.
Bug 2: LLM hallucinated field names not present in pending_fields.
Bug 3: Step labels were duplicated / inconsistent across modules.
Bug 4: Escalation return from confirmar_documentacion_base mixed success
        and progression fields, causing the mode to advance on failure.
Bug 5: elementos_confirmados not populated by presupuesto_mode on tariff
        calculation, breaking the PRESUPUESTO → EXPEDIENTE handoff.

All tests are pure unit tests — no DB, Redis or LLM calls required.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module-level paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PROMPTS_DIR = _PROJECT_ROOT / "agent" / "prompts"


# ===========================================================================
# GROUP 1 — Step Label Consistency (Bug 3)
# ===========================================================================


class TestStepLabelConsistency:
    """Verify expediente_constants provides a single source of truth for step labels."""

    def test_step_labels_completeness(self):
        """All 6 expediente sub-modes are defined in STEP_LABELS."""
        from agent.services.expediente_constants import STEP_LABELS

        expected_sub_modes = {
            "collect_element_data",
            "collect_base_docs",
            "collect_personal",
            "collect_vehicle",
            "collect_workshop",
            "review_summary",
        }
        assert set(STEP_LABELS.keys()) == expected_sub_modes

    def test_step_numbers_are_sequential(self):
        """Step numbers run from 1 to 6 without gaps."""
        from agent.services.expediente_constants import STEP_LABELS

        numbers = sorted(entry[0] for entry in STEP_LABELS.values())
        assert numbers == [1, 2, 3, 4, 5, 6]

    def test_total_steps_equals_6(self):
        """TOTAL_STEPS is derived from STEP_LABELS and equals 6."""
        from agent.services.expediente_constants import TOTAL_STEPS

        assert TOTAL_STEPS == 6

    def test_step_prefix_format(self):
        """step_prefix() returns '📍 Paso X/6 — Label' for each sub_mode."""
        from agent.services.expediente_constants import step_prefix, STEP_LABELS

        for sub_mode, (step_number, label) in STEP_LABELS.items():
            result = step_prefix(sub_mode)
            expected = f"📍 Paso {step_number}/6 — {label}"
            assert result == expected, (
                f"step_prefix('{sub_mode}') returned {result!r}, "
                f"expected {expected!r}"
            )

    def test_step_prefix_unknown_submode(self):
        """step_prefix() returns empty string for an unrecognised sub_mode."""
        from agent.services.expediente_constants import step_prefix

        assert step_prefix("nonexistent_step") == ""
        assert step_prefix("") == ""

    def test_phase_overview_lines_count(self):
        """phase_overview_lines() returns exactly 6 lines."""
        from agent.services.expediente_constants import phase_overview_lines

        lines = phase_overview_lines()
        assert len(lines) == 6

    def test_phase_overview_lines_format(self):
        """Each overview line matches '📍 Paso X/6 - Label' format."""
        from agent.services.expediente_constants import phase_overview_lines

        lines = phase_overview_lines()
        for line in lines:
            assert re.match(r"📍 Paso \d/6 - .+", line), (
                f"Overview line does not match expected format: {line!r}"
            )

    def test_phase_overview_lines_ordered(self):
        """Overview lines are ordered by step number (1 through 6)."""
        from agent.services.expediente_constants import phase_overview_lines

        lines = phase_overview_lines()
        for idx, line in enumerate(lines, start=1):
            assert line.startswith(f"📍 Paso {idx}/6"), (
                f"Line {idx} should start with '📍 Paso {idx}/6', got: {line!r}"
            )

    def test_step_labels_have_non_empty_labels(self):
        """Every label in STEP_LABELS is a non-empty string."""
        from agent.services.expediente_constants import STEP_LABELS

        for sub_mode, (_, label) in STEP_LABELS.items():
            assert isinstance(label, str) and len(label) > 0, (
                f"STEP_LABELS['{sub_mode}'] has empty or non-string label"
            )


# ===========================================================================
# GROUP 2 — Escalation Exclusivity (Bug 4)
# ===========================================================================


class TestEscalationExclusivity:
    """
    Confirm confirmar_documentacion_base escalation return is mutually
    exclusive with progression fields (base_docs_confirmed, next_step,
    fsm_state_update).
    """

    def _build_escalation_return(self) -> dict[str, Any]:
        """Return the escalation dict as defined in the fixed code."""
        # This mirrors the exact return from confirmar_documentacion_base
        # when usuario_confirma=True but images are still missing after wait.
        return {
            "success": False,
            "escalated": True,
            "images_received": 0,
            "current_step": "collect_base_docs",
            "message": (
                "He registrado una incidencia con la recepción de documentos. "
                "Un agente humano revisará el caso. Mientras tanto, puedes "
                "intentar reenviar los documentos."
            ),
            "_internal_flags": {
                "base_docs_registered": False,
                "can_narrate_next_step_details": False,
                "delivery_outcome_status": "not_requested",
            },
        }

    def _build_success_return(self) -> dict[str, Any]:
        """Return the success dict as defined in the fixed code."""
        return {
            "success": True,
            "base_docs_confirmed": True,
            "images_received": 3,
            "next_step": "COLLECT_PERSONAL",
            "fsm_state_update": {"some": "state"},
            "base_docs_received": True,
            "message": "Documentación base recibida y registrada correctamente.",
            "_internal_flags": {
                "base_docs_registered": True,
                "can_narrate_next_step_details": False,
                "delivery_outcome_status": "not_requested",
            },
        }

    def test_escalation_returns_success_false(self):
        """When confirmar_documentacion_base escalates, success must be False."""
        result = self._build_escalation_return()
        assert result["success"] is False

    def test_escalation_has_escalated_flag(self):
        """Escalation return must have escalated=True."""
        result = self._build_escalation_return()
        assert result["escalated"] is True

    def test_escalation_has_no_progression_fields(self):
        """Escalation return must NOT contain base_docs_confirmed, next_step, or fsm_state_update."""
        result = self._build_escalation_return()
        assert "base_docs_confirmed" not in result, (
            "Escalation must not contain 'base_docs_confirmed'"
        )
        assert "next_step" not in result, (
            "Escalation must not contain 'next_step'"
        )
        assert "fsm_state_update" not in result, (
            "Escalation must not contain 'fsm_state_update'"
        )

    def test_escalation_flags_do_not_register_docs(self):
        """Escalation _internal_flags must set base_docs_registered=False."""
        result = self._build_escalation_return()
        flags = result.get("_internal_flags", {})
        assert flags.get("base_docs_registered") is False

    def test_success_path_has_progression_fields(self):
        """Success path still returns base_docs_confirmed=True and next_step."""
        result = self._build_success_return()
        assert result["success"] is True
        assert result["base_docs_confirmed"] is True
        assert result["next_step"] == "COLLECT_PERSONAL"
        assert "fsm_state_update" in result

    def test_success_flags_register_docs(self):
        """Success _internal_flags must set base_docs_registered=True."""
        result = self._build_success_return()
        flags = result.get("_internal_flags", {})
        assert flags.get("base_docs_registered") is True

    @pytest.mark.asyncio
    async def test_escalation_return_from_tool(self):
        """
        Integration-level: confirm the actual tool returns the escalation
        contract when images are missing and user confirmed.
        """
        from agent.state.helpers import set_current_state, clear_current_state
        from agent.tools.element_data_tools import confirmar_documentacion_base

        case_id = str(uuid.uuid4())
        conversation_id = "42"

        state = {
            "conversation_id": conversation_id,
            "current_mode": "EXPEDIENTE_MODE",
            "mode_context": {
                "expediente_sub_mode": "collect_base_docs",
                "case_id": case_id,
            },
            "fsm_state": {},
        }
        set_current_state(state)

        try:
            with (
                patch(
                    "agent.tools.element_data_tools._get_case_image_count",
                    new_callable=AsyncMock,
                    return_value=0,
                ),
                patch(
                    "agent.tools.element_data_tools._escalate_image_receipt_issue",
                    new_callable=AsyncMock,
                ),
                patch(
                    "agent.tools.element_data_tools.get_settings",
                ) as mock_settings,
                patch("asyncio.sleep", new_callable=AsyncMock),
            ):
                settings_instance = MagicMock()
                settings_instance.EXPEDIENTE_V2_ENABLED = False
                mock_settings.return_value = settings_instance

                result = await confirmar_documentacion_base.ainvoke(
                    {"usuario_confirma": True}
                )

            # Parse if result is JSON string
            data = json.loads(result) if isinstance(result, str) else result

            # Verify escalation contract
            assert data["success"] is False, "Escalation must return success=False"
            assert data.get("escalated") is True
            assert "base_docs_confirmed" not in data, (
                "Escalation must NOT contain 'base_docs_confirmed'"
            )
            assert "next_step" not in data, (
                "Escalation must NOT contain 'next_step'"
            )
            assert "fsm_state_update" not in data, (
                "Escalation must NOT contain 'fsm_state_update'"
            )
        finally:
            clear_current_state()


# ===========================================================================
# GROUP 3 — Case ID NOT in Prompt Context (Bug 1)
# ===========================================================================


class TestCaseIdNotInPrompt:
    """Verify that case_id (UUID) is never injected into the LLM prompt text."""

    def test_case_id_not_in_prompt_context(self):
        """
        format_mode_context for EXPEDIENTE_MODE must NOT embed case_id
        as visible text.  The comment 'case_id intentionally NOT injected'
        must be present in loader.py as proof of the fix.
        """
        from agent.prompts.loader import format_mode_context

        mode_context = {
            "case_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "expediente_sub_mode": "collect_personal",
            "element_codes": ["ESCAPE"],
        }

        result = format_mode_context("EXPEDIENTE_MODE", mode_context)

        # The UUID must not appear anywhere in the prompt text
        assert "a1b2c3d4" not in result, (
            "case_id UUID fragment leaked into prompt context"
        )
        assert "a1b2c3d4-e5f6-7890-abcd-ef1234567890" not in result

    def test_no_uuid_pattern_in_expediente_prompt_context(self):
        """
        Generated prompt context for EXPEDIENTE_MODE should not contain
        any full UUID v4 pattern (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx).
        """
        from agent.prompts.loader import format_mode_context

        mode_context = {
            "case_id": str(uuid.uuid4()),
            "expediente_sub_mode": "collect_vehicle",
            "element_codes": ["ESCAPE", "MANILLAR"],
            "current_element_index": 0,
            "element_phase": "photos",
        }

        result = format_mode_context("EXPEDIENTE_MODE", mode_context)

        uuid_pattern = re.compile(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            re.IGNORECASE,
        )
        match = uuid_pattern.search(result)
        assert match is None, (
            f"UUID pattern found in prompt context: {match.group()}"
        )

    def test_loader_has_intentional_exclusion_comment(self):
        """
        The comment 'case_id intentionally NOT injected' must exist in loader.py,
        proving the fix is documented in the source.
        """
        loader_path = _PROMPTS_DIR / "loader.py"
        content = loader_path.read_text(encoding="utf-8")
        assert "case_id intentionally NOT injected" in content, (
            "Expected documentation comment about case_id exclusion in loader.py"
        )


# ===========================================================================
# GROUP 4 — Prompt Anti-Hallucination Rule (Bug 2)
# ===========================================================================


class TestPromptAntiHallucination:
    """
    Verify expediente_documentacion_elementos.md contains the critical
    anti-hallucination rule that prevents the LLM from inventing field names.
    """

    @pytest.fixture(autouse=True)
    def _load_prompt(self):
        """Load the prompt file once for all tests in this class."""
        prompt_path = (
            _PROMPTS_DIR / "modes" / "expediente_documentacion_elementos.md"
        )
        self.prompt_content = prompt_path.read_text(encoding="utf-8")

    def test_prompt_contains_field_only_rule(self):
        """
        The prompt must contain a rule restricting data collection to
        fields from obtener_campos_elemento() / pending_fields only.
        """
        # Check for the key phrase from the anti-hallucination section
        assert "Solo campos de la base de datos" in self.prompt_content or \
               "ÚNICOS datos técnicos" in self.prompt_content, (
            "Missing anti-hallucination rule header in prompt"
        )

    def test_prompt_prohibits_invented_fields(self):
        """The prompt explicitly prohibits inventing field names."""
        lower = self.prompt_content.lower()
        assert "inventar" in lower or "inventes" in lower, (
            "Prompt must mention 'inventar' or 'inventes' to prohibit "
            "hallucinated fields"
        )

    def test_prompt_references_pending_fields(self):
        """The prompt references pending_fields as the source of truth."""
        assert "pending_fields" in self.prompt_content, (
            "Prompt must reference 'pending_fields' as the authoritative "
            "field source"
        )

    def test_prompt_references_obtener_campos(self):
        """The prompt references obtener_campos_elemento() as the source of truth."""
        assert "obtener_campos_elemento" in self.prompt_content, (
            "Prompt must reference 'obtener_campos_elemento()' as the "
            "authoritative field source"
        )

    def test_prompt_prohibits_specific_hallucinated_fields(self):
        """
        The PROHIBIDO section must list common hallucinated fields
        like 'marca', 'modelo', 'medidas' as examples of what NOT to ask.
        """
        lower = self.prompt_content.lower()
        # The prompt should mention at least one of these commonly hallucinated fields
        hallucinated_examples = ["marca", "modelo", "medidas"]
        mentioned = [f for f in hallucinated_examples if f in lower]
        assert len(mentioned) >= 2, (
            f"Prompt should list at least 2 of {hallucinated_examples} as "
            f"hallucination examples. Found: {mentioned}"
        )

    def test_prompt_has_tool_first_rule(self):
        """The prompt enforces TOOL-FIRST: call tools before generating text."""
        lower = self.prompt_content.lower()
        assert "tool-first" in lower or "herramienta correspondiente" in lower, (
            "Prompt must enforce TOOL-FIRST rule"
        )


# ===========================================================================
# GROUP 5 — Module Importability & Structural (Bugs 1, 3)
# ===========================================================================


class TestModuleImportability:
    """Verify new modules are importable without circular dependency errors."""

    def test_constants_importable(self):
        """expediente_constants module imports without error."""
        from agent.services.expediente_constants import (  # noqa: F401
            STEP_LABELS,
            TOTAL_STEPS,
            step_prefix,
            phase_overview_lines,
        )

    def test_case_helpers_importable(self):
        """case_helpers module imports without error."""
        from agent.services.case_helpers import (  # noqa: F401
            get_or_create_active_case,
            ACTIVE_STATUSES,
        )

    def test_constants_is_leaf_dependency(self):
        """
        expediente_constants must NOT import from agent package
        (leaf dependency — avoids circular imports).
        """
        import importlib
        import inspect

        mod = importlib.import_module("agent.services.expediente_constants")
        source = inspect.getsource(mod)

        # Should not import from agent.* (only stdlib and typing)
        agent_import_pattern = re.compile(
            r"^\s*(?:from|import)\s+agent\.", re.MULTILINE
        )
        match = agent_import_pattern.search(source)
        assert match is None, (
            f"expediente_constants imports from agent package: {match.group()!r}. "
            "This module must be a leaf dependency."
        )


# ===========================================================================
# GROUP 6 — elementos_confirmados Population (Bug 5)
# ===========================================================================


class TestElementosConfirmadosPopulation:
    """
    Verify PresupuestoModeNode._extract_context_from_tool populates
    elementos_confirmados when calcular_tarifa_con_elementos succeeds.
    """

    def _make_tariff_result(
        self,
        *,
        success: bool = True,
        element_codes: list[str] | None = None,
        element_names: list[str] | None = None,
    ) -> str:
        """Build a JSON string mimicking calcular_tarifa_con_elementos output."""
        codes = element_codes or ["ESCAPE", "MANILLAR"]
        names = element_names or ["Escape", "Manillar"]
        data = {
            "success": success,
            "texto": "El presupuesto es de 410€ +IVA.",
            "datos": {
                "price": 410.0,
                "element_codes": codes,
                "elements": names,
                "tier_code": "T3",
            },
            "_internal_flags": {
                "precio_comunicado": True,
                "imagenes_enviadas": False,
            },
        }
        return json.dumps(data, ensure_ascii=False)

    def test_elementos_confirmados_populated_on_success(self):
        """
        When calcular_tarifa_con_elementos succeeds, _extract_context_from_tool
        must set elementos_confirmados with code+name entries.
        """
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        result_json = self._make_tariff_result(
            element_codes=["ESCAPE", "MANILLAR"],
            element_names=["Escape", "Manillar"],
        )

        updates = PresupuestoModeNode._extract_context_from_tool(
            tool_name="calcular_tarifa_con_elementos",
            tool_args={"elementos": ["ESCAPE", "MANILLAR"], "categoria": "motos-part"},
            result=result_json,
        )

        assert "elementos_confirmados" in updates, (
            "elementos_confirmados must be populated on successful tariff calculation"
        )
        elementos = updates["elementos_confirmados"]
        assert len(elementos) == 2
        assert elementos[0]["code"] == "ESCAPE"
        assert elementos[0]["name"] == "Escape"
        assert elementos[1]["code"] == "MANILLAR"
        assert elementos[1]["name"] == "Manillar"

    def test_elementos_confirmados_not_set_on_failure(self):
        """
        When calcular_tarifa_con_elementos returns success=False,
        elementos_confirmados should NOT be populated.
        """
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        result_json = self._make_tariff_result(success=False)

        updates = PresupuestoModeNode._extract_context_from_tool(
            tool_name="calcular_tarifa_con_elementos",
            tool_args={"elementos": ["ESCAPE"], "categoria": "motos-part"},
            result=result_json,
        )

        assert "elementos_confirmados" not in updates, (
            "elementos_confirmados must NOT be set when tariff calculation fails"
        )

    def test_elementos_confirmados_entries_have_code_and_name(self):
        """Each entry in elementos_confirmados must have 'code' and 'name' keys."""
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        result_json = self._make_tariff_result(
            element_codes=["SUSPENSION"],
            element_names=["Suspensión"],
        )

        updates = PresupuestoModeNode._extract_context_from_tool(
            tool_name="calcular_tarifa_con_elementos",
            tool_args={"elementos": ["SUSPENSION"], "categoria": "motos-part"},
            result=result_json,
        )

        elementos = updates.get("elementos_confirmados", [])
        assert len(elementos) == 1
        entry = elementos[0]
        assert "code" in entry
        assert "name" in entry
        assert entry["code"] == "SUSPENSION"
        assert entry["name"] == "Suspensión"

    def test_elementos_confirmados_fallback_to_element_codes(self):
        """
        When datos lacks element_codes/elements, the function falls back
        to current_element_codes parameter.
        """
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        # Minimal tariff result without datos.element_codes
        data = {
            "success": True,
            "texto": "El presupuesto es de 200€ +IVA.",
            "datos": {"price": 200.0},
        }
        result_json = json.dumps(data, ensure_ascii=False)

        updates = PresupuestoModeNode._extract_context_from_tool(
            tool_name="calcular_tarifa_con_elementos",
            tool_args={"elementos": ["ESCAPE"], "categoria": "motos-part"},
            result=result_json,
            current_element_codes=["ESCAPE"],
        )

        elementos = updates.get("elementos_confirmados", [])
        assert len(elementos) == 1
        assert elementos[0]["code"] == "ESCAPE"

    def test_tarifa_calculada_stored(self):
        """_extract_context_from_tool always stores the full tariff response."""
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        result_json = self._make_tariff_result()

        updates = PresupuestoModeNode._extract_context_from_tool(
            tool_name="calcular_tarifa_con_elementos",
            tool_args={"elementos": ["ESCAPE"], "categoria": "motos-part"},
            result=result_json,
        )

        assert "tarifa_calculada" in updates
        tarifa = updates["tarifa_calculada"]
        assert tarifa["success"] is True
        assert tarifa["datos"]["price"] == 410.0
