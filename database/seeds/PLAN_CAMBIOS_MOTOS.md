# PLAN COMPLETO DE REESTRUCTURACIÓN - MOTOS-PART SEEDS

## ✅ CAMBIOS YA APLICADOS

### 1. Nodo padre FRENADO creado
- ✅ Creado elemento base `FRENADO` con `is_base=True`
- ✅ Añadido `parent_code="FRENADO"` a los 5 hijos:
  - `FRENADO_DISCOS` (variant_code="DISCOS")
  - `FRENADO_PINZAS` (variant_code="PINZAS")
  - `FRENADO_BOMBAS` (variant_code="BOMBAS")
  - `FRENADO_LATIGUILLOS` (variant_code="LATIGUILLOS")
  - `FRENADO_DEPOSITO` (variant_code="DEPOSITO")
- ✅ Keywords limpiados: marcas movidas al padre, hijos solo tienen keywords específicos
- ✅ Warning añadido a `FRENADO_LATIGUILLOS`

### 2. Nodo padre CARROCERIA_EXT creado
- ✅ Creado elemento base `CARROCERIA_EXT` con `is_base=True`
- ✅ Añadido `parent_code="CARROCERIA_EXT"` a los 4 hijos:
  - `CARENADO` (variant_code="CARENADO")
  - `GUARDABARROS_DEL` (variant_code="GUARDA_DEL")
  - `GUARDABARROS_TRAS` (variant_code="GUARDA_TRAS")
  - `CARROCERIA` (variant_code="OTRAS")
- ✅ Keywords limpiados: genéricos movidos al padre

### 3. Keywords limpiados en SUSPENSION
- ✅ Padre `SUSPENSION`: mantiene marcas (ohlins, showa, etc.)
- ✅ `SUSPENSION_TRAS`: removidos genéricos "trasera", "detras", "posterior"

### 4. Required fields completados
- ✅ `ESPEJOS`: añadido campo `distancia_centros_mm`
- ✅ `MANILLAR`: añadido campo `tipo` (Manillar completo / Semimanillares)

---

## 🔨 CAMBIOS PENDIENTES

### GRUPO A: Required Fields Faltantes

#### 1. INTERMITENTES_DEL (línea ~1329)
**Añadir campo:**
```python
{
    "field_key": "altura_mm",
    "field_label": "Altura desde el suelo (mm)",
    "field_type": "number",
    "sort_order": 4,  # después de distancia_faro_mm
    "example_value": "500",
    "llm_instruction": "Solicita la altura del intermitente delantero desde el suelo en milímetros",
    "validation_rules": {"min_value": 250, "max_value": 1200},
}
```

#### 2. INTERMITENTES_TRAS (línea ~1381)
**Añadir campo:**
```python
{
    "field_key": "altura_mm",
    "field_label": "Altura desde el suelo (mm)",
    "field_type": "number",
    "sort_order": 5,  # después de integra_luz_freno
    "example_value": "600",
    "llm_instruction": "Solicita la altura del intermitente trasero desde el suelo en milímetros",
    "validation_rules": {"min_value": 250, "max_value": 1200},
}
```

#### 3. PILOTO_FRENO (línea ~1441)
**Añadir campo ANTES de contrasena_homologacion:**
```python
{
    "field_key": "marca",
    "field_label": "Marca o Referencia",
    "field_type": "text",
    "sort_order": 1,
    "example_value": "Puig",
    "llm_instruction": "Solicita la marca o referencia del piloto de freno",
}
```
**Y actualizar sort_order de los demás campos** (contrasena_homologacion → 2, altura_mm → 3, integra_intermitentes → 4)

#### 4. LUZ_MATRICULA (línea ~1490)
**Añadir campo ANTES de contrasena_homologacion:**
```python
{
    "field_key": "marca",
    "field_label": "Marca o Referencia",
    "field_type": "text",
    "sort_order": 1,
    "example_value": "Puig",
    "llm_instruction": "Solicita la marca o referencia de la luz de matrícula",
}
```
**Y actualizar sort_order** (contrasena_homologacion → 2, altura_mm → 3, posicion → 4)

#### 5. CATADIOPTRICO (línea ~1533)
**Añadir campo ANTES de contrasena_homologacion:**
```python
{
    "field_key": "marca",
    "field_label": "Marca o Referencia",
    "field_type": "text",
    "sort_order": 1,
    "example_value": "OEM",
    "llm_instruction": "Solicita la marca o referencia del catadióptrico",
}
```
**Y actualizar sort_order** (contrasena_homologacion → 2, altura_mm → 3, perpendicular → 4)

