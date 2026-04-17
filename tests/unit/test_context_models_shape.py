"""
Shape tests for SharedContext TypedDict in agent.state.context_models.

These tests verify the CONTRACT of the TypedDict — which fields are
declared as typed annotations, not just set at runtime.

A typed annotation guarantees:
  - Static analysis tools (mypy, pyright) can check assignments
  - The field shows up in SharedContext.__annotations__
  - Documentation reflects the actual schema

Tests are pure unit — no DB, no Redis, no LLM, no network.
"""

from __future__ import annotations

from agent.state.context_models import SharedContext


class TestSharedContextShape:
    """Verify SharedContext declares all expected typed fields."""

    def test_warnings_acknowledged_declared_in_shared_context(self) -> None:
        """warnings_acknowledged must be a declared TypedDict annotation."""
        assert "warnings_acknowledged" in SharedContext.__annotations__, (
            "SharedContext is missing 'warnings_acknowledged: bool' annotation. "
            "The field is written at runtime by confirmar_presupuesto / "
            "iniciar_expediente hook but is not declared in the TypedDict, "
            "breaking the type contract."
        )

    def test_warnings_acknowledged_is_bool_annotation(self) -> None:
        """warnings_acknowledged annotation must be bool (or bool | None via total=False).

        Note: with `from __future__ import annotations` the annotations dict stores
        ForwardRef objects (PEP 563). We check the string representation, which is
        the portable way to verify type hints under deferred evaluation.
        """
        annotation = SharedContext.__annotations__.get("warnings_acknowledged")
        assert annotation is not None, (
            "warnings_acknowledged not found in SharedContext.__annotations__"
        )
        # Under PEP 563 (`from __future__ import annotations`) the annotation is
        # a ForwardRef whose __forward_arg__ is 'bool'. Under eager evaluation it
        # would be the bool type itself. We normalise to string for portability.
        annotation_str = (
            annotation.__forward_arg__
            if hasattr(annotation, "__forward_arg__")
            else str(annotation)
        )
        assert annotation_str == "bool", (
            f"Expected annotation 'bool', got {annotation_str!r}. "
            "Declare as: warnings_acknowledged: bool"
        )

    def test_existing_bool_flags_still_present(self) -> None:
        """Regression: ensure existing bool fields are not accidentally removed."""
        expected_bool_fields = {
            "precio_comunicado",
            "imagenes_enviadas",
            "presupuesto_images_shown",
        }
        missing = expected_bool_fields - set(SharedContext.__annotations__)
        assert not missing, (
            f"Existing bool fields missing from SharedContext: {missing}"
        )
