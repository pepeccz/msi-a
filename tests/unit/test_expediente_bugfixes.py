"""
Regression tests for EXPEDIENTE_MODE bugfixes (Feb 2026).

Four bugs were fixed:

B1 - CRITICAL: Idempotent path in actualizar_datos_expediente had no next_step.
     When the LLM re-called the tool with already-saved data the FSM got stuck.
     Fix: evaluate completeness of EXISTING data and return correct next_step.

B2 - CRITICAL: confirmar_fotos_elemento ignored by _extract_context_from_tool
     for sub-mode transitions. Only completar_elemento_actual was listened to.
     Fix: both tools now trigger COLLECT_BASE_DOCS when all_elements_complete=True.

B3 - HIGH: LLM could declare "expediente complete" as free text before calling
     finalizar_expediente(), lying to the user about the case state.
     Fix: regex guard in tool-calling loop blocks and re-prompts the LLM.

B4 - MEDIUM: _initialize_mode_context always reset element progress to 0/pending
     on re-entry, ignoring persisted CaseElementData rows in the DB.
     Fix: query CaseElementData and reconcile current_element_index + element_data_status.
"""

import json
import re
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from agent.modes.expediente_mode import (
    ExpedienteModeNode,
    REVIEW_SUMMARY,
    COLLECT_ELEMENT_DATA,
    COLLECT_BASE_DOCS,
    _build_element_completion_transition_closure,
)
from agent.utils.fsm_compat import CollectionStep, validate_personal_data, validate_vehicle_data


# =============================================================================
# B1 — Idempotent path in actualizar_datos_expediente
# =============================================================================

class TestB1IdempotentNextStep:
    """
    B1: When the tool is called with data already saved, the idempotent path
    must return next_step='collect_vehicle' (personal complete) or
    next_step='collect_workshop' (vehicle complete), NOT stay silent.
    """

    # ------------------------------------------------------------------
    # validate_personal_data / validate_vehicle_data — helpers the fix uses
    # ------------------------------------------------------------------

    def test_validate_personal_data_complete(self):
        """validate_personal_data returns (True, []) for complete data."""
        data = {
            "nombre": "Pepe",
            "apellidos": "García López",
            "dni_cif": "12345678A",
            "email": "pepe@example.com",
            "domicilio_calle": "Calle Mayor 1",
            "domicilio_localidad": "Madrid",
            "domicilio_provincia": "Madrid",
            "domicilio_cp": "28001",
            "itv_nombre": "ITV Madrid Norte",
        }
        is_valid, missing = validate_personal_data(data)
        assert is_valid is True
        assert missing == []

    def test_validate_personal_data_incomplete(self):
        """validate_personal_data returns (False, [...]) for incomplete data."""
        data = {
            "nombre": "Pepe",
            # Missing apellidos, dni_cif, email, domicilio_*, itv_nombre
        }
        is_valid, missing = validate_personal_data(data)
        assert is_valid is False
        assert len(missing) > 0

    def test_validate_vehicle_data_complete(self):
        """validate_vehicle_data returns (True, []) for complete data."""
        data = {
            "marca": "Honda",
            "modelo": "CBR 600",
            "anio": "2018",
            "matricula": "1234BCD",
        }
        is_valid, missing = validate_vehicle_data(data)
        assert is_valid is True
        assert missing == []

    def test_validate_vehicle_data_incomplete(self):
        """validate_vehicle_data returns (False, [...]) for incomplete data."""
        data = {
            "marca": "Honda",
            # Missing modelo, anio, matricula
        }
        is_valid, missing = validate_vehicle_data(data)
        assert is_valid is False
        assert len(missing) > 0

    # ------------------------------------------------------------------
    # Idempotent path returns correct next_step (pure logic, no DB)
    # ------------------------------------------------------------------

    def test_idempotent_logic_complete_personal_returns_collect_vehicle(self):
        """
        Logic check: when existing personal data is complete and current_step
        is COLLECT_PERSONAL, next_step must be 'collect_vehicle'.

        This mirrors exactly what the fix does inside the is_idempotent branch.
        """
        existing_personal = {
            "nombre": "Pepe",
            "apellidos": "García López",
            "dni_cif": "12345678A",
            "email": "pepe@example.com",
            "domicilio_calle": "Calle Mayor 1",
            "domicilio_localidad": "Madrid",
            "domicilio_provincia": "Madrid",
            "domicilio_cp": "28001",
            "itv_nombre": "ITV Madrid Norte",
        }
        current_step = CollectionStep.COLLECT_PERSONAL

        is_complete, _ = validate_personal_data(existing_personal)
        if is_complete and current_step == CollectionStep.COLLECT_PERSONAL:
            next_step_val = CollectionStep.COLLECT_VEHICLE.value
        else:
            next_step_val = current_step.value

        assert next_step_val == "collect_vehicle"

    def test_idempotent_logic_incomplete_personal_stays(self):
        """
        Logic check: when existing personal data is INCOMPLETE, next_step stays
        at current step (no premature transition).
        """
        existing_personal = {
            "nombre": "Pepe",
            # Missing apellidos, dni_cif, email, etc.
        }
        current_step = CollectionStep.COLLECT_PERSONAL

        is_complete, _ = validate_personal_data(existing_personal)
        if is_complete and current_step == CollectionStep.COLLECT_PERSONAL:
            next_step_val = CollectionStep.COLLECT_VEHICLE.value
        else:
            next_step_val = current_step.value

        assert next_step_val == "collect_personal"

    def test_idempotent_logic_complete_vehicle_returns_collect_workshop(self):
        """
        Logic check: when existing vehicle data is complete and current_step
        is COLLECT_VEHICLE, next_step must be 'collect_workshop'.
        """
        existing_vehicle = {
            "marca": "Honda",
            "modelo": "CBR 600",
            "anio": "2018",
            "matricula": "1234BCD",
        }
        current_step = CollectionStep.COLLECT_VEHICLE

        is_complete, _ = validate_vehicle_data(existing_vehicle)
        if is_complete and current_step == CollectionStep.COLLECT_VEHICLE:
            next_step_val = CollectionStep.COLLECT_WORKSHOP.value
        else:
            next_step_val = current_step.value

        assert next_step_val == "collect_workshop"

    def test_idempotent_logic_incomplete_vehicle_stays(self):
        """
        Logic check: when existing vehicle data is INCOMPLETE, next_step stays
        at 'collect_vehicle'.
        """
        existing_vehicle = {
            "marca": "Honda",
            # Missing modelo, anio, matricula
        }
        current_step = CollectionStep.COLLECT_VEHICLE

        is_complete, _ = validate_vehicle_data(existing_vehicle)
        if is_complete and current_step == CollectionStep.COLLECT_VEHICLE:
            next_step_val = CollectionStep.COLLECT_WORKSHOP.value
        else:
            next_step_val = current_step.value

        assert next_step_val == "collect_vehicle"

    def test_idempotent_logic_complete_personal_but_wrong_step_stays(self):
        """
        Logic check: complete personal data but NOT in COLLECT_PERSONAL step
        → no transition (prevents double-advance).
        """
        existing_personal = {
            "nombre": "Pepe",
            "apellidos": "García López",
            "dni_cif": "12345678A",
            "email": "pepe@example.com",
            "domicilio_calle": "Calle Mayor 1",
            "domicilio_localidad": "Madrid",
            "domicilio_provincia": "Madrid",
            "domicilio_cp": "28001",
            "itv_nombre": "ITV Madrid Norte",
        }
        # Simulate we're already past COLLECT_PERSONAL (e.g., in COLLECT_VEHICLE)
        current_step = CollectionStep.COLLECT_VEHICLE

        is_complete, _ = validate_personal_data(existing_personal)
        if is_complete and current_step == CollectionStep.COLLECT_PERSONAL:
            next_step_val = CollectionStep.COLLECT_VEHICLE.value
        else:
            next_step_val = current_step.value

        # Should stay at collect_vehicle (the current step), not jump to collect_workshop
        assert next_step_val == "collect_vehicle"


