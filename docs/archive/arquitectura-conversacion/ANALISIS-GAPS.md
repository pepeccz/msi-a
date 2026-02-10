# Análisis de Gaps - Arquitectura de Conversación MSI-a

## 📋 Resumen Ejecutivo

Este documento documenta los **gaps críticos** entre la arquitectura ideal (plantilla) y la implementación real del sistema MSI-a. Fue generado mediante análisis estático del código fuente.

**Fecha de análisis**: Febrero 2026  
**Archivos analizados**: 15 módulos principales del agente  
**Método**: Búsqueda de patrones de reintentos, timeouts, manejo de errores y recuperación

---

## 🔴 GAPS CRÍTICOS (Riesgo Alto)

### Gap #1: Sin Timeouts de Estado por Inactividad

**Severidad**: 🔴 Crítico  
**Archivos afectados**: Todos los estados FSM  
**Líneas de código relevantes**: `case_collection.py:83-88`

#### Descripción

El sistema **no tiene** mecanismo para detectar cuando un usuario ha abandonado una conversación a mitad de un estado. El estado FSM persiste indefinidamente en Redis hasta que:
- El usuario responda (podrían ser días)
- Se reinicie el servidor (pérdida de datos si no hay persistencia)
- El TTL de Redis expire (24 horas por defecto)

#### Evidencia en Código

```python
# case_collection.py:83-88
class CaseFSMState(TypedDict, total=False):
    # ... otros campos ...
    retry_count: int  # Retries for current step
    error_message: str | None  # Last error if any
    # ❌ NO HAY: last_activity_timestamp, state_timeout, etc.

MAX_RETRIES_PER_STEP = 3
```

#### Escenario de Fallo

```
Usuario está en COLLECT_ELEMENT_DATA enviando fotos del elemento 2 de 3
Usuario recibe llamada telefónica importante y abandona el móvil
...
3 horas después:
Usuario vuelve y escribe "Hola"
Agente responde: "Elemento 2 de 3: Escape. Envíame las fotos..."
Usuario: "¿De qué hablas? Ya te envié las fotos hace 3 horas"
[Confusión total - las fotos se perdieron o el contexto cambió]
```

#### Impacto

- **UX**: Usuario desorientado al retornar
- **Recursos**: Estados huérfanos ocupando memoria en Redis
- **Datos**: Riesgo de pérdida si no hay persistencia en PostgreSQL
- **Operación**: Expedientes incompletos sin detección

#### Solución Propuesta

**Opción A: Timeout con Reset (Recomendada)**
```python
# Agregar a case_collection.py
STATE_INACTIVITY_TIMEOUT_MINUTES = 20

async def check_state_inactivity(fsm_state: CaseFSMState) -> bool:
    """Check if state has been inactive beyond timeout."""
    last_activity = fsm_state.get("last_activity_timestamp")
    if not last_activity:
        return False
    
    elapsed = (datetime.now(UTC) - last_activity).total_seconds() / 60
    return elapsed > STATE_INACTIVITY_TIMEOUT_MINUTES

# En conversational_agent_node, antes de procesar:
if await check_state_inactivity(case_state):
    # Resetear a IDLE con mensaje explicativo
    return {
        "fsm_state_update": reset_fsm(fsm_state),
        "messages": add_message(messages, "assistant", 
            "Veo que ha pasado un tiempo. Reiniciemos tu consulta...")
    }
```

**Opción B: Timeout con Nudge (Proactive)**
```python
# Agregar worker en main.py
async def inactivity_nudge_worker():
    """Send nudge messages to inactive conversations."""
    # Cada 5 minutos, buscar conversaciones inactivas > 15 min
    # Enviar: "¿Sigues ahí? Necesito que me confirmes para continuar..."
    # Si no respuesta en 10 min más → Resetear
```

**Complejidad**: Media (1-2 días de desarrollo)  
**Prioridad**: Alta - Afecta experiencia de usuario críticamente

---

### Gap #2: Política de Reintentos sin Acción de Escape

**Severidad**: 🔴 Crítico  
**Archivos afectados**: `case_collection.py`, `element_data_tools.py`  
**Líneas de código**: `case_collection.py:88`, `case_collection.py:83`

#### Descripción

Existe la constante `MAX_RETRIES_PER_STEP = 3` y el campo `retry_count` en el estado, **pero nunca se verifica ni se actúa** cuando se alcanza el límite.

#### Evidencia en Código

