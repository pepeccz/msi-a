# Plan: Categoría Autocaravanas Particulares (aseicars-part)

## Status: Proposed
## Date: 2026-02-16
## Priority: HIGH

---

## Resumen Ejecutivo

Crear la categoría `aseicars-part` (Autocaravanas para Particulares) basada en el PDF "2026 TARIFAS USUARIOS FINALES REGULARIZACIÓN ELEMENTOS AUTOCARAVANAS". Esta categoría complementa la ya existente `aseicars-prof` (Profesionales) con precios y elementos adaptados al usuario final.

Adicionalmente, se retroaplican 11 elementos nuevos a `aseicars-prof` que existían como texto en las condiciones de tiers pero NO tenían `Element` correspondiente en la base de datos (gap detectado durante el análisis).

**Fuente de datos**: `datos/tarifas/2026 TARIFAS USUARIOS FINALES REGULARIZACION ELEMENTOS AUTOCARAVANAS (1).pdf`

---

## Servicios Afectados

- [x] Database (seeds + datos)
- [ ] API (no requiere cambios — los seeders y rutas son genéricos por categoría)
- [ ] Agent (no requiere cambios — tools operan por `category_slug` dinámicamente)
- [ ] Admin (no requiere cambios — panel ya muestra todas las categorías)
- [ ] Shared (no requiere cambios)

> **Nota**: La arquitectura de MSI-a está diseñada para que añadir nuevas categorías sea 100% data-driven. Los seeders, API routes, agent tools y admin panel ya soportan múltiples categorías sin cambios de código.

---

## Datos Extraídos del PDF

### Precios por Tier

| Tier | Nombre | Prof (actual) | **Particular (PDF)** | Δ |
|------|--------|:---:|:---:|:---:|
| T1 | Proyecto Completo | 270€ | **300€** | +30€ |
| T2 | Proyecto Medio | 230€ | **265€** | +35€ |
| T3 | Proyecto Básico | 180€ | **225€** | +45€ |
| T4 | Regularización varios | 135€ | **195€** | +60€ |
| T5 | Hasta 3 elementos | 65€ | **145€** | +80€ |
| T6 | 1 elemento | 59€ | **75€** | +16€ |

### Elementos Nuevos (no existentes en aseicars-prof)

| # | Código | Nombre | Tier | Variantes | Warnings |
|---|--------|--------|:----:|:---------:|----------|
| 1 | `MOBILIARIO_INT` | Modificación del mobiliario interior | T3 | NO | — |
| 2 | `ELECTRICOS_INT` | Elementos eléctricos interiores | T3 | NO | Requiere boletín eléctrico |
| 3 | `LLANTAS_ALETINES` | Llantas con aletines | T3 | NO | — |
| 4 | `TOMA_GAS_EXT` | Toma de gas exterior | T3 | NO | — |
| 5 | `LUCES_CORTESIA_EXT` | Luces de cortesía exterior | T3 | NO | — |
| 6 | `CAMBIO_CLASIF` | Cambio de clasificación | T3 | **SÍ** (2) | Sin contraseña: +100€ consulta |
| 7 | `NEUMATICOS_NO_EQUIV` | Neumáticos no equivalentes | T4 | NO | Sin ensayo, sin aletines |
| 8 | `GALIBOS` | Instalación/reubicación de gálibos | T4 | NO | — |
| 9 | `LUCES_ADICIONALES` | Luces adicionales homologadas | T4 | NO | No de cortesía |
| 10 | `TOMAS_EXT_GAS_DUCHA` | Tomas externas gas/ducha | T4 | NO | Excepto paragolpes delantero |

#### Variantes de CAMBIO_CLASIF

| Código | Nombre | variant_type | variant_code | Warning |
|--------|--------|:---:|:---:|---------|
| `CAMBIO_CLASIF_CON` | Con contraseña de homologación | `contrasena_option` | `CON_CONTRASENA` | — |
| `CAMBIO_CLASIF_SIN` | Sin contraseña de homologación | `contrasena_option` | `SIN_CONTRASENA` | +100€ previo consulta |

### Servicios Adicionales (Particulares)

| Código | Nombre | Precio |
|--------|--------|:------:|
| `cert_taller_aseicars_part` | Certificado taller (no autorizado) | 75€ |
| `cert_electrico_aseicars_part` | Certificado eléctrico 12v/230v | 75€ |
| `cert_gas_aseicars_part` | Certificado gas | 75€ |
| `plus_lab_simple_aseicars_part` | Plus laboratorio (sin proyecto) | 25€ |
| `plus_lab_complejo_aseicars_part` | Plus laboratorio (con proyecto) | 75€ |
| `ayuda_digital_aseicars_part` | Ayuda digital (por hora) | 20€ |
| `redaccion_cert_taller_aseicars_part` | Redacción certificado taller | 10€ |

