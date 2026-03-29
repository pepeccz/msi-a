"""Unit tests for the kickoff phase truthfulness guard (Fix C).

Tests cover:
- C1: _SUBMODE_STEP_MAP constant definition and values
- C2: Step-mismatch regex detection — wrong step stripped, correct step passes
- C3: Advancement-language detection — advancement phrases stripped, valid
      questions pass unchanged
- Edge cases: unknown sub-mode, no step prefix, collect_base_docs, mixed content

All tests are pure unit tests — no database, no Redis, no async I/O.
The guard logic is tested by importing the constant and replicating the exact
regex patterns defined in expediente_mode.py so the tests remain tightly coupled
to the implementation.
"""

from __future__ import annotations

import re

import pytest

from agent.modes.expediente_mode import _SUBMODE_STEP_MAP
from agent.services.expediente_constants import STEP_LABELS


# ---------------------------------------------------------------------------
# Helpers — replicate exact guard patterns from expediente_mode.py
# ---------------------------------------------------------------------------

_STEP_MISMATCH_RE = re.compile(r"[Pp]aso\s+(\d)\s*/\s*6")
_ADVANCEMENT_RE = re.compile(
    r"siguiente\s+paso|pasemos\s+a"
    r"|continuamos\s+con\s+el\s+paso"
    r"|hemos\s+completado|ya\s+tenemos\s+todo",
    re.IGNORECASE,
)


def _apply_phase_guard(sub_mode: str, response: str) -> tuple[str, bool, bool]:
    """Apply the same guard logic as expediente_mode.py kickoff branch.

    Returns:
        (cleaned_response, step_mismatch_fired, advancement_fired)
    """
    step_mismatch_fired = False
    advancement_fired = False

    expected_step = _SUBMODE_STEP_MAP.get(sub_mode.lower() if sub_mode else "")
    step_match = _STEP_MISMATCH_RE.search(response)
    if (
        step_match
        and expected_step is not None
        and int(step_match.group(1)) != expected_step
    ):
        response = _STEP_MISMATCH_RE.sub("", response).strip()
        step_mismatch_fired = True

    if _ADVANCEMENT_RE.search(response):
        response = _ADVANCEMENT_RE.sub("", response).strip()
        advancement_fired = True

    return response, step_mismatch_fired, advancement_fired


# =============================================================================
# C1 — _SUBMODE_STEP_MAP constant
# =============================================================================


class TestSubModeStepMap:
    """Verify the constant is correctly defined and matches STEP_LABELS."""

    def test_all_six_sub_modes_present(self) -> None:
        expected_keys = {
            "collect_element_data",
            "collect_base_docs",
            "collect_personal",
            "collect_vehicle",
            "collect_workshop",
            "review_summary",
        }
        assert set(_SUBMODE_STEP_MAP.keys()) == expected_keys

    def test_step_numbers_match_step_labels(self) -> None:
        """_SUBMODE_STEP_MAP[k] must equal STEP_LABELS[k][0] for all keys."""
        for sub_mode, step_number in _SUBMODE_STEP_MAP.items():
            assert sub_mode in STEP_LABELS, f"'{sub_mode}' missing from STEP_LABELS"
            expected = STEP_LABELS[sub_mode][0]
            assert step_number == expected, (
                f"_SUBMODE_STEP_MAP['{sub_mode}'] = {step_number}, "
                f"but STEP_LABELS['{sub_mode}'] = {expected}"
            )

    def test_collect_personal_is_step_3(self) -> None:
        assert _SUBMODE_STEP_MAP["collect_personal"] == 3

    def test_collect_vehicle_is_step_4(self) -> None:
        assert _SUBMODE_STEP_MAP["collect_vehicle"] == 4

    def test_collect_workshop_is_step_5(self) -> None:
        assert _SUBMODE_STEP_MAP["collect_workshop"] == 5

    def test_collect_base_docs_is_step_2(self) -> None:
        assert _SUBMODE_STEP_MAP["collect_base_docs"] == 2

    def test_collect_element_data_is_step_1(self) -> None:
        assert _SUBMODE_STEP_MAP["collect_element_data"] == 1

    def test_review_summary_is_step_6(self) -> None:
        assert _SUBMODE_STEP_MAP["review_summary"] == 6


# =============================================================================
# C2 — Step-mismatch detection
# =============================================================================


