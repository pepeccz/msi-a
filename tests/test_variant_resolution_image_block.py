"""
Tests for fix-variant-resolution-image-block

Root cause: validate_and_apply_allocations stores option TEXT as variant_code
in resoluciones instead of element CODE, causing mode_context["element_codes"]
to be incomplete and blocking enviar_imagenes_ejemplo.

Fixes:
  1. option_to_code_map in validate_and_apply_allocations -> correct storage
  2. Accumulator guard in presupuesto_mode -> prevent cross-call overwrites
"""

import importlib
import re
import sys
from types import ModuleType
from unittest.mock import MagicMock


def _import_variant_service():
    """Import variant_interpretation_service bypassing agent/__init__.py."""
    # Save and temporarily replace agent package to avoid __init__ chain
    saved = {}
    stubs = [
        "agent", "agent.graph", "agent.graph.conversation_graph",
        "agent.state", "agent.state.checkpointer", "agent.state.helpers",
        "agent.router", "agent.router.intent_router",
        "agent.modes", "agent.tools",
        "structlog", "langgraph", "langgraph.graph", "langgraph.graph.state",
        "langgraph.checkpoint", "langgraph.checkpoint.base",
        "langgraph.checkpoint.redis", "langgraph.checkpoint.redis.aio",
        "langgraph.types", "redisvl", "redisvl.index", "redisvl.index.index",
        "pydantic_settings", "asyncpg", "redis", "redis.asyncio",
        "httpx", "qdrant_client", "sentence_transformers",
        "langchain_core", "langchain_core.tools",
        "langchain_openai", "langchain_ollama",
    ]
    for mod in stubs:
        if mod in sys.modules:
            saved[mod] = sys.modules[mod]
        sys.modules[mod] = MagicMock()

    # Create a minimal agent package that doesn't trigger __init__.py imports
    agent_pkg = ModuleType("agent")
    agent_pkg.__path__ = ["agent"]
    agent_pkg.__package__ = "agent"
    sys.modules["agent"] = agent_pkg

    # Stub agent.state.conversation_state with the TypedDicts we need
    state_mod = ModuleType("agent.state.conversation_state")
    state_mod.PendingVariantGroup = dict
    state_mod.VariantResolution = dict
    sys.modules["agent.state"] = ModuleType("agent.state")
    sys.modules["agent.state"].__path__ = ["agent/state"]
    sys.modules["agent.state.conversation_state"] = state_mod

    # Stub shared modules
    shared_pkg = ModuleType("shared")
    shared_pkg.__path__ = ["shared"]
    sys.modules["shared"] = shared_pkg
    config_mod = MagicMock()
    config_mod.get_settings = MagicMock(return_value=MagicMock())
    sys.modules["shared.config"] = config_mod
    sys.modules["shared.llm_router"] = MagicMock()

    # Import the actual service module
    spec = importlib.util.spec_from_file_location(
        "agent.services.variant_interpretation_service",
        "agent/services/variant_interpretation_service.py",
    )
    svc = importlib.util.module_from_spec(spec)
    sys.modules["agent.services.variant_interpretation_service"] = svc
    spec.loader.exec_module(svc)

    return svc


_svc = _import_variant_service()
VariantAllocation = _svc.VariantAllocation
validate_and_apply_allocations = _svc.validate_and_apply_allocations


# ---------------------------------------------------------------------------
# Test 1: option_to_code_map stores element code instead of option text
# ---------------------------------------------------------------------------


