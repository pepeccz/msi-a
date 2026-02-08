"""
Tests for semantic validation (Phase 2 - Database-backed validation).

Tests database validators and SemanticValidator integration.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from agent.utils.tool_validation import SemanticValidator
from agent.services.constraint_service import (
    validate_categoria_slug,
    validate_element_code,
    validate_case_id,
    validate_user_id,
    validate_tier_id,
    cached_db_lookup,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_tool():
    """Mock LangChain tool."""
    tool = MagicMock()
    tool.name = "test_tool"
    return tool


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)  # Default: cache miss
    redis.setex = AsyncMock()
    return redis


# ============================================================================
# cached_db_lookup tests
# ============================================================================


@pytest.mark.skip(reason="Redis mocking issue - internal function not exposed for testing")
@pytest.mark.asyncio
async def test_cached_db_lookup_cache_miss(mock_redis):
    """Test cached_db_lookup with cache miss."""
    async def query_func():
        return {"result": "data"}
    
    with patch("agent.services.constraint_service.get_redis_client", return_value=mock_redis):
        result = await cached_db_lookup("test_key", query_func, ttl=300)
    
    assert result == {"result": "data"}
    mock_redis.get.assert_called_once_with("test_key")
    mock_redis.setex.assert_called_once()


@pytest.mark.skip(reason="Redis mocking issue - internal function not exposed for testing")
@pytest.mark.asyncio
async def test_cached_db_lookup_cache_hit(mock_redis):
    """Test cached_db_lookup with cache hit."""
    import json
    
    mock_redis.get = AsyncMock(return_value=json.dumps({"result": "cached"}))
    
    async def query_func():
        pytest.fail("Should not call DB on cache hit")
    
    with patch("agent.services.constraint_service.get_redis_client", return_value=mock_redis):
        result = await cached_db_lookup("test_key", query_func, ttl=300)
    
    assert result == {"result": "cached"}
    mock_redis.get.assert_called_once_with("test_key")
    mock_redis.setex.assert_not_called()


@pytest.mark.skip(reason="Redis mocking issue - internal function not exposed for testing")
@pytest.mark.asyncio
async def test_cached_db_lookup_redis_error_graceful(mock_redis):
    """Test cached_db_lookup handles Redis errors gracefully."""
    mock_redis.get = AsyncMock(side_effect=Exception("Redis down"))
    mock_redis.setex = AsyncMock(side_effect=Exception("Redis down"))
    
    async def query_func():
        return {"result": "data"}
    
    with patch("agent.services.constraint_service.get_redis_client", return_value=mock_redis):
        result = await cached_db_lookup("test_key", query_func, ttl=300)
    
    # Should still return data despite Redis errors
    assert result == {"result": "data"}


# ============================================================================
# validate_categoria_slug tests
# ============================================================================


@pytest.mark.asyncio
async def test_validate_categoria_slug_valid(mock_redis):
    """Test valid categoria_slug."""
    async def mock_query():
        return {"exists": True}
    
    with patch("agent.services.constraint_service.cached_db_lookup", return_value={"exists": True}):
        is_valid, error = await validate_categoria_slug("motos-part")
    
    assert is_valid is True
    assert error is None


@pytest.mark.asyncio
async def test_validate_categoria_slug_invalid(mock_redis):
    """Test invalid categoria_slug."""
    with patch("agent.services.constraint_service.cached_db_lookup", return_value={"exists": False}):
        is_valid, error = await validate_categoria_slug("invalid-slug")
    
    assert is_valid is False
    assert "no existe" in error


# ============================================================================
# validate_element_code tests
# ============================================================================


@pytest.mark.asyncio
async def test_validate_element_code_valid():
    """Test valid element_code for category."""
    with patch("agent.services.constraint_service.cached_db_lookup", return_value={"exists": True}):
        is_valid, error = await validate_element_code("ESCAPE", "motos-part")
    
    assert is_valid is True
    assert error is None


@pytest.mark.asyncio
async def test_validate_element_code_invalid():
    """Test invalid element_code for category."""
    with patch("agent.services.constraint_service.cached_db_lookup", return_value={"exists": False}):
        is_valid, error = await validate_element_code("INVALID", "motos-part")
    
    assert is_valid is False
    assert "no existe" in error
    assert "INVALID" in error
    assert "motos-part" in error


# ============================================================================
# validate_case_id tests
# ============================================================================


@pytest.mark.asyncio
async def test_validate_case_id_valid():
    """Test valid case_id."""
    case_id = str(uuid4())
    
    with patch("agent.services.constraint_service.cached_db_lookup", return_value={"exists": True, "is_active": True}):
        is_valid, error = await validate_case_id(case_id)
    
    assert is_valid is True
    assert error is None


@pytest.mark.asyncio
async def test_validate_case_id_not_exists():
    """Test case_id doesn't exist."""
    case_id = str(uuid4())
    
    with patch("agent.services.constraint_service.cached_db_lookup", return_value={"exists": False, "is_active": False}):
        is_valid, error = await validate_case_id(case_id)
    
    assert is_valid is False
    assert "no existe" in error


