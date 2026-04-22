"""
Unit tests for fix-broken-imports: import resolution.

T4.1  _get_category_id_by_slug can be imported from agent.services.case_service
      (regression guard: NOT from agent.tools.case_tools)

T4.4  _load_user_data_for_case can be imported from agent.services.case_service
      (regression guard: NOT from agent.tools.case_tools)
"""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub heavy optional deps so the module tree loads without full Docker stack.
# These must come BEFORE any agent.* imports.
# ---------------------------------------------------------------------------
sys.modules.setdefault("phonenumbers", types.ModuleType("phonenumbers"))

# Minimal langchain_openai stub — expediente_mode imports ChatOpenAI at top level
if "langchain_openai" not in sys.modules:
    _lco_stub = types.ModuleType("langchain_openai")
    _lco_stub.ChatOpenAI = MagicMock  # type: ignore[attr-defined]
    sys.modules["langchain_openai"] = _lco_stub

# Minimal langchain_core stubs required by base_mode / generic_loop
for _mod in [
    "langchain_core",
    "langchain_core.messages",
    "langchain_core.tools",
    "langchain_core.runnables",
]:
    sys.modules.setdefault(_mod, types.ModuleType(_mod))


# ---------------------------------------------------------------------------
# T4.1 — _get_category_id_by_slug importable from agent.services.case_service
# ---------------------------------------------------------------------------


class TestT41ImportGetCategoryIdBySlug:
    """T4.1: _get_category_id_by_slug MUST live in agent.services.case_service."""

    def test_symbol_exists_in_case_service(self) -> None:
        """The refactored helper is importable from its new home."""
        # This import must not raise ImportError.
        from agent.services.case_service import _get_category_id_by_slug  # noqa: F401

        # The symbol must be callable (async function).
        import asyncio
        import inspect

        assert callable(_get_category_id_by_slug), (
            "_get_category_id_by_slug must be callable"
        )
        assert inspect.iscoroutinefunction(_get_category_id_by_slug), (
            "_get_category_id_by_slug must be async"
        )

    def test_symbol_absent_from_case_tools(self) -> None:
        """The helper MUST NOT be defined in agent.tools.case_tools (it was moved)."""
        import importlib

        case_tools = importlib.import_module("agent.tools.case_tools")
        assert not hasattr(case_tools, "_get_category_id_by_slug"), (
            "_get_category_id_by_slug should NOT be in agent.tools.case_tools — "
            "it was moved to agent.services.case_service in the tools-refactor. "
            "If it reappears here, it will shadow the service version."
        )


# ---------------------------------------------------------------------------
# T4.4 — _load_user_data_for_case importable from agent.services.case_service
# ---------------------------------------------------------------------------


class TestT44ImportLoadUserDataForCase:
    """T4.4: _load_user_data_for_case MUST live in agent.services.case_service."""

    def test_symbol_exists_in_case_service(self) -> None:
        """The refactored helper is importable from its new home."""
        from agent.services.case_service import _load_user_data_for_case  # noqa: F401

        import inspect

        assert callable(_load_user_data_for_case), (
            "_load_user_data_for_case must be callable"
        )
        assert inspect.iscoroutinefunction(_load_user_data_for_case), (
            "_load_user_data_for_case must be async"
        )

    def test_symbol_absent_from_case_tools(self) -> None:
        """The helper MUST NOT be defined in agent.tools.case_tools (it was moved)."""
        import importlib

        case_tools = importlib.import_module("agent.tools.case_tools")
        assert not hasattr(case_tools, "_load_user_data_for_case"), (
            "_load_user_data_for_case should NOT be in agent.tools.case_tools — "
            "it was moved to agent.services.case_service."
        )


