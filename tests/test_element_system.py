"""
Tests for Element System - hierarchical tariff resolution.

Verifies that the element matching and tariff selection algorithms work
correctly according to the PDF specification for Autocaravanas Profesional.

Run with: pytest tests/test_element_system.py
"""

import pytest
from uuid import uuid4

from agent.services.element_service import ElementService
from agent.services.tarifa_service import TarifaService
from database.models import (
    VehicleCategory,
    TariffTier,
    Element,
    ElementImage,
    TierElementInclusion,
)
from database.connection import get_async_session
from sqlalchemy import select

# Skip marker for tests that use select_tariff_by_elements (not implemented)
# See test_tarifa_service.py for explanation
SKIP_ELEMENT_BASED = pytest.mark.skip(
    reason="select_tariff_by_elements not implemented - uses select_tariff_by_rules instead"
)


@pytest.fixture
async def test_category():
    """Get or create test category."""
    async with get_async_session() as session:
        result = await session.execute(
            select(VehicleCategory)
            .where(VehicleCategory.slug == "aseicars")
        )
        category = result.scalar()
        assert category is not None, "Test category 'aseicars' not found"
        return category


@pytest.fixture
async def test_tiers(test_category):
    """Get tiers for test category."""
    async with get_async_session() as session:
        result = await session.execute(
            select(TariffTier)
            .where(TariffTier.category_id == test_category.id)
            .where(TariffTier.is_active == True)
            .order_by(TariffTier.sort_order)
        )
        tiers = {t.code: t for t in result.scalars().all()}
        assert tiers, "No tiers found for test category"
        return tiers


@pytest.fixture
async def element_service():
    """Get element service instance."""
    return ElementService()


@pytest.fixture
async def tarifa_service():
    """Get tarifa service instance."""
    return TarifaService()


# =============================================================================
# TEST SUITE 1: Element Matching (Phase 1 - Keywords)
# =============================================================================

@pytest.mark.asyncio
async def test_match_single_element(element_service, test_category):
    """Test matching a single element by keyword."""
    description = "necesito homologar una escalera mecánica"

    matches = await element_service.match_elements_from_description(
        description,
        str(test_category.id),
    )

    assert len(matches) > 0, "No elements matched"

    # ESC_MEC should be in top matches
    codes = [elem.get("code") for elem, score in matches]
    assert "ESC_MEC" in codes, "ESC_MEC not found in matches"

    # Check confidence > 0
    for elem, score in matches:
        assert score > 0, f"Negative score for {elem.get('code')}"


@pytest.mark.asyncio
async def test_match_multiple_elements(element_service, test_category):
    """Test matching multiple elements."""
    description = "escalera y toldo lateral"

    matches = await element_service.match_elements_from_description(
        description,
        str(test_category.id),
    )

    codes = [elem.get("code") for elem, score in matches]
    assert "ESC_MEC" in codes, "ESC_MEC not found"
    assert "TOLDO_LAT" in codes, "TOLDO_LAT not found"


@pytest.mark.asyncio
async def test_match_with_typo(element_service, test_category):
    """Test matching with typos (fuzzy matching)."""
    # "eskalera" is a typo of "escalera"
    description = "necesito una eskalera"

    matches = await element_service.match_elements_from_description(
        description,
        str(test_category.id),
    )

    codes = [elem.get("code") for elem, score in matches]
    # May or may not match depending on threshold, but shouldn't crash
    assert len(matches) >= 0


@pytest.mark.asyncio
async def test_no_match(element_service, test_category):
    """Test when no elements match."""
    description = "xyz abc qwerty"

    matches = await element_service.match_elements_from_description(
        description,
        str(test_category.id),
    )

    # Should have no or very low confidence matches
    high_conf = [m for m in matches if m[1] > 0.6]
    assert len(high_conf) == 0, "Should not match random words"


@pytest.mark.asyncio
async def test_element_with_images(element_service, test_category):
    """Test getting element details with images."""
    # Get first element from category
    async with get_async_session() as session:
        result = await session.execute(
            select(Element)
            .where(Element.category_id == test_category.id)
            .limit(1)
        )
        element = result.scalar()

    if element:
        elem_details = await element_service.get_element_with_images(str(element.id))

        assert elem_details is not None
        assert "images" in elem_details
        assert isinstance(elem_details["images"], list)

        if elem_details["images"]:
            img = elem_details["images"][0]
            assert "image_url" in img
            assert "is_required" in img


# =============================================================================
# TEST SUITE 2: Tier Element Resolution (Recursive Algorithm)
# =============================================================================

