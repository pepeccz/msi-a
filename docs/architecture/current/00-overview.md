# Propuesta de Arquitectura de Conversación MSI-a v2.0

## 📋 Resumen Ejecutivo

**Fecha**: Febrero 2026  
**Autor**: Equipo de Arquitectura  
**Estado**: Propuesta para revisión  
**Versión**: 2.0 (rediseño desde v1.0)

### Problema con la Arquitectura v1.0

La arquitectura actual tiene un **estado IDLE monolítico** que intenta hacer todo:
- Responder consultas informativas (10% de tráfico)
- Evaluar viabilidad técnica (65% de tráfico - mayoría)
- Calcular presupuestos (25% de tráfico)
- Iniciar expedientes

Esto genera **confusión tanto en el usuario como en el agente** porque no hay claridad de "en qué modo estamos conversando".

### Solución Propuesta

**Arquitectura de "Modos de Conversación"** con 4 centros de gravedad claros:

1. **CONSULTA_MODE** (10% de tráfico) - Educar y clarificar
2. **VIABILIDAD_MODE** (65% de tráfico) - Evaluar si se puede homologar
3. **PRESUPUESTO_MODE** (25% de tráfico) - Calcular precios específicos
4. **EXPEDIENTE_MODE** (conversión) - Recolección formal de datos

**Flujo no lineal (grafo)**: El usuario puede navegar entre modos según necesidad.

---

## 🎯 Análisis del Sistema Actual (Reciclaje)

### ✅ Qué se Recicla (Lo que funciona bien)

| Componente | Estado | Acción |
|------------|--------|--------|
| **Smart Collection Mode** | ✅ Excelente | Reciclar tal cual |
| **Constraint Service** | ✅ Excelente | Reciclar tal cual |
| **Security layers** | ✅ Excelente | Reciclar tal cual |
| **Element tools** | ✅ Bueno | Reciclar con ajustes menores |
| **Tarifa service** | ✅ Bueno | Reciclar tal cual |
| **Dynamic prompts** | ✅ Bueno | Adaptar a nuevos modos |
| **Image handling** | ✅ Bueno | Reciclar tal cual |
| **Tool logging** | ✅ Bueno | Reciclar tal cual |
| **Redis/Postgres** | ✅ Bueno | Reciclar tal cual |

### ⚠️ Qué se Refactoriza (Funciona pero mal ubicado)

| Componente | Problema Actual | Solución |
|------------|-----------------|----------|
| **IDLE state** | Hace todo | Dividir en 3 modos especializados |
| **FSM lineal** | Secuencia forzada | Grafo con transiciones flexibles |
| **Retry logic** | `MAX_RETRIES` sin acción | Nueva política con escape definido |
| **Timeouts** | No existen | Implementar en cada modo |
| **Intent detection** | Implícito por LLM | Clasificador explícito con umbral |

### ❌ Qué se Elimina (Deuda técnica)

| Componente | Razón |
|------------|-------|
| **Estado IDLE único** | Reemplazado por 3 modos especializados |
| **Transiciones forzadas** | El usuario controla el flujo, no la máquina |
| **Acumulación de contexto** | Cada modo tiene su propio contexto aislado |

---

## 🏗️ Nueva Arquitectura: Modos de Conversación

### Principios Fundamentales

1. **Claridad de Propósito**: Cada modo tiene UN objetivo claro
2. **Navegabilidad**: El usuario puede cambiar de modo sin perder progreso
3. **Progresividad**: No se piden datos hasta que hay intención confirmada
4. **Recuperación**: Cada modo define su política de errores y timeouts
5. **Herramientas Contextuales**: Solo herramientas relevantes disponibles por modo

### Grafo de Modos

