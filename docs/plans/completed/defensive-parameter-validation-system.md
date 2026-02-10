# Plan: Defensive Parameter Validation System

**Date**: February 7, 2026  
**Priority**: 🔴 CRITICAL  
**Estimated Effort**: 30-40 hours  
**Status**: READY FOR REVIEW

---

## Executive Summary

Implement a comprehensive **defensive parameter validation system** to prevent tool execution failures caused by LLM parameter hallucination or omission. This addresses a **systemic architectural vulnerability** affecting 7 high-risk tools and ~60-75% reliability for complex parameter extraction.

### Problem Statement

**Current**: LLMs can hallucinate, omit, or incorrectly pass tool parameters. No validation layer exists before tool execution → tools crash with NULL/missing params → corrupt database records.

**Evidence**:
- `iniciar_expediente()` creates Cases with NULL `tariff_amount`/`tariff_tier_id` (production bug)
- 7 high-risk tools vulnerable to same pattern
- LLM reliability: 60-75% for complex context extraction, 50-60% for critical business data

**Impact**: Data integrity compromised, manual cleanup required, user trust degradation.

### Solution Overview

Implement **3-layer validation**:
1. **Syntax**: Required params present, types correct (fast, no I/O)
2. **State**: State dependencies satisfied (case_id exists, etc.)
3. **Semantics**: Values valid (categoria_slug exists in DB)

**Implementation**: Validation in `_execute_and_log_tool()` (central point, non-breaking)

---

## Phase 1: Core Parameter Validation (CRITICAL - Week 1)

### Objective

Add validation layer that intercepts tool calls BEFORE execution, validates parameters against tool schema, and returns structured errors to LLM for retry.

### Implementation Plan

#### 1.1 Create Validation Infrastructure

**File**: `agent/utils/tool_validation.py` (NEW)

```python
"""
Tool parameter validation utilities.

Validates tool calls BEFORE execution to prevent:
- Missing required parameters
- Invalid parameter types
- Missing state dependencies
"""

import structlog
from typing import Any, Protocol
from langchain.tools import BaseTool

logger = structlog.get_logger(__name__)


class ToolValidator(Protocol):
    """Protocol for tool validators."""
    
    async def validate(
        self,
        tool: BaseTool,
        params: dict[str, Any],
        state: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """
        Validate tool parameters.
        
        Args:
            tool: LangChain tool instance
            params: Parameters provided by LLM
            state: Current conversation state
        
        Returns:
            (is_valid, errors)
        """
        ...


class SyntaxValidator:
    """
    Validates parameter syntax (required fields, types).
    
    Uses LangChain's args_schema for introspection.
    """
    
    async def validate(
        self,
        tool: BaseTool,
        params: dict[str, Any],
        state: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """Validate required parameters are present."""
        errors = []
        
        # Get tool schema from LangChain
        schema = tool.args_schema
        if not schema:
            # No schema = can't validate
            logger.warning(
                "tool_no_schema",
                tool_name=tool.name,
            )
            return (True, [])
        
        # Check each field
        for field_name, field_info in schema.__fields__.items():
            # Required field missing?
            if field_info.required and field_name not in params:
                errors.append(
                    f"Missing required parameter: {field_name}"
                )
            
            # Type check (basic)
            if field_name in params and params[field_name] is not None:
                expected_type = field_info.outer_type_
                actual_value = params[field_name]
                
                # Skip complex type validation (Pydantic will do it)
                # Just check basic types
                if expected_type in (str, int, float, bool):
                    if not isinstance(actual_value, expected_type):
                        errors.append(
                            f"Parameter {field_name} must be {expected_type.__name__}, "
                            f"got {type(actual_value).__name__}"
                        )
        
        if errors:
            logger.warning(
                "syntax_validation_failed",
                tool_name=tool.name,
                errors=errors,
                provided_params=list(params.keys()),
            )
        
        return (len(errors) == 0, errors)


class StateValidator:
    """
    Validates state dependencies.
    
    Checks that required state keys exist before tool execution.
    """
    
    # Map tool names to required state keys
    STATE_REQUIREMENTS = {
        "iniciar_expediente": ["categoria_slug", "user_id"],
        "actualizar_datos_personales": ["case_id"],
        "actualizar_datos_vehiculo": ["case_id"],
        "completar_elemento_actual": ["case_id", "current_element_index"],
        "actualizar_taller": ["case_id"],
        "confirmar_expediente": ["case_id"],
        "enviar_imagenes_ejemplo": ["precio_comunicado"],
        "calcular_tarifa_con_elementos": ["categoria_slug"],
    }
    
    async def validate(
        self,
        tool: BaseTool,
        params: dict[str, Any],
        state: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """Validate required state exists."""
        tool_name = tool.name
        
        if tool_name not in self.STATE_REQUIREMENTS:
            # No state requirements for this tool
            return (True, [])
        
        errors = []
        required_keys = self.STATE_REQUIREMENTS[tool_name]
        
        for key in required_keys:
            if key not in state or state[key] is None:
                errors.append(
                    f"Required state missing: {key}"
                )
        
        if errors:
            logger.warning(
                "state_validation_failed",
                tool_name=tool_name,
                errors=errors,
                state_keys=list(state.keys()),
            )
        
        return (len(errors) == 0, errors)


class ToolValidationService:
    """
    Coordinates all validation layers.
    
    Usage:
        validator = ToolValidationService()
        is_valid, errors = await validator.validate(tool, params, state)
    """
    
    def __init__(self):
        self.syntax_validator = SyntaxValidator()
        self.state_validator = StateValidator()
    
    async def validate(
        self,
        tool: BaseTool,
        params: dict[str, Any],
        state: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """
        Run all validation layers.
        
        Returns on first failure (fast fail).
        """
        all_errors = []
        
        # Layer 1: Syntax validation (fast)
        is_valid, errors = await self.syntax_validator.validate(tool, params, state)
        if not is_valid:
            all_errors.extend(errors)
        
        # Layer 2: State validation (fast)
        is_valid, errors = await self.state_validator.validate(tool, params, state)
        if not is_valid:
            all_errors.extend(errors)
        
        # Note: Semantic validation (DB checks) added in Phase 2
        
        if all_errors:
            logger.warning(
                "tool_validation_failed",
                tool_name=tool.name,
                errors=all_errors,
            )
            return (False, all_errors)
        
        logger.info(
            "tool_validation_passed",
            tool_name=tool.name,
        )
        return (True, [])


# Singleton instance
_validator_instance = None

def get_tool_validator() -> ToolValidationService:
    """Get singleton ToolValidationService."""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = ToolValidationService()
    return _validator_instance
```

