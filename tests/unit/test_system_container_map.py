"""
Tests: CONTAINER_MAP in api/routes/system.py should NOT contain stale RAG services.

After the RAG stack was removed, "qdrant" and "document-processor" entries must
be removed from CONTAINER_MAP so the admin system page doesn't show phantom services.

Import strategy: read CONTAINER_MAP by parsing the source file directly (ast.literal_eval
on the dict literal). This avoids any import-time side effects on sys.modules.
"""

import ast
from pathlib import Path


def _load_container_map_from_source() -> dict:
    """
    Parse CONTAINER_MAP from api/routes/system.py source without importing.

    Finds the dict literal assigned to CONTAINER_MAP and evaluates it safely
    via ast.literal_eval — no imports, no side effects.
    """
    source_path = Path(__file__).parents[2] / "api" / "routes" / "system.py"
    source = source_path.read_text()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "CONTAINER_MAP"
            and isinstance(node.value, ast.Dict)
        ):
            return ast.literal_eval(node.value)

    raise RuntimeError("CONTAINER_MAP dict literal not found in api/routes/system.py")


CONTAINER_MAP = _load_container_map_from_source()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_container_map_does_not_contain_qdrant() -> None:
    """CONTAINER_MAP must not list 'qdrant' — the service was removed with the RAG stack."""
    assert "qdrant" not in CONTAINER_MAP, (
        f"CONTAINER_MAP still contains stale 'qdrant' entry: {CONTAINER_MAP}"
    )


def test_container_map_does_not_contain_document_processor() -> None:
    """CONTAINER_MAP must not list 'document-processor' — removed with the RAG stack."""
    assert "document-processor" not in CONTAINER_MAP, (
        f"CONTAINER_MAP still contains stale 'document-processor' entry: {CONTAINER_MAP}"
    )


def test_container_map_contains_live_services() -> None:
    """Smoke test: all expected live services are present in CONTAINER_MAP."""
    expected_live = {"api", "agent", "postgres", "redis", "admin-panel", "ollama"}
    for service in expected_live:
        assert service in CONTAINER_MAP, (
            f"Live service '{service}' is missing from CONTAINER_MAP"
        )