### Diferencias con aseicars-prof

| Aspecto | aseicars-prof | aseicars-part |
|---------|:---:|:---:|
| **Precios** | 59€ - 270€ | 75€ - 300€ |
| **Elementos** | ~33 | ~47 (33 + 11 nuevos + 3 variantes) |
| **Servicios** | 4 | 7 |
| **AIRE_ACONDI** | `is_active: False` | `is_active: True` (con warning boletín) |
| **CLARABOYA keywords** | claraboya, ventana techo | + ventana, ventanas, portón, portones |

---

## Tareas por Servicio

### Database → database-dev

#### Tarea 1: Crear archivo `database/seeds/data/aseicars_part.py`

**Nuevo archivo** (~1100 líneas estimadas). Contiene:

- `CATEGORY_SLUG = "aseicars-part"`
- `CATEGORY: CategoryData` — slug, nombre, description, icon="caravan", client_type="particular", sort_order=2
- `TIERS: list[TierData]` — 6 tiers con precios de particulares (300€, 265€, 225€, 195€, 145€, 75€)
- `ELEMENTS: list[ElementData]` — TODOS los elementos:
  - 20 elementos base copiados de prof (ESCALON_ELEC, TOLDO_LAT, PLACA_SOLAR, ANTENA_PAR, PORTABICIS, CLARABOYA con keywords expandidos, BACA_TECHO, BOLA_REMOLQUE, NEVERA_COMPRESOR, DEPOSITO_AGUA, AIRE_ACONDI con is_active=True, PORTAMOTOS, SUSP_NEUM, KIT_ESTAB, AUMENTO_MMTA, GLP_INSTALACION, AUMENTO_PLAZAS, CIERRES_EXT, FAROS_LA, DEFENSAS_DEL)
  - 14 variantes copiadas de prof (TOLDO_SIMPLE, TOLDO_GALIBO, PLACA_SOLAR_SIMPLE, PLACA_SOLAR_MALETERO, BOLA_SIN_MMR, BOLA_CON_MMR, BRAZO_PORTA, SUSP_NEUM_EST, SUSP_NEUM_FULL, GLP_KIT_BOMB, GLP_DEPOSITO, GLP_DUOCONTROL, FAROS_LA_2F, FAROS_LA_1D)
  - 10 elementos nuevos standalone (MOBILIARIO_INT, ELECTRICOS_INT, LLANTAS_ALETINES, TOMA_GAS_EXT, LUCES_CORTESIA_EXT, NEUMATICOS_NO_EQUIV, GALIBOS, LUCES_ADICIONALES, TOMAS_EXT_GAS_DUCHA, CAMBIO_CLASIF base)
  - 2 variantes nuevas (CAMBIO_CLASIF_CON, CAMBIO_CLASIF_SIN)
- `CATEGORY_WARNINGS: list[WarningData]` — warnings de categoría (adaptar de prof + nuevos para elementos nuevos)
- `ADDITIONAL_SERVICES: list[AdditionalServiceData]` — 7 servicios
- `BASE_DOCUMENTATION: list[BaseDocumentationData]` — misma que prof (ficha técnica + fotos vehículo)
- `PROMPT_SECTIONS: list[PromptSectionData]` — recognition_table y special_cases actualizados con elementos nuevos

**IMPORTANTE**: Cada elemento tiene su propio `category_slug` en el UUID determinístico. Los elementos con el mismo `code` pero diferente categoría generan UUIDs DIFERENTES. Esto es correcto — cada categoría tiene sus propias instancias de elementos.

**Cambios específicos respecto a prof**:
- `CLARABOYA`: Expandir keywords con `["ventana", "ventanas", "porton", "portones", "sustitucion ventanas", "incorporacion ventanas"]`
- `AIRE_ACONDI`: Cambiar `is_active: True` y añadir warning de boletín eléctrico
- Todos los precios de tiers ajustados a particulares

#### Tarea 2: Modificar `database/seeds/data/aseicars_prof.py`

**Añadir los 11 elementos nuevos + 2 variantes** al archivo existente (mismos códigos, mismas keywords, mismo tier level). Esto cierra el gap detectado donde los tiers referenciaban elementos que no existían como `Element`.

