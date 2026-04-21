"""
Strip LLM-hallucinated "send failed" phrasings when images were actually queued.

Repro bug: user asks for example images, `enviar_imagenes_ejemplo` returns
`success=true` and queues 6 images, but the LLM copies the failure example
sentence from pre_expediente_post_price.md verbatim ("No he podido enviarte
los ejemplos en este momento."), so the user sees failure text while the
images arrive.
"""
from __future__ import annotations

from pathlib import Path

from agent.modes.pre_expediente_mode import _strip_false_image_failure_phrasing


_POST_PRICE_MD = (
    Path(__file__).parents[3]
    / "agent"
    / "prompts"
    / "modes"
    / "pre_expediente_post_price.md"
)


# ---------------------------------------------------------------------------
# Prompt-level: failure example removed, success branch imperative
# ---------------------------------------------------------------------------

def test_post_price_prompt_no_longer_lists_fail_example_verbatim() -> None:
    text = _POST_PRICE_MD.read_text(encoding="utf-8")
    # The old prompt literally quoted the hallucinated sentence as an example.
    assert '"No he podido enviarte los ejemplos en este momento."' not in text


def test_post_price_prompt_forbids_fail_phrases_on_success() -> None:
    text = _POST_PRICE_MD.read_text(encoding="utf-8")
    assert "PROHIBIDO" in text
    assert "no he podido" in text.lower()


# ---------------------------------------------------------------------------
# Strip behaviour
# ---------------------------------------------------------------------------

def test_strip_removes_exact_repro_sentence() -> None:
    raw = (
        "No he podido enviarte los ejemplos en este momento.\n\n"
        "¿Abrimos expediente o tienes alguna duda?"
    )
    out = _strip_false_image_failure_phrasing(
        ai_response=raw,
        tools_called=["enviar_imagenes_ejemplo"],
        imagenes_enviadas_codigos=["A", "B", "C"],
    )
    assert "No he podido enviarte" not in out
    assert "Abrimos expediente" in out


def test_strip_removes_variant_no_pude() -> None:
    raw = "No pude enviarte las imágenes.\n\n¿Abrimos expediente o tienes alguna duda?"
    out = _strip_false_image_failure_phrasing(
        ai_response=raw,
        tools_called=["enviar_imagenes_ejemplo"],
        imagenes_enviadas_codigos=["A"],
    )
    assert "No pude enviarte" not in out


def test_strip_removes_variant_no_se_han_podido_enviar() -> None:
    raw = "Las imágenes no se han podido enviar ahora.\n\nCTA?"
    out = _strip_false_image_failure_phrasing(
        ai_response=raw,
        tools_called=["enviar_imagenes_ejemplo"],
        imagenes_enviadas_codigos=["A"],
    )
    assert "no se han" not in out.lower()


def test_strip_noop_when_tool_not_called() -> None:
    raw = "No he podido enviarte los ejemplos."
    out = _strip_false_image_failure_phrasing(
        ai_response=raw,
        tools_called=["calcular_tarifa_con_elementos"],
        imagenes_enviadas_codigos=["A"],
    )
    assert out == raw


def test_strip_noop_when_codigos_empty() -> None:
    raw = "No he podido enviarte los ejemplos."
    out = _strip_false_image_failure_phrasing(
        ai_response=raw,
        tools_called=["enviar_imagenes_ejemplo"],
        imagenes_enviadas_codigos=[],
    )
    assert out == raw


def test_strip_preserves_legitimate_content() -> None:
    raw = "¿Abrimos expediente o tienes alguna duda?"
    out = _strip_false_image_failure_phrasing(
        ai_response=raw,
        tools_called=["enviar_imagenes_ejemplo"],
        imagenes_enviadas_codigos=["A"],
    )
    assert out == raw


def test_strip_collapses_blank_runs_after_removal() -> None:
    raw = (
        "No he podido enviarte los ejemplos en este momento.\n\n\n"
        "¿Abrimos expediente o tienes alguna duda?"
    )
    out = _strip_false_image_failure_phrasing(
        ai_response=raw,
        tools_called=["enviar_imagenes_ejemplo"],
        imagenes_enviadas_codigos=["A"],
    )
    assert "\n\n\n" not in out
