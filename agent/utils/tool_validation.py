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

        Args:
            tool: LangChain tool instance
            params: Parameters provided by LLM
            state: Current conversation state

        Returns:
            Tuple of (is_valid, errors)
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
_validator_instance: ToolValidationService | None = None


def get_tool_validator() -> ToolValidationService:
    """Get singleton ToolValidationService."""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = ToolValidationService()
    return _validator_instance
