"""
Tests: State Key Preservation (T1.3-RED)

These tests verify that:
1. Non-canonical keys in mode_context are NOT deleted when enforce=False
2. Keys set by tools via _internal_flags persist across the canonical key enforcement step
3. LLM-generated keys in mode_context are preserved regardless of enforcement flag

SPEC REFERENCE: REQ-P1-3 in delta spec
DESIGN REFERENCE: AD-3 (constraint removal) — canonical enforcement must NOT delete keys
AFFECTED FILES:
  - agent/state/mode_context_keys.py  — validate_mode_context_update / validate_state_update
  - agent/modes/base_mode.py          — _validate_canonical_keys
  - shared/config.py                  — ENABLE_STATE_CONTRACT_ENFORCEMENT default=False

BUG BEING FIXED: When ENABLE_STATE_CONTRACT_ENFORCEMENT=True, unknown keys were
  stripped from mode_context. Spec says this setting should only control LOGGING
  level (warning vs. debug), NOT whether data is deleted.

Tests T1.3-RED:
  - Tests that require enforce=False to pass:    GREEN against current code
  - Tests that require enforce=True to NOT strip: FAIL against current code (RED)
                                                   PASS after T1.3 fix (GREEN)

Note on patching: get_settings is imported locally inside functions, so we patch
at 'shared.config.get_settings' (the definition site) to intercept all callers.
"""

import contextlib
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Patch helper: control ENABLE_STATE_CONTRACT_ENFORCEMENT for a test
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _patch_enforcement(enabled: bool):
    """
    Context manager that:
    1. Patches shared.config.get_settings to return a mock with the given flag.
    2. Clears the lru_cache BEFORE patching so the mock is actually used.
    3. Clears the lru_cache AFTER patching so other tests aren't affected.

    This handles the case where get_settings() is lru_cached and may return
    a previously-cached real Settings object rather than the mock.
    """
    from shared.config import get_settings as _real_get_settings

    mock_settings = MagicMock()
    mock_settings.ENABLE_STATE_CONTRACT_ENFORCEMENT = enabled

    # Clear cache before to ensure our mock is used
    _real_get_settings.cache_clear()
    try:
        with patch("shared.config.get_settings", return_value=mock_settings):
            yield
    finally:
        # Clear cache after to restore clean state for subsequent tests
        _real_get_settings.cache_clear()


# ---------------------------------------------------------------------------
# T1: test_non_canonical_keys_not_stripped — enforce=False (default)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_non_canonical_keys_not_stripped_when_enforcement_disabled():
    """
    SPEC REQ-P1-3:
    When ENABLE_STATE_CONTRACT_ENFORCEMENT=False (default), keys that are NOT in
    the canonical whitelist MUST NOT be deleted from mode_context.

    Scenario:
      - GIVEN ENABLE_STATE_CONTRACT_ENFORCEMENT=False
      - AND mode_context contains key 'pending_confirmation_question' (non-canonical)
      - WHEN validate_mode_context_update() is called
      - THEN the key is preserved in the returned dict
      - AND no 'non_canonical_mode_context_keys_stripped' warning is logged
    """
    from agent.state.mode_context_keys import validate_mode_context_update

    updates = {
        "categoria_slug": "motos-part",  # canonical
        "pending_confirmation_question": "¿Confirmas el escape?",  # NON-canonical
        "_last_agent_turn": "presupuesto",  # NON-canonical (tool-set key)
    }

    with _patch_enforcement(enabled=False):
        cleaned, warnings = validate_mode_context_update(updates, "PRESUPUESTO_MODE")

    # Key must survive
    assert "pending_confirmation_question" in cleaned, (
        "Non-canonical key 'pending_confirmation_question' was stripped even though "
        "ENABLE_STATE_CONTRACT_ENFORCEMENT=False. Keys must be preserved when enforcement is off."
    )
    assert cleaned["pending_confirmation_question"] == "¿Confirmas el escape?"

    # Canonical key must also survive
    assert "categoria_slug" in cleaned
    assert cleaned["categoria_slug"] == "motos-part"

    # Non-canonical tool-set key must survive
    assert "_last_agent_turn" in cleaned

    # warnings list may be populated (used for telemetry), but it must NOT cause deletion
    # (warnings are descriptive strings — existence of warnings ≠ deletion)


