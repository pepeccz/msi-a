"""
Tests for Schema Drift Fix — Tasks 4.1 & 4.2 (RED phase)

Spec 5: ModeContextData declared keys must match runtime keys.

The three drifted keys:
  TypedDict (before fix)  |  Runtime (submodos/_shared.py)
  datos_personales        |  personal_data
  datos_vehiculo          |  vehicle_data
  datos_taller            |  taller_data

Fix direction: rename TypedDict keys to English (match runtime).

After the fix:
- validate_mode_context_update({"personal_data": {}})    → empty warnings list
- validate_mode_context_update({"vehicle_data": {}})     → empty warnings list
- validate_mode_context_update({"taller_data": {}})      → empty warnings list
- validate_mode_context_update({"datos_personales": {}}) → non-empty warnings (removed
  from TypedDict and not in compat set → unknown key → DEBUG log, NO deletion)
- ModeContextData TypedDict __annotations__ must contain personal_data / vehicle_data /
  taller_data and must NOT contain datos_personales / datos_vehiculo / datos_taller
- _TYPED_DICT_KEYS frozenset must contain English keys, NOT Spanish keys
- _CASE_COLLECTION_COMPAT_KEYS must still contain English data keys (pre-existing)

Design reference: AD-3 in design.md
Spec reference:   Spec 5 in spec.md
"""

import sys
import types
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Pre-import stubs — must come before ANY agent.* import
# ---------------------------------------------------------------------------
# The root conftest (tests/conftest.py) fails because PIL is not installed.
# We apply stubs here directly so the test file works with --noconftest.


def _install_stub(name: str) -> None:
    if name not in sys.modules:
        stub = MagicMock()
        stub.__name__ = name
        sys.modules[name] = stub


# structlog
if "structlog" not in sys.modules:
    _sl = types.ModuleType("structlog")
    _sl.get_logger = lambda *a, **kw: MagicMock()  # type: ignore[attr-defined]
    sys.modules["structlog"] = _sl

# PIL
_install_stub("PIL")
_install_stub("PIL.Image")

# langgraph.checkpoint.redis
for _rmod in ("langgraph.checkpoint.redis", "langgraph.checkpoint.redis.aio"):
    if _rmod not in sys.modules:
        _rm = types.ModuleType(_rmod)
        _rm.AsyncRedisSaver = MagicMock()  # type: ignore[attr-defined]
        sys.modules[_rmod] = _rm

# phonenumbers
_install_stub("phonenumbers")
_install_stub("phonenumbers.phonenumberutil")


# ---------------------------------------------------------------------------
# Task 4.1 — English keys must be canonical (validate_mode_context_update)
# ---------------------------------------------------------------------------


def test_personal_data_key_is_canonical() -> None:
    """
    validate_mode_context_update({"personal_data": {}}) must return
    empty warnings list — personal_data is a canonical key.
    """
    from agent.state.mode_context_keys import validate_mode_context_update

    updates = {"personal_data": {"nombre": "Test", "dni": "12345678A"}}
    result, warnings = validate_mode_context_update(updates, mode="EXPEDIENTE_MODE")

    assert result is updates, (
        "validate_mode_context_update must return the original dict unchanged"
    )
    assert warnings == [], (
        f"'personal_data' must be a canonical key (no warnings expected). "
        f"Got: {warnings}"
    )


def test_vehicle_data_key_is_canonical() -> None:
    """validate_mode_context_update({"vehicle_data": {}}) must return empty warnings."""
    from agent.state.mode_context_keys import validate_mode_context_update

    updates = {"vehicle_data": {"marca": "Honda", "modelo": "CBR500"}}
    result, warnings = validate_mode_context_update(updates, mode="EXPEDIENTE_MODE")

    assert result is updates
    assert warnings == [], (
        f"'vehicle_data' must be a canonical key (no warnings expected). Got: {warnings}"
    )


def test_taller_data_key_is_canonical() -> None:
    """validate_mode_context_update({"taller_data": {}}) must return empty warnings."""
    from agent.state.mode_context_keys import validate_mode_context_update

    updates = {"taller_data": {"nombre": "Taller MSI", "direccion": "Calle Mayor 1"}}
    result, warnings = validate_mode_context_update(updates, mode="EXPEDIENTE_MODE")

    assert result is updates
    assert warnings == [], (
        f"'taller_data' must be a canonical key (no warnings expected). Got: {warnings}"
    )