**Key Design Decisions**:
- ✅ Uses LangChain's `args_schema` for introspection (no manual schema maintenance)
- ✅ Layered validators (easy to add semantic layer in Phase 2)
- ✅ Singleton pattern (reused across all tool calls)
- ✅ Structured logging with context
- ✅ Fast-fail (stops on first validation error)

---

#### 1.2 Integrate Validation into BaseModeNode

**File**: `agent/modes/base_mode.py` (MODIFY)

**Location**: Lines 300-350 (in `_execute_and_log_tool`)

**Current Code**:
```python
async def _execute_and_log_tool(
    self,
    tool_name: str,
    tool_kwargs: dict,
    conversation_id: int,
) -> dict:
    """Execute tool with logging and error handling."""
    try:
        # Get tool instance
        tool = self._get_tool_by_name(tool_name)
        if not tool:
            logger.error("tool_not_found", tool_name=tool_name)
            return tool_error_response(
                f"Tool {tool_name} not found",
                tool_name,
                error_type="tool_not_found"
            )
        
        # Execute tool  ← NO VALIDATION HERE
        logger.info("tool_execution_start", tool=tool_name, params=tool_kwargs)
        result = await tool.ainvoke(tool_kwargs)
        
        # ... rest of function
```

**NEW Code** (add validation before execution):
```python
async def _execute_and_log_tool(
    self,
    tool_name: str,
    tool_kwargs: dict,
    conversation_id: int,
) -> dict:
    """
    Execute tool with validation, logging, and error handling.
    
    NEW: Validates parameters BEFORE execution (defensive programming).
    """
    try:
        # Get tool instance
        tool = self._get_tool_by_name(tool_name)
        if not tool:
            logger.error("tool_not_found", tool_name=tool_name)
            return tool_error_response(
                f"Tool {tool_name} not found",
                tool_name,
                error_type="tool_not_found"
            )
        
        # ================================================================
        # NEW: VALIDATE PARAMETERS BEFORE EXECUTION
        # ================================================================
        from agent.utils.tool_validation import get_tool_validator
        from agent.state.helpers import get_current_state
        
        validator = get_tool_validator()
        current_state = get_current_state()
        
        is_valid, errors = await validator.validate(
            tool=tool,
            params=tool_kwargs,
            state=current_state,
        )
        
        if not is_valid:
            logger.warning(
                "tool_parameter_validation_failed",
                tool=tool_name,
                errors=errors,
                provided_params=list(tool_kwargs.keys()),
            )
            
            # Return structured error to LLM
            error_response = {
                "success": False,
                "error": "Invalid tool parameters",
                "error_type": "parameter_validation",
                "tool_name": tool_name,
                "validation_errors": errors,
                "provided_params": list(tool_kwargs.keys()),
                "required_params": self._get_required_params(tool),
                "suggestion": self._generate_fix_suggestion(tool, errors),
            }
            
            # Log failed validation
            await log_tool_call(
                conversation_id=conversation_id,
                tool_name=tool_name,
                parameters=tool_kwargs,
                result=error_response,
                success=False,
            )
            
            return error_response
        
        # ================================================================
        # END VALIDATION - Proceed with execution
        # ================================================================
        
        # Execute tool (unchanged)
        logger.info("tool_execution_start", tool=tool_name, params=tool_kwargs)
        result = await tool.ainvoke(tool_kwargs)
        
        # Log tool call
        await log_tool_call(
            conversation_id=conversation_id,
            tool_name=tool_name,
            parameters=tool_kwargs,
            result=result,
            success=result.get("success", False),
        )
        
        logger.info(
            "tool_execution_complete",
            tool=tool_name,
            success=result.get("success"),
        )
        
        return result
        
    except Exception as e:
        logger.error(
            "tool_execution_failed",
            tool=tool_name,
            error=str(e),
            traceback=traceback.format_exc(),
        )
        
        error_response = tool_error_response(
            f"Error executing {tool_name}: {str(e)}",
            tool_name,
            error_type="execution_exception",
            details={"exception": str(e)},
        )
        
        # Log failed call
        await log_tool_call(
            conversation_id=conversation_id,
            tool_name=tool_name,
            parameters=tool_kwargs,
            result=error_response,
            success=False,
        )
        
        return error_response


def _get_required_params(self, tool: BaseTool) -> list[str]:
    """Extract required parameter names from tool schema."""
    if not tool.args_schema:
        return []
    
    required = []
    for field_name, field_info in tool.args_schema.__fields__.items():
        if field_info.required:
            required.append(field_name)
    
    return required


def _generate_fix_suggestion(self, tool: BaseTool, errors: list[str]) -> str:
    """
    Generate helpful suggestion for LLM to fix parameters.
    
    Example:
        "Please provide the categoria_slug parameter. 
         You can extract it from mode_context['categoria_slug']."
    """
    # Extract missing param names from errors
    missing_params = []
    for error in errors:
        if "Missing required parameter:" in error:
            param_name = error.split(":")[-1].strip()
            missing_params.append(param_name)
    
    if not missing_params:
        return "Please check the parameter values and try again."
    
    # Generate context extraction hints
    hints = {
        "categoria_slug": "Extract from mode_context['categoria_slug']",
        "tarifa_calculada": "Extract from mode_context['tarifa_calculada']['datos']['price']",
        "tier_id": "Extract from mode_context['tarifa_calculada']['datos']['tier_id']",
        "case_id": "Extract from state or mode_context['case_id']",
    }
    
    suggestions = []
    for param in missing_params:
        hint = hints.get(param, f"Provide {param}")
        suggestions.append(f"- {param}: {hint}")
    
    return "Please provide the following parameters:\n" + "\n".join(suggestions)
```