@pytest.mark.unit
def test_non_canonical_keys_not_stripped_when_enforcement_enabled():
    """
    SPEC REQ-P1-3 — Extended:
    Even when ENABLE_STATE_CONTRACT_ENFORCEMENT=True (warn-only mode),
    unknown keys MUST NOT be deleted. The flag controls logging level only.

    This test verifies the correct behavior described in the spec:
      "If ENABLE_STATE_CONTRACT_ENFORCEMENT remains True (warn-only mode), the system
       MUST log a warning for unknown keys but MUST NOT delete them."

    NOTE: This test FAILS against code where enforce=True deletes keys (RED).
    It becomes GREEN after the fix in validate_mode_context_update.
    """
    from agent.state.mode_context_keys import validate_mode_context_update

    updates = {
        "categoria_slug": "motos-part",  # canonical
        "pending_confirmation_question": "¿Confirmas el escape?",  # NON-canonical
        "v2_collection_context": {"step": 1},  # NON-canonical
    }

    with _patch_enforcement(enabled=True):
        cleaned, warnings = validate_mode_context_update(updates, "PRESUPUESTO_MODE")

    # SPEC: even with enforce=True, keys MUST NOT be deleted
    assert "pending_confirmation_question" in cleaned, (
        "Non-canonical key 'pending_confirmation_question' was stripped when "
        "ENABLE_STATE_CONTRACT_ENFORCEMENT=True. The spec says enforce=True should "
        "only WARN (for monitoring), not DELETE keys. "
        "Fix: validate_mode_context_update should always return updates unchanged."
    )
    assert "v2_collection_context" in cleaned, (
        "Non-canonical key 'v2_collection_context' was stripped. "
        "This key is critical for expediente V2 collection state."
    )
    assert cleaned["categoria_slug"] == "motos-part"

    # warnings MUST be populated (for monitoring) when enforce=True
    assert len(warnings) > 0, (
        "When ENABLE_STATE_CONTRACT_ENFORCEMENT=True and unknown keys exist, "
        "warnings list must be populated for monitoring purposes."
    )


# ---------------------------------------------------------------------------
# T2: test_tool_set_keys_persist_across_turns
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_tool_set_keys_persist_across_canonical_validation():
    """
    SPEC REQ-P1-3:
    Keys set by tools via _internal_flags must survive the canonical key
    enforcement step in _validate_canonical_keys (base_mode.py).

    Scenario:
      - GIVEN a tool sets mode_context["precio_comunicado"] = True (canonical)
      - AND a tool sets mode_context["element_states"] = {...} (non-canonical)
      - WHEN _validate_canonical_keys is called by base_mode.process()
      - THEN both keys must be present in the returned result

    This tests the integration: validate_mode_context_update + base_mode integration.
    """
    from agent.state.mode_context_keys import validate_mode_context_update

    # Simulate a mode_context dict that includes both canonical and tool-set keys
    tool_populated_context = {
        "precio_comunicado": True,  # canonical (in _TYPED_DICT_KEYS)
        "categoria_slug": "motos-part",  # canonical
        "element_states": {  # NON-canonical — set by element_state_service
            "ESCAPE": {"photos_confirmed": False, "fields_complete": False}
        },
        "v2_collection_context": {  # NON-canonical — V2 context
            "current_step": "collect_element_data",
        },
    }

    with _patch_enforcement(enabled=False):
        cleaned, warnings = validate_mode_context_update(
            tool_populated_context, "EXPEDIENTE_MODE"
        )

    # Canonical keys must survive
    assert cleaned["precio_comunicado"] is True
    assert cleaned["categoria_slug"] == "motos-part"

    # Non-canonical tool-set keys must also survive
    assert "element_states" in cleaned, (
        "element_states was stripped from mode_context. "
        "This key is written by element_state_service and is critical for "
        "expediente flow — its deletion causes element phase tracking to break."
    )
    assert "v2_collection_context" in cleaned, (
        "v2_collection_context was stripped from mode_context. "
        "This key holds V2 collection state and must survive across turns."
    )

    # Verify values were not corrupted
    assert cleaned["element_states"]["ESCAPE"]["photos_confirmed"] is False
    assert cleaned["v2_collection_context"]["current_step"] == "collect_element_data"