```python
# case_collection.py:88
MAX_RETRIES_PER_STEP = 3  # ✅ Definido

# case_collection.py:83
retry_count: int  # ✅ Existe en estado

# case_collection.py:741, 607
"retry_count": 0,  # ✅ Se resetea en transiciones

# ❌ PERO EN NINGÚN LUGAR:
# if retry_count >= MAX_RETRIES_PER_STEP:
#     escalate_to_human()
```

#### Escenario de Fallo

```
Agente: "¿Cuál es tu email?"
Usuario: "juan"
Agente: "El formato no es válido. Usa formato email@ejemplo.com"
Usuario: "juan@gmail"
Agente: "Todavía no es válido. Intenta de nuevo."
Usuario: "no tengo email"
Agente: "Necesito un email válido para continuar."
Usuario: "ya te dije que no tengo"
Agente: "Por favor, proporciona un email válido."
[Usuario: "..."]
[Bucle infinito potencial]
```

#### Impacto

- **UX**: Usuario atrapado en bucle de validación
- **Escalación**: No hay mecanismo de escape forzado
- **Satisfacción**: Frustración del usuario, posible abandono

#### Solución Propuesta

```python
# En element_data_tools.py - guardar_datos_elemento()
# O en case_tools.py - actualizar_datos_expediente()

MAX_RETRIES_PER_STEP = 3

async def handle_validation_failure(fsm_state, field_name):
    """Handle repeated validation failures."""
    retry_count = fsm_state.get("retry_count", 0) + 1
    
    if retry_count >= MAX_RETRIES_PER_STEP:
        # Forzar escalación
        return {
            "success": False,
            "action": "FORCE_ESCALATION",
            "message": (
                "Parece que estamos teniendo dificultades con este dato. "
                "Te conecto con un agente humano que podrá ayudarte mejor."
            ),
            "escalation_reason": f"validation_failed_{field_name}"
        }
    
    # Continuar normal con retry_count incrementado
    return {
        "success": False,
        "retry_count": retry_count,
        "message": f"Intento {retry_count}/{MAX_RETRIES_PER_STEP}: El dato no es válido..."
    }
```

**Complejidad**: Baja (4-6 horas)  
**Prioridad**: Alta - Impacto directo en experiencia de usuario

---

### Gap #3: Sin Detección de Fallos NLU

**Severidad**: 🔴 Crítico  
**Archivos afectados**: `conversational_agent.py`  
**Líneas de código**: `conversational_agent.py:590-700` (node principal)

#### Descripción

El sistema **no detecta** cuando el LLM no ha entendido la intención del usuario. No hay:
- Umbral de confianza mínima (`intent_confidence`)
- Contador de "no entendimientos" consecutivos
- Fallback a intención por defecto

#### Evidencia en Código

```python
# conversational_agent.py
# El LLM recibe el mensaje y genera respuesta
# ❌ NO HAY:
# - Verificación de confidence_score
# - Detección de "no_tool_called" cuando debería haberse llamado
# - Detección de respuesta genérica/vacía

# Lo más cercano es constraint validation, pero eso es POST-generación:
validation_result = await validate_response(
    ai_content, 
    tools_used,
    fsm_state
)
# Esto valida si la respusa cumple constraints, no si entendió al usuario
```

#### Escenario de Fallo

```
Usuario: "La verdad es que no estoy seguro de qué necesito exactamente"
[LLM no reconoce intención clara, no llama ninguna herramienta]
Agente: "Entiendo. ¿En qué más puedo ayudarte?"
[Respuesta genérica sin contenido útil]
Usuario: "Es que mi moto tiene algo raro en el escape"
Agente: "¿Qué tipo de ayuda necesitas con tu moto?"
[Ciclo de confusión - el agente no guía, no identifica que podría ser presupuesto]
```

#### Impacto

- **Conversaciones huérfanas**: El agente no guía al usuario
- **Tasa de conversión**: Usuario no llega a presupuesto
- **Escalaciones innecesarias**: Usuario se frustra y pide humano

#### Solución Propuesta

**Opción A: Intent Classification Explícito (Recomendada)**
```python
# Nuevo módulo: agent/nlu/intent_classifier.py

class IntentClassifier:
    INTENTS = ["presupuesto", "consulta", "expediente", "escalacion", "ambiguo"]
    
    async def classify(self, message: str, context: dict) -> IntentResult:
        # Usar modelo ligero (qwen2.5:3b local) para clasificar
        confidence, intent = await self._classify(message)
        
        if confidence < 0.7:
            return IntentResult(
                intent="ambiguo",
                confidence=confidence,
                action="CLARIFY"
            )
        
        return IntentResult(intent=intent, confidence=confidence)
```

