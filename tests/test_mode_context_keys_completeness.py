"""
Tests for mode_context_keys completeness.

Validates that all keys written by tools and modes are present in the
canonical whitelist, and that anti-hallucination messaging is correct
in element_data_tools.confirmar_fotos_elemento responses.
"""

import pytest

from agent.state.mode_context_keys import (
    CANONICAL_MODE_CONTEXT_KEYS,
    _TOOL_FLAG_KEYS,
    _CASE_COLLECTION_COMPAT_KEYS,
    _MODE_RUNTIME_KEYS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1: Canonical key set completeness
# ─────────────────────────────────────────────────────────────────────────────


class TestCanonicalModeContextKeysCompleteness:
    """Verify that all 13 newly added keys are in the canonical set."""

    # -- Tool flag keys (10 new) --

    @pytest.mark.parametrize(
        "key",
        [
            "datos_updated",
            "confirmed_fields",
            "can_narrate_completion",
            "taller_updated",
            "case_finalized",
            "expediente_edited",
            "edit_target_sub_mode",
            "elemento_completed",
            "base_docs_registered",
            "can_narrate_next_step_details",
        ],
    )
    def test_tool_flag_key_in_canonical_set(self, key: str) -> None:
        """Each tool flag key must be present in CANONICAL_MODE_CONTEXT_KEYS."""
        assert key in CANONICAL_MODE_CONTEXT_KEYS, (
            f"Key '{key}' is missing from CANONICAL_MODE_CONTEXT_KEYS"
        )

    # -- Mode runtime key (1 new) --

    def test_element_display_names_in_canonical_set(self) -> None:
        """element_display_names must be in canonical set."""
        assert "element_display_names" in CANONICAL_MODE_CONTEXT_KEYS

    # -- FSM compat keys (2 new) --

    @pytest.mark.parametrize("key", ["step", "retry_count"])
    def test_fsm_compat_key_in_canonical_set(self, key: str) -> None:
        """FSM compat keys must be in CANONICAL_MODE_CONTEXT_KEYS."""
        assert key in CANONICAL_MODE_CONTEXT_KEYS, (
            f"Key '{key}' is missing from CANONICAL_MODE_CONTEXT_KEYS"
        )


class TestUnknownKeysRejected:
    """Verify that truly unknown keys are NOT in the whitelist."""

    @pytest.mark.parametrize(
        "key",
        [
            "totally_bogus_key",
            "hallucinated_field_name",
            "nonexistent_tool_flag",
            "__internal_secret__",
        ],
    )
    def test_unknown_key_not_in_canonical_set(self, key: str) -> None:
        """Random / bogus keys must NOT appear in the canonical set."""
        assert key not in CANONICAL_MODE_CONTEXT_KEYS, (
            f"Key '{key}' should NOT be in CANONICAL_MODE_CONTEXT_KEYS"
        )


class TestToolFlagKeysSubset:
    """Verify _TOOL_FLAG_KEYS contains all expected tool flag keys."""

    EXPECTED_TOOL_FLAG_KEYS = [
        # Pre-existing keys
        "precio_comunicado",
        "imagenes_enviadas",
        "all_elements_complete",
        "can_narrate_next_element",
        "fotos_elemento_registered",
        # Newly added keys
        "datos_updated",
        "confirmed_fields",
        "can_narrate_completion",
        "taller_updated",
        "case_finalized",
        "expediente_edited",
        "edit_target_sub_mode",
        "elemento_completed",
        "base_docs_registered",
        "can_narrate_next_step_details",
    ]

    @pytest.mark.parametrize("key", EXPECTED_TOOL_FLAG_KEYS)
    def test_key_in_tool_flag_keys(self, key: str) -> None:
        """Each expected tool flag key must be in _TOOL_FLAG_KEYS."""
        assert key in _TOOL_FLAG_KEYS, f"Key '{key}' is missing from _TOOL_FLAG_KEYS"


class TestCaseCollectionCompatKeysSubset:
    """Verify _CASE_COLLECTION_COMPAT_KEYS contains step and retry_count."""

    @pytest.mark.parametrize("key", ["step", "retry_count"])
    def test_key_in_case_collection_compat_keys(self, key: str) -> None:
        """step and retry_count must be in _CASE_COLLECTION_COMPAT_KEYS."""
        assert key in _CASE_COLLECTION_COMPAT_KEYS, (
            f"Key '{key}' is missing from _CASE_COLLECTION_COMPAT_KEYS"
        )

    def _build_next_element_message(self, element_name: str = "ESCAPE") -> str:
        """Build the message from the more-elements-to-process path."""
        return (
            f"Fotos de {element_name} recibidas ✅\n\n"
            "Este elemento NO tiene datos técnicos adicionales que recoger. "
            "NO pidas marca, modelo, medidas ni ningún otro dato técnico al usuario.\n\n"
            "Pasamos al siguiente elemento."
        )

    def test_all_complete_path_contains_anti_hallucination(self) -> None:
        """All-elements-complete path message must contain anti-hallucination text."""
        message = self._build_all_complete_message()
        for phrase in self.ANTI_HALLUCINATION_PHRASES:
            assert phrase in message, f"Anti-hallucination phrase missing: '{phrase}'"

    def test_next_element_path_contains_anti_hallucination(self) -> None:
        """More-elements-to-process path message must contain anti-hallucination text."""
        message = self._build_next_element_message()
        for phrase in self.ANTI_HALLUCINATION_PHRASES:
            assert phrase in message, f"Anti-hallucination phrase missing: '{phrase}'"

    def test_all_complete_path_confirms_photos(self) -> None:
        """All-elements-complete path should confirm photo receipt."""
        message = self._build_all_complete_message("MANILLAR")
        assert "Fotos de MANILLAR recibidas ✅" in message

    def test_next_element_path_confirms_photos(self) -> None:
        """More-elements path should confirm photo receipt."""
        message = self._build_next_element_message("SUSPENSION")
        assert "Fotos de SUSPENSION recibidas ✅" in message

    def test_all_complete_path_mentions_completion(self) -> None:
        """All-elements-complete path should mention all elements complete."""
        message = self._build_all_complete_message()
        assert "Todos los elementos están completos" in message

    def test_next_element_path_mentions_next(self) -> None:
        """More-elements path should mention moving to next element."""
        message = self._build_next_element_message()
        assert "Pasamos al siguiente elemento" in message

    def test_source_code_has_anti_hallucination_text(self) -> None:
        """
        Verify the actual source code of element_data_tools contains the
        anti-hallucination phrases in the confirmar_fotos_elemento function.

        This is a stronger test than just reconstructing the message — it
        reads the actual source to make sure the phrases were not removed.
        """
        import inspect
        from agent.tools import element_data_tools

        source = inspect.getsource(element_data_tools)

        for phrase in self.ANTI_HALLUCINATION_PHRASES:
            assert phrase in source, (
                f"Anti-hallucination phrase not found in element_data_tools source: '{phrase}'"
            )