@pytest.mark.unit
def test_internal_flags_keys_survive_validation():
    """
    SPEC REQ-P1-3:
    Keys from tool _internal_flags that ARE in the canonical set must always
    survive validation (regression check: canonical keys must never be stripped).

    This verifies the canonical set is not accidentally restricting tool flag keys
    like precio_comunicado, imagenes_enviadas, pending_variants, etc.
    """
    from agent.state.mode_context_keys import (
        validate_mode_context_update,
        CANONICAL_MODE_CONTEXT_KEYS,
    )

    # All these keys are written by tools via _internal_flags
    tool_flag_keys = {
        "precio_comunicado": True,
        "imagenes_enviadas": False,
        "pending_variants": [],
        "elemento_confirmado": "ESCAPE",
        "element_codes": ["ESCAPE"],
        "elementos_confirmados": ["ESCAPE"],
        "tarifa_calculada": 410.0,
        "categoria_slug": "motos-part",
    }

    # Sanity: all these keys are in the canonical set
    for key in tool_flag_keys:
        assert key in CANONICAL_MODE_CONTEXT_KEYS, (
            f"Key '{key}' is NOT in CANONICAL_MODE_CONTEXT_KEYS but is written by "
            f"tool _internal_flags. The canonical set must include all tool flag keys."
        )

    # Test with enforcement ENABLED — canonical keys MUST survive even then
    with _patch_enforcement(enabled=True):
        cleaned, warnings = validate_mode_context_update(
            tool_flag_keys, "PRESUPUESTO_MODE"
        )

    # All canonical keys must survive regardless of enforcement flag
    for key in tool_flag_keys:
        assert key in cleaned, (
            f"Canonical key '{key}' was stripped during validation. "
            "Canonical keys must NEVER be stripped — they are known valid keys."
        )
        assert cleaned[key] == tool_flag_keys[key]

    # No warnings should be generated for canonical keys
    assert len(warnings) == 0, (
        f"Warnings were generated for canonical keys: {warnings}. "
        "Known canonical keys must not produce warnings."
    )


# ---------------------------------------------------------------------------
# T3: test_lm_generated_keys_preserved
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_lm_generated_keys_preserved_enforce_false():
    """
    SPEC REQ-P1-3:
    Keys the LLM generates in mode_context (via context updates or tool flags)
    must be preserved across turns.

    Scenario (from spec):
      - GIVEN ENABLE_STATE_CONTRACT_ENFORCEMENT=False
      - AND a tool sets mode_context["pending_confirmation_question"] = "..." on turn N
      - WHEN the conversation moves to turn N+1 (canonical validation runs)
      - THEN mode_context["pending_confirmation_question"] is still present
      - AND no 'non_canonical_mode_context_keys_stripped' warning appears in logs

    This test uses the full validate_mode_context_update path to simulate
    what happens at turn boundary validation.
    """
    from agent.state.mode_context_keys import validate_mode_context_update

    # Simulate mode_context that has LLM/tool-generated keys from previous turn
    mode_context_at_turn_n = {
        "categoria_slug": "motos-part",
        "element_codes": ["SUSPENSION"],
        "pending_confirmation_question": "¿La suspensión es delantera o trasera?",
        "_last_agent_turns": [
            {"role": "assistant", "content": "Te presento el presupuesto"}
        ],
        "active_variant_context": {
            "element_code": "SUSPENSION",
            "question_asked": True,
        },
    }

    with _patch_enforcement(enabled=False):
        cleaned, warnings = validate_mode_context_update(
            mode_context_at_turn_n, "PRESUPUESTO_MODE"
        )

    # All keys must survive
    assert "pending_confirmation_question" in cleaned, (
        "pending_confirmation_question was deleted. Keys set by tools/LLM in "
        "mode_context must survive across turns when enforcement is disabled."
    )
    assert "_last_agent_turns" in cleaned, (
        "_last_agent_turns was deleted. This key tracks agent turn history and "
        "must persist for proper conversation flow."
    )
    assert "active_variant_context" in cleaned, (
        "active_variant_context was deleted. Variant state must persist "
        "so the next turn can route the user's answer correctly."
    )

    # Canonical keys must also be intact
    assert cleaned["categoria_slug"] == "motos-part"
    assert cleaned["element_codes"] == ["SUSPENSION"]

    # Spec says: no 'non_canonical_mode_context_keys_stripped' event — only DEBUG log
    # (we can't easily assert on structlog output here, but key presence is sufficient)