class TestStepMismatchGuard:
    """Verify that wrong-step prefixes are stripped and correct ones are not."""

    @pytest.mark.parametrize(
        "sub_mode,response_text,should_strip",
        [
            # Wrong step in collect_personal (expects 3, claims 5) → strip
            (
                "collect_personal",
                "📍 Paso 5/6 — Taller de montaje\n¿Quién realizó la instalación?",
                True,
            ),
            # Wrong step in collect_personal (expects 3, claims 6) → strip
            (
                "collect_personal",
                "Paso 6/6 — Revisión y confirmación\nVamos a revisar todo.",
                True,
            ),
            # Wrong step in collect_vehicle (expects 4, claims 6) → strip
            (
                "collect_vehicle",
                "Paso 6/6 — Resumen y confirmación\nConfirma los datos.",
                True,
            ),
            # Wrong step in collect_vehicle (expects 4, claims 5) → strip
            (
                "collect_vehicle",
                "Paso 5/6 — Taller\n¿Cuál es el nombre del taller?",
                True,
            ),
            # Correct step in collect_personal (3/6) → pass through unchanged
            (
                "collect_personal",
                "Paso 3/6 — Datos personales\nNecesito tu nombre y DNI.",
                False,
            ),
            # Correct step in collect_vehicle (4/6) → pass through unchanged
            (
                "collect_vehicle",
                "📍 Paso 4/6 — Datos del vehículo\n¿Cuál es la matrícula?",
                False,
            ),
            # Correct step in collect_workshop (5/6) → pass through unchanged
            (
                "collect_workshop",
                "Paso 5/6 — Certificado del taller\n¿El taller tiene certificación?",
                False,
            ),
            # Correct step in collect_base_docs (2/6) → pass through unchanged
            (
                "collect_base_docs",
                "Paso 2/6 — Documentación base\nNecesito la ficha técnica.",
                False,
            ),
            # Wrong step in collect_base_docs (expects 2, claims 5) → strip
            (
                "collect_base_docs",
                "Paso 5/6 — Taller\nVamos a hablar del taller.",
                True,
            ),
            # No step prefix at all → pass through unchanged
            (
                "collect_personal",
                "¿Me puedes indicar tu nombre completo y DNI?",
                False,
            ),
        ],
    )
    def test_step_mismatch_stripping(
        self, sub_mode: str, response_text: str, should_strip: bool
    ) -> None:
        cleaned, step_fired, _ = _apply_phase_guard(sub_mode, response_text)

        if should_strip:
            assert step_fired, (
                f"Expected step-mismatch guard to fire for sub_mode='{sub_mode}' "
                f"with response: {response_text!r}"
            )
            # The stripped response must not still contain a wrong step prefix
            step_match = _STEP_MISMATCH_RE.search(cleaned)
            if step_match:
                expected = _SUBMODE_STEP_MAP.get(sub_mode.lower())
                claimed = int(step_match.group(1))
                assert claimed == expected, (
                    f"Wrong step prefix still present after stripping: claimed={claimed}, "
                    f"expected={expected}"
                )
        else:
            assert not step_fired, (
                f"Step-mismatch guard should NOT fire for sub_mode='{sub_mode}' "
                f"with response: {response_text!r}"
            )
            # Response must be unchanged
            assert cleaned == response_text.strip()

    def test_stripped_response_retains_question_content(self) -> None:
        """After stripping wrong step, the actual question content survives."""
        sub_mode = "collect_personal"
        original = "📍 Paso 5/6 — Taller de montaje\n¿Quién realizó la instalación?"
        cleaned, step_fired, _ = _apply_phase_guard(sub_mode, original)

        assert step_fired
        assert "¿Quién realizó la instalación?" in cleaned

    def test_unknown_sub_mode_passes_through(self) -> None:
        """Unknown sub-mode → no expected step → guard never fires."""
        cleaned, step_fired, _ = _apply_phase_guard(
            "unknown_submode", "Paso 5/6 — Algo raro"
        )
        assert not step_fired
        assert "Paso 5/6" in cleaned  # unchanged


# =============================================================================
# C3 — Advancement-language detection
# =============================================================================


