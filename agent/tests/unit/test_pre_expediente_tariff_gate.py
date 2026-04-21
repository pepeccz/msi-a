"""
L3 tariff-gate tests — premature-CTA/footer red-net.

Covers the <tariff_gate> rule in pre_expediente_pricing.md (L2/L3):
when no price was communicated AND no tarifa is stored AND the response
has no numeric price literal, premature CTAs (3/4/5) and the
"_Precios válidos por 30 días._" footer must be stripped.

Defense-in-depth for the prompt-level rule. If the LLM emits them anyway,
_strip_premature_price_artifacts removes them before render.
"""
from __future__ import annotations

from pathlib import Path

from agent.modes.pre_expediente_mode import (
    _propagate_post_self_heal_state,
    _strip_premature_price_artifacts,
)
from agent.prompts.ctas_catalog import CTAS


_PRICING_MD = (
    Path(__file__).parents[3]
    / "agent"
    / "prompts"
    / "modes"
    / "pre_expediente_pricing.md"
)


# ---------------------------------------------------------------------------
# Prompt-level drift guards
# ---------------------------------------------------------------------------

def test_pricing_prompt_has_tariff_gate_block() -> None:
    text = _PRICING_MD.read_text(encoding="utf-8")
    assert "<tariff_gate>" in text
    assert "</tariff_gate>" in text
    assert "calcular_tarifa_con_elementos" in text


def test_pricing_prompt_has_priority_hierarchy() -> None:
    text = _PRICING_MD.read_text(encoding="utf-8")
    assert "<priority_hierarchy>" in text
    assert "L1" in text and "L2" in text and "L3" in text


def test_pricing_prompt_footer_is_conditional() -> None:
    text = _PRICING_MD.read_text(encoding="utf-8")
    # Old unconditional wording must be gone
    assert "SIEMPRE incluye al final de toda comunicación de precio" not in text
    # New conditional wording present
    assert 'SOLO si el mensaje contiene el precio numérico' in text


# ---------------------------------------------------------------------------
# _strip_premature_price_artifacts behaviour
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# F2 — short-circuit when stripping would empty the response
# Spec: sdd/fix-pricing-gate-self-heal-loop/spec — "Output Guard
# Empty-Result Short-Circuit"
# ---------------------------------------------------------------------------

def test_strip_short_circuits_when_result_below_threshold() -> None:
    """Single-paragraph confirmation containing 'presupuesto' must NOT be
    nuked to empty — the guard preserves the original text instead.
    Reproduces the production bug: msg "Hola, quiero homologar el subchasis..."
    where the LLM emitted a single-sentence confirmation that, after sentence-
    level stripping, collapsed to <30 chars and triggered the empty safety net.
    """
    raw = (
        "Antes de calcularte el presupuesto, necesito una confirmación rápida: "
        "¿quieres homologar los dos elementos?"
    )
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=False, tarifa_calculada=None
    )
    assert out == raw, "guard must short-circuit instead of nuking entire text"


def test_strip_returns_short_input_unchanged() -> None:
    """If input itself is below threshold (<30 chars), guard is a no-op."""
    raw = "Te paso el presupuesto."  # contains "presupuesto" but already short
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=False, tarifa_calculada=None
    )
    assert out == raw


def test_strip_keeps_partial_when_above_threshold() -> None:
    """Multi-sentence text where stripping leaves >=30 chars must strip
    normally (NO short-circuit)."""
    keeper = "Para tu moto puedes homologar los dos elementos sin problema. "
    stripped = "Te paso el presupuesto enseguida. "
    raw = keeper + stripped + "Necesito una confirmación final, ¿de acuerdo?"
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=False, tarifa_calculada=None
    )
    assert "presupuesto" not in out
    assert "puedes homologar los dos elementos" in out
    assert len(out.strip()) >= 30


def test_strip_removes_cta3_when_no_price() -> None:
    raw = f"Documentación general:\n- Foto\n\n{CTAS[3]}"
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=False, tarifa_calculada=None
    )
    assert CTAS[3] not in out
    assert "Documentación general" in out


def test_strip_removes_cta4_when_no_price() -> None:
    raw = f"Info útil.\n\n{CTAS[4]}"
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=False, tarifa_calculada=None
    )
    assert CTAS[4] not in out


def test_strip_removes_cta5_when_no_price() -> None:
    raw = f"Texto.\n\n{CTAS[5]}"
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=False, tarifa_calculada=None
    )
    assert CTAS[5] not in out


def test_strip_removes_footer_when_no_price() -> None:
    raw = "Documentación...\n\n_Precios válidos por 30 días._"
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=False, tarifa_calculada=None
    )
    assert "Precios válidos por 30 días" not in out


def test_strip_noop_when_precio_comunicado() -> None:
    raw = f"El presupuesto es *410€ +IVA*.\n\n{CTAS[4]}"
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=True, tarifa_calculada={"total": 410}
    )
    assert out == raw


def test_strip_noop_when_tarifa_present() -> None:
    raw = f"Texto.\n\n{CTAS[4]}"
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=False, tarifa_calculada={"total": 410}
    )
    assert out == raw


