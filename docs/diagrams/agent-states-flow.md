# Diagrama de Estados del Agente MSI-a v2.0

**Arquitectura**: Basada en Modos (post-fusión VIABILIDAD + PRESUPUESTO)  
**Fecha**: Febrero 2026

---

## 🎯 Estados (Modos) Principales

```
┌─────────────────────────────────────────────────────────────────┐
│                        ESTADOS DEL AGENTE                       │
└─────────────────────────────────────────────────────────────────┘

┌──────────────┐
│    START     │  Inicial (nueva conversación o sin modo activo)
└──────────────┘
       │
       ▼
┌──────────────┐
│ CONSULTA_MODE│  ~10% tráfico - Consultas educativas generales
└──────────────┘  Tools: 5 (RAG, listar elementos, etc.)
       │
       ▼
┌──────────────┐
│PRESUPUESTO   │  ~90% tráfico - Precio inmediato (fusión con viabilidad)
│   _MODE      │  Tools: 10 (identificar, calcular, imágenes, etc.)
└──────────────┘
       │
       ▼
┌──────────────┐
│ EVALUACION   │  Gateway confirmación - Pattern-based (NO LLM)
│  _GATEWAY    │  Tools: 0 (solo regex YES/NO)
└──────────────┘
       │
       ├─[SÍ]──►
       │         ┌──────────────┐
       │         │ EXPEDIENTE   │  Recopilación formal (6 sub-modos)
       │         │   _MODE      │  Tools: 26 (elemento-por-elemento)
       │         └──────────────┘
       │                │
       │                ▼
       └─[NO]──►  ┌──────────────┐
                  │  ESCALATION  │  Terminal - Handoff a humano
                  └──────────────┘
                         │
                         ▼
                  ┌──────────────┐
                  │  COMPLETED   │  Terminal - Conversación finalizada
                  └──────────────┘
```

---

## 🔄 Flujo Completo de Conversación

```
┌─────────────────────────────────────────────────────────────────┐
│                    FLUJO DE PROCESAMIENTO                       │
└─────────────────────────────────────────────────────────────────┘

Usuario envía mensaje (WhatsApp → Chatwoot → Redis Streams)
       │
       ▼
┌──────────────┐
│  PREPROCESS  │  - Extrae mensaje
│     NODE     │  - Incrementa contadores
└──────┬───────┘  - Verifica panic button (agent_disabled)
       │
       ▼
┌──────────────┐
│   ROUTER     │  - Intent classification (START)
│     NODE     │  - Digression detection (modos activos)
└──────┬───────┘  - Transition validation
       │
       ├────────► (conditional edge: route_to_mode)
       │
   ┌───┴───────────────────────────────────┐
   │                                       │
   ▼                                       ▼
┌──────────────┐                    ┌──────────────┐
│ consulta_mode│                    │presupuesto   │
│     node     │                    │  mode_node   │
└──────┬───────┘                    └──────┬───────┘
       │                                   │
       │          ┌──────────────┐         │
       │          │eval_gateway  │         │
       │          │     node     │◄────────┘
       │          └──────┬───────┘
       │                 │
       ├─────────────────┴─────────────────┤
       │                                   │
       ▼                                   ▼
┌──────────────┐                    ┌──────────────┐
│ expediente   │                    │ escalation   │
│  mode_node   │                    │     node     │
└──────┬───────┘                    └──────┬───────┘
       │                                   │
       └───────────────┬───────────────────┘
                       │
                       ▼
                    [ END ]  → Envía respuesta y guarda state
```

---

## 🧭 Intent Routing (desde START)