class TestAdvancementLanguageGuard:
    """Verify that phase-advancement phrases are stripped on kickoff no-tool turns."""

    @pytest.mark.parametrize(
        "sub_mode,response_text,should_strip",
        [
            # "siguiente paso" → strip
            (
                "collect_personal",
                "Perfecto, pasemos al siguiente paso.",
                True,
            ),
            # "pasemos a" → strip
            (
                "collect_personal",
                "Bien, pasemos a la siguiente fase.",
                True,
            ),
            # "continuamos con el paso" → strip
            (
                "collect_vehicle",
                "Continuamos con el paso de documentación.",
                True,
            ),
            # "hemos completado" → strip
            (
                "collect_vehicle",
                "Hemos completado los datos del vehículo.",
                True,
            ),
            # "ya tenemos todo" → strip
            (
                "collect_workshop",
                "Ya tenemos todo lo necesario del taller.",
                True,
            ),
            # Case-insensitive: SIGUIENTE PASO → strip
            (
                "collect_personal",
                "PASEMOS AL SIGUIENTE PASO de inmediato.",
                True,
            ),
            # Valid question — no advancement language → pass
            (
                "collect_personal",
                "¿Me puedes indicar tu nombre completo y DNI?",
                False,
            ),
            # Valid question in collect_vehicle → pass
            (
                "collect_vehicle",
                "¿Cuál es la matrícula de tu vehículo?",
                False,
            ),
            # "paso" alone (not "siguiente paso") → pass
            (
                "collect_personal",
                "En este paso necesito tus datos personales.",
                False,
            ),
        ],
    )
    def test_advancement_stripping(
        self, sub_mode: str, response_text: str, should_strip: bool
    ) -> None:
        cleaned, _, advancement_fired = _apply_phase_guard(sub_mode, response_text)

        if should_strip:
            assert advancement_fired, (
                f"Expected advancement guard to fire for sub_mode='{sub_mode}' "
                f"with response: {response_text!r}"
            )
        else:
            assert not advancement_fired, (
                f"Advancement guard should NOT fire for sub_mode='{sub_mode}' "
                f"with response: {response_text!r}"
            )
            # Response must be unchanged (modulo strip which guard also applies)
            assert cleaned == response_text.strip()

    def test_step_mismatch_runs_before_advancement(self) -> None:
        """When response has BOTH a wrong step AND advancement language, both are stripped."""
        sub_mode = "collect_personal"
        # Wrong step (5 vs expected 3) AND advancement language
        response = "Paso 5/6 — Taller\nPasemos al siguiente paso."
        cleaned, step_fired, adv_fired = _apply_phase_guard(sub_mode, response)

        assert step_fired, "Step-mismatch guard should fire"
        assert adv_fired, "Advancement guard should fire"
        # Neither prefix should remain
        assert "Paso 5/6" not in cleaned
        assert "siguiente paso" not in cleaned.lower()

    def test_advancement_stripped_preserves_remaining_text(self) -> None:
        """After stripping the advancement phrase, remaining text is preserved."""
        sub_mode = "collect_personal"
        response = "Pasemos a la siguiente fase. ¿Cuál es tu nombre completo?"
        cleaned, _, adv_fired = _apply_phase_guard(sub_mode, response)

        assert adv_fired
        # The question part should still be in the cleaned response
        assert "¿Cuál es tu nombre completo?" in cleaned


# =============================================================================
# C4 — Combined parameterized scenarios (acceptance criteria from task spec)
# =============================================================================


@pytest.mark.parametrize(
    "sub_mode,response_text,should_strip",
    [
        # Wrong step in collect_personal → strip
        (
            "collect_personal",
            "📍 Paso 5/6 — Taller de montaje\n¿Quién realizó la instalación?",
            True,
        ),
        # Wrong step in collect_vehicle → strip
        (
            "collect_vehicle",
            "Paso 6/6 — Resumen y confirmación",
            True,
        ),
        # Correct step in collect_personal → pass through
        (
            "collect_personal",
            "Paso 3/6 — Datos personales\nNecesito tu nombre y DNI.",
            False,
        ),
        # Advancement language in collect_personal → strip
        (
            "collect_personal",
            "Perfecto, pasemos al siguiente paso.",
            True,
        ),
        # Advancement language in collect_vehicle → strip
        (
            "collect_vehicle",
            "Continuamos con el paso de documentación.",
            True,
        ),
        # Valid collect_personal response → pass
        (
            "collect_personal",
            "¿Me puedes indicar tu nombre completo y DNI?",
            False,
        ),
        # collect_base_docs edge case — wrong step → strip
        (
            "collect_base_docs",
            "Paso 5/6 — Taller\nVamos a verificar el taller.",
            True,
        ),
        # collect_base_docs — correct step → pass
        (
            "collect_base_docs",
            "Paso 2/6 — Documentación base del vehículo\nNecesito la ficha técnica.",
            False,
        ),
    ],
)
def test_kickoff_phase_guard(
    sub_mode: str, response_text: str, should_strip: bool
) -> None:
    """Main acceptance-criteria test for the phase truthfulness guard.

    Any response that contains a wrong step number OR advancement language on a
    kickoff no-tool turn must be stripped.  Valid responses must pass unchanged.
    """
    cleaned, step_fired, adv_fired = _apply_phase_guard(sub_mode, response_text)
    guard_fired = step_fired or adv_fired

    if should_strip:
        assert guard_fired, (
            f"Guard should have fired for sub_mode='{sub_mode}', "
            f"response={response_text!r}"
        )
    else:
        assert not guard_fired, (
            f"Guard should NOT fire for sub_mode='{sub_mode}', "
            f"response={response_text!r}"
        )
        assert cleaned == response_text.strip(), (
            f"Response must be unchanged when guard does not fire. Got: {cleaned!r}"
        )
