"""
Pytest configuration and shared fixtures for all tests.

This file is automatically loaded by pytest and provides:
- Database session fixtures
- Test client fixtures
- Category and tier fixtures
- Async test support
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import pytest_asyncio
import asyncio
from typing import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from database.connection import get_async_session
from database.models import Base, VehicleCategory, TariffTier
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.engine import make_url


async def _ensure_test_database_exists(source_database_url: str, test_db_name: str | None) -> None:
    """Create test database if missing (PostgreSQL)."""
    import asyncpg

    if not test_db_name:
        return

    source_dsn = source_database_url.replace("+asyncpg", "")

    conn = await asyncpg.connect(source_dsn)
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            test_db_name,
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{test_db_name}"')
    finally:
        await conn.close()


# =============================================================================
# ASYNC TEST SUPPORT
# =============================================================================

_SYSMOD_SNAPSHOT: dict[str, object] | None = None


def pytest_configure(config):
    """Snapshot sys.modules before test collection begins and register markers."""
    global _SYSMOD_SNAPSHOT
    _SYSMOD_SNAPSHOT = dict(sys.modules)

    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")
    config.addinivalue_line("markers", "e2e: marks tests as end-to-end tests")


def pytest_collectstart(collector):
    """Restore sys.modules before collecting each top-level test file.

    Some test files stub agent.* in sys.modules at import time without
    restoring them.  This prevents one file's stubs from poisoning the
    import state of subsequent files.
    """
    if _SYSMOD_SNAPSHOT is None:
        return
    # Only act on Module collectors (i.e. test files), not directories
    if not hasattr(collector, "fspath"):
        return
    for key in list(sys.modules):
        if key not in _SYSMOD_SNAPSHOT:
            del sys.modules[key]
    for key, mod in _SYSMOD_SNAPSHOT.items():
        sys.modules[key] = mod


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

@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Create test database engine."""
    from shared.config import get_settings

    settings = get_settings()

    # Use test database URL if configured, otherwise use test suffix
    test_db_url = settings.DATABASE_URL.replace("msia_db", "msia_db_test")
    test_db_name = make_url(test_db_url).database
    await _ensure_test_database_exists(settings.DATABASE_URL, test_db_name)

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


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a test database session."""
    TestingSessionLocal = async_sessionmaker(
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

@pytest_asyncio.fixture(scope="function")
async def test_category_setup(db_engine):
    """Create test category for all tests to use."""
    TestingSessionLocal = async_sessionmaker(
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


@pytest_asyncio.fixture(scope="function")
async def test_tiers_setup(test_category_setup, db_engine):
    """Create test tiers for category."""
    TestingSessionLocal = async_sessionmaker(
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

@pytest.fixture(scope="function")
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


@dataclass(slots=True)
class ConversationFootprint:
    """Reusable footprint covering DB, Redis keys, and local files."""

    conversation_uuid: UUID
    chatwoot_conversation_id: str
    user_id: UUID
    case_id: UUID
    image_id: UUID
    image_path: Path
    redis_keys: list[str]


@pytest.fixture
def conversation_reset_redis():
    """Mock Redis client aligned with reset cleanup patterns."""
    from unittest.mock import AsyncMock, MagicMock

    redis_mock = MagicMock()
    redis_mock.scan = AsyncMock(return_value=(0, []))
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.xdel = AsyncMock(return_value=0)
    return redis_mock


@pytest.fixture
def conversation_reset_chatwoot_mock():
    """Optional Chatwoot mock for best-effort reset stage."""
    from unittest.mock import AsyncMock

    chatwoot_mock = AsyncMock()
    chatwoot_mock.add_private_note = AsyncMock(return_value={"id": 1001})
    chatwoot_mock.add_labels = AsyncMock(return_value=True)
    chatwoot_mock.toggle_status = AsyncMock(return_value=True)
    return chatwoot_mock


@pytest_asyncio.fixture
async def conversation_footprint(db_session, tmp_path) -> ConversationFootprint:
    """Create a minimal conversation footprint used by reset tests."""
    from database.models import (
        Case,
        CaseImage,
        ConversationHistory,
        ConversationMessage,
        Escalation,
        RAGQuery,
        User,
    )

    chatwoot_conversation_id = f"reset-{uuid4().hex[:10]}"

    user = User(phone=f"+346{uuid4().int % 100000000:08d}")
    db_session.add(user)
    await db_session.flush()

    conversation = ConversationHistory(
        user_id=user.id,
        conversation_id=chatwoot_conversation_id,
        message_count=1,
    )
    db_session.add(conversation)
    await db_session.flush()

    db_session.add(
        ConversationMessage(
            conversation_history_id=conversation.id,
            role="user",
            content="Mensaje de prueba para reset",
        )
    )

    case = Case(conversation_id=chatwoot_conversation_id, user_id=user.id)
    db_session.add(case)
    await db_session.flush()

    stored_filename = f"{uuid4().hex}.jpg"
    image_path = tmp_path / stored_filename
    image_path.write_bytes(b"test-image-bytes")

    case_image = CaseImage(
        case_id=case.id,
        stored_filename=stored_filename,
        original_filename="foto.jpg",
        display_name="foto_reset",
        mime_type="image/jpeg",
    )
    db_session.add(case_image)

    db_session.add(
        Escalation(
            conversation_id=chatwoot_conversation_id,
            user_id=user.id,
            reason="Reset fixture escalation",
            source="tool_call",
            status="pending",
        )
    )

    db_session.add(
        RAGQuery(
            query_text="reset fixture query",
            query_hash=uuid4().hex,
            conversation_id=chatwoot_conversation_id,
            total_ms=1,
            num_results_retrieved=1,
            num_results_reranked=1,
            num_results_used=1,
            response_generated=False,
            cache_hit=False,
        )
    )

    await db_session.commit()
    await db_session.refresh(case_image)

    redis_keys = [
        f"checkpoint:{chatwoot_conversation_id}:ns",
        f"checkpoint_write:{chatwoot_conversation_id}:ns",
        f"write_keys_zset:{chatwoot_conversation_id}:ns",
        f"checkpoint_latest:{chatwoot_conversation_id}:ns",
        f"image_batch:{chatwoot_conversation_id}",
        f"image_batch_final:{chatwoot_conversation_id}",
    ]

    return ConversationFootprint(
        conversation_uuid=conversation.id,
        chatwoot_conversation_id=chatwoot_conversation_id,
        user_id=user.id,
        case_id=case.id,
        image_id=case_image.id,
        image_path=image_path,
        redis_keys=redis_keys,
    )


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
# ADMIN AUTH FIXTURES (secure-admin-auth Phase A)
# =============================================================================

@pytest.fixture
def valid_admin_jwt() -> str:
    """Return a valid, non-expired admin JWT signed with the test secret.

    This fixture produces a token suitable for use as the admin_token cookie
    or as a Bearer token in tests that exercise get_current_user.

    The token is created using the minimal JWT implementation in
    tests/api/test_admin_auth.py's _make_jose_stub(), but since conftest.py
    runs before any test module we produce the token using PyJWT or jose
    directly.  We avoid importing admin.py here to keep the fixture lightweight.
    """
    import base64
    import hashlib
    import hmac
    import json
    import time

    secret = "test-secret-key-for-admin-jwt-tests-only"
    jti = str(uuid4())
    claims = {
        "sub": "testadmin",
        "user_id": str(uuid4()),
        "role": "admin",
        "type": "admin",
        "jti": jti,
        "exp": int(time.time()) + 86400,
        "iat": int(time.time()),
    }

    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps(claims, separators=(",", ":")).encode())
    sig_input = f"{header}.{payload}".encode()
    sig = hmac.new(secret.encode(), sig_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64(sig)}"


@pytest_asyncio.fixture
async def async_client_with_cookie(valid_admin_jwt: str):
    """httpx.AsyncClient with admin_token cookie pre-set and no Authorization header.

    Prerequisite fixture for tests/api/test_admin_auth.py A2–A5.
    The client is configured with the cookie only; no Bearer header is added,
    so requests exercise the cookie-fallback path of get_current_user.
    """
    import httpx

    transport = httpx.MockTransport()  # placeholder — tests call get_current_user directly
    async with httpx.AsyncClient(
        cookies={"admin_token": valid_admin_jwt},
        base_url="http://testserver",
    ) as client:
        yield client


# =============================================================================
# MARKERS
# =============================================================================

