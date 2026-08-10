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


# ---------------------------------------------------------------------------
# as_node explicit-value guardrail (fix-resume-bot-ambiguous-update).
# Deliberately a SEPARATE function from test_agent_aupdate_state_uses_
# mutation_config_builder above, which is already RED today on an unrelated
# pre-existing violation (agent/main.py:1518, tracked separately) — this
# guardrail must not inherit that failure.
# ---------------------------------------------------------------------------

_AS_NODE_EXEMPT_FILES: frozenset[str] = frozenset(
    {
        # agent/main.py's 4 aupdate_state call sites run AFTER a completed
        # graph.ainvoke(), so versions_seen is already populated and
        # LangGraph's as_node inference resolves correctly today. Adding
        # as_node there would write a "branch:to:preprocess" checkpoint
        # entry and could alter next-turn routing in the ~90%-traffic hot
        # path (PRE_EXPEDIENTE_MODE). Approved non-goal for
        # fix-resume-bot-ambiguous-update; tracked as a separate follow-up.
        "agent/main.py",
    }
)


def _is_state_mutation_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"aupdate_state", "update_state"}
    )


def _keyword_value_is_as_node_constant(value: ast.AST) -> bool:
    if isinstance(value, ast.Name):
        return value.id == "STATE_MUTATION_AS_NODE"
    if isinstance(value, ast.Attribute):
        return value.attr == "STATE_MUTATION_AS_NODE"
    return False


@pytest.mark.unit
def test_state_mutation_calls_pass_explicit_as_node() -> None:
    """Every in-scope aupdate_state/update_state call passes as_node explicitly,
    resolving to STATE_MUTATION_AS_NODE (not merely any literal), so a stray
    "preprocess" string can never silently drift from the graph."""
    repo_root = Path(__file__).resolve().parents[2]
    scan_roots = [repo_root / "agent", repo_root / "api"]

    violations: list[str] = []

    for scan_root in scan_roots:
        for path in scan_root.rglob("*.py"):
            if "archive" in path.parts:
                continue

            relative_path = path.relative_to(repo_root).as_posix()
            if relative_path in _AS_NODE_EXEMPT_FILES:
                continue

            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not _is_state_mutation_call(node):
                    continue

                as_node_keyword = next(
                    (kw for kw in node.keywords if kw.arg == "as_node"), None
                )
                if as_node_keyword is None or not _keyword_value_is_as_node_constant(
                    as_node_keyword.value
                ):
                    violations.append(f"{relative_path}:{node.lineno}")

    assert not violations, (
        "All graph.aupdate_state/update_state calls under agent/ and api/ "
        "(except _AS_NODE_EXEMPT_FILES) must pass as_node=STATE_MUTATION_AS_NODE "
        f"explicitly. Violations: {', '.join(violations)}"
    )


@pytest.mark.integration
def test_state_mutation_as_node_matches_graph_entry_node() -> None:
    """STATE_MUTATION_AS_NODE must name a real node in the compiled graph.

    Load-bearing: an as_node value naming an absent node raises a DIFFERENT
    LangGraph error ("Node X does not exist"), turning this fix into a new 500.
    """
    from agent.graph.conversation_graph import NODE_PREPROCESS, build_conversation_graph
    from agent.state.mutation_config import STATE_MUTATION_AS_NODE

    assert STATE_MUTATION_AS_NODE == NODE_PREPROCESS

    graph_builder = build_conversation_graph()
    assert STATE_MUTATION_AS_NODE in graph_builder.nodes
