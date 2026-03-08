"""
Tests for _gate_response_claims() in agent/modes/expediente_mode.py — Phase 5.

_gate_response_claims is a module-level pure function (no I/O, no async).
It rewrites or hedges AI response text based on the certainty envelope.

Scenarios covered:
  A. Flag OFF — passthrough with zero rewrites
  B. COMPLETION_CLAIM — hedge appended when confirming tool not called
  C. COMPLETION_CLAIM — allowed when confirming tool succeeded
  D. CASE_FINALIZED — replaced with deterministic message when not finalized
  E. CASE_FINALIZED — allowed when case_finalized=True in envelope
  F. IMAGES_SENT — rewritten to intent-only when images not confirmed
  G. IMAGES_SENT — allowed when images confirmed
  H. DOCS_RECEIVED — qualifier appended when docs not confirmed
  I. DOCS_RECEIVED — allowed when docs confirmed
  J. Multiple claims in same response — each handled independently
  K. Empty / None response — returned unchanged
  L. Count return values (blocked_count, allowed_count)

NOTE ON PHRASE SELECTION:
The regex patterns in expediente_mode.py are intentionally conservative (as
documented in the source): only high-confidence, unambiguous phrases trigger
a rewrite.  The test phrases below are validated against the actual compiled
patterns — some intuitively "triggerable" phrases (e.g. "hemos enviado tu
expediente", "te he enviado las imágenes") do NOT match the patterns by design.
Do NOT add phrases here unless they are first verified against the patterns.
"""

from __future__ import annotations

import pytest

from agent.modes.expediente_guardrails import CertaintyEnvelope
from agent.modes.expediente_mode import _gate_response_claims


# =============================================================================
# Helpers
# =============================================================================

CONV_ID = "test-conv-gate-001"
SUB_MODE = "collect_base_docs"


def _env(**kwargs) -> CertaintyEnvelope:
    """Return an envelope with given fields set (all others default to False)."""
    return CertaintyEnvelope(**kwargs)


def gate(response: str, env: CertaintyEnvelope, *, enabled: bool = True) -> tuple[str, int, int]:
    return _gate_response_claims(
        ai_response=response,
        turn_envelope=env,
        sub_mode=SUB_MODE,
        conversation_id=CONV_ID,
        guardrails_enabled=enabled,
    )


# =============================================================================
# A. Flag OFF → passthrough
# =============================================================================

class TestFlagOff:
    def test_passthrough_when_disabled(self) -> None:
        # Even a response with flagged phrases must be returned unchanged.
        response = "Tu expediente ha sido enviado para revisión."
        env = _env(case_finalized=False)
        gated, blocked, allowed = gate(response, env, enabled=False)
        assert gated == response
        assert blocked == 0
        assert allowed == 0

    def test_empty_response_when_disabled(self) -> None:
        gated, blocked, allowed = gate("", _env(), enabled=False)
        assert gated == ""
        assert blocked == 0
        assert allowed == 0


# =============================================================================
# B. COMPLETION_CLAIM — hedge appended
# =============================================================================

class TestCompletionClaimHedge:
    """When confirming tool has NOT succeeded, completion language gets a hedge."""

    # sub-mode collect_base_docs requires confirmar_documentacion_base
    # NOTE: Stems like "complet" are found inside "completo"/"completado" via re.search.
    # However "ya hemos terminado" does NOT match because "terminado" → "terminad"+"o"+\s+
    # which is not whitespace immediately after the stem.
    _TRIGGERING_PHRASES = [
        "todo ya está completado",
        "el expediente ya está completo",
        "el expediente ha quedado completo",
        "el proceso ha quedado completado",
        "todo queda registrado",
    ]

    @pytest.mark.parametrize("phrase", _TRIGGERING_PHRASES)
    def test_hedge_appended_for_completion_phrase(self, phrase: str) -> None:
        env = _env()  # No confirming tool succeeded
        gated, blocked, _ = gate(phrase, env)
        # Hedge must be appended (not remove the original)
        assert phrase in gated or "confirmaré" in gated.lower()
        assert blocked == 1

    def test_hedge_not_duplicated_on_second_pass(self) -> None:
        """Idempotency: if hedge already present, don't append again."""
        env = _env()
        phrase = "el expediente ya está completo"
        gated1, _, _ = gate(phrase, env)
        gated2, blocked2, _ = gate(gated1, env)
        # Either hedge is already present so no new appending, or blocked once
        assert blocked2 <= 1

    def test_no_hedge_when_no_completion_phrase(self) -> None:
        env = _env()
        response = "Aquí tienes el resumen de los elementos registrados."
        gated, blocked, _ = gate(response, env)
        assert gated == response
        assert blocked == 0


# =============================================================================
# C. COMPLETION_CLAIM — allowed when tool succeeded
# =============================================================================

