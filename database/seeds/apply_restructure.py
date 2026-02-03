#!/usr/bin/env python3
"""
Script para aplicar reestructuración completa de motos_part.py

Este script aplica todos los cambios pendientes del PLAN_CAMBIOS_MOTOS.md:
- Añade required_fields faltantes a 10 elementos
- Añade warnings a 2 elementos
- Crea elemento nuevo ACCESORIO_GENERICO
"""

import re
import sys
from pathlib import Path


def main():
    """Aplica todos los cambios a motos_part.py"""
    
    # Leer archivo
    seeds_path = Path(__file__).parent / "data" / "motos_part.py"
    
    print(f"📖 Leyendo {seeds_path}...")
    content = seeds_path.read_text(encoding="utf-8")
    original_content = content  # Backup
    
    print("\n🔧 Aplicando cambios...\n")
    
    # GRUPO A: Required fields faltantes
    
    # 1. INTERMITENTES_DEL - añadir altura_mm
    print("1️⃣  Añadiendo altura_mm a INTERMITENTES_DEL...")
    content = add_field_to_element(
        content,
        element_code="INTERMITENTES_DEL",
        field_code="""            {
                "field_key": "altura_mm",
                "field_label": "Altura desde el suelo (mm)",
                "field_type": "number",
                "sort_order": 4,
                "example_value": "500",
                "llm_instruction": "Solicita la altura del intermitente delantero desde el suelo en milímetros",
                "validation_rules": {"min_value": 250, "max_value": 1200},
            },""",
        after_field="distancia_faro_mm"
    )
    
    # 2. INTERMITENTES_TRAS - añadir altura_mm
    print("2️⃣  Añadiendo altura_mm a INTERMITENTES_TRAS...")
    content = add_field_to_element(
        content,
        element_code="INTERMITENTES_TRAS",
        field_code="""            {
                "field_key": "altura_mm",
                "field_label": "Altura desde el suelo (mm)",
                "field_type": "number",
                "sort_order": 5,
                "example_value": "600",
                "llm_instruction": "Solicita la altura del intermitente trasero desde el suelo en milímetros",
                "validation_rules": {"min_value": 250, "max_value": 1200},
            },""",
        after_field="integra_luz_freno"
    )
    
    # 3. PILOTO_FRENO - añadir marca al inicio
    print("3️⃣  Añadiendo marca a PILOTO_FRENO...")
    content = add_first_field_and_reorder(
        content,
        element_code="PILOTO_FRENO",
        new_field="""            {
                "field_key": "marca",
                "field_label": "Marca o Referencia",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "Puig",
                "llm_instruction": "Solicita la marca o referencia del piloto de freno",
            },""",
        reorder_map={
            "contrasena_homologacion": 2,
            "altura_mm": 3,
            "integra_intermitentes": 4,
        }
    )
    
    # 4. LUZ_MATRICULA - añadir marca al inicio
    print("4️⃣  Añadiendo marca a LUZ_MATRICULA...")
    content = add_first_field_and_reorder(
        content,
        element_code="LUZ_MATRICULA",
        new_field="""            {
                "field_key": "marca",
                "field_label": "Marca o Referencia",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "Puig",
                "llm_instruction": "Solicita la marca o referencia de la luz de matrícula",
            },""",
        reorder_map={
            "contrasena_homologacion": 2,
            "altura_mm": 3,
            "posicion": 4,
        }
    )
    
    # 5. CATADIOPTRICO - añadir marca al inicio
    print("5️⃣  Añadiendo marca a CATADIOPTRICO...")
    content = add_first_field_and_reorder(
        content,
        element_code="CATADIOPTRICO",
        new_field="""            {
                "field_key": "marca",
                "field_label": "Marca o Referencia",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "OEM",
                "llm_instruction": "Solicita la marca o referencia del catadióptrico",
            },""",
        reorder_map={
            "contrasena_homologacion": 2,
            "altura_mm": 3,
            "perpendicular": 4,
        }
    )
    
    # 6. ANTINIEBLAS - añadir marca al inicio
    print("6️⃣  Añadiendo marca a ANTINIEBLAS...")
    content = add_first_field_and_reorder(
        content,
        element_code="ANTINIEBLAS",
        new_field="""            {
                "field_key": "marca",
                "field_label": "Marca",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "Hella",
                "llm_instruction": "Solicita la marca de las luces antiniebla",
            },""",
        reorder_map={
            "contrasena_homologacion": 2,
            "tiene_pictograma": 3,
        }
    )
    
    # 7. MANDOS_AVANZADOS - reemplazar required_fields completos
    print("7️⃣  Reemplazando required_fields de MANDOS_AVANZADOS...")
    content = replace_required_fields(
        content,
        element_code="MANDOS_AVANZADOS",
        new_fields="""        "required_fields": [
            {
                "field_key": "marca",
                "field_label": "Marca",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "Gilles Tooling",
                "llm_instruction": "Solicita la marca de los mandos avanzados",
            },
            {
                "field_key": "mando_freno_material",
                "field_label": "Material mando de freno",
                "field_type": "select",
                "options": ["Aluminio", "Aluminio CNC", "Acero", "Titanio"],
                "sort_order": 2,
                "llm_instruction": "Pregunta el material del mando de freno (pedal)",
            },
            {
                "field_key": "mando_marchas_material",
                "field_label": "Material mando de marchas",
                "field_type": "select",
                "options": ["Aluminio", "Aluminio CNC", "Acero", "Titanio"],
                "sort_order": 3,
                "llm_instruction": "Pregunta el material del mando de marchas (pedal)",
            },
        ],"""
    )
    
    # 8. MATRICULA - añadir 4 campos condicionales
    print("8️⃣  Añadiendo campos condicionales a MATRICULA...")
    content = add_matricula_fields(content)
    
    # 9. VELOCIMETRO - añadir ubicacion_captador_nuevo
    print("9️⃣  Añadiendo ubicacion_captador_nuevo a VELOCIMETRO...")
    content = add_field_to_element(
        content,
        element_code="VELOCIMETRO",
        field_code="""            {
                "field_key": "ubicacion_captador_nuevo",
                "field_label": "Ubicación del nuevo captador",
                "field_type": "text",
                "sort_order": 7,
                "is_required": False,
                "example_value": "Rueda delantera eje derecho",
                "llm_instruction": "Si se instala captador nuevo, describe dónde se ubica exactamente",
                "condition_field_key": "captador",
                "condition_operator": "equals",
                "condition_value": "Nuevo captador",
            },""",
        after_field="captador"
    )
    
    # 10. LLANTAS - añadir posicion al inicio
    print("🔟 Añadiendo posicion a LLANTAS...")
    content = add_first_field_and_reorder(
        content,
        element_code="LLANTAS",
        new_field="""            {
                "field_key": "posicion",
                "field_label": "Posición",
                "field_type": "select",
                "options": ["Delantera", "Trasera", "Ambas"],
                "sort_order": 1,
                "llm_instruction": "Pregunta si se cambia la llanta delantera, trasera o ambas",
            },""",
        reorder_map={
            "marca": 2,
            "medidas_del": 3,
            "medidas_tras": 4,
        }
    )
    
    # GRUPO B: Warnings faltantes
    
    # 11. ANTINIEBLAS - añadir segundo warning
    print("1️⃣1️⃣ Añadiendo warning pictograma a ANTINIEBLAS...")
    content = add_warning_to_element(
        content,
        element_code="ANTINIEBLAS",
        warning_code="""            {
                "code": "antinieblas_pictograma_obligatorio",
                "message": "Necesario pictograma homologado en el botón de encendido (requisito obligatorio).",
                "severity": "warning",
            },"""
    )
    
    # 12. LLANTAS - añadir warning ensayo
    print("1️⃣2️⃣ Añadiendo warning ensayo a LLANTAS...")
    content = add_warning_to_element(
        content,
        element_code="LLANTAS",
        warning_code="""            {
                "code": "llantas_ensayo_neumatico",
                "message": "Si el neumático delantero supera 10% en diámetro o trasero supera 8%, puede requerir ensayo de frenada (+375 EUR).",
                "severity": "warning",
            },"""
    )
    
    # GRUPO C: Elemento nuevo
    
    # 13. ACCESORIO_GENERICO - insertar al final
    print("1️⃣3️⃣ Añadiendo elemento ACCESORIO_GENERICO...")
    content = add_accesorio_generico(content)
    
    # Guardar archivo
    print(f"\n💾 Guardando cambios en {seeds_path}...")
    seeds_path.write_text(content, encoding="utf-8")
    
    print("\n✅ ¡COMPLETADO! Todos los cambios aplicados exitosamente.\n")
    print("📊 Resumen:")
    print("   - Required fields añadidos: ~25 campos en 10 elementos")
    print("   - Warnings añadidos: 2")
    print("   - Elementos nuevos: 1 (ACCESORIO_GENERICO)")
    print("\n🔄 Próximo paso: Actualizar tier_mappings.py")


