"""Tests for asyncio.gather variant resolution in identificar_y_resolver_elementos.

Covers the two-phase gather pattern:
- Phase 1: asyncio.gather for get_element_variants() on all matched elements
- Phase 2: asyncio.gather for get_element_by_code() on elements with variants

Scenarios:
1. All variants resolve successfully → correct output
2. One variant query fails (Exception) → other still works, failed defaults to no-variants
3. Zero matched elements → no gather needed, empty result

Run with: pytest tests/agent/tools/test_identificar_gather_variants.py -v
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4


FAKE_CATEGORY_ID = str(uuid4())
FAKE_CATEGORY_SLUG = "motos-part"


def _make_matched_element(code: str, name: str) -> dict:
    """Create an element dict as returned by match_elements_with_unmatched."""
    return {
        "id": str(uuid4()),
        "code": code,
        "name": name,
        "description": "",
        "keywords": [],
    }


def _make_variant(code: str, name: str, position: int) -> dict:
    """Create a variant dict as returned by get_element_variants."""
    return {
        "id": str(uuid4()),
        "code": code,
        "name": name,
        "variant_type": "option",
        "variant_code": code,
        "variant_position": position,
    }


def _make_base_element(code: str, question_hint: str | None = None) -> dict:
    """Create a base element dict as returned by get_element_by_code."""
    return {
        "id": str(uuid4()),
        "code": code,
        "name": code.replace("_", " ").title(),
        "description": "",
        "keywords": [],
        "question_hint": question_hint,
        "multi_select_keywords": [],
        "is_active": True,
    }


def _setup_common_mocks():
    """Set up common mock objects for the function under test."""
    mock_element_service = MagicMock()
    mock_tarifa_service = MagicMock()

    mock_state = {"client_type": "particular", "current_mode": "PRESUPUESTO"}

    return mock_element_service, mock_tarifa_service, mock_state


@pytest.mark.asyncio
class TestIdentificarGatherVariants:
    """Test the asyncio.gather variant resolution in identificar_y_resolver_elementos."""

    async def test_all_variants_resolve_successfully(self):
        """Two elements with variants, both resolve → correct preguntas_variantes."""
        mock_es, mock_ts, mock_state = _setup_common_mocks()

        elem_a = _make_matched_element("SUSPENSION", "Suspensión")
        elem_b = _make_matched_element("ESCAPE", "Escape")

        variants_a = [
            _make_variant("SUSPENSION_DEL", "Delantera", 1),
            _make_variant("SUSPENSION_TRA", "Trasera", 2),
        ]
        variants_b = [
            _make_variant("ESCAPE_HOM", "Homologado", 1),
            _make_variant("ESCAPE_LIB", "Libre", 2),
        ]

        base_a = _make_base_element("SUSPENSION", "¿Qué suspensión?")
        base_b = _make_base_element("ESCAPE", "¿Qué escape?")

        # match_elements_with_unmatched returns both elements
        mock_es.match_elements_with_unmatched = AsyncMock(return_value={
            "matches": [(elem_a, 0.95), (elem_b, 0.90)],
            "unmatched_terms": [],
            "quantities": {},
        })
        mock_es.get_elements_by_category = AsyncMock(return_value=[elem_a, elem_b])
        mock_es.get_element_variants = AsyncMock(
            side_effect=[variants_a, variants_b]
        )
        mock_es.get_element_by_code = AsyncMock(
            side_effect=[base_a, base_b]
        )

        with patch("agent.tools.element_tools.get_element_service", return_value=mock_es), \
             patch("agent.tools.element_tools.get_tarifa_service", return_value=mock_ts), \
             patch("agent.tools.element_tools.get_or_fetch_category_id", return_value=FAKE_CATEGORY_ID), \
             patch("agent.tools.element_tools.get_current_state", return_value=mock_state), \
             patch("agent.tools.element_tools.validate_category_slug"):

            from agent.tools.element_tools import identificar_y_resolver_elementos

            raw_result = await identificar_y_resolver_elementos.ainvoke(
                {"categoria_vehiculo": FAKE_CATEGORY_SLUG, "descripcion": "suspensión y escape"}
            )

        result = json.loads(raw_result)

        # No elementos_listos (both have variants)
        assert result["elementos_listos"] == []
        # Both appear in elementos_con_variantes
        assert len(result["elementos_con_variantes"]) == 2
        variant_codes = [e["codigo_base"] for e in result["elementos_con_variantes"]]
        assert "SUSPENSION" in variant_codes
        assert "ESCAPE" in variant_codes
        # Both have preguntas_variantes
        assert len(result["preguntas_variantes"]) == 2

        # Verify gather called both variant fetches
        assert mock_es.get_element_variants.await_count == 2
        # Verify gather called both base element fetches
        assert mock_es.get_element_by_code.await_count == 2

    async def test_one_variant_query_fails_other_succeeds(self):
        """One variant query raises Exception → failed one defaults to no-variants."""
        mock_es, mock_ts, mock_state = _setup_common_mocks()

        elem_a = _make_matched_element("SUSPENSION", "Suspensión")
        elem_b = _make_matched_element("ESCAPE", "Escape")

        variants_b = [
            _make_variant("ESCAPE_HOM", "Homologado", 1),
            _make_variant("ESCAPE_LIB", "Libre", 2),
        ]

        base_b = _make_base_element("ESCAPE", "¿Qué escape?")

        mock_es.match_elements_with_unmatched = AsyncMock(return_value={
            "matches": [(elem_a, 0.95), (elem_b, 0.90)],
            "unmatched_terms": [],
            "quantities": {},
        })
        mock_es.get_elements_by_category = AsyncMock(return_value=[elem_a, elem_b])

        # SUSPENSION variant query fails, ESCAPE succeeds
        mock_es.get_element_variants = AsyncMock(
            side_effect=[Exception("DB timeout on SUSPENSION"), variants_b]
        )
        mock_es.get_element_by_code = AsyncMock(return_value=base_b)

        with patch("agent.tools.element_tools.get_element_service", return_value=mock_es), \
             patch("agent.tools.element_tools.get_tarifa_service", return_value=mock_ts), \
             patch("agent.tools.element_tools.get_or_fetch_category_id", return_value=FAKE_CATEGORY_ID), \
             patch("agent.tools.element_tools.get_current_state", return_value=mock_state), \
             patch("agent.tools.element_tools.validate_category_slug"):

            from agent.tools.element_tools import identificar_y_resolver_elementos

            raw_result = await identificar_y_resolver_elementos.ainvoke(
                {"categoria_vehiculo": FAKE_CATEGORY_SLUG, "descripcion": "suspensión y escape"}
            )

        result = json.loads(raw_result)

        # SUSPENSION failed → goes to elementos_listos (no-variants fallback)
        suspension_listos = [
            e for e in result["elementos_listos"] if e["codigo"] == "SUSPENSION"
        ]
        assert len(suspension_listos) == 1
        assert suspension_listos[0]["cantidad"] == 1

        # ESCAPE succeeded → goes to elementos_con_variantes
        escape_variantes = [
            e for e in result["elementos_con_variantes"] if e["codigo_base"] == "ESCAPE"
        ]
        assert len(escape_variantes) == 1
        assert len(escape_variantes[0]["variantes"]) == 2

    async def test_zero_matched_elements_no_gather(self):
        """No matched elements → no gather calls, empty result."""
        mock_es, mock_ts, mock_state = _setup_common_mocks()

        mock_es.match_elements_with_unmatched = AsyncMock(return_value={
            "matches": [],
            "unmatched_terms": ["foobarbaz"],
            "quantities": {},
        })
        mock_es.get_elements_by_category = AsyncMock(return_value=[
            _make_matched_element("BOLA", "Bola"),
        ])

        with patch("agent.tools.element_tools.get_element_service", return_value=mock_es), \
             patch("agent.tools.element_tools.get_tarifa_service", return_value=mock_ts), \
             patch("agent.tools.element_tools.get_or_fetch_category_id", return_value=FAKE_CATEGORY_ID), \
             patch("agent.tools.element_tools.get_current_state", return_value=mock_state), \
             patch("agent.tools.element_tools.validate_category_slug"):

            from agent.tools.element_tools import identificar_y_resolver_elementos

            raw_result = await identificar_y_resolver_elementos.ainvoke(
                {"categoria_vehiculo": FAKE_CATEGORY_SLUG, "descripcion": "foobarbaz"}
            )

        result = json.loads(raw_result)

        assert result["elementos_listos"] == []
        assert result["elementos_con_variantes"] == []
        assert "foobarbaz" in result["terminos_no_reconocidos"]

        # No variant or base element queries should have been made
        mock_es.get_element_variants.assert_not_called()
        mock_es.get_element_by_code.assert_not_called()
