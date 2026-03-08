"""
Unit tests for expediente-flow-redesign-followup R2: Rich Field Metadata.

Tests cover:
- _extract_field_keys_from_tool_result enriched with instruction/example/options (TASK-4.3)

These are pure unit tests (no DB, no Redis, no LLM).
"""

import pytest


# =============================================================================
# TASK-4.3: Tests for rich field metadata in _extract_field_keys_from_tool_result
# =============================================================================


class TestExtractFieldKeysIncludesMetadata:
    """
    Tests for agent.modes.expediente_mode._extract_field_keys_from_tool_result
    verifying R2 rich-metadata behaviour.
    """

    def test_extract_field_keys_includes_metadata_from_fields_list(self):
        """
        Given a tool result with instruction/example/options in the 'fields' list,
        the extracted dict MUST include all three.
        """
        from agent.modes.expediente_mode import _extract_field_keys_from_tool_result

        tool_result = {
            "success": True,
            "fields": [
                {
                    "field_key": "descripcion_modificacion",
                    "field_label": "Descripción de la modificación",
                    "field_type": "text",
                    "is_required": True,
                    "instruction": "Explica en qué consiste la modificación realizada",
                    "example": "Acortado 50mm respecto a estándar",
                    "options": None,
                }
            ],
        }

        result = _extract_field_keys_from_tool_result(tool_result)

        assert result is not None
        assert len(result) == 1
        fk = result[0]
        assert fk["field_key"] == "descripcion_modificacion"
        assert fk["instruction"] == "Explica en qué consiste la modificación realizada"
        assert fk["example"] == "Acortado 50mm respecto a estándar"
        assert fk["options"] is None

    def test_extract_field_keys_includes_options_when_present(self):
        """
        A field with non-empty 'options' list must be preserved in the output.
        """
        from agent.modes.expediente_mode import _extract_field_keys_from_tool_result

        tool_result = {
            "success": True,
            "fields": [
                {
                    "field_key": "tipo_escape",
                    "field_label": "Tipo de escape",
                    "field_type": "select",
                    "is_required": True,
                    "instruction": "Selecciona el tipo de sistema de escape",
                    "example": "full_system",
                    "options": ["full_system", "slip_on", "link_pipe"],
                }
            ],
        }

        result = _extract_field_keys_from_tool_result(tool_result)

        assert result is not None
        fk = result[0]
        assert fk["options"] == ["full_system", "slip_on", "link_pipe"]

    def test_extract_field_keys_missing_metadata_defaults_to_none(self):
        """
        Given a tool result with only field_key/field_label (no instruction/example/options),
        the extracted dict MUST NOT crash and must default all three to None.
        """
        from agent.modes.expediente_mode import _extract_field_keys_from_tool_result

        tool_result = {
            "success": True,
            "fields": [
                {
                    "field_key": "nueva_longitud_total",
                    "field_label": "Nueva longitud total (mm)",
                    # No instruction, example, or options
                }
            ],
        }

        result = _extract_field_keys_from_tool_result(tool_result)

        assert result is not None
        fk = result[0]
        assert fk["field_key"] == "nueva_longitud_total"
        assert fk["instruction"] is None
        assert fk["example"] is None
        assert fk["options"] is None

    def test_extract_field_keys_from_current_field_includes_metadata(self):
        """
        The 'current_field' path (sequential mode) also supports rich metadata.
        """
        from agent.modes.expediente_mode import _extract_field_keys_from_tool_result

        tool_result = {
            "success": True,
            "current_field": {
                "field_key": "placa_potencia_w",
                "field_label": "Potencia de la placa solar (W)",
                "field_type": "number",
                "instruction": "Indica la potencia en vatios de la placa instalada",
                "example": "200",
                "options": None,
            },
        }

        result = _extract_field_keys_from_tool_result(tool_result)

        assert result is not None
        fk = result[0]
        assert fk["field_key"] == "placa_potencia_w"
        assert fk["instruction"] == "Indica la potencia en vatios de la placa instalada"
        assert fk["example"] == "200"

    def test_extract_field_keys_returns_none_when_no_field_data(self):
        """
        If neither 'fields' nor 'current_field' is present, returns None.
        """
        from agent.modes.expediente_mode import _extract_field_keys_from_tool_result

        tool_result = {
            "success": True,
            "element_code": "ESCAPE",
            # No fields or current_field
        }

        result = _extract_field_keys_from_tool_result(tool_result)

        assert result is None

    def test_extract_deduplicates_keys_across_sources(self):
        """
        When 'fields' list and 'current_field' share the same field_key,
        the key must only appear once in the output.
        """
        from agent.modes.expediente_mode import _extract_field_keys_from_tool_result

        tool_result = {
            "success": True,
            "fields": [
                {
                    "field_key": "descripcion_modificacion",
                    "field_label": "Descripción",
                    "instruction": "First source instruction",
                    "example": None,
                    "options": None,
                }
            ],
            "current_field": {
                # Same key — should be deduplicated
                "field_key": "descripcion_modificacion",
                "field_label": "Descripción (current)",
                "instruction": "Second source instruction",
                "example": "Example from current",
                "options": None,
            },
        }

        result = _extract_field_keys_from_tool_result(tool_result)

        assert result is not None
        # fields list comes first, current_field is deduped away
        assert len(result) == 1
        assert result[0]["field_key"] == "descripcion_modificacion"