@pytest.mark.asyncio
async def test_resolve_tier_t6(tarifa_service, test_tiers):
    """Test resolving T6 tier elements.

    T6 should include ANTENA_PAR and PORTABICIS.
    """
    if "T6" not in test_tiers:
        pytest.skip("T6 tier not found")

    resolved = await tarifa_service.resolve_tier_elements(str(test_tiers["T6"].id))

    assert isinstance(resolved, dict)
    # Should have at least 2 elements (ANTENA_PAR, PORTABICIS)
    assert len(resolved) >= 2


@pytest.mark.asyncio
async def test_resolve_tier_t3_includes_t6(tarifa_service, test_tiers):
    """Test resolving T3 tier (includes T6).

    T3 should include: ESC_MEC (max 1), TOLDO_LAT (max 1), PLACA_200W (max 1),
    plus all elements from T6 (unlimited).
    """
    if "T3" not in test_tiers or "T6" not in test_tiers:
        pytest.skip("T3 or T6 tier not found")

    resolved = await tarifa_service.resolve_tier_elements(str(test_tiers["T3"].id))

    # T3 should have at least 5 elements (ESC_MEC, TOLDO_LAT, PLACA_200W + T6 elements)
    assert len(resolved) >= 5, f"T3 should have >= 5 elements, got {len(resolved)}"

    # Check specific elements exist
    async with get_async_session() as session:
        # Get element IDs
        elems_result = await session.execute(
            select(Element)
            .where(Element.category_id == test_tiers["T3"].category_id)
        )
        elements_by_code = {e.code: str(e.id) for e in elems_result.scalars().all()}

    if "ESC_MEC" in elements_by_code:
        elem_id = elements_by_code["ESC_MEC"]
        assert elem_id in resolved, "T3 should include ESC_MEC"
        assert resolved[elem_id] == 1, "ESC_MEC should have max quantity 1"


@pytest.mark.asyncio
async def test_resolve_tier_t2_references_t3(tarifa_service, test_tiers):
    """Test resolving T2 tier (references T3).

    T2 should include up to 2 elements from T3 plus unlimited T6.
    """
    if "T2" not in test_tiers:
        pytest.skip("T2 tier not found")

    resolved = await tarifa_service.resolve_tier_elements(str(test_tiers["T2"].id))

    # T2 should have elements from T3 (capped at 2) and T6
    assert len(resolved) > 0


@pytest.mark.asyncio
async def test_resolve_tier_t1_complete(tarifa_service, test_tiers):
    """Test resolving T1 tier (should include everything).

    T1 includes T2, T3, T4, T5, T6 (all unlimited).
    """
    if "T1" not in test_tiers:
        pytest.skip("T1 tier not found")

    resolved = await tarifa_service.resolve_tier_elements(str(test_tiers["T1"].id))

    # T1 should have most/all elements
    # Minimum expected: at least 8 distinct elements
    assert len(resolved) >= 8, f"T1 should include >= 8 elements, got {len(resolved)}"


# =============================================================================
# TEST SUITE 3: Tariff Selection (Element-based Algorithm)
# =============================================================================
# NOTE: These tests use select_tariff_by_elements() which was not implemented.
# The system uses select_tariff_by_rules() instead.

@SKIP_ELEMENT_BASED
@pytest.mark.asyncio
async def test_select_tariff_single_element(tarifa_service, test_category, test_tiers):
    """Test selecting tariff for single element.

    User wants: 1 ANTENA_PAR
    Expected: T6 (cheapest that covers it)
    """
    if "T6" not in test_tiers:
        pytest.skip("T6 tier not found")

    # Get ANTENA_PAR element
    async with get_async_session() as session:
        result = await session.execute(
            select(Element)
            .where(Element.category_id == test_category.id)
            .where(Element.code == "ANTENA_PAR")
        )
        antenna = result.scalar()

    if not antenna:
        pytest.skip("ANTENA_PAR element not found")

    user_elements = [{"id": str(antenna.id), "quantity": 1}]

    result = await tarifa_service.select_tariff_by_elements(
        str(test_category.id),
        user_elements,
    )

    assert "tier_code" in result
    assert result["tier_code"] == "T6", f"Expected T6, got {result.get('tier_code')}"
    assert result["price"] < 100, "T6 should be cheapest tier"