```
┌─────────────────────────────────────────────────────────────────────┐
│                    GRAFO DE MODOS DE CONVERSACIÓN                   │
└─────────────────────────────────────────────────────────────────────┘

                         ┌──────────────┐
                         │    START     │
                         └──────┬───────┘
                                │
                ┌───────────────┼───────────────┐
                │               │               │
                ▼               ▼               ▼
        ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
        │ CONSULTA_MODE│ │VIABILIDAD_MODE│ │PRESUPUESTO_  │
        │   (Educar)   │ │  (¿Se puede?) │ │    MODE      │
        └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
               │                │                │
               │◄───────────────┼───────────────►│
               │                │                │
               ▼                │                ▼
        ┌──────────────┐        │        ┌──────────────┐
        │   (vuelve    │        │        │  (vuelve a   │
        │  a consultar)│        │        │  viabilidad) │
        └──────────────┘        │        └──────────────┘
                                │
                                ▼
                         ┌──────────────┐
                         │  EVALUACIÓN  │
                         │   GATEWAY    │
                         │(¿Expediente? │
                         └──────┬───────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
                    ▼                       ▼
            ┌──────────────┐        ┌──────────────┐
            │ EXPEDIENTE_  │        │  (vuelve a   │
            │    MODE      │        │ presupuesto) │
            │ (Recolección)│        └──────────────┘
            └──────┬───────┘
                   │
                   ▼
            ┌──────────────┐
            │  COMPLETED   │
            └──────────────┘
```

### Descripción de Modos

#### Modo 1: CONSULTA_MODE

**Propósito**: Responder preguntas informativas y educar al usuario sobre homologación.

**Cuándo se entra**:
- Usuario pregunta "¿Qué es homologación?"
- Usuario pregunta "¿Es obligatorio?"
- Usuario pregunta "¿Cuánto tarda?"
- Transición desde otro modo cuando el usuario hace consulta off-topic

**Cuándo se sale**:
- Usuario indica interés en evaluar viabilidad: "¿Se puede homologar X?"
- Usuario indica interés directo en presupuesto: "¿Cuánto cuesta Y?"
- Usuario solicita hablar con humano

**Herramientas disponibles** (5 herramientas):
```python
consulta_mode_tools = [
    responder_consulta_general,      # RAG sobre documentación
    explicar_proceso_homologacion,   # Flujo paso a paso
    listar_categorias,               # Qué vehículos soportamos
    listar_elementos_generales,      # Qué se puede homologar (genérico)
    escalar_a_humano,                # Siempre disponible
]
```

**Datos recolectados**: Ninguno (solo conversación para analytics)

**Timeout**: 10 minutos de inactividad → Mensaje "¿Sigues ahí?"

**Ejemplo de interacción**:
```
Usuario: ¿Qué es la homologación?
Agente: [CONSULTA_MODE] La homologación es el proceso de...

Usuario: ¿Y es obligatoria?
Agente: [CONSULTA_MODE] Sí, es obligatoria cuando...

Usuario: ¿Se puede homologar un escape?
Agente: [TRANSICIÓN A VIABILIDAD_MODE] 
       Déjame evaluar eso por ti...
```

---

#### Modo 2: VIABILIDAD_MODE

**Propósito**: Evaluar si una modificación específica puede ser homologada (65% del tráfico).

**Cuándo se entra**:
- Usuario pregunta "¿Se puede homologar X en mi moto?"
- Transición desde CONSULTA_MODE cuando hay interés específico
- Transición desde PRESUPUESTO_MODE si hay dudas de viabilidad

**Cuándo se sale**:
- Viabilidad confirmada + usuario quiere presupuesto
- Viabilidad dudosa → Escalación a humano técnico
- Viabilidad negativa + usuario acepta

**Herramientas disponibles** (7 herramientas):
```python
viabilidad_mode_tools = [
    identificar_elemento,            # Buscar elemento en catálogo
    evaluar_compatibilidad,          # ¿Elemento + vehículo son compatibles?
    verificar_restricciones,         # Restricciones legales/regulatorias
    consultar_documentacion,         # Qué docs se necesitarían
    listar_elementos,                # Alternativas si no es viable
    calcular_estimacion_rapida,      # Rango de precio sin detalle
    transicion_a_presupuesto,        # Cuando usuario confirma interés
    escalar_a_humano,                # Siempre disponible
]
```

**Datos recolectados**:
- Elemento(s) de interés (códigos tentativos)
- Vehículo (marca/modelo si se menciona)
- Resultado de viabilidad (viable/dudoso/no_viable)

