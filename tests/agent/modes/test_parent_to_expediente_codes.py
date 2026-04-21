"""
Unit tests for imagenes_enviadas_codigos cross-mode propagation.

fix-pre-to-expediente-state-propagation — Bug 1:
Verifies that parent_to_expediente() carries imagenes_enviadas_codigos from
shared_context into ExpedienteState so the EXPEDIENTE dedup gate can fire.

Pure unit tests (no DB, no Redis, no LLM).
"""

from agent.modes.expediente_state import parent_to_expediente


class TestImagenesEnviadasCodigosPropagation:
    """parent_to_expediente must bridge imagenes_enviadas_codigos from shared_context."""

    def test_codes_propagate_from_shared_context(self):
        """
        A1 — Happy path: shared_context has codes → ExpedienteState carries them.

        GIVEN shared_context["imagenes_enviadas_codigos"] == ["A1", "B2"]
        WHEN parent_to_expediente is called
        THEN result["imagenes_enviadas_codigos"] == ["A1", "B2"]
        """
        parent_state = {
            "shared_context": {"imagenes_enviadas_codigos": ["A1", "B2"]},
            "mode_context": {},
        }

        result = parent_to_expediente(parent_state)

        assert result["imagenes_enviadas_codigos"] == ["A1", "B2"]

    def test_empty_list_propagates_cleanly(self):
        """
        A2 — Empty list: shared_context has [] → ExpedienteState gets [].

        GIVEN shared_context["imagenes_enviadas_codigos"] == []
        WHEN parent_to_expediente is called
        THEN result["imagenes_enviadas_codigos"] == []
        AND no dedup false-positives are triggered (list is genuinely empty)
        """
        parent_state = {
            "shared_context": {"imagenes_enviadas_codigos": []},
            "mode_context": {},
        }

        result = parent_to_expediente(parent_state)

        assert result["imagenes_enviadas_codigos"] == []

    def test_key_absent_in_shared_context_defaults_to_empty(self):
        """
        A3 — Missing key: neither shared_context nor mode_context has it
        → no KeyError, field absent (consistent with other optional fields).

        GIVEN shared_context does not contain imagenes_enviadas_codigos
        WHEN parent_to_expediente is called
        THEN no KeyError is raised
        AND the field is not present (callers should use .get("imagenes_enviadas_codigos", []))
        """
        parent_state = {
            "shared_context": {},
            "mode_context": {},
        }

        result = parent_to_expediente(parent_state)

        # Must not raise — field simply absent (old-checkpoint compat)
        assert result.get("imagenes_enviadas_codigos") is None or "imagenes_enviadas_codigos" not in result

    def test_shared_context_wins_over_mode_context(self):
        """
        A4 — shared_context takes precedence over stale mode_context value.
        """
        parent_state = {
            "shared_context": {"imagenes_enviadas_codigos": ["A1"]},
            "mode_context": {"imagenes_enviadas_codigos": ["STALE"]},
        }

        result = parent_to_expediente(parent_state)

        assert result["imagenes_enviadas_codigos"] == ["A1"]

    def test_mode_context_fallback_when_shared_context_absent(self):
        """
        A5 — Backward compat: if shared_context missing, mode_context value used.
        """
        parent_state = {
            "shared_context": {},
            "mode_context": {"imagenes_enviadas_codigos": ["X9"]},
        }

        result = parent_to_expediente(parent_state)

        assert result["imagenes_enviadas_codigos"] == ["X9"]


class TestDeduplicationGateReceivesCodesAfterTransition:
    """
    A6 — Triangulation: after PRE→EXPEDIENTE transition, the codes reach the
    ExpedienteState field that _build_mode_context_from_expediente_state() will
    expose to image_service.py's dedup gate.

    We verify the full bridge: shared_context → parent_to_expediente → ExpedienteState.
    A post-transition EXPEDIENTE turn must see the codes so it can skip re-dispatch.
    """

    def test_dedup_gate_codes_present_after_transition(self):
        """
        GIVEN PRE-phase sent codes ["ASIDERO", "SUBCHASIS"] in shared_context
        WHEN parent_to_expediente builds ExpedienteState for the first EXPEDIENTE turn
        THEN the state contains those codes — image_service dedup gate will skip them.
        """
        parent_state = {
            "shared_context": {"imagenes_enviadas_codigos": ["ASIDERO", "SUBCHASIS"]},
            "mode_context": {"expediente_sub_mode": "collect_element_data"},
        }

        result = parent_to_expediente(parent_state)

        codes = result.get("imagenes_enviadas_codigos", [])
        assert "ASIDERO" in codes
        assert "SUBCHASIS" in codes
        assert len(codes) == 2

    def test_three_codes_all_propagate(self):
        """
        Triangulation with 3 codes — ensures the list is not truncated or deduplicated
        by parent_to_expediente (that would silently break the dedup gate).
        """
        sent = ["AA", "BB", "CC"]
        parent_state = {
            "shared_context": {"imagenes_enviadas_codigos": sent},
            "mode_context": {},
        }

        result = parent_to_expediente(parent_state)

        assert result["imagenes_enviadas_codigos"] == sent