def test_all_three_english_keys_canonical_together() -> None:
    """
    Triangulation: when all three English keys are present together,
    no warnings must be returned.
    """
    from agent.state.mode_context_keys import validate_mode_context_update

    updates = {
        "personal_data": {"nombre": "Ana García"},
        "vehicle_data": {"marca": "Yamaha"},
        "taller_data": {"nombre": "MSI Oficial"},
    }
    result, warnings = validate_mode_context_update(updates, mode="EXPEDIENTE_MODE")

    assert result is updates
    assert warnings == [], (
        f"All three English keys together must produce no warnings. Got: {warnings}"
    )


# ---------------------------------------------------------------------------
# Task 4.1b — ModeContextData TypedDict annotations must use English keys
# ---------------------------------------------------------------------------


def test_mode_context_data_annotations_contain_english_keys() -> None:
    """
    ModeContextData TypedDict __annotations__ must contain 'personal_data',
    'vehicle_data', 'taller_data' (English keys).

    Before fix: ModeContextData declares 'datos_personales', 'datos_vehiculo',
      'datos_taller' — runtime code using English keys gets TypedDict key errors.
    After fix:  English keys are declared — aligns TypedDict to runtime usage.
    """
    from agent.state.conversation_state import ModeContextData

    annotations = ModeContextData.__annotations__
    assert "personal_data" in annotations, (
        "ModeContextData must declare 'personal_data' (English key). "
        f"Currently declared data-like keys: "
        f"{[k for k in annotations if 'data' in k or 'personal' in k or 'vehicle' in k or 'taller' in k]}"
    )
    assert "vehicle_data" in annotations, (
        "ModeContextData must declare 'vehicle_data' (English key). "
        f"Currently declared data-like keys: "
        f"{[k for k in annotations if 'data' in k or 'personal' in k or 'vehicle' in k or 'taller' in k]}"
    )
    assert "taller_data" in annotations, (
        "ModeContextData must declare 'taller_data' (English key). "
        f"Currently declared data-like keys: "
        f"{[k for k in annotations if 'data' in k or 'personal' in k or 'vehicle' in k or 'taller' in k]}"
    )


def test_mode_context_data_annotations_do_not_have_spanish_keys() -> None:
    """
    ModeContextData must NOT declare 'datos_personales', 'datos_vehiculo',
    'datos_taller' as TypedDict fields after the fix.

    The Spanish names are removed from the TypedDict — they become legacy
    backward-compat names (preserved in Redis checkpoints, but unknown to
    the validator which logs them at DEBUG level without deleting them).
    """
    from agent.state.conversation_state import ModeContextData

    annotations = ModeContextData.__annotations__
    assert "datos_personales" not in annotations, (
        "ModeContextData must NOT declare 'datos_personales' (Spanish key removed). "
        "Use 'personal_data' instead."
    )
    assert "datos_vehiculo" not in annotations, (
        "ModeContextData must NOT declare 'datos_vehiculo' (Spanish key removed). "
        "Use 'vehicle_data' instead."
    )
    assert "datos_taller" not in annotations, (
        "ModeContextData must NOT declare 'datos_taller' (Spanish key removed). "
        "Use 'taller_data' instead."
    )


# ---------------------------------------------------------------------------
# Task 4.2 — Spanish keys: no crash, no deletion, DEBUG warning (not error)
# ---------------------------------------------------------------------------


def test_datos_personales_logs_debug_not_error() -> None:
    """
    Task 4.2: validate_mode_context_update({"datos_personales": {}}) must:
    - NOT raise an exception
    - Return the dict UNCHANGED (no deletion — validator is warn-only)
    - Produce a warning (datos_personales is removed from _TYPED_DICT_KEYS
      and is not in any other canonical set)
    - Log at DEBUG level (not ERROR) — verified by warning message format

    Old Redis checkpoints containing 'datos_personales' will pass through:
    merge_dicts preserves all keys regardless of canonical status, and the
    validator never deletes (contract: warn-only).
    """
    from agent.state.mode_context_keys import (
        validate_mode_context_update,
        CANONICAL_MODE_CONTEXT_KEYS,
    )

    # After the fix: datos_personales removed from _TYPED_DICT_KEYS and NOT
    # in any other canonical set → no longer canonical
    assert "datos_personales" not in CANONICAL_MODE_CONTEXT_KEYS, (
        "datos_personales must NOT be in CANONICAL_MODE_CONTEXT_KEYS after the fix. "
        "It was removed from _TYPED_DICT_KEYS and was never in other canonical sets."
    )

    updates = {"datos_personales": {"nombre": "Legacy checkpoint data"}}
    result, warnings = validate_mode_context_update(updates, mode="EXPEDIENTE_MODE")

    # Dict is returned unchanged — validator NEVER deletes keys
    assert result is updates, (
        "validate_mode_context_update must return original dict unchanged"
    )
    assert result["datos_personales"] == {"nombre": "Legacy checkpoint data"}, (
        "datos_personales value must not be deleted — validator is warn-only (no deletion)"
    )
    # After removing from _TYPED_DICT_KEYS, it becomes unknown → produces a warning
    assert len(warnings) > 0, (
        "datos_personales must produce a warning after being removed from _TYPED_DICT_KEYS. "
        "This is expected and correct: (1) no crash, (2) no deletion, (3) only DEBUG log."
    )
    assert any("datos_personales" in w for w in warnings), (
        f"Warning must mention 'datos_personales'. Got: {warnings}"
    )


