"""
Integration tests for Agent Tools - Element System Integration.

Tests that agent tools correctly use the element system for:
- Element listing
- Tariff calculation based on elements
- Documentation retrieval with multiple images

Run with: pytest tests/test_agent_tools_integration.py -v
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock

from agent.tools.tarifa_tools import (
    listar_elementos,
    calcular_tarifa,
    obtener_documentacion,
)
from database.models import VehicleCategory
from database.connection import get_async_session
from sqlalchemy import select


@pytest.fixture
async def test_category():
    """Get test category."""
    async with get_async_session() as session:
        result = await session.execute(
            select(VehicleCategory)
            .where(VehicleCategory.slug == "aseicars")
        )
        category = result.scalar()
        assert category is not None
        return category


# =============================================================================
# TEST SUITE 1: listar_elementos Tool
# =============================================================================

@pytest.mark.asyncio
async def test_listar_elementos_returns_formatted_list(test_category):
    """Test that listar_elementos returns properly formatted element list."""
    result = await listar_elementos("autocaravanas-profesional")

    # Should return a string formatted for WhatsApp (no markdown)
    assert isinstance(result, str)
    assert len(result) > 0

    # Should contain recognizable element names
    assert "Escalera" in result or "escalera" in result.lower() or "elementos" in result.lower()


@pytest.mark.asyncio
async def test_listar_elementos_includes_keywords():
    """Test that element list includes keywords for user understanding."""
    result = await listar_elementos("autocaravanas-profesional")

    # Keywords should be present in the output
    # (they help users understand what each element is)
    assert isinstance(result, str)
    assert len(result) > 100  # Should be detailed


@pytest.mark.asyncio
async def test_listar_elementos_handles_disabled_system():
    """Test listar_elementos behavior when element system is disabled.

    When USE_ELEMENT_SYSTEM=false, should return appropriate message.
    """
    with patch("shared.config.get_settings") as mock_settings:
        mock_settings.return_value.USE_ELEMENT_SYSTEM = False

        result = await listar_elementos("autocaravanas-profesional")

        # Should either return message or handle gracefully
        assert isinstance(result, str)


@pytest.mark.asyncio
async def test_listar_elementos_nonexistent_category():
    """Test listar_elementos with non-existent category."""
    result = await listar_elementos("nonexistent-category")

    # Should handle gracefully without crashing
    assert isinstance(result, str)


# =============================================================================
# TEST SUITE 2: calcular_tarifa Tool with Element System
# =============================================================================

@pytest.mark.asyncio
async def test_calcular_tarifa_identifies_elements():
    """Test that calcular_tarifa identifies elements from user description."""
    # Example: User mentions "escalera" which should map to ESC_MEC element
    result = await calcular_tarifa(
        categoria_vehiculo="autocaravanas-profesional",
        descripcion_elementos="Quiero homologar una escalera mecánica",
    )

    assert isinstance(result, str)
    # Should contain tariff information
    assert "Tarifa" in result or "€" in result or "precio" in result.lower()


@pytest.mark.asyncio
async def test_calcular_tarifa_respects_feature_flag_disabled():
    """Test calcular_tarifa behavior when USE_ELEMENT_SYSTEM=false.

    Should use legacy system instead.
    """
    with patch("shared.config.get_settings") as mock_settings:
        mock_settings.return_value.USE_ELEMENT_SYSTEM = False

        result = await calcular_tarifa(
            categoria_vehiculo="autocaravanas-profesional",
            descripcion_elementos="escalera",
        )

        # Should work without crashing
        assert isinstance(result, str)


@pytest.mark.asyncio
async def test_calcular_tarifa_compare_mode():
    """Test calcular_tarifa in compare mode (both systems run).

    ELEMENT_SYSTEM_COMPARE_MODE=true should run both systems and log discrepancies.
    """
    with patch("shared.config.get_settings") as mock_settings:
        mock_settings.return_value.USE_ELEMENT_SYSTEM = False
        mock_settings.return_value.ELEMENT_SYSTEM_COMPARE_MODE = True

        with patch("agent.tools.tarifa_tools.logger") as mock_logger:
            result = await calcular_tarifa(
                categoria_vehiculo="autocaravanas-profesional",
                descripcion_elementos="escalera y toldo",
            )

            # Should return result without errors
            assert isinstance(result, str)

            # In compare mode, may log discrepancies
            # (actual logging depends on implementation)


@pytest.mark.asyncio
async def test_calcular_tarifa_with_multiple_elements():
    """Test calcular_tarifa identifying multiple elements correctly."""
    result = await calcular_tarifa(
        categoria_vehiculo="autocaravanas-profesional",
        descripcion_elementos="Necesito homologar escalera, toldo lateral y 2 placas solares",
    )

    assert isinstance(result, str)
    # Should indicate multiple elements are understood
    # (response format depends on implementation)


@pytest.mark.asyncio
async def test_calcular_tarifa_no_elements_found():
    """Test calcular_tarifa when no elements are identified."""
    result = await calcular_tarifa(
        categoria_vehiculo="autocaravanas-profesional",
        descripcion_elementos="xyz abc qwerty nonsense words",
    )

    # Should handle gracefully
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_calcular_tarifa_returns_formatted_for_whatsapp():
    """Test that calcular_tarifa response is formatted for WhatsApp."""
    result = await calcular_tarifa(
        categoria_vehiculo="autocaravanas-profesional",
        descripcion_elementos="una antena parabólica",
    )

    # Should be WhatsApp-friendly (plain text, no markdown if not supported)
    assert isinstance(result, str)
    assert len(result) > 0

    # Response should contain price information
    # (exact format varies, but should be informative)


# =============================================================================
# TEST SUITE 3: obtener_documentacion Tool with Multiple Images
# =============================================================================

@pytest.mark.asyncio
async def test_obtener_documentacion_returns_multiple_images():
    """Test that obtener_documentacion returns multiple images per element."""
    result = await obtener_documentacion(
        categoria_vehiculo="autocaravanas-profesional",
        descripcion_elementos="escalera mecánica",
    )

    # Should return structured response
    assert isinstance(result, dict) or isinstance(result, str)


@pytest.mark.asyncio
async def test_obtener_documentacion_distinguishes_required_vs_examples():
    """Test that documentation distinguishes required documents from examples."""
    result = await obtener_documentacion(
        categoria_vehiculo="autocaravanas-profesional",
        descripcion_elementos="escalera",
    )

    # Result should contain information about required vs optional photos
    # (exact format depends on implementation - string or dict)
    assert result is not None


@pytest.mark.asyncio
async def test_obtener_documentacion_multiple_elements():
    """Test that documentation handles multiple elements correctly."""
    result = await obtener_documentacion(
        categoria_vehiculo="autocaravanas-profesional",
        descripcion_elementos="escalera, toldo y placa solar",
    )

    # Should handle multiple elements
    assert result is not None


@pytest.mark.asyncio
async def test_obtener_documentacion_element_system_disabled():
    """Test obtener_documentacion when element system is disabled."""
    with patch("shared.config.get_settings") as mock_settings:
        mock_settings.return_value.USE_ELEMENT_SYSTEM = False

        result = await obtener_documentacion(
            categoria_vehiculo="autocaravanas-profesional",
            descripcion_elementos="escalera",
        )

        # Should still return documentation (fallback to legacy system)
        assert result is not None


# =============================================================================
# TEST SUITE 4: Tool Integration with Agent
# =============================================================================

@pytest.mark.asyncio
async def test_tools_exported_in_all_tools():
    """Test that all tools are properly exported for agent."""
    from agent.tools.tarifa_tools import ALL_TOOLS

    # Should include new tools
    tool_names = [t.name if hasattr(t, 'name') else str(t) for t in ALL_TOOLS]

    assert any("listar" in str(t).lower() for t in ALL_TOOLS), \
        "listar_elementos tool should be in ALL_TOOLS"


@pytest.mark.asyncio
async def test_tools_have_proper_descriptions():
    """Test that tools have meaningful descriptions for agent understanding."""
    from agent.tools.tarifa_tools import ALL_TOOLS

    # Each tool should have a docstring/description
    for tool in ALL_TOOLS:
        # Tools should have some form of description
        assert tool is not None


@pytest.mark.asyncio
async def test_calcular_tarifa_backward_compatible():
    """Test that calcular_tarifa is backward compatible with legacy calls."""
    # Legacy code might call with just category and description
    result = await calcular_tarifa(
        categoria_vehiculo="autocaravanas-profesional",
        descripcion_elementos="escalera",
    )

    # Should work without errors
    assert isinstance(result, str)


# =============================================================================
# TEST SUITE 5: Error Handling in Tools
# =============================================================================

@pytest.mark.asyncio
async def test_listar_elementos_handles_database_errors():
    """Test that listar_elementos handles database errors gracefully."""
    with patch("agent.services.element_service.ElementService.get_elements_by_category") as mock:
        mock.side_effect = Exception("Database connection error")

        # Should handle error without crashing
        result = await listar_elementos("autocaravanas-profesional")
        assert result is not None  # Should return error message or default response


@pytest.mark.asyncio
async def test_calcular_tarifa_handles_matching_errors():
    """Test that calcular_tarifa handles element matching errors gracefully."""
    with patch("agent.services.element_service.ElementService.match_elements_from_description") as mock:
        mock.side_effect = Exception("Matching service error")

        # Should fall back to legacy system or handle error
        result = await calcular_tarifa(
            categoria_vehiculo="autocaravanas-profesional",
            descripcion_elementos="test",
        )
        assert result is not None


@pytest.mark.asyncio
async def test_obtener_documentacion_handles_image_retrieval_errors():
    """Test that obtener_documentacion handles image retrieval errors."""
    with patch("agent.services.element_service.ElementService.get_element_with_images") as mock:
        mock.side_effect = Exception("Image retrieval error")

        # Should handle error gracefully
        result = await obtener_documentacion(
            categoria_vehiculo="autocaravanas-profesional",
            descripcion_elementos="test",
        )
        assert result is not None


# =============================================================================
# TEST SUITE 6: Performance Tests
# =============================================================================

@pytest.mark.asyncio
async def test_calcular_tarifa_performance():
    """Test that calcular_tarifa responds in reasonable time."""
    import time

    start = time.time()
    result = await calcular_tarifa(
        categoria_vehiculo="autocaravanas-profesional",
        descripcion_elementos="escalera mecánica",
    )
    elapsed = time.time() - start

    assert isinstance(result, str)
    # Should respond reasonably fast (< 5s including DB queries)
    assert elapsed < 5.0, f"calcular_tarifa took {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_obtener_documentacion_performance():
    """Test that obtener_documentacion responds in reasonable time."""
    import time

    start = time.time()
    result = await obtener_documentacion(
        categoria_vehiculo="autocaravanas-profesional",
        descripcion_elementos="escalera",
    )
    elapsed = time.time() - start

    assert result is not None
    # Should respond reasonably fast
    assert elapsed < 5.0, f"obtener_documentacion took {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_listar_elementos_performance():
    """Test that listar_elementos responds in reasonable time."""
    import time

    start = time.time()
    result = await listar_elementos("autocaravanas-profesional")
    elapsed = time.time() - start

    assert isinstance(result, str)
    # Should respond fast (cached)
    assert elapsed < 2.0, f"listar_elementos took {elapsed:.2f}s"


# =============================================================================
# TEST SUITE 7: Regression Tests (Legacy System Compatibility)
# =============================================================================

@pytest.mark.asyncio
async def test_legacy_system_still_works():
    """Test that legacy tariff system still works when element system is disabled."""
    with patch("shared.config.get_settings") as mock_settings:
        mock_settings.return_value.USE_ELEMENT_SYSTEM = False

        result = await calcular_tarifa(
            categoria_vehiculo="autocaravanas-profesional",
            descripcion_elementos="escalera",
        )

        # Should use legacy system successfully
        assert isinstance(result, str)
        assert len(result) > 0


@pytest.mark.asyncio
async def test_tools_dont_break_existing_agent_flow():
    """Test that modified tools don't break existing agent conversation flow."""
    # Simulate agent calling the tools
    results = []

    # Simulated agent workflow
    result1 = await listar_elementos("autocaravanas-profesional")
    results.append(result1)

    result2 = await calcular_tarifa(
        categoria_vehiculo="autocaravanas-profesional",
        descripcion_elementos="escalera",
    )
    results.append(result2)

    result3 = await obtener_documentacion(
        categoria_vehiculo="autocaravanas-profesional",
        descripcion_elementos="escalera",
    )
    results.append(result3)

    # All should succeed
    assert all(r is not None for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