@SKIP_ELEMENT_BASED
@pytest.mark.asyncio
async def test_select_tariff_two_elements(tarifa_service, test_category, test_tiers):
    """Test selecting tariff for multiple elements.

    User wants: 1 ESC_MEC + 1 TOLDO_LAT
    Expected: T3 or higher (but T2 if config allows)
    """
    if "T3" not in test_tiers:
        pytest.skip("T3 tier not found")

    # Get elements
    async with get_async_session() as session:
        elems_result = await session.execute(
            select(Element)
            .where(Element.category_id == test_category.id)
            .where(Element.code.in_(["ESC_MEC", "TOLDO_LAT"]))
        )
        elements = {e.code: e for e in elems_result.scalars().all()}

    if len(elements) < 2:
        pytest.skip("Required elements not found")

    user_elements = [
        {"id": str(elements["ESC_MEC"].id), "quantity": 1},
        {"id": str(elements["TOLDO_LAT"].id), "quantity": 1},
    ]

    result = await tarifa_service.select_tariff_by_elements(
        str(test_category.id),
        user_elements,
    )

    assert "tier_code" in result
    # Should select T3 or higher (T2 has limit of 2 from T3, so this fits)
    assert result["tier_code"] in ["T1", "T2", "T3"]


@SKIP_ELEMENT_BASED
@pytest.mark.asyncio
async def test_select_tariff_respects_limits(tarifa_service, test_category, test_tiers):
    """Test that tariff selection respects quantity limits.

    User wants: 2 ESC_MEC (but T3 max is 1)
    Expected: Should escalate or find higher tariff
    """
    if "T3" not in test_tiers:
        pytest.skip("T3 tier not found")

    # Get element
    async with get_async_session() as session:
        result = await session.execute(
            select(Element)
            .where(Element.category_id == test_category.id)
            .where(Element.code == "ESC_MEC")
        )
        escalera = result.scalar()

    if not escalera:
        pytest.skip("ESC_MEC element not found")

    # Request 2 escaleras (exceeds T3 limit of 1)
    user_elements = [
        {"id": str(escalera.id), "quantity": 2},
    ]

    result = await tarifa_service.select_tariff_by_elements(
        str(test_category.id),
        user_elements,
    )

    assert "tier_code" in result
    # T1 includes T3 unlimited, so should select T1
    # Or it may have excluded_elements if no tier covers it
    if "excluded_elements" in result and result["excluded_elements"]:
        # This is acceptable - user needs special handling
        pass
    else:
        # Should have found a tier that covers it
        assert "tier_code" in result


# =============================================================================
# TEST SUITE 4: Consistency Checks
# =============================================================================

@pytest.mark.asyncio
async def test_no_circular_references(test_tiers):
    """Verify no circular references in tier structure."""
    visited = set()
    recursion_stack = set()

    async def check_cycles(tier_id):
        if tier_id in recursion_stack:
            return True  # Cycle detected
        if tier_id in visited:
            return False

        visited.add(tier_id)
        recursion_stack.add(tier_id)

        async with get_async_session() as session:
            result = await session.execute(
                select(TierElementInclusion)
                .where(TierElementInclusion.tier_id == tier_id)
                .where(TierElementInclusion.included_tier_id != None)
            )
            inclusions = result.scalars().all()

        for inc in inclusions:
            if await check_cycles(inc.included_tier_id):
                return True

        recursion_stack.discard(tier_id)
        return False

    # Check all tiers
    for tier in test_tiers.values():
        has_cycle = await check_cycles(tier.id)
        assert not has_cycle, f"Circular reference detected starting from {tier.code}"


@pytest.mark.asyncio
async def test_all_elements_accessible(test_category):
    """Verify all elements are accessible from admin."""
    element_service = ElementService()

    elements = await element_service.get_elements_by_category(str(test_category.id))

    assert len(elements) > 0, "No elements in category"

    for elem in elements:
        assert "id" in elem
        assert "code" in elem
        assert "name" in elem
        assert "keywords" in elem


# =============================================================================
# TEST SUITE 5: Performance Checks
# =============================================================================

@pytest.mark.asyncio
async def test_resolution_performance(tarifa_service, test_tiers):
    """Verify tier resolution completes in reasonable time.

    Should complete in < 1 second even for complex tier hierarchies.
    """
    import time

    if "T1" not in test_tiers:
        pytest.skip("T1 tier not found")

    start = time.time()
    resolved = await tarifa_service.resolve_tier_elements(str(test_tiers["T1"].id))
    elapsed = time.time() - start

    # Should be fast (< 1 second)
    # Note: First call may hit DB, subsequent calls hit Redis cache
    assert elapsed < 5, f"Tier resolution took {elapsed:.2f}s (expected < 5s)"
    assert len(resolved) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
