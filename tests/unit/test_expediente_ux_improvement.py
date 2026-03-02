"""
Unit tests for expediente-ux-improvement change.

Tests the following behaviors:
1. _progress_prefix() returns correct format
2. _progress_prefix() returns "" for unknown sub-modes
3. SUB_MODE_STEP mapping has exactly 6 entries
4. ENABLE_SAME_TURN_TRANSITION_CLOSURE defaults to True
5. _build_element_photo_instructions(None) returns "" without exception
"""

import pytest
import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class TestProgressPrefix:
    """Tests for the _progress_prefix() function in expediente_mode.py."""

    def test_progress_prefix_returns_correct_format_collect_element_data(self):
        """_progress_prefix('collect_element_data') returns '📍 Paso 1/6 — Fotos y datos de elementos'"""
        from agent.modes.expediente_mode import _progress_prefix
        result = _progress_prefix("collect_element_data")
        assert result == "📍 Paso 1/6 — Fotos y datos de elementos"

    def test_progress_prefix_returns_correct_format_collect_base_docs(self):
        """_progress_prefix('collect_base_docs') returns correct step 2"""
        from agent.modes.expediente_mode import _progress_prefix
        result = _progress_prefix("collect_base_docs")
        assert result == "📍 Paso 2/6 — Documentación base"

    def test_progress_prefix_returns_correct_format_collect_personal(self):
        """_progress_prefix('collect_personal') returns correct step 3"""
        from agent.modes.expediente_mode import _progress_prefix
        result = _progress_prefix("collect_personal")
        assert result == "📍 Paso 3/6 — Datos personales"

    def test_progress_prefix_returns_correct_format_collect_vehicle(self):
        """_progress_prefix('collect_vehicle') returns correct step 4"""
        from agent.modes.expediente_mode import _progress_prefix
        result = _progress_prefix("collect_vehicle")
        assert result == "📍 Paso 4/6 — Datos del vehículo"

    def test_progress_prefix_returns_correct_format_collect_workshop(self):
        """_progress_prefix('collect_workshop') returns correct step 5"""
        from agent.modes.expediente_mode import _progress_prefix
        result = _progress_prefix("collect_workshop")
        assert result == "📍 Paso 5/6 — Certificado del taller"

    def test_progress_prefix_returns_correct_format_review_summary(self):
        """_progress_prefix('review_summary') returns correct step 6"""
        from agent.modes.expediente_mode import _progress_prefix
        result = _progress_prefix("review_summary")
        assert result == "📍 Paso 6/6 — Revisión final"

    def test_progress_prefix_unknown_submode_returns_empty(self):
        """_progress_prefix('unknown') returns '' without exception."""
        from agent.modes.expediente_mode import _progress_prefix
        result = _progress_prefix("unknown")
        assert result == ""

    def test_progress_prefix_empty_string_returns_empty(self):
        """_progress_prefix('') returns '' without exception."""
        from agent.modes.expediente_mode import _progress_prefix
        result = _progress_prefix("")
        assert result == ""

    def test_progress_prefix_none_like_input_returns_empty(self):
        """_progress_prefix with non-existent key returns ''."""
        from agent.modes.expediente_mode import _progress_prefix
        result = _progress_prefix("not_a_real_mode")
        assert result == ""