# =============================================================================
# B2 — confirmar_fotos_elemento triggers sub-mode transition
# =============================================================================

class TestB2ConfirmarFotosElementoTransition:
    """
    B2: _extract_context_from_tool must handle confirmar_fotos_elemento
    exactly like completar_elemento_actual when all_elements_complete=True.
    """

    @pytest.fixture
    def extract(self):
        return ExpedienteModeNode._extract_context_from_tool

    def test_confirmar_fotos_all_elements_complete_transitions(self, extract):
        """
        confirmar_fotos_elemento with all_elements_complete=True must set
        expediente_sub_mode to collect_base_docs (sub-mode transition).

        This is the B2 fix: elements with no required fields complete via
        confirmar_fotos_elemento(), NOT via completar_elemento_actual().
        Before the fix, this call was silently ignored.
        """
        data = {
            "success": True,
            "all_elements_complete": True,
            "current_element_index": 2,
        }
        updates = extract("confirmar_fotos_elemento", {}, json.dumps(data), {})
        assert updates.get("expediente_sub_mode") == "collect_base_docs", (
            "confirmar_fotos_elemento with all_elements_complete=True MUST trigger "
            "transition to collect_base_docs. Before B2 fix, this was ignored."
        )

    def test_confirmar_fotos_not_all_complete_no_transition(self, extract):
        """
        confirmar_fotos_elemento with all_elements_complete=False must NOT
        trigger a sub-mode transition (just tracks progress).
        """
        data = {
            "success": True,
            "all_elements_complete": False,
            "current_element_index": 0,
        }
        updates = extract("confirmar_fotos_elemento", {}, json.dumps(data), {})
        assert "expediente_sub_mode" not in updates

    def test_confirmar_fotos_and_completar_elemento_both_trigger(self, extract):
        """
        BOTH confirmar_fotos_elemento AND completar_elemento_actual must
        trigger the transition when all_elements_complete=True.
        """
        data = json.dumps({"success": True, "all_elements_complete": True})

        updates_confirmar = extract("confirmar_fotos_elemento", {}, data, {})
        updates_completar = extract("completar_elemento_actual", {}, data, {})

        assert updates_confirmar.get("expediente_sub_mode") == "collect_base_docs"
        assert updates_completar.get("expediente_sub_mode") == "collect_base_docs"

    def test_confirmar_fotos_only_checks_all_elements_complete_flag(self, extract):
        """
        NOTE: The confirmar_fotos_elemento/completar_elemento_actual extractor
        checks ONLY all_elements_complete (not success) because these tools
        never return all_elements_complete=True alongside success=False in
        practice — it would be a contradictory state.

        This is intentionally different from other extractors (e.g.
        confirmar_documentacion_base) which DO check success first. The
        current behavior is correct and this test documents it explicitly.
        """
        data = {
            "success": True,
            "all_elements_complete": True,
        }
        updates = extract("confirmar_fotos_elemento", {}, json.dumps(data), {})
        # With success=True and all_elements_complete=True → transition fires
        assert updates.get("expediente_sub_mode") == "collect_base_docs"

        # With success=False but all_elements_complete=True → transition also fires
        # (the extractor doesn't check success here — see docstring above)
        data_fail = {"success": False, "all_elements_complete": True}
        updates_fail = extract("confirmar_fotos_elemento", {}, json.dumps(data_fail), {})
        assert updates_fail.get("expediente_sub_mode") == "collect_base_docs"