def add_field_to_element(content: str, element_code: str, field_code: str, after_field: str) -> str:
    """Añade un campo después de otro campo específico en un elemento"""
    # Buscar el elemento
    element_pattern = rf'("code": "{element_code}",.*?"required_fields": \[)(.*?)(\],.*?"code":)'
    
    match = re.search(element_pattern, content, re.DOTALL)
    if not match:
        print(f"   ⚠️  Elemento {element_code} no encontrado")
        return content
    
    fields_section = match.group(2)
    
    # Buscar el campo after_field
    field_pattern = rf'("field_key": "{after_field}".*?\}}),\n'
    field_match = re.search(field_pattern, fields_section, re.DOTALL)
    
    if not field_match:
        print(f"   ⚠️  Campo {after_field} no encontrado en {element_code}")
        return content
    
    # Insertar nuevo campo después
    new_fields = fields_section[:field_match.end()] + field_code + "\n" + fields_section[field_match.end():]
    
    # Reemplazar en content
    new_content = content[:match.start(2)] + new_fields + content[match.end(2):]
    
    print(f"   ✓ Campo añadido a {element_code}")
    return new_content


def add_first_field_and_reorder(content: str, element_code: str, new_field: str, reorder_map: dict) -> str:
    """Añade un campo al inicio y actualiza sort_order de los demás"""
    # Buscar el elemento
    element_pattern = rf'("code": "{element_code}",.*?"required_fields": \[)(.*?)(\],)'
    
    match = re.search(element_pattern, content, re.DOTALL)
    if not match:
        print(f"   ⚠️  Elemento {element_code} no encontrado")
        return content
    
    fields_section = match.group(2)
    
    # Actualizar sort_order de los campos existentes
    updated_fields = fields_section
    for field_key, new_order in reorder_map.items():
        updated_fields = re.sub(
            rf'("field_key": "{field_key}".*?"sort_order": )\d+',
            rf'\g<1>{new_order}',
            updated_fields,
            flags=re.DOTALL
        )
    
    # Insertar nuevo campo al inicio (después del primer salto de línea)
    first_newline = updated_fields.find('\n')
    new_fields = updated_fields[:first_newline+1] + new_field + "\n" + updated_fields[first_newline+1:]
    
    # Reemplazar en content
    new_content = content[:match.start(2)] + new_fields + content[match.end(2):]
    
    print(f"   ✓ Campo añadido al inicio de {element_code} y sort_order actualizado")
    return new_content


