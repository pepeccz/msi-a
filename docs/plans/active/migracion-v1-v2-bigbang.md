# Plan de Migración v1.0 → v2.0 (Big Bang)

## 📋 Resumen Ejecutivo

**Estrategia**: Big Bang (eliminación completa de v1.0)  
**Prioridad**: VIABILIDAD_MODE primero (65% tráfico)  
**Metodología**: 6 fases, con Digression Manager desde Fase 1  
**Duración estimada**: 8-10 semanas con IA asistida

---

## 🗑️ ELIMINAR COMPLETAMENTE (Sin Rastro)

### Directorios a Eliminar
```
agent/fsm/                          # FSM lineal completo
agent/prompts/phases/               # Prompts por fases v1
agent/prompts/core/09_fsm_awareness.md  # Referencias a FSM
agent/routing/                      # Placeholder vacío (reemplazado por IntentRouter)
```

### Archivos a Eliminar
```
agent/fsm/case_collection.py        # FSM completo (rediseño total)
agent/fsm/__init__.py
agent/fsm/states.py                 # Si existe
agent/fsm/transitions.py            # Si existe

agent/prompts/phases/idle_quotation.md
agent/prompts/phases/collect_element_data.md
agent/prompts/phases/collect_base_docs.md
agent/prompts/phases/collect_personal.md
agent/prompts/phases/collect_vehicle.md
agent/prompts/phases/collect_workshop.md
agent/prompts/phases/review_summary.md
agent/prompts/phases/completed.md

agent/graphs/conversation_flow.py   # Grafo v1 simple

agent/nodes/conversational_agent.py # Nodo monolítico v1
agent/nodes/process_message.py      # Procesamiento v1

agent/services/prompt_service.py    # Legacy calculator prompt
agent/services/collection_mode.py   # Reciclado a element_collection_service.py

agent/tools/case_tools.py           # Tools v1 (rediseño)
agent/tools/element_data_tools.py   # Rediseño a element_collection_tools.py
agent/tools/tool_manager.py         # Eliminado en 95475b0 — selección por modo en pre_expediente_mode.py y submodos/_shared.py
```

### Funciones a Eliminar (de archivos que reciclamos)

En `agent/prompts/loader.py`:
- `PHASE_MODULES` dict completo
- `get_current_phase()` (usa FSM)
- `load_phase_module()`
- `get_prompt_stats()` (adaptar a modos)

En `agent/tools/element_tools.py`:
- `iniciar_expediente()` (rediseño completo)
- `confirmar_fotos_elemento()` (rediseño)
- `completar_elemento_actual()` (rediseño)

En `agent/tools/tarifa_tools.py`:
- `calcular_tarifa_con_elementos()` → adaptar a nuevo flujo

---

## ♻️ RECICLAR (Adaptar a v2.0)

### Servicios (Reciclar sin cambios de API)
```
agent/services/tarifa_service.py        # Reciclar 100%
agent/services/element_service.py       # Reciclar 100%
agent/services/constraint_service.py    # Reciclar 100%
agent/services/tool_logging_service.py  # Reciclar 100%
agent/services/token_tracking.py        # Reciclar 100%
agent/services/element_required_fields_service.py  # Reciclar lógica
```

### Tools (Reciclar con adaptaciones menores)
```
agent/tools/element_tools.py:
  - identificar_y_resolver_elementos()     # Mantener, adaptar a modo
  - seleccionar_variante_por_respuesta()   # Mantener
  - listar_categorias()                    # Mantener
  - listar_elementos()                     # Mantener
  - buscar_elemento_por_nombre()           # Mantener
  - obtener_elemento_por_codigo()          # Mantener
  - obtener_variantes_de_elemento()        # Mantener

agent/tools/tarifa_tools.py:
  - obtener_tarifas_por_categoria()        # Mantener
  - obtener_servicios_adicionales()        # Mantener
  - obtener_documentacion_elemento()       # Mantener

agent/tools/image_tools.py:
  - enviar_imagenes_ejemplo()              # Mantener
  - get_pending_images_result()            # Mantener (adaptar a modo)

agent/tools/vehicle_tools.py:
  - identificar_tipo_vehiculo()            # Mantener
```