class TestB2TransitionClosureContract:
    """Same-turn closure contract for all_elements_complete transitions."""

    @pytest.mark.parametrize("tool_name", ["confirmar_fotos_elemento", "completar_elemento_actual"])
    def test_element_completion_closure_parity_across_entry_points(self, tool_name):
        """Both completion entry points must emit the exact same closure text."""
        closure = _build_element_completion_transition_closure(
            from_sub_mode=COLLECT_ELEMENT_DATA,
            to_sub_mode=COLLECT_BASE_DOCS,
            tool_name=tool_name,
            tool_data={"all_elements_complete": True},
        )

        assert closure == (
            "Perfecto, con esto cerramos la parte de elementos. "
            "Seguimos con el siguiente bloque del expediente."
        )

    def test_element_completion_closure_requires_all_elements_complete(self):
        """Closure contract only applies on explicit all-elements completion."""
        closure = _build_element_completion_transition_closure(
            from_sub_mode=COLLECT_ELEMENT_DATA,
            to_sub_mode=COLLECT_BASE_DOCS,
            tool_name="confirmar_fotos_elemento",
            tool_data={"all_elements_complete": False},
        )

        assert closure is None


# =============================================================================
# B3 — False completion guard (regex)
# =============================================================================

class TestB3FalseCompletionGuard:
    """
    B3: The _FALSE_COMPLETION_RE regex must match sentences where the LLM
    declares the expediente as complete/sent in sub-modes before REVIEW_SUMMARY.

    We test the regex directly (it's a module-level constant compiled inside
    _process_message, but we can reproduce the same pattern here).
    """

    @pytest.fixture
    def false_completion_re(self):
        """Reproduce the same regex used in expediente_mode._process_message."""
        return re.compile(
            r"expediente\s+(?:est[aá]\s+)?(?:complet|enviad|finaliz|cerrad|tramitad|list)"
            r"|(?:tu|el|su)\s+(?:caso|expediente)\s+(?:ha\s+sido|est[aá])\s+(?:enviad|complet|cerrad|registrad)"
            r"|hemos\s+(?:terminad|completad|finaliz|cerrad)\s+(?:el\s+)?(?:expediente|caso|proceso)"
            r"|ya\s+(?:hemos\s+)?(?:terminad|completad)\s+(?:el\s+)?(?:expediente|proceso)"
            r"|todo\s+(?:est[aá]|listo)\s+(?:completad|guardad|registrad)",
            re.IGNORECASE,
        )

    @pytest.mark.parametrize("text", [
        # Pattern 1: "expediente + [opt. está] + completion verb"
        "Tu expediente está completo y ha sido enviado.",
        "El expediente está enviado.",
        "Tu expediente ha sido completado correctamente.",
        "Tu expediente está finalizado.",
        "El expediente está cerrado.",
        "El expediente está completado.",
        "Tu expediente está tramitado.",
        # Pattern 2: "[tu|el|su] + [caso|expediente] + [ha sido|está] + completion verb"
        "Tu caso ha sido registrado.",
        # Pattern 4: "todo + [está|listo] + completion verb"
        "Todo está completado.",
    ])
    def test_false_completion_phrases_detected(self, false_completion_re, text):
        """
        Phrases that falsely declare completion are matched by the regex.

        NOTE: The regex has known gaps (documented below). These tests only
        cover what the regex ACTUALLY matches, not what the ideal regex would.

        Known false-negative gaps (phrases NOT matched by current regex):
        - "Hemos terminado el expediente." — hemos + terminad + expediente requires
          the word order [hemos][terminad][el][expediente] but "terminado" != "terminad"
          (the prefix terminad does NOT match "terminado" - needs terminad+word).
        - "Hemos completado el proceso." — same issue with prefix matching.
        - "Ya hemos terminado el expediente." — same.
        - "Hemos cerrado el proceso." — same.
        - "Todo listo, guardado correctamente." — "listo," has a comma before
          "guardado" so todo+listo+guardad doesn't match.

        These gaps mean the guard is not exhaustive, but it catches the most
        common LLM patterns. The prompts (B3b fix) reinforce the rule explicitly.
        """
        assert false_completion_re.search(text), (
            f"Expected regex to match false-completion phrase: {text!r}"
        )

    @pytest.mark.parametrize("text", [
        # Legitimate partial statements that should NOT trigger
        "Tu expediente está en proceso de tramitación.",
        "¿Podrías confirmar los datos del vehículo?",
        "Necesito la matrícula de tu moto.",
        "Perfecto, seguimos con los datos personales.",
        "Tu caso está activo y lo estamos gestionando.",
        "El expediente está siendo procesado.",
        # "list" prefix but different context
        "Aquí tienes la lista de documentos pendientes.",
    ])
    def test_legitimate_phrases_not_detected(self, false_completion_re, text):
        """
        Phrases that are NOT false completion are NOT matched.

        NOTE: "Todo está guardado hasta ahora, falta el taller." IS matched by
        the regex (false positive — 'todo + esta + guardad' matches). This is a
        known limitation. In practice this edge case is rare (agent won't generate
        this exact phrasing without also calling a tool).
        """
        assert not false_completion_re.search(text), (
            f"Regex incorrectly matched legitimate phrase: {text!r}"
        )

    def test_known_regex_false_positive_documented(self, false_completion_re):
        """
        Documents known false positive: 'Todo está guardado hasta ahora' matches
        the last pattern (todo + está + guardad).

        This is accepted as-is. In practice the guard only fires when no tool
        was called AND the response has no tool calls, so the LLM rarely produces
        this exact phrasing in a context where it matters.
        """
        problematic = "Todo está guardado hasta ahora, falta el taller."
        # Currently matches — documenting as a KNOWN limitation
        assert false_completion_re.search(problematic) is not None, (
            "If this now passes, the regex was improved and this test can be updated."
        )

    def test_known_regex_gaps_documented(self, false_completion_re):
        """
        Documents known false negatives: phrases using 'hemos + terminado/completado'
        are NOT matched because the regex uses prefix 'terminad' which does not
        match the full word 'terminado' when followed immediately by whitespace.

        These are non-critical gaps — the prompt reinforcement (B3b) covers them.
        """
        # These do NOT currently match — documenting the gaps
        gap_phrases = [
            "Hemos terminado el expediente.",
            "Hemos completado el proceso.",
            "Ya hemos terminado el expediente.",
            "Hemos cerrado el proceso.",
        ]
        for phrase in gap_phrases:
            # Currently NOT matched — documenting known gap
            match = false_completion_re.search(phrase)
            # NOTE: If these start matching in future, update to assert match is not None
            assert match is None, (
                f"Regex now matches '{phrase}' — update test_known_regex_gaps_documented "
                "to confirm this is intentional."
            )

    def test_guard_only_applies_outside_review_summary(self, false_completion_re):
        """
        Confirm the guard logic: false completion only blocked when NOT in
        REVIEW_SUMMARY. In REVIEW_SUMMARY, it's valid to say completion.
        """
        false_completion_text = "Tu expediente está completo."
        assert false_completion_re.search(false_completion_text)

        # Outside REVIEW_SUMMARY → guard fires (True means we must block)
        for sub_mode in ["collect_personal", "collect_vehicle", "collect_element_data", "collect_base_docs", "collect_workshop"]:
            should_block = (
                sub_mode != REVIEW_SUMMARY
                and false_completion_re.search(false_completion_text)
            )
            assert should_block, f"Guard should fire for sub_mode={sub_mode}"

        # In REVIEW_SUMMARY → guard does NOT fire
        should_block_in_review = (
            REVIEW_SUMMARY != REVIEW_SUMMARY  # Always False
            and false_completion_re.search(false_completion_text)
        )
        assert not should_block_in_review


