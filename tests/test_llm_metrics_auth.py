"""
Integration tests for /llm-metrics/summary authentication.

Verifies that the endpoint requires a valid JWT — unauthenticated requests
are rejected with 401.

Run with: pytest tests/test_llm_metrics_auth.py -v
"""

import pytest
from httpx import AsyncClient

from api.main import app


@pytest.fixture
async def client():
    """Async HTTP test client bound to the FastAPI app."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


# =============================================================================
# S3 — Integration tests
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_summary_without_auth_returns_401(client):
    """GET /llm-metrics/summary without any Authorization header must return 401."""
    response = await client.get("/llm-metrics/summary")
    assert response.status_code == 401, (
        f"Expected 401 Unauthorized but got {response.status_code}"
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_summary_with_invalid_token_returns_401(client):
    """GET /llm-metrics/summary with a malformed Bearer token must return 401."""
    response = await client.get(
        "/llm-metrics/summary",
        headers={"Authorization": "Bearer not-a-valid-jwt"},
    )
    assert response.status_code == 401, (
        f"Expected 401 Unauthorized but got {response.status_code}"
    )
