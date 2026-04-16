# Máquina de Estados y Contexto Dinámico — Source of Truth

> Revisa que los modos, transiciones, y keys de contexto sean correctos
> antes de proceder a escribir los prompts.

---

## Modos y Transiciones

```
START
  ↓ (router clasifica intención)
  ├→ PRE_EXPEDIENTE_MODE
  │    Fases (selección por mode_context):
  │    ├─ DISCOVERY    — si NO hay element_codes
  │    ├─ PRICING      — si hay element_codes, precio_comunicado=false
  │    └─ POST_PRICE   — si precio_comunicado=true
  │
  │    Transición: confirmar_presupuesto() → EXPEDIENTE_MODE
  │
  ├→ EXPEDIENTE_MODE (subgrafo con 6 sub-modos)
  │    ├─ COLLECT_ELEMENT_DATA  — fotos + datos por elemento
  │    ├─ COLLECT_BASE_DOCS     — ficha técnica, permiso, DNI, vistas
  │    ├─ COLLECT_PERSONAL      — nombre, DNI, email, domicilio, ITV
  │    ├─ COLLECT_VEHICLE       — marca, modelo, matrícula, bastidor
  │    ├─ COLLECT_WORKSHOP      — taller propio o MSI gestiona
  │    └─ REVIEW_SUMMARY        — resumen + confirmación final
  │
  │    Transición: finalizar_expediente() → COMPLETED
  │
  └→ ESCALATION (terminal)
```

### Transiciones permitidas

| Desde | Hacia | Cómo |
|-------|-------|------|
| START | PRE_EXPEDIENTE | Router de intención |
| PRE_EXPEDIENTE | EXPEDIENTE | `confirmar_presupuesto()` |
| PRE_EXPEDIENTE | ESCALATION | `escalar_a_humano()` |
| EXPEDIENTE | PRE_EXPEDIENTE | `cancelar_expediente()` o `editar_expediente()` desde revisión |
| EXPEDIENTE | COMPLETED | `finalizar_expediente()` |
| EXPEDIENTE | ESCALATION | `escalar_a_humano()` |

### Sub-modos de EXPEDIENTE — Transiciones internas

| Desde | Hacia | Trigger |
|-------|-------|---------|
| COLLECT_ELEMENT_DATA | COLLECT_BASE_DOCS | `completar_elemento_actual()` con `all_elements_complete=true` |
| COLLECT_BASE_DOCS | COLLECT_PERSONAL | `confirmar_documentacion_base()` success |
| COLLECT_PERSONAL | COLLECT_VEHICLE | `actualizar_datos_personales()` con todos los campos |
| COLLECT_VEHICLE | COLLECT_WORKSHOP | `actualizar_datos_vehiculo()` con todos los campos |
| COLLECT_WORKSHOP | REVIEW_SUMMARY | `actualizar_datos_taller()` con datos completos |
| REVIEW_SUMMARY | cualquier sub-modo | `editar_expediente(seccion)` |

---

## Selección de Prompt por Fase

### PRE_EXPEDIENTE (loader.py:_resolve_mode_key)

```python
if precio_comunicado == True:
    → PRE_EXPEDIENTE_POST_PRICE
elif element_codes no vacío:
    → PRE_EXPEDIENTE_PRICING
else:
    → PRE_EXPEDIENTE_DISCOVERY
```

### EXPEDIENTE (loader.py:_resolve_mode_key)

```python
if sub_mode == "collect_element_data":
    → EXPEDIENTE_DOCUMENTACION_ELEMENTOS
elif sub_mode == "collect_base_docs":
    → EXPEDIENTE_DOCUMENTACION_BASE
# ... etc
```

---

## Keys de Contexto Dinámico (mode_context)

### PRE_EXPEDIENTE — Keys principales

