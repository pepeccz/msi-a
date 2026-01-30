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

### Backend (Python + pytest)

```
tests/
├── conftest.py                 # Shared fixtures
├── api/
│   ├── test_elements.py        # API endpoint tests
│   └── test_tarifa_service.py  # Service unit tests
├── agent/
│   ├── test_validation.py      # Input validation tests (NEW)
│   ├── test_element_tools_cache.py  # Cache tests (NEW)
│   └── test_agent_tools_integration.py
└── test_image_security.py      # Security tests
```

### Frontend (TypeScript + Jest + React Testing Library)

```
admin-panel/
├── jest.config.js              # Jest configuration
├── jest.setup.js               # Setup file (@testing-library/jest-dom)
├── src/
│   └── components/
│       └── tariffs/
│           ├── elements-tree-section.tsx
│           └── __tests__/
│               └── elements-tree-section.test.tsx
└── coverage/                   # Generated coverage reports
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

### Backend (pytest)

```bash
# Run all backend tests
pytest

# Run with coverage
pytest --cov=api --cov=agent --cov-report=term-missing

# Run specific file
pytest tests/agent/test_validation.py

# Run specific test
pytest tests/test_tarifa_service.py::TestTarifaService::test_calculate_tariff_single_element

# Run with verbose output
pytest -v

# Run async tests only
pytest -m asyncio

# Stop on first failure
pytest -x
```

### Frontend (Jest + React Testing Library)

```bash
# Run all frontend tests
cd admin-panel && npm test

# Watch mode (re-run on changes)
npm run test:watch

# Coverage report
npm run test:coverage

# Run specific test file
npm test -- elements-tree-section

# Update snapshots (if using)
npm test -- -u
```

### Using `/test` Command

The project includes a custom `/test` command that auto-detects backend vs frontend tests:

```bash
/test                          # Run all tests (backend + frontend)
/test backend                  # Run Python tests only
/test frontend                 # Run React/Next.js tests only
/test agent/test_validation.py # Run specific Python test
/test elements-tree-section    # Run specific React test
/test --coverage               # Run with coverage
```

## Frontend Test Example (React Testing Library)

```typescript
// admin-panel/src/components/tariffs/__tests__/elements-tree-section.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ElementsTreeSection } from "../elements-tree-section";

// Mock API client
jest.mock("@/lib/api", () => ({
  api: {
    get: jest.fn(),
  },
}));

import { api } from "@/lib/api";

describe("ElementsTreeSection", () => {
  beforeEach(() => {
    // Reset mocks before each test
    jest.clearAllMocks();
  });

  it("renders elements tree correctly", async () => {
    (api.get as jest.Mock).mockResolvedValue([
      { id: "1", code: "ESCAPE", name: "Escape", parent_id: null },
      { id: "2", code: "ESCAPE_DEPORTIVO", name: "Escape Deportivo", parent_id: "1" },
    ]);

    render(<ElementsTreeSection categoryId="motos-part" />);

    await waitFor(() => {
      expect(screen.getByText("ESCAPE")).toBeInTheDocument();
    });
    expect(screen.getByText("ESCAPE_DEPORTIVO")).toBeInTheDocument();
  });

  it("filters elements on search", async () => {
    (api.get as jest.Mock).mockResolvedValue([
      { id: "1", code: "ESCAPE", name: "Escape", parent_id: null },
      { id: "2", code: "SUSPENSION", name: "Suspensión", parent_id: null },
    ]);

    const user = userEvent.setup();
    render(<ElementsTreeSection categoryId="motos-part" />);

    await waitFor(() => screen.getByText("ESCAPE"));

    const searchInput = screen.getByPlaceholderText(/buscar/i);
    await user.type(searchInput, "escape");

    // After search, SUSPENSION should be filtered out
    await waitFor(() => {
      expect(screen.queryByText("SUSPENSION")).not.toBeInTheDocument();
    });
    expect(screen.getByText("ESCAPE")).toBeInTheDocument();
  });

  it("handles API errors gracefully", async () => {
    (api.get as jest.Mock).mockRejectedValue(new Error("Network error"));

    render(<ElementsTreeSection categoryId="motos-part" />);

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });
});
```

### Key Testing Patterns (Frontend)

- Use `waitFor()` for async rendering
- Use `userEvent` for interactions (NOT `fireEvent`)
- Mock API calls with `jest.mock()`
- Test accessibility with `getByRole()`, `getByLabelText()`
- Test user-facing behavior, not implementation details
- Reset mocks in `beforeEach()` to avoid test pollution

## Critical Rules

### Backend (pytest)
- ALWAYS use in-memory SQLite for unit tests
- ALWAYS use fixtures for database setup
- ALWAYS rollback after each test
- ALWAYS use `@pytest.mark.asyncio` for async tests
- ALWAYS mock external services (Chatwoot, Redis, LLM)
- ALWAYS test both success and error cases
- NEVER depend on production database
- PREFER parametrize for multiple similar test cases

### Frontend (Jest + RTL)
- ALWAYS use React Testing Library (NOT Enzyme)
- ALWAYS use `userEvent` for interactions (NOT `fireEvent`)
- ALWAYS mock API calls with `jest.mock()`
- ALWAYS reset mocks in `beforeEach()` to avoid pollution
- ALWAYS use `waitFor()` for async operations
- ALWAYS test accessibility (use `getByRole`, ARIA labels)
- NEVER test implementation details (state, props)
- PREFER testing user-facing behavior

## Resources

- [pytest-async skill](../pytest-async/SKILL.md) - Generic pytest patterns
- [msia-admin skill](../msia-admin/SKILL.md) - Admin panel patterns
