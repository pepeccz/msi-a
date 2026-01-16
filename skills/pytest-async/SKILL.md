---
name: pytest-async
description: >
  Pytest patterns for async Python testing.
  Trigger: When writing tests with pytest, especially async tests, fixtures, mocking, or parametrize.
metadata:
  author: msi-automotive
  version: "1.0"
  scope: [root, api, agent]
  auto_invoke: "Writing Python tests"
---

## Basic Test Structure

```python
import pytest

class TestUserService:
    def test_create_user_success(self):
        user = create_user(name="John", email="john@test.com")
        assert user.name == "John"
        assert user.email == "john@test.com"

    def test_create_user_invalid_email_fails(self):
        with pytest.raises(ValueError, match="Invalid email"):
            create_user(name="John", email="invalid")
```

## Async Tests

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    result = await fetch_data()
    assert result is not None

@pytest.mark.asyncio
async def test_async_with_db(session):
    user = await UserService.create(session, name="Test")
    assert user.id is not None
```

## Fixtures

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Basic fixture
@pytest.fixture
def user():
    return User(name="Test User", email="test@example.com")

# Async fixture
@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()

# Fixture with teardown
@pytest.fixture
async def temp_file():
    path = Path("/tmp/test_file.txt")
    path.write_text("test content")
    yield path
    path.unlink()

# Fixture scopes
@pytest.fixture(scope="module")   # Once per module
@pytest.fixture(scope="class")    # Once per class
@pytest.fixture(scope="session")  # Once per test session
```

## conftest.py

```python
# tests/conftest.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

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
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest.fixture
async def session(engine):
    """Create test database session."""
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()
```

## Mocking

```python
from unittest.mock import patch, MagicMock, AsyncMock

# Sync mock
def test_with_sync_mock():
    with patch("module.function") as mock_func:
        mock_func.return_value = "mocked"
        result = call_function()
        assert result == "mocked"
        mock_func.assert_called_once()

# Async mock
@pytest.mark.asyncio
async def test_with_async_mock():
    with patch("module.async_function", new_callable=AsyncMock) as mock_func:
        mock_func.return_value = "mocked"
        result = await call_async_function()
        assert result == "mocked"

# Mock object attributes
def test_with_mock_object():
    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.name = "Test"
    mock_user.is_active = True
    
    result = process_user(mock_user)
    assert result["name"] == "Test"

# Mock context manager
@pytest.mark.asyncio
async def test_mock_context_manager():
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    
    async with mock_session as session:
        pass
```

## Parametrize

```python
@pytest.mark.parametrize("input,expected", [
    ("hello", "HELLO"),
    ("world", "WORLD"),
    ("pytest", "PYTEST"),
])
def test_uppercase(input, expected):
    assert input.upper() == expected

@pytest.mark.parametrize("email,is_valid", [
    ("user@example.com", True),
    ("invalid-email", False),
    ("", False),
    ("user@.com", False),
])
def test_email_validation(email, is_valid):
    assert validate_email(email) == is_valid

# Multiple parameters
@pytest.mark.parametrize("a,b,expected", [
    (1, 2, 3),
    (0, 0, 0),
    (-1, 1, 0),
])
def test_add(a, b, expected):
    assert add(a, b) == expected
```

## Markers

```python
# pyproject.toml
[tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow",
    "integration: marks integration tests",
]
asyncio_mode = "auto"

# Usage
@pytest.mark.slow
def test_large_data_processing():
    ...

@pytest.mark.integration
async def test_database_connection():
    ...

@pytest.mark.skip(reason="Not implemented yet")
def test_future_feature():
    ...

@pytest.mark.skipif(sys.platform == "win32", reason="Unix only")
def test_unix_specific():
    ...
```

## Testing FastAPI

```python
import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

@pytest.mark.asyncio
async def test_list_users(client):
    response = await client.get("/api/users")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

@pytest.mark.asyncio
async def test_create_user(client):
    response = await client.post(
        "/api/users",
        json={"name": "Test", "email": "test@example.com"}
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Test"
```

## Commands

```bash
pytest                          # Run all tests
pytest -v                       # Verbose output
pytest -x                       # Stop on first failure
pytest -k "test_user"           # Filter by name
pytest -m "not slow"            # Filter by marker
pytest --cov=src                # With coverage
pytest -n auto                  # Parallel (pytest-xdist)
pytest --tb=short               # Short traceback
pytest tests/test_api.py        # Run specific file
pytest tests/test_api.py::test_create_user  # Run specific test
```

## Critical Rules

- ALWAYS use `@pytest.mark.asyncio` for async tests
- ALWAYS use `AsyncMock` for mocking async functions
- ALWAYS use fixtures for shared setup
- ALWAYS clean up resources in fixtures (yield + cleanup)
- NEVER share state between tests
- ALWAYS use `scope="session"` for expensive fixtures
- PREFER parametrize over multiple similar tests
