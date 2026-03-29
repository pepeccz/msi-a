"""
Tool parameter validation utilities.

Validates tool calls BEFORE execution to prevent:
- Missing required parameters
- Invalid parameter types
- Missing state dependencies

This implements Phase 1 of the defensive parameter validation system.
See: docs/plans/defensive-parameter-validation-system.md
"""

from __future__ import annotations

import structlog
from typing import Any, Protocol
from langchain_core.tools import BaseTool

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
        """
        Validate required parameters are present and types are correct.

        Args:
            tool: LangChain tool instance
            params: Parameters provided by LLM
            state: Current conversation state (unused in syntax validation)

        Returns:
            Tuple of (is_valid, errors)
        """
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

        # Check each field (Pydantic v2 API)
        for field_name, field_info in schema.model_fields.items():
            # Required field missing?
            if field_info.is_required() and field_name not in params:
                errors.append(f"Missing required parameter: {field_name}")

            # Type check (basic)
            if field_name in params and params[field_name] is not None:
                # Get expected type from annotation
                expected_type = field_info.annotation
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
        """
        Validate required state exists.

        Args:
            tool: LangChain tool instance
            params: Parameters provided by LLM (unused in state validation)
            state: Current conversation state

        Returns:
            Tuple of (is_valid, errors)
        """
        tool_name = tool.name

        if tool_name not in self.STATE_REQUIREMENTS:
            # No state requirements for this tool
            return (True, [])

        errors = []
        required_keys = self.STATE_REQUIREMENTS[tool_name]

        # In EXPEDIENTE_MODE, precio_comunicado is guaranteed (precondition
        # for reaching this mode) — skip state checks that only apply to
        # PRESUPUESTO_MODE.
        current_mode = state.get("current_mode", "")
        skip_keys: set[str] = set()
        if current_mode == "EXPEDIENTE_MODE":
            skip_keys.add("precio_comunicado")

        for key in required_keys:
            if key in skip_keys:
                continue
            if key not in state or state[key] is None:
                errors.append(f"Required state missing: {key}")

        if errors:
            logger.warning(
                "state_validation_failed",
                tool_name=tool_name,
                errors=errors,
                state_keys=list(state.keys()),
            )

        return (len(errors) == 0, errors)