Elementos a añadir:
- `MOBILIARIO_INT` (sort_order: 210)
- `ELECTRICOS_INT` (sort_order: 220) con warning de boletín eléctrico
- `LLANTAS_ALETINES` (sort_order: 230)
- `TOMA_GAS_EXT` (sort_order: 240)
- `LUCES_CORTESIA_EXT` (sort_order: 250)
- `CAMBIO_CLASIF` (sort_order: 260, is_base: True)
- `CAMBIO_CLASIF_CON` (sort_order: 261, variante)
- `CAMBIO_CLASIF_SIN` (sort_order: 262, variante con warning +100€)
- `NEUMATICOS_NO_EQUIV` (sort_order: 270)
- `GALIBOS` (sort_order: 280)
- `LUCES_ADICIONALES` (sort_order: 290)
- `TOMAS_EXT_GAS_DUCHA` (sort_order: 300)

#### Tarea 3: Modificar `database/seeds/data/tier_mappings.py`

Añadir:

1. **`ASEICARS_PART_MAPPINGS`** — Nuevo diccionario con:
   - `T6_ELEMENTS`: mismos que prof + fix de código (usar `PLACA_SOLAR` en vez de `PLACA_200W`)
   - `T5_ELEMENTS`: reference a T6 
   - `T4_ELEMENTS`: mismos que prof + NEUMATICOS_NO_EQUIV, GALIBOS, LUCES_ADICIONALES, TOMAS_EXT_GAS_DUCHA
   - `T3_ELEMENTS`: mismos que prof + MOBILIARIO_INT, ELECTRICOS_INT, LLANTAS_ALETINES, TOMA_GAS_EXT, LUCES_CORTESIA_EXT, CAMBIO_CLASIF, CAMBIO_CLASIF_CON, CAMBIO_CLASIF_SIN
   - `T2_ELEMENTS` y `T1_ELEMENTS`: mismos que prof
   - `TIER_CONFIGS`: misma estructura pero con precios de particulares

2. **Actualizar `ASEICARS_PROF_MAPPINGS`** para:
   - Corregir `PLACA_200W` → `PLACA_SOLAR` (o las variantes que correspondan)
   - Corregir `ESC_MEC` → `ESCALON_ELEC`
   - Añadir los 11 elementos nuevos en sus tiers correspondientes

3. **Actualizar `get_tier_mapping()`** para incluir `"aseicars-part"`

4. **Actualizar `get_element_tier_level()`** para incluir `"aseicars-part"`

#### Tarea 4: Modificar `database/seeds/seeders/inclusion.py`

Añadir método `_seed_aseicars_part_inclusions()` para la nueva categoría. Puede reutilizar la lógica de `_seed_aseicars_inclusions()` con las adaptaciones:
- Misma estructura T6→T1 con herencia
- Incluye los elementos nuevos en sus tiers correspondientes
- Los T3 nuevos (MOBILIARIO_INT, etc.) con max_qty apropiado
- Los T4 nuevos (NEUMATICOS_NO_EQUIV, etc.) sin límite

Actualizar `seed()` method para reconocer `"aseicars-part"`.

**ALTERNATIVA RECOMENDADA**: Refactorizar para usar un método genérico `_seed_aseicars_inclusions()` parametrizado que sirva para AMBAS categorías (prof y part), dado que la estructura de tier-element es idéntica excepto por los elementos adicionales.

#### Tarea 5: Modificar `database/seeds/data/__init__.py`

- Importar `aseicars_part`
- Añadir a `__all__`

#### Tarea 6: Modificar `database/seeds/run_all_seeds.py`

- Importar `aseicars_part` de `database.seeds.data`
- Añadir paso de seed: `[3/4] Seeding aseicars-part (Autocaravanas Particular)...`
- Actualizar summary

#### Tarea 7: NO se necesita migración Alembic

Las tablas ya soportan múltiples categorías (la migración 013 `separate_categories_by_type` ya preparó el esquema). Los seeds crean los datos. No hay cambios de esquema necesarios.

---

## Dependencias entre Tareas

```
Tarea 5 (data/__init__.py)     ──┐
Tarea 1 (aseicars_part.py)     ──┤
Tarea 2 (aseicars_prof.py)     ──┼──→ Tarea 6 (run_all_seeds.py) → Ejecutar seeds
Tarea 3 (tier_mappings.py)     ──┤
Tarea 4 (inclusion.py)         ──┘
```

Todas las tareas 1-5 son independientes entre sí y pueden desarrollarse en paralelo. La tarea 6 depende de todas las anteriores. No hay orden estricto dentro de 1-5.