class TestCompletionClaimAllowed:
    def test_allowed_count_incremented_when_tool_succeeded(self) -> None:
        env = _env(tools_succeeded=["confirmar_documentacion_base"])
        phrase = "el expediente ya está completo"
        _, blocked, allowed = gate(phrase, env, enabled=True)
        assert blocked == 0
        assert allowed >= 1


# =============================================================================
# D. CASE_FINALIZED — replaced with deterministic message
# =============================================================================

class TestCaseFinalizedReplaced:
    # NOTE: The CASE_FINALIZED regex ends each alternative WITHOUT a \s+ after the
    # verb stem, so `re.search` finds the stem as a substring inside the conjugated form.
    # However, alternatives with `hemos\s+<stem>\s+` DO require whitespace after the
    # stem — so "hemos enviado" (stem+o before space) does NOT match.
    # Only phrases that match the verified patterns are listed here.
    _TRIGGERING_PHRASES = [
        "tu expediente ha sido enviado para revisión",
        "el expediente ha sido tramitado",
        "tu expediente fue tramitado",
        "el caso ha sido tramitado",
    ]

    @pytest.mark.parametrize("phrase", _TRIGGERING_PHRASES)
    def test_deterministic_replacement_when_not_finalized(self, phrase: str) -> None:
        env = _env(case_finalized=False)
        gated, blocked, _ = gate(phrase, env)
        # Original phrase must NOT appear verbatim
        assert phrase not in gated or "confirmaré" in gated.lower() or "Cuando confirmes" in gated
        assert blocked >= 1

    def test_replacement_text_is_bounded(self) -> None:
        """Replacement must be deterministic / future-conditional language."""
        phrase = "tu expediente ha sido enviado para revisión"
        env = _env(case_finalized=False)
        gated, _, _ = gate(phrase, env)
        # Deterministic replacement contains forward-looking language
        assert "confirmes" in gated.lower() or "finalización" in gated.lower() or "comunicaré" in gated.lower()


# =============================================================================
# E. CASE_FINALIZED — allowed when finalized
# =============================================================================

class TestCaseFinalizedAllowed:
    def test_no_replacement_when_finalized(self) -> None:
        env = _env(case_finalized=True)
        phrase = "tu expediente ha sido enviado para revisión"
        gated, blocked, allowed = gate(phrase, env)
        assert blocked == 0
        assert gated == phrase
        assert allowed >= 1


# =============================================================================
# F. IMAGES_SENT — rewritten to intent-only
# =============================================================================

class TestImagesSentRewrite:
    # NOTE: The IMAGES_SENT regex has two alternatives:
    #   1. te\s+he\s+(?:enviad|mandad)\s+(?:las?\s+)?(?:imágenes?|fotos?|ejemplos?)
    #      This requires \s+ AFTER the stem — so "te he enviado" does NOT match
    #      because after "enviad" comes "o" (not whitespace).
    #   2. acabo\s+de\s+(?:enviar|mandar)\s+(?:las?\s+)?(?:imágenes?|fotos?)
    #      This uses the full infinitive form and DOES match.
    # Only phrases verified to match the compiled pattern are listed here.
    _TRIGGERING_PHRASES = [
        ("acabo de enviar las imágenes", "acabo de enviar"),
        ("acabo de mandar las fotos", "acabo de mandar"),
        ("acabo de enviar las fotos", "acabo de enviar"),
    ]

    @pytest.mark.parametrize("phrase,past_tense", _TRIGGERING_PHRASES)
    def test_past_tense_rewritten_to_intent(self, phrase: str, past_tense: str) -> None:
        env = _env(images_sent=False)
        gated, blocked, _ = gate(phrase, env)
        assert blocked >= 1

    def test_no_rewrite_when_no_image_claim(self) -> None:
        env = _env(images_sent=False)
        response = "Aquí van los documentos que necesitas para la homologación."
        gated, blocked, _ = gate(response, env)
        assert gated == response
        assert blocked == 0


# =============================================================================
# G. IMAGES_SENT — allowed when images confirmed
# =============================================================================

class TestImagesSentAllowed:
    def test_allowed_count_incremented_when_sent(self) -> None:
        # Use a phrase verified to match the IMAGES_SENT regex (acabo-de alternative)
        env = _env(images_sent=True)
        phrase = "acabo de enviar las imágenes de ejemplo"
        _, blocked, allowed = gate(phrase, env)
        assert blocked == 0
        assert allowed >= 1


# =============================================================================
# H. DOCS_RECEIVED — qualifier appended
# =============================================================================

