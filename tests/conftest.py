"""
Pytest configuration and shared fixtures for all tests.

This file is automatically loaded by pytest and provides:
- Database session fixtures
- Test client fixtures
- Category and tier fixtures
- Async test support
"""

import pytest
import asyncio
from typing import AsyncGenerator

from database.connection import get_async_session
from database.models import Base, VehicleCategory, TariffTier
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


# =============================================================================
# ASYNC TEST SUPPORT
# =============================================================================

def pytest_collection_modifyitems(items):
    """Mark all async tests with pytest.mark.asyncio."""
    for item in items:
        if asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)


# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

@pytest.fixture(scope="session")
def setup_logging():
    """Configure logging for tests."""
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Reduce noise from third-party loggers
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


# =============================================================================
# DATABASE FIXTURES
# =============================================================================

@pytest.fixture(scope="session")
async def db_engine():
    """Create test database engine."""
    from shared.config import get_settings

    settings = get_settings()

    # Use test database URL if configured, otherwise use test suffix
    test_db_url = settings.DATABASE_URL.replace(
        "msia_db", "msia_db_test"
    )

    engine = create_async_engine(
        test_db_url,
        echo=False,
        pool_pre_ping=True,
    )

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a test database session."""
    TestingSessionLocal = sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with TestingSessionLocal() as session:
        yield session


# =============================================================================
# TEST DATA FIXTURES
# =============================================================================

@pytest.fixture(scope="session")
async def test_category_setup(db_engine):
    """Create test category for all tests to use."""
    TestingSessionLocal = sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with TestingSessionLocal() as session:
        from database.models import VehicleCategory

        # Check if category exists
        from sqlalchemy import select
        result = await session.execute(
            select(VehicleCategory).where(VehicleCategory.slug == "aseicars")
        )
        category = result.scalar()

        if not category:
            # Create test category
            category = VehicleCategory(
                name="Autocaravanas (32xx, 33xx)",
                slug="aseicars",
                description="Professional motorhome homologation",
                is_active=True,
                sort_order=1,
            )
            session.add(category)
            await session.commit()

        return category


@pytest.fixture(scope="session")
async def test_tiers_setup(test_category_setup, db_engine):
    """Create test tiers for category."""
    TestingSessionLocal = sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with TestingSessionLocal() as session:
        from database.models import TariffTier
        from sqlalchemy import select

        category = test_category_setup

        # Check if tiers already exist
        result = await session.execute(
            select(TariffTier)
            .where(TariffTier.category_id == category.id)
            .limit(1)
        )
        existing = result.scalar()

        if existing:
            # Tiers already created
            result = await session.execute(
                select(TariffTier)
                .where(TariffTier.category_id == category.id)
                .order_by(TariffTier.sort_order)
            )
            return {t.code: t for t in result.scalars().all()}

        # Create tiers according to PDF
        tiers_data = [
            {"code": "T1", "name": "Proyecto Completo", "price": 270.00, "sort_order": 1},
            {"code": "T2", "name": "Proyecto Ampliado", "price": 230.00, "sort_order": 2},
            {"code": "T3", "name": "Proyecto Básico", "price": 180.00, "sort_order": 3},
            {"code": "T4", "name": "Proyecto Reducido", "price": 135.00, "sort_order": 4},
            {"code": "T5", "name": "Mínimo con Elementos", "price": 65.00, "sort_order": 5},
            {"code": "T6", "name": "Sin Proyecto", "price": 59.00, "sort_order": 6},
        ]

        tiers = {}
        for tier_data in tiers_data:
            tier = TariffTier(
                category_id=category.id,
                code=tier_data["code"],
                name=tier_data["name"],
                description=f"Tier {tier_data['code']}",
                price=tier_data["price"],
                is_active=True,
                sort_order=tier_data["sort_order"],
            )
            session.add(tier)
            tiers[tier_data["code"]] = tier

        await session.commit()
        return tiers


# =============================================================================
# PYTEST CONFIGURATION
# =============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def setup_test_env(setup_logging):
    """Setup test environment."""
    import os

    # Ensure test environment variables are set
    os.environ.setdefault("ENVIRONMENT", "test")
    os.environ.setdefault("LOG_LEVEL", "INFO")

    yield


# =============================================================================
# MOCK FIXTURES
# =============================================================================

@pytest.fixture
def mock_redis():
    """Provide mock Redis client for tests."""
    from unittest.mock import AsyncMock, MagicMock

    redis_mock = MagicMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.setex = AsyncMock(return_value=True)

    return redis_mock


@pytest.fixture
def mock_llm():
    """Provide mock LLM for tests."""
    from unittest.mock import AsyncMock

    llm_mock = AsyncMock()
    llm_mock.return_value = "Test LLM response"

    return llm_mock


@pytest.fixture
def mock_chatwoot():
    """Provide mock Chatwoot client for tests."""
    from unittest.mock import AsyncMock

    chatwoot_mock = AsyncMock()
    chatwoot_mock.send_message = AsyncMock(return_value={"id": 123})
    chatwoot_mock.update_conversation = AsyncMock(return_value=True)

    return chatwoot_mock


# =============================================================================
# UTILITY FIXTURES
# =============================================================================

@pytest.fixture
def random_string():
    """Generate random string for unique test data."""
    import uuid
    return lambda: uuid.uuid4().hex[:8]


@pytest.fixture
def random_uuid():
    """Generate random UUID."""
    from uuid import uuid4
    return uuid4


# =============================================================================
# MARKERS
# =============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
    config.addinivalue_line(
        "markers", "e2e: marks tests as end-to-end tests"
    )