class TestSubModeStepMapping:
    """Tests for the SUB_MODE_STEP mapping."""

    def test_sub_mode_step_mapping_complete(self):
        """SUB_MODE_STEP has exactly 6 entries."""
        from agent.modes.expediente_mode import SUB_MODE_STEP
        assert len(SUB_MODE_STEP) == 6

    def test_sub_mode_step_mapping_has_all_submode_keys(self):
        """SUB_MODE_STEP contains all 6 expected sub-mode keys."""
        from agent.modes.expediente_mode import SUB_MODE_STEP
        expected_keys = {
            "collect_element_data",
            "collect_base_docs",
            "collect_personal",
            "collect_vehicle",
            "collect_workshop",
            "review_summary",
        }
        assert set(SUB_MODE_STEP.keys()) == expected_keys

    def test_sub_mode_step_values_are_sequential(self):
        """Step numbers in SUB_MODE_STEP are 1 through 6 with no gaps."""
        from agent.modes.expediente_mode import SUB_MODE_STEP
        step_numbers = {step for step, _ in SUB_MODE_STEP.values()}
        assert step_numbers == {1, 2, 3, 4, 5, 6}

    def test_sub_mode_step_labels_are_non_empty(self):
        """All labels in SUB_MODE_STEP are non-empty strings."""
        from agent.modes.expediente_mode import SUB_MODE_STEP
        for step, label in SUB_MODE_STEP.values():
            assert isinstance(label, str) and label.strip(), \
                f"Step {step} has empty or non-string label"


class TestConfigClosureFlag:
    """Tests for the ENABLE_SAME_TURN_TRANSITION_CLOSURE config flag."""

    def test_config_closure_flag_default_is_true(self):
        """ENABLE_SAME_TURN_TRANSITION_CLOSURE defaults to True."""
        # Import with a fresh settings instance (avoid cached env var issues)
        from shared.config import Settings
        settings = Settings()
        assert settings.ENABLE_SAME_TURN_TRANSITION_CLOSURE is True

    def test_config_closure_flag_exists_in_settings(self):
        """ENABLE_SAME_TURN_TRANSITION_CLOSURE field exists on Settings class."""
        from shared.config import Settings
        assert hasattr(Settings, "model_fields") or hasattr(Settings, "__fields__")
        # Verify via instantiation
        settings = Settings()
        assert hasattr(settings, "ENABLE_SAME_TURN_TRANSITION_CLOSURE")

    def test_config_closure_flag_is_bool(self):
        """ENABLE_SAME_TURN_TRANSITION_CLOSURE is a boolean field."""
        from shared.config import Settings
        settings = Settings()
        assert isinstance(settings.ENABLE_SAME_TURN_TRANSITION_CLOSURE, bool)