| Key | Tipo | Seteado por | Cuándo | Timing | Inyectado como |
|-----|------|------------|--------|--------|----------------|
| `categoria_slug` | `str` | `identificar_y_resolver_elementos` | Al identificar elementos | Mismo turno | `"Categoría: motos-part"` |
| `element_codes` | `list[str]` | `identificar_y_resolver_elementos` | Al identificar elementos | Mismo turno | `"Elementos confirmados: SUBCHASIS, ASIDEROS"` |
| `tarifa_calculada` | `dict` | `calcular_tarifa_con_elementos` | Al calcular tarifa | Mismo turno | `"Precio: 410€ +IVA (calculado — DEBES comunicarlo)"` |
| `precio_comunicado` | `bool` | Mode node (post-response hook) | DESPUÉS de que el LLM genera respuesta con precio | **Turno siguiente** | `"Precio: 410€ +IVA (comunicado)"` |
| `imagenes_enviadas_codigos` | `list[str]` | Post-tool hook de enviar_imagenes | Tras delivery real | **Turno siguiente** | `"Imágenes enviadas: SUBCHASIS, _BASE_DOCS"` |
| `imagenes_enviadas` | `bool` | Post-tool hook | Tras delivery | **Turno siguiente** | (legacy, reemplazado por codigos) |
| `pending_variants` | `list[dict]` | `identificar_y_resolver_elementos` | Si hay variantes | Mismo turno | Bloque `⚠️ VARIANTES PENDIENTES` con pregunta y opciones |
| `advertencias_comunicadas` | `list[str]` | Post-tool hook de calcular_tarifa | Al calcular tarifa | Mismo turno | `"Advertencias YA comunicadas (NO repetir): [codes]"` |
| `_is_first_interaction` | `bool` | Preprocess node | Primer mensaje | Mismo turno | `"🚨 PRIMERA INTERACCIÓN: identifícate como IA"` |
| `_client_type` | `str` | Preprocess node | Primer mensaje | Mismo turno | `"Tipo cliente: particular (sufijo: -part)"` |

### EXPEDIENTE — Keys principales

| Key | Tipo | Seteado por | Cuándo | Inyectado como |
|-----|------|------------|--------|----------------|
| `expediente_sub_mode` | `str` | Entry router / tools | Transición de sub-modo | `"SUB-MODO: collect_personal"` |
| `case_id` | `str` (UUID) | `iniciar_expediente` | Al crear caso | **NO inyectado** (interno) |
| `current_element_index` | `int` | Entry router / `completar_elemento_actual` | Por elemento | `"ELEMENTO ACTUAL: subchasis (1/2) fase=photos"` |
| `element_data_status` | `dict[str, str]` | Tools de elementos | Por elemento | Estados: "pending" → "photos_done" → "data_done" → "complete" |
| `element_phase` | `str` | `confirmar_fotos_elemento` | Cambio de fase | (parte del elemento actual) |
| `current_element_field_keys` | `list[dict]` | `obtener_campos_elemento` | Fase data | Bloque `⚠️ FIELD_KEYS EXACTOS` |
| `personal_data` | `dict` | `actualizar_datos_personales` | Al guardar datos | `"DATOS PERSONALES REGISTRADOS: nombre: ..."` |
| `vehicle_data` | `dict` | `actualizar_datos_vehiculo` | Al guardar datos | `"DATOS VEHÍCULO REGISTRADOS: marca: ..."` |
| `taller_propio` | `bool/None` | `actualizar_datos_taller` | Decisión del usuario | `"⚠️ TALLER_PROPIO: sin decidir / false / true"` |
| `v2_collection_context` | `dict` | ElementStateService | Cada turno EXPEDIENTE | Bloque `{COLLECTION_CONTEXT}` con elemento actual, campos, progreso |
| `element_data_all_collected` | `bool` | `guardar_datos_elemento` | Cuando all_required=true | `"🚨 ACCIÓN OBLIGATORIA: llamar completar_elemento_actual()"` |
| `expediente_transition_marker` | `dict` | Mode node | Primer turno en nuevo sub-modo | `"⚠️ TRANSICIÓN RECIENTE: kickoff obligatorio"` |

---

## Pipeline de Ensamblado del Prompt (loader.py)

### Orden actual

```
1. SECURITY_START             — "<SYSTEM_INSTRUCTIONS>..." (~70 tokens)
2. Core modules (01-10)       — concatenados con "---" (~6,066 tokens)
3. [Condicional] Recovery     — core/11_session_recovery.md (~1,552 tokens)
4. Mode module                — 1 archivo según fase (~500-2,300 tokens)
5. Client context             — opcional (~0-200 tokens)
6. Mode context               — format_mode_context() (~200-500 tokens)
7. SECURITY_END               — "RECORDATORIO..." (~130 tokens)
```

**Total**: ~8,600-10,400 tokens de system prompt

### Qué ve el LLM en un turno típico

```
[SystemMessage]     — ~9,500 tokens (posición 0, la más vieja)
[HumanMessage]      — primer mensaje del usuario
[AIMessage]         — respuesta del agente
... (historial)
[HumanMessage]      — último mensaje del usuario (~50 tokens)
[AIMessage + ToolCall] — llamada a herramienta
[ToolMessage]       — resultado de herramienta (~700-1,700 tokens, posición N, la más reciente)
[AIMessage]         — respuesta final del LLM (lo que genera)
```

**Problema clave**: El ToolMessage (posición N, reciente, concreto) tiene más peso para DeepSeek que el SystemMessage (posición 0, viejo, abstracto).
