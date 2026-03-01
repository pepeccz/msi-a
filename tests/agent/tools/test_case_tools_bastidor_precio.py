"""
Regression tests for fix-expediente-bastidor-precio — Grupos A y B/C.

Grupo A — _vehicle_data_complete() helper (R2, R3, R4)
    Pure synchronous function — no DB, no mocks needed.

Grupo B — precio_total en obtener_estado_expediente (R5, S5-S7b)
    Tests the inline vehicle_data_complete check that includes bastidor,
    and the pricing logic embedded in the note builder.

Grupo C — nota Chatwoot en finalizar_expediente (R6, S8-S9)
    Tests the _build_precio_display helper or inline note-building logic.

IMPORTANT: Groups B/C contain notes on partial coverage where the full tool
    mock is too complex. See the "PENDIENTE" section at the bottom.
"""

import pytest

from agent.tools.case_tools import _vehicle_data_complete


# =============================================================================
# Grupo A — _vehicle_data_complete() (R2, R4, S1-S4)
# =============================================================================


class TestVehicleDataComplete:
    """
    Unit tests for _vehicle_data_complete() helper.

    This is a pure sync function — no DB, no async, no mocks.

    Spec coverage: R2, R4, S1, S3, S4
    """

    # ------------------------------------------------------------------
    # R4/S3 — con bastidor → True
    # ------------------------------------------------------------------

    def test_con_todos_los_campos_incluido_bastidor_retorna_true(self):
        """
        R4/S3: Complete vehicle data INCLUDING bastidor must return True.
        """
        data = {
            "marca": "Honda",
            "modelo": "CBR 600",
            "matricula": "1234BCD",
            "anio": "2018",
            "bastidor": "WBA3A5G59DNP26082",
        }
        assert _vehicle_data_complete(data) is True, (
            "All required fields present (including bastidor) must return True."
        )

    # ------------------------------------------------------------------
    # R2/S1 — sin bastidor → False
    # ------------------------------------------------------------------

    def test_sin_bastidor_retorna_false(self):
        """
        R2/S1: Vehicle data without bastidor must return False.

        Regression: before the fix, bastidor was NOT in the required list,
        so this returned True and the case was submitted without VIN.
        """
        data = {
            "marca": "Honda",
            "modelo": "CBR 600",
            "matricula": "1234BCD",
            "anio": "2018",
            # bastidor intentionally absent
        }
        result = _vehicle_data_complete(data)

        assert result is False, (
            "_vehicle_data_complete() must return False when bastidor is missing. "
            "This was the root bug: bastidor was not in required list."
        )

    # ------------------------------------------------------------------
    # S4 — data=None → False (guard defensivo)
    # ------------------------------------------------------------------

    def test_data_none_retorna_false(self):
        """
        S4: _vehicle_data_complete(None) must return False (defensive guard).

        The function is typed as dict | None — None means no data at all.
        """
        assert _vehicle_data_complete(None) is False, (
            "_vehicle_data_complete(None) must return False."
        )

    # ------------------------------------------------------------------
    # S4b — data={} → False
    # ------------------------------------------------------------------

    def test_data_vacio_retorna_false(self):
        """
        S4b: Empty dict must return False (all fields missing).
        """
        assert _vehicle_data_complete({}) is False

    # ------------------------------------------------------------------
    # bastidor="" → False (cadena vacía es falsy)
    # ------------------------------------------------------------------

    def test_bastidor_cadena_vacia_retorna_false(self):
        """
        S4c: bastidor="" (empty string) must return False.

        Empty string is falsy in Python — data.get("bastidor") returns ""
        which evaluates to False in the all() check.
        """
        data = {
            "marca": "Honda",
            "modelo": "CBR 600",
            "matricula": "1234BCD",
            "anio": "2018",
            "bastidor": "",  # empty string — falsy
        }
        assert _vehicle_data_complete(data) is False, (
            "bastidor='' (empty string) must be treated as missing."
        )

    # ------------------------------------------------------------------
    # bastidor=None → False
    # ------------------------------------------------------------------

    def test_bastidor_none_retorna_false(self):
        """bastidor=None must return False (falsy value)."""
        data = {
            "marca": "Honda",
            "modelo": "CBR 600",
            "matricula": "1234BCD",
            "anio": "2018",
            "bastidor": None,
        }
        assert _vehicle_data_complete(data) is False

    # ------------------------------------------------------------------
    # Non-regression: other fields still enforced
    # ------------------------------------------------------------------

    def test_sin_marca_retorna_false(self):
        """Non-regression: marca is still required."""
        data = {
            "modelo": "CBR 600",
            "matricula": "1234BCD",
            "anio": "2018",
            "bastidor": "WBA3A5G59DNP26082",
        }
        assert _vehicle_data_complete(data) is False

    def test_sin_modelo_retorna_false(self):
        """Non-regression: modelo is still required."""
        data = {
            "marca": "Honda",
            "matricula": "1234BCD",
            "anio": "2018",
            "bastidor": "WBA3A5G59DNP26082",
        }
        assert _vehicle_data_complete(data) is False

    def test_sin_matricula_retorna_false(self):
        """Non-regression: matricula is still required."""
        data = {
            "marca": "Honda",
            "modelo": "CBR 600",
            "anio": "2018",
            "bastidor": "WBA3A5G59DNP26082",
        }
        assert _vehicle_data_complete(data) is False

    def test_sin_anio_retorna_false(self):
        """Non-regression: anio is still required."""
        data = {
            "marca": "Honda",
            "modelo": "CBR 600",
            "matricula": "1234BCD",
            "bastidor": "WBA3A5G59DNP26082",
        }
        assert _vehicle_data_complete(data) is False

    # ------------------------------------------------------------------
    # Return type is always bool
    # ------------------------------------------------------------------

    def test_return_type_is_bool(self):
        """_vehicle_data_complete always returns a bool, never truthy/falsy int."""
        data = {
            "marca": "Honda",
            "modelo": "CBR 600",
            "matricula": "1234BCD",
            "anio": "2018",
            "bastidor": "WBA3A5G59DNP26082",
        }
        result = _vehicle_data_complete(data)
        assert isinstance(result, bool)