def replace_required_fields(content: str, element_code: str, new_fields: str) -> str:
    """Reemplaza todos los required_fields de un elemento"""
    # Buscar el bloque required_fields completo
    pattern = rf'("code": "{element_code}",.*?)("required_fields": \[.*?\],)(\s+\}})'
    
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        print(f"   ⚠️  Elemento {element_code} no encontrado")
        return content
    
    # Reemplazar
    new_content = content[:match.start(2)] + new_fields + content[match.end(2):]
    
    print(f"   ✓ Required fields reemplazados en {element_code}")
    return new_content


def add_matricula_fields(content: str) -> str:
    """Añade los 4 campos condicionales a MATRICULA"""
    element_code = "MATRICULA"
    
    # Buscar required_fields de MATRICULA
    pattern = rf'("code": "{element_code}",.*?"required_fields": \[)(.*?)(\],)'
    
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        print(f"   ⚠️  Elemento {element_code} no encontrado")
        return content
    
    fields_section = match.group(2)
    
    # Buscar el campo "tipo_montaje" para insertar después
    tipo_pattern = r'("field_key": "tipo_montaje".*?\}),\n'
    tipo_match = re.search(tipo_pattern, fields_section, re.DOTALL)
    
    if not tipo_match:
        print(f"   ⚠️  Campo tipo_montaje no encontrado en {element_code}")
        return content
    
    # Campos a insertar
    new_fields = """            {
                "field_key": "ubicacion_sin_brazo",
                "field_label": "Ubicación (sin brazo)",
                "field_type": "text",
                "sort_order": 2,
                "is_required": False,
                "example_value": "Bajo el colín",
                "llm_instruction": "Si es sin brazo, describe la ubicación específica del portamatrículas",
                "condition_field_key": "tipo_montaje",
                "condition_operator": "equals",
                "condition_value": "Sin brazo (portamatrículas corto)",
            },
            {
                "field_key": "brazo_material",
                "field_label": "Material del brazo",
                "field_type": "select",
                "options": ["Aluminio", "Acero", "Fibra de carbono", "Plástico ABS"],
                "sort_order": 3,
                "is_required": False,
                "llm_instruction": "Si es con brazo lateral, pregunta el material del brazo",
                "condition_field_key": "tipo_montaje",
                "condition_operator": "equals",
                "condition_value": "Con brazo lateral",
            },
            {
                "field_key": "brazo_tipo",
                "field_label": "Tipo de brazo",
                "field_type": "select",
                "options": ["Artesanal", "Marca comercial"],
                "sort_order": 4,
                "is_required": False,
                "llm_instruction": "Si es con brazo lateral, pregunta si es artesanal o de marca comercial",
                "condition_field_key": "tipo_montaje",
                "condition_operator": "equals",
                "condition_value": "Con brazo lateral",
            },
            {
                "field_key": "brazo_marca",
                "field_label": "Marca del brazo",
                "field_type": "text",
                "sort_order": 5,
                "is_required": False,
                "example_value": "Rizoma",
                "llm_instruction": "Si es de marca comercial, solicita la marca",
                "condition_field_key": "brazo_tipo",
                "condition_operator": "equals",
                "condition_value": "Marca comercial",
            },
"""
    
    # Insertar después de tipo_montaje
    new_fields_section = fields_section[:tipo_match.end()] + new_fields + fields_section[tipo_match.end():]
    
    # Actualizar sort_order de campos existentes posteriores
    reorder_map = {
        "nueva_longitud_mm": 6,
        "distancia_final_mm": 7,
        "matricula_antigua": 8,
        "burlete_goma": 9,
    }
    
    for field_key, new_order in reorder_map.items():
        new_fields_section = re.sub(
            rf'("field_key": "{field_key}".*?"sort_order": )\d+',
            rf'\g<1>{new_order}',
            new_fields_section,
            flags=re.DOTALL
        )
    
    # Reemplazar en content
    new_content = content[:match.start(2)] + new_fields_section + content[match.end(2):]
    
    print(f"   ✓ 4 campos condicionales añadidos a {element_code}")
    return new_content