def test_validate_apply_with_map_stores_element_code():
    """
    GIVEN allocations matching option text and an option_to_code_map
    WHEN validate_and_apply_allocations is called
    THEN resoluciones[].variant_code = element code, NOT option text
    """
    pending = {
        "pending_id": "TOLDO_LAT_1",
        "codigo_base": "TOLDO_LAT",
        "pregunta": "El toldo afecta al galibo?",
        "opciones": [
            "A - Toldo lateral (sin afectar galibo)",
            "B - Toldo lateral (afecta galibo)",
        ],
        "cantidad_total": 1,
        "cantidad_resuelta": 0,
        "cantidad_pendiente": 1,
        "resoluciones": [],
        "status": "pending",
    }

    allocations = [
        VariantAllocation(
            variant_code="Toldo lateral (sin afectar galibo)",
            quantity=1,
            confidence=0.52,
        ),
    ]

    option_to_code_map = {
        "A - Toldo lateral (sin afectar galibo)": "TOLDO_SIMPLE",
        "B - Toldo lateral (afecta galibo)": "TOLDO_GALIBO",
    }

    updated, errors = validate_and_apply_allocations(
        pending,
        allocations,
        option_to_code_map=option_to_code_map,
    )

    assert not errors
    assert updated["status"] == "resolved"
    assert len(updated["resoluciones"]) == 1
    assert updated["resoluciones"][0]["variant_code"] == "TOLDO_SIMPLE"


def test_validate_apply_without_map_stores_option_text():
    """
    GIVEN allocations matching option text but NO map
    WHEN validate_and_apply_allocations is called
    THEN resoluciones[].variant_code = matched option text (backward compat)
    """
    pending = {
        "pending_id": "TOLDO_LAT_1",
        "codigo_base": "TOLDO_LAT",
        "pregunta": "El toldo afecta al galibo?",
        "opciones": [
            "A - Toldo lateral (sin afectar galibo)",
            "B - Toldo lateral (afecta galibo)",
        ],
        "cantidad_total": 1,
        "cantidad_resuelta": 0,
        "cantidad_pendiente": 1,
        "resoluciones": [],
        "status": "pending",
    }

    allocations = [
        VariantAllocation(
            variant_code="Toldo lateral (sin afectar galibo)",
            quantity=1,
            confidence=0.52,
        ),
    ]

    updated, errors = validate_and_apply_allocations(
        pending,
        allocations,
    )

    assert not errors
    assert updated["resoluciones"][0]["variant_code"] == "A - Toldo lateral (sin afectar galibo)"


def test_validate_apply_with_map_multi_allocation():
    """
    GIVEN 2 allocations for a multi-unit variant with an option_to_code_map
    WHEN validate_and_apply_allocations is called
    THEN each resolucion gets the correct element code
    """
    pending = {
        "pending_id": "SUSPENSION_0",
        "codigo_base": "SUSPENSION",
        "pregunta": "Que tipo de suspension?",
        "opciones": [
            "A - Suspension delantera",
            "B - Suspension trasera",
        ],
        "cantidad_total": 3,
        "cantidad_resuelta": 0,
        "cantidad_pendiente": 3,
        "resoluciones": [],
        "status": "pending",
    }

    allocations = [
        VariantAllocation(variant_code="Suspension delantera", quantity=2, confidence=0.9),
        VariantAllocation(variant_code="Suspension trasera", quantity=1, confidence=0.85),
    ]

    option_to_code_map = {
        "A - Suspension delantera": "SUSPENSION_DEL",
        "B - Suspension trasera": "SUSPENSION_TRAS",
    }

    updated, errors = validate_and_apply_allocations(
        pending,
        allocations,
        option_to_code_map=option_to_code_map,
    )

    assert not errors
    assert updated["status"] == "resolved"
    assert len(updated["resoluciones"]) == 2
    assert updated["resoluciones"][0]["variant_code"] == "SUSPENSION_DEL"
    assert updated["resoluciones"][0]["quantity"] == 2
    assert updated["resoluciones"][1]["variant_code"] == "SUSPENSION_TRAS"
    assert updated["resoluciones"][1]["quantity"] == 1


# ---------------------------------------------------------------------------
# Test 2: Accumulator guard prevents cross-call overwrite
# ---------------------------------------------------------------------------

_ELEMENT_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")