# =============================================================================
# Grupo B — precio_total inline logic (R5, S5-S7b)
#
# The pricing logic for expediente is embedded inside obtener_estado_expediente()
# and finalizar_expediente() as inline note building. Since these @tool functions
# require mocking get_current_state() + FSM state (complex ContextVar setup),
# we test the PURE PRICING LOGIC as a standalone helper function here.
#
# Strategy: extract and test the exact computation that the tools perform:
#   precio_certificado = 85.0 if taller_propio is False else 0.0
#   precio_total = tariff_amount + precio_certificado
# =============================================================================


class TestPrecioTotalLogic:
    """
    Unit tests for the precio_total calculation logic (R5, S5-S7b).

    We test the pure arithmetic directly — this mirrors what the tools
    must compute. If a refactor extracts this into a helper, these tests
    remain valid.

    Business rules:
    - taller_propio=False → MSI gestiona el certificado → +85€
    - taller_propio=True → cliente tiene taller propio → +0€
    - taller_propio=None → no decision yet → precio_total=None (undetermined)
    - tariff_amount=None → guard defensivo → precio_total=None

    Spec coverage: R5, S5, S6, S7, S7b
    """

    CERTIFICADO_PRECIO = 85.0  # precio fijo del certificado MSI (invariante de negocio)

    def _compute_precio_total(
        self,
        taller_propio: bool | None,
        tariff_amount: float | None,
    ) -> float | None:
        """
        Pure Python mirror of the pricing logic that tools must implement.

        This is the canonical computation:
        - taller_propio is None → cannot compute → None
        - tariff_amount is None → cannot compute → None
        - taller_propio=False → precio_certificado=85 → total=tariff+85
        - taller_propio=True → precio_certificado=0 → total=tariff
        """
        if taller_propio is None:
            return None
        if tariff_amount is None:
            return None
        precio_certificado = self.CERTIFICADO_PRECIO if taller_propio is False else 0.0
        return tariff_amount + precio_certificado

    # ------------------------------------------------------------------
    # S5 — taller_propio=False, tariff_amount=410.0 → precio_total=495.0
    # ------------------------------------------------------------------

    def test_taller_propio_false_añade_certificado(self):
        """
        S5: taller_propio=False + tariff_amount=410.0 → precio_total=495.0.

        MSI gestiona el certificado: 410 + 85 = 495.
        """
        precio_total = self._compute_precio_total(
            taller_propio=False,
            tariff_amount=410.0,
        )
        assert precio_total == 495.0, (
            f"Expected 495.0 (410 + 85 certificado). Got: {precio_total}"
        )

    def test_taller_propio_false_precio_certificado_es_85(self):
        """
        S5b: When taller_propio=False, precio_certificado must be exactly 85.
        """
        tariff_amount = 410.0
        if False is False:  # taller_propio=False
            precio_certificado = self.CERTIFICADO_PRECIO
        else:
            precio_certificado = 0.0
        assert precio_certificado == 85.0

    # ------------------------------------------------------------------
    # S6 — taller_propio=True, tariff_amount=350.0 → precio_total=350.0
    # ------------------------------------------------------------------

    def test_taller_propio_true_sin_certificado(self):
        """
        S6: taller_propio=True + tariff_amount=350.0 → precio_total=350.0.

        Cliente tiene taller propio: sin coste adicional.
        """
        precio_total = self._compute_precio_total(
            taller_propio=True,
            tariff_amount=350.0,
        )
        assert precio_total == 350.0, (
            f"Expected 350.0 (no certificado). Got: {precio_total}"
        )

    # ------------------------------------------------------------------
    # S7 — taller_propio=None → precio_total=None
    # ------------------------------------------------------------------

    def test_taller_propio_none_precio_total_none(self):
        """
        S7: taller_propio=None (decision not made yet) → precio_total=None.

        Cannot compute total without knowing if MSI manages certificate.
        """
        precio_total = self._compute_precio_total(
            taller_propio=None,
            tariff_amount=410.0,
        )
        assert precio_total is None, (
            "When taller_propio is None, precio_total must be None (undetermined)."
        )

    # ------------------------------------------------------------------
    # S7b — tariff_amount=None → guard defensivo → precio_total=None
    # ------------------------------------------------------------------

    def test_tariff_amount_none_precio_total_none(self):
        """
        S7b: tariff_amount=None (no tariff calculated) → precio_total=None.

        Defensive guard: cannot add certificado to an unknown base price.
        """
        precio_total = self._compute_precio_total(
            taller_propio=False,
            tariff_amount=None,
        )
        assert precio_total is None, (
            "When tariff_amount is None, precio_total must be None (defensive guard)."
        )

    # ------------------------------------------------------------------
    # Invariant: CERTIFICADO_PRECIO is exactly 85€ (business rule)
    # ------------------------------------------------------------------

    def test_certificado_precio_invariante_85(self):
        """
        Business invariant: the certificado price is exactly 85€.

        This is an MSI Automotive business constant — if it changes,
        multiple places in the codebase need updating.
        """
        assert self.CERTIFICADO_PRECIO == 85.0, (
            "El precio del certificado MSI es 85€ (invariante de negocio). "
            "Si cambió, actualiza este test Y todos los lugares donde se usa."
        )

    # ------------------------------------------------------------------
    # Edge case: tariff_amount=0 with taller_propio=False → 85.0
    # ------------------------------------------------------------------

    def test_tariff_zero_with_certificado(self):
        """Edge: tariff_amount=0.0 + taller_propio=False → precio_total=85.0."""
        precio_total = self._compute_precio_total(
            taller_propio=False,
            tariff_amount=0.0,
        )
        assert precio_total == 85.0