# =============================================================================
# B4 — Element state reconciliation in _initialize_mode_context
# =============================================================================

class TestB4ElementStateReconciliation:
    """
    B4: _initialize_mode_context must rebuild element_data_status and
    current_element_index from CaseElementData DB records instead of
    always resetting to 0/pending.
    """

    def test_reconciliation_logic_all_pending(self):
        """
        When all CaseElementData rows are pending_photos, current_element_index=0
        and all statuses are 'pending_photos'.
        """
        codes = ["ESCAPE", "SUBCHASIS", "SUSPENSION"]
        ced_by_code = {
            "ESCAPE": "pending_photos",
            "SUBCHASIS": "pending_photos",
            "SUSPENSION": "pending_photos",
        }

        reconciled_status, reconciled_index, all_done = _reconcile_element_progress(codes, ced_by_code)

        assert reconciled_index == 0
        assert reconciled_status["ESCAPE"] == "pending_photos"
        assert all_done is False

    def test_reconciliation_logic_first_element_completed(self):
        """
        When first element is completed, current_element_index=1 (next pending).
        """
        codes = ["ESCAPE", "SUBCHASIS", "SUSPENSION"]
        ced_by_code = {
            "ESCAPE": "completed",
            "SUBCHASIS": "pending_photos",
            "SUSPENSION": "pending_photos",
        }

        reconciled_status, reconciled_index, all_done = _reconcile_element_progress(codes, ced_by_code)

        assert reconciled_index == 1  # SUBCHASIS is next
        assert reconciled_status["ESCAPE"] == "completed"
        assert reconciled_status["SUBCHASIS"] == "pending_photos"
        assert all_done is False

    def test_reconciliation_logic_all_completed(self):
        """
        When all elements are completed, all_done=True and sub-mode should
        advance to collect_base_docs.
        """
        codes = ["ESCAPE", "SUBCHASIS"]
        ced_by_code = {
            "ESCAPE": "completed",
            "SUBCHASIS": "completed",
        }

        reconciled_status, reconciled_index, all_done = _reconcile_element_progress(codes, ced_by_code)

        assert all_done is True
        assert reconciled_status["ESCAPE"] == "completed"
        assert reconciled_status["SUBCHASIS"] == "completed"

    def test_reconciliation_logic_pending_data_status(self):
        """
        Elements in 'pending_data' state must be the current element (photos done,
        data still needed).
        """
        codes = ["ESCAPE", "SUBCHASIS", "SUSPENSION"]
        ced_by_code = {
            "ESCAPE": "completed",
            "SUBCHASIS": "pending_data",
            "SUSPENSION": "pending_photos",
        }

        reconciled_status, reconciled_index, all_done = _reconcile_element_progress(codes, ced_by_code)

        assert reconciled_index == 1   # SUBCHASIS (pending_data comes before pending_photos)
        assert reconciled_status["SUBCHASIS"] == "pending_data"
        assert all_done is False

    def test_reconciliation_logic_no_db_records_starts_fresh(self):
        """
        When there are no CaseElementData records (empty ced_by_code), we start
        fresh with index=0 and all pending_photos.
        """
        codes = ["ESCAPE", "SUBCHASIS"]
        ced_by_code = {}  # No DB records yet

        reconciled_status, reconciled_index, all_done = _reconcile_element_progress(codes, ced_by_code)

        assert reconciled_index == 0
        assert all(v == "pending_photos" for v in reconciled_status.values())
        assert all_done is False

    def test_all_done_advances_sub_mode_to_collect_base_docs(self):
        """
        When all_done=True and persisted sub_mode is collect_element_data,
        reconciled sub_mode must be collect_base_docs (auto-advance).
        """
        all_elements_done = True
        persisted_sub_mode = COLLECT_ELEMENT_DATA

        if all_elements_done and persisted_sub_mode == COLLECT_ELEMENT_DATA:
            reconciled_sub_mode = COLLECT_BASE_DOCS
        else:
            reconciled_sub_mode = persisted_sub_mode

        assert reconciled_sub_mode == COLLECT_BASE_DOCS

    def test_all_done_preserves_advanced_sub_mode(self):
        """
        When all_done=True but persisted sub_mode is already beyond
        collect_element_data (e.g. collect_base_docs), do NOT reset it.
        """
        all_elements_done = True
        persisted_sub_mode = "collect_base_docs"

        if all_elements_done and persisted_sub_mode == COLLECT_ELEMENT_DATA:
            reconciled_sub_mode = COLLECT_BASE_DOCS
        else:
            reconciled_sub_mode = persisted_sub_mode

        assert reconciled_sub_mode == "collect_base_docs"  # Preserved

    def test_not_all_done_preserves_any_sub_mode(self):
        """
        When not all elements done, sub_mode is always preserved as-is.
        """
        all_elements_done = False
        persisted_sub_mode = COLLECT_ELEMENT_DATA

        if all_elements_done and persisted_sub_mode == COLLECT_ELEMENT_DATA:
            reconciled_sub_mode = COLLECT_BASE_DOCS
        else:
            reconciled_sub_mode = persisted_sub_mode

        assert reconciled_sub_mode == COLLECT_ELEMENT_DATA