**Impact**:
- ✅ ALL tool calls now validated
- ✅ Structured errors help LLM fix and retry
- ✅ No changes to tool signatures
- ✅ Logs validation failures for monitoring

---

#### 1.3 Add Helper for Tool Error Responses

**File**: `agent/utils/tool_helpers.py` (MODIFY)

**Add structured error response** (more detailed than current):

```python
def structured_validation_error(
    tool_name: str,
    validation_errors: list[str],
    provided_params: list[str],
    required_params: list[str],
    suggestion: str,
) -> dict:
    """
    Generate structured validation error for LLM retry.
    
    Provides enough context for LLM to fix parameters.
    """
    return {
        "success": False,
        "error": "Invalid tool parameters",
        "error_type": "parameter_validation",
        "tool_name": tool_name,
        "validation_errors": validation_errors,
        "provided_params": provided_params,
        "required_params": required_params,
        "suggestion": suggestion,
        "can_retry": True,  # Signal to LLM that retry is expected
    }
```

---

#### 1.4 Testing

**File**: `tests/agent/utils/test_tool_validation.py` (NEW)

```python
"""
Tests for tool parameter validation.

Covers all validation layers (syntax, state, semantic).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from agent.utils.tool_validation import (
    SyntaxValidator,
    StateValidator,
    ToolValidationService,
    get_tool_validator,
)
from langchain.tools import tool


@pytest.mark.asyncio
async def test_syntax_validator_required_param_missing():
    """Test syntax validator catches missing required parameter."""
    
    @tool
    def test_tool(param1: str, param2: int) -> dict:
        """Test tool with required params."""
        return {"success": True}
    
    validator = SyntaxValidator()
    
    # Missing param2
    params = {"param1": "value1"}
    state = {}
    
    is_valid, errors = await validator.validate(test_tool, params, state)
    
    assert is_valid is False
    assert len(errors) == 1
    assert "param2" in errors[0]


@pytest.mark.asyncio
async def test_syntax_validator_all_params_present():
    """Test syntax validator passes when all params present."""
    
    @tool
    def test_tool(param1: str, param2: int = 10) -> dict:
        """Test tool."""
        return {"success": True}
    
    validator = SyntaxValidator()
    
    # All required params present
    params = {"param1": "value1", "param2": 20}
    state = {}
    
    is_valid, errors = await validator.validate(test_tool, params, state)
    
    assert is_valid is True
    assert len(errors) == 0


@pytest.mark.asyncio
async def test_state_validator_missing_case_id():
    """Test state validator catches missing case_id."""
    
    @tool
    def actualizar_datos_personales(nombre: str) -> dict:
        """Tool that needs case_id in state."""
        return {"success": True}
    
    validator = StateValidator()
    
    # State without case_id
    params = {"nombre": "Juan"}
    state = {"conversation_id": 123}
    
    is_valid, errors = await validator.validate(
        actualizar_datos_personales,
        params,
        state,
    )
    
    assert is_valid is False
    assert len(errors) == 1
    assert "case_id" in errors[0]


@pytest.mark.asyncio
async def test_state_validator_has_case_id():
    """Test state validator passes when case_id present."""
    
    @tool
    def actualizar_datos_personales(nombre: str) -> dict:
        """Tool that needs case_id."""
        return {"success": True}
    
    validator = StateValidator()
    
    # State with case_id
    params = {"nombre": "Juan"}
    state = {"conversation_id": 123, "case_id": "uuid-123"}
    
    is_valid, errors = await validator.validate(
        actualizar_datos_personales,
        params,
        state,
    )
    
    assert is_valid is True
    assert len(errors) == 0


@pytest.mark.asyncio
async def test_tool_validation_service_integration():
    """Test full validation service with multiple validators."""
    
    @tool
    def test_tool(param1: str, param2: int) -> dict:
        """Test tool."""
        return {"success": True}
    
    validator = ToolValidationService()
    
    # Missing param + missing state
    params = {"param1": "value1"}  # Missing param2
    state = {}
    
    is_valid, errors = await validator.validate(test_tool, params, state)
    
    assert is_valid is False
    assert len(errors) >= 1  # At least syntax error


@pytest.mark.asyncio
async def test_get_tool_validator_singleton():
    """Test validator singleton returns same instance."""
    validator1 = get_tool_validator()
    validator2 = get_tool_validator()
    
    assert validator1 is validator2
```