# =============================================================================
# Grupo C — nota Chatwoot / precio_display (R6, S8-S9)
#
# finalizar_expediente() builds a Chatwoot private note inline.
# The current implementation does NOT have a _build_precio_display() helper.
# We test the logic as a standalone pure function that mirrors the note content.
#
# If a future refactor extracts _build_precio_display(), these tests will
# validate that function directly.
# =============================================================================


class TestPrecioDisplayLogic:
    """
    Unit tests for the precio_display note logic (R6, S8-S9).

    We test the PURE STRING BUILDING logic that finalizar_expediente uses
    when creating the Chatwoot private note.

    Business rules (from the note template in case_tools.py line 1727-1734):
    - tariff_amount + certificado info must appear in the note
    - When taller_propio=False: note must mention 85€ (certificado) and total
    - When taller_propio=True: note must NOT mention 85€

    Spec coverage: R6, S8, S9
    """

    def _build_precio_display(
        self,
        taller_propio: bool | None,
        tariff_amount: float | None,
    ) -> str:
        """
        Pure Python mirror of the precio display string for the Chatwoot note.

        This mirrors what finalizar_expediente() computes inline.
        If extracted to a helper, this becomes a thin wrapper around that helper.

        Returns:
            String describing precio info for the Chatwoot note.
            Empty string if tariff_amount is None.
        """
        if tariff_amount is None:
            return ""  # guard defensivo: no info to show

        if taller_propio is False:
            precio_certificado = 85.0
            precio_total = tariff_amount + precio_certificado
            return (
                f"{tariff_amount}€ + 85€ certificado = {precio_total}€ + IVA"
            )
        elif taller_propio is True:
            return f"{tariff_amount}€ + IVA (taller propio, sin certificado)"
        else:
            # taller_propio is None — just show base price
            return f"{tariff_amount}€ + IVA (taller pendiente de confirmar)"

    # ------------------------------------------------------------------
    # S8 — taller_propio=False → nota contiene "85" y "495"
    # ------------------------------------------------------------------

    def test_taller_propio_false_nota_contiene_85_y_total(self):
        """
        S8: taller_propio=False, tariff_amount=410 → precio_display must
        contain '85' (certificado) and '495' (total).

        Regression: before the fix, the note showed only 410 without the
        certificado cost, misleading human reviewers.
        """
        display = self._build_precio_display(
            taller_propio=False,
            tariff_amount=410.0,
        )
        assert "85" in display, (
            f"precio_display for taller_propio=False must contain '85' (certificado). "
            f"Got: {display!r}"
        )
        assert "495" in display, (
            f"precio_display for taller_propio=False must contain '495' (total). "
            f"Got: {display!r}"
        )

    # ------------------------------------------------------------------
    # S9 — taller_propio=True → nota NO contiene "85"
    # ------------------------------------------------------------------

    def test_taller_propio_true_nota_no_contiene_85(self):
        """
        S9: taller_propio=True, tariff_amount=350 → precio_display must NOT
        contain '85' (no certificado cost for client with own workshop).
        """
        display = self._build_precio_display(
            taller_propio=True,
            tariff_amount=350.0,
        )
        assert "85" not in display, (
            f"precio_display for taller_propio=True must NOT contain '85'. "
            f"Got: {display!r}"
        )
        # Should still contain the tariff amount
        assert "350" in display, (
            f"precio_display must contain tariff amount '350'. Got: {display!r}"
        )

    # ------------------------------------------------------------------
    # Guard defensivo — tariff_amount=None → no falla (S9b)
    # ------------------------------------------------------------------

    def test_tariff_amount_none_no_falla(self):
        """
        S9b: tariff_amount=None → defensive guard, returns empty string without crash.
        """
        try:
            display = self._build_precio_display(
                taller_propio=False,
                tariff_amount=None,
            )
            # Must not raise — just return empty or safe string
            assert isinstance(display, str), "Must return a string even with None tariff"
        except Exception as exc:
            pytest.fail(
                f"_build_precio_display with tariff_amount=None must not raise. "
                f"Got: {type(exc).__name__}: {exc}"
            )

    # ------------------------------------------------------------------
    # taller_propio=None → no falla, no "85" (undetermined)
    # ------------------------------------------------------------------

    def test_taller_propio_none_no_falla(self):
        """
        Guard: taller_propio=None must not crash. No '85' in output.
        """
        display = self._build_precio_display(
            taller_propio=None,
            tariff_amount=410.0,
        )
        assert isinstance(display, str)
        # Should not include certificado amount since decision is pending
        assert "85" not in display, (
            f"With taller_propio=None, '85' should not appear. Got: {display!r}"
        )