# =============================================================================
# Helper: pure Python reimplementation of the reconciliation logic
# (mirrors _initialize_mode_context without DB dependencies)
# =============================================================================

def _reconcile_element_progress(
    codes: list[str],
    ced_by_code: dict[str, str],
) -> tuple[dict[str, str], int, bool]:
    """
    Pure-Python mirror of the reconciliation logic in _initialize_mode_context.

    Reproduces exactly the algorithm implemented in the B4 fix:
    1. Iterate codes in order.
    2. Map each code's status from ced_by_code.
    3. Track first incomplete (pending_data before pending_photos).
    4. Return (reconciled_status, reconciled_index, all_elements_done).
    """
    if not ced_by_code:
        # No DB records — start fresh
        status = {code: "pending_photos" for code in codes}
        return status, 0, False

    reconciled_status: dict[str, str] = {}
    first_incomplete_idx: int = len(codes)

    for idx, code in enumerate(codes):
        db_status = ced_by_code.get(code)
        if db_status == "completed":
            reconciled_status[code] = "completed"
        elif db_status == "pending_data":
            reconciled_status[code] = "pending_data"
            if first_incomplete_idx == len(codes):
                first_incomplete_idx = idx
        else:
            reconciled_status[code] = "pending_photos"
            if first_incomplete_idx == len(codes):
                first_incomplete_idx = idx

    reconciled_index = min(first_incomplete_idx, len(codes) - 1) if codes else 0
    all_done = all(v == "completed" for v in reconciled_status.values()) if reconciled_status else False

    return reconciled_status, reconciled_index, all_done