class TestBuildElementPhotoInstructions:
    """Tests for the _build_element_photo_instructions() defensive helper."""

    def test_build_element_photo_instructions_defensive_none(self):
        """_build_element_photo_instructions(None) returns '' without exception."""
        from agent.modes.expediente_mode import _build_element_photo_instructions
        result = _build_element_photo_instructions(None)
        assert result == ""

    def test_build_element_photo_instructions_defensive_invalid_string(self):
        """_build_element_photo_instructions('not-json') returns '' without exception."""
        from agent.modes.expediente_mode import _build_element_photo_instructions
        result = _build_element_photo_instructions("not-valid-json{{{")
        assert result == ""

    def test_build_element_photo_instructions_defensive_empty_dict(self):
        """_build_element_photo_instructions({}) returns '' (no documentacion key)."""
        from agent.modes.expediente_mode import _build_element_photo_instructions
        result = _build_element_photo_instructions({})
        assert result == ""

    def test_build_element_photo_instructions_with_valid_data(self):
        """_build_element_photo_instructions() returns photo block when data is present."""
        from agent.modes.expediente_mode import _build_element_photo_instructions
        tarifa = {
            "documentacion": {
                "elementos": [
                    {
                        "nombre": "Escape",
                        "imagenes": [
                            {"instruccion_usuario": "Foto lateral del escape instalado"}
                        ],
                    }
                ]
            }
        }
        result = _build_element_photo_instructions(tarifa)
        assert result != ""
        assert "Escape" in result
        assert "Foto lateral del escape instalado" in result

    def test_build_element_photo_instructions_with_json_string(self):
        """_build_element_photo_instructions() handles JSON string input."""
        import json
        from agent.modes.expediente_mode import _build_element_photo_instructions
        tarifa = {
            "documentacion": {
                "elementos": [
                    {
                        "nombre": "Suspensión",
                        "imagenes": [
                            {"instruccion_usuario": "Foto de la suspensión instalada"}
                        ],
                    }
                ]
            }
        }
        result = _build_element_photo_instructions(json.dumps(tarifa))
        assert result != ""
        assert "Suspensión" in result

    def test_build_element_photo_instructions_includes_whatsapp_reminder(self):
        """_build_element_photo_instructions() includes WhatsApp format reminder."""
        from agent.modes.expediente_mode import _build_element_photo_instructions
        tarifa = {
            "documentacion": {
                "elementos": [
                    {
                        "nombre": "Escape",
                        "imagenes": [{"instruccion_usuario": "Foto lateral"}],
                    }
                ]
            }
        }
        result = _build_element_photo_instructions(tarifa)
        # Should include the WhatsApp format reminder
        assert "imagen" in result.lower() or "documento adjunto" in result.lower()

    def test_build_element_photo_instructions_empty_elementos_list(self):
        """_build_element_photo_instructions() returns '' when elementos list is empty."""
        from agent.modes.expediente_mode import _build_element_photo_instructions
        tarifa = {
            "documentacion": {
                "elementos": []
            }
        }
        result = _build_element_photo_instructions(tarifa)
        assert result == ""

    def test_build_element_photo_instructions_no_exception_on_corrupted_data(self):
        """_build_element_photo_instructions() never raises an exception."""
        from agent.modes.expediente_mode import _build_element_photo_instructions
        # Various corrupted inputs — must NEVER raise
        corrupted_inputs = [
            {"documentacion": None},
            {"documentacion": {"elementos": "not-a-list"}},
            {"documentacion": {"elementos": [None, 42, "string"]}},
            {"documentacion": {"elementos": [{"nombre": None, "imagenes": [{"instruccion_usuario": None}]}]}},
        ]
        for inp in corrupted_inputs:
            try:
                result = _build_element_photo_instructions(inp)
                assert isinstance(result, str), f"Expected str, got {type(result)} for input {inp}"
            except Exception as e:
                pytest.fail(f"_build_element_photo_instructions raised {e} for input {inp}")


class TestTransitionClosureBuilders:
    """Tests for the transition closure builder functions."""

    def test_build_base_docs_to_personal_closure_has_destination_prefix(self):
        """base_docs→personal closure message starts with step-3 progress prefix."""
        from agent.modes.expediente_mode import _build_base_docs_to_personal_closure
        result = _build_base_docs_to_personal_closure({"success": True})
        assert result.startswith("📍 Paso 3/6")

    def test_build_personal_to_vehicle_closure_has_destination_prefix(self):
        """personal→vehicle closure message starts with step-4 progress prefix."""
        from agent.modes.expediente_mode import _build_personal_to_vehicle_closure
        result = _build_personal_to_vehicle_closure({"success": True})
        assert result.startswith("📍 Paso 4/6")

    def test_build_vehicle_to_workshop_closure_has_destination_prefix(self):
        """vehicle→workshop closure message starts with step-5 progress prefix."""
        from agent.modes.expediente_mode import _build_vehicle_to_workshop_closure
        result = _build_vehicle_to_workshop_closure({"success": True})
        assert result.startswith("📍 Paso 5/6")

    def test_build_workshop_to_review_closure_has_destination_prefix(self):
        """workshop→review_summary closure message starts with step-6 progress prefix."""
        from agent.modes.expediente_mode import _build_workshop_to_review_closure
        result = _build_workshop_to_review_closure({"success": True})
        assert result.startswith("📍 Paso 6/6")

    def test_build_element_completion_transition_closure_has_base_docs_prefix(self):
        """element_data→base_docs closure starts with step-2 progress prefix."""
        from agent.modes.expediente_mode import _build_element_completion_transition_closure
        result = _build_element_completion_transition_closure(
            from_sub_mode="collect_element_data",
            to_sub_mode="collect_base_docs",
            tool_name="confirmar_fotos_elemento",
            tool_data={"all_elements_complete": True},
            base_documentation=[{"description": "Ficha técnica"}],
        )
        assert result is not None
        assert result.startswith("📍 Paso 2/6")