**Opción B: Detección de No-Tool-Called**
```python
# En conversational_agent.py

if not any(tool_called for tool_called in tool_calls):
    # LLM no llamó ninguna herramienta cuando debería haberlo hecho
    no_tool_count = state.get("no_tool_count", 0) + 1
    
    if no_tool_count >= 2:
        # Forzar sugerencia o escalación
        return {
            "messages": add_message(messages, "assistant",
                "No estoy seguro de entender. ¿Quieres un presupuesto, "
                "tienes una consulta general, o prefieres hablar con una persona?")
        }
```

**Complejidad**: Alta (3-5 días)  
**Prioridad**: Alta - Mejora dramáticamente la robustez

---

## 🟡 GAPS MEDIOS (Riesgo Moderado)

### Gap #4: Sin Diferenciación de Estados Bloqueantes

**Severidad**: 🟡 Medio  
**Archivos afectados**: Todos los estados FSM

#### Descripción

No hay distinción formal entre estados donde:
- El usuario **debe** responder específicamente (bloqueantes)
- El usuario **puede** hacer consultas adicionales (permisivos)

El comportamiento depende del prompt de fase, no de una flag explícita.

#### Evidencia

```python
# tool_manager.py - get_tools_for_phase()
# Todos los estados (excepto IDLE) tienen disponible:
# - consulta_durante_expediente()
# - obtener_estado_expediente()
# - escalar_a_humano()
# - cancelar_expediente()

# Pero el comportamiento real varía según el prompt:
# collect_element_data.md: "Enfócate en recolectar datos"
# review_summary.md: "El usuario debe confirmar sí o no"
```

#### Inconsistencias Observadas

| Estado | Bloqueante en Práctica | Herramientas de Digresión | Conflicto |
|--------|----------------------|---------------------------|-----------|
| COLLECT_ELEMENT_DATA | Parcial (fotos sí, consultas técnicas) | ✅ Disponibles | ⚠️ Sí |
| COLLECT_BASE_DOCS | Parcial | ✅ Disponibles | ⚠️ Sí |
| REVIEW_SUMMARY | **Sí** (debe confirmar) | ✅ Disponibles | 🔴 **Sí** |

#### Solución Propuesta

```python
# case_collection.py

class CollectionStep(str, Enum):
    IDLE = "idle"
    COLLECT_ELEMENT_DATA = "collect_element_data"
    # ... otros ...
    REVIEW_SUMMARY = "review_summary"

# Agregar propiedades
STEP_PROPERTIES = {
    CollectionStep.IDLE: {"blocking": False, "allows_digression": True},
    CollectionStep.COLLECT_ELEMENT_DATA: {"blocking": True, "allows_digression": False},
    CollectionStep.REVIEW_SUMMARY: {"blocking": True, "allows_digression": False},
    # ... etc ...
}

# En conversational_agent.py
if STEP_PROPERTIES[current_step]["blocking"]:
    # Filtrar herramientas de digresión
    available_tools = [t for t in tools if t.name != "consulta_durante_expediente"]
```

**Complejidad**: Baja (1 día)  
**Prioridad**: Media - Clarifica comportamiento

---

### Gap #5: Manejo de Errores de Herramientas sin Escalación Progresiva

**Severidad**: 🟡 Medio  
**Archivos afectados**: `utils/errors.py`, `tools/*`

#### Descripción

Existe manejo de errores (`handle_tool_errors` decorator) pero:
- Muestra mensaje genérico siempre
- No hay backoff progresivo
- No hay escalación tras N fallos consecutivos del mismo tipo

#### Evidencia

```python
# utils/errors.py:164
@handle_tool_errors(
    error_category=ErrorCategory.DATABASE_ERROR,
    error_code="DB_QUERY_FAILED",
    user_message="Lo siento, hubo un problema técnico. ¿Puedes intentarlo de nuevo?",
)
async def some_tool():
    # Si falla, muestra el mismo mensaje siempre
    # ❌ No cuenta cuántas veces ha fallado esta herramienta
    # ❌ No escala si el fallo es persistente
```

#### Escenario