```
┌─────────────────────────────────────────────────────────────────┐
│                   CLASIFICACIÓN DE INTENCIONES                  │
└─────────────────────────────────────────────────────────────────┘

Mensaje del usuario
       │
       ▼
┌──────────────────────┐
│  Keyword Patterns    │  Fast path (regex)
│  (9 intents)         │
└──────┬───────────────┘
       │
       ├─[match >= 0.75]──► Ruta directa al modo
       │
       └─[no match]
              │
              ▼
       ┌──────────────┐
       │ LLM Classify │  qwen2.5:3b (local, TaskType.CLASSIFICATION)
       │ (Tier 1)     │
       └──────┬───────┘
              │
              ├─[confidence >= 0.75]──► Ruta al modo sugerido
              │
              └─[confidence < 0.75]
                     │
                     ▼
              ┌──────────────┐
              │   AMBIGUO    │  → CONSULTA_MODE + pregunta aclaratoria
              └──────────────┘

INTENCIONES:
├─ CONSULTA_GENERAL      → CONSULTA_MODE
├─ PRESUPUESTO_DIRECTO   → PRESUPUESTO_MODE (fusionó VIABILIDAD)
├─ INICIAR_EXPEDIENTE    → EVALUACION_GATEWAY
├─ ESCALAR               → ESCALATION
├─ CONFIRMACION          → Context-dependent (ver gateway)
├─ RECHAZO               → Context-dependent (volver a PRESUPUESTO)
├─ MODIFICAR_ELEMENTOS   → PRESUPUESTO_MODE
└─ AMBIGUO               → CONSULTA_MODE (con clarification_question)
```

---

## 🎭 Sub-modos de EXPEDIENTE_MODE

```
┌─────────────────────────────────────────────────────────────────┐
│              EXPEDIENTE_MODE - 6 SUB-MODOS                      │
└─────────────────────────────────────────────────────────────────┘

Entrada: gateway_confirmed=True desde EVALUACION_GATEWAY
       │
       ▼
┌──────────────────────┐
│ 1. COLLECT_ELEMENT   │  Elemento-por-elemento:
│      _DATA           │  - Confirmar fotos (confirmar_fotos_elemento)
│                      │  - Obtener campos (obtener_campos_elemento)
└──────┬───────────────┘  - Guardar datos (guardar_datos_elemento)
       │                  - Completar (completar_elemento_actual)
       │
       ▼
┌──────────────────────┐
│ 2. COLLECT_BASE      │  Documentación base:
│      _DOCS           │  - Ficha técnica
│                      │  - Permiso de circulación
└──────┬───────────────┘  - 4 vistas (lateral, frontal, posterior, matrícula)
       │
       ▼
┌──────────────────────┐
│ 3. COLLECT_PERSONAL  │  Datos personales:
│                      │  - Nombre completo
│                      │  - DNI/NIE
└──────┬───────────────┘  - Email, domicilio, fecha ITV
       │
       ▼
┌──────────────────────┐
│ 4. COLLECT_VEHICLE   │  Datos vehículo:
│                      │  - Marca, modelo
│                      │  - Matrícula
└──────┬───────────────┘  - Número de bastidor
       │
       ▼
┌──────────────────────┐
│ 5. COLLECT_WORKSHOP  │  Decisión taller:
│                      │  - MSI / Propio
│                      │  [Si propio: nombre, dirección]
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ 6. REVIEW_SUMMARY    │  Revisión final:
│                      │  - Presentar resumen completo
│                      │  - Confirmar o editar
└──────┬───────────────┘
       │
       ▼
   [COMPLETED]  → El caso se marca como listo para procesamiento
```

---

## 🔀 Digression Management (Modos Activos)

```
┌─────────────────────────────────────────────────────────────────┐
│                   DETECCIÓN DE DIGRESIONES                      │
└─────────────────────────────────────────────────────────────────┘

Modo activo (no START)
       │
       ▼
┌──────────────────┐
│ ¿Es permisivo?   │  CONSULTA, VIABILIDAD → skip check
│ (permissive_mode)│
└──────┬───────────┘
       │ NO (focused mode)
       ▼
┌──────────────────┐
│ Check digression │  Regex + context patterns
│  (4 tipos)       │
└──────┬───────────┘
       │
       ├─[OFF_TOPIC]─────► Transición a CONSULTA_MODE
       ├─[GREETING]──────► Respuesta rápida en modo actual
       ├─[QUESTION]──────► Transición a CONSULTA_MODE
       └─[ESCALATION]────► Transición a ESCALATION

MODOS FOCUSED (bloquean digresión):
├─ PRESUPUESTO_MODE    (elemento en proceso)
├─ EVALUACION_GATEWAY  (esperando yes/no)
└─ EXPEDIENTE_MODE     (recopilación formal)

TIPOS DE DIGRESIÓN:
├─ OFF_TOPIC     "¿Qué hora es?" (no relacionado)
├─ GREETING      "Hola", "Buenos días"
├─ QUESTION      "¿Cómo funciona X?" (consulta educativa)
└─ ESCALATION    "Quiero hablar con un humano"
```

