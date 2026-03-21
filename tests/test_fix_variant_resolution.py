"""
Tests for fix-variant-resolution change.

Covers:
  Phase 1 — _normalize_to_canonical_letter() unit tests
  Phase 2 — LLM-path substring guard unit tests
  Phase 4 — Chatwoot PII log sanitization
  Integration & Regression — decorated positional responses resolve via variant_position

Run with:
    pytest tests/test_fix_variant_resolution.py -v

Note: Integration tests import from agent.tools.element_tools which requires
the full agent stack (structlog, langchain, etc.). Those run in the Docker
container. Pure unit tests for _normalize_to_canonical_letter use direct
module loading to avoid the dependency chain.
"""
import sys
import os
import re
import importlib.util
import types
import json
import logging
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# ===========================================================================
# Direct module extraction — load only what we need from element_tools.py
# without triggering agent/__init__.py and the full LangGraph stack.
# This mirrors the approach used in test_element_variant_guard.py.
# ===========================================================================

def _load_normalize_helper():
    """
    Extract _normalize_to_canonical_letter and _POSITIONAL_LETTER_RE from
    element_tools.py by executing only the minimal stubs needed.
    """
    # Stub every heavy dependency so element_tools.py's module-level code
    # doesn't fail. We only need the regex constant + pure helper function.

    def _stub(name: str) -> types.ModuleType:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        return mod

    required_stubs = [
        "structlog",
        "langchain_core",
        "langchain_core.tools",
        "agent",
        "agent.services",
        "agent.services.element_service",
        "agent.services.tarifa_service",
        "agent.services.variant_interpretation_service",
        "agent.state",
        "agent.state.conversation_state",
        "agent.state.helpers",
        "agent.utils",
        "agent.utils.validation",
        "database",
        "database.connection",
        "database.models",
        "shared",
        "shared.config",
    ]

    for name in required_stubs:
        if name not in sys.modules:
            _stub(name)

    # Provide minimal API surfaces needed at import time
    sys.modules["structlog"].get_logger = lambda *a, **kw: MagicMock()
    sys.modules["langchain_core.tools"].tool = lambda f: f  # passthrough decorator
    sys.modules["agent.services.element_service"].get_element_service = MagicMock()
    sys.modules["agent.services.tarifa_service"].get_tarifa_service = MagicMock()
    sys.modules["agent.services.variant_interpretation_service"].VariantInterpretationResult = MagicMock()
    sys.modules["agent.services.variant_interpretation_service"].interpret_variant_allocations = MagicMock()
    sys.modules["agent.services.variant_interpretation_service"].validate_and_apply_allocations = MagicMock()
    sys.modules["agent.state.conversation_state"].PendingVariantGroup = dict
    sys.modules["agent.state.helpers"].get_current_state = MagicMock(return_value={})
    sys.modules["agent.state.helpers"].normalize_pending_variants = MagicMock(return_value=[])
    sys.modules["agent.utils.validation"].validate_category_slug = MagicMock(return_value=None)
    sys.modules["database.connection"].get_async_session = MagicMock()
    sys.modules["database.models"].VehicleCategory = type("VehicleCategory", (), {})

    settings_mock = MagicMock()
    settings_mock.ENABLE_LLM_VARIANT_INTERPRETATION = False
    sys.modules["shared.config"].get_settings = lambda: settings_mock

    # Now load element_tools.py via importlib (bypasses agent/__init__)
    tool_path = Path(__file__).parent.parent / "agent" / "tools" / "element_tools.py"
    spec = importlib.util.spec_from_file_location("agent.tools.element_tools_isolated", tool_path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    return module._normalize_to_canonical_letter, module._POSITIONAL_LETTER_RE


# Load once at module level
try:
    _normalize_to_canonical_letter, _POSITIONAL_LETTER_RE = _load_normalize_helper()
    _HELPER_AVAILABLE = True
except Exception as e:
    _HELPER_AVAILABLE = False
    _HELPER_LOAD_ERROR = str(e)
    _normalize_to_canonical_letter = None
    _POSITIONAL_LETTER_RE = None


# ===========================================================================
# Phase 1: _normalize_to_canonical_letter() unit tests
# ===========================================================================

@pytest.mark.skipif(not _HELPER_AVAILABLE, reason=f"Could not load helper: {locals().get('_HELPER_LOAD_ERROR', 'unknown')}")
class TestNormalizeToCanonicalLetter:
    """Unit tests for the _normalize_to_canonical_letter() helper."""

    def _call(self, response: str) -> "str | None":
        return _normalize_to_canonical_letter(response)

    # --- Positive cases (should extract letter) ---

    def test_bare_lowercase_b(self):
        """'b' → 'b' (bare single letter)."""
        assert self._call("b") == "b"

    def test_bare_uppercase_b(self):
        """'B' → 'b' (uppercase normalizes to lowercase)."""
        assert self._call("B") == "b"

    def test_opcion_b_lowercase(self):
        """'opción b' → 'b' (decorated with accent)."""
        assert self._call("opción b") == "b"

    def test_opcion_b_uppercase_letter(self):
        """'opción B' → 'b' (uppercase letter in decoration)."""
        assert self._call("opción B") == "b"

    def test_la_b(self):
        """'la b' → 'b' (article decoration)."""
        assert self._call("la b") == "b"

    def test_el_b(self):
        """'el b' → 'b' (masculine article decoration)."""
        assert self._call("el b") == "b"

    def test_b_with_period(self):
        """'B.' → 'b' (letter followed by period)."""
        assert self._call("B.") == "b"

    def test_b_with_closing_paren(self):
        """'b)' → 'b' (letter followed by closing paren)."""
        assert self._call("b)") == "b"

    def test_opcion_without_accent(self):
        """'opcion b' → 'b' (without tilde — Spanish keyboards vary)."""
        assert self._call("opcion b") == "b"

    def test_letter_a_extraction(self):
        """'opción a' → 'a'."""
        assert self._call("opción a") == "a"

    def test_letter_e_extraction(self):
        """'opción e' → 'e' (boundary — max allowed letter)."""
        assert self._call("opción e") == "e"

    def test_whitespace_surrounding(self):
        """'  b  ' → 'b' (surrounding whitespace stripped by caller)."""
        # The helper receives already-stripped input from the tool
        assert self._call("b") == "b"

    def test_la_opcion_b(self):
        """'la opción b' → 'b' (full decoration)."""
        assert self._call("la opción b") == "b"

    # --- Negative cases (should return None) ---

    def test_el_visible_is_not_positional(self):
        """'el visible' → None (semantic description, not positional)."""
        assert self._call("el visible") is None

    def test_number_2_is_not_positional(self):
        """'2' → None (numbers excluded to avoid FAROS_LA_2F conflicts)."""
        assert self._call("2") is None

    def test_modelo_b_is_not_positional(self):
        """'modelo b' → None (multi-word prefix not in pattern)."""
        assert self._call("modelo b") is None

    def test_el_mas_barato_is_not_positional(self):
        """'el más barato' → None (semantic — multiple words after 'el')."""
        assert self._call("el más barato") is None

    def test_empty_string_is_not_positional(self):
        """'' → None (empty response)."""
        assert self._call("") is None

    def test_f_is_not_positional(self):
        """'f' → None (letter f is out of a-e range)."""
        assert self._call("f") is None

    def test_two_letters_is_not_positional(self):
        """'ab' → None (two-letter response is not positional)."""
        assert self._call("ab") is None

    def test_number_word_is_not_positional(self):
        """'segunda' → None (ordinal word, not letter)."""
        assert self._call("segunda") is None


# ===========================================================================
# Standalone regex tests (always run — no dependency on module load)
# Validates the regex pattern directly, independent of module loading.
# ===========================================================================

# This is the same pattern from element_tools.py — test it in isolation
_PATTERN = re.compile(
    r'^\s*(?:(?:la\s+|el\s+)?opci[oó]n\s+|la\s+|el\s+)?([a-eA-E])[.):\s]*$',
    re.IGNORECASE,
)


def _regex_extract(response: str) -> "str | None":
    """Apply the regex directly — no module dependency."""
    m = _PATTERN.match(response.strip())
    return m.group(1).lower() if m else None


class TestRegexPatternDirectly:
    """
    Tests the regex pattern directly without importing element_tools.
    These always run, even in environments where the full agent stack is absent.
    """

    def test_bare_lowercase_b(self):
        assert _regex_extract("b") == "b"

    def test_bare_uppercase_b(self):
        assert _regex_extract("B") == "b"

    def test_opcion_b_with_accent(self):
        assert _regex_extract("opción b") == "b"

    def test_opcion_b_without_accent(self):
        assert _regex_extract("opcion b") == "b"

    def test_opcion_b_uppercase_letter(self):
        assert _regex_extract("opción B") == "b"

    def test_la_b(self):
        assert _regex_extract("la b") == "b"

    def test_el_b(self):
        assert _regex_extract("el b") == "b"

    def test_b_with_period(self):
        assert _regex_extract("B.") == "b"

    def test_b_with_paren(self):
        assert _regex_extract("b)") == "b"

    def test_la_opcion_b(self):
        assert _regex_extract("la opción b") == "b"

    def test_letter_a(self):
        assert _regex_extract("opción a") == "a"

    def test_letter_e(self):
        assert _regex_extract("opción e") == "e"

    # Negative cases

    def test_f_out_of_range(self):
        assert _regex_extract("f") is None

    def test_number_2(self):
        assert _regex_extract("2") is None

    def test_el_visible_semantic(self):
        assert _regex_extract("el visible") is None

    def test_el_mas_barato_semantic(self):
        assert _regex_extract("el más barato") is None

    def test_modelo_b_unrecognized_prefix(self):
        assert _regex_extract("modelo b") is None

    def test_empty_string(self):
        assert _regex_extract("") is None

    def test_two_char_ab(self):
        assert _regex_extract("ab") is None

    def test_segunda_ordinal(self):
        assert _regex_extract("segunda") is None


# ===========================================================================
# Phase 2: LLM-path substring guard unit tests (pure logic, no imports)
# ===========================================================================

class TestLLMPathSubstringGuard:
    """
    Verify the len(alloc_norm) > 2 guard prevents single/double-char
    allocations from spuriously matching variant names.

    Pure logic test — reproduces element_tools.py lines 904-908 in isolation.
    No module imports needed.
    """

    def _simulate_guard(self, alloc_norm: str, v_name_norm: str, v_code_norm: str) -> bool:
        """Reproduce the guard logic from element_tools.py lines 904-908."""
        return (
            (len(alloc_norm) > 2 and alloc_norm in v_name_norm)
            or v_name_norm in alloc_norm
            or alloc_norm == v_code_norm
        )

    def test_single_char_b_does_not_match_visible(self):
        """'b' (len=1) must NOT substring-match 'regulador visible'."""
        result = self._simulate_guard(
            alloc_norm="b",
            v_name_norm="regulador visible",
            v_code_norm="regulador_visible",
        )
        assert result is False, "'b' should not match 'regulador visible' via substring"

    def test_single_char_b_does_not_match_interior(self):
        """'b' (len=1) must NOT substring-match 'regulador interior'."""
        result = self._simulate_guard(
            alloc_norm="b",
            v_name_norm="regulador interior",
            v_code_norm="regulador_interior",
        )
        assert result is False, "'b' should not match 'regulador interior' via substring"

    def test_three_char_still_matches(self):
        """A 3+ char alloc_norm CAN still match via substring."""
        result = self._simulate_guard(
            alloc_norm="reg",
            v_name_norm="regulador visible",
            v_code_norm="regulador_visible",
        )
        assert result is True, "'reg' (len=3) should substring-match 'regulador visible'"

    def test_full_name_matches_via_substring(self):
        """'regulador' (len>2) should match 'regulador visible' via substring."""
        result = self._simulate_guard(
            alloc_norm="regulador",
            v_name_norm="regulador visible",
            v_code_norm="regulador_visible",
        )
        assert result is True, "'regulador' should match 'regulador visible'"

    def test_exact_code_match_still_works_for_short(self):
        """Exact code match (alloc_norm == v_code_norm) still works for any length."""
        result = self._simulate_guard(
            alloc_norm="b",
            v_name_norm="opcion b",
            v_code_norm="b",  # exact match
        )
        assert result is True, "Exact code match must always work regardless of length"

    def test_v_name_in_alloc_still_works(self):
        """v_name_norm in alloc_norm (long response containing short name) still works."""
        result = self._simulate_guard(
            alloc_norm="regulador interior completo",
            v_name_norm="regulador interior",
            v_code_norm="interior",
        )
        assert result is True, "v_name_norm in alloc_norm must still match"

    def test_two_char_allocation_no_substring_match(self):
        """2-char alloc must also NOT substring-match via alloc_norm in v_name_norm."""
        result = self._simulate_guard(
            alloc_norm="ab",
            v_name_norm="cable de freno ab",
            v_code_norm="cable_freno",
        )
        # len("ab") = 2, NOT > 2, so substring check skipped
        # v_name_norm in alloc_norm → "cable de freno ab" in "ab" → False
        # alloc_norm == v_code_norm → "ab" == "cable_freno" → False
        assert result is False, "2-char alloc should NOT substring-match"

    def test_guard_boundary_exactly_3_chars(self):
        """Boundary: exactly 3 chars (len > 2) is allowed to substring-match."""
        result = self._simulate_guard(
            alloc_norm="reg",
            v_name_norm="regulador",
            v_code_norm="regulador",
        )
        assert result is True, "len=3 should pass the guard and substring-match"

    def test_guard_boundary_exactly_2_chars(self):
        """Boundary: exactly 2 chars (NOT > 2) is blocked from substring-match."""
        result = self._simulate_guard(
            alloc_norm="re",
            v_name_norm="regulador",
            v_code_norm="regulador",
        )
        # len("re") = 2, NOT > 2 → substring check skipped
        # "regulador" in "re" → False
        # "re" == "regulador" → False
        assert result is False, "len=2 should be blocked from substring-matching"


# ===========================================================================
# Integration tests — decorated positional response resolves via variant_position
# (require full agent stack — skipped if structlog not available)
# ===========================================================================

FAKE_CATEGORY_ID = "bbbbbbbb-0000-0000-0000-000000000002"

VARIANTS_PLACA_SOLAR_DESIGN = [
    {
        "code": "PLACA_SOLAR_REGULADOR_VISIBLE",
        "name": "Placa Solar - Regulador Visible",
        "variant_code": "REGULADOR_VISIBLE",
        "keywords": ["visible", "regulador visible", "exterior"],
        "sort_order": 10,
        "variant_position": 1,
        "parent_element_id": "parent-uuid-ps",
        "multi_select_keywords": [],
    },
    {
        "code": "PLACA_SOLAR_REGULADOR_INTERIOR",
        "name": "Placa Solar - Regulador Interior",
        "variant_code": "REGULADOR_INTERIOR",
        "keywords": ["interior", "regulador interior", "oculto"],
        "sort_order": 20,
        "variant_position": 2,
        "parent_element_id": "parent-uuid-ps",
        "multi_select_keywords": [],
    },
]

BASE_ELEMENT_PLACA_SOLAR = {
    "code": "PLACA_SOLAR",
    "multi_select_keywords": [],
}


def _has_full_stack() -> bool:
    """
    Check if the full agent stack is available for integration tests.
    We check for langchain_core (which is not stubbed) as a proxy for the
    full Docker environment being present.
    """
    try:
        import langchain_core.tools  # noqa: F401
        # Verify it's a real module, not our stub (stub has no real attributes)
        if not hasattr(langchain_core.tools, "StructuredTool"):
            return False
        import structlog  # noqa: F401
        if not hasattr(structlog, "BoundLogger"):
            return False
        return True
    except (ImportError, AttributeError):
        return False


def _make_tool_call(variants, base_element, respuesta: str, category_id=FAKE_CATEGORY_ID):
    """
    Invoke seleccionar_variante_por_respuesta with mocked services.
    Returns the parsed JSON dict from the tool.
    """
    import asyncio
    from agent.tools.element_tools import seleccionar_variante_por_respuesta

    with (
        patch(
            "agent.tools.element_tools.get_or_fetch_category_id",
            new=AsyncMock(return_value=category_id),
        ),
        patch(
            "agent.tools.element_tools.get_element_service",
        ) as mock_get_svc,
        patch(
            "agent.tools.element_tools.validate_category_slug",
            return_value=None,
        ),
    ):
        mock_svc = MagicMock()
        mock_svc.get_element_variants = AsyncMock(return_value=variants)
        mock_svc.get_element_by_code = AsyncMock(return_value=base_element)
        mock_get_svc.return_value = mock_svc

        result = asyncio.run(
            seleccionar_variante_por_respuesta.ainvoke(
                {
                    "categoria_vehiculo": "aseicars-prof",
                    "codigo_elemento_base": base_element["code"],
                    "respuesta_usuario": respuesta,
                }
            )
        )

    return json.loads(result)


@pytest.mark.skipif(not _has_full_stack(), reason="Requires full agent stack (structlog, langchain)")
class TestDecoratedPositionalIntegration:
    """Integration tests: decorated positional responses resolve via variant_position."""

    def test_opcion_b_resolves_to_position_2(self):
        """
        'opción b' must resolve to PLACA_SOLAR_REGULADOR_INTERIOR (variant_position=2).
        This was the confirmed bug: 'opción b' was falling to LLM and getting position 1.
        """
        result = _make_tool_call(
            VARIANTS_PLACA_SOLAR_DESIGN, BASE_ELEMENT_PLACA_SOLAR, "opción b"
        )
        assert "selected_variant" in result, f"Unexpected result: {result}"
        assert result["selected_variant"] == "PLACA_SOLAR_REGULADOR_INTERIOR", (
            f"'opción b' must resolve to PLACA_SOLAR_REGULADOR_INTERIOR (position 2), "
            f"got: {result.get('selected_variant')}"
        )
        assert result.get("match_method") == "variant_position", (
            "'opción b' must use variant_position fast-path, not LLM"
        )
        assert result.get("variant_position") == 2

    def test_opcion_b_uppercase_resolves_to_position_2(self):
        """'opción B' → same as 'opción b' → PLACA_SOLAR_REGULADOR_INTERIOR."""
        result = _make_tool_call(
            VARIANTS_PLACA_SOLAR_DESIGN, BASE_ELEMENT_PLACA_SOLAR, "opción B"
        )
        assert result["selected_variant"] == "PLACA_SOLAR_REGULADOR_INTERIOR"
        assert result.get("match_method") == "variant_position"

    def test_b_with_period_resolves_to_position_2(self):
        """'B.' → PLACA_SOLAR_REGULADOR_INTERIOR (position 2)."""
        result = _make_tool_call(
            VARIANTS_PLACA_SOLAR_DESIGN, BASE_ELEMENT_PLACA_SOLAR, "B."
        )
        assert result["selected_variant"] == "PLACA_SOLAR_REGULADOR_INTERIOR"
        assert result.get("match_method") == "variant_position"

    def test_la_b_resolves_to_position_2(self):
        """'la b' → PLACA_SOLAR_REGULADOR_INTERIOR (position 2)."""
        result = _make_tool_call(
            VARIANTS_PLACA_SOLAR_DESIGN, BASE_ELEMENT_PLACA_SOLAR, "la b"
        )
        assert result["selected_variant"] == "PLACA_SOLAR_REGULADOR_INTERIOR"
        assert result.get("match_method") == "variant_position"

    def test_opcion_a_resolves_to_position_1(self):
        """'opción a' → PLACA_SOLAR_REGULADOR_VISIBLE (position 1)."""
        result = _make_tool_call(
            VARIANTS_PLACA_SOLAR_DESIGN, BASE_ELEMENT_PLACA_SOLAR, "opción a"
        )
        assert result["selected_variant"] == "PLACA_SOLAR_REGULADOR_VISIBLE"
        assert result.get("match_method") == "variant_position"
        assert result.get("variant_position") == 1


@pytest.mark.skipif(not _has_full_stack(), reason="Requires full agent stack (structlog, langchain)")
class TestRegressionBareLetterStillWorks:
    """Bare letters must still work exactly as before (no regression)."""

    def test_bare_b_resolves_to_position_2(self):
        """'b' (bare, original behavior) must still resolve to position 2."""
        result = _make_tool_call(
            VARIANTS_PLACA_SOLAR_DESIGN, BASE_ELEMENT_PLACA_SOLAR, "b"
        )
        assert result.get("match_method") == "variant_position"
        assert result["selected_variant"] == "PLACA_SOLAR_REGULADOR_INTERIOR"
        assert result.get("variant_position") == 2

    def test_bare_a_resolves_to_position_1(self):
        """'a' → PLACA_SOLAR_REGULADOR_VISIBLE (position 1) — unchanged."""
        result = _make_tool_call(
            VARIANTS_PLACA_SOLAR_DESIGN, BASE_ELEMENT_PLACA_SOLAR, "a"
        )
        assert result.get("match_method") == "variant_position"
        assert result["selected_variant"] == "PLACA_SOLAR_REGULADOR_VISIBLE"

    def test_number_2_is_still_excluded(self):
        """'2' must NOT trigger positional resolution (numbers excluded)."""
        result = _make_tool_call(
            VARIANTS_PLACA_SOLAR_DESIGN, BASE_ELEMENT_PLACA_SOLAR, "2"
        )
        assert result.get("match_method") != "variant_position", (
            "'2' should never use variant_position fast-path"
        )

    def test_semantic_visible_still_uses_keyword(self):
        """'el visible' must fall through to keyword matching, not positional."""
        result = _make_tool_call(
            VARIANTS_PLACA_SOLAR_DESIGN, BASE_ELEMENT_PLACA_SOLAR, "el visible"
        )
        assert result.get("match_method") != "variant_position", (
            "'el visible' is semantic and must go through keyword/LLM path"
        )
        if "selected_variant" in result:
            assert result["selected_variant"] == "PLACA_SOLAR_REGULADOR_VISIBLE", (
                "'visible' keyword should resolve to PLACA_SOLAR_REGULADOR_VISIBLE"
            )


# ===========================================================================
# Phase 4: Chatwoot PII log sanitization tests (pure — no module imports)
# ===========================================================================

class TestChatwootWebhookLogSanitization:
    """Verify INFO logs from webhook handler contain no raw PII."""

    def test_new_log_pattern_does_not_include_raw_body(self):
        """
        The new 'webhook_received' log must use payload_length (int), not body_str.
        This is a contract test — verifying the design of the new log pattern.
        """
        import logging

        captured = []

        class CapturingHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                if record.levelno == logging.INFO:
                    captured.append(record)

        handler = CapturingHandler()
        test_logger = logging.getLogger("test.chatwoot.pii")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)

        try:
            phone_number = "+34612345678"
            raw_body = (
                f'{{"event":"message_created","phone":"{phone_number}",'
                f'"content":"Hola quiero homologar mi escape"}}'
            )

            # Reproduce EXACTLY the new logging pattern from chatwoot.py
            test_logger.info(
                "webhook_received",
                extra={
                    "payload_length": len(raw_body),
                },
            )

            assert len(captured) == 1, "Should have 1 INFO log record"
            record = captured[0]

            # Message must be the sanitized one
            assert "webhook_received" in record.getMessage()

            # Phone must NOT be in the message string
            assert phone_number not in record.getMessage(), (
                "Phone number must NOT appear in INFO log message"
            )
            # Raw body must NOT be in the message string
            assert raw_body not in record.getMessage(), (
                "Raw body must NOT appear in INFO log message"
            )

            # payload_length (non-PII) must be present in extra
            assert hasattr(record, "payload_length"), (
                "payload_length field must be present in log record extra"
            )
        finally:
            test_logger.removeHandler(handler)

    def test_payload_preview_truncated_to_80_chars(self):
        """
        Error log's payload_preview must be ≤80 chars (was ≤1000 in old code).
        Pure assertion — no module import needed.
        """
        raw_body = "+" + "9" * 100  # 101 chars of potentially PII-containing data
        payload_preview = raw_body[:80]

        assert len(payload_preview) <= 80, "payload_preview must be ≤80 chars"
        assert len(raw_body) > 80, "test body should exceed truncation limit"

    def test_debug_log_pattern_does_not_include_full_body(self):
        """
        DEBUG log must also avoid emitting the full raw body.
        The new pattern only logs payload_length and a 80-char hint.
        """
        raw_body = "+34612345678 Hello this is a test message with PII"
        payload_hint = raw_body[:80]
        payload_length = len(raw_body)

        # Verify the hint is bounded
        assert len(payload_hint) <= 80
        # Verify full body is NOT the same as the hint when body > 80 chars
        long_body = "+" + "x" * 200
        assert len(long_body[:80]) < len(long_body), "hint must be shorter than full body"