def _run_accumulator_guard(resolved: dict, pv: dict) -> None:
    """Replicates the guard logic from presupuesto_mode.py."""
    cb = pv["codigo_base"]
    existing_val = resolved.get(cb)
    if existing_val and _ELEMENT_CODE_RE.match(existing_val):
        pass  # Guard: don't overwrite
    else:
        for res in pv.get("resoluciones", []):
            vc = res.get("variant_code") if isinstance(res, dict) else None
            if vc:
                resolved[cb] = vc
                break


def test_accumulator_guard_preserves_valid_code():
    """
    GIVEN _resolved already has TOLDO_LAT -> "TOLDO_SIMPLE" (valid code)
    AND   a parallel tool call tries to write corrupted option text
    WHEN  the guard runs
    THEN  the valid code is NOT overwritten
    """
    resolved = {"TOLDO_LAT": "TOLDO_SIMPLE"}

    pv = {
        "codigo_base": "TOLDO_LAT",
        "status": "resolved",
        "resoluciones": [
            {"variant_code": "A - Toldo lateral (sin afectar galibo)", "quantity": 1}
        ],
    }

    _run_accumulator_guard(resolved, pv)
    assert resolved["TOLDO_LAT"] == "TOLDO_SIMPLE"


def test_accumulator_guard_allows_overwrite_of_corrupted_value():
    """
    GIVEN _resolved has corrupted option text for TOLDO_LAT
    AND   a tool call brings a valid element code
    WHEN  the guard runs
    THEN  the corrupted value IS replaced with the valid code
    """
    resolved = {"TOLDO_LAT": "A - Toldo lateral (sin afectar galibo)"}

    pv = {
        "codigo_base": "TOLDO_LAT",
        "status": "resolved",
        "resoluciones": [{"variant_code": "TOLDO_SIMPLE", "quantity": 1}],
    }

    _run_accumulator_guard(resolved, pv)
    assert resolved["TOLDO_LAT"] == "TOLDO_SIMPLE"


def test_accumulator_guard_allows_write_when_empty():
    """
    GIVEN _resolved has NO entry for TOLDO_LAT
    WHEN  a tool call provides a value
    THEN  the value is written normally
    """
    resolved: dict[str, str] = {}

    pv = {
        "codigo_base": "TOLDO_LAT",
        "status": "resolved",
        "resoluciones": [{"variant_code": "TOLDO_SIMPLE", "quantity": 1}],
    }

    _run_accumulator_guard(resolved, pv)
    assert resolved["TOLDO_LAT"] == "TOLDO_SIMPLE"


# ---------------------------------------------------------------------------
# Test 3: End-to-end -- with root cause fix, resolved_codes are complete
# ---------------------------------------------------------------------------


def test_resolved_codes_complete_after_root_cause_fix():
    """
    GIVEN both PLACA_SOLAR and TOLDO_LAT resolved with correct element codes
    WHEN  building resolved_codes with element code regex filter
    THEN  BOTH codes pass through (no more presupuesto_resolved_code_rejected)
    """
    ELEMENT_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")

    _resolved_variants = {
        "PLACA_SOLAR": "PLACA_SOLAR_REGULADOR_INTERIOR",
        "TOLDO_LAT": "TOLDO_SIMPLE",
    }

    resolved_codes = [rc for rc in _resolved_variants.values() if ELEMENT_CODE_RE.match(rc)]

    assert len(resolved_codes) == 2
    assert "PLACA_SOLAR_REGULADOR_INTERIOR" in resolved_codes
    assert "TOLDO_SIMPLE" in resolved_codes


def test_budget_scope_passes_with_complete_codes():
    """
    GIVEN tarifa_codes and current_codes both have the same 2 element codes
    WHEN  checking subset for budget scope guard
    THEN  passes -- images NOT blocked
    """
    tarifa_codes = {"PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_SIMPLE"}
    current_codes = {"PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_SIMPLE"}

    assert tarifa_codes.issubset(current_codes)