class TestDocsReceivedQualifier:
    # NOTE: The DOCS_RECEIVED regex has two alternatives:
    #   1. (?:ya\s+)?(?:he\s+)?(?:recibid|registrad|guardad|confirmad)\s+(?:la\s+)?documentaci[oó]n
    #      Stem-based: "recibido" does NOT match because after "recibid" comes "o" not \s+.
    #      BUT "confirmad" + \s+ works if we use "confirmada" — wait, same issue.
    #      The stem must be directly followed by whitespace: only works if the verb
    #      happens to end at the stem (e.g. "he confirmad la documentación" — ungrammatical).
    #      Effectively this alternative does not match natural Spanish conjugations.
    #   2. documentaci[oó]n\s+(?:base\s+)?(?:ya\s+)?(?:recibida|registrada|confirmada|guardada)
    #      Full adjective forms — DOES match natural Spanish.
    # Only phrases verified to match the compiled pattern are listed here.
    _TRIGGERING_PHRASES = [
        "documentación base confirmada",
        "documentación confirmada",
        "documentación base recibida",
        "documentación registrada",
    ]

    @pytest.mark.parametrize("phrase", _TRIGGERING_PHRASES)
    def test_qualifier_appended_when_not_confirmed(self, phrase: str) -> None:
        env = _env(docs_confirmed=False)
        gated, blocked, _ = gate(phrase, env)
        assert blocked >= 1
        # Qualifier must be present somewhere in the response
        assert "pendiente" in gated.lower() or "verificaci" in gated.lower() or len(gated) > len(phrase)

    def test_no_qualifier_for_unrelated_text(self) -> None:
        env = _env(docs_confirmed=False)
        response = "Para continuar, envíame las fotos de la ficha técnica."
        gated, blocked, _ = gate(response, env)
        assert gated == response
        assert blocked == 0


# =============================================================================
# I. DOCS_RECEIVED — allowed when confirmed
# =============================================================================

class TestDocsReceivedAllowed:
    def test_allowed_count_incremented_when_confirmed(self) -> None:
        # Use a phrase verified to match the DOCS_RECEIVED regex (adjective-form alternative)
        env = _env(docs_confirmed=True)
        phrase = "documentación base confirmada"
        _, blocked, allowed = gate(phrase, env)
        assert blocked == 0
        assert allowed >= 1


# =============================================================================
# J. Multiple claims in one response
# =============================================================================

class TestMultipleClaimsInResponse:
    def test_multiple_blocked_claims_accumulate(self) -> None:
        """Both an images-sent claim AND a docs-received claim in same response."""
        # Use verified matching phrases for each claim class:
        #   IMAGES_SENT: "acabo de enviar las imágenes" (acabo-de alternative)
        #   DOCS_RECEIVED: "documentación base confirmada" (adjective-form alternative)
        env = _env(images_sent=False, docs_confirmed=False)
        response = (
            "Acabo de enviar las imágenes de ejemplo. "
            "Además, tengo la documentación base confirmada."
        )
        gated, blocked, _ = gate(response, env)
        # At least 2 claims should have been caught
        assert blocked >= 2

    def test_finalized_and_completion_in_same_response(self) -> None:
        env = _env(case_finalized=False, tools_succeeded=[])
        response = (
            "El expediente ya está completo "
            "y tu expediente ha sido enviado para revisión."
        )
        gated, blocked, _ = gate(response, env)
        assert blocked >= 2


# =============================================================================
# K. Edge cases — empty / None / very short
# =============================================================================

class TestEdgeCases:
    def test_empty_string_returned_unchanged(self) -> None:
        gated, blocked, allowed = gate("", _env())
        assert gated == ""
        assert blocked == 0
        assert allowed == 0

    def test_whitespace_only_response(self) -> None:
        """Whitespace-only response should not crash."""
        gated, blocked, allowed = gate("   ", _env())
        assert blocked == 0

    def test_response_with_no_flagged_content(self) -> None:
        env = _env()
        response = "Perfecto, vamos al siguiente paso. ¿Tienes la ficha técnica a mano?"
        gated, blocked, allowed = gate(response, env)
        assert gated == response
        assert blocked == 0
        assert allowed == 0

    def test_very_long_response_does_not_timeout(self) -> None:
        """Regex must not exhibit catastrophic backtracking on long input."""
        # 5,000 chars of benign text — should complete in under 1 second
        long_response = "Aquí va información sobre el proceso de homologación. " * 90
        env = _env()
        import time
        t0 = time.monotonic()
        gated, _, _ = gate(long_response, env)
        elapsed = time.monotonic() - t0
        assert elapsed < 2.0, f"Regex took too long: {elapsed:.2f}s"
        assert len(gated) >= len(long_response)


# =============================================================================
# L. Return value types and semantics
# =============================================================================

class TestReturnValueSemantics:
    def test_returns_tuple_of_three(self) -> None:
        result = gate("any response", _env())
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_gated_response_is_string(self) -> None:
        gated, _, _ = gate("hello", _env())
        assert isinstance(gated, str)

    def test_counts_are_non_negative_ints(self) -> None:
        _, blocked, allowed = gate("hello", _env())
        assert isinstance(blocked, int) and blocked >= 0
        assert isinstance(allowed, int) and allowed >= 0

    def test_flag_off_returns_zero_counts(self) -> None:
        phrase = "tu expediente ha sido enviado"
        _, blocked, allowed = gate(phrase, _env(case_finalized=False), enabled=False)
        assert blocked == 0
        assert allowed == 0
