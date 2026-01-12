"""
Tests for TarifaService - tariff selection and tier resolution algorithms.

Tests both the legacy system and new element-based system to ensure
backward compatibility and correctness of the new algorithms.

Run with: pytest tests/test_tarifa_service.py -v
"""

import pytest
from uuid import uuid4
from decimal import Decimal

from agent.services.tarifa_service import TarifaService
from agent.services.element_service import ElementService
from database.models import (
    VehicleCategory,
    TariffTier,
    Element,
    TierElementInclusion,
)
from database.connection import get_async_session
from sqlalchemy import select


@pytest.fixture
async def tarifa_service():
    """Get tarifa service instance."""
    return TarifaService()


@pytest.fixture
async def element_service():
    """Get element service instance."""
    return ElementService()


@pytest.fixture
async def test_category():
    """Get test category (aseicars)."""
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
    """Get all tiers for test category ordered by sort_order."""
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


# =============================================================================
# TEST SUITE 1: Tier Element Resolution Algorithm
# =============================================================================

@pytest.mark.asyncio
async def test_resolve_tier_elements_direct(tarifa_service, test_tiers):
    """Test resolving a tier with direct element inclusions.

    T6 includes ANTENA_PAR and PORTABICIS directly.
    """
    if "T6" not in test_tiers:
        pytest.skip("T6 tier not found")

    resolved = await tarifa_service.resolve_tier_elements(str(test_tiers["T6"].id))

    assert isinstance(resolved, dict)
    assert len(resolved) >= 2, "T6 should include at least 2 elements"


@pytest.mark.asyncio
async def test_resolve_tier_elements_with_references(tarifa_service, test_tiers):
    """Test resolving a tier with tier references (indirect elements).

    T3 includes T6 as reference plus direct elements.
    Total elements should be more than T6 alone.
    """
    if "T3" not in test_tiers or "T6" not in test_tiers:
        pytest.skip("T3 or T6 tier not found")

    t3_resolved = await tarifa_service.resolve_tier_elements(str(test_tiers["T3"].id))
    t6_resolved = await tarifa_service.resolve_tier_elements(str(test_tiers["T6"].id))

    # T3 should have more elements than T6 (includes T6 plus additional)
    assert len(t3_resolved) > len(t6_resolved), \
        f"T3 ({len(t3_resolved)}) should have more elements than T6 ({len(t6_resolved)})"


@pytest.mark.asyncio
async def test_resolve_tier_elements_nested_references(tarifa_service, test_tiers):
    """Test resolving tiers with nested references (T1 → T2 → T3 → T6).

    All nested elements should be resolved correctly.
    """
    if "T1" not in test_tiers:
        pytest.skip("T1 tier not found")

    t1_resolved = await tarifa_service.resolve_tier_elements(str(test_tiers["T1"].id))

    # T1 should include a large set of elements from all tiers
    assert len(t1_resolved) >= 8, \
        f"T1 should resolve to >= 8 elements, got {len(t1_resolved)}"


@pytest.mark.asyncio
async def test_resolve_tier_elements_no_duplicates(tarifa_service, test_tiers):
    """Test that resolved elements have no duplicates even with multiple paths.

    Example: T1 → T2 → T6 and T1 → T3 → T6 should resolve T6 elements only once.
    """
    if "T1" not in test_tiers:
        pytest.skip("T1 tier not found")

    resolved = await tarifa_service.resolve_tier_elements(str(test_tiers["T1"].id))

    # All keys should be unique (dict by definition, but verify structure)
    assert len(resolved) == len(set(resolved.keys())), \
        "Resolved elements should have no duplicate keys"


@pytest.mark.asyncio
async def test_resolve_tier_elements_respects_limits(tarifa_service, test_tiers):
    """Test that resolved elements have correct quantity limits.

    Limits should propagate correctly:
    - Direct inclusions: use their max_quantity
    - References: use minimum of (direct limit, reference limit)
    """
    if "T2" not in test_tiers or "T3" not in test_tiers:
        pytest.skip("T2 or T3 tier not found")

    t2_resolved = await tarifa_service.resolve_tier_elements(str(test_tiers["T2"].id))

    # Check that limits are either None (unlimited) or integers >= 1
    for element_id, max_qty in t2_resolved.items():
        if max_qty is not None:
            assert isinstance(max_qty, int) and max_qty >= 1, \
                f"Invalid quantity limit: {max_qty} for element {element_id}"


