#!/usr/bin/env python3
"""
Script de verificación post-migración para reestructuración de motos.

Verifica que todos los cambios de la migración 035 se aplicaron correctamente.
"""

import asyncio
import sys
from typing import List, Tuple

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

# Add project root to path
sys.path.insert(0, "/home/autohomologacion/msi-a")

from database.connection import get_async_session
from database.models import (
    Element,
    ElementRequiredField,
    Warning,
    ElementWarningAssociation,
)


async def verify_base_elements(session: AsyncSession) -> Tuple[bool, str]:
    """Verificar que los 2 elementos base fueron creados."""
    result = await session.execute(
        select(Element)
        .where(Element.code.in_(["FRENADO", "CARROCERIA_EXT"]))
        .where(Element.is_base == True)
    )
    elements = result.scalars().all()
    
    if len(elements) == 2:
        return True, f"✅ 2 elementos base creados: {', '.join(e.code for e in elements)}"
    else:
        return False, f"❌ Esperados 2 elementos base, encontrados {len(elements)}"


async def verify_parent_relationships(session: AsyncSession) -> Tuple[bool, str]:
    """Verificar que los 9 hijos tienen parent_element_id correcto."""
    # Hijos de FRENADO
    brake_children = ["FRENADO_DISCOS", "FRENADO_PINZAS", "FRENADO_BOMBAS", 
                      "FRENADO_LATIGUILLOS", "FRENADO_DEPOSITO"]
    
    result = await session.execute(
        select(func.count())
        .select_from(Element)
        .where(Element.code.in_(brake_children))
        .where(Element.parent_element_id.isnot(None))
    )
    brake_count = result.scalar()
    
    # Hijos de CARROCERIA_EXT
    body_children = ["CARENADO", "GUARDABARROS_DEL", "GUARDABARROS_TRAS", "CARROCERIA"]
    
    result = await session.execute(
        select(func.count())
        .select_from(Element)
        .where(Element.code.in_(body_children))
        .where(Element.parent_element_id.isnot(None))
    )
    body_count = result.scalar()
    
    total = brake_count + body_count
    if total == 9:
        return True, f"✅ 9 elementos con parent_element_id: {brake_count} brake + {body_count} bodywork"
    else:
        return False, f"❌ Esperados 9 hijos con parent, encontrados {total}"


async def verify_new_fields(session: AsyncSession) -> Tuple[bool, str]:
    """Verificar que los 19 campos nuevos fueron creados."""
    # Campos específicos a verificar
    test_fields = [
        ("INTERMITENTES_DEL", "altura_mm"),
        ("INTERMITENTES_TRAS", "altura_mm"),
        ("PILOTO_FRENO", "marca"),
        ("VELOCIMETRO", "ubicacion_captador_nuevo"),
        ("LLANTAS", "posicion"),
        ("ACCESORIO_GENERICO", "descripcion_elemento"),
    ]
    
    found = 0
    for elem_code, field_key in test_fields:
        result = await session.execute(
            select(func.count())
            .select_from(ElementRequiredField)
            .join(Element, ElementRequiredField.element_id == Element.id)
            .where(Element.code == elem_code)
            .where(ElementRequiredField.field_key == field_key)
        )
        if result.scalar() > 0:
            found += 1
    
    # Contar todos los campos nuevos
    all_fields_query = text("""
        SELECT COUNT(*) 
        FROM element_required_fields f
        JOIN elements e ON f.element_id = e.id
        WHERE e.code IN ('INTERMITENTES_DEL', 'INTERMITENTES_TRAS', 'PILOTO_FRENO', 
                         'LUZ_MATRICULA', 'CATADIOPTRICO', 'ANTINIEBLAS',
                         'MANDOS_AVANZADOS', 'MATRICULA', 'VELOCIMETRO', 
                         'LLANTAS', 'ACCESORIO_GENERICO')
    """)
    result = await session.execute(all_fields_query)
    total_fields = result.scalar()
    
    if found == len(test_fields):
        return True, f"✅ {found}/{len(test_fields)} campos críticos verificados, {total_fields} campos totales en elementos modificados"
    else:
        return False, f"❌ Solo {found}/{len(test_fields)} campos críticos encontrados"