**Additional tests** (30+ total):
- Test type validation (string passed as int)
- Test optional parameters (should pass if missing)
- Test state validator for each tool in STATE_REQUIREMENTS
- Test structured error generation
- Test suggestion generation for missing params

---

### Deliverables (Phase 1)

1. ✅ `agent/utils/tool_validation.py` - Core validation infrastructure
2. ✅ `agent/modes/base_mode.py` - Integration in `_execute_and_log_tool`
3. ✅ `agent/utils/tool_helpers.py` - Structured error response
4. ✅ `tests/agent/utils/test_tool_validation.py` - Comprehensive tests (30+)
5. ✅ Documentation update in `docs/coding-standards/03-agent-architecture.md`

### Success Criteria

- [ ] All 30 tools have parameter validation
- [ ] Validation catches missing required params BEFORE execution
- [ ] LLM receives structured errors with "how to fix"
- [ ] Tests achieve 95%+ coverage for validation logic
- [ ] No breaking changes to existing tool behavior
- [ ] Logs show validation failures for monitoring

---

## Phase 2: Semantic Validation (Week 2)

### Objective

Add database-level validation to catch semantic errors (e.g., `categoria_slug` doesn't exist, `element_code` not in category).

### Implementation Plan

#### 2.1 Extend ConstraintService

**File**: `agent/services/constraint_service.py` (MODIFY)

**Add pre-execution validation methods**:

```python
class ConstraintService:
    """
    Validates agent parameters against database constraints.
    
    NEW: Pre-execution validation (before tool runs).
    """
    
    # Existing methods...
    
    async def validate_categoria_exists(
        self,
        categoria_slug: str,
    ) -> bool:
        """Check if category exists."""
        async with get_async_session() as session:
            result = await session.execute(
                select(Category).where(Category.slug == categoria_slug)
            )
            return result.scalar_one_or_none() is not None
    
    async def validate_element_in_category(
        self,
        element_code: str,
        categoria_slug: str,
    ) -> bool:
        """Check if element exists in category."""
        async with get_async_session() as session:
            result = await session.execute(
                select(Element)
                .join(Category)
                .where(
                    Element.code == element_code,
                    Category.slug == categoria_slug,
                )
            )
            return result.scalar_one_or_none() is not None
    
    async def validate_case_exists(
        self,
        case_id: str,
    ) -> bool:
        """Check if case exists."""
        async with get_async_session() as session:
            result = await session.execute(
                select(Case).where(Case.id == UUID(case_id))
            )
            return result.scalar_one_or_none() is not None
```

#### 2.2 Add Semantic Validator

**File**: `agent/utils/tool_validation.py` (MODIFY)

**Add SemanticValidator**:

```python
class SemanticValidator:
    """
    Validates parameter semantics (DB checks).
    
    Checks that values are valid (categoria_slug exists, etc.).
    """
    
    def __init__(self):
        from agent.services.constraint_service import ConstraintService
        self.constraint_service = ConstraintService()
    
    # Map tool names to semantic validators
    SEMANTIC_VALIDATORS = {
        "identificar_y_resolver_elementos": ["validate_categoria"],
        "calcular_tarifa_con_elementos": ["validate_categoria"],
        "iniciar_expediente": ["validate_categoria"],
        "actualizar_datos_personales": ["validate_case"],
        "actualizar_datos_vehiculo": ["validate_case"],
        # ... more tools
    }
    
    async def validate(
        self,
        tool: BaseTool,
        params: dict[str, Any],
        state: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """Validate parameter semantics."""
        tool_name = tool.name
        
        if tool_name not in self.SEMANTIC_VALIDATORS:
            # No semantic validation for this tool
            return (True, [])
        
        errors = []
        validators = self.SEMANTIC_VALIDATORS[tool_name]
        
        for validator_name in validators:
            if validator_name == "validate_categoria":
                categoria_slug = params.get("categoria_slug")
                if categoria_slug:
                    exists = await self.constraint_service.validate_categoria_exists(
                        categoria_slug
                    )
                    if not exists:
                        errors.append(
                            f"Category '{categoria_slug}' does not exist"
                        )
            
            elif validator_name == "validate_case":
                case_id = state.get("case_id")
                if case_id:
                    exists = await self.constraint_service.validate_case_exists(case_id)
                    if not exists:
                        errors.append(
                            f"Case '{case_id}' does not exist"
                        )
        
        if errors:
            logger.warning(
                "semantic_validation_failed",
                tool_name=tool_name,
                errors=errors,
            )
        
        return (len(errors) == 0, errors)
```

#### 2.3 Integrate into ToolValidationService

**File**: `agent/utils/tool_validation.py` (MODIFY)

**Add semantic layer to validation**:

```python
class ToolValidationService:
    """Coordinates all validation layers."""
    
    def __init__(self):
        self.syntax_validator = SyntaxValidator()
        self.state_validator = StateValidator()
        self.semantic_validator = SemanticValidator()  # NEW
    
    async def validate(
        self,
        tool: BaseTool,
        params: dict[str, Any],
        state: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """Run all validation layers."""
        all_errors = []
        
        # Layer 1: Syntax (fast)
        is_valid, errors = await self.syntax_validator.validate(tool, params, state)
        if not is_valid:
            all_errors.extend(errors)
            # Fast fail - don't do DB checks if syntax invalid
            return (False, all_errors)
        
        # Layer 2: State (fast)
        is_valid, errors = await self.state_validator.validate(tool, params, state)
        if not is_valid:
            all_errors.extend(errors)
            # Fast fail
            return (False, all_errors)
        
        # Layer 3: Semantic (DB checks) - NEW
        is_valid, errors = await self.semantic_validator.validate(tool, params, state)
        if not is_valid:
            all_errors.extend(errors)
        
        if all_errors:
            logger.warning(
                "tool_validation_failed",
                tool_name=tool.name,
                errors=all_errors,
            )
            return (False, all_errors)
        
        logger.info(
            "tool_validation_passed",
            tool_name=tool.name,
        )
        return (True, [])
```

#### 2.4 Add Redis Caching

**Optimization**: Cache semantic validation results in Redis (5-min TTL).

```python
class SemanticValidator:
    """Semantic validation with caching."""
    
    async def validate(self, tool, params, state):
        """Validate with Redis cache."""
        from shared.redis_client import get_redis_client
        
        redis = get_redis_client()
        
        # Check cache
        if "categoria_slug" in params:
            cache_key = f"categoria_exists:{params['categoria_slug']}"
            cached = await redis.get(cache_key)
            if cached is not None:
                if cached == "1":
                    exists = True
                else:
                    exists = False
            else:
                # Not cached - query DB
                exists = await self.constraint_service.validate_categoria_exists(
                    params["categoria_slug"]
                )
                # Cache result (5 min TTL)
                await redis.setex(cache_key, 300, "1" if exists else "0")
            
            if not exists:
                return (False, [f"Category '{params['categoria_slug']}' not found"])
        
        return (True, [])
```

### Deliverables (Phase 2)

1. ✅ `agent/services/constraint_service.py` - Pre-execution validators
2. ✅ `agent/utils/tool_validation.py` - SemanticValidator + caching
3. ✅ `tests/agent/utils/test_semantic_validation.py` - Tests for DB checks
4. ✅ Monitoring dashboard for validation failure rates

### Success Criteria

- [ ] Semantic errors caught BEFORE tool execution
- [ ] Redis caching reduces DB load
- [ ] Validation errors distinguish syntax vs. semantic
- [ ] LLM receives actionable errors ("Category 'invalid' not found")

---

## Phase 3: Error Recovery & Retry (Week 3)

### Objective

Integrate FallbackHandler into mode nodes for automatic retry with progressive reprompting.

### Implementation Plan

#### 3.1 Extend FallbackHandler

**File**: `agent/fallback/fallback_handler.py` (MODIFY)

**Add validation-specific retry logic**:

```python
class FallbackHandler:
    """Handles retry logic with progressive reprompting."""
    
    def __init__(self, mode: str):
        self.mode = mode
        self.max_retries = RETRY_LIMITS.get(mode, 2)
        self.retry_count = 0
        self.validation_failures = []  # NEW: Track validation errors
    
    def should_retry(self, error_type: str) -> bool:
        """Determine if retry appropriate."""
        if self.retry_count >= self.max_retries:
            return False
        
        # Retry validation errors
        if error_type == "parameter_validation":
            return True
        
        # Don't retry user errors
        if error_type in ["validation_error", "user_input_error"]:
            return False
        
        # Retry LLM/system errors
        if error_type in ["llm_error", "tool_execution_error"]:
            return True
        
        return False
    
    def record_validation_failure(
        self,
        tool_name: str,
        errors: list[str],
    ):
        """Record validation failure for progressive reprompting."""
        self.validation_failures.append({
            "tool": tool_name,
            "errors": errors,
            "retry_count": self.retry_count,
        })
    
    def get_retry_message(self, error_context: dict | None = None) -> str:
        """
        Generate progressive reprompt.
        
        NEW: Include validation context.
        """
        if self.retry_count == 0:
            return "Por favor, revisa los parámetros e intenta de nuevo."
        
        elif self.retry_count == 1:
            # Add hints from validation errors
            if self.validation_failures:
                latest_failure = self.validation_failures[-1]
                return (
                    f"Faltan parámetros para {latest_failure['tool']}. "
                    f"Revisa: {', '.join(latest_failure['errors'])}"
                )
            return "Necesito que seas más específico. Intenta de nuevo."
        
        else:
            return "Parece que hay dificultades. Voy a escalarte con un humano."
    
    def increment_retry(self):
        """Increment retry counter."""
        self.retry_count += 1
        logger.info(
            "retry_incremented",
            mode=self.mode,
            retry_count=self.retry_count,
            max_retries=self.max_retries,
        )
```

#### 3.2 Integrate into BaseModeNode

**File**: `agent/modes/base_mode.py` (MODIFY)

**Add fallback to message processing loop**:

```python
class BaseModeNode:
    """Base class for mode nodes with retry logic."""
    
    def __init__(self, mode_name: str):
        self.mode_name = mode_name
        self.fallback_handler = FallbackHandler(mode_name)  # NEW
    
    async def _process_message(self, message, state):
        """Main message processing with retry logic."""
        
        # LLM loop (max 5 iterations)
        for iteration in range(5):
            logger.info("llm_iteration_start", iteration=iteration)
            
            # Call LLM
            response = await llm.ainvoke(messages)
            
            # Check for tool calls
            if not response.tool_calls:
                return {"ai_response": response.content}
            
            # Execute tool calls
            tool_results = []
            has_validation_error = False
            
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_kwargs = tool_call["args"]
                
                # Execute with validation
                result = await self._execute_and_log_tool(
                    tool_name,
                    tool_kwargs,
                    state["conversation_id"],
                )
                
                # Check for validation errors
                if not result.get("success") and result.get("error_type") == "parameter_validation":
                    has_validation_error = True
                    
                    # Record for retry
                    self.fallback_handler.record_validation_failure(
                        tool_name,
                        result.get("validation_errors", []),
                    )
                    
                    # Should retry?
                    if self.fallback_handler.should_retry("parameter_validation"):
                        self.fallback_handler.increment_retry()
                        
                        # Add reprompt message
                        retry_message = self.fallback_handler.get_retry_message(result)
                        
                        # Inject into conversation
                        messages.append({
                            "role": "assistant",
                            "content": retry_message,
                        })
                        
                        # Continue loop (retry)
                        break
                    else:
                        # Max retries reached - escalate
                        return {
                            "ai_response": "No pude procesar tu solicitud. Te voy a conectar con un humano.",
                            "should_escalate": True,
                            "escalation_reason": "max_validation_retries",
                        }
                
                tool_results.append(result)
            
            # If validation error, retry loop
            if has_validation_error and self.fallback_handler.should_retry("parameter_validation"):
                continue  # Next iteration
            
            # Otherwise, check for final response
            if self._should_end_loop(tool_results):
                return {
                    "ai_response": self._format_final_response(tool_results),
                }
        
        # Max iterations reached
        return {
            "ai_response": "Disculpa, necesito que reformules tu pregunta.",
        }
```

### Deliverables (Phase 3)

1. ✅ `agent/fallback/fallback_handler.py` - Enhanced retry logic
2. ✅ `agent/modes/base_mode.py` - Integrated retry in processing loop
3. ✅ `tests/agent/test_error_recovery.py` - Retry scenarios
4. ✅ Monitoring for retry rates per mode

### Success Criteria

- [ ] Validation errors trigger retry with reprompt
- [ ] Progressive reprompting includes validation context
- [ ] Max retries escalates to human
- [ ] Retry count logged for monitoring

---

## Phase 4: Defensive Tool Hardening (Week 4)

### Objective

Apply defensive programming patterns to 7 high-risk tools individually.

### Implementation Plan

#### 4.1 Extract Dynamic Validation Decorator

**File**: `agent/utils/tool_decorators.py` (NEW)

```python
"""
Decorators for defensive tool programming.

Extracted patterns from completar_elemento_actual.
"""

from functools import wraps
import structlog

logger = structlog.get_logger(__name__)


def validate_dynamic_params(required_fields_extractor):
    """
    Decorator: Validate dynamic parameters against DB schema.
    
    Args:
        required_fields_extractor: Function that returns list of required fields
    
    Usage:
        @validate_dynamic_params(lambda state: get_element_required_fields(state))
        @tool
        async def my_tool(**kwargs):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            from agent.state.helpers import get_current_state
            
            state = get_current_state()
            
            # Get required fields from DB
            required_fields = await required_fields_extractor(state)
            
            # Validate provided params
            missing_fields = []
            for field_def in required_fields:
                field_key = field_def["key"]
                is_required = field_def.get("required", False)
                
                if is_required and (field_key not in kwargs or not kwargs[field_key]):
                    missing_fields.append(field_def.get("name", field_key))
            
            # Return error if missing
            if missing_fields:
                logger.warning(
                    "dynamic_param_validation_failed",
                    tool=func.__name__,
                    missing_fields=missing_fields,
                )
                return {
                    "success": False,
                    "error": f"Faltan campos requeridos: {', '.join(missing_fields)}",
                    "missing_fields": missing_fields,
                    "required_fields": required_fields,
                }
            
            # Execute tool
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator
```

#### 4.2 Apply to High-Risk Tools

**Tools to harden**:

1. ✅ `completar_elemento_actual` - Already has pattern, extract to decorator
2. ✅ `actualizar_datos_personales` - Add defensive validation
3. ✅ `actualizar_datos_vehiculo` - Add format validation
4. ✅ `actualizar_taller` - Validate conditional requirements
5. ✅ `calcular_tarifa_con_elementos` - Add skip_validation default inference
6. ✅ `enviar_imagenes_ejemplo` - Add precio_comunicado check with fallback
7. ✅ `confirmar_expediente` - Validate case data completeness

**Example** (actualizar_datos_personales):

**Current**:
```python
@tool
async def actualizar_datos_personales(
    nombre: str,
    apellidos: str,
    dni: str,
    email: str,
    telefono: str,
) -> dict:
    """Update personal data."""
    # No validation
    # Just saves to DB
```

**Hardened**:
```python
@tool
async def actualizar_datos_personales(
    nombre: str,
    apellidos: str,
    dni: str,
    email: str,
    telefono: str,
) -> dict:
    """
    Update personal data with defensive validation.
    
    Validates formats BEFORE saving to DB.
    """
    from agent.utils.validation import validate_email, validate_phone, validate_dni
    
    errors = []
    
    # Validate email format
    if not validate_email(email):
        errors.append("Email inválido (formato: ejemplo@dominio.com)")
    
    # Validate phone format
    if not validate_phone(telefono):
        errors.append("Teléfono inválido (formato: +34600000000)")
    
    # Validate DNI format
    if not validate_dni(dni):
        errors.append("DNI/NIE inválido (formato: 12345678A o X1234567A)")
    
    # Return errors if any
    if errors:
        logger.warning(
            "personal_data_validation_failed",
            errors=errors,
        )
        return {
            "success": False,
            "error": "Datos personales inválidos",
            "validation_errors": errors,
        }
    
    # Save to DB (existing logic)
    # ...
```

### Deliverables (Phase 4)

1. ✅ `agent/utils/tool_decorators.py` - Reusable defensive patterns
2. ✅ Hardened versions of 7 high-risk tools
3. ✅ Tests for each hardened tool (validation scenarios)
4. ✅ Documentation of defensive patterns

### Success Criteria

- [ ] All 7 high-risk tools have defensive validation
- [ ] Dynamic param validation extracted to reusable decorator
- [ ] Format validation applied where relevant
- [ ] Tests cover validation edge cases

---

## Phase 5: Monitoring & Observability (Week 4)

### Objective

Add monitoring dashboards to track validation failures, retry rates, and error patterns.

### Implementation Plan

#### 5.1 Add Metrics to ToolValidationService

**File**: `agent/utils/tool_validation.py` (MODIFY)

```python
class ToolValidationService:
    """Validation service with metrics."""
    
    def __init__(self):
        self.syntax_validator = SyntaxValidator()
        self.state_validator = StateValidator()
        self.semantic_validator = SemanticValidator()
        
        # NEW: Metrics tracking
        self.validation_attempts = 0
        self.validation_failures = 0
        self.failure_by_tool = {}  # {tool_name: count}
        self.failure_by_type = {"syntax": 0, "state": 0, "semantic": 0}
    
    async def validate(self, tool, params, state):
        """Validate with metrics tracking."""
        self.validation_attempts += 1
        
        all_errors = []
        
        # Syntax
        is_valid, errors = await self.syntax_validator.validate(tool, params, state)
        if not is_valid:
            all_errors.extend(errors)
            self.failure_by_type["syntax"] += 1
        
        # State
        is_valid, errors = await self.state_validator.validate(tool, params, state)
        if not is_valid:
            all_errors.extend(errors)
            self.failure_by_type["state"] += 1
        
        # Semantic
        is_valid, errors = await self.semantic_validator.validate(tool, params, state)
        if not is_valid:
            all_errors.extend(errors)
            self.failure_by_type["semantic"] += 1
        
        # Track failures
        if all_errors:
            self.validation_failures += 1
            self.failure_by_tool[tool.name] = self.failure_by_tool.get(tool.name, 0) + 1
            
            # Log to Redis for monitoring
            await self._log_validation_failure(tool.name, all_errors)
        
        return (len(all_errors) == 0, all_errors)
    
    async def _log_validation_failure(self, tool_name: str, errors: list[str]):
        """Log validation failure to Redis for monitoring."""
        from shared.redis_client import get_redis_client
        from datetime import datetime, UTC
        
        redis = get_redis_client()
        
        # Increment daily counter
        date_key = datetime.now(UTC).strftime("%Y-%m-%d")
        await redis.hincrby(f"validation_failures:{date_key}", tool_name, 1)
        
        # Set expiry (30 days)
        await redis.expire(f"validation_failures:{date_key}", 30 * 24 * 60 * 60)
    
    def get_metrics(self) -> dict:
        """Get validation metrics."""
        failure_rate = (
            (self.validation_failures / self.validation_attempts * 100)
            if self.validation_attempts > 0
            else 0
        )
        
        return {
            "total_attempts": self.validation_attempts,
            "total_failures": self.validation_failures,
            "failure_rate_pct": round(failure_rate, 2),
            "failures_by_tool": self.failure_by_tool,
            "failures_by_type": self.failure_by_type,
        }
```

#### 5.2 Add Monitoring Endpoint

**File**: `api/routes/system.py` (MODIFY)

```python
@router.get("/validation-metrics")
async def get_validation_metrics(
    current_user: AdminUser = Depends(get_current_user),
):
    """Get tool validation metrics."""
    from agent.utils.tool_validation import get_tool_validator
    
    validator = get_tool_validator()
    metrics = validator.get_metrics()
    
    return {
        "metrics": metrics,
        "timestamp": datetime.now(UTC).isoformat(),
    }
```

#### 5.3 Create Monitoring Dashboard Query

**SQL for validation failure rate**:

```sql
-- Daily validation failures by tool
SELECT 
    tool_name,
    COUNT(*) as failures,
    DATE(created_at) as date
FROM tool_logs
WHERE success = FALSE
  AND error_type = 'parameter_validation'
  AND created_at > NOW() - INTERVAL '30 days'
GROUP BY tool_name, DATE(created_at)
ORDER BY date DESC, failures DESC;
```

### Deliverables (Phase 5)

1. ✅ Metrics tracking in ToolValidationService
2. ✅ Redis logging for daily counters
3. ✅ API endpoint for metrics
4. ✅ SQL queries for dashboard
5. ✅ Alert configuration (>5% failure rate)

### Success Criteria

- [ ] Validation failure rate tracked per tool
- [ ] Dashboard shows daily trends
- [ ] Alerts trigger on high failure rates
- [ ] Metrics help identify prompt gaps

---

## Testing Strategy

### Unit Tests

**Coverage Target**: 95%+ for validation code

**Files**:
- `tests/agent/utils/test_tool_validation.py` - All validators
- `tests/agent/utils/test_tool_decorators.py` - Defensive decorators
- `tests/agent/test_error_recovery.py` - Retry logic

**Scenarios**:
- ✅ Missing required parameters
- ✅ Wrong parameter types
- ✅ Missing state dependencies
- ✅ Invalid semantic values (categoria doesn't exist)
- ✅ Dynamic param validation
- ✅ Retry after validation error
- ✅ Max retries escalation

### Integration Tests

**File**: `tests/integration/test_validation_flow.py`

**Scenarios**:
- ✅ End-to-end: LLM forgets param → validation fails → retry → success
- ✅ End-to-end: LLM forgets param → max retries → escalation
- ✅ End-to-end: Semantic error (invalid category) → LLM fixes → success

### Load Testing

**Validate performance impact**:
- Baseline: Tool call latency without validation
- With validation: Latency increase should be <50ms
- Redis cache: Should reduce semantic validation latency to <10ms

---

## Risk Mitigation

### Risk 1: LangChain Introspection Fails

**Mitigation**:
- Test against all 30 tools
- Fallback: If `args_schema` is None, log warning and skip validation
- Document tools that need manual schema definition

### Risk 2: Validation Breaks Existing Tools

**Mitigation**:
- Implement validation as opt-out (not opt-in)
- Add feature flag: `ENABLE_PARAMETER_VALIDATION` (default=True)
- Gradual rollout: Enable for 1 mode at a time

### Risk 3: Performance Degradation

**Mitigation**:
- Redis caching for semantic validation
- Fast-fail on syntax errors (no DB check)
- Monitor P95 latency

### Risk 4: False Positives

**Mitigation**:
- Log all validation failures for review
- Add override mechanism for admins
- Tune STATE_REQUIREMENTS based on production data

---

## Rollout Plan

### Week 1: Phase 1 (Parameter Validation)

- Day 1-2: Implement validation infrastructure
- Day 3-4: Integrate into BaseModeNode
- Day 5: Testing and bug fixes

**Rollout**: Deploy to staging, test with synthetic conversations

### Week 2: Phase 2 (Semantic Validation)

- Day 1-2: Extend ConstraintService
- Day 3: Add SemanticValidator
- Day 4-5: Testing and caching

**Rollout**: Enable for PRESUPUESTO_MODE only, monitor for false positives

### Week 3: Phase 3 (Error Recovery)

- Day 1-2: Enhance FallbackHandler
- Day 3-4: Integrate retry logic
- Day 5: Testing

**Rollout**: Enable retry for all modes

### Week 4: Phases 4-5 (Hardening + Monitoring)

- Day 1-3: Harden 7 high-risk tools
- Day 4-5: Add monitoring and dashboards

**Rollout**: Full production deployment, monitor metrics

---

## Success Metrics

### Technical Metrics

- ✅ Validation coverage: 100% of tool calls
- ✅ Validation failure rate: <5% (after prompt improvements)
- ✅ False positive rate: <1%
- ✅ Retry success rate: >80% (LLM fixes params on retry)
- ✅ Latency impact: <50ms P95

### Business Metrics

- ✅ Cases with NULL tariff: 0% (down from ~10-20%)
- ✅ Expediente data completeness: 100%
- ✅ Escalations due to missing data: -90%
- ✅ Manual cleanup time: -80%

---

## Appendices

### Appendix A: All 30 Tools Parameter Analysis

[Complete table with all tools, parameters, risk scores]

### Appendix B: State Requirements Map

[Complete map of tool_name → required state keys]

### Appendix C: Validation Error Message Templates

[Templates for all validation error types]

### Appendix D: Migration Guide

[Guide for adding validation to new tools]

---

## Questions for Review

1. **Phase prioritization**: Should we do phases in order, or prioritize Phase 4 (hardening) for the 7 high-risk tools first?

2. **Rollout strategy**: Gradual (1 mode at a time) or Big Bang (all modes)?

3. **Feature flag**: Should validation be opt-in or opt-out initially?

4. **Prompt improvements**: Should we couple this with Phase 2 of the previous plan (systematic prompt enhancement)?

5. **Testing scope**: Is 95% coverage target realistic for Week 1, or should we aim for 80% and iterate?

---

**Plan Status**: ✅ READY FOR ARCHITECT REVIEW  
**Next Step**: Review with stakeholders, get approval, begin Week 1 implementation

**Created by**: architect (based on investigator-dev comprehensive analysis)  
**Date**: February 7, 2026