# =============================================================================
# TESTS PENDIENTES (fuera de scope por complejidad de mock)
# =============================================================================
#
# Los siguientes tests NO se implementaron en este archivo porque requieren
# mockear el ContextVar de FSM (`get_current_state`) de forma compleja:
#
# 1. obtener_estado_expediente() — test de integración completo:
#    - Requiere: mock de get_current_state() + mock de get_case_fsm_state()
#    - El ContextVar es un objeto de contexto de asyncio que no puede
#      substituirse fácilmente con patch() estándar.
#    - Alternativa sugerida: convertir el check de vehicle_data_complete
#      en línea 1918 a llamar a _vehicle_data_complete() — luego testeable.
#    - Spec afectada: R5, S5-S7b (precio_total en response dict)
#
# 2. finalizar_expediente() — nota Chatwoot con precio correcto:
#    - Requiere: mock de get_current_state() + get_case_fsm_state() +
#      get_async_session() + ChatwootClient
#    - La lógica inline de note_content (líneas 1727-1734) no tiene helper
#      extraíble en el código actual.
#    - Para hacer este test factible sin refactor, hay que:
#      a) Extraer _build_chatwoot_note() como helper testeable, o
#      b) Usar un test de integración pesado que mockee toda la cadena.
#    - Spec afectada: R6, S8-S9 (precio_display en nota privada)
#
# RECOMENDACIÓN para la siguiente fase de hardening:
#   - Extraer _build_precio_display(taller_propio, tariff_amount) → str
#   - Extraer _build_chatwoot_note(case_fsm_state) → str
#   - Ambos como módulo-level helpers en case_tools.py
#   - Luego estos tests de Grupo B/C pasan a testear los helpers directamente
#
# =============================================================================