---

## Detalle de Elementos por Tier (aseicars-part)

### T6 (75€) — 1 elemento sin proyecto
- PLACA_SOLAR (variantes: SIMPLE/MALETERO)
- TOLDO_LAT (variantes: SIMPLE/GALIBO)
- ANTENA_PAR

### T5 (145€) — Hasta 3 elementos
- Todos los T6 (max 3)
- PLACA_SOLAR_MALETERO (con boletín BT)

### T4 (195€) — Regularización varios sin proyecto
- Todos los T6 + T5 (sin límite)
- CLARABOYA (expandido: ventanas/portones)
- BOLA_REMOLQUE / BOLA_SIN_MMR
- AIRE_ACONDI (con boletín eléctrico)
- PORTABICIS
- **NEUMATICOS_NO_EQUIV** (nuevo)
- **GALIBOS** (nuevo)
- **LUCES_ADICIONALES** (nuevo)
- **TOMAS_EXT_GAS_DUCHA** (nuevo)

### T3 (225€) — Proyecto básico
- Todos los T4 + T6
- NEVERA_COMPRESOR
- DEPOSITO_AGUA
- ESCALON_ELEC (con boletín)
- CIERRES_EXT
- **MOBILIARIO_INT** (nuevo)
- **ELECTRICOS_INT** (nuevo, con boletín)
- **LLANTAS_ALETINES** (nuevo)
- **TOMA_GAS_EXT** (nuevo)
- **LUCES_CORTESIA_EXT** (nuevo)
- **CAMBIO_CLASIF** (nuevo, variantes CON/SIN contraseña)

### T2 (265€) — Proyecto medio
- Todos los T3 + T4 + T6
- BOLA_CON_MMR / BRAZO_PORTA
- PORTAMOTOS
- BACA_TECHO
- SUSP_NEUM (variantes: EST/FULL)
- KIT_ESTAB
- FAROS_LA (variantes: 2F/1D)
- DEFENSAS_DEL

### T1 (300€) — Proyecto completo
- Todos los T2 + T3 + T4 + T5 + T6 (sin límite)
- AUMENTO_MMTA (+300€ sin ensayo / +500€ con ensayo)
- GLP_INSTALACION (variantes: KIT_BOMB/DEPOSITO/DUOCONTROL)
- AUMENTO_PLAZAS (+115€ previo consulta)

---

## Tests Requeridos

### Unit Tests → qa-dev

- [ ] **test_aseicars_part_seed_data_integrity**: Validar que `aseicars_part.py` tiene todos los campos requeridos (TypedDict compliance)
- [ ] **test_aseicars_part_element_codes_unique**: Todos los element codes son únicos dentro de la categoría
- [ ] **test_aseicars_part_variant_parents_exist**: Todos los `parent_code` referencian elementos que existen en ELEMENTS
- [ ] **test_aseicars_part_tier_mapping_codes_match**: Todos los códigos en `ASEICARS_PART_MAPPINGS` corresponden a elementos que existen
- [ ] **test_aseicars_prof_tier_mapping_codes_fixed**: Verificar que `PLACA_200W`→`PLACA_SOLAR` y `ESC_MEC`→`ESCALON_ELEC` están corregidos
- [ ] **test_deterministic_uuids_no_collision**: Verificar que UUIDs de `aseicars-part` no colisionan con `aseicars-prof`
- [ ] **test_seed_execution_idempotent**: Ejecutar seeds 2 veces y verificar mismos resultados (no duplicados)

### Integration Tests → qa-dev

- [ ] **test_full_seed_pipeline**: Ejecutar `run_all_seeds` completo y verificar:
  - 3 categorías creadas (motos-part, aseicars-prof, aseicars-part)
  - Conteo correcto de elementos por categoría
  - Dual warning system sincronizado
  - Tier-element inclusions correctas
- [ ] **test_aseicars_prof_new_elements**: Verificar que los 11 elementos nuevos existen en aseicars-prof
- [ ] **test_element_tier_level_function**: Verificar `get_element_tier_level("aseicars-part", code)` retorna tier correcto para cada elemento

### Validación Manual → qa-dev

- [ ] Ejecutar `python -m database.seeds.validate_elements_seed` → sin errores
- [ ] Ejecutar `python -m database.seeds.verify_warning_sync` → counts match

---

## Criterios de Aceptación