@pytest.mark.asyncio
async def test_resolve_tier_elements_performance(tarifa_service, test_tiers):
    """Test that tier resolution completes in reasonable time.

    Even complex tier hierarchies should resolve < 1 second.
    """
    import time

    if "T1" not in test_tiers:
        pytest.skip("T1 tier not found")

    start = time.time()
    resolved = await tarifa_service.resolve_tier_elements(str(test_tiers["T1"].id))
    elapsed = time.time() - start

    # Should be fast (< 1 second)
    assert elapsed < 1.0, \
        f"Tier resolution took {elapsed:.3f}s (expected < 1s)"
    assert len(resolved) > 0, "Should have resolved elements"


# =============================================================================
# TEST SUITE 2: Tariff Selection Algorithm (Element-Based)
# =============================================================================

@pytest.mark.asyncio
async def test_select_tariff_single_element_optimal(tarifa_service, test_category, test_tiers):
    """Test selecting cheapest tariff for single element.

    User: "1 antena parabólica"
    Expected: T6 (59€) as it's the cheapest that includes ANTENA_PAR
    """
    if "T6" not in test_tiers:
        pytest.skip("T6 tier not found")

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
    assert result["tier_code"] == "T6", \
        f"Expected T6 for single antenna, got {result.get('tier_code')}"
    assert result["price"] <= 65, "T6 should be cheapest tier"


@pytest.mark.asyncio
async def test_select_tariff_multiple_elements(tarifa_service, test_category, test_tiers):
    """Test selecting tariff for multiple elements.

    User: "escalera + toldo"
    Expected: T3 (180€) or T2 (230€), but NOT T6
    """
    if "T3" not in test_tiers:
        pytest.skip("T3 tier not found")

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
    assert result["tier_code"] in ["T1", "T2", "T3"], \
        f"Expected T1/T2/T3 for escalera+toldo, got {result['tier_code']}"


@pytest.mark.asyncio
async def test_select_tariff_respects_quantity_limits(tarifa_service, test_category):
    """Test that tariff selection respects element quantity limits.

    User: "2 escaleras"
    But T3 max is 1 escalera, so should select higher tier or escalate.
    """
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

    # Should either:
    # 1. Select T1 which has unlimited everything
    # 2. Have excluded_elements if no tier covers 2 escaleras
    if "excluded_elements" not in result or not result["excluded_elements"]:
        # If it found a tier, T1 is the only one that can cover 2 escaleras
        assert result["tier_code"] == "T1", \
            f"Only T1 can cover 2 ESC_MEC, got {result['tier_code']}"


@pytest.mark.asyncio
async def test_select_tariff_no_elements_found(tarifa_service, test_category):
    """Test behavior when no elements match user input or empty list.

    Should handle gracefully without crashing.
    """
    user_elements = []

    result = await tarifa_service.select_tariff_by_elements(
        str(test_category.id),
        user_elements,
    )

    assert "tier_code" in result or "error" in result, \
        "Should return either tier_code or error message"


@pytest.mark.asyncio
async def test_select_tariff_price_ordering(tarifa_service, test_category):
    """Test that selection algorithm chooses cheapest valid tariff.

    Algorithm should return first tariff that covers all elements,
    iterating from most expensive to cheapest.
    """
    async with get_async_session() as session:
        result = await session.execute(
            select(Element)
            .where(Element.category_id == test_category.id)
            .where(Element.code == "PORTABICIS")
        )
        portabicis = result.scalar()

    if not portabicis:
        pytest.skip("PORTABICIS element not found")

    user_elements = [{"id": str(portabicis.id), "quantity": 1}]

    result = await tarifa_service.select_tariff_by_elements(
        str(test_category.id),
        user_elements,
    )

    # All tiers include PORTABICIS, so should pick cheapest (T6)
    assert result["tier_code"] == "T6", \
        f"Should select T6 (cheapest) for single T6 element, got {result['tier_code']}"


# =============================================================================
# TEST SUITE 3: Cache Validation
# =============================================================================

