"""
WS3 — Recursion Limit Tests.

Verifies that build_mode_tool_loop() returns a ToolLoopResult NamedTuple
with .graph and .recursion_limit fields, and that no legacy custom-attribute
or compiled.config-patch patterns remain.
"""

import ast
import inspect
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stubs (mirror tests/agent/conftest.py)
# ---------------------------------------------------------------------------
if "structlog" not in sys.modules:
    _structlog = types.ModuleType("structlog")
    _structlog.get_logger = lambda *a, **kw: MagicMock()  # type: ignore[attr-defined]
    sys.modules["structlog"] = _structlog

for _mod in ("langgraph.checkpoint.redis", "langgraph.checkpoint.redis.aio"):
    if _mod not in sys.modules:
        _stub = types.ModuleType(_mod)
        _stub.AsyncRedisSaver = MagicMock()  # type: ignore[attr-defined]
        sys.modules[_mod] = _stub


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_config():
    """Return a ModeLoopConfig with a stub LLM override so no Settings needed."""
    from agent.modes.tool_loop import ModeLoopConfig

    mock_llm = MagicMock()
    mock_llm.bind_tools = lambda tools, **kw: mock_llm
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(tool_calls=[], content="ok"))

    return ModeLoopConfig(
        mode_name="TEST_MODE",
        get_tools=lambda ctx: [],
        get_system_prompt=lambda state: "test prompt",
        post_tool_hook=None,
        max_iterations=10,
        _llm_override=mock_llm,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_mode_tool_loop_returns_named_tuple():
    """build_mode_tool_loop() must return an object with .graph and .recursion_limit."""
    from agent.modes.tool_loop import build_mode_tool_loop

    config = _make_minimal_config()
    result = build_mode_tool_loop(config)

    assert hasattr(result, "graph"), "ToolLoopResult must have .graph attribute"
    assert hasattr(result, "recursion_limit"), "ToolLoopResult must have .recursion_limit attribute"


def test_tool_loop_recursion_limit_formula():
    """recursion_limit must equal max_iterations * 3 + 5 (35 for default 10)."""
    from agent.modes.tool_loop import build_mode_tool_loop

    config = _make_minimal_config()
    result = build_mode_tool_loop(config)

    expected = config.max_iterations * 3 + 5  # 35 for max_iterations=10
    assert result.recursion_limit == expected, (
        f"Expected recursion_limit={expected}, got {result.recursion_limit}"
    )


def test_no_custom_recursion_limit_attribute():
    """The compiled graph must NOT have _msia_recursion_limit attribute."""
    from agent.modes.tool_loop import build_mode_tool_loop

    config = _make_minimal_config()
    result = build_mode_tool_loop(config)

    assert not hasattr(result.graph, "_msia_recursion_limit"), (
        "_msia_recursion_limit should not exist on the compiled graph — "
        "recursion_limit must be passed at ainvoke() time"
    )


def test_no_compiled_config_patch():
    """conversation_graph.py must not contain a compiled.config assignment patch."""
    import ast
    import pathlib

    source_path = pathlib.Path(
        "/home/pepe/Proyectos/msi-a/agent/graph/conversation_graph.py"
    )
    source = source_path.read_text()

    # Parse AST and look for compiled.config = ... assignments
    tree = ast.parse(source)

    config_assignments = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and target.attr == "config"
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "compiled"
                ):
                    config_assignments.append(node.lineno)

    assert not config_assignments, (
        f"Found compiled.config assignment(s) at line(s) {config_assignments} in "
        "conversation_graph.py — this try/except patch should be removed. "
        "Pass recursion_limit in ainvoke() instead."
    )