- [ ] `aseicars-part` aparece como categoría en la DB con `client_type="particular"`
- [ ] 6 tiers creados con precios correctos (300, 265, 225, 195, 145, 75)
- [ ] ~47 elementos creados con keywords, aliases, images, warnings
- [ ] `CAMBIO_CLASIF` tiene 2 variantes con question_hint correcto
- [ ] `CLARABOYA` tiene keywords expandidos (ventana, portón)
- [ ] `AIRE_ACONDI` está `is_active=True` en aseicars-part
- [ ] 7 servicios adicionales creados con precios correctos
- [ ] Dual warning system sincronizado (inline + associations)
- [ ] Tier-element inclusions correctas (T6→T1 hierarchy)
- [ ] `aseicars-prof` tiene los 11+2 elementos nuevos añadidos
- [ ] `tier_mappings.py` corregido: `PLACA_200W`→códigos correctos, `ESC_MEC`→`ESCALON_ELEC`
- [ ] Seeds son idempotentes (ejecutar 2x = mismo resultado)
- [ ] Prompt sections actualizadas con recognition_table y special_cases
- [ ] `get_tier_mapping("aseicars-part")` funciona correctamente
- [ ] `get_element_tier_level("aseicars-part", "MOBILIARIO_INT")` retorna "T3"

---

## Checklist de Verificación Pre-Deploy

- [ ] Seeds ejecutadas sin errores en staging
- [ ] `validate_elements_seed.py` pasa sin errores
- [ ] `verify_warning_sync.py` muestra counts sincronizados
- [ ] Seeds idempotentes verificadas (2 ejecuciones)
- [ ] Admin panel muestra nueva categoría con todos sus datos
- [ ] Agent tools responden a `category_slug="aseicars-part"` correctamente
- [ ] No hay regresión en `motos-part` ni `aseicars-prof`

---

## Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|:---:|:---:|------------|
| Colisión de UUIDs entre categorías | Muy baja | Alto | UUIDs son `category_slug`-scoped: `element:aseicars-part:ESCAPE` ≠ `element:aseicars-prof:ESCAPE` |
| Tier mappings inconsistentes | Media | Medio | Tests automatizados verifican que todos los códigos en mappings existen como elementos |
| Bug existente `PLACA_200W`/`ESC_MEC` | Confirmado | Medio | Se corrige en esta misma tarea |
| Regresión en seeds existentes | Baja | Alto | Ejecutar full seed pipeline test antes y después |
| Datos del PDF ambiguos | Baja | Bajo | Todas las decisiones documentadas y validadas con el usuario |

---

## Estimación de Esfuerzo

| Tarea | Líneas estimadas | Complejidad | Tiempo |
|-------|:---:|:---:|:---:|
| T1: aseicars_part.py | ~1100 | Media (copiar + adaptar) | 45 min |
| T2: aseicars_prof.py modificación | ~200 | Baja (añadir elementos) | 15 min |
| T3: tier_mappings.py | ~120 | Media (nuevos mappings + fixes) | 20 min |
| T4: inclusion.py | ~80 | Media (nuevo método o refactor) | 15 min |
| T5-T6: __init__.py + run_all_seeds.py | ~15 | Baja | 5 min |
| Tests | ~200 | Media | 30 min |
| **Total** | **~1715** | | **~2h 10min** |

---

## Orden de Ejecución Recomendado

1. **database-dev**: Tareas 1-6 (en paralelo donde sea posible)
2. **qa-dev**: Tests unitarios + integración + validación manual
3. **Usuario**: Verificación visual en admin panel
4. **deploy-dev**: Ejecutar seeds en producción (con confirmación)

---

## Archivos Afectados (Resumen)

| Archivo | Acción | Líneas Δ |
|---------|:------:|:--------:|
| `database/seeds/data/aseicars_part.py` | **CREAR** | +1100 |
| `database/seeds/data/aseicars_prof.py` | MODIFICAR | +200 |
| `database/seeds/data/tier_mappings.py` | MODIFICAR | +120 |
| `database/seeds/data/__init__.py` | MODIFICAR | +3 |
| `database/seeds/seeders/inclusion.py` | MODIFICAR | +80 |
| `database/seeds/run_all_seeds.py` | MODIFICAR | +15 |
| `tests/test_aseicars_part_seeds.py` | **CREAR** | +200 |
| **Total** | | **+1718** |

---

**Creado por**: Architect Agent  
**Fecha**: 16 de Febrero de 2026  
**Fuente**: PDF "2026 TARIFAS USUARIOS FINALES REGULARIZACIÓN ELEMENTOS AUTOCARAVANAS"  
**Aprobado por**: Pendiente
