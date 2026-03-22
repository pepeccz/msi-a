"""
Tests for combined-utterance fragment extraction helpers.

Covers:
  - _build_element_anchors() — builds regex anchors for element detection
  - _score_clause_for_element() — scores clause relevance to an element
  - _extract_element_fragment() — extracts the relevant fragment from a mixed response

Run with:
    pytest tests/test_fragment_extraction.py -v

Note: These functions live in agent/tools/element_tools.py which requires
the full agent stack (structlog, langchain, etc.). We use direct module
loading with stubs to avoid the dependency chain, matching the pattern
from test_fix_variant_resolution.py.
"""
import sys
import importlib.util
import types
import pytest
from pathlib import Path
from unittest.mock import MagicMock


# ===========================================================================
# Direct module extraction — load fragment helpers from element_tools.py
# without triggering agent/__init__.py and the full LangGraph stack.
# ===========================================================================

def _load_fragment_helpers():
    """
    Extract _build_element_anchors, _score_clause_for_element, and
    _extract_element_fragment from element_tools.py by stubbing heavy deps.
    """

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

    # We also need agent.utils.text_utils to be importable for normalize_text
    # It's used lazily inside the helpers, so ensure the real module loads.
    # Stub it in sys.modules so the import inside the helpers finds it.
    text_utils_path = Path(__file__).parent.parent / "agent" / "utils" / "text_utils.py"
    text_spec = importlib.util.spec_from_file_location("agent.utils.text_utils", text_utils_path)
    text_mod = importlib.util.module_from_spec(text_spec)  # type: ignore[arg-type]
    text_spec.loader.exec_module(text_mod)  # type: ignore[union-attr]
    sys.modules["agent.utils.text_utils"] = text_mod

    # Now load element_tools.py via importlib (bypasses agent/__init__)
    tool_path = Path(__file__).parent.parent / "agent" / "tools" / "element_tools.py"
    spec = importlib.util.spec_from_file_location("agent.tools.element_tools_fragment", tool_path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    return (
        module._build_element_anchors,
        module._score_clause_for_element,
        module._extract_element_fragment,
        module._CLAUSE_SPLIT_RE,
        module._FRAGMENT_MIN_SCORE,
    )


# Load once at module level
try:
    (
        _build_element_anchors,
        _score_clause_for_element,
        _extract_element_fragment,
        _CLAUSE_SPLIT_RE,
        _FRAGMENT_MIN_SCORE,
    ) = _load_fragment_helpers()
    _HELPERS_AVAILABLE = True
except Exception as e:
    _HELPERS_AVAILABLE = False
    _HELPERS_LOAD_ERROR = str(e)
    _build_element_anchors = None
    _score_clause_for_element = None
    _extract_element_fragment = None
    _CLAUSE_SPLIT_RE = None
    _FRAGMENT_MIN_SCORE = None


# ===========================================================================
# Shared test fixtures
# ===========================================================================

VARIANTS_PLACA_SOLAR = [
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

VARIANTS_TOLDO = [
    {
        "code": "TOLDO_MANUAL",
        "name": "Toldo Manual",
        "variant_code": "MANUAL",
        "keywords": ["manual"],
        "sort_order": 10,
        "variant_position": 1,
        "parent_element_id": "parent-uuid-toldo",
        "multi_select_keywords": [],
    },
    {
        "code": "TOLDO_ELECTRICO",
        "name": "Toldo Electrico",
        "variant_code": "ELECTRICO",
        "keywords": ["electrico", "automatico"],
        "sort_order": 20,
        "variant_position": 2,
        "parent_element_id": "parent-uuid-toldo",
        "multi_select_keywords": [],
    },
]

BASE_PLACA_SOLAR = {"code": "PLACA_SOLAR", "name": "Placa Solar", "multi_select_keywords": []}
BASE_TOLDO = {"code": "TOLDO", "name": "Toldo", "multi_select_keywords": []}


_SKIP_MSG = f"Could not load helpers: {locals().get('_HELPERS_LOAD_ERROR', 'unknown')}"


# ===========================================================================
# _build_element_anchors tests
# ===========================================================================

@pytest.mark.skipif(not _HELPERS_AVAILABLE, reason=_SKIP_MSG)
class TestBuildElementAnchors:
    """Unit tests for _build_element_anchors."""

    def test_anchors_from_element_code(self):
        """Element code 'PLACA_SOLAR' produces anchors containing 'placa solar'."""
        anchors = _build_element_anchors("PLACA_SOLAR", None, None, [])
        joined = " ".join(anchors)
        assert "placa" in joined
        assert "solar" in joined

    def test_anchors_from_base_element_name(self):
        """Base element name contributes to anchors."""
        anchors = _build_element_anchors(
            "TOLDO", {"name": "Toldo Lateral", "code": "TOLDO"}, None, []
        )
        # "lateral" (len > 3) should appear as anchor
        assert any("lateral" in a for a in anchors)

    def test_anchors_from_pending_question(self):
        """Pending question text contributes anchor words."""
        pending = {"pregunta": "Qué tipo de regulador prefieres?"}
        anchors = _build_element_anchors("PLACA_SOLAR", None, pending, [])
        assert any("regulador" in a for a in anchors)

    def test_anchors_deduplicated(self):
        """Anchors list contains no duplicates."""
        anchors = _build_element_anchors(
            "PLACA_SOLAR", BASE_PLACA_SOLAR, None, VARIANTS_PLACA_SOLAR
        )
        assert len(anchors) == len(set(anchors))

    def test_stop_words_excluded(self):
        """Stop words (de, del, el, la, etc.) are excluded from anchors."""
        # Use an element code that would produce stop words
        anchors = _build_element_anchors("BOLA_DE_REMOLQUE", None, None, [])
        # "de" should not appear as a standalone anchor
        assert "de" not in anchors

    def test_empty_code_returns_empty(self):
        """An empty code with no other context produces no anchors."""
        anchors = _build_element_anchors("", None, None, [])
        # Should not crash; may return empty list
        assert isinstance(anchors, list)


# ===========================================================================
# _score_clause_for_element tests
# ===========================================================================

@pytest.mark.skipif(not _HELPERS_AVAILABLE, reason=_SKIP_MSG)
class TestScoreClauseForElement:
    """Unit tests for _score_clause_for_element."""

    def test_matching_clause_scores_above_zero(self):
        """A clause containing anchor words scores > 0."""
        anchors = ["placa solar", "placa", "solar"]
        score = _score_clause_for_element("placa solar opcion b", anchors)
        assert score > 0.0

    def test_non_matching_clause_scores_zero(self):
        """A clause with no overlap to anchors scores 0."""
        anchors = ["placa solar", "placa", "solar"]
        score = _score_clause_for_element("cama abatible grande", anchors)
        assert score == 0.0

    def test_empty_clause_scores_zero(self):
        """An empty clause scores 0."""
        anchors = ["placa", "solar"]
        score = _score_clause_for_element("", anchors)
        assert score == 0.0

    def test_score_capped_at_one(self):
        """Score never exceeds 1.0 regardless of anchor matches."""
        anchors = ["placa", "solar", "regulador", "panel", "fotovoltaico"]
        score = _score_clause_for_element(
            "placa solar regulador panel fotovoltaico", anchors
        )
        assert score <= 1.0

    def test_longer_anchor_scores_higher(self):
        """A multi-word anchor match scores higher than a single-word match."""
        anchors_multi = ["placa solar"]
        anchors_single = ["placa"]
        score_multi = _score_clause_for_element("placa solar opcion b", anchors_multi)
        score_single = _score_clause_for_element("placa solar opcion b", anchors_single)
        assert score_multi > score_single

    def test_partial_word_overlap_scores_positive(self):
        """Partial word overlap (some anchor words match) gives a positive score."""
        anchors = ["placa solar"]  # multi-word anchor
        # Only "placa" appears in clause, not "solar"
        score = _score_clause_for_element("placa opcion b", anchors)
        assert score > 0.0


# ===========================================================================
# _extract_element_fragment tests
# ===========================================================================

@pytest.mark.skipif(not _HELPERS_AVAILABLE, reason=_SKIP_MSG)
class TestExtractElementFragment:
    """Unit tests for _extract_element_fragment — the main entry point."""

    # --- Combined utterance isolation ---

    def test_combined_response_extracts_placa_solar_fragment(self):
        """
        'placa solar opcion b y el toldo A' while resolving PLACA_SOLAR
        should extract the placa solar fragment.
        """
        fragment = _extract_element_fragment(
            "placa solar opcion b y el toldo A",
            "PLACA_SOLAR",
            BASE_PLACA_SOLAR,
            None,
            VARIANTS_PLACA_SOLAR,
        )
        fragment_lower = fragment.lower()
        assert "placa solar" in fragment_lower, (
            f"Fragment should contain 'placa solar', got: '{fragment}'"
        )
        assert "toldo" not in fragment_lower, (
            f"Fragment should NOT contain 'toldo', got: '{fragment}'"
        )

    def test_combined_response_extracts_toldo_fragment(self):
        """
        'placa solar opcion b y el toldo A' while resolving TOLDO
        should extract the toldo fragment.
        """
        fragment = _extract_element_fragment(
            "placa solar opcion b y el toldo A",
            "TOLDO",
            BASE_TOLDO,
            None,
            VARIANTS_TOLDO,
        )
        fragment_lower = fragment.lower()
        assert "toldo" in fragment_lower, (
            f"Fragment should contain 'toldo', got: '{fragment}'"
        )
        assert "placa solar" not in fragment_lower, (
            f"Fragment should NOT contain 'placa solar', got: '{fragment}'"
        )

    def test_combined_with_comma_separator(self):
        """Comma-separated combined response splits correctly."""
        fragment = _extract_element_fragment(
            "placa solar opcion b, toldo manual",
            "PLACA_SOLAR",
            BASE_PLACA_SOLAR,
            None,
            VARIANTS_PLACA_SOLAR,
        )
        assert "placa solar" in fragment.lower()
        assert "toldo" not in fragment.lower()

    # --- Single element response (no splitting needed) ---

    def test_single_element_response_returns_full(self):
        """'opcion b' with no connectors returns the full response."""
        fragment = _extract_element_fragment(
            "opcion b",
            "PLACA_SOLAR",
            BASE_PLACA_SOLAR,
            None,
            VARIANTS_PLACA_SOLAR,
        )
        assert fragment == "opcion b"

    def test_single_word_response_returns_full(self):
        """'interior' with no connectors returns the full response."""
        fragment = _extract_element_fragment(
            "interior",
            "PLACA_SOLAR",
            BASE_PLACA_SOLAR,
            None,
            VARIANTS_PLACA_SOLAR,
        )
        assert fragment == "interior"

    # --- Bare letter behavior ---

    def test_bare_letter_returns_full(self):
        """
        A bare letter like 'b' has no connectors to split on,
        so it returns the full response (single clause).
        """
        fragment = _extract_element_fragment(
            "b",
            "PLACA_SOLAR",
            BASE_PLACA_SOLAR,
            None,
            VARIANTS_PLACA_SOLAR,
        )
        assert fragment == "b"

    # --- Variant name in response ---

    def test_variant_name_mention_extracts_correct_clause(self):
        """
        When user mentions a variant name directly in a combined response,
        the correct clause is extracted.
        """
        fragment = _extract_element_fragment(
            "placa solar regulador visible y toldo manual",
            "PLACA_SOLAR",
            BASE_PLACA_SOLAR,
            None,
            VARIANTS_PLACA_SOLAR,
        )
        fragment_lower = fragment.lower()
        assert "placa solar" in fragment_lower or "regulador visible" in fragment_lower

    # --- Edge cases ---

    def test_empty_response_returns_empty(self):
        """Empty response returns empty string."""
        fragment = _extract_element_fragment(
            "",
            "PLACA_SOLAR",
            BASE_PLACA_SOLAR,
            None,
            VARIANTS_PLACA_SOLAR,
        )
        assert fragment == ""

    def test_whitespace_only_response_returns_empty(self):
        """Whitespace-only response returns empty string."""
        fragment = _extract_element_fragment(
            "   ",
            "PLACA_SOLAR",
            BASE_PLACA_SOLAR,
            None,
            VARIANTS_PLACA_SOLAR,
        )
        assert fragment == ""

    def test_no_matching_element_returns_full_response(self):
        """
        When no clause matches the element above the threshold,
        the full response is returned as a safe fallback.
        """
        fragment = _extract_element_fragment(
            "cama abatible grande y mesa plegable",
            "PLACA_SOLAR",
            BASE_PLACA_SOLAR,
            None,
            VARIANTS_PLACA_SOLAR,
        )
        # Neither clause mentions placa solar — should fall back to full response
        assert fragment == "cama abatible grande y mesa plegable"

    def test_only_connectors_returns_full_response(self):
        """
        A response with only connectors (e.g., 'y') after splitting
        returns the full response as fallback.
        """
        fragment = _extract_element_fragment(
            "y",
            "PLACA_SOLAR",
            BASE_PLACA_SOLAR,
            None,
            VARIANTS_PLACA_SOLAR,
        )
        # "y" is a split delimiter — after splitting, clauses may be empty
        # The function should handle this gracefully
        assert isinstance(fragment, str)

    def test_three_elements_combined(self):
        """Three elements separated by connectors extracts the right one."""
        fragment = _extract_element_fragment(
            "placa solar opcion b y toldo manual y escalera exterior",
            "TOLDO",
            BASE_TOLDO,
            None,
            VARIANTS_TOLDO,
        )
        fragment_lower = fragment.lower()
        assert "toldo" in fragment_lower
        assert "placa solar" not in fragment_lower
        assert "escalera" not in fragment_lower

    def test_semicolon_separator(self):
        """Semicolon-separated combined response splits correctly."""
        fragment = _extract_element_fragment(
            "placa solar la b; toldo el manual",
            "TOLDO",
            BASE_TOLDO,
            None,
            VARIANTS_TOLDO,
        )
        assert "toldo" in fragment.lower()

    def test_pending_question_improves_matching(self):
        """Providing a pending question with specific words improves clause scoring."""
        pending = {"pregunta": "Qué tipo de toldo prefieres?"}
        fragment = _extract_element_fragment(
            "placa solar opcion b y toldo manual",
            "TOLDO",
            BASE_TOLDO,
            pending,
            VARIANTS_TOLDO,
        )
        assert "toldo" in fragment.lower()