**Timeout**: 15 minutos → Nudge "¿Quieres que busque un presupuesto detallado?"

**Ejemplo de interacción**:
```
Usuario: ¿Se puede homologar un turbo en una Yamaha MT-07?
Agente: [VIABILIDAD_MODE] 
       Déjame verificar... Buscando información sobre turbos...
       
       Encontré información. Para tu Yamaha MT-07:
       • Turbo: SÍ es homologable
       • Pero requiere modificaciones adicionales en admisión
       • Documentación compleja (fotos del sistema completo)
       
       Estimación rápida: 1.200€ - 1.800€ (rango amplio)
       
       ¿Quieres un presupuesto detallado con precio exacto?

Usuario: Sí
Agente: [TRANSICIÓN A PRESUPUESTO_MODE]
```

---

#### Modo 3: PRESUPUESTO_MODE

**Propósito**: Calcular presupuesto exacto y mostrar documentación necesaria.

**Cuándo se entra**:
- Usuario solicita presupuesto directamente
- Transición desde VIABILIDAD_MODE tras confirmación
- Vuelta desde EXPEDIENTE_MODE si usuario quiere modificar elementos

**Cuándo se sale**:
- Usuario acepta presupuesto → EVALUACIÓN_GATEWAY
- Usuario rechaza → Vuelta a CONSULTA_MODE o VIABILIDAD_MODE
- Usuario quiere agregar/quitar elementos → Loop dentro del modo

**Herramientas disponibles** (9 herramientas):
```python
presupuesto_mode_tools = [
    identificar_y_resolver_elementos,     # Buscar elementos específicos
    seleccionar_variante_por_respuesta,   # Resolver ambigüedades
    agregar_elemento,                     # Añadir más elementos al presupuesto
    quitar_elemento,                      # Remover elementos
    recalcular_tarifa,                    # Actualizar precio
    calcular_tarifa_con_elementos,        # Precio final exacto
    enviar_imagenes_ejemplo,              # Mostrar docs requeridas
    explicar_desglose_precio,             # Detallar qué incluye
    iniciar_expediente,                   # Transición a gateway
    escalar_a_humano,                     # Siempre disponible
]
```

**Datos recolectados**:
- Lista final de elementos (códigos confirmados)
- Tarifa calculada (tier, precio, warnings)
- Imágenes de ejemplo enviadas (flag)
- Precio comunicado (flag)

**Timeout**: 20 minutos → "¿Te gustaría que guarde este presupuesto y vuelvas luego?"

**Ejemplo de interacción**:
```
Usuario: [Viene de VIABILIDAD_MODE]

Agente: [PRESUPUESTO_MODE]
       Perfecto, voy a calcular tu presupuesto exacto.
       
       Elementos identificados:
       • Escape deportivo
       • Filtro de aire de alto flujo
       
       Precio total: 890€ + IVA
       
       [Envía imágenes de ejemplo]
       
       ¿Te gustaría que te abriera un expediente?
       
Usuario: También quiero homologar el manillar
Agente: [PRESUPUESTO_MODE - Loop]
       Agregando manillar...
       
       Actualización:
       • Escape deportivo
       • Filtro de aire
       • Manillar
       
       Nuevo precio: 1.150€ + IVA
       
       ¿Iniciamos el expediente?
```

---

#### Modo 4: EVALUACIÓN_GATEWAY (Estado de Decisión)

**Propósito**: Punto de control antes de iniciar expediente formal. Verificar que el usuario realmente quiere proceder.

**Cuándo se entra**:
- Siempre desde PRESUPUESTO_MODE tras aceptación

**Cuándo se sale**:
- Confirmación explícita → EXPEDIENTE_MODE
- Dudas/rechazo → Vuelta a PRESUPUESTO_MODE o CONSULTA_MODE

**Herramientas disponibles** (3 herramientas):
```python
evaluacion_tools = [
    confirmar_inicio_expediente,     # Validar intención explícita
    guardar_presupuesto_borrador,    # Por si quiere volver luego
    volver_a_presupuesto,            # Si tiene dudas
    escalar_a_humano,                # Siempre disponible
]
```