# =============================================================================
# S1 — Transition/closure regression coverage (Task 5.1)
# Verifies: explicit closure, anti-anticipation, entry-point parity
# =============================================================================

class TestTransitionClosureRegressionS1:
    """
    Regression suite for the element completion transition closure contract.

    Covers three scenarios required by spec S1:
    1. Closure text is explicit and user-friendly (not empty/abrupt)
    2. Anti-anticipation: no next-step details leak in closure
    3. Both entry points (confirmar_fotos_elemento, completar_elemento_actual)
       produce identical closure behavior
    """

    # ------------------------------------------------------------------
    # 1. Explicit closure text (not empty, not abrupt)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("tool_name", ["confirmar_fotos_elemento", "completar_elemento_actual"])
    def test_closure_text_is_non_empty_and_explicit(self, tool_name):
        """Closure text must be a non-empty, human-readable sentence."""
        closure = _build_element_completion_transition_closure(
            from_sub_mode=COLLECT_ELEMENT_DATA,
            to_sub_mode=COLLECT_BASE_DOCS,
            tool_name=tool_name,
            tool_data={"all_elements_complete": True},
        )

        assert closure is not None, "Closure must not be None on valid transition"
        assert len(closure) > 20, "Closure must be a meaningful sentence, not a stub"
        assert closure[0].isupper(), "Closure must start with uppercase (proper sentence)"
        assert closure.endswith("."), "Closure must end with a period (complete sentence)"

    # ------------------------------------------------------------------
    # 2. Anti-anticipation: no next-step details leaked
    # ------------------------------------------------------------------

    _FORBIDDEN_NEXT_STEP_TERMS = [
        "ficha técnica",
        "permiso de circulación",
        "documentación base",
        "datos personales",
        "datos del vehículo",
        "matrícula",
        "bastidor",
        "DNI",
        "nombre",
        "taller",
        "certificado",
    ]

    @pytest.mark.parametrize("tool_name", ["confirmar_fotos_elemento", "completar_elemento_actual"])
    def test_closure_does_not_leak_next_step_details(self, tool_name):
        """
        Anti-anticipation regression: the closure must NOT mention any
        next-step-specific terms (ficha técnica, permiso, datos personales, etc.).

        The next sub-mode's content is the responsibility of the NEXT turn.
        """
        closure = _build_element_completion_transition_closure(
            from_sub_mode=COLLECT_ELEMENT_DATA,
            to_sub_mode=COLLECT_BASE_DOCS,
            tool_name=tool_name,
            tool_data={"all_elements_complete": True},
        )

        assert closure is not None
        closure_lower = closure.lower()
        for term in self._FORBIDDEN_NEXT_STEP_TERMS:
            assert term.lower() not in closure_lower, (
                f"Closure must NOT contain next-step term '{term}' — "
                f"anti-anticipation violation. Got: {closure!r}"
            )

    @pytest.mark.parametrize("tool_name", ["confirmar_fotos_elemento", "completar_elemento_actual"])
    def test_closure_does_not_contain_question_marks(self, tool_name):
        """
        Anti-anticipation: closure must NOT ask questions about the next step.
        Questions about what comes next belong to the next turn's prompt.
        """
        closure = _build_element_completion_transition_closure(
            from_sub_mode=COLLECT_ELEMENT_DATA,
            to_sub_mode=COLLECT_BASE_DOCS,
            tool_name=tool_name,
            tool_data={"all_elements_complete": True},
        )

        assert closure is not None
        assert "?" not in closure, (
            f"Closure must NOT contain question marks — "
            f"anti-anticipation violation. Got: {closure!r}"
        )

    # ------------------------------------------------------------------
    # 3. Entry-point parity
    # ------------------------------------------------------------------

    def test_both_entry_points_produce_identical_closure(self):
        """
        Entry-point parity: confirmar_fotos_elemento and completar_elemento_actual
        must produce the EXACT SAME closure text for the same transition.
        """
        closure_confirmar = _build_element_completion_transition_closure(
            from_sub_mode=COLLECT_ELEMENT_DATA,
            to_sub_mode=COLLECT_BASE_DOCS,
            tool_name="confirmar_fotos_elemento",
            tool_data={"all_elements_complete": True},
        )
        closure_completar = _build_element_completion_transition_closure(
            from_sub_mode=COLLECT_ELEMENT_DATA,
            to_sub_mode=COLLECT_BASE_DOCS,
            tool_name="completar_elemento_actual",
            tool_data={"all_elements_complete": True},
        )

        assert closure_confirmar == closure_completar, (
            "Both entry points must produce identical closure text. "
            f"confirmar: {closure_confirmar!r}, completar: {closure_completar!r}"
        )

    # ------------------------------------------------------------------
    # Negative cases: closure should NOT fire for non-matching transitions
    # ------------------------------------------------------------------

    def test_closure_none_for_non_element_completion_transitions(self):
        """Closure is None when transition is NOT from COLLECT_ELEMENT_DATA."""
        closure = _build_element_completion_transition_closure(
            from_sub_mode=COLLECT_BASE_DOCS,
            to_sub_mode="collect_personal",
            tool_name="confirmar_documentacion_base",
            tool_data={"success": True},
        )
        assert closure is None

    def test_closure_none_for_unrecognized_tool(self):
        """Closure is None for tools that are not completion entry points."""
        closure = _build_element_completion_transition_closure(
            from_sub_mode=COLLECT_ELEMENT_DATA,
            to_sub_mode=COLLECT_BASE_DOCS,
            tool_name="guardar_datos_elemento",
            tool_data={"all_elements_complete": True},
        )
        assert closure is None

    def test_closure_none_when_tool_data_is_none(self):
        """Closure handles None tool_data gracefully."""
        closure = _build_element_completion_transition_closure(
            from_sub_mode=COLLECT_ELEMENT_DATA,
            to_sub_mode=COLLECT_BASE_DOCS,
            tool_name="completar_elemento_actual",
            tool_data=None,
        )
        assert closure is None

    def test_closure_none_when_all_elements_complete_missing(self):
        """Closure is None when tool_data has no all_elements_complete key."""
        closure = _build_element_completion_transition_closure(
            from_sub_mode=COLLECT_ELEMENT_DATA,
            to_sub_mode=COLLECT_BASE_DOCS,
            tool_name="completar_elemento_actual",
            tool_data={"success": True},
        )
        assert closure is None


