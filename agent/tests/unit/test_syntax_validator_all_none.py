"""Tests for SyntaxValidator all-None payload guard.

Task 3.1 [RED] / 3.2 [GREEN]: SyntaxValidator must reject calls where
all payload params are None or empty dict for tools in REQUIRE_AT_LEAST_ONE.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from pydantic import BaseModel, Field

from agent.utils.tool_validation import SyntaxValidator


def _make_tool(name: str, schema: type[BaseModel]) -> MagicMock:
    """Create a mock tool with the given name and schema."""
    tool = MagicMock()
    tool.name = name
    tool.args_schema = schema
    return tool


class DummyAllOptionalSchema(BaseModel):
    """Schema where all params are optional — simulates the old bug."""

    taller_propio: bool | None = Field(default=None)
    datos_taller: dict[str, str] | None = Field(default=None)


class DummyRequiredSchema(BaseModel):
    """Schema with a required param."""

    datos_personales: dict[str, str] = Field()


class TestSyntaxValidatorAllNoneGuard:
    """SyntaxValidator must reject all-None payloads for guarded tools."""

    @pytest.mark.asyncio
    async def test_rejects_all_none_for_guarded_tool(self):
        """Calling a guarded tool with all-None params must fail."""
        tool = _make_tool("actualizar_datos_taller", DummyAllOptionalSchema)
        validator = SyntaxValidator()

        is_valid, errors = await validator.validate(tool, {}, {})

        assert is_valid is False
        assert any("payload" in e.lower() or "none" in e.lower() for e in errors)

    @pytest.mark.asyncio
    async def test_accepts_non_none_for_guarded_tool(self):
        """Calling a guarded tool with at least one non-None param must pass."""
        tool = _make_tool("actualizar_datos_taller", DummyAllOptionalSchema)
        validator = SyntaxValidator()

        is_valid, errors = await validator.validate(
            tool, {"taller_propio": False}, {}
        )

        assert is_valid is True
        assert errors == []

    @pytest.mark.asyncio
    async def test_non_guarded_tool_passes_with_empty(self):
        """Tools NOT in REQUIRE_AT_LEAST_ONE should pass even with empty params."""
        tool = _make_tool("some_other_tool", DummyAllOptionalSchema)
        validator = SyntaxValidator()

        is_valid, errors = await validator.validate(tool, {}, {})

        assert is_valid is True
        assert errors == []

    @pytest.mark.asyncio
    async def test_required_field_still_caught(self):
        """Required fields must still be caught by existing logic."""
        tool = _make_tool("actualizar_datos_personales", DummyRequiredSchema)
        validator = SyntaxValidator()

        is_valid, errors = await validator.validate(tool, {}, {})

        assert is_valid is False
        assert any("datos_personales" in e for e in errors)