**Datos recolectados**: Confirmación explícita (sí/no ambiguo)

**Timeout**: 5 minutos (decisión rápida) → "¿Confirmás que Quieres iniciar el expediente?"

**Nota**: Este es un estado BLOQUEANTE. El usuario debe responder sí/no explícitamente.

---

#### Modo 5: EXPEDIENTE_MODE

**Propósito**: Recolección formal de datos y documentación para crear caso legal.

**Cuándo se entra**:
- Solo desde EVALUACIÓN_GATEWAY con confirmación explícita

**Estructura interna (sub-modos)**:
```
EXPEDIENTE_MODE
  ├─ SUBMODO_DATOS_PERSONALES
  │   └─ nombre, apellidos, dni_cif, email, domicilio, itv
  ├─ SUBMODO_DATOS_VEHICULO
  │   └─ marca, modelo, matricula, anio, bastidor
  ├─ SUBMODO_DOCUMENTACION_ELEMENTOS
  │   └─ Para cada elemento: fotos + datos técnicos
  ├─ SUBMODO_DOCUMENTACION_BASE
  │   └─ ficha técnica, permiso circulación, vistas vehículo
  ├─ SUBMODO_TALLER
  │   └─ MSI (+85€) o taller propio (datos del taller)
  └─ SUBMODO_REVISION
      └─ Resumen final, confirmación, escalación
```

**Herramientas disponibles por sub-modo**:

```python
# DATOS_PERSONALES (4 herramientas)
datos_personales_tools = [
    actualizar_datos_personales,
    consulta_durante_expediente,     # Solo preguntas sobre por qué pedimos esto
    obtener_estado_expediente,
    escalar_a_humano,
]

# DATOS_VEHICULO (4 herramientas)
datos_vehiculo_tools = [
    actualizar_datos_vehiculo,
    consulta_durante_expediente,
    obtener_estado_expediente,
    escalar_a_humano,
]

# DOCUMENTACION_ELEMENTOS (8 herramientas)
doc_elementos_tools = [
    confirmar_fotos_elemento,
    guardar_datos_elemento,
    completar_elemento_actual,
    obtener_campos_elemento,
    obtener_progreso_elementos,
    reenviar_imagenes_elemento,
    consulta_durante_expediente,
    escalar_a_humano,
]

# DOCUMENTACION_BASE (5 herramientas)
doc_base_tools = [
    confirmar_documentacion_base,
    enviar_imagenes_ejemplo,
    consulta_durante_expediente,
    escalar_a_humano,
]

# TALLER (4 herramientas)
taller_tools = [
    actualizar_datos_taller,
    consulta_durante_expediente,
    escalar_a_humano,
]

# REVISION (5 herramientas)
revision_tools = [
    finalizar_expediente,
    editar_seccion_expediente,       # Volver a sub-modo anterior
    consulta_durante_expediente,
    obtener_resumen_expediente,
    escalar_a_humano,
]
```

**Transiciones entre sub-modos**:
- Progresión: DATOS_PERSONALES → DATOS_VEHICULO → DOC_ELEMENTOS → DOC_BASE → TALLER → REVISION
- Regresión: Desde REVISION puede volver a cualquier sub-modo anterior
- No se puede saltar sub-modos (secuencial pero editable)

**Timeout**: 30 minutos por sub-modo → Nudge "¿Estás teniendo dificultades? Puedo conectarte con un agente"

---

## 🔧 Soluciones a Gaps Críticos

### Gap #1: Timeouts de Estado

**Solución de raíz**: Cada modo define su propia política de timeout

```python
MODE_TIMEOUTS = {
    CONSULTA_MODE: 600,      # 10 min - consultas son rápidas
    VIABILIDAD_MODE: 900,    # 15 min - requiere búsqueda
    PRESUPUESTO_MODE: 1200,  # 20 min - puede iterar varias veces
    EVALUACION_GATEWAY: 300, # 5 min - decisión rápida
    EXPEDIENTE_MODE: 1800,   # 30 min - por sub-modo
}

async def check_mode_timeout(current_mode, last_activity):
    timeout = MODE_TIMEOUTS[current_mode]
    if inactive_for > timeout:
        return TimeoutAction.NUDGE  # Primero nudge
    elif inactive_for > timeout * 2:
        return TimeoutAction.RESET_TO_CONSULTA_MODE  # Luego reset
```