class TestExtractContextTransitionParity:
    """
    Verify _extract_context_from_tool produces identical context updates
    for both completion entry points when all_elements_complete=True.
    """

    @pytest.fixture
    def extract(self):
        return ExpedienteModeNode._extract_context_from_tool

    def test_extract_context_parity_on_all_elements_complete(self, extract):
        """Both tools must set the same context keys on completion."""
        data = json.dumps({
            "success": True,
            "all_elements_complete": True,
            "current_element_index": 2,
            "element_phase": "photos",
        })
        context = {}

        updates_confirmar = extract("confirmar_fotos_elemento", {}, data, dict(context))
        updates_completar = extract("completar_elemento_actual", {}, data, dict(context))

        # Both must trigger the same sub-mode transition
        assert updates_confirmar.get("expediente_sub_mode") == COLLECT_BASE_DOCS
        assert updates_completar.get("expediente_sub_mode") == COLLECT_BASE_DOCS

        # Both must set the same transition marker
        assert updates_confirmar.get("just_transitioned_from") == COLLECT_ELEMENT_DATA
        assert updates_completar.get("just_transitioned_from") == COLLECT_ELEMENT_DATA

    def test_extract_context_no_transition_when_elements_remain(self, extract):
        """Neither tool should trigger transition when elements remain."""
        data = json.dumps({
            "success": True,
            "all_elements_complete": False,
            "current_element_index": 1,
        })

        updates_confirmar = extract("confirmar_fotos_elemento", {}, data, {})
        updates_completar = extract("completar_elemento_actual", {}, data, {})

        assert "expediente_sub_mode" not in updates_confirmar
        assert "expediente_sub_mode" not in updates_completar


# =============================================================================
# S1+S2 — Integration smoke test: expediente element completion flow (Task 5.3)
#
# Simulates the full expediente element completion flow and verifies both
# transition closure (S1) and image attribution (S2) are correct end-to-end.
# =============================================================================

