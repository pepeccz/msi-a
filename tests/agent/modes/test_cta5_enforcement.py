"""
Unit tests for CTA 5 post-images enforcement — escenario 7.bis / regla 9.

Spec reference: docs/system/01-agente/flujo-pre-expediente.md
  - Escenario 7.bis: Enforcement determinístico de CTA 5 post-imágenes
  - Regla 9: CTA 5 es determinística post-imágenes (anexar, no sustituir)

Contract (pure function _enforce_cta5_if_needed):
  - Preconditions met (precio_comunicado=True AND imagenes_enviadas_codigos non-empty):
    - Case 1: LLM produced useful text WITHOUT CTA 5 → append CTA 5 at the end
    - Case 2: LLM produced text WITH CTA 5 already → no duplication
    - Case 3: ai_response is empty or whitespace only → emit CTA 5 as sole content
  - Preconditions NOT met (no price or no images) → passthrough unchanged

CTA 5 gate contract (_process_with_tool_loop):
  - CTA-1-A: when result_dict["current_mode"] is truthy after the PRE_EXPEDIENTE
    turn, _enforce_cta5_if_needed MUST NOT be invoked.
  - CTA-1-B: when result_dict["current_mode"] is absent/falsy, _enforce_cta5_if_needed
    MUST still be called (regression guard — normal PRE_EXPEDIENTE turns unaffected).

All tests are pure unit tests — no DB, no Redis, no LLM.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.modes.pre_expediente_mode import _enforce_cta5_if_needed, _CTA_5 as _CANONICAL_CTA_5

# The canonical CTA 5 text (must match exactly what's defined in pre_expediente_mode.py)
CTA_5 = "¿Empezamos con el expediente?"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _preconditions_met(precio_comunicado: bool = True, codigos: list | None = None) -> tuple:
    """Return (precio_comunicado, imagenes_enviadas_codigos) for the test cases."""
    if codigos is None:
        codigos = ["ESCAPE"]
    return precio_comunicado, codigos


# ---------------------------------------------------------------------------
# Case 1: Preconditions met + text without CTA 5 → append CTA 5
# ---------------------------------------------------------------------------


class TestAppendsWhenMissingCta5:
    """Preconditions met, LLM text has no CTA 5 → CTA 5 appended at end."""

    def test_appends_cta5_to_llm_text(self):
        """Basic case: LLM produced useful text without CTA 5."""
        llm_text = "El presupuesto para el escape es de 410€ +IVA."
        precio, codigos = _preconditions_met()
        result = _enforce_cta5_if_needed(llm_text, precio, codigos)

        assert result.rstrip().endswith(CTA_5)
        # LLM text must be preserved
        assert llm_text.strip() in result

    def test_preserves_llm_text_content(self):
        """The LLM text (price, warnings, context) is preserved before the appended CTA 5."""
        llm_text = "El presupuesto es de 520€ +IVA. Recuerda que necesitarás los documentos del taller."
        precio, codigos = _preconditions_met()
        result = _enforce_cta5_if_needed(llm_text, precio, codigos)

        # Both original content and CTA 5 must be present
        assert "520€ +IVA" in result
        assert "documentos del taller" in result
        assert result.rstrip().endswith(CTA_5)

    def test_appends_with_separator(self):
        """
        Appended CTA 5 is separated from LLM text.
        Result should NOT be: "...text.¿Empezamos con el expediente?" (no space).
        """
        llm_text = "Aquí tienes los ejemplos de fotos."
        precio, codigos = _preconditions_met()
        result = _enforce_cta5_if_needed(llm_text, precio, codigos)

        # CTA 5 must appear at the end, separated from the rest
        assert result.rstrip().endswith(CTA_5)
        # The original text must come BEFORE the CTA 5
        cta5_idx = result.rindex(CTA_5)
        assert llm_text.strip() in result[:cta5_idx]

    def test_multiple_image_codes_still_enforces(self):
        """Having multiple imagenes_enviadas_codigos still triggers enforcement."""
        llm_text = "Ya te envié las fotos de ejemplo."
        precio, codigos = _preconditions_met(codigos=["ESCAPE", "SUSPENSION"])
        result = _enforce_cta5_if_needed(llm_text, precio, codigos)

        assert result.rstrip().endswith(CTA_5)

    def test_cta5_appears_only_once_when_appended(self):
        """CTA 5 appears exactly once in result when appended (no duplication)."""
        llm_text = "Te he enviado los ejemplos."
        precio, codigos = _preconditions_met()
        result = _enforce_cta5_if_needed(llm_text, precio, codigos)

        assert result.count(CTA_5) == 1


# ---------------------------------------------------------------------------
# Case 2: Preconditions met + LLM text already contains CTA 5 → no duplication
# ---------------------------------------------------------------------------


class TestNoDuplicationWhenCta5Present:
    """Preconditions met, LLM already included CTA 5 → passthrough (no duplicate)."""

    def test_no_duplication_exact_cta5_at_end(self):
        """LLM text ends exactly with CTA 5 → no duplicate."""
        llm_text = f"Aquí tienes las fotos de ejemplo. {CTA_5}"
        precio, codigos = _preconditions_met()
        result = _enforce_cta5_if_needed(llm_text, precio, codigos)

        assert result.count(CTA_5) == 1
        assert result.rstrip().endswith(CTA_5)

    def test_no_duplication_cta5_with_trailing_whitespace(self):
        """LLM text ends with CTA 5 + trailing whitespace → no duplicate."""
        llm_text = f"Ya puedes ver las fotos. {CTA_5}  "
        precio, codigos = _preconditions_met()
        result = _enforce_cta5_if_needed(llm_text, precio, codigos)

        assert result.count(CTA_5) == 1

    def test_no_duplication_cta5_with_trailing_newline(self):
        """LLM text ends with CTA 5 + newline → no duplicate."""
        llm_text = f"Perfecto, ya ves cómo son las fotos.\n{CTA_5}\n"
        precio, codigos = _preconditions_met()
        result = _enforce_cta5_if_needed(llm_text, precio, codigos)

        assert result.count(CTA_5) == 1

    def test_preserves_text_when_cta5_already_present(self):
        """When CTA 5 is already present, the full original text is preserved."""
        llm_text = f"El presupuesto fue de 410€. {CTA_5}"
        precio, codigos = _preconditions_met()
        result = _enforce_cta5_if_needed(llm_text, precio, codigos)

        assert "410€" in result
        assert result.count(CTA_5) == 1


# ---------------------------------------------------------------------------
# Case 3: Preconditions met + empty/whitespace ai_response → CTA 5 as sole content
# ---------------------------------------------------------------------------


class TestEmptyResponseBecomescta5:
    """Preconditions met, ai_response is empty or whitespace → CTA 5 as sole output."""

    def test_empty_string_becomes_cta5(self):
        """Empty string ai_response → CTA 5 as sole content."""
        precio, codigos = _preconditions_met()
        result = _enforce_cta5_if_needed("", precio, codigos)

        assert result == CTA_5

    def test_whitespace_only_becomes_cta5(self):
        """Whitespace-only ai_response → CTA 5 as sole content."""
        precio, codigos = _preconditions_met()
        result = _enforce_cta5_if_needed("   \n\t  ", precio, codigos)

        assert result == CTA_5

    def test_newline_only_becomes_cta5(self):
        """Newline-only ai_response → CTA 5 as sole content."""
        precio, codigos = _preconditions_met()
        result = _enforce_cta5_if_needed("\n\n\n", precio, codigos)

        assert result == CTA_5


# ---------------------------------------------------------------------------
# Case 4: Preconditions NOT met → passthrough unchanged
# ---------------------------------------------------------------------------


class TestPassthroughWhenPreconditionsNotMet:
    """When preconditions are not met, ai_response is returned unchanged."""

    def test_no_price_communicated_passthrough(self):
        """precio_comunicado=False → no CTA 5 enforcement."""
        llm_text = "Aquí tienes algo."
        result = _enforce_cta5_if_needed(llm_text, precio_comunicado=False, imagenes_enviadas_codigos=["ESCAPE"])

        assert result == llm_text

    def test_empty_imagenes_no_longer_blocks_enforcement(self):
        """
        B1 contract change: imagenes_enviadas_codigos=[] does NOT block enforcement.
        When precio_comunicado=True, CTA5 is appended regardless of image history.
        (Previously this was a passthrough — the imagenes guard has been removed.)
        """
        llm_text = "Aquí tienes algo."
        result = _enforce_cta5_if_needed(llm_text, precio_comunicado=True, imagenes_enviadas_codigos=[])

        assert result.rstrip().endswith(_CANONICAL_CTA_5), (
            "B1 fix: imagenes=[] must NOT block CTA5 enforcement when precio_comunicado=True."
        )

    def test_none_imagenes_no_longer_blocks_enforcement(self):
        """
        B1 contract change: imagenes_enviadas_codigos=None does NOT block enforcement.
        When precio_comunicado=True, CTA5 is appended regardless of image history.
        (Previously this was a passthrough — the imagenes guard has been removed.)
        """
        llm_text = "Aquí tienes algo."
        result = _enforce_cta5_if_needed(llm_text, precio_comunicado=True, imagenes_enviadas_codigos=None)

        assert result.rstrip().endswith(_CANONICAL_CTA_5), (
            "B1 fix: imagenes=None must NOT block CTA5 enforcement when precio_comunicado=True."
        )

    def test_no_price_no_images_passthrough(self):
        """Both preconditions False → passthrough."""
        llm_text = "Aquí tienes algo."
        result = _enforce_cta5_if_needed(llm_text, precio_comunicado=False, imagenes_enviadas_codigos=None)

        assert result == llm_text

    def test_passthrough_preserves_text_exactly(self):
        """Passthrough returns the exact same string object or identical content."""
        llm_text = "Texto cualquiera sin modificar."
        result = _enforce_cta5_if_needed(llm_text, precio_comunicado=False, imagenes_enviadas_codigos=["ESCAPE"])

        assert result == llm_text

    def test_passthrough_does_not_add_cta5(self):
        """No preconditions → CTA 5 never injected."""
        llm_text = "Texto sin CTA 5."
        result = _enforce_cta5_if_needed(llm_text, precio_comunicado=False, imagenes_enviadas_codigos=["ESCAPE"])

        assert CTA_5 not in result


# ---------------------------------------------------------------------------
# B1: CTA5 enforced regardless of imagenes_enviadas_codigos
# (Scenarios B1-1, B1-2, B1-3, B1-4 from fix-doc-fidelity-and-cta-enforcement spec)
# RED: B1-1 and B1-2 currently FAIL — imagenes guard blocks enforcement.
# They will PASS after the B1 precondition fix.
# ---------------------------------------------------------------------------


class TestB1CtaEnforcedRegardlessOfImages:
    """B1: CTA5 must fire on precio_comunicado=True regardless of image history."""

    def test_b1_1_cta5_appended_when_no_images_sent(self):
        """
        Scenario B1-1: precio_comunicado=True AND imagenes_enviadas_codigos=[]
        → CTA5 MUST be appended (image history must NOT block enforcement).

        Currently FAILS: the imagenes guard returns passthrough for empty list.
        Will PASS after removing the 'not imagenes_enviadas_codigos' clause.
        """
        llm_text = "El presupuesto es de 410€ +IVA."
        result = _enforce_cta5_if_needed(
            llm_text, precio_comunicado=True, imagenes_enviadas_codigos=[]
        )
        assert result.rstrip().endswith(_CANONICAL_CTA_5), (
            "B1-1: CTA5 must be appended when precio_comunicado=True, "
            "even if no images have been sent yet."
        )

    def test_b1_2_cta5_appended_when_images_sent(self):
        """
        Scenario B1-2: precio_comunicado=True AND imagenes_enviadas_codigos=["img1"]
        → CTA5 MUST be appended.
        """
        llm_text = "Ya te he enviado las fotos de ejemplo."
        result = _enforce_cta5_if_needed(
            llm_text, precio_comunicado=True, imagenes_enviadas_codigos=["img1"]
        )
        assert result.rstrip().endswith(_CANONICAL_CTA_5), (
            "B1-2: CTA5 must be appended when precio_comunicado=True and images were sent."
        )

    def test_b1_3_no_emission_when_cta_already_present(self):
        """
        Scenario B1-3: CTA already present in response → no duplicate.
        """
        llm_text = f"El presupuesto es de 410€ +IVA. {_CANONICAL_CTA_5}"
        result = _enforce_cta5_if_needed(
            llm_text, precio_comunicado=True, imagenes_enviadas_codigos=[]
        )
        assert result.count(_CANONICAL_CTA_5) == 1

    def test_b1_4_no_emission_when_precio_false(self):
        """
        Scenario B1-4: precio_comunicado=False → no CTA5 regardless of images.
        """
        llm_text = "Aquí tienes información."
        result = _enforce_cta5_if_needed(
            llm_text, precio_comunicado=False, imagenes_enviadas_codigos=["img1"]
        )
        assert result == llm_text


# ---------------------------------------------------------------------------
# CTA 5 gate — B2-T1 and B2-T2
# ---------------------------------------------------------------------------
# These tests verify the gate in _process_with_tool_loop that decides whether
# to call _enforce_cta5_if_needed based on result_dict["current_mode"].
#
# Strategy: patch the loop infrastructure so _process_with_tool_loop reaches
# the gate without real DB/Redis/LLM, then spy on _enforce_cta5_if_needed.
#
# Patches applied:
#   - _load_active_draft_quote_into_context → AsyncMock (no-op)
#   - build_mode_tool_loop → returns mock with .graph.ainvoke returning loop_result
#   - clear_image_tools_state → MagicMock (no-op)
#   - _build_client_context on the node instance → MagicMock
#   - assemble_system_prompt → MagicMock (avoids prompt file I/O)
#   - agent.modes.pre_expediente_mode._enforce_cta5_if_needed → spy
#
# The draft-quote deactivation runs inside a try/finally that imports
# _deactivate_draft_quote locally. We patch that import path.
# ---------------------------------------------------------------------------

_MODULE = "agent.modes.pre_expediente_mode"


def _make_loop_result(*, current_mode: str | None = None) -> dict:
    """Build a minimal loop_result dict as returned by build_mode_tool_loop graph."""
    result: dict = {
        "ai_response": "Texto de respuesta del LLM.",
        "exit_reason": "response",
        "tools_called": [],
        "pending_state_updates": {
            "precio_comunicado": True,
            "imagenes_enviadas_codigos": ["ESCAPE"],
        },
    }
    if current_mode is not None:
        result["pending_state_updates"]["_transition_to"] = current_mode
    return result


def _make_graph_mock(loop_result: dict) -> MagicMock:
    """Build a mock build_mode_tool_loop return value whose graph.ainvoke returns loop_result."""
    graph_mock = MagicMock()
    graph_mock.graph.ainvoke = AsyncMock(return_value=loop_result)
    graph_mock.recursion_limit = 25
    return graph_mock


def _minimal_state() -> dict:
    """Minimal ConversationState-compatible dict for _process_with_tool_loop."""
    return {
        "conversation_id": "test-cta5-gate",
        "mode_context": {
            "precio_comunicado": True,
            "imagenes_enviadas_codigos": ["ESCAPE"],
        },
        "messages": [],
        "client_type": "particular",
        "is_first_interaction": False,
    }


class TestCta5GateOnTransition:
    """CTA-1-A/B: gate skips or invokes _enforce_cta5_if_needed based on current_mode."""

    @pytest.mark.asyncio
    async def test_cta5_skipped_when_current_mode_set(self):
        """
        CTA-1-A: when _transition_to is emitted (current_mode set in result_dict),
        _enforce_cta5_if_needed must NOT be called.

        This is the RED test for B2-I1: today the call is unconditional (line 642),
        so this test FAILS before the guard is added.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        loop_result = _make_loop_result(current_mode="EXPEDIENTE_MODE")
        graph_mock = _make_graph_mock(loop_result)
        node = PreExpedienteModeNode()
        node._build_client_context = MagicMock(return_value={})

        with (
            patch(f"{_MODULE}._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch(f"{_MODULE}.build_mode_tool_loop", return_value=graph_mock),
            patch(f"{_MODULE}.clear_image_tools_state"),
            patch(f"{_MODULE}.assemble_system_prompt", return_value="prompt"),
            patch("agent.tools.draft_quote_service._deactivate_draft_quote", new_callable=AsyncMock),
            patch(f"{_MODULE}._enforce_cta5_if_needed") as mock_enforce,
        ):
            mock_enforce.return_value = "Texto de respuesta del LLM."
            await node._process_with_tool_loop("¿Cuánto cuesta el escape?", _minimal_state())

        mock_enforce.assert_not_called(), (
            "CTA-1-A: _enforce_cta5_if_needed must NOT be called when current_mode is set "
            "(outgoing transition turn — CTA would contradict the handoff)"
        )

    @pytest.mark.asyncio
    async def test_cta5_enforced_when_no_transition(self):
        """
        CTA-1-B: when no transition occurs (current_mode NOT set in result_dict),
        _enforce_cta5_if_needed MUST still be called.

        Regression guard — normal PRE_EXPEDIENTE POST_PRICE turns must keep enforcing CTA 5.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        loop_result = _make_loop_result(current_mode=None)  # no transition
        graph_mock = _make_graph_mock(loop_result)
        node = PreExpedienteModeNode()
        node._build_client_context = MagicMock(return_value={})

        with (
            patch(f"{_MODULE}._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch(f"{_MODULE}.build_mode_tool_loop", return_value=graph_mock),
            patch(f"{_MODULE}.clear_image_tools_state"),
            patch(f"{_MODULE}.assemble_system_prompt", return_value="prompt"),
            patch("agent.tools.draft_quote_service._deactivate_draft_quote", new_callable=AsyncMock),
            patch(f"{_MODULE}._enforce_cta5_if_needed") as mock_enforce,
        ):
            mock_enforce.return_value = "Texto de respuesta del LLM."
            await node._process_with_tool_loop("¿Cuánto cuesta el escape?", _minimal_state())

        mock_enforce.assert_called_once(), (
            "CTA-1-B: _enforce_cta5_if_needed MUST be called when no mode transition occurred "
            "(normal PRE_EXPEDIENTE POST_PRICE turn — CTA 5 enforcement must be preserved)"
        )