### Utilidades (Reciclar 100%)
```
agent/utils/validation.py               # Reciclar
agent/utils/text_utils.py               # Reciclar
agent/utils/errors.py                   # Reciclar (adaptar a RetryError)
agent/utils/tool_helpers.py             # Reciclar
agent/state/helpers.py                  # Reciclar
agent/state/checkpointer.py             # Reciclar
```

### Prompts Core (Reciclar contenido, nueva estructura)
```
agent/prompts/core/01_security.md       # Reciclar contenido
agent/prompts/core/02_identity.md       # Reciclar contenido
agent/prompts/core/03_format_style.md   # Reciclar contenido
agent/prompts/core/04_anti_patterns.md  # Reciclar contenido
agent/prompts/core/05_tools_efficiency.md  # Reciclar contenido
agent/prompts/core/06_escalation.md     # Reciclar contenido
agent/prompts/core/07_pricing_rules.md  # Reciclar contenido
agent/prompts/core/08_documentation.md  # Reciclar contenido
# ELIMINAR: 09_fsm_awareness.md
```

### Schemas (Extender)
```
agent/state/schemas.py:
  - Agregar ConversationModeV2 TypedDict
  - Agregar RetryState
  - Agregar IntentResult
  - Mantener compatibilidad hacia atrás mientras migramos
```

---

## 🆕 CREAR (Nuevos Componentes v2.0)

### Estructura de Directorios Nueva
```
agent/
├── v2/                                     # NUEVO: Todo v2.0 aquí
│   ├── __init__.py
│   ├── modes/                              # Nodos de modo
│   │   ├── __init__.py
│   │   ├── base_mode.py                    # BaseModeNode con fallback
│   │   ├── consulta_mode.py                # CONSULTA_MODE
│   │   ├── viabilidad_mode.py              # VIABILIDAD_MODE
│   │   ├── presupuesto_mode.py             # PRESUPUESTO_MODE
│   │   ├── evaluacion_gateway.py           # EVALUACION_GATEWAY
│   │   └── expediente_mode.py              # EXPEDIENTE_MODE + submodos
│   │
│   ├── router/                             # Intent routing
│   │   ├── __init__.py
│   │   ├── intent_router.py                # Clasificador de intención
│   │   ├── digression_manager.py           # Option B: Parallel listener
│   │   └── mode_transitions.py             # Reglas de transición
│   │
│   ├── state/                              # State management v2
│   │   ├── __init__.py
│   │   ├── conversation_state_v2.py        # Nuevo schema
│   │   ├── retry_state.py                  # Retry tracking
│   │   └── mode_context.py                 # Contexto por modo
│   │
│   ├── fallback/                           # Fallback handling
│   │   ├── __init__.py
│   │   └── fallback_handler.py             # Centralizado (mover de nodes/)
│   │
│   ├── prompts/                            # NUEVO: prompts por modo
│   │   ├── __init__.py
│   │   ├── loader_v2.py                    # Dynamic loader v2
│   │   ├── core/                           # Reciclado de prompts/core/
│   │   │   ├── 01_security.md              # Copiar contenido
│   │   │   ├── 02_identity.md              # Copiar contenido
│   │   │   ├── 03_format_style.md          # Copiar contenido
│   │   │   ├── 04_anti_patterns.md         # Copiar contenido
│   │   │   ├── 05_tools_efficiency.md      # Copiar contenido
│   │   │   ├── 06_escalation.md            # Copiar contenido
│   │   │   ├── 07_pricing_rules.md         # Copiar contenido
│   │   │   └── 08_documentation.md         # Copiar contenido
│   │   │
│   │   └── modes/                          # NUEVO: prompts por modo
│   │       ├── consulta_mode.md            # 10% tráfico
│   │       ├── viabilidad_mode.md          # 65% tráfico
│   │       ├── presupuesto_mode.md         # 25% tráfico
│   │       ├── evaluacion_gateway.md       # Gateway sí/no
│   │       ├── expediente_datos_personales.md
│   │       ├── expediente_datos_vehiculo.md
│   │       ├── expediente_documentacion.md
│   │       └── expediente_revision.md
│   │
│   ├── tools/                              # Tools específicos por modo
│   │   ├── __init__.py
│   │   ├── consulta_tools.py               # Tools para CONSULTA_MODE
│   │   ├── viabilidad_tools.py             # Tools para VIABILIDAD_MODE
│   │   ├── presupuesto_tools.py            # Tools para PRESUPUESTO_MODE
│   │   ├── expediente_tools.py             # Tools para EXPEDIENTE_MODE
│   │   └── shared_tools.py                 # Tools universales
│   │
│   ├── graph/                              # Grafo v2.0
│   │   ├── __init__.py
│   │   └── conversation_graph_v2.py        # StateGraph v2
│   │
│   └── main_v2.py                          # Entry point v2
│
└── main.py                                 # Cambiar a dispatcher v1/v2
```

