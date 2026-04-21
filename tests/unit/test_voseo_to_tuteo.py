"""
Defensive voseo → tuteo normalisation applied to every outbound message.

The bot persona is Castilian Spain (tuteo). The LLM occasionally drifts
into Rioplatense voseo ("tenés", "dale", "pedímelo"). `normalize_voseo_to_tuteo`
maps the common drifts to their Castilian equivalents as a safety net.
"""
from __future__ import annotations

import pytest

from shared.text_utils import normalize_voseo_to_tuteo, strip_markdown_for_whatsapp


@pytest.mark.parametrize(
    "src,expected",
    [
        ("¿Tenés alguna duda?", "¿Tienes alguna duda?"),
        ("tenés", "tienes"),
        ("Querés que te envíe ejemplos?", "Quieres que te envíe ejemplos?"),
        ("No podés avanzar sin eso", "No puedes avanzar sin eso"),
        ("Mirá esta foto", "Mira esta foto"),
        ("Enviá tus fotos", "Envía tus fotos"),
        ("Llamá al teléfono", "Llama al teléfono"),
        ("Usá este tool", "Usa este tool"),
        ("Pedímelo cuando quieras", "Pídemelo cuando quieras"),
        ("Dale, seguimos", "Vale, seguimos"),
        ("Esperá un momento", "Espera un momento"),
        ("Hacé click aquí", "Haz click aquí"),
        ("Contame qué pasa", "Cuéntame qué pasa"),
        ("Mostrame el subchasis", "Muéstrame el subchasis"),
    ],
)
def test_common_voseo_forms_normalised(src: str, expected: str) -> None:
    assert normalize_voseo_to_tuteo(src) == expected


def test_noop_on_already_tuteo_text() -> None:
    raw = "Hola, ¿tienes alguna duda? Pídemelo y te envío los ejemplos."
    assert normalize_voseo_to_tuteo(raw) == raw


def test_preserves_capitalisation() -> None:
    assert normalize_voseo_to_tuteo("Tenés que esperar") == "Tienes que esperar"
    assert normalize_voseo_to_tuteo("Dale") == "Vale"
    # ALL CAPS also normalised (case-insensitive match, Title-cased output).
    assert normalize_voseo_to_tuteo("MIRÁ eso") == "Mira eso"


def test_word_boundary_avoids_false_positives() -> None:
    # 'dale' as substring inside 'desordenadamente' must not match
    assert normalize_voseo_to_tuteo("desordenadamente") == "desordenadamente"
    # 'mirá' substring inside 'admirá' (not a real word but ensures boundary)
    assert normalize_voseo_to_tuteo("Admiración") == "Admiración"


def test_noop_on_empty_or_none_like() -> None:
    assert normalize_voseo_to_tuteo("") == ""


def test_strip_markdown_pipes_through_voseo_normalisation() -> None:
    raw = "**Tenés** que enviar las fotos. Dale, *hacé* click."
    out = strip_markdown_for_whatsapp(raw)
    assert "Tenés" not in out
    assert "Dale" not in out
    assert "hacé" not in out
    assert "Tienes" in out
    assert "haz" in out  # mid-sentence keeps lowercase
    assert "Vale" in out


def test_repro_observed_llm_drift() -> None:
    raw = "Pedímelos si querés ver ejemplos. Envialos cuando los tengás."
    # "tengás" not in our table — leave it for the prompt to handle.
    out = normalize_voseo_to_tuteo(raw)
    assert "Pedímelos" not in out
    assert "Pídemelos" in out
    assert "querés" not in out
    assert "quieres" in out