class SemanticValidator:
    """
    Validates parameter semantics (database checks).

    Checks that parameter values are valid by verifying them against the database:
    - categoria_slug exists in vehicle_categories
    - element_code exists in elements for given category
    - case_id exists and is active
    - user_id exists
    - tier_id exists for given category

    Uses Redis caching (5-min TTL) to minimize database load.
    """

    # Map tool parameters to validation functions
    # Format: param_name -> (validator_func, depends_on_params)
    PARAM_VALIDATORS = {
        "categoria_slug": (None, []),  # Set dynamically to avoid import issues
        "element_code": (None, ["categoria_slug"]),
        "case_id": (None, []),
        "user_id": (None, []),
        "tier_id": (None, ["categoria_slug"]),
    }

    # Map tool names to parameters that need semantic validation
    TOOL_VALIDATIONS = {
        "identificar_y_resolver_elementos": ["categoria_slug"],
        "calcular_tarifa_con_elementos": ["categoria_slug"],
        "iniciar_expediente": ["categoria_slug", "tier_id"],
        "actualizar_datos_personales": ["case_id"],
        "actualizar_datos_vehiculo": ["case_id"],
        "completar_elemento_actual": ["case_id"],
        "actualizar_taller": ["case_id"],
        "confirmar_expediente": ["case_id"],
        "seleccionar_variante_por_respuesta": ["categoria_slug"],
        "obtener_campos_elemento": ["element_code", "categoria_slug"],
        "guardar_datos_elemento": ["case_id", "element_code", "categoria_slug"],
        "confirmar_fotos_elemento": ["case_id"],
        "listar_categorias": [],  # No validation needed
        "verificar_warnings": ["categoria_slug"],
    }

    async def validate(
        self,
        tool: BaseTool,
        params: dict[str, Any],
        state: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """
        Validate parameter semantics against database.

        Args:
            tool: LangChain tool instance
            params: Parameters provided by LLM
            state: Current conversation state

        Returns:
            Tuple of (is_valid, errors)
        """
        from agent.services.constraint_service import (
            validate_categoria_slug,
            validate_element_code,
            validate_case_id,
            validate_user_id,
            validate_tier_id,
        )

        tool_name = tool.name

        # Check if this tool needs semantic validation
        if tool_name not in self.TOOL_VALIDATIONS:
            return (True, [])

        errors = []
        params_to_validate = self.TOOL_VALIDATIONS[tool_name]

        for param_name in params_to_validate:
            # Get param value (from params or state)
            param_value = params.get(param_name) or state.get(param_name)

            if not param_value:
                # Param not provided (syntax validator should catch this)
                continue

            # Run appropriate validator
            try:
                if param_name == "categoria_slug":
                    is_valid, error = await validate_categoria_slug(param_value)
                    if not is_valid:
                        errors.append(error)

                elif param_name == "element_code":
                    # element_code validation needs categoria_slug
                    categoria_slug = params.get("categoria_slug") or state.get(
                        "categoria_slug"
                    )
                    if not categoria_slug:
                        logger.warning(
                            "element_code_validation_skipped_no_category",
                            tool_name=tool_name,
                        )
                        errors.append(
                            f"Cannot validate element_code '{param_value}': categoria_slug is required"
                        )
                        continue

                    is_valid, error = await validate_element_code(
                        param_value,
                        categoria_slug,
                    )
                    if not is_valid:
                        errors.append(error)

                elif param_name == "case_id":
                    is_valid, error = await validate_case_id(param_value)
                    if not is_valid:
                        errors.append(error)

                elif param_name == "user_id":
                    is_valid, error = await validate_user_id(param_value)
                    if not is_valid:
                        errors.append(error)

                elif param_name == "tier_id":
                    # tier_id validation needs categoria_slug
                    categoria_slug = params.get("categoria_slug") or state.get(
                        "categoria_slug"
                    )
                    if not categoria_slug:
                        logger.warning(
                            "tier_id_validation_skipped_no_category",
                            tool_name=tool_name,
                        )
                        errors.append(
                            f"Cannot validate tier_id '{param_value}': categoria_slug is required"
                        )
                        continue

                    is_valid, error = await validate_tier_id(
                        param_value,
                        categoria_slug,
                    )
                    if not is_valid:
                        errors.append(error)

            except Exception as e:
                # Fail-safe: Log error but don't crash validation
                logger.error(
                    "semantic_validation_error",
                    tool_name=tool_name,
                    param_name=param_name,
                    error=str(e),
                )
                # Don't add to errors list - fail open

        if errors:
            logger.warning(
                "semantic_validation_failed",
                tool_name=tool_name,
                errors=errors,
            )

        return (len(errors) == 0, errors)


class ToolValidationService:
    """
    Coordinates all validation layers.

    Usage:
        validator = ToolValidationService()
        is_valid, errors, failed_layer = await validator.validate(tool, params, state)
    """

    def __init__(self):
        self.syntax_validator = SyntaxValidator()
        self.state_validator = StateValidator()
        self.semantic_validator = SemanticValidator()  # Phase 2: DB validation

    async def validate(
        self,
        tool: BaseTool,
        params: dict[str, Any],
        state: dict[str, Any],
    ) -> tuple[bool, list[str], str]:
        """
        Run all validation layers (Phase 3: now returns failed layer).

        Fast-fails on syntax/state errors (no DB checks if those fail).

        Args:
            tool: LangChain tool instance
            params: Parameters provided by LLM
            state: Current conversation state

        Returns:
            Tuple of (is_valid, errors, failed_layer)

            failed_layer values:
            - "syntax": Syntax validation failed
            - "state": State validation failed
            - "semantic": Semantic/DB validation failed
            - "none": All validations passed
        """
        all_errors = []

        # Layer 1: Syntax validation (fast)
        is_valid, errors = await self.syntax_validator.validate(tool, params, state)
        if not is_valid:
            all_errors.extend(errors)
            # Fast fail - don't do state/semantic checks if syntax invalid
            logger.warning(
                "tool_validation_failed",
                tool_name=tool.name,
                layer="syntax",
                errors=all_errors,
            )
            return (False, all_errors, "syntax")

        # Layer 2: State validation (fast)
        is_valid, errors = await self.state_validator.validate(tool, params, state)
        if not is_valid:
            all_errors.extend(errors)
            # Fast fail - don't do DB checks if state invalid
            logger.warning(
                "tool_validation_failed",
                tool_name=tool.name,
                layer="state",
                errors=all_errors,
            )
            return (False, all_errors, "state")

        # Layer 3: Semantic validation (DB checks) - Phase 2
        is_valid, errors = await self.semantic_validator.validate(tool, params, state)
        if not is_valid:
            all_errors.extend(errors)
            logger.warning(
                "tool_validation_failed",
                tool_name=tool.name,
                layer="semantic",
                errors=all_errors,
            )
            return (False, all_errors, "semantic")

        logger.info(
            "tool_validation_passed",
            tool_name=tool.name,
        )
        return (True, [], "none")


# Singleton instance
_validator_instance: ToolValidationService | None = None


def get_tool_validator() -> ToolValidationService:
    """Get singleton ToolValidationService."""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = ToolValidationService()
    return _validator_instance