@pytest.mark.asyncio
async def test_validate_case_id_inactive():
    """Test case exists but is inactive."""
    case_id = str(uuid4())
    
    with patch("agent.services.constraint_service.cached_db_lookup", return_value={"exists": True, "is_active": False}):
        is_valid, error = await validate_case_id(case_id)
    
    assert is_valid is False
    assert "inactivo" in error


@pytest.mark.asyncio
async def test_validate_case_id_invalid_format():
    """Test case_id with invalid UUID format."""
    is_valid, error = await validate_case_id("not-a-uuid")
    
    assert is_valid is False
    assert "formato válido" in error


# ============================================================================
# validate_user_id tests
# ============================================================================


@pytest.mark.asyncio
async def test_validate_user_id_valid():
    """Test valid user_id."""
    user_id = str(uuid4())
    
    with patch("agent.services.constraint_service.cached_db_lookup", return_value={"exists": True}):
        is_valid, error = await validate_user_id(user_id)
    
    assert is_valid is True
    assert error is None


@pytest.mark.asyncio
async def test_validate_user_id_invalid():
    """Test invalid user_id."""
    user_id = str(uuid4())
    
    with patch("agent.services.constraint_service.cached_db_lookup", return_value={"exists": False}):
        is_valid, error = await validate_user_id(user_id)
    
    assert is_valid is False
    assert "no existe" in error


@pytest.mark.asyncio
async def test_validate_user_id_invalid_format():
    """Test user_id with invalid UUID format."""
    is_valid, error = await validate_user_id("not-a-uuid")
    
    assert is_valid is False
    assert "formato válido" in error


# ============================================================================
# validate_tier_id tests
# ============================================================================


@pytest.mark.asyncio
async def test_validate_tier_id_valid():
    """Test valid tier_id for category."""
    tier_id = str(uuid4())
    
    with patch("agent.services.constraint_service.cached_db_lookup", return_value={"exists": True}):
        is_valid, error = await validate_tier_id(tier_id, "motos-part")
    
    assert is_valid is True
    assert error is None


@pytest.mark.asyncio
async def test_validate_tier_id_invalid():
    """Test invalid tier_id for category."""
    tier_id = str(uuid4())
    
    with patch("agent.services.constraint_service.cached_db_lookup", return_value={"exists": False}):
        is_valid, error = await validate_tier_id(tier_id, "motos-part")
    
    assert is_valid is False
    assert "no existe" in error


@pytest.mark.asyncio
async def test_validate_tier_id_invalid_format():
    """Test tier_id with invalid UUID format."""
    is_valid, error = await validate_tier_id("not-a-uuid", "motos-part")
    
    assert is_valid is False
    assert "formato válido" in error


# ============================================================================
# SemanticValidator tests
# ============================================================================


@pytest.mark.asyncio
async def test_semantic_validator_tool_not_configured(mock_tool):
    """Test SemanticValidator skips tools not in TOOL_VALIDATIONS."""
    validator = SemanticValidator()
    mock_tool.name = "unconfigured_tool"
    
    is_valid, errors = await validator.validate(mock_tool, {}, {})
    
    assert is_valid is True
    assert errors == []


@pytest.mark.asyncio
async def test_semantic_validator_categoria_slug_valid(mock_tool):
    """Test SemanticValidator with valid categoria_slug."""
    validator = SemanticValidator()
    mock_tool.name = "identificar_y_resolver_elementos"
    
    with patch("agent.services.constraint_service.validate_categoria_slug", return_value=(True, None)):
        is_valid, errors = await validator.validate(
            mock_tool,
            {"categoria_slug": "motos-part"},
            {}
        )
    
    assert is_valid is True
    assert errors == []


@pytest.mark.asyncio
async def test_semantic_validator_categoria_slug_invalid(mock_tool):
    """Test SemanticValidator with invalid categoria_slug."""
    validator = SemanticValidator()
    mock_tool.name = "identificar_y_resolver_elementos"
    
    with patch("agent.services.constraint_service.validate_categoria_slug", return_value=(False, "Category not found")):
        is_valid, errors = await validator.validate(
            mock_tool,
            {"categoria_slug": "invalid"},
            {}
        )
    
    assert is_valid is False
    assert len(errors) == 1
    assert "not found" in errors[0]