---

## 📊 Fases de Implementación

### FASE 1: Foundation (2 semanas)
**Objetivo**: State, Router, Fallback, Digression Manager

**Archivos a crear**:
```
agent/v2/state/conversation_state_v2.py     # Nuevo schema completo
agent/v2/state/retry_state.py               # RetryState + RetryPolicy
agent/v2/fallback/fallback_handler.py       # Mover y adaptar de nodes/
agent/v2/router/intent_router.py            # Clasificador de intención
agent/v2/router/digression_manager.py       # Parallel listener (Option B)
agent/v2/router/mode_transitions.py         # Reglas de transición
agent/v2/modes/base_mode.py                 # BaseModeNode con fallback integrado
agent/v2/prompts/loader_v2.py               # Loader dinámico por modo
agent/v2/prompts/core/*.md                  # Copiar y adaptar de prompts/core/
agent/v2/graph/conversation_graph_v2.py     # Grafo básico con router
```

**Archivos a eliminar en esta fase**:
```
# (Ninguno - coexisten durante desarrollo)
```

**Tests**:
```
tests/v2/test_intent_router.py
tests/v2/test_fallback_handler.py
tests/v2/test_digression_manager.py
tests/v2/test_state_v2.py
```

---

### FASE 2: VIABILIDAD_MODE (1.5 semanas)
**Objetivo**: Modo de viabilidad (65% del tráfico)

**Archivos a crear**:
```
agent/v2/modes/viabilidad_mode.py           # Nodo de modo
agent/v2/prompts/modes/viabilidad_mode.md   # System prompt específico
agent/v2/tools/viabilidad_tools.py          # Tools específicas
agent/v2/services/viabilidad_service.py     # Lógica de negocio
```

**Archivos a reciclar**:
```
agent/services/element_service.py           # identificar_elemento()
agent/services/tarifa_service.py            # calcular_estimacion_rapida()
```

**Tests**:
```
tests/v2/test_viabilidad_mode.py
tests/v2/e2e/test_viabilidad_flows.py       # Flujos completos
```

---

### FASE 3: CONSULTA_MODE (1 semana)
**Objetivo**: Modo consulta (10% - más simple)

**Archivos a crear**:
```
agent/v2/modes/consulta_mode.py             # Nodo de modo
agent/v2/prompts/modes/consulta_mode.md     # System prompt
agent/v2/tools/consulta_tools.py            # RAG, listar categorías
```

**Tests**:
```
tests/v2/test_consulta_mode.py
```

---