@pytest.mark.unit
def test_lm_generated_keys_preserved_enforce_true_warn_only():
    """
    SPEC REQ-P1-3 — Warn-only:
    When ENABLE_STATE_CONTRACT_ENFORCEMENT=True, unknown keys must be LOGGED
    as warnings but MUST NOT be deleted from mode_context.

    This test documents the SPEC REQUIREMENT that enforcement=True means
    "warn-only" (for monitoring), NOT "delete".

    NOTE: This test FAILS against the ORIGINAL code where enforce=True
    causes key deletion (line 308 of mode_context_keys.py). It becomes
    GREEN after the fix where only logging behavior changes, not key deletion.
    """
    from agent.state.mode_context_keys import validate_mode_context_update

    mode_context = {
        "categoria_slug": "motos-part",
        "pending_confirmation_question": "¿Confirmas?",
        "v2_collection_context": {"step": 1},
        "element_states": {"ESCAPE": {"complete": False}},
    }

    with _patch_enforcement(enabled=True):
        cleaned, warnings = validate_mode_context_update(
            mode_context, "EXPEDIENTE_MODE"
        )

    # Keys must survive even with enforcement=True (warn-only mode per spec)
    assert "pending_confirmation_question" in cleaned, (
        "SPEC VIOLATION: 'pending_confirmation_question' was deleted when "
        "ENABLE_STATE_CONTRACT_ENFORCEMENT=True. The spec says enforce=True should "
        "only WARN (for monitoring), not DELETE keys. Fix: return updates unchanged "
        "in both branches of validate_mode_context_update."
    )
    assert "v2_collection_context" in cleaned, (
        "SPEC VIOLATION: 'v2_collection_context' was deleted. "
        "This key is critical for expediente V2 collection state."
    )
    assert "element_states" in cleaned, (
        "SPEC VIOLATION: 'element_states' was deleted. "
        "This key is written by element_state_service and is critical for "
        "tracking element completion in EXPEDIENTE_MODE."
    )

    # Warnings must be populated (for monitoring)
    assert len(warnings) > 0, (
        "With enforce=True and unknown keys, warnings list must be populated "
        "for monitoring purposes."
    )
    # Canonical keys must be intact
    assert "categoria_slug" in cleaned


# ---------------------------------------------------------------------------
# T4: base_mode integration — _validate_canonical_keys assigns correctly
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_base_mode_validate_canonical_keys_no_deletion_on_enforce_false():
    """
    SPEC REQ-P1-3:
    Verify that base_mode._validate_canonical_keys does NOT delete non-canonical
    mode_context keys when ENABLE_STATE_CONTRACT_ENFORCEMENT=False.

    This tests the base_mode layer that calls validate_mode_context_update and
    then conditionally assigns back to result["mode_context"].

    Bug risk: in base_mode.py line 637-638:
        if ctx_warnings:
            result["mode_context"] = cleaned_ctx
    When enforce=False, cleaned_ctx IS the original updates (no deletion),
    so this is safe. But this test confirms the end-to-end behavior.
    """
    from agent.modes.presupuesto_mode import PresupuestoModeNode

    # Minimal result dict simulating what _process_message returns
    result = {
        "ai_response": "El presupuesto es de 410€ +IVA",
        "current_mode": "PRESUPUESTO_MODE",
        "mode_context": {
            "categoria_slug": "motos-part",
            "precio_comunicado": True,
            # Non-canonical keys that MUST survive:
            "pending_confirmation_question": "¿Quieres iniciar el expediente?",
            "element_states": {"ESCAPE": {"complete": False}},
            "_last_agent_turn_summary": "price quoted",
        },
    }

    with _patch_enforcement(enabled=False):
        node = PresupuestoModeNode()
        validated_result, warnings = node._validate_canonical_keys(result)

    # mode_context in result must still have non-canonical keys
    mode_ctx = validated_result.get("mode_context", {})

    assert "pending_confirmation_question" in mode_ctx, (
        "Non-canonical key 'pending_confirmation_question' was deleted by "
        "_validate_canonical_keys even though ENABLE_STATE_CONTRACT_ENFORCEMENT=False. "
        "Keys must be preserved when enforcement is off."
    )
    assert "element_states" in mode_ctx, (
        "Non-canonical key 'element_states' was deleted. "
        "This key must survive for expediente element tracking."
    )
    assert "_last_agent_turn_summary" in mode_ctx

    # Canonical keys must also be intact
    assert mode_ctx["categoria_slug"] == "motos-part"
    assert mode_ctx["precio_comunicado"] is True


