---
name: msia-test
description: >
  MSI-a testing patterns for API and agent.
  Trigger: When writing tests for MSI-a components.
metadata:
  author: msi-automotive
  version: "1.0"
  scope: [root, api, agent]
  auto_invoke: "Writing tests for MSI-a"
---

## Test Structure

```
tests/
├── conftest.py                 # Shared fixtures
├── test_api_elements.py        # API endpoint tests
├── test_tarifa_service.py      # Service unit tests
├── test_element_system.py      # Element matching tests
├── test_agent_tools_integration.py  # Agent tool tests
└── test_image_security.py      # Security tests
```

## conftest.py Pattern

```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from database.models import Base

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def engine():
    """Create test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest.fixture
async def session(engine):
    """Create test database session with rollback."""
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()

@pytest.fixture
async def sample_category(session):
    """Create a sample vehicle category."""
    from database.models import VehicleCategory
    
    category = VehicleCategory(
        slug="test-category-part",
        name="Test Category",
        client_type="particular",
    )
    session.add(category)
    await session.flush()
    return category

@pytest.fixture
async def sample_elements(session, sample_category):
    """Create sample elements."""
    from database.models import Element
    
    elements = [
        Element(
            category_id=sample_category.id,
            code="ELEM_1",
            name="Element 1",
            keywords=["element", "one"],
        ),
        Element(
            category_id=sample_category.id,
            code="ELEM_2",
            name="Element 2",
            keywords=["element", "two"],
        ),
    ]
    session.add_all(elements)
    await session.flush()
    return elements
```

## API Test Pattern

```python
import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app

@pytest.fixture
async def client():
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

@pytest.mark.asyncio
class TestElementsAPI:
    async def test_list_elements(self, client, sample_category, sample_elements):
        """Test listing elements for a category."""
        response = await client.get(
            f"/api/elements/category/{sample_category.id}"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["code"] == "ELEM_1"

    async def test_create_element(self, client, sample_category):
        """Test creating a new element."""
        response = await client.post(
            "/api/elements",
            json={
                "category_id": str(sample_category.id),
                "code": "NEW_ELEM",
                "name": "New Element",
                "keywords": ["new"],
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["code"] == "NEW_ELEM"

    async def test_create_element_duplicate_code_fails(
        self, client, sample_category, sample_elements
    ):
        """Test that duplicate codes are rejected."""
        response = await client.post(
            "/api/elements",
            json={
                "category_id": str(sample_category.id),
                "code": "ELEM_1",  # Already exists
                "name": "Duplicate",
                "keywords": [],
            }
        )
        assert response.status_code == 409
```

## Service Test Pattern

```python
import pytest
from agent.services.tarifa_service import TarifaService

@pytest.mark.asyncio
class TestTarifaService:
    async def test_calculate_tariff_single_element(
        self, session, sample_category, sample_elements, sample_tiers
    ):
        """Test tariff calculation with single element."""
        result = await TarifaService.calculate(
            session,
            category_slug="test-category-part",
            elements=["element one"],
            client_type="particular",
        )
        
        assert result.tier.code == "T3"
        assert len(result.matched_elements) == 1
        assert result.matched_elements[0].code == "ELEM_1"

    async def test_calculate_tariff_multiple_elements(
        self, session, sample_category, sample_elements, sample_tiers
    ):
        """Test tariff calculation with multiple elements."""
        result = await TarifaService.calculate(
            session,
            category_slug="test-category-part",
            elements=["element one", "element two"],
            client_type="particular",
        )
        
        assert result.tier.code == "T3"  # 1-2 elements
        assert len(result.matched_elements) == 2
```

## Element Matching Test Pattern

```python
import pytest
from agent.services.element_service import ElementService

@pytest.mark.asyncio
class TestElementMatching:
    @pytest.mark.parametrize("input_text,expected_code", [
        ("escalera", "ESC_MEC"),
        ("escalera mecánica", "ESC_MEC"),
        ("peldaños", "ESC_MEC"),
        ("toldo lateral", "TOLDO_LAT"),
        ("awning", "TOLDO_LAT"),
    ])
    async def test_match_element_by_keyword(
        self, session, sample_category, input_text, expected_code
    ):
        """Test element matching with various keywords."""
        result = await ElementService.match_element(
            session,
            category_id=sample_category.id,
            text=input_text,
        )
        
        assert result is not None
        assert result.code == expected_code

    async def test_no_match_returns_none(self, session, sample_category):
        """Test that unrecognized text returns None."""
        result = await ElementService.match_element(
            session,
            category_id=sample_category.id,
            text="something completely unrelated",
        )
        
        assert result is None
```

## Agent Tool Test Pattern

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
class TestAgentTools:
    async def test_calculate_tariff_tool(self, session):
        """Test the calculate_tariff tool."""
        from agent.tools.tarifa_tools import calculate_tariff
        
        with patch("agent.tools.tarifa_tools.get_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = session
            
            result = await calculate_tariff.ainvoke({
                "category_slug": "aseicars",
                "elements": ["escalera", "toldo"],
                "client_type": "particular",
            })
        
        assert "Tarifa:" in result
        assert "€" in result

    async def test_tool_handles_invalid_category(self, session):
        """Test tool behavior with invalid category."""
        from agent.tools.tarifa_tools import calculate_tariff
        
        with patch("agent.tools.tarifa_tools.get_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = session
            
            result = await calculate_tariff.ainvoke({
                "category_slug": "nonexistent",
                "elements": ["escalera"],
                "client_type": "particular",
            })
        
        assert "no encontrada" in result.lower()
```

## Mocking External Services

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_chatwoot_webhook_processing():
    """Test webhook processing with mocked Chatwoot."""
    with patch("shared.chatwoot_client.ChatwootClient") as MockClient:
        mock_client = MockClient.return_value
        mock_client.send_message = AsyncMock(return_value={"id": 123})
        
        # Test your code that uses ChatwootClient
        result = await process_and_respond(...)
        
        mock_client.send_message.assert_called_once()
```

## Commands

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=api --cov=agent

# Run specific file
pytest tests/test_tarifa_service.py

# Run specific test
pytest tests/test_tarifa_service.py::TestTarifaService::test_calculate_tariff_single_element

# Run with verbose output
pytest -v

# Run async tests only
pytest -m asyncio

# Stop on first failure
pytest -x
```

## Critical Rules

- ALWAYS use in-memory SQLite for unit tests
- ALWAYS use fixtures for database setup
- ALWAYS rollback after each test
- ALWAYS use `@pytest.mark.asyncio` for async tests
- ALWAYS mock external services (Chatwoot, Redis, LLM)
- ALWAYS test both success and error cases
- NEVER depend on production database
- PREFER parametrize for multiple similar test cases

## Resources

- [pytest-async skill](../pytest-async/SKILL.md) - Generic pytest patterns
