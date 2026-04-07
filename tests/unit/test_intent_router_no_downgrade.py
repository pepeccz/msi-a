"""
Tests for waiting_for_image_choice dead-code removal.

Spec 4 (Batch 2): The `waiting_for_image_choice` flag is NEVER set to True
anywhere in the codebase. The downgrade logic in `_validate_keyword_with_context`
that depends on it permanently suppresses VER_IMAGENES and ABRIR_EXPEDIENTE intents
(confidence → 0.50), defeating the keyword classifier.

Fix: remove the two `if not context_hints.get("waiting_for_image_choice")` blocks.

After the fix:
- VER_IMAGENES must retain full confidence regardless of waiting_for_image_choice
- ABRIR_EXPEDIENTE must retain full confidence regardless of waiting_for_image_choice
- CONFIRMACION downgrade (on precio_comunicado / tarifa_calculada) is unaffected
- Router with no context hints (empty dict or None) must return full confidence

Design reference: AD-2 (design.md) — remove read-side references, keep TypedDict field.
"""

import pytest
from agent.router.intent_router import (
    IntentRouter,
    UserIntent,
    get_intent_router,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _router() -> IntentRouter:
    """Return a fresh IntentRouter instance (no LLM needed for unit tests)."""
    return get_intent_router()


# ---------------------------------------------------------------------------
# Task 2.1 — Basic: empty context must not downgrade VER_IMAGENES / ABRIR_EXPEDIENTE
# ---------------------------------------------------------------------------


def test_ver_imagenes_no_downgrade_empty_context() -> None:
    """
    _validate_keyword_with_context(VER_IMAGENES, 0.95, {}) must return 0.95.

    Before fix: returns 0.50 because waiting_for_image_choice is falsy.
    After fix:  returns 0.95 (no downgrade — dead condition removed).
    """
    router = _router()
    result = router._validate_keyword_with_context(
        intent=UserIntent.VER_IMAGENES,
        confidence=0.95,
        context_hints={},
    )
    assert result == 0.95, (
        f"VER_IMAGENES with empty context should return 0.95, got {result}. "
        "The waiting_for_image_choice downgrade block must be removed."
    )


def test_abrir_expediente_no_downgrade_empty_context() -> None:
    """
    _validate_keyword_with_context(ABRIR_EXPEDIENTE, 0.95, {}) must return 0.95.

    Before fix: returns 0.50 because waiting_for_image_choice is falsy.
    After fix:  returns 0.95 (no downgrade — dead condition removed).
    """
    router = _router()
    result = router._validate_keyword_with_context(
        intent=UserIntent.ABRIR_EXPEDIENTE,
        confidence=0.95,
        context_hints={},
    )
    assert result == 0.95, (
        f"ABRIR_EXPEDIENTE with empty context should return 0.95, got {result}. "
        "The waiting_for_image_choice downgrade block must be removed."
    )


# ---------------------------------------------------------------------------
# Task 2.2 — Triangulation: explicit False in context still returns full confidence
# ---------------------------------------------------------------------------


def test_ver_imagenes_no_downgrade_when_flag_false() -> None:
    """
    _validate_keyword_with_context(VER_IMAGENES, 0.90, {'waiting_for_image_choice': False})
    must return 0.90 — explicit False must not downgrade either.

    This is the key regression case: element_tools.py resets the flag to False
    on re-identification, which MUST NOT permanently suppress VER_IMAGENES.
    """
    router = _router()
    result = router._validate_keyword_with_context(
        intent=UserIntent.VER_IMAGENES,
        confidence=0.90,
        context_hints={"waiting_for_image_choice": False},
    )
    assert result == 0.90, (
        f"VER_IMAGENES with waiting_for_image_choice=False should return 0.90, got {result}. "
        "The flag reset in element_tools.py must not suppress valid image intents."
    )


def test_abrir_expediente_no_downgrade_when_flag_false() -> None:
    """
    _validate_keyword_with_context(ABRIR_EXPEDIENTE, 0.90, {'waiting_for_image_choice': False})
    must return 0.90.

    Parallel to VER_IMAGENES — the B-option path must also be unblocked.
    """
    router = _router()
    result = router._validate_keyword_with_context(
        intent=UserIntent.ABRIR_EXPEDIENTE,
        confidence=0.90,
        context_hints={"waiting_for_image_choice": False},
    )
    assert result == 0.90, (
        f"ABRIR_EXPEDIENTE with waiting_for_image_choice=False should return 0.90, got {result}. "
        "Flag reset in element_tools.py must not suppress ABRIR_EXPEDIENTE intent."
    )


# ---------------------------------------------------------------------------
# Regression: CONFIRMACION downgrade is unaffected by this change
# ---------------------------------------------------------------------------


def test_confirmacion_still_downgrades_without_price_context() -> None:
    """
    CONFIRMACION downgrade on missing precio_comunicado/tarifa_calculada is preserved.

    This verifies that removing the waiting_for_image_choice blocks did NOT
    accidentally remove the CONFIRMACION downgrade (a separate, unrelated condition).
    """
    router = _router()
    result = router._validate_keyword_with_context(
        intent=UserIntent.CONFIRMACION,
        confidence=0.95,
        context_hints={},  # No precio_comunicado, no tarifa_calculada
    )
    assert result == 0.50, (
        f"CONFIRMACION without price context should still return 0.50 (downgraded), got {result}."
    )


def test_confirmacion_not_downgraded_with_price_context() -> None:
    """
    CONFIRMACION with precio_comunicado=True returns full confidence (unaffected by fix).
    """
    router = _router()
    result = router._validate_keyword_with_context(
        intent=UserIntent.CONFIRMACION,
        confidence=0.95,
        context_hints={"precio_comunicado": True},
    )
    assert result == 0.95, (
        f"CONFIRMACION with precio_comunicado=True should return 0.95, got {result}."
    )


# ---------------------------------------------------------------------------
# Edge case: None context always returns full confidence (existing guard)
# ---------------------------------------------------------------------------


def test_ver_imagenes_none_context_returns_full_confidence() -> None:
    """
    _validate_keyword_with_context with context_hints=None returns confidence unchanged.

    This is the existing guard at the top of the function (not affected by the fix)
    but we verify it still works after the edit.
    """
    router = _router()
    result = router._validate_keyword_with_context(
        intent=UserIntent.VER_IMAGENES,
        confidence=0.95,
        context_hints=None,
    )
    assert result == 0.95, (
        f"VER_IMAGENES with None context_hints should return 0.95, got {result}."
    )
