"""
MSI Automotive - Constraint Service Optimization Tests.

Tests para FASE 5 del fix de sistema de imágenes.
Verifica que el constraint 'price_requires_tool' se omita correctamente
cuando el precio ya fue calculado en turnos anteriores.
"""

import sys
from pathlib import Path

# Agregar el directorio raíz al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    import pytest
    PYTEST_AVAILABLE = True
except ImportError:
    PYTEST_AVAILABLE = False

from agent.services.constraint_service import _should_skip_constraint


def test_skip_price_constraint_when_tarifa_calculada_exists():
    """Verify constraint is skipped when tariff exists from previous turn."""
    mode_context = {
        "tarifa_calculada": {"precio_final": 410.0},
        "precio_calculado": 410.0,
    }
    
    # Should skip
    result = _should_skip_constraint("price_requires_tool", mode_context)
    assert result is True, "Constraint should be skipped when tarifa_calculada exists"
    
    print("✅ Test pass: Constraint skipped when tarifa_calculada exists")


def test_do_not_skip_price_constraint_when_no_tariff():
    """Verify constraint is NOT skipped when no tariff exists."""
    mode_context = {}
    
    # Should NOT skip
    result = _should_skip_constraint("price_requires_tool", mode_context)
    assert result is False, "Constraint should NOT be skipped when no tariff"
    
    print("✅ Test pass: Constraint active when no tariff")


def test_skip_with_only_precio_calculado():
    """Verify constraint is skipped with only precio_calculado (no tarifa_calculada)."""
    mode_context = {
        "precio_calculado": 410.0,
    }
    
    result = _should_skip_constraint("price_requires_tool", mode_context)
    assert result is True, "Constraint should be skipped with precio_calculado"
    
    print("✅ Test pass: Constraint skipped with precio_calculado")


def test_skip_with_only_tarifa_calculada():
    """Verify constraint is skipped with only tarifa_calculada (no precio_calculado)."""
    mode_context = {
        "tarifa_calculada": {"precio_final": 410.0, "warnings": []},
    }
    
    result = _should_skip_constraint("price_requires_tool", mode_context)
    assert result is True, "Constraint should be skipped with tarifa_calculada"
    
    print("✅ Test pass: Constraint skipped with tarifa_calculada")


def test_existing_expediente_logic_still_works():
    """Verify existing expediente skip logic is not broken."""
    mode_context = {
        "expediente_sub_mode": "collect_personal",
        "tariff_amount": 410.0,
    }
    
    result = _should_skip_constraint("price_requires_tool", mode_context)
    assert result is True, "Existing expediente logic should still work"
    
    print("✅ Test pass: Existing expediente logic preserved")


def test_existing_presupuesto_done_logic_still_works():
    """Verify existing presupuesto_completado skip logic is not broken."""
    mode_context = {
        "presupuesto_completado": True,
    }
    
    result = _should_skip_constraint("price_requires_tool", mode_context)
    assert result is True, "Existing presupuesto_completado logic should still work"
    
    print("✅ Test pass: Existing presupuesto_completado logic preserved")


def test_non_price_constraint_not_affected():
    """Verify non-price constraints are not affected by the change."""
    mode_context = {
        "tarifa_calculada": {"precio_final": 410.0},
        "precio_calculado": 410.0,
    }
    
    # Should NOT skip (different constraint type)
    result = _should_skip_constraint("some_other_constraint", mode_context)
    assert result is False, "Non-price constraints should not be affected"
    
    print("✅ Test pass: Non-price constraints unaffected")


def test_all_constraint_optimization_tests():
    """Run all constraint optimization tests."""
    test_skip_price_constraint_when_tarifa_calculada_exists()
    test_do_not_skip_price_constraint_when_no_tariff()
    test_skip_with_only_precio_calculado()
    test_skip_with_only_tarifa_calculada()
    test_existing_expediente_logic_still_works()
    test_existing_presupuesto_done_logic_still_works()
    test_non_price_constraint_not_affected()
    
    print("\n" + "="*70)
    print("✅ FASE 5 Test: Todas las optimizaciones de constraint funcionan correctamente")
    print("="*70)


if __name__ == "__main__":
    # Permite ejecutar directamente
    test_all_constraint_optimization_tests()