**Acción en timeout**:
1. **Nudge (1x timeout)**: "¿Sigues ahí? Responde cualquier cosa para continuar"
2. **Reset (2x timeout)**: Volver a CONSULTA_MODE con mensaje explicativo
3. **Preservar contexto**: El presupuesto calculado se guarda como "borrador"

---

### Gap #2: Política de Reintentos sin Escape

**Solución de raíz**: Cada modo define su estrategia de recuperación

```python
MODE_RETRY_POLICIES = {
    CONSULTA_MODE: {
        max_retries: 3,
        action_on_limit: "offer_human",  # Escalar si no entendemos
    },
    VIABILIDAD_MODE: {
        max_retries: 3,
        action_on_limit: "escalate_technical",  # Necesita experto
    },
    PRESUPUESTO_MODE: {
        max_retries: 5,  # Más tolerante, usuario explorando
        action_on_limit: "return_to_viabilidad",  # Quizás necesita otra cosa
    },
    EXPEDIENTE_MODE: {
        max_retries: 3,
        action_on_limit: "offer_human_help",  # Asistencia en datos
    },
}
```

**Implementación**:
- Contador `retry_count` por modo (no global)
- Reset al cambiar de modo (nueva intención, nuevo contador)
- Acción explícita definida (no dejar en bucle)

---

### Gap #3: Sin Detección de Fallos NLU

**Solución de raíz**: Clasificador de intención explícito en el punto de entrada

```python
class IntentClassifier:
    """Clasifica intención del usuario con confidence score."""
    
    INTENTS = [
        "consulta_general",      # Preguntas informativas
        "evaluar_viabilidad",    # "¿Se puede homologar X?"
        "presupuesto_directo",   # "¿Cuánto cuesta Y?"
        "iniciar_expediente",    # "Quiero empezar"
        "escalar",              # "Hablar con persona"
        "ambiguo",              # No claro
    ]
    
    async def classify(self, message, conversation_history) -> IntentResult:
        # Usar modelo ligero local (qwen2.5:3b) para clasificación rápida
        # Retornar: intent + confidence + suggested_mode
        
        if confidence < 0.75:
            return IntentResult(
                intent="ambiguo",
                confidence=confidence,
                suggested_mode=CONSULTA_MODE,  # Default seguro
                clarification_question="¿Buscás información general, evaluar si algo se puede homologar, o un presupuesto específico?"
            )
```

**Uso en el grafo**:
```python
# En entry point del grafo
intent_result = await intent_classifier.classify(user_message, history)

if intent_result.confidence >= 0.75:
    # Ir directo al modo sugerido
    target_mode = intent_result.suggested_mode
else:
    # Ambiguo: ir a CONSULTA_MODE con pregunta de clarificación
    target_mode = CONSULTA_MODE
    context["pending_clarification"] = intent_result.clarification_question
```

---

### Gap #4: Estados Bloqueantes vs Permisivos

**Solución de raíz**: Definición explícita en cada modo

```python
MODE_PROPERTIES = {
    CONSULTA_MODE: {
        blocking: False,
        allows_digression: True,
        can_transition_to: [VIABILIDAD_MODE, PRESUPUESTO_MODE],
    },
    VIABILIDAD_MODE: {
        blocking: False,
        allows_digression: True,
        can_transition_to: [CONSULTA_MODE, PRESUPUESTO_MODE],
    },
    PRESUPUESTO_MODE: {
        blocking: False,
        allows_digression: False,  # Foco en presupuesto
        can_transition_to: [CONSULTA_MODE, VIABILIDAD_MODE, EVALUACION_GATEWAY],
    },
    EVALUACION_GATEWAY: {
        blocking: True,  # SÍ/NO explícito requerido
        allows_digression: False,
        can_transition_to: [PRESUPUESTO_MODE, EXPEDIENTE_MODE],
    },
    EXPEDIENTE_MODE: {
        blocking: True,  # Datos requeridos
        allows_digression: False,
        can_transition_to: [],  # Secuencial interno
    },
}
```