def test_strip_noop_when_price_literal_in_response() -> None:
    # Self-healing: if the response somehow contains a price, assume valid
    raw = f"El presupuesto es *410€ +IVA*.\n\n{CTAS[4]}"
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=False, tarifa_calculada=None
    )
    assert out == raw


def test_strip_removes_tuteo_cta5_variant() -> None:
    raw = "Texto.\n\n¿Abrimos expediente o tienes alguna duda?"
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=False, tarifa_calculada=None
    )
    assert "Abrimos expediente" not in out


def test_strip_regression_subchasis_agarraderas_case() -> None:
    """Exact repro of the reported bug: subchasis + agarraderas without price."""
    raw = (
        "Documentación general:\n"
        "- Foto de la ficha técnica\n"
        "- Foto del DNI\n\n"
        "Documentación del subchasis:\n"
        "- subchasis-tanque-moto\n\n"
        "⚠️ Esta modificación es compleja.\n\n"
        "_Precios válidos por 30 días._\n\n"
        f"{CTAS[4]}"
    )
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=False, tarifa_calculada=None
    )
    assert CTAS[4] not in out
    assert "Precios válidos por 30 días" not in out
    # Documentation survives
    assert "Documentación general" in out
    assert "subchasis-tanque-moto" in out
    assert "⚠️" in out


def test_strip_collapses_triple_newlines() -> None:
    raw = f"Texto.\n\n\n\n{CTAS[4]}\n\n_Precios válidos por 30 días._"
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=False, tarifa_calculada=None
    )
    assert "\n\n\n" not in out


# ---------------------------------------------------------------------------
# F1 — Post-self-heal state propagation
# Spec: sdd/fix-pricing-gate-self-heal-loop/spec — "Post-Self-Heal State
# Propagation Contract"
# ---------------------------------------------------------------------------

_TARIFA_PAYLOAD = {
    "datos": {
        "tier_name": "Moto - 2 elementos",
        "price": 410.0,
        "elements": ["Subchasis", "Asideros"],
        "warnings": [],
    }
}


def test_propagate_sets_precio_comunicado_when_tarifa_present() -> None:
    mc, sc, tools, fired = _propagate_post_self_heal_state(
        updated_context={"tarifa_calculada": _TARIFA_PAYLOAD, "categoria_slug": "motos-part"},
        shared_context={},
        tools_called=["identificar_y_resolver_elementos"],
    )
    assert fired is True
    assert mc["precio_comunicado"] is True
    assert sc["precio_comunicado"] is True
    assert "calcular_tarifa_con_elementos" in tools
    assert "identificar_y_resolver_elementos" in tools  # preserved


def test_propagate_noop_when_tarifa_missing() -> None:
    mc, sc, tools, fired = _propagate_post_self_heal_state(
        updated_context={"categoria_slug": "motos-part"},  # no tarifa
        shared_context={"existing": "value"},
        tools_called=["identificar_y_resolver_elementos"],
    )
    assert fired is False
    assert "precio_comunicado" not in mc
    assert sc == {"existing": "value"}
    assert tools == ["identificar_y_resolver_elementos"]


def test_propagate_noop_when_tarifa_falsy() -> None:
    mc, _sc, _tools, fired = _propagate_post_self_heal_state(
        updated_context={"tarifa_calculada": None},
        shared_context={},
        tools_called=[],
    )
    assert fired is False
    assert mc.get("precio_comunicado") is None


def test_propagate_does_not_duplicate_calcular_tarifa() -> None:
    _mc, _sc, tools, fired = _propagate_post_self_heal_state(
        updated_context={"tarifa_calculada": _TARIFA_PAYLOAD},
        shared_context={},
        tools_called=["calcular_tarifa_con_elementos"],  # already present
    )
    assert fired is True
    assert tools.count("calcular_tarifa_con_elementos") == 1


def test_propagate_preserves_other_shared_context_keys() -> None:
    _mc, sc, _tools, fired = _propagate_post_self_heal_state(
        updated_context={"tarifa_calculada": _TARIFA_PAYLOAD},
        shared_context={"warnings_acknowledged": True, "other": "x"},
        tools_called=[],
    )
    assert fired is True
    assert sc["precio_comunicado"] is True
    assert sc["warnings_acknowledged"] is True
    assert sc["other"] == "x"


def test_propagate_does_not_mutate_input_dicts() -> None:
    in_mc = {"tarifa_calculada": _TARIFA_PAYLOAD}
    in_sc = {"existing": "value"}
    in_tools = ["identificar_y_resolver_elementos"]
    out_mc, out_sc, out_tools, _ = _propagate_post_self_heal_state(
        updated_context=in_mc, shared_context=in_sc, tools_called=in_tools
    )
    # Inputs unchanged
    assert in_mc == {"tarifa_calculada": _TARIFA_PAYLOAD}
    assert "precio_comunicado" not in in_mc
    assert in_sc == {"existing": "value"}
    assert in_tools == ["identificar_y_resolver_elementos"]
    # Outputs are new objects
    assert out_mc is not in_mc
    assert out_sc is not in_sc
    assert out_tools is not in_tools

