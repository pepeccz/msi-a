---
name: tdd-workflow
description: >
  Test-Driven Development methodology for MSI-a.
  Trigger: When implementing new features or fixing bugs with tests.
metadata:
  author: msi-automotive
  version: "1.0"
  scope: [api, agent, admin-panel]
  auto_invoke: "Implementing features with TDD"
---

## Overview

Test-Driven Development (TDD) methodology for MSI-a, emphasizing the Red-Green-Refactor cycle.

## The TDD Cycle

```
┌───────────────────────────────────────────────────────────┐
│                                                           │
│    ┌─────────┐      ┌─────────┐      ┌──────────┐        │
│    │   RED   │─────▶│  GREEN  │─────▶│ REFACTOR │        │
│    │  Write  │      │  Make   │      │  Clean   │        │
│    │  Test   │      │  Pass   │      │   Up     │        │
│    └─────────┘      └─────────┘      └────┬─────┘        │
│         ▲                                  │              │
│         └──────────────────────────────────┘              │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

### 1. RED: Write a Failing Test

```python
# Write the test FIRST
@pytest.mark.asyncio
async def test_calculate_tariff_returns_total():
    # Arrange
    service = TariffService()
    
    # Act - This will fail because method doesn't exist yet
    result = await service.calculate(category_id=1, elements=[])
    
    # Assert
    assert result.total >= 0
    assert result.currency == "EUR"
```

**Run the test - it MUST fail.**

### 2. GREEN: Write Minimal Code to Pass

```python
# Write the MINIMUM code to make the test pass
class TariffService:
    async def calculate(self, category_id: int, elements: list) -> TariffResult:
        return TariffResult(total=0, currency="EUR")
```

**Run the test - it should pass.**

### 3. REFACTOR: Improve the Code

```python
# Now improve while keeping tests green
class TariffService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def calculate(self, category_id: int, elements: list) -> TariffResult:
        category = await self._get_category(category_id)
        total = await self._calculate_total(category, elements)
        return TariffResult(total=total, currency="EUR")
```

**Run the test - it should still pass.**

## Python Testing Patterns

### Async Tests with pytest

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_async_function():
    result = await my_async_function()
    assert result is not None
```

### Fixtures

```python
# conftest.py
@pytest.fixture
async def db_session():
    """Async database session for tests."""
    async with async_session_maker() as session:
        yield session
        await session.rollback()

@pytest.fixture
def sample_tariff():
    """Sample tariff for testing."""
    return Tariff(id=1, name="Test", price=Decimal("100.00"))
```

### Mocking External Services

```python
@patch("agent.services.chatwoot.send_message", new_callable=AsyncMock)
async def test_sends_notification(mock_send):
    mock_send.return_value = {"id": 123}
    
    await notify_user(user_id=1, message="Test")
    
    mock_send.assert_called_once_with(
        conversation_id=1,
        message="Test"
    )
```

### Parametrized Tests

```python
@pytest.mark.parametrize("input_value,expected", [
    ("1234ABC", True),   # Valid plate
    ("ABC1234", False),  # Invalid format
    ("", False),         # Empty
    (None, False),       # None
])
async def test_validate_plate(input_value, expected):
    result = validate_plate(input_value)
    assert result == expected
```

## Test Organization

```
api/tests/
├── conftest.py              # Shared fixtures
├── test_routes/
│   ├── test_tariffs.py      # Route tests
│   └── test_auth.py
├── test_services/
│   ├── test_tariff_service.py
│   └── test_auth_service.py
└── test_integration/
    └── test_full_flow.py

agent/tests/
├── conftest.py
├── test_nodes/
│   └── test_process_message.py
├── test_tools/
│   └── test_tariff_tools.py
└── test_graphs/
    └── test_conversation_graph.py
```

## What to Test

### Unit Tests

- Pure functions
- Business logic
- Validation rules
- Data transformations

### Integration Tests

- Database operations
- API endpoints
- Service interactions

### Edge Cases

- Empty inputs
- Null/None values
- Boundary conditions
- Error scenarios

## Test Coverage Goals

| Type | Minimum | Target |
|------|---------|--------|
| Unit | 70% | 85% |
| Integration | 50% | 70% |
| Critical paths | 100% | 100% |

## TDD Anti-Patterns

### Don't Do These

1. **Writing tests after code** - Defeats the purpose
2. **Testing implementation details** - Test behavior instead
3. **Over-mocking** - Test real interactions when possible
4. **Skipping refactor step** - Technical debt accumulates
5. **Large test steps** - Keep cycles small

### Do These Instead

1. Write one test at a time
2. Make it fail first
3. Write minimal code to pass
4. Refactor with confidence
5. Repeat

## Related Skills

- `pytest-async` - Detailed pytest patterns
- `msia-test` - MSI-a specific test conventions
