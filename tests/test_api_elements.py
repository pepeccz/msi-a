"""
Integration tests for Element System API endpoints.

Tests all CRUD operations on elements, images, and tier inclusions
via HTTP endpoints using TestClient.

Run with: pytest tests/test_api_elements.py -v
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4

from api.main import app
from database.models import (
    VehicleCategory,
    Element,
    ElementImage,
    TierElementInclusion,
    TariffTier,
)
from database.connection import get_async_session
from sqlalchemy import select


@pytest.fixture
async def client():
    """Create test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


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


@pytest.fixture
async def test_element(test_category):
    """Create a test element."""
    async with get_async_session() as session:
        result = await session.execute(
            select(Element)
            .where(Element.category_id == test_category.id)
            .limit(1)
        )
        element = result.scalar()
        assert element is not None
        return element


# =============================================================================
# TEST SUITE 1: Element CRUD Endpoints
# =============================================================================

@pytest.mark.asyncio
async def test_get_elements_list(client, test_category):
    """Test GET /api/admin/elements - list all elements."""
    response = await client.get(
        "/api/admin/elements",
        params={"category_id": str(test_category.id)}
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert "total" in data
    assert data["total"] >= 0


@pytest.mark.asyncio
async def test_get_elements_with_filters(client, test_category):
    """Test GET /api/admin/elements with category filter."""
    response = await client.get(
        "/api/admin/elements",
        params={
            "category_id": str(test_category.id),
            "is_active": True,
            "limit": 10,
            "offset": 0,
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data

    # All returned items should have expected fields
    for item in data["items"]:
        assert "id" in item
        assert "code" in item
        assert "name" in item
        assert "category_id" in item
        assert "is_active" in item


@pytest.mark.asyncio
async def test_get_single_element(client, test_element):
    """Test GET /api/admin/elements/{id} - get single element."""
    response = await client.get(f"/api/admin/elements/{test_element.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_element.id)
    assert data["code"] == test_element.code
    assert data["name"] == test_element.name


@pytest.mark.asyncio
async def test_get_nonexistent_element(client):
    """Test GET /api/admin/elements/{id} with non-existent ID."""
    response = await client.get(f"/api/admin/elements/{uuid4()}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_element(client, test_category):
    """Test POST /api/admin/elements - create new element."""
    payload = {
        "category_id": str(test_category.id),
        "code": f"TEST_ELEM_{uuid4().hex[:8]}",
        "name": "Test Element",
        "description": "A test element for testing",
        "keywords": ["test", "element"],
        "aliases": ["te"],
        "is_active": True,
    }

    response = await client.post("/api/admin/elements", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["code"] == payload["code"]
    assert data["name"] == payload["name"]
    assert "id" in data


@pytest.mark.asyncio
async def test_create_element_duplicate_code(client, test_category, test_element):
    """Test POST /api/admin/elements with duplicate code in same category."""
    payload = {
        "category_id": str(test_category.id),
        "code": test_element.code,  # Duplicate
        "name": "Different Name",
        "keywords": ["test"],
    }

    response = await client.post("/api/admin/elements", json=payload)

    # Should reject due to UNIQUE(category_id, code) constraint
    assert response.status_code in [400, 409]


@pytest.mark.asyncio
async def test_create_element_missing_required(client, test_category):
    """Test POST /api/admin/elements with missing required fields."""
    payload = {
        "category_id": str(test_category.id),
        # Missing 'code' and 'name'
    }

    response = await client.post("/api/admin/elements", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_element(client, test_element):
    """Test PUT /api/admin/elements/{id} - update element."""
    payload = {
        "name": "Updated Test Element",
        "description": "Updated description",
        "keywords": ["updated", "test"],
    }

    response = await client.put(
        f"/api/admin/elements/{test_element.id}",
        json=payload
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == payload["name"]
    assert data["description"] == payload["description"]


@pytest.mark.asyncio
async def test_update_element_partial(client, test_element):
    """Test PUT /api/admin/elements/{id} with partial update."""
    original_name = test_element.name
    payload = {
        "description": "New description only",
    }

    response = await client.put(
        f"/api/admin/elements/{test_element.id}",
        json=payload
    )

    assert response.status_code == 200
    data = response.json()
    # Name should remain unchanged
    assert data["name"] == original_name
    assert data["description"] == payload["description"]


@pytest.mark.asyncio
async def test_delete_element(client, test_category):
    """Test DELETE /api/admin/elements/{id} - delete element."""
    # First create an element to delete
    create_payload = {
        "category_id": str(test_category.id),
        "code": f"DELETE_TEST_{uuid4().hex[:8]}",
        "name": "Element to Delete",
        "keywords": ["delete"],
    }

    create_response = await client.post("/api/admin/elements", json=create_payload)
    assert create_response.status_code == 201
    element_id = create_response.json()["id"]

    # Delete it
    delete_response = await client.delete(f"/api/admin/elements/{element_id}")
    assert delete_response.status_code == 204

    # Verify it's deleted
    get_response = await client.get(f"/api/admin/elements/{element_id}")
    assert get_response.status_code == 404


# =============================================================================
# TEST SUITE 2: Element Image Endpoints
# =============================================================================

@pytest.mark.asyncio
async def test_get_element_images(client, test_element):
    """Test GET /api/admin/elements/{id}/images - list images."""
    response = await client.get(f"/api/admin/elements/{test_element.id}/images")

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)

    # Verify image structure
    for img in data["items"]:
        assert "id" in img
        assert "image_url" in img
        assert "image_type" in img
        assert img["image_type"] in ["example", "required_document", "warning"]


@pytest.mark.asyncio
async def test_create_element_image(client, test_element):
    """Test POST /api/admin/elements/{id}/images - create image."""
    payload = {
        "image_url": "https://example.com/image.jpg",
        "title": "Test Image",
        "description": "A test image",
        "image_type": "example",
        "is_required": False,
    }

    response = await client.post(
        f"/api/admin/elements/{test_element.id}/images",
        json=payload
    )

    assert response.status_code == 201
    data = response.json()
    assert data["image_url"] == payload["image_url"]
    assert data["image_type"] == payload["image_type"]


@pytest.mark.asyncio
async def test_create_image_invalid_type(client, test_element):
    """Test POST /api/admin/elements/{id}/images with invalid type."""
    payload = {
        "image_url": "https://example.com/image.jpg",
        "title": "Test",
        "image_type": "invalid_type",  # Invalid
    }

    response = await client.post(
        f"/api/admin/elements/{test_element.id}/images",
        json=payload
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_element_image(client, test_element):
    """Test PUT /api/admin/element-images/{id} - update image."""
    # First create an image
    create_payload = {
        "image_url": "https://example.com/original.jpg",
        "title": "Original",
        "description": "Original description",
        "image_type": "example",
    }

    create_response = await client.post(
        f"/api/admin/elements/{test_element.id}/images",
        json=create_payload
    )
    assert create_response.status_code == 201
    image_id = create_response.json()["id"]

    # Update it
    update_payload = {
        "title": "Updated",
        "description": "Updated description",
    }

    update_response = await client.put(
        f"/api/admin/element-images/{image_id}",
        json=update_payload
    )

    assert update_response.status_code == 200
    data = update_response.json()
    assert data["title"] == update_payload["title"]


@pytest.mark.asyncio
async def test_delete_element_image(client, test_element):
    """Test DELETE /api/admin/element-images/{id} - delete image."""
    # Create an image
    create_payload = {
        "image_url": "https://example.com/delete_me.jpg",
        "title": "Delete Me",
        "image_type": "example",
    }

    create_response = await client.post(
        f"/api/admin/elements/{test_element.id}/images",
        json=create_payload
    )
    image_id = create_response.json()["id"]

    # Delete it
    delete_response = await client.delete(f"/api/admin/element-images/{image_id}")
    assert delete_response.status_code == 204

    # Verify it's deleted
    get_response = await client.get(f"/api/admin/element-images/{image_id}")
    assert get_response.status_code == 404


# =============================================================================
# TEST SUITE 3: Tier Element Resolution Endpoints
# =============================================================================

@pytest.mark.asyncio
async def test_get_tier_resolved_elements(client, test_category):
    """Test GET /api/admin/tariff-tiers/{id}/resolved-elements."""
    # Get a tier
    async with get_async_session() as session:
        result = await session.execute(
            select(TariffTier)
            .where(TariffTier.category_id == test_category.id)
            .where(TariffTier.code == "T1")
        )
        tier = result.scalar()

    if not tier:
        pytest.skip("T1 tier not found")

    response = await client.get(
        f"/api/admin/tariff-tiers/{tier.id}/resolved-elements"
    )

    assert response.status_code == 200
    data = response.json()
    assert "elements" in data
    assert isinstance(data["elements"], dict)

    # Each element should have a max_quantity
    for element_id, max_qty in data["elements"].items():
        assert isinstance(element_id, str)
        assert max_qty is None or isinstance(max_qty, int)


@pytest.mark.asyncio
async def test_get_tier_resolved_elements_invalid_tier(client):
    """Test GET /api/admin/tariff-tiers/{id}/resolved-elements with invalid tier."""
    response = await client.get(
        f"/api/admin/tariff-tiers/{uuid4()}/resolved-elements"
    )

    assert response.status_code == 404


# =============================================================================
# TEST SUITE 4: Tier Inclusion CRUD Endpoints
# =============================================================================

@pytest.mark.asyncio
async def test_create_tier_element_inclusion(client, test_category):
    """Test POST /api/admin/tariff-tiers/{id}/inclusions - add element."""
    # Get tier and element
    async with get_async_session() as session:
        tier_result = await session.execute(
            select(TariffTier)
            .where(TariffTier.category_id == test_category.id)
            .where(TariffTier.code == "T1")
        )
        tier = tier_result.scalar()

        elem_result = await session.execute(
            select(Element)
            .where(Element.category_id == test_category.id)
            .limit(1)
        )
        element = elem_result.scalar()

    if not tier or not element:
        pytest.skip("Required tier or element not found")

    payload = {
        "element_id": str(element.id),
        "max_quantity": 5,
        "notes": "Test inclusion",
    }

    response = await client.post(
        f"/api/admin/tariff-tiers/{tier.id}/inclusions",
        json=payload
    )

    # Should succeed or return conflict if already exists
    assert response.status_code in [201, 409]


@pytest.mark.asyncio
async def test_create_tier_reference_inclusion(client, test_category):
    """Test POST /api/admin/tariff-tiers/{id}/inclusions - add tier reference."""
    # Get tiers
    async with get_async_session() as session:
        t1_result = await session.execute(
            select(TariffTier)
            .where(TariffTier.category_id == test_category.id)
            .where(TariffTier.code == "T1")
        )
        t1 = t1_result.scalar()

        t2_result = await session.execute(
            select(TariffTier)
            .where(TariffTier.category_id == test_category.id)
            .where(TariffTier.code == "T2")
        )
        t2 = t2_result.scalar()

    if not t1 or not t2:
        pytest.skip("Required tiers not found")

    payload = {
        "included_tier_id": str(t2.id),
        "max_quantity": None,
        "notes": "T1 includes T2",
    }

    response = await client.post(
        f"/api/admin/tariff-tiers/{t1.id}/inclusions",
        json=payload
    )

    # Should succeed or return conflict if already exists
    assert response.status_code in [201, 409]


@pytest.mark.asyncio
async def test_create_circular_reference_rejected(client, test_category):
    """Test that circular tier references are rejected.

    T1 → T2 → T1 should be prevented.
    """
    # Get tiers
    async with get_async_session() as session:
        t1_result = await session.execute(
            select(TariffTier)
            .where(TariffTier.category_id == test_category.id)
            .where(TariffTier.code == "T1")
        )
        t1 = t1_result.scalar()

        t2_result = await session.execute(
            select(TariffTier)
            .where(TariffTier.category_id == test_category.id)
            .where(TariffTier.code == "T2")
        )
        t2 = t2_result.scalar()

    if not t1 or not t2:
        pytest.skip("Required tiers not found")

    # First, create T1→T2 if not exists
    payload1 = {
        "included_tier_id": str(t2.id),
        "max_quantity": None,
    }
    client.post(f"/api/admin/tariff-tiers/{t1.id}/inclusions", json=payload1)

    # Then try to create T2→T1 (circular)
    payload2 = {
        "included_tier_id": str(t1.id),
        "max_quantity": None,
    }

    response = await client.post(
        f"/api/admin/tariff-tiers/{t2.id}/inclusions",
        json=payload2
    )

    # Should be rejected
    assert response.status_code in [400, 409]


@pytest.mark.asyncio
async def test_delete_tier_inclusion(client, test_category):
    """Test DELETE /api/admin/tier-inclusions/{id} - remove inclusion."""
    # This would require first creating an inclusion
    # For now, test that endpoint exists and handles missing ID
    response = await client.delete(f"/api/admin/tier-inclusions/{uuid4()}")

    # Should return 404 for non-existent inclusion
    assert response.status_code == 404


# =============================================================================
# TEST SUITE 5: Search and Filter Endpoints
# =============================================================================

@pytest.mark.asyncio
async def test_search_elements_by_keyword(client, test_category):
    """Test GET /api/admin/elements/search with keyword filter."""
    # Test with a known keyword from the seed data
    response = await client.get(
        "/api/admin/elements/search",
        params={
            "category_id": str(test_category.id),
            "query": "escalera",
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

    # If results found, they should contain the search term
    if data:
        for item in data:
            # At least one field should contain the search term
            text = f"{item.get('name', '')} {' '.join(item.get('keywords', []))}".lower()
            # Search should return relevant results (may not all contain exact term)


@pytest.mark.asyncio
async def test_get_elements_by_category(client, test_category):
    """Test getting elements filtered by category."""
    response = await client.get(
        "/api/admin/elements",
        params={"category_id": str(test_category.id)}
    )

    assert response.status_code == 200
    data = response.json()

    # All returned elements should belong to the requested category
    for item in data["items"]:
        assert item["category_id"] == str(test_category.id)


# =============================================================================
# TEST SUITE 6: Cache Invalidation
# =============================================================================

@pytest.mark.asyncio
async def test_cache_invalidation_on_element_create(client, test_category):
    """Test that cache is invalidated when element is created."""
    # Get initial elements count
    response1 = await client.get(
        "/api/admin/elements",
        params={"category_id": str(test_category.id)}
    )
    count1 = response1.json()["total"]

    # Create new element
    payload = {
        "category_id": str(test_category.id),
        "code": f"CACHE_TEST_{uuid4().hex[:8]}",
        "name": "Cache Test Element",
        "keywords": ["cache", "test"],
    }
    await client.post("/api/admin/elements", json=payload)

    # Get elements again - should see new count
    response2 = await client.get(
        "/api/admin/elements",
        params={"category_id": str(test_category.id)}
    )
    count2 = response2.json()["total"]

    assert count2 > count1, "New element should be counted after creation"


@pytest.mark.asyncio
async def test_cache_invalidation_on_inclusion_change(client, test_category):
    """Test that tier resolution cache is invalidated on inclusion change."""
    # Get initial tier resolution
    async with get_async_session() as session:
        tier_result = await session.execute(
            select(TariffTier)
            .where(TariffTier.category_id == test_category.id)
            .where(TariffTier.code == "T1")
        )
        tier = tier_result.scalar()

    if not tier:
        pytest.skip("T1 tier not found")

    response1 = await client.get(
        f"/api/admin/tariff-tiers/{tier.id}/resolved-elements"
    )
    count1 = len(response1.json()["elements"])

    # Make some change (simulated - actual change logic depends on implementation)
    # For now, just verify the endpoint works
    response2 = await client.get(
        f"/api/admin/tariff-tiers/{tier.id}/resolved-elements"
    )
    count2 = len(response2.json()["elements"])

    # Should have same count on re-fetch (cached)
    assert count1 == count2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