---

## ⚡ Mode Transitions (Whitelist)

```
┌─────────────────────────────────────────────────────────────────┐
│                  TRANSICIONES PERMITIDAS                        │
└─────────────────────────────────────────────────────────────────┘

START
  ├──► CONSULTA_MODE
  ├──► PRESUPUESTO_MODE
  ├──► EVALUACION_GATEWAY (raro, pero posible)
  └──► ESCALATION

CONSULTA_MODE
  ├──► PRESUPUESTO_MODE
  ├──► EVALUACION_GATEWAY (si ya tiene presupuesto)
  └──► ESCALATION

PRESUPUESTO_MODE
  ├──► CONSULTA_MODE (digresión)
  ├──► EVALUACION_GATEWAY (precio confirmado)
  └──► ESCALATION

EVALUACION_GATEWAY
  ├──► EXPEDIENTE_MODE (confirmación SÍ)
  ├──► PRESUPUESTO_MODE (rechazo NO)
  └──► ESCALATION

EXPEDIENTE_MODE
  ├──► CONSULTA_MODE (digresión permitida con preservación)
  ├──► ESCALATION
  └──► COMPLETED (expediente completo)

ESCALATION
  └──► END (terminal)

COMPLETED
  └──► END (terminal)
```

---

## 🛡️ Fallback & Retry (Por Modo)

```
┌─────────────────────────────────────────────────────────────────┐
│                  POLÍTICAS DE REINTENTOS                        │
└─────────────────────────────────────────────────────────────────┘

CONSULTA_MODE
  Max retries: 2
  Fallback: ESCALATION (si se excede)
  Progressive reprompts: ✓

PRESUPUESTO_MODE (BLOCKING)
  Max retries: 3
  Fallback: ESCALATION
  Progressive reprompts: ✓
  ⚠️ BLOCKING: el usuario DEBE responder para avanzar

EVALUACION_GATEWAY (BLOCKING)
  Max retries: 2
  Fallback: Volver a PRESUPUESTO_MODE
  Progressive reprompts: Sí/No clarification
  ⚠️ BLOCKING: patrón yes/no obligatorio

EXPEDIENTE_MODE (BLOCKING)
  Max retries: 5 (recopilación larga)
  Fallback: ESCALATION
  Progressive reprompts: ✓ (per sub-mode)
  ⚠️ BLOCKING: datos obligatorios

ESCALATION
  No retries (terminal)
```

---

## 🎨 Context Preservation (Draft Contexts)

```
┌─────────────────────────────────────────────────────────────────┐
│                  PRESERVACIÓN DE CONTEXTO                       │
└─────────────────────────────────────────────────────────────────┘

Al salir de un modo:
       │
       ▼
┌──────────────────────┐
│ Guardar mode_context │  draft_contexts[mode_name] = mode_context
│ en draft_contexts    │
└──────────────────────┘

Al regresar a un modo:
       │
       ▼
┌──────────────────────┐
│ Restaurar context    │  mode_context = draft_contexts.pop(mode_name)
│ desde draft          │
└──────────────────────┘

KEYS PRESERVADOS (según transición):
├─ PRESUPUESTO → CONSULTA:
│    - categoria_slug
│    - elementos_confirmados
│    - element_codes
│    - tarifa_calculada
│    - precio_comunicado
│
├─ PRESUPUESTO → EVALUACION:
│    - categoria_slug
│    - element_codes
│    - tarifa_calculada
│    - precio_exacto (calculado)
│
├─ EVALUACION → EXPEDIENTE:
│    - categoria_slug
│    - element_codes
│    - tarifa_calculada
│    - precio_exacto
│
└─ EXPEDIENTE → CONSULTA (digresión):
     - case_id
     - sub_modo
     - current_element_index
     - element_data_status
     - ALL expediente data preserved
```

---

