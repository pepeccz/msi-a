"""
Pin the kickoff instruction structure produced by
``build_new_expediente_case_instructions``.

UX regression reported: LLM emitted a terse "1. Foto del aseidero. Envíamelas
como foto o como PDF." on the first turn of a freshly opened expediente.
The kickoff template now forces a warm opener, a fixed transition, a
numbered photo list with a per-photo rationale, and a fixed closing that
invites the user to request visual examples or send their photos and wait.
"""
from __future__ import annotations

from agent.services.expediente_onboarding import (
    build_new_expediente_case_instructions,
)


def _render(**kwargs) -> str:
    defaults = dict(first_element_display="ASIDEROS", total_elements=2)
    defaults.update(kwargs)
    return build_new_expediente_case_instructions(**defaults)


def test_kickoff_contains_warm_opener_variants() -> None:
    text = _render()
    assert "Excelente, te he abierto un expediente" in text
    assert "¡Perfecto! Ya tienes tu expediente abierto" in text
    assert "Genial, acabo de abrir tu expediente de homologación" in text


def test_kickoff_contains_fixed_transition() -> None:
    text = _render()
    assert "Ahora necesito que me envíes las siguientes imágenes:" in text


def test_kickoff_contains_fixed_closing() -> None:
    text = _render()
    assert "Si quieres que te envíe imágenes de ejemplo" in text
    assert "envíame tus fotos y espera a que las procese" in text
    assert "¡Gracias!" in text


def test_kickoff_forbids_old_terse_closing() -> None:
    text = _render()
    # Hard ban on the old terse close that produced the regression.
    assert "Envíamelas como foto o como PDF" in text  # appears inside PROHIBIDO
    assert "PROHIBIDO" in text


def test_kickoff_forbids_voseo_forms() -> None:
    text = _render()
    # Project guideline: castellano de España — tuteo only.
    assert "Nada de voseo" in text or "tuteo" in text.lower()


def test_kickoff_requires_rationale_per_photo() -> None:
    text = _render()
    assert "motivo breve" in text or "para qué se usa" in text


def test_kickoff_includes_first_element_and_total() -> None:
    text = _render(first_element_display="SUBCHASIS", total_elements=3)
    assert "SUBCHASIS" in text
    assert "1/3" in text or "TOTAL ELEMENTOS: 3" in text


def test_kickoff_still_forbids_initiating_or_finalizing_without_tool() -> None:
    text = _render()
    assert "NO llames iniciar_expediente()" in text
    assert "finalizar_expediente()" in text