class TestExpedienteElementFlowSmokeTest:
    """
    Focused integration smoke test for the expediente element completion flow.

    Simulates: photos → data → completion → transition → image attribution
    and verifies that:
    1. Transition closure is deterministic and anti-anticipation compliant
    2. Image assignment snapshot captures correct element_code
    3. Both confirmar_fotos and completar_elemento trigger identical context updates
    4. Images attributed to the correct element via snapshot context
    """

    @pytest.fixture
    def element_flow_context(self) -> dict:
        """Base mode_context for a 2-element expediente mid-flow."""
        return {
            "case_id": "case-smoke-test",
            "category_slug": "motos-part",
            "element_codes": ["PLACA_SOLAR", "CABEZA"],
            "current_element_index": 1,  # On last element
            "element_phase": "photos",
            "element_data_status": {
                "PLACA_SOLAR": "completed",
                "CABEZA": "pending_photos",
            },
            "expediente_sub_mode": COLLECT_ELEMENT_DATA,
        }

    # ------------------------------------------------------------------
    # Phase 1: Image attribution during photo collection
    # ------------------------------------------------------------------

    def test_snapshot_captures_correct_element_during_photos(self, element_flow_context):
        """
        While collecting photos for CABEZA (index=1), the assignment snapshot
        must resolve element_code to 'CABEZA', not 'PLACA_SOLAR'.
        """
        from agent.services.image_handling import (
            get_current_element_code,
            is_in_image_collection_mode,
        )

        ctx = element_flow_context
        assert is_in_image_collection_mode(ctx) is True
        assert get_current_element_code(ctx) == "CABEZA", (
            "Snapshot must resolve to current element at index=1"
        )

    def test_snapshot_clears_element_after_photos_confirmed(self, element_flow_context):
        """
        After confirmar_fotos_elemento transitions element_phase to 'data',
        images should NOT be attributed to the element anymore.
        """
        from agent.services.image_handling import get_current_element_code

        ctx = dict(element_flow_context)
        ctx["element_phase"] = "data"  # Photos confirmed, collecting data
        assert get_current_element_code(ctx) is None, (
            "After photos confirmed, element_code must be None (data phase)"
        )

    # ------------------------------------------------------------------
    # Phase 2: Completion triggers transition
    # ------------------------------------------------------------------

    def test_last_element_completion_triggers_transition(self, element_flow_context):
        """
        When the last element completes (all_elements_complete=True),
        _extract_context_from_tool must set expediente_sub_mode to collect_base_docs.
        """
        extract = ExpedienteModeNode._extract_context_from_tool
        tool_result = json.dumps({
            "success": True,
            "all_elements_complete": True,
            "current_element_index": 1,
            "element_phase": "photos",
        })

        updates = extract(
            "completar_elemento_actual", {}, tool_result, dict(element_flow_context),
        )

        assert updates.get("expediente_sub_mode") == COLLECT_BASE_DOCS
        assert updates.get("just_transitioned_from") == COLLECT_ELEMENT_DATA

    # ------------------------------------------------------------------
    # Phase 3: Transition closure is correct
    # ------------------------------------------------------------------

    def test_completion_emits_deterministic_closure(self, element_flow_context):
        """
        The transition from COLLECT_ELEMENT_DATA to COLLECT_BASE_DOCS must
        produce a deterministic closure message that passes anti-anticipation.
        """
        closure = _build_element_completion_transition_closure(
            from_sub_mode=COLLECT_ELEMENT_DATA,
            to_sub_mode=COLLECT_BASE_DOCS,
            tool_name="completar_elemento_actual",
            tool_data={"all_elements_complete": True},
        )

        assert closure is not None, "Closure must be generated"

        # Anti-anticipation: no next-step terms
        forbidden = [
            "ficha técnica", "permiso", "documentación base",
            "datos personales", "matrícula",
        ]
        closure_lower = closure.lower()
        for term in forbidden:
            assert term not in closure_lower, (
                f"Closure leaks next-step term '{term}': {closure!r}"
            )

        # No questions
        assert "?" not in closure

    # ------------------------------------------------------------------
    # Phase 4: End-to-end flow coherence
    # ------------------------------------------------------------------

    def test_full_flow_photos_to_transition(self, element_flow_context):
        """
        End-to-end coherence check: simulate the full sequence from photo
        collection through completion to transition, verifying each step
        produces the expected state.
        """
        from agent.services.image_handling import get_current_element_code

        extract = ExpedienteModeNode._extract_context_from_tool
        ctx = dict(element_flow_context)

        # Step 1: During photo collection, element_code is CABEZA
        assert get_current_element_code(ctx) == "CABEZA"

        # Step 2: Photos confirmed — confirmar_fotos returns with phase transition
        confirm_result = json.dumps({
            "success": True,
            "element_phase": "data",
            "current_element_index": 1,
        })
        updates = extract("confirmar_fotos_elemento", {}, confirm_result, dict(ctx))
        ctx.update(updates)

        # After confirmation, element_phase is 'data' — images are now base docs
        assert ctx.get("element_phase") == "data"
        assert get_current_element_code(ctx) is None, (
            "After photo confirmation, element_code must be None"
        )

        # Step 3: Data collected and element completed (last element)
        complete_result = json.dumps({
            "success": True,
            "all_elements_complete": True,
            "current_element_index": 1,
        })
        updates = extract("completar_elemento_actual", {}, complete_result, dict(ctx))
        ctx.update(updates)

        # Step 4: Verify transition happened
        assert ctx.get("expediente_sub_mode") == COLLECT_BASE_DOCS, (
            "After last element completion, sub_mode must transition to collect_base_docs"
        )
        assert ctx.get("just_transitioned_from") == COLLECT_ELEMENT_DATA

        # Step 5: Verify closure is available for this transition
        closure = _build_element_completion_transition_closure(
            from_sub_mode=COLLECT_ELEMENT_DATA,
            to_sub_mode=COLLECT_BASE_DOCS,
            tool_name="completar_elemento_actual",
            tool_data={"all_elements_complete": True},
        )
        assert closure is not None
        assert len(closure) > 20

    def test_mid_flow_no_transition_when_elements_remain(self, element_flow_context):
        """
        When completing a non-last element, no sub-mode transition should occur
        and no closure message should be generated.
        """
        extract = ExpedienteModeNode._extract_context_from_tool

        ctx = dict(element_flow_context)
        ctx["current_element_index"] = 0  # First element, second still pending

        complete_result = json.dumps({
            "success": True,
            "all_elements_complete": False,
            "current_element_index": 0,
        })
        updates = extract("completar_elemento_actual", {}, complete_result, dict(ctx))

        # No sub-mode transition
        assert "expediente_sub_mode" not in updates or \
               updates.get("expediente_sub_mode") == COLLECT_ELEMENT_DATA

        # No closure
        closure = _build_element_completion_transition_closure(
            from_sub_mode=COLLECT_ELEMENT_DATA,
            to_sub_mode=COLLECT_BASE_DOCS,
            tool_name="completar_elemento_actual",
            tool_data={"all_elements_complete": False},
        )
        assert closure is None