### FASE 4: PRESUPUESTO_MODE (1.5 semanas)
**Objetivo**: Modo presupuesto (25% - más complejo)

**Archivos a crear**:
```
agent/v2/modes/presupuesto_mode.py          # Nodo de modo
agent/v2/prompts/modes/presupuesto_mode.md  # System prompt
agent/v2/tools/presupuesto_tools.py         # Tools específicas
agent/v2/modes/evaluacion_gateway.py        # Gateway sí/no
agent/v2/prompts/modes/evaluacion_gateway.md
```

**Archivos a reciclar**:
```
agent/tools/element_tools.py                # identificar_y_resolver_elementos()
agent/tools/tarifa_tools.py                 # calcular_tarifa_con_elementos()
agent/tools/image_tools.py                  # enviar_imagenes_ejemplo()
```

**Tests**:
```
tests/v2/test_presupuesto_mode.py
```

---

### FASE 5: EXPEDIENTE_MODE (2 semanas)
**Objetivo**: Rediseño completo de expediente

**Archivos a crear**:
```
agent/v2/modes/expediente_mode.py           # Modo principal + router de submodos
agent/v2/modes/submodos/
    ├── datos_personales.py
    ├── datos_vehiculo.py
    ├── documentacion_elementos.py
    ├── documentacion_base.py
    ├── taller.py
    └── revision.py

agent/v2/prompts/modes/expediente_*.md      # 6 prompts de submodos
agent/v2/tools/expediente_tools.py          # Tools de expediente
agent/v2/services/expediente_service.py     # Lógica de caso (reemplaza FSM)
```

**Archivos a eliminar (FINALMENTE)**:
```
agent/fsm/                                  # FSM v1 completo
agent/prompts/phases/                       # Phases v1
```

**Tests**:
```
tests/v2/test_expediente_mode.py
```

---

### FASE 6: Integración y Testing (2 semanas)
**Objetivo**: Testing E2E, eliminación v1, deploy

**Archivos a modificar**:
```
agent/main.py                               # Dispatcher v1/v2 → Solo v2
```

**Archivos a eliminar (Big Bang)**:
```
# TODO: Lista completa de todos los archivos v1
```

**Tests**:
```
tests/v2/e2e/test_full_conversations.py     # Conversaciones completas
```

---

## 🎯 System Prompt Dinámico v2.0

### Estructura

```
┌─────────────────────────────────────────────────────────────┐
│                    SYSTEM PROMPT v2.0                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. CORE (siempre)                                          │
│     ├── 01_security.md                                      │
│     ├── 02_identity.md                                      │
│     ├── 03_format_style.md                                  │
│     ├── 04_anti_patterns.md                                 │
│     ├── 05_tools_efficiency.md                              │
│     ├── 06_escalation.md                                    │
│     ├── 07_pricing_rules.md                                 │
│     └── 08_documentation.md                                 │
│                                                             │
│  2. MODE-SPECIFIC (uno por conversación)                    │
│     ├── consulta_mode.md          ← 10% de llamadas         │
│     ├── viabilidad_mode.md        ← 65% de llamadas         │
│     ├── presupuesto_mode.md       ← 25% de llamadas         │
│     ├── evaluacion_gateway.md     ← breve                   │
│     └── expediente_*.md           ← por submodo             │
│                                                             │
│  3. MODE CONTEXT (dinámico)                                 │
│     └── Estado actual del modo (elementos, tarifa, etc.)    │
│                                                             │
│  4. CONVERSATION HISTORY                                    │
│     └── Últimos N mensajes                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Loader v2.0

```python
# agent/v2/prompts/loader_v2.py