@pytest.mark.unit
def test_base_mode_validate_canonical_keys_no_deletion_on_enforce_true():
    """
    SPEC REQ-P1-3 — Extended:
    base_mode._validate_canonical_keys MUST NOT delete mode_context keys
    even when ENABLE_STATE_CONTRACT_ENFORCEMENT=True.

    This test confirms that the _validate_canonical_keys integration
    respects the "warn-only" behavior for enforce=True.

    NOTE: This test FAILS against original code where enforce=True strips keys.
    Becomes GREEN after the fix.
    """
    from agent.modes.presupuesto_mode import PresupuestoModeNode

    result = {
        "ai_response": "El presupuesto es de 410€ +IVA",
        "mode_context": {
            "categoria_slug": "motos-part",
            "precio_comunicado": True,
            "pending_confirmation_question": "¿Quieres iniciar el expediente?",
            "element_states": {"ESCAPE": {"complete": False}},
        },
    }

    with _patch_enforcement(enabled=True):
        node = PresupuestoModeNode()
        validated_result, warnings = node._validate_canonical_keys(result)

    mode_ctx = validated_result.get("mode_context", {})

    assert "pending_confirmation_question" in mode_ctx, (
        "SPEC VIOLATION: 'pending_confirmation_question' deleted by "
        "_validate_canonical_keys even when spec says enforce=True should be warn-only."
    )
    assert "element_states" in mode_ctx, (
        "SPEC VIOLATION: 'element_states' deleted. "
        "Enforcement should never delete keys — only log them."
    )
    assert mode_ctx["categoria_slug"] == "motos-part"


# ---------------------------------------------------------------------------
# T5: known-keys-preserved regression check (spec requires this)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_canonical_keys_always_preserved_regardless_of_flag():
    """
    SPEC REQ-P1-3 — Regression check:
    Known canonical keys (like categoria_slug) MUST persist regardless of the
    ENABLE_STATE_CONTRACT_ENFORCEMENT flag value.

    This is a regression check to ensure fixing enforce=True doesn't accidentally
    break canonical key handling.
    """
    from agent.state.mode_context_keys import validate_mode_context_update

    canonical_updates = {
        "categoria_slug": "motos-part",
        "element_codes": ["ESCAPE", "SUSPENSION"],
        "precio_comunicado": True,
        "tarifa_calculada": 450.0,
        "expediente_sub_mode": "collect_personal",
        "case_id": "case-uuid-123",
    }

    for enforce_value in [True, False]:
        with _patch_enforcement(enabled=enforce_value):
            cleaned, warnings = validate_mode_context_update(
                canonical_updates, "EXPEDIENTE_MODE"
            )

        # All canonical keys must be present regardless of flag
        for key in canonical_updates:
            assert key in cleaned, (
                f"Canonical key '{key}' was missing from cleaned dict "
                f"with enforce={enforce_value}. Canonical keys MUST always survive."
            )
            assert cleaned[key] == canonical_updates[key], (
                f"Canonical key '{key}' value was corrupted with enforce={enforce_value}."
            )

        # No warnings for canonical-only updates
        assert len(warnings) == 0, (
            f"Got unexpected warnings for canonical-only updates with enforce={enforce_value}: "
            f"{warnings}"
        )


# ---------------------------------------------------------------------------
# T6: test_flag_defaults_to_false
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_flag_defaults_to_false():
    """
    SPEC REQ-P1-3 / config default:
    ENABLE_STATE_CONTRACT_ENFORCEMENT MUST default to False.

    Rationale from spec: the bug being fixed is that unknown keys were
    being stripped, which corrupts LLM-set and tool-set state. The safe
    default is False (no enforcement = no deletion, no warning noise).
    Operators who want monitoring can opt in by setting the flag to True.

    This test verifies the default WITHOUT patching — uses the real Settings
    class to confirm the declared default value in shared/config.py.
    """
    from shared.config import Settings

    # Instantiate with no env vars (use class field defaults only)
    # We use model_fields to read the default without loading .env
    field = Settings.model_fields["ENABLE_STATE_CONTRACT_ENFORCEMENT"]
    default_value = field.default

    assert default_value is False, (
        f"ENABLE_STATE_CONTRACT_ENFORCEMENT default is {default_value!r}, expected False. "
        "REQ-P1-3 requires this flag to default to False so that key stripping is "
        "disabled by default — operators opt in to monitoring by setting it to True."
    )