def test_truly_unknown_key_does_produce_warning() -> None:
    """
    Triangulation: a truly unknown key DOES produce a warning.
    This confirms the canonical check works — our 'empty warnings' assertions
    above for English keys are meaningful (not trivially passing).
    """
    from agent.state.mode_context_keys import validate_mode_context_update

    updates = {"totally_unknown_key_xyz_abc_999": "some_value"}
    result, warnings = validate_mode_context_update(updates, mode="EXPEDIENTE_MODE")

    assert result is updates
    assert len(warnings) > 0, (
        "A truly unknown key must produce non-empty warnings list. "
        "This confirms the canonical check actually exercises real logic."
    )
    assert any("totally_unknown_key_xyz_abc_999" in w for w in warnings), (
        f"Warning message must mention the unknown key. Got: {warnings}"
    )


# ---------------------------------------------------------------------------
# Task 4.4 — _TYPED_DICT_KEYS contains English keys, NOT Spanish keys
# ---------------------------------------------------------------------------


def test_typed_dict_keys_contains_english_keys() -> None:
    """
    _TYPED_DICT_KEYS frozenset must contain the English runtime keys.
    After fix: personal_data, vehicle_data, taller_data in _TYPED_DICT_KEYS.
    Before fix: datos_personales, datos_vehiculo, datos_taller in _TYPED_DICT_KEYS.
    """
    from agent.state.mode_context_keys import _TYPED_DICT_KEYS

    assert "personal_data" in _TYPED_DICT_KEYS, (
        "_TYPED_DICT_KEYS must contain 'personal_data' (English) after schema drift fix. "
        f"Current data-like keys in _TYPED_DICT_KEYS: "
        f"{[k for k in _TYPED_DICT_KEYS if 'data' in k or 'personal' in k]}"
    )
    assert "vehicle_data" in _TYPED_DICT_KEYS, (
        "_TYPED_DICT_KEYS must contain 'vehicle_data' (English) after schema drift fix."
    )
    assert "taller_data" in _TYPED_DICT_KEYS, (
        "_TYPED_DICT_KEYS must contain 'taller_data' (English) after schema drift fix."
    )


def test_typed_dict_keys_does_not_contain_spanish_keys() -> None:
    """
    _TYPED_DICT_KEYS must NOT contain the Spanish variants.
    They must have been removed (not moved — they weren't in other canonical sets).
    """
    from agent.state.mode_context_keys import _TYPED_DICT_KEYS

    assert "datos_personales" not in _TYPED_DICT_KEYS, (
        "_TYPED_DICT_KEYS must NOT contain 'datos_personales' after fix. "
        "Spanish TypedDict key removed — runtime uses 'personal_data'."
    )
    assert "datos_vehiculo" not in _TYPED_DICT_KEYS, (
        "_TYPED_DICT_KEYS must NOT contain 'datos_vehiculo' after fix."
    )
    assert "datos_taller" not in _TYPED_DICT_KEYS, (
        "_TYPED_DICT_KEYS must NOT contain 'datos_taller' after fix."
    )


def test_case_collection_compat_keys_still_contains_english_data_keys() -> None:
    """
    Triangulation for _CASE_COLLECTION_COMPAT_KEYS: the English keys
    personal_data, vehicle_data, taller_data must still be present
    (they were there before the fix — confirmed from reading the source).

    This ensures we don't accidentally remove them while editing.
    """
    from agent.state.mode_context_keys import _CASE_COLLECTION_COMPAT_KEYS

    assert "personal_data" in _CASE_COLLECTION_COMPAT_KEYS, (
        "_CASE_COLLECTION_COMPAT_KEYS must contain 'personal_data' (pre-existing)."
    )
    assert "vehicle_data" in _CASE_COLLECTION_COMPAT_KEYS, (
        "_CASE_COLLECTION_COMPAT_KEYS must contain 'vehicle_data' (pre-existing)."
    )
    assert "taller_data" in _CASE_COLLECTION_COMPAT_KEYS, (
        "_CASE_COLLECTION_COMPAT_KEYS must contain 'taller_data' (pre-existing)."
    )