#### 6. ANTINIEBLAS (línea ~1582)
**Añadir campo ANTES de contrasena_homologacion:**
```python
{
    "field_key": "marca",
    "field_label": "Marca",
    "field_type": "text",
    "sort_order": 1,
    "example_value": "Hella",
    "llm_instruction": "Solicita la marca de las luces antiniebla",
}
```
**Y actualizar sort_order** (contrasena_homologacion → 2, tiene_pictograma → 3)

#### 7. MANDOS_AVANZADOS (línea ~1226)
**REEMPLAZAR todos los required_fields actuales con:**
```python
"required_fields": [
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
]
```

#### 8. MATRICULA (línea ~2034)
**Añadir 3 campos condicionales después de tipo_montaje:**
```python
{
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
```
**Y actualizar sort_order de los demás campos** (nueva_longitud_mm → 6, distancia_final_mm → 7, matricula_antigua → 8, burlete_goma → 9)

#### 9. VELOCIMETRO (línea ~1960)
**Añadir campo condicional:**
```python
{
    "field_key": "ubicacion_captador_nuevo",
    "field_label": "Ubicación del nuevo captador",
    "field_type": "text",
    "sort_order": 7,  # después de captador
    "is_required": False,
    "example_value": "Rueda delantera eje derecho",
    "llm_instruction": "Si se instala captador nuevo, describe dónde se ubica exactamente",
    "condition_field_key": "captador",
    "condition_operator": "equals",
    "condition_value": "Nuevo captador",
}
```

#### 10. LLANTAS (línea ~1742)
**Añadir campo al inicio:**
```python
{
    "field_key": "posicion",
    "field_label": "Posición",
    "field_type": "select",
    "options": ["Delantera", "Trasera", "Ambas"],
    "sort_order": 1,
    "llm_instruction": "Pregunta si se cambia la llanta delantera, trasera o ambas",
}
```
**Y actualizar sort_order de los demás** (marca → 2, medidas_del → 3, medidas_tras → 4)

---

### GRUPO B: Warnings Faltantes

#### 1. ANTINIEBLAS (línea ~1582)
**Añadir warning adicional:**
```python
{
    "code": "antinieblas_pictograma_obligatorio",
    "message": "Necesario pictograma homologado en el botón de encendido (requisito obligatorio).",
    "severity": "warning",
}
```
(Ya tiene uno, este sería el segundo warning)

#### 2. LLANTAS (línea ~1742)
**Añadir warning:**
```python
{
    "code": "llantas_ensayo_neumatico",
    "message": "Si el neumático delantero supera 10% en diámetro o trasero supera 8%, puede requerir ensayo de frenada (+375 EUR).",
    "severity": "warning",
}
```

---

### GRUPO C: Elemento Nuevo

#### ACCESORIO_GENERICO (insertar al FINAL del array ELEMENTS, antes del cierre ])
```python
    # =========================================================================
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
]  # ← Cierre del array ELEMENTS
```

---

## 📊 RESUMEN DE CAMBIOS PENDIENTES

| Tipo de cambio | Cantidad |
|----------------|----------|
| Required fields a añadir | 10 elementos (~20 campos) |
| Warnings a añadir | 2 elementos |
| Elemento nuevo (ACCESORIO_GENERICO) | 1 |
| **TOTAL DE OPERACIONES** | **13** |

---

## 🔄 PRÓXIMOS PASOS

1. ✅ Revisás este documento
2. ⏳ Creo script Python automatizado que aplique TODOS los cambios
3. ⏳ Actualizo `tier_mappings.py` con los nuevos elementos base
4. ⏳ Creo migración Alembic para BD existente
5. ⏳ Testing completo

---

## ⚠️ NOTAS IMPORTANTES

- Todos los `sort_order` existentes necesitan recalcularse cuando se añaden campos nuevos
- Los campos condicionales DEBEN tener `is_required: False`
- El elemento `ACCESORIO_GENERICO` debe ir en tier_mappings como T4_BASE_ELEMENTS
- La migración Alembic será COMPLEJA porque necesita:
  1. Crear 2 elementos base nuevos (FRENADO, CARROCERIA_EXT)
  2. Actualizar parent_element_id de 9 elementos hijos
  3. Añadir ~20 ElementRequiredField nuevos
  4. Añadir 3 warnings nuevos
  5. Crear 1 elemento nuevo (ACCESORIO_GENERICO)