```
[Base de datos caída temporalmente]
Usuario: "Quiero homologar el escape"
Agente: "Lo siento, hubo un problema técnico. ¿Puedes intentarlo de nuevo?"
Usuario: [reintenta]
Agente: "Lo siento, hubo un problema técnico. ¿Puedes intentarlo de nuevo?"
Usuario: [reintenta]
Agente: "Lo siento, hubo un problema técnico. ¿Puedes intentarlo de nuevo?"
[Usuario se frustra, abandona]
```

#### Solución Propuesta

```python
# Agregar a tool_logging_service.py o nuevo service

class ToolFailureTracker:
    """Track consecutive failures per tool type."""
    
    async def record_failure(self, tool_name: str, conversation_id: str):
        key = f"failures:{conversation_id}:{tool_name}"
        count = await redis.incr(key)
        await redis.expire(key, 3600)  # 1 hora TTL
        return count
    
    async def should_escalate(self, tool_name: str, conversation_id: str) -> bool:
        count = await self.get_failure_count(tool_name, conversation_id)
        return count >= 3  # Escalar tras 3 fallos

# En tools, usar:
async def some_tool():
    try:
        return await db_operation()
    except Exception as e:
        failure_count = await failure_tracker.record_failure("some_tool", conv_id)
        if await failure_tracker.should_escalate("some_tool", conv_id):
            return {
                "success": False,
                "action": "ESCALATE",
                "message": "Parece que hay un problema técnico persistente..."
            }
        raise  # Deja que handle_tool_errors maneje
```

**Complejidad**: Media (1-2 días)  
**Prioridad**: Media - Mejora resiliencia

---

## 🟢 GAPS BAJOS (Mejoras Deseables)

### Gap #6: Sin Reciclaje Inteligente de Datos

**Estado**: 🟢 Funciona básicamente, pero puede mejorar

**Actual**: Se cargan datos previos de usuario pero la experiencia podría ser más fluida.

**Mejora**: Autocompletar proactivamente campos obvios (email, teléfono desde WhatsApp).

### Gap #7: Validaciones Síncronas Podrían Ser Async

**Estado**: 🟢 Funciona

Algunas validaciones (formato email, DNI) son regex síncronas. Podrían hacerse async para no bloquear.

---

## 📊 Matriz de Priorización

| Gap | Severidad | Complejidad | Esfuerzo | Prioridad Recomendada |
|-----|-----------|-------------|----------|----------------------|
| #1 Timeouts de Estado | 🔴 Alta | Media | 1-2 días | **P0** - Crítico |
| #2 Reintentos sin Escape | 🔴 Alta | Baja | 4-6 horas | **P0** - Crítico |
| #3 Detección NLU | 🔴 Alta | Alta | 3-5 días | **P1** - Alto |
| #4 Estados Bloqueantes | 🟡 Media | Baja | 1 día | **P2** - Medio |
| #5 Errores de Herramientas | 🟡 Media | Media | 1-2 días | **P2** - Medio |
| #6 Reciclaje Inteligente | 🟢 Baja | Media | 2-3 días | P3 - Bajo |
| #7 Validaciones Async | 🟢 Baja | Baja | 4 horas | P3 - Bajo |

---

## 🎯 Recomendaciones de Implementación

### Fase 1 (Inmediato - 1 semana)
1. Implementar Gap #2 (Reintentos con escape) - Impacto inmediato, esfuerzo bajo
2. Implementar Gap #1 (Timeouts) - Mejora experiencia drásticamente

### Fase 2 (Corto plazo - 2-3 semanas)
3. Implementar Gap #3 (Detección NLU) - Requiere más diseño y testing
4. Implementar Gap #4 (Estados bloqueantes) - Clarifica arquitectura

### Fase 3 (Mediano plazo)
5. Gap #5 (Errores de herramientas)
6. Gaps #6-7 (Mejoras)

---

## 📞 Notas para el Equipo

**Cómo usar este análisis**:
1. Los gaps P0 deben entrar en el próximo sprint
2. Cada gap tiene evidencia de código real - no es especulación
3. Las soluciones propuestas son puntos de partida, no dogma
4. Al implementar, actualizar este documento para reflejar estado real

**Mantenimiento**:
- Revisar este análisis cada 3 meses
- Actualizar al detectar nuevos gaps
- Marcar como "resuelto" cuando se implemente solución

---

**Documento generado mediante análisis estático del código MSI-a**  
**Versión**: 1.0  
**Fecha**: Febrero 2026