# =============================================================================
# TASK-4.3 (extra): Verify format_mode_context renders instruction+example inline
# =============================================================================


class TestFormatModeContextFieldRendering:
    """
    Verify that format_mode_context (loader.py) renders instruction/example/options
    inline in the FIELD_KEYS block when they are present in the field dict.
    """

    def test_format_field_with_instruction_and_example(self):
        """
        Given a mode_context with element in 'data' phase and field_keys containing
        instruction and example, the assembled context string must include both.
        """
        from agent.prompts.loader import format_mode_context

        mode = "EXPEDIENTE_MODE"
        context = {
            "element_codes": ["PLACA_SOLAR"],
            "current_element_index": 0,
            "element_phase": "data",
            "element_display_names": {"PLACA_SOLAR": "Placa solar"},
            "current_element_field_keys": [
                {
                    "field_key": "placa_potencia_w",
                    "field_label": "Potencia de la placa solar (W)",
                    "instruction": "Indica la potencia en vatios",
                    "example": "200",
                    "options": None,
                }
            ],
        }

        rendered = format_mode_context(mode, context)

        # Instruction must appear in rendered output
        assert "Indica la potencia en vatios" in rendered, (
            f"Expected instruction in rendered context. Got:\n{rendered}"
        )
        # Example must appear
        assert "ej: 200" in rendered, (
            f"Expected example '200' in rendered context. Got:\n{rendered}"
        )
        # Field key must appear
        assert "placa_potencia_w" in rendered, (
            f"Expected field_key in rendered context. Got:\n{rendered}"
        )

    def test_format_field_with_options_renders_option_list(self):
        """
        Given a field with a non-empty 'options' list, the rendered context
        must include the options.
        """
        from agent.prompts.loader import format_mode_context

        mode = "EXPEDIENTE_MODE"
        context = {
            "element_codes": ["ESCAPE"],
            "current_element_index": 0,
            "element_phase": "data",
            "current_element_field_keys": [
                {
                    "field_key": "tipo_escape",
                    "field_label": "Tipo de escape",
                    "instruction": None,
                    "example": None,
                    "options": ["full_system", "slip_on"],
                }
            ],
        }

        rendered = format_mode_context(mode, context)

        assert "full_system" in rendered
        assert "slip_on" in rendered

    def test_format_field_without_metadata_renders_basic_line(self):
        """
        Even without instruction/example/options, the field_key line must be rendered.
        """
        from agent.prompts.loader import format_mode_context

        mode = "EXPEDIENTE_MODE"
        context = {
            "element_codes": ["SUBCHASIS"],
            "current_element_index": 0,
            "element_phase": "data",
            "current_element_field_keys": [
                {
                    "field_key": "longitud_mm",
                    "field_label": "Longitud total (mm)",
                    "instruction": None,
                    "example": None,
                    "options": None,
                }
            ],
        }

        rendered = format_mode_context(mode, context)

        assert "longitud_mm" in rendered
        assert "Longitud total" in rendered