MODE_MODULES = {
    "CONSULTA_MODE": "modes/consulta_mode.md",
    "VIABILIDAD_MODE": "modes/viabilidad_mode.md",
    "PRESUPUESTO_MODE": "modes/presupuesto_mode.md",
    "EVALUACION_GATEWAY": "modes/evaluacion_gateway.md",
    "EXPEDIENTE_DATOS_PERSONALES": "modes/expediente_datos_personales.md",
    "EXPEDIENTE_DATOS_VEHICULO": "modes/expediente_datos_vehiculo.md",
    "EXPEDIENTE_DOCUMENTACION": "modes/expediente_documentacion.md",
    "EXPEDIENTE_TALLER": "modes/expediente_taller.md",
    "EXPEDIENTE_REVISION": "modes/expediente_revision.md",
}

def assemble_system_prompt_v2(
    mode: str,
    mode_context: dict,
    history: list,
) -> str:
    parts = []
    
    # 1. Core modules
    parts.append(load_core_modules())
    
    # 2. Mode-specific module
    parts.append(load_mode_module(mode))
    
    # 3. Mode context
    parts.append(format_mode_context(mode, mode_context))
    
    # 4. History
    parts.append(format_history(history))
    
    return "\n\n---\n\n".join(parts)
```

---

## 📁 Prompts por Modo (Contenido a Crear)

### 1. `viabilidad_mode.md` (65% tráfico - PRIORIDAD)

```markdown
# MODO: VIABILIDAD

## Propósito
Evaluar si una modificación específica puede ser homologada en un vehículo determinado.

## Cuándo estás en este modo
- El usuario pregunta "¿Se puede homologar X en mi moto?"
- El usuario viene de CONSULTA_MODE con interés específico
- El clasificador de intención detectó: evaluar_viabilidad

## Herramientas disponibles
- identificar_elemento: Buscar elemento en catálogo
- evaluar_compatibilidad: Verificar si elemento + vehículo son compatibles
- verificar_restricciones: Chequear restricciones legales/regulatorias
- consultar_documentacion: Qué documentación sería necesaria
- listar_elementos_alternativos: Si no es viable, ofrecer alternativas
- calcular_estimacion_rapida: Rango de precio amplio (no exacto)
- transicionar_a_presupuesto: Cuando usuario confirma interés

## Reglas críticas
1. SIEMPRE evaluar viabilidad antes de mencionar precios
2. Si es viable: proporcionar rango de precio AMPLIO (ej: 800€-1200€)
3. Si es dudoso: explicar por qué y ofrecer escalación
4. Si no es viable: explicar alternativas, nunca inventar
5. NUNCA pedir datos personales en este modo

## Transiciones permitidas
- A PRESUPUESTO_MODE: Cuando usuario dice "sí, quiero presupuesto"
- A CONSULTA_MODE: Cuando usuario tiene dudas generales
- A ESCALACIÓN: Casos complejos o dudosos

## Ejemplo de interacción
Usuario: "¿Se puede homologar un escape en una MT-07?"
→ identificar_elemento("escape", "motos-part")
→ evaluar_compatibilidad(elemento, "Yamaha MT-07")
→ calcular_estimacion_rapida(elemento)

Respuesta: "Sí, es homologable. Requiere fotos del escape actual y factura del nuevo. Estimación: 800€-1200€. ¿Querés un presupuesto exacto?"
```

### 2. `consulta_mode.md`

```markdown
# MODO: CONSULTA

## Propósito
Responder preguntas informativas y educar al usuario sobre homologación.

## Cuándo estás en este modo
- Preguntas generales: "¿Qué es homologación?"
- Preguntas de proceso: "¿Cuánto tarda?"
- Intención ambigua (confidence < 75%)
- Digresión desde otro modo

## Herramientas disponibles
- responder_consulta_general: RAG sobre documentación
- explicar_proceso_homologacion: Flujo paso a paso
- listar_categorias: Qué vehículos soportamos
- listar_elementos_generales: Qué se puede homologar (genérico)

## Reglas críticas
1. Mantener respuestas concisas (WhatsApp)
2. NO calcular presupuestos en este modo
3. Detectar interés específico para transicionar
4. Permitir digresiones a consultas off-topic

