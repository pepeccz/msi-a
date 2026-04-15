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

    # Tools where passing all-None/empty params is invalid.
    # Belt-and-suspenders for tools with optional-only schemas.
    REQUIRE_AT_LEAST_ONE: frozenset[str] = frozenset({
        "actualizar_datos_taller",
    })

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

        # All-None guard: reject calls where every payload param is None/empty
        if (
            not errors
            and tool.name in self.REQUIRE_AT_LEAST_ONE
            and schema
        ):
            all_none = all(
                params.get(fname) is None or params.get(fname) == {}
                for fname, finfo in schema.model_fields.items()
            )
            if all_none:
                errors.append(
                    f"All payload parameters are None or empty for {tool.name}. "
                    f"At least one must have a value."
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
    # NOTE: Only include keys that are TRUE state dependencies (not available
    # as direct tool parameters). calcular_tarifa_con_elementos receives
    # categoria_vehiculo as a direct parameter — no state dependency needed.
    STATE_REQUIREMENTS = {
        "iniciar_expediente": ["categoria_slug", "user_id"],
        "actualizar_datos_personales": ["case_id"],
        "actualizar_datos_vehiculo": ["case_id"],
        "completar_elemento_actual": ["case_id", "current_element_index"],
        "actualizar_taller": ["case_id"],
        "confirmar_expediente": ["case_id"],
        "enviar_imagenes_ejemplo": ["precio_comunicado"],
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

    async def validate(
        self,
        tool: BaseTool,
        params: dict[str, Any],
        state: dict[str, Any],
    ) -> tuple[bool, list[str], str]:
        """
        Run all validation layers.

        Fast-fails on syntax errors (no state checks if syntax fails).

        Args:
            tool: LangChain tool instance
            params: Parameters provided by LLM
            state: Current conversation state

        Returns:
            Tuple of (is_valid, errors, failed_layer)

            failed_layer values:
            - "syntax": Syntax validation failed
            - "state": State validation failed
            - "none": All validations passed
        """
        all_errors = []

        # Layer 1: Syntax validation (fast)
        is_valid, errors = await self.syntax_validator.validate(tool, params, state)
        if not is_valid:
            all_errors.extend(errors)
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
            logger.warning(
                "tool_validation_failed",
                tool_name=tool.name,
                layer="state",
                errors=all_errors,
            )
            return (False, all_errors, "state")

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