**Filtrado de herramientas**:
```python
def get_tools_for_mode(mode, sub_mode=None):
    base_tools = mode_tool_map[mode]
    
    if MODE_PROPERTIES[mode].blocking:
        # Estados bloqueantes: NO incluir consulta_durante_expediente
        return [t for t in base_tools if t.name != "consulta_durante_expediente"]
    else:
        # Estados permisivos: Incluir herramientas de digresión
        return base_tools + [consulta_durante_expediente]
```

---

## 🔄 Transiciones del Grafo

### Transiciones Permitidas

| Desde | Hacia | Condición |
|-------|-------|-----------|
| START | CONSULTA_MODE | Intent=consulta_general o ambiguo |
| START | VIABILIDAD_MODE | Intent=evaluar_viabilidad |
| START | PRESUPUESTO_MODE | Intent=presupuesto_directo |
| CONSULTA_MODE | VIABILIDAD_MODE | Usuario pregunta "¿Se puede X?" |
| CONSULTA_MODE | PRESUPUESTO_MODE | Usuario pide precio específico |
| VIABILIDAD_MODE | CONSULTA_MODE | Usuario tiene más preguntas generales |
| VIABILIDAD_MODE | PRESUPUESTO_MODE | Viabilidad confirmada + interés |
| PRESUPUESTO_MODE | CONSULTA_MODE | Usuario rechaza, vuelve a preguntar |
| PRESUPUESTO_MODE | VIABILIDAD_MODE | Usuario quiere evaluar otra cosa |
| PRESUPUESTO_MODE | EVALUACION_GATEWAY | Presupuesto aceptado |
| EVALUACION_GATEWAY | PRESUPUESTO_MODE | Usuario tiene dudas |
| EVALUACION_GATEWAY | EXPEDIENTE_MODE | Confirmación explícita |
| EXPEDIENTE_MODE | PRESUPUESTO_MODE | Desde revisión, modificar elementos |
| CUALQUIERA | (escalación) | Solicitud explícita o 3+ fallos |

### Transiciones PROHIBIDAS

| Desde | Hacia | Razón |
|-------|-------|-------|
| CONSULTA_MODE | EXPEDIENTE_MODE | Falta presupuesto |
| VIABILIDAD_MODE | EXPEDIENTE_MODE | Falta presupuesto detallado |
| EVALUACION_GATEWAY | CONSULTA_MODE | Ya hay presupuesto, decide sí/no |
| EXPEDIENTE_MODE | CONSULTA_MODE | Perdería todo el progreso del caso |
| EXPEDIENTE_MODE | START | Sin completar o cancelar explícitamente |

---

## 📊 Reciclaje de Componentes Actuales

### Mapeo de Herramientas Existentes

| Herramienta Actual | Nuevo Modo/Estado | Cambios Requeridos |
|--------------------|-------------------|-------------------|
| `listar_categorias` | CONSULTA_MODE | Ninguno |
| `listar_elementos` | CONSULTA_MODE, VIABILIDAD_MODE | Ninguno |
| `identificar_y_resolver_elementos` | PRESUPUESTO_MODE | Ninguno |
| `seleccionar_variante_por_respuesta` | PRESUPUESTO_MODE | Ninguno |
| `calcular_tarifa_con_elementos` | PRESUPUESTO_MODE | Ninguno |
| `enviar_imagenes_ejemplo` | PRESUPUESTO_MODE | Ninguno |
| `iniciar_expediente` | EVALUACION_GATEWAY → EXPEDIENTE_MODE | Agregar validación de confirmación |
| `confirmar_fotos_elemento` | EXPEDIENTE_MODE (DOC_ELEMENTOS) | Ninguno |
| `guardar_datos_elemento` | EXPEDIENTE_MODE (DOC_ELEMENTOS) | Ninguno |
| `completar_elemento_actual` | EXPEDIENTE_MODE (DOC_ELEMENTOS) | Ninguno |
| `actualizar_datos_expediente` | EXPEDIENTE_MODE (DATOS_*) | Dividir en personales/vehiculo |
| `actualizar_datos_taller` | EXPEDIENTE_MODE (TALLER) | Ninguno |
| `finalizar_expediente` | EXPEDIENTE_MODE (REVISION) | Ninguno |
| `escalar_a_humano` | TODOS | Siempre disponible |
| `consulta_durante_expediente` | Modos permisivos | Limitar a modos no-bloqueantes |