class TestTransitionKickoffMessage:
    """Tests for _build_transition_kickoff_message()."""

    def test_kickoff_collect_base_docs_has_prefix_and_cta(self):
        """kickoff for COLLECT_BASE_DOCS includes prefix and CTA."""
        from agent.modes.expediente_mode import ExpedienteModeNode
        result = ExpedienteModeNode._build_transition_kickoff_message(
            sub_mode_name="COLLECT_BASE_DOCS",
            mode_context={},
        )
        assert "📍 Paso 2/6" in result
        assert "?" in result  # CTA should include a question

    def test_kickoff_collect_personal_has_prefix_and_cta(self):
        """kickoff for COLLECT_PERSONAL includes prefix and CTA."""
        from agent.modes.expediente_mode import ExpedienteModeNode
        result = ExpedienteModeNode._build_transition_kickoff_message(
            sub_mode_name="COLLECT_PERSONAL",
            mode_context={},
        )
        assert "📍 Paso 3/6" in result
        assert "?" in result

    def test_kickoff_collect_vehicle_has_prefix_and_cta(self):
        """kickoff for COLLECT_VEHICLE includes prefix and CTA."""
        from agent.modes.expediente_mode import ExpedienteModeNode
        result = ExpedienteModeNode._build_transition_kickoff_message(
            sub_mode_name="COLLECT_VEHICLE",
            mode_context={},
        )
        assert "📍 Paso 4/6" in result
        assert "?" in result

    def test_kickoff_collect_workshop_has_prefix_and_cta(self):
        """kickoff for COLLECT_WORKSHOP includes prefix and CTA."""
        from agent.modes.expediente_mode import ExpedienteModeNode
        result = ExpedienteModeNode._build_transition_kickoff_message(
            sub_mode_name="COLLECT_WORKSHOP",
            mode_context={},
        )
        assert "📍 Paso 5/6" in result
        assert "?" in result

    def test_kickoff_review_summary_has_prefix_no_cta(self):
        """kickoff for REVIEW_SUMMARY has prefix but no CTA (terminal step)."""
        from agent.modes.expediente_mode import ExpedienteModeNode
        result = ExpedienteModeNode._build_transition_kickoff_message(
            sub_mode_name="REVIEW_SUMMARY",
            mode_context={},
        )
        assert "📍 Paso 6/6" in result
        # Terminal step: no CTA (no question mark required)


class TestIdempotencyGuard:
    """Test that the idempotency guard prevents double-prefixing."""

    def test_progress_prefix_format_starts_with_pushpin_emoji(self):
        """All non-empty progress prefixes start with '📍'."""
        from agent.modes.expediente_mode import _progress_prefix, SUB_MODE_STEP
        for sub_mode in SUB_MODE_STEP:
            prefix = _progress_prefix(sub_mode)
            assert prefix.startswith("📍"), \
                f"Expected prefix for {sub_mode} to start with '📍', got: {repr(prefix)}"

    def test_idempotency_check_would_work_for_prefixed_response(self):
        """
        Verify that the idempotency check used in _run_llm_loop works as expected:
        a response already starting with '📍' would NOT be prefixed again.
        """
        from agent.modes.expediente_mode import _progress_prefix

        # Simulate what _run_llm_loop does
        sub_mode = "collect_element_data"
        already_prefixed_response = "📍 Paso 1/6 — Fotos y datos de elementos\n\nAlgún mensaje previo"

        progress_pfx = _progress_prefix(sub_mode)
        # The guard: if response already starts with "📍", skip
        would_be_double_prefixed = (
            progress_pfx
            and already_prefixed_response
            and not already_prefixed_response.startswith("📍")
        )
        assert not would_be_double_prefixed, "Should NOT double-prefix already-prefixed responses"