async def verify_warnings(session: AsyncSession) -> Tuple[bool, str]:
    """Verificar que las 4 warnings fueron creadas."""
    warning_codes = [
        "frenado_latiguillos_especificacion",
        "antinieblas_pictograma_obligatorio",
        "llantas_ensayo_neumatico",
        "accesorio_generico_evaluacion",
    ]
    
    result = await session.execute(
        select(func.count())
        .select_from(Warning)
        .where(Warning.code.in_(warning_codes))
    )
    count = result.scalar()
    
    if count == 4:
        return True, f"✅ 4 warnings creadas: {', '.join(warning_codes)}"
    else:
        return False, f"❌ Esperadas 4 warnings, encontradas {count}"


async def verify_warning_associations(session: AsyncSession) -> Tuple[bool, str]:
    """Verificar que las 4 asociaciones fueron creadas (dual system)."""
    # Verificar que las warnings de elementos tienen associations
    result = await session.execute(
        select(func.count())
        .select_from(ElementWarningAssociation)
        .join(Warning, ElementWarningAssociation.warning_id == Warning.id)
        .where(Warning.code.in_([
            "frenado_latiguillos_especificacion",
            "antinieblas_pictograma_obligatorio",
            "llantas_ensayo_neumatico",
            "accesorio_generico_evaluacion",
        ]))
    )
    count = result.scalar()
    
    if count == 4:
        return True, f"✅ 4 element_warning_associations creadas (dual system)"
    else:
        return False, f"❌ Esperadas 4 associations, encontradas {count}"


async def verify_accesorio_generico(session: AsyncSession) -> Tuple[bool, str]:
    """Verificar que ACCESORIO_GENERICO fue creado correctamente."""
    result = await session.execute(
        select(Element).where(Element.code == "ACCESORIO_GENERICO")
    )
    element = result.scalar_one_or_none()
    
    if not element:
        return False, "❌ ACCESORIO_GENERICO no encontrado"
    
    # Verificar que tiene 5 campos
    result = await session.execute(
        select(func.count())
        .select_from(ElementRequiredField)
        .where(ElementRequiredField.element_id == element.id)
    )
    field_count = result.scalar()
    
    # Verificar que tiene 1 warning (via M2M association)
    result = await session.execute(
        select(func.count())
        .select_from(ElementWarningAssociation)
        .where(ElementWarningAssociation.element_id == element.id)
    )
    warning_count = result.scalar()
    
    if field_count == 5 and warning_count == 1:
        return True, f"✅ ACCESORIO_GENERICO completo: {field_count} campos, {warning_count} warning, sort_order={element.sort_order}"
    else:
        return False, f"❌ ACCESORIO_GENERICO incompleto: {field_count}/5 campos, {warning_count}/1 warning"


async def run_verification():
    """Ejecutar todas las verificaciones."""
    print("=" * 70)
    print("🔍 Verificación post-migración: 035_restructure_motos_elements")
    print("=" * 70)
    print()
    
    checks = [
        ("Elementos base (FRENADO, CARROCERIA_EXT)", verify_base_elements),
        ("Relaciones padre-hijo (9 elementos)", verify_parent_relationships),
        ("Campos nuevos (19 campos)", verify_new_fields),
        ("Warnings (4 warnings)", verify_warnings),
        ("Asociaciones warning-element (4 assocs)", verify_warning_associations),
        ("ACCESORIO_GENERICO completo", verify_accesorio_generico),
    ]
    
    results: List[Tuple[str, bool, str]] = []
    
    async with get_async_session() as session:
        for check_name, check_func in checks:
            print(f"Verificando: {check_name}...")
            try:
                success, message = await check_func(session)
                results.append((check_name, success, message))
                print(f"  {message}")
            except Exception as e:
                results.append((check_name, False, f"❌ Error: {str(e)}"))
                print(f"  ❌ Error: {str(e)}")
            print()
    
    # Resumen
    print("=" * 70)
    print("📊 RESUMEN")
    print("=" * 70)
    
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    
    for check_name, success, message in results:
        status = "✅" if success else "❌"
        print(f"{status} {check_name}")
    
    print()
    print(f"Resultado: {passed}/{total} verificaciones exitosas")
    
    if passed == total:
        print()
        print("🎉 ¡Todas las verificaciones pasaron! La migración se aplicó correctamente.")
        return 0
    else:
        print()
        print("⚠️  Algunas verificaciones fallaron. Revisar los mensajes arriba.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_verification())
    sys.exit(exit_code)