## 📊 Estadísticas de Tráfico

```
┌─────────────────────────────────────────────────────────────────┐
│                  DISTRIBUCIÓN DE TRÁFICO                        │
└─────────────────────────────────────────────────────────────────┘

CONSULTA_MODE          ██ 10%   (educativas, catálogo)
PRESUPUESTO_MODE       █████████ 90%  (precio directo - fusionó viabilidad)
EVALUACION_GATEWAY     █ <5%    (confirmación yes/no)
EXPEDIENTE_MODE        █ <5%    (tramitación formal)
ESCALATION             █ <2%    (handoff humano)

NOTAS:
- PRESUPUESTO_MODE es ahora el punto de entrada principal
- Ya NO existe VIABILIDAD_MODE separado (fusionado en feb 2026)
- ~90% de usuarios obtienen precio inmediatamente
- ~5% avanzan a expediente formal
```

---

## 🔧 Anti-Patterns Críticos

```
┌─────────────────────────────────────────────────────────────────┐
│                     ANTI-PATTERNS (NUNCA)                       │
└─────────────────────────────────────────────────────────────────┘

❌ NUNCA re-identificar después de variante
   User: "delantera"
   ✗ identificar_y_resolver_elementos(...)
   ✓ seleccionar_variante_por_respuesta("motos-part", "SUSPENSION", "delantera")

❌ NUNCA olvidar mencionar el precio antes de imágenes
   ✗ Bot: "Te envío fotos:" (sin precio)
   ✓ Bot: "410€ +IVA. Te envío fotos:"

❌ NUNCA skip_validation=False después de identificación
   ✗ calcular_tarifa_con_elementos(elementos, categoria)
   ✓ calcular_tarifa_con_elementos(elementos, categoria, skip_validation=True)

❌ NUNCA modificar state directamente (usar transition_mode)
   ✗ state["current_mode"] = "PRESUPUESTO_MODE"
   ✓ return {"current_mode": "PRESUPUESTO_MODE", ...}

❌ NUNCA hardcoded flow (LLM decide)
   ✗ if message == "X": do_thing()
   ✓ System prompt guides LLM decision
```

---

## 🧪 Testing State Flows

```bash
# Test conversación completa (happy path)
Usuario: "Hola, quiero homologar un escape"
  → PRESUPUESTO_MODE (intent: PRESUPUESTO_DIRECTO)
  → Tool: identificar_y_resolver_elementos
  → [variante: delantera/trasera?]

Usuario: "trasera"
  → Tool: seleccionar_variante_por_respuesta
  → Tool: calcular_tarifa_con_elementos (skip_validation=True)
  → Response: "410€ +IVA para escape trasera. ¿Te envío fotos?"

Usuario: "sí"
  → Tool: enviar_imagenes_ejemplo
  → Response: [imágenes] + "¿Iniciamos el expediente?"
  → Transición: EVALUACION_GATEWAY

Usuario: "sí"
  → Transición: EXPEDIENTE_MODE (sub_modo: COLLECT_ELEMENT_DATA)
  → [recopilación elemento-por-elemento...]

# Test digresión (focused mode)
[En PRESUPUESTO_MODE, esperando respuesta variante]
Usuario: "¿Cómo funciona la homologación?"
  → Digression detected: QUESTION
  → Transición: CONSULTA_MODE
  → Preserva: categoria_slug, elementos_confirmados
  → Response: [explicación] + "¿Volvemos al presupuesto?"

# Test panic button
Usuario: [mensaje]
  → preprocess_node detecta agent_disabled=True
  → Transición inmediata: ESCALATION
  → Response: "Te conecto con un especialista..."
```

---

## 📝 Leyenda

```
┌──────────┐   Nodo/Estado
└──────────┘

────►        Transición directa

[condición]  Condicional

⚠️ BLOCKING  Modo bloquea hasta obtener respuesta

✓            Feature activo
✗            Anti-pattern (nunca hacer)
```

---

**Creado**: Febrero 2026  
**Versión**: 2.0 (post-fusión VIABILIDAD+PRESUPUESTO)  
**Referencia**: `agent/graph/conversation_graph.py`, `agent/state/conversation_state.py`