### Servicios que se Reciclan Sin Cambios

- `tarifa_service.py`
- `element_service.py`
- `element_required_fields_service.py`
- `collection_mode.py`
- `constraint_service.py`
- `tool_logging_service.py`
- `validation.py`

### Servicios que Requieren Ajustes

- `prompts/loader.py`: Agregar modos nuevos al `PHASE_MODULES`
- `tool_manager.py`: Mapear herramientas a modos (no solo a fsm_state)

---

## 📁 Estructura de Documentación Propuesta

```
docs/arquitectura-v2/
├── 00-propuesta-maestra.md                # Este documento
├── 01-filosofia-arquitectura.md           # Principios y decisiones
├── 02-modos-overview.md                   # Descripción de 4 modos
├── 03-modo-consulta.md                    # Detalle completo CONSULTA_MODE
├── 04-modo-viabilidad.md                  # Detalle completo VIABILIDAD_MODE
├── 05-modo-presupuesto.md                 # Detalle completo PRESUPUESTO_MODE
├── 06-modo-expediente.md                  # Detalle completo EXPEDIENTE_MODE
├── 07-transiciones-grafo.md               # Matriz de transiciones válidas
├── 08-herramientas-por-modo.md            # Inventario de herramientas
├── 09-solucion-gaps.md                    # Cómo resolvemos críticos
├── 10-reciclaje-componentes.md            # Qué se recicla de v1
├── 11-nuevos-componentes.md               # Qué hay que crear nuevo
├── 12-migracion-v1-v2.md                  # Plan de migración
├── 13-casos-uso-flujos.md                 # Ejemplos de conversaciones
└── 14-fallback-handler.md                 # Manejo de errores y recuperación
```

---

## 🎯 Plan de Implementación

### Fase 1: Preparación (1 semana)
1. Documentar completamente cada modo (este documento y sub-documentos)
2. Diseñar nuevas herramientas necesarias
3. Definir tests de aceptación por modo

### Fase 2: Implementación de Modos (3 semanas)
1. Semana 1: CONSULTA_MODE + VIABILIDAD_MODE + transiciones
2. Semana 2: PRESUPUESTO_MODE + EVALUACION_GATEWAY
3. Semana 3: EXPEDIENTE_MODE (con sub-modos)

### Fase 3: Solución de Gaps (1 semana)
1. Implementar timeouts por modo
2. **Implementar Fallback Handler** (política de reintentos por modo)
3. Implementar clasificador de intención
4. Integrar Digression Manager (Option B)

### Fase 4: Migración y Testing (2 semanas)
1. Testing paralelo v1 vs v2
2. Feature flags para rollout gradual
3. Rollback plan

---

## ✅ Checklist de Decisiones para Confirmar

- [ ] ¿Están de acuerdo con los 4 modos propuestos?
- [ ] ¿El flujo de VIABILIDAD_MODE → 65% de tráfico les funciona?
- [ ] ¿Está bien que EVALUACIÓN_GATEWAY sea bloqueante (sí/no explícito)?
- [ ] ¿Los timeouts propuestos (10-30 min) son apropiados?
- [ ] ¿Quieren conservar el expediente al final (no pedir datos antes)?
- [ ] ¿El plan de 7 semanas es viable?

---

**Próximo paso**: Si están de acuerdo con esta propuesta de alto nivel, procedo a crear los 13 documentos detallados en `docs/arquitectura-v2/`.

**¿Procedemos?** (responder: sí / ajustar / no)