def add_warning_to_element(content: str, element_code: str, warning_code: str) -> str:
    """Añade un warning a un elemento (o crea el array warnings si no existe)"""
    # Buscar si ya tiene warnings
    element_pattern = rf'("code": "{element_code}",.*?)("warnings": \[)(.*?)(\],)'
    
    match = re.search(element_pattern, content, re.DOTALL)
    
    if match:
        # Ya tiene warnings, añadir al final
        warnings_section = match.group(3)
        new_warnings = warnings_section + warning_code + "\n        "
        new_content = content[:match.start(3)] + new_warnings + content[match.end(3):]
        print(f"   ✓ Warning añadido a {element_code} (ya tenía warnings)")
        return new_content
    else:
        # No tiene warnings, crear el array después de sort_order
        element_pattern_no_warnings = rf'("code": "{element_code}",.*?"sort_order": \d+,)\n'
        match_no_warnings = re.search(element_pattern_no_warnings, content, re.DOTALL)
        
        if not match_no_warnings:
            print(f"   ⚠️  Elemento {element_code} no encontrado")
            return content
        
        new_warnings_block = f"""
        "warnings": [
{warning_code}
        ],
"""
        new_content = content[:match_no_warnings.end()] + new_warnings_block + content[match_no_warnings.end():]
        print(f"   ✓ Warnings creado y añadido a {element_code}")
        return new_content