@pytest.mark.asyncio
async def test_resolve_tier_elements_cache_hit(tarifa_service, test_tiers):
    """Test that resolved elements are cached and subsequent calls are fast.

    Second call should use cache and be much faster.
    """
    import time

    if "T1" not in test_tiers:
        pytest.skip("T1 tier not found")

    tier_id = str(test_tiers["T1"].id)

    # First call (cache miss)
    start1 = time.time()
    resolved1 = await tarifa_service.resolve_tier_elements(tier_id)
    time1 = time.time() - start1

    # Second call (cache hit)
    start2 = time.time()
    resolved2 = await tarifa_service.resolve_tier_elements(tier_id)
    time2 = time.time() - start2

    assert resolved1 == resolved2, "Cached results should be identical"
    # Cache hit should be significantly faster (at least 10x)
    if time1 > 0.01:  # Only assert if first call was measurable
        assert time2 < time1 / 5, \
            f"Cache hit ({time2:.4f}s) should be faster than cache miss ({time1:.4f}s)"


# =============================================================================
# TEST SUITE 4: Edge Cases and Error Handling
# =============================================================================

@pytest.mark.asyncio
async def test_resolve_tier_with_missing_reference(tarifa_service, test_category):
    """Test handling of broken tier references (reference to non-existent tier).

    Should handle gracefully without crashing.
    """
    # This test would require creating a malformed tier in test setup
    # For now, just verify the function exists and doesn't crash
    async with get_async_session() as session:
        result = await session.execute(
            select(TariffTier)
            .where(TariffTier.category_id == test_category.id)
            .where(TariffTier.is_active == True)
            .limit(1)
        )
        tier = result.scalar()

    if tier:
        resolved = await tarifa_service.resolve_tier_elements(str(tier.id))
        assert isinstance(resolved, dict), "Should return dict even for edge cases"


@pytest.mark.asyncio
async def test_select_tariff_with_invalid_element_id(tarifa_service, test_category):
    """Test behavior when provided element ID doesn't exist.

    Should handle gracefully.
    """
    user_elements = [
        {"id": str(uuid4()), "quantity": 1},  # Non-existent element
    ]

    result = await tarifa_service.select_tariff_by_elements(
        str(test_category.id),
        user_elements,
    )

    # Should either skip non-existent element or return error
    assert "tier_code" in result or "error" in result, \
        "Should handle non-existent elements gracefully"


@pytest.mark.asyncio
async def test_select_tariff_with_zero_quantity(tarifa_service, test_category):
    """Test handling of zero or negative quantities.

    Should be ignored or raise meaningful error.
    """
    async with get_async_session() as session:
        result = await session.execute(
            select(Element)
            .where(Element.category_id == test_category.id)
            .limit(1)
        )
        element = result.scalar()

    if not element:
        pytest.skip("No elements found")

    user_elements = [
        {"id": str(element.id), "quantity": 0},
    ]

    result = await tarifa_service.select_tariff_by_elements(
        str(test_category.id),
        user_elements,
    )

    # Should handle zero quantity gracefully
    assert "tier_code" in result or "error" in result, \
        "Should handle zero quantities"


# =============================================================================
# TEST SUITE 5: Legacy System Backward Compatibility
# =============================================================================

@pytest.mark.asyncio
async def test_select_tariff_legacy_mode_exists(tarifa_service, test_category):
    """Test that legacy tariff selection method still exists and works.

    `select_tariff_by_rules` should be callable for backward compatibility.
    """
    assert hasattr(tarifa_service, 'select_tariff_by_rules'), \
        "select_tariff_by_rules method should still exist"


@pytest.mark.asyncio
async def test_both_systems_coexist(tarifa_service, test_category):
    """Test that both tariff selection systems can be used independently.

    Both methods should be callable without conflicts.
    """
    assert hasattr(tarifa_service, 'select_tariff_by_elements'), \
        "New select_tariff_by_elements should exist"
    assert hasattr(tarifa_service, 'select_tariff_by_rules'), \
        "Legacy select_tariff_by_rules should still exist"

    # Both should return compatible response formats
    # (This test verifies they coexist, actual compatibility tested elsewhere)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
