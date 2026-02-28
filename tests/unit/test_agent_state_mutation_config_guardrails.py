import ast
from pathlib import Path

import pytest

from agent.state.mutation_config import build_state_mutation_config


@pytest.mark.unit
def test_build_state_mutation_config_keeps_only_thread_id() -> None:
    mutation_config = build_state_mutation_config(
        {
            "configurable": {
                "thread_id": "conv-123",
                "checkpoint_ns": "conversation",
                "checkpoint_id": "cp-1",
            }
        }
    )

    assert mutation_config == {"configurable": {"thread_id": "conv-123"}}
    assert "checkpoint_ns" not in mutation_config["configurable"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "invalid_config",
    [
        {},
        {"configurable": {}},
        {"configurable": {"thread_id": ""}},
        {"configurable": {"thread_id": None}},
    ],
)
def test_build_state_mutation_config_requires_thread_id(invalid_config: dict) -> None:
    with pytest.raises(ValueError, match="thread_id|configurable"):
        build_state_mutation_config(invalid_config)


def _is_builder_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Name):
        return node.func.id == "build_state_mutation_config"
    if isinstance(node.func, ast.Attribute):
        return node.func.attr == "build_state_mutation_config"
    return False


def _iter_aupdate_state_calls(tree: ast.AST) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "aupdate_state":
                calls.append(node)
    return calls


@pytest.mark.unit
def test_agent_aupdate_state_uses_mutation_config_builder() -> None:
    agent_root = Path(__file__).resolve().parents[2] / "agent"
    violations: list[str] = []

    for path in agent_root.rglob("*.py"):
        if "archive" in path.parts:
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"))
        for call in _iter_aupdate_state_calls(tree):
            first_arg = call.args[0] if call.args else None
            if first_arg is None and call.keywords:
                for keyword in call.keywords:
                    if keyword.arg == "config":
                        first_arg = keyword.value
                        break

            if not _is_builder_call(first_arg):
                violations.append(f"{path}:{call.lineno}")

    assert not violations, (
        "All agent graph.aupdate_state calls must pass build_state_mutation_config(...) "
        f"as config. Violations: {', '.join(violations)}"
    )