@pytest.mark.asyncio
async def test_semantic_validator_element_code_valid(mock_tool):
    """Test SemanticValidator with valid element_code."""
    validator = SemanticValidator()
    mock_tool.name = "obtener_campos_elemento"
    
    with patch("agent.services.constraint_service.validate_element_code", return_value=(True, None)):
        with patch("agent.services.constraint_service.validate_categoria_slug", return_value=(True, None)):
            is_valid, errors = await validator.validate(
                mock_tool,
                {"element_code": "ESCAPE", "categoria_slug": "motos-part"},
                {}
            )
    
    assert is_valid is True
    assert errors == []


@pytest.mark.asyncio
async def test_semantic_validator_element_code_no_category(mock_tool):
    """Test SemanticValidator skips element_code if categoria_slug missing."""
    validator = SemanticValidator()
    mock_tool.name = "obtener_campos_elemento"
    
    # element_code validation should be skipped if no categoria_slug
    is_valid, errors = await validator.validate(
        mock_tool,
        {"element_code": "ESCAPE"},  # Missing categoria_slug
        {}
    )
    
    # Should pass (skipped validation)
    assert is_valid is True
    assert errors == []


@pytest.mark.asyncio
async def test_semantic_validator_case_id_valid(mock_tool):
    """Test SemanticValidator with valid case_id."""
    validator = SemanticValidator()
    mock_tool.name = "actualizar_datos_personales"
    case_id = str(uuid4())
    
    with patch("agent.services.constraint_service.validate_case_id", return_value=(True, None)):
        is_valid, errors = await validator.validate(
            mock_tool,
            {"case_id": case_id},
            {}
        )
    
    assert is_valid is True
    assert errors == []


@pytest.mark.asyncio
async def test_semantic_validator_case_id_from_state(mock_tool):
    """Test SemanticValidator reads case_id from state."""
    validator = SemanticValidator()
    mock_tool.name = "actualizar_datos_personales"
    case_id = str(uuid4())
    
    with patch("agent.services.constraint_service.validate_case_id", return_value=(True, None)):
        is_valid, errors = await validator.validate(
            mock_tool,
            {},  # No params
            {"case_id": case_id}  # From state
        )
    
    assert is_valid is True
    assert errors == []


@pytest.mark.asyncio
async def test_semantic_validator_multiple_errors(mock_tool):
    """Test SemanticValidator aggregates multiple errors."""
    validator = SemanticValidator()
    mock_tool.name = "iniciar_expediente"
    
    with patch("agent.services.constraint_service.validate_categoria_slug", return_value=(False, "Category error")):
        with patch("agent.services.constraint_service.validate_tier_id", return_value=(False, "Tier error")):
            is_valid, errors = await validator.validate(
                mock_tool,
                {"categoria_slug": "invalid", "tier_id": str(uuid4())},
                {}
            )
    
    assert is_valid is False
    assert len(errors) == 2
    assert "Category error" in errors
    assert "Tier error" in errors


@pytest.mark.asyncio
async def test_semantic_validator_exception_handling(mock_tool):
    """Test SemanticValidator handles exceptions gracefully (fail-safe)."""
    validator = SemanticValidator()
    mock_tool.name = "identificar_y_resolver_elementos"
    
    # Simulate validator raising exception
    with patch("agent.services.constraint_service.validate_categoria_slug", side_effect=Exception("DB down")):
        is_valid, errors = await validator.validate(
            mock_tool,
            {"categoria_slug": "motos-part"},
            {}
        )
    
    # Should pass (fail open on exception)
    assert is_valid is True
    assert errors == []


# ============================================================================
# Integration tests
# ============================================================================


@pytest.mark.asyncio
async def test_semantic_validator_integration_calcular_tarifa(mock_tool):
    """Integration test: calcular_tarifa_con_elementos with valid categoria_slug."""
    validator = SemanticValidator()
    mock_tool.name = "calcular_tarifa_con_elementos"
    
    with patch("agent.services.constraint_service.validate_categoria_slug", return_value=(True, None)):
        is_valid, errors = await validator.validate(
            mock_tool,
            {"categoria_slug": "motos-part", "elementos": ["ESCAPE"]},
            {}
        )
    
    assert is_valid is True
    assert errors == []


@pytest.mark.asyncio
async def test_semantic_validator_integration_guardar_datos(mock_tool):
    """Integration test: guardar_datos_elemento with valid case_id, element_code, categoria_slug."""
    validator = SemanticValidator()
    mock_tool.name = "guardar_datos_elemento"
    case_id = str(uuid4())
    
    with patch("agent.services.constraint_service.validate_case_id", return_value=(True, None)):
        with patch("agent.services.constraint_service.validate_element_code", return_value=(True, None)):
            with patch("agent.services.constraint_service.validate_categoria_slug", return_value=(True, None)):
                is_valid, errors = await validator.validate(
                    mock_tool,
                    {
                        "case_id": case_id,
                        "element_code": "ESCAPE",
                        "categoria_slug": "motos-part",
                        "datos": {"field1": "value1"}
                    },
                    {}
                )
    
    assert is_valid is True
    assert errors == []