def add_accesorio_generico(content: str) -> str:
    """Añade el elemento ACCESORIO_GENERICO al final del array ELEMENTS"""
    # Buscar el cierre del array ELEMENTS (último ] antes de CATEGORY_WARNINGS)
    pattern = r'(\],\s*\}\s*\]\s*\n\s*# =+\s*\n\s*# Category-Scoped Warnings)'
    
    match = re.search(pattern, content)
    if not match:
        print(f"   ⚠️  No se encontró el final del array ELEMENTS")
        return content
    
    # Elemento a insertar
    new_element = """    # =========================================================================
    # GRUPO 15: ACCESORIOS GENERICOS
    # =========================================================================
    {
        "code": "ACCESORIO_GENERICO",
        "name": "Accesorio genérico / Otro",
        "description": "Catch-all para accesorios no especificados en otras categorías. Definir accesorio y aportar marca y fotos.",
        "keywords": [
            "accesorio", "otro", "generico", "otro accesorio",
            "accesorio adicional", "modificacion no listada",
            "otro elemento", "accesorio no especificado"
        ],
        "aliases": ["other", "generic accessory", "other modification"],
        "sort_order": 200,
        "required_fields": [
            {
                "field_key": "descripcion_accesorio",
                "field_label": "Descripción del accesorio",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "Protector de tanque de fibra de carbono",
                "llm_instruction": "Solicita una descripción detallada del accesorio que se quiere homologar",
            },
            {
                "field_key": "marca",
                "field_label": "Marca",
                "field_type": "text",
                "sort_order": 2,
                "is_required": False,
                "example_value": "Puig",
                "llm_instruction": "Solicita la marca del accesorio si la tiene",
            },
            {
                "field_key": "material",
                "field_label": "Material",
                "field_type": "text",
                "sort_order": 3,
                "is_required": False,
                "example_value": "Fibra de carbono",
                "llm_instruction": "Pregunta de qué material está hecho el accesorio",
            },
        ],
    },
"""
    
    # Insertar antes del cierre
    # Buscar la posición correcta (después del último }, antes de ])
    insert_pos = match.start()
    
    # Retroceder hasta encontrar el },
    pos = insert_pos - 1
    while pos > 0 and content[pos:pos+2] != "},":
        pos -= 1
    
    if pos <= 0:
        print(f"   ⚠️  No se pudo encontrar la posición de inserción")
        return content
    
    # Insertar después del },\n
    insert_pos = pos + 3  # Después de },\n
    
    new_content = content[:insert_pos] + "\n" + new_element + content[insert_pos:]
    
    print(f"   ✓ Elemento ACCESORIO_GENERICO añadido")
    return new_content


if __name__ == "__main__":
    main()
