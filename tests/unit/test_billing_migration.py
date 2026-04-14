"""
Tests for Billing Migration — Task 3 (044_billing_tables)

All tests use AST parsing and raw file inspection to avoid importing
the migration module directly (alembic is not available outside Docker).

Requirements verified:
  - Migration file exists and has correct structure
  - downgrade() is not empty / not a pass-only function
  - uix_invoices_period_active partial unique index is present
  - 'invoices' table name appears in the migration
  - 'payments' table name appears in the migration
  - down_revision points to the correct predecessor
  - upgrade() and downgrade() functions are defined
"""

from __future__ import annotations

import ast
from pathlib import Path

MIGRATION_PATH = Path(__file__).parents[2] / "database" / "alembic" / "versions" / "044_billing_tables.py"


def _parse_migration() -> ast.Module:
    """Parse the migration file into an AST module."""
    source = MIGRATION_PATH.read_text()
    return ast.parse(source)


def _get_function_node(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    """Return the FunctionDef node with the given name, or None."""
    return next(
        (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name),
        None,
    )


def _get_function_source(fn_name: str) -> str:
    """Extract the source lines of a named function from the migration file."""
    source = MIGRATION_PATH.read_text()
    tree = ast.parse(source)
    lines = source.splitlines()
    fn_node = _get_function_node(tree, fn_name)
    assert fn_node is not None, f"Function '{fn_name}' not found in migration"
    start = fn_node.lineno - 1
    end = fn_node.end_lineno
    return "\n".join(lines[start:end])


def _get_string_assignments(tree: ast.Module) -> dict[str, str]:
    """Return module-level string assignments as {name: value}.

    Handles both plain assignments (x = "v") and annotated assignments
    (x: str = "v"), which is the pattern used in Alembic migration headers.
    """
    assignments: dict[str, str] = {}
    for node in ast.walk(tree):
        # Plain assignment: revision = "044_billing_tables"
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                    assignments[target.id] = node.value.value
        # Annotated assignment: revision: str = "044_billing_tables"
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.value and isinstance(node.value, ast.Constant):
                assignments[node.target.id] = node.value.value
    return assignments


class TestMigrationFileExists:
    """Migration file must exist on disk."""

    def test_migration_file_exists(self) -> None:
        """044_billing_tables.py must exist in alembic/versions/."""
        assert MIGRATION_PATH.exists(), (
            f"Migration file not found at {MIGRATION_PATH}"
        )


class TestMigrationStructure:
    """Migration file must define upgrade() and downgrade() functions."""

    def test_migration_has_upgrade_function(self) -> None:
        """Migration must define an upgrade() function."""
        tree = _parse_migration()
        fn = _get_function_node(tree, "upgrade")
        assert fn is not None, "Migration is missing the upgrade() function"

    def test_migration_has_downgrade_function(self) -> None:
        """Migration must define a downgrade() function."""
        tree = _parse_migration()
        fn = _get_function_node(tree, "downgrade")
        assert fn is not None, "Migration is missing the downgrade() function"


class TestMigrationRevision:
    """Migration must have correct revision metadata."""

    def test_revision_id(self) -> None:
        """revision must be '044_billing_tables'."""
        tree = _parse_migration()
        assignments = _get_string_assignments(tree)
        assert assignments.get("revision") == "044_billing_tables", (
            f"Expected revision='044_billing_tables' but got {assignments.get('revision')!r}"
        )

    def test_down_revision_points_to_043(self) -> None:
        """down_revision must point to 043_case_lifecycle_fields."""
        tree = _parse_migration()
        assignments = _get_string_assignments(tree)
        assert assignments.get("down_revision") == "043_case_lifecycle_fields", (
            f"Expected down_revision='043_case_lifecycle_fields' but got {assignments.get('down_revision')!r}"
        )


class TestMigrationDowngradeNotEmpty:
    """downgrade() must not be a no-op (never pass)."""

    def test_downgrade_is_not_pass_only(self) -> None:
        """downgrade() must contain real drop statements, not just pass."""
        tree = _parse_migration()
        downgrade_fn = _get_function_node(tree, "downgrade")
        assert downgrade_fn is not None, "downgrade() function not found in AST"

        # A pass-only function body has exactly one statement: ast.Pass
        body = downgrade_fn.body
        is_pass_only = len(body) == 1 and isinstance(body[0], ast.Pass)
        assert not is_pass_only, (
            "downgrade() is a no-op (pass only) — it must drop tables and indexes"
        )

    def test_downgrade_source_contains_drop_table(self) -> None:
        """downgrade() source must include drop_table calls."""
        source = _get_function_source("downgrade")
        assert "drop_table" in source, (
            "downgrade() must call op.drop_table() to revert the migration"
        )

    def test_downgrade_source_contains_drop_index(self) -> None:
        """downgrade() source must drop indexes created in upgrade()."""
        source = _get_function_source("downgrade")
        assert "drop_index" in source or "DROP INDEX" in source, (
            "downgrade() must drop indexes created in upgrade()"
        )


class TestMigrationTablesPresent:
    """Both 'invoices' and 'payments' must appear in the migration."""

    def test_invoices_table_in_migration(self) -> None:
        """'invoices' must appear in the migration file."""
        source = MIGRATION_PATH.read_text()
        assert "invoices" in source, (
            "Migration does not reference the 'invoices' table"
        )

    def test_payments_table_in_migration(self) -> None:
        """'payments' must appear in the migration file."""
        source = MIGRATION_PATH.read_text()
        assert "payments" in source, (
            "Migration does not reference the 'payments' table"
        )


class TestMigrationPartialUniqueIndex:
    """The partial unique index uix_invoices_period_active must be present."""

    def test_partial_index_name_in_migration(self) -> None:
        """'uix_invoices_period_active' must appear in the migration file."""
        source = MIGRATION_PATH.read_text()
        assert "uix_invoices_period_active" in source, (
            "Migration is missing the partial unique index uix_invoices_period_active. "
            "It must be created via op.execute() with a WHERE clause."
        )

    def test_partial_index_uses_where_clause(self) -> None:
        """The partial index must include a WHERE status != 'void' clause."""
        source = MIGRATION_PATH.read_text()
        assert "WHERE status != 'void'" in source, (
            "uix_invoices_period_active must have WHERE status != 'void' partial condition"
        )

    def test_partial_index_dropped_in_downgrade(self) -> None:
        """downgrade() must drop uix_invoices_period_active."""
        source = _get_function_source("downgrade")
        assert "uix_invoices_period_active" in source, (
            "downgrade() must drop uix_invoices_period_active partial index"
        )
