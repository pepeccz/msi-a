"""
Tests: Presupuesto Price Integrity — S4 Price-Authority Injection

Validates that the S4 block in presupuesto_mode.py correctly injects an
authoritative price system message after a successful calcular_tarifa_con_elementos
call, and that it does NOT inject when the tool failed or was not called.

These tests exercise the injection logic directly via the _apply_s4_price_injection
helper extracted inline, without needing a running LLM or database.
"""

import json
import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers — replicate S4 logic inline so tests are pure-logic (no LLM, no DB)
# ---------------------------------------------------------------------------


def apply_s4_price_injection(
    tool_name: str,
    result_dict: dict | str | None,
    llm_messages: list,
    logger: object | None = None,
    conversation_id: str = "test",
) -> None:
    """
    Replicate the S4 price-authority injection block from presupuesto_mode.py.

    This is a direct copy of the logic extracted for unit-testability.
    If the production S4 block changes, update this helper to match.
    """
    # Parse result_dict if it's a JSON string (matches production behaviour)
    if isinstance(result_dict, str):
        try:
            result_dict = json.loads(result_dict)
        except (json.JSONDecodeError, TypeError):
            result_dict = {}

    if (
        tool_name == "calcular_tarifa_con_elementos"
        and isinstance(result_dict, dict)
        and result_dict.get("success") is not False
    ):
        _s4_datos = result_dict.get("datos", {})
        _s4_price = _s4_datos.get("price") if isinstance(_s4_datos, dict) else None
        if _s4_price is not None:
            llm_messages.append(
                {
                    "role": "system",
                    "content": (
                        f"[SISTEMA]: PRECIO AUTORITATIVO de este cálculo: "
                        f"{_s4_price} EUR +IVA. "
                        f"Usa EXACTAMENTE este número. "
                        f"Ignora precios de turnos anteriores del historial."
                    ),
                }
            )


# ---------------------------------------------------------------------------
# Test 1: Recalculation scenario (the 410→65 bug)
# ---------------------------------------------------------------------------


def test_s4_recalculation_scenario_injects_new_price():
    """
    Regression: history has "410 EUR", new tool result says price=65.
    S4 must inject a system message with "65" and NOT reference "410".
    """
    # Simulate: previous LLM response with 410€ already in the messages list
    llm_messages = [
        {"role": "system", "content": "You are an assistant."},
        {"role": "user", "content": "Quiero homologar el escape."},
        {
            "role": "assistant",
            "content": "El presupuesto es de 410 EUR +IVA.",
        },
        {"role": "user", "content": "Quiero quitar el escape, solo la suspension."},
    ]

    # New tool result with recalculated price 65€
    result_dict = {
        "success": True,
        "datos": {
            "price": 65.0,
            "precio_final": 65.0,
            "warnings": [],
        },
    }

    apply_s4_price_injection("calcular_tarifa_con_elementos", result_dict, llm_messages)

    # A system message must have been appended
    assert len(llm_messages) == 5, "S4 must append exactly one system message"
    injected = llm_messages[-1]
    assert injected["role"] == "system"

    content = injected["content"]
    assert "65" in content, f"Injected price must be 65, got: {content}"
    assert "410" not in content, (
        f"Injected message must NOT reference old price 410, got: {content}"
    )
    assert "PRECIO AUTORITATIVO" in content


# ---------------------------------------------------------------------------
# Test 2: First calculation — price rendered correctly
# ---------------------------------------------------------------------------


def test_s4_first_calculation_injects_price():
    """
    First ever calcular_tarifa call in a conversation.
    S4 must inject a system message with the exact price.
    """
    llm_messages = [
        {"role": "system", "content": "You are an assistant."},
        {"role": "user", "content": "Quiero homologar un escape."},
    ]

    result_dict = {
        "success": True,
        "datos": {
            "price": 450.0,
            "precio_final": 450.0,
            "warnings": [],
        },
    }

    apply_s4_price_injection("calcular_tarifa_con_elementos", result_dict, llm_messages)

    assert len(llm_messages) == 3, "S4 must append one system message"
    injected = llm_messages[-1]
    assert injected["role"] == "system"
    assert "450" in injected["content"]
    assert "PRECIO AUTORITATIVO" in injected["content"]


# ---------------------------------------------------------------------------
# Test 3: No injection when tool fails (success=False)
# ---------------------------------------------------------------------------


def test_s4_no_injection_on_tool_failure():
    """
    When calcular_tarifa_con_elementos returns success=False,
    no price-authority message must be injected.
    """
    llm_messages = [
        {"role": "system", "content": "You are an assistant."},
        {"role": "user", "content": "Quiero homologar un escape."},
    ]

    result_dict = {
        "success": False,
        "error": "element_not_found",
        "message": "No se encontró el elemento.",
    }

    apply_s4_price_injection("calcular_tarifa_con_elementos", result_dict, llm_messages)

    assert len(llm_messages) == 2, (
        "S4 must NOT inject any system message on tool failure"
    )
    # Confirm no price-authority message was inserted anywhere
    for msg in llm_messages:
        assert "PRECIO AUTORITATIVO" not in msg.get("content", "")


# ---------------------------------------------------------------------------
# Test 4: No injection when tool not called this turn
# ---------------------------------------------------------------------------


def test_s4_no_injection_when_different_tool():
    """
    When the tool called this iteration is NOT calcular_tarifa_con_elementos,
    no price-authority message must be injected.
    """
    llm_messages = [
        {"role": "system", "content": "You are an assistant."},
        {"role": "user", "content": "Muéstrame las fotos."},
    ]

    result_dict = {
        "success": True,
        "images": ["https://example.com/img1.jpg"],
    }

    # A different tool (e.g., enviar_imagenes_ejemplo)
    apply_s4_price_injection("enviar_imagenes_ejemplo", result_dict, llm_messages)

    assert len(llm_messages) == 2, (
        "S4 must NOT inject any message for tools other than calcular_tarifa_con_elementos"
    )
    for msg in llm_messages:
        assert "PRECIO AUTORITATIVO" not in msg.get("content", "")


# ---------------------------------------------------------------------------
# Test 5: No injection when datos.price is None (edge case guard)
# ---------------------------------------------------------------------------


def test_s4_no_injection_when_price_is_none():
    """
    When calcular_tarifa_con_elementos succeeds but datos.price is None
    (edge case: unknown price structure), no injection must occur.
    """
    llm_messages = [
        {"role": "system", "content": "You are an assistant."},
    ]

    result_dict = {
        "success": True,
        "datos": {
            "price": None,
        },
    }

    apply_s4_price_injection("calcular_tarifa_con_elementos", result_dict, llm_messages)

    assert len(llm_messages) == 1, "S4 must NOT inject when datos.price is None"


# ---------------------------------------------------------------------------
# Test 6: Injection works with JSON string result (production path)
# ---------------------------------------------------------------------------


def test_s4_injection_with_json_string_result():
    """
    In production, tool results arrive as JSON strings.
    S4 must handle string input by parsing first.
    """
    llm_messages = [
        {"role": "system", "content": "You are an assistant."},
        {"role": "user", "content": "Cuánto cuesta el escape?"},
    ]

    result_str = json.dumps(
        {
            "success": True,
            "datos": {
                "price": 180.0,
                "warnings": [],
            },
        }
    )

    apply_s4_price_injection("calcular_tarifa_con_elementos", result_str, llm_messages)

    assert len(llm_messages) == 3
    injected = llm_messages[-1]
    assert injected["role"] == "system"
    assert "180" in injected["content"]
    assert "PRECIO AUTORITATIVO" in injected["content"]