## Transiciones
- A VIABILIDAD_MODE: "¿Se puede X?"
- A PRESUPUESTO_MODE: "¿Cuánto cuesta Y?"
```

### 3. `presupuesto_mode.md`

```markdown
# MODO: PRESUPUESTO

## Propósito
Calcular presupuesto exacto y mostrar documentación necesaria.

## Cuándo estás en este modo
- Usuario solicita presupuesto directo
- Transición desde VIABILIDAD_MODE tras confirmación
- Vuelta desde EVALUACION_GATEWAY si tiene dudas

## Herramientas disponibles
- identificar_y_resolver_elementos
- seleccionar_variante_por_respuesta
- agregar_elemento / quitar_elemento
- recalcular_tarifa
- calcular_tarifa_con_elementos (precio final)
- enviar_imagenes_ejemplo
- explicar_desglose_precio
- iniciar_expediente (transición a gateway)

## Reglas críticas
1. SIEMPRE mencionar precio ANTES de enviar imágenes
2. Permitir iteraciones: agregar/quitar elementos
3. Validar cada elemento con Constraint Service
4. Si hay dudas: volver a VIABILIDAD_MODE, no inventar

## Flujo
1. Identificar elementos exactos
2. Calcular tarifa precisa
3. Comunicar precio + IVA
4. Enviar imágenes de ejemplo
5. Preguntar: "¿Iniciamos el expediente?"
```

### 4. `evaluacion_gateway.md`

```markdown
# MODO: EVALUACIÓN_GATEWAY

## Propósito
Punto de control antes de iniciar expediente. Validar intención explícita.

## Características
- Estado BLOQUEANTE
- Requiere SÍ/NO explícito
- NO permite digresiones

## Reglas
1. Si ambiguo: repetir pregunta (no interpretar)
2. Si SÍ: transicionar a EXPEDIENTE_MODE
3. Si NO: volver a PRESUPUESTO_MODE
4. Si dudas: volver a PRESUPUESTO_MODE, nunca a consulta
```

### 5. `expediente_*.md` (Sub-modos)

Un prompt por sub-modo, con:
- Propósito específico del sub-modo
- Tools disponibles
- Datos a recolectar
- Validaciones requeridas
- Transiciones permitidas

---

## 🧪 Testing Estrategia

### Tests Unitarios (por fase)
- Intent Router: clasificación de intenciones
- Fallback Handler: retry policies, acciones
- Digression Manager: detección de off-topic
- Cada modo: transiciones, tools, mensajes

### Tests de Integración
- Flujo completo: entrada → modo → salida
- Transiciones entre modos
- Fallback actions
- Digression handling

### Tests E2E
- Conversaciones completas simuladas
- Casos edge: errores, timeouts, fallbacks
- Comparación v1 vs v2 (antes del Big Bang)

---

## ✅ Checklist por Fase

### FASE 1 Checklist
- [ ] Intent Router clasifica correctamente 5 intenciones
- [ ] Fallback Handler ejecuta acciones por modo
- [ ] Digression Manager detecta off-topic
- [ ] State v2 persiste correctamente
- [ ] Loader v2 ensambla prompts correctamente

### FASE 2 Checklist (VIABILIDAD)
- [ ] Nodo identifica elementos
- [ ] Calcula estimaciones rápidas
- [ ] Detecta cuando transicionar a presupuesto
- [ ] Maneja casos dudosos (escalación)

### FASE 6 Checklist (Big Bang)
- [ ] Todos los archivos v1 eliminados
- [ ] Tests v2 pasan 100%
- [ ] Conversaciones E2E funcionan
- [ ] Métricas de fallback < 15%
- [ ] Rollback plan documentado (por si acaso)

---

**Próximo paso**: ¿Creo los documentos detallados de cada fase con especificaciones técnicas completas?
