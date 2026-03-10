"""Tests for canonical expediente onboarding builders."""

from agent.modes.expediente_mode import EXPEDIENTE_INTRO_MESSAGE
from agent.services.expediente_onboarding import (
    build_expediente_opening_overview,
    build_new_expediente_case_instructions,
    build_resume_expediente_case_instructions,
)


def test_expediente_intro_message_reexports_canonical_overview() -> None:
    """The public expediente intro constant stays aligned with the service source."""
    assert EXPEDIENTE_INTRO_MESSAGE == build_expediente_opening_overview()


def test_new_expediente_instructions_share_canonical_opening_text() -> None:
    """New expediente entry paths use the shared onboarding builder."""
    instructions = build_new_expediente_case_instructions(
        first_element_display="Toldo lateral",
        total_elements=2,
        intro_already_sent=False,
        auto_created=False,
    )

    assert "He abierto tu expediente de homologación" in instructions
    assert "Toldo lateral" in instructions
    assert "TOTAL ELEMENTOS: 2" in instructions


def test_resume_expediente_instructions_restate_same_process_overview() -> None:
    """Resume/recovery entry paths reuse the same onboarding source."""
    instructions = build_resume_expediente_case_instructions(
        elementos_str="Toldo lateral, Placa solar",
        progress_desc="1/2 elementos completados",
        resume_phase_label="Documentación base del vehículo",
        created_at_str="10/03/2026 a las 12:30",
    )

    assert "RESUMEN DEL PROCESO" in instructions
    assert build_expediente_opening_overview() in instructions
    assert "1/2 elementos completados" in instructions
    assert "Documentación base del vehículo" in instructions
