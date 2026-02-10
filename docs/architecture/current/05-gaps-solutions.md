# Solución a Gaps Críticos

## 🎯 Resumen de Gaps Identificados

| Gap | Severidad | Solución Propuesta | Esfuerzo |
|-----|-----------|-------------------|----------|
| **#1 Timeouts de estado** | 🔴 Crítico | Timeouts por modo con nudge progresivo | 2 días |
| **#2 Reintentos sin escape** | 🔴 Crítico | Política por modo con acción definida | 1 día |
| **#3 Sin detección NLU** | 🔴 Crítico | Clasificador de intención explícito | 3 días |
| **#4 Estados bloqueantes** | 🟡 Medio | Definición explícita en cada modo | 1 día |

---

## 🔴 Gap #1: Timeouts de Estado

### Problema Actual

El sistema no detecta cuando un usuario abandona una conversación a mitad de un estado. El estado FSM persiste indefinidamente en Redis.

**Evidencia**: No existe `last_activity_timestamp` ni mecanismo de timeout en `case_collection.py`.

### Solución de Raíz: Timeouts por Modo

Cada modo define su propio timeout según la complejidad esperada:

```python
# Nueva configuración en config.py o modo_config.py
MODE_TIMEOUTS = {
    # Modo -> Segundos de inactividad antes de nudge
    CONSULTA_MODE: 600,      # 10 min - consultas simples
    VIABILIDAD_MODE: 900,    # 15 min - requiere búsqueda
    PRESUPUESTO_MODE: 1200,  # 20 min - puede iterar
    EVALUACION_GATEWAY: 300, # 5 min - decisión rápida
    EXPEDIENTE_MODE: 1800,   # 30 min - por sub-modo
}

# Doble del timeout para reset completo
MODE_RESET_TIMEOUTS = {k: v * 2 for k, v in MODE_TIMEOUTS.items()}
```

### Implementación

#### Paso 1: Agregar timestamp de actividad

```python
# En ConversationState o modo state
class ConversationState(TypedDict, total=False):
    # ... campos existentes ...
    
    # Nuevo campo para tracking de actividad
    last_activity_timestamp: datetime
    current_mode: str  # Modo actual (no solo FSM state)
    mode_entry_timestamp: datetime  # Cuándo entró al modo actual
```

#### Paso 2: Actualizar timestamp en cada mensaje

```python
# En process_incoming_message_node
async def process_incoming_message_node(state: ConversationState):
    # ... lógica existente ...
    
    return {
        # ... updates existentes ...
        "last_activity_timestamp": datetime.now(UTC),
    }
```

#### Paso 3: Verificar timeout antes de procesar

```python
# En entry point del grafo, antes de llamar al modo actual
async def check_mode_timeout(state: ConversationState):
    current_mode = state.get("current_mode", CONSULTA_MODE)
    last_activity = state.get("last_activity_timestamp")
    
    if not last_activity:
        return TimeoutCheckResult.OK
    
    elapsed_seconds = (datetime.now(UTC) - last_activity).total_seconds()
    timeout = MODE_TIMEOUTS.get(current_mode, 600)
    
    if elapsed_seconds > timeout * 2:
        # Doble timeout: Reset completo
        return TimeoutCheckResult.RESET_TO_DEFAULT
    elif elapsed_seconds > timeout:
        # Timeout simple: Nudge
        return TimeoutCheckResult.SEND_NUDGE
    else:
        return TimeoutCheckResult.OK

# Uso en el grafo
@entry_point
def conversation_entry(state: ConversationState):
    timeout_check = await check_mode_timeout(state)
    
    if timeout_check == TimeoutCheckResult.RESET_TO_DEFAULT:
        # Resetear a CONSULTA_MODE con mensaje
        return {
            "current_mode": CONSULTA_MODE,
            "messages": add_message(
                state["messages"],
                "assistant",
                "Reiniciamos la conversación por inactividad. "
                "¿En qué puedo ayudarte hoy?"
            ),
            "context": reset_context_keep_drafts(state.get("context", {})),
        }
    elif timeout_check == TimeoutCheckResult.SEND_NUDGE:
        # Enviar nudge y quedarse en modo actual
        return {
            "messages": add_message(
                state["messages"],
                "assistant",
                "¿Sigues ahí? Respondé cualquier cosa para continuar."
            ),
            "last_nudge_sent": datetime.now(UTC),
        }
```

### Mensajes de Nudge por Modo

| Modo | Nudge (1x timeout) | Reset (2x timeout) |
|------|-------------------|-------------------|
| CONSULTA | "¿Sigues ahí? Respondé para continuar." | "Reiniciamos. ¿Qué Quieres saber?" |
| VIABILIDAD | "¿Quieres que busque ese presupuesto?" | "Volvamos a empezar. ¿Qué necesitás?" |
| PRESUPUESTO | "¿Guardo este presupuesto y volvés luego?" | "Reiniciamos. Tenés un borrador guardado." |
| EVALUACIÓN | "¿Confirmás que Quieres iniciar el expediente?" | "Volvamos al presupuesto. ¿Tenías dudas?" |
| EXPEDIENTE | "¿Estás teniendo dificultades? Te puedo conectar con alguien." | "Guardamos tu progreso. Contactá un agente para continuar." |

### Preservación de Contexto

```python
def reset_context_keep_drafts(context: dict) -> dict:
    """Al resetear, preservar borradores útiles."""
    preserved = {}
    
    # Preservar presupuesto calculado
    if "draft_quote" in context:
        preserved["draft_quote"] = context["draft_quote"]
    
    # Preservar datos de usuario si ya los teníamos
    if "user_data" in context:
        preserved["user_data"] = context["user_data"]
    
    return preserved
```

---

## 🔴 Gap #2: Política de Reintentos sin Escape

### Problema Actual

`MAX_RETRIES_PER_STEP = 3` existe pero no tiene acción definida al alcanzar el límite. El usuario puede quedar atrapado en bucle infinito de validación fallida.

### Solución de Raíz: Política por Modo

Cada modo define su estrategia de reintentos y acción al alcanzar el límite:

```python
MODE_RETRY_POLICIES = {
    CONSULTA_MODE: {
        "max_retries": 3,
        "action_on_limit": "escalate_to_human",
        "message": "Parece que no estamos entendiéndonos bien. Te conecto con un agente."
    },
    VIABILIDAD_MODE: {
        "max_retries": 3,
        "action_on_limit": "escalate_to_human",
        "message": "Esta consulta requiere evaluación técnica especializada. Te conecto con un experto."
    },
    PRESUPUESTO_MODE: {
        "max_retries": 5,  # Más tolerante
        "action_on_limit": "return_to_viabilidad",
        "message": "Parece que este presupuesto no se ajusta a lo que necesitás. ¿Quieres evaluar otras opciones?"
    },
    EXPEDIENTE_MODE: {
        "max_retries": 3,
        "action_on_limit": "escalate_with_progress",
        "message": "Parece que estás teniendo dificultades con los datos. Te conecto con un agente que te ayude."
    },
}
```

### Implementación

#### Paso 1: Contador por modo (no global)

```python
class ConversationState(TypedDict, total=False):
    # ... campos existentes ...
    
    # Nuevo: Contador de reintentos por modo
    mode_retry_counts: dict[str, int]  # {mode_name: count}
    last_retry_mode: str | None  # Para detectar cambio de modo
```

#### Paso 2: Incrementar contador en fallos

```python
async def handle_mode_failure(state: ConversationState, mode: str, failure_type: str):
    """Manejar fallo dentro de un modo."""
    retry_counts = state.get("mode_retry_counts", {})
    current_count = retry_counts.get(mode, 0) + 1
    
    policy = MODE_RETRY_POLICIES.get(mode, MODE_RETRY_POLICIES[CONSULTA_MODE])
    max_retries = policy["max_retries"]
    
    if current_count >= max_retries:
        # Alcanzado límite: ejecutar acción definida
        return await execute_retry_limit_action(state, mode, policy)
    else:
        # Aún hay reintentos: incrementar y continuar
        retry_counts[mode] = current_count
        return {
            "mode_retry_counts": retry_counts,
            "retry_message": f"Intento {current_count}/{max_retries}. " + get_retry_guidance(failure_type),
        }
```

#### Paso 3: Acciones al alcanzar límite

```python
async def execute_retry_limit_action(state: ConversationState, mode: str, policy: dict):
    """Ejecutar acción definida cuando se alcanza límite de reintentos."""
    action = policy["action_on_limit"]
    message = policy["message"]
    
    if action == "escalate_to_human":
        return {
            "escalation_triggered": True,
            "escalation_reason": f"retry_limit_exceeded_{mode}",
            "messages": add_message(
                state["messages"],
                "assistant",
                message
            ),
        }
    
    elif action == "return_to_viabilidad":
        return {
            "current_mode": VIABILIDAD_MODE,
            "messages": add_message(
                state["messages"],
                "assistant",
                message
            ),
            "mode_retry_counts": {},  # Resetear contadores
        }
    
    elif action == "escalate_with_progress":
        # Guardar progreso parcial y escalar
        return {
            "escalation_triggered": True,
            "escalation_reason": f"retry_limit_with_progress_{mode}",
            "partial_case_data": extract_partial_data(state),
            "messages": add_message(
                state["messages"],
                "assistant",
                message
            ),
        }
```

#### Paso 4: Resetear al cambiar de modo

```python
async def transition_mode(state: ConversationState, new_mode: str):
    """Transicionar a nuevo modo, resetear contador si es modo diferente."""
    current_mode = state.get("current_mode")
    
    if current_mode != new_mode:
        # Cambio de modo: resetear contador del modo anterior
        retry_counts = state.get("mode_retry_counts", {})
        if current_mode in retry_counts:
            retry_counts[current_mode] = 0
        
        return {
            "current_mode": new_mode,
            "mode_retry_counts": retry_counts,
            "mode_entry_timestamp": datetime.now(UTC),
        }
```

### Tipos de Fallo y Guías

```python
def get_retry_guidance(failure_type: str) -> str:
    """Mensaje específico según tipo de fallo."""
    guidance = {
        "nlu_failure": "Intentá ser más específico.",
        "validation_error": "Revisá el formato que te pedí.",
        "tool_error": "Hubo un problema técnico. Intentá de nuevo.",
        "ambiguous_response": "Por favor, respondé sí o no claramente.",
    }
    return guidance.get(failure_type, "Intentá de nuevo.")
```

---

## 🔴 Gap #3: Sin Detección de Fallos NLU

### Problema Actual

El sistema no detecta cuando el LLM no ha entendido la intención del usuario. No hay umbral de confianza ni fallback.

### Solución de Raíz: Clasificador de Intención Explícito

#### Paso 1: Nuevo servicio de clasificación

```python
# agent/services/intent_classifier.py

from enum import Enum
from typing import NamedTuple

class UserIntent(Enum):
    CONSULTA_GENERAL = "consulta_general"
    EVALUAR_VIABILIDAD = "evaluar_viabilidad"
    PRESUPUESTO_DIRECTO = "presupuesto_directo"
    INICIAR_EXPEDIENTE = "iniciar_expediente"
    ESCALAR = "escalar"
    AMBIGUO = "ambiguo"

class IntentResult(NamedTuple):
    intent: UserIntent
    confidence: float
    suggested_mode: str
    clarification_question: str | None

class IntentClassifier:
    """Clasifica intención del usuario usando modelo ligero local."""
    
    CONFIDENCE_THRESHOLD = 0.75
    
    async def classify(self, message: str, history: list[dict]) -> IntentResult:
        """
        Clasificar mensaje del usuario.
        Usa modelo local (qwen2.5:3b) para velocidad y costo.
        """
        # Preparar prompt de clasificación
        classification_prompt = self._build_classification_prompt(message, history)
        
        # Llamar modelo ligero
        response = await self.llm_light.invoke(classification_prompt)
        
        # Parsear respuesta
        intent_str, confidence = self._parse_classification_response(response)
        intent = UserIntent(intent_str)
        
        if confidence >= self.CONFIDENCE_THRESHOLD:
            return IntentResult(
                intent=intent,
                confidence=confidence,
                suggested_mode=self._intent_to_mode(intent),
                clarification_question=None,
            )
        else:
            # Confianza baja: pedir clarificación
            return IntentResult(
                intent=UserIntent.AMBIGUO,
                confidence=confidence,
                suggested_mode=CONSULTA_MODE,  # Default seguro
                clarification_question=self._generate_clarification_question(message),
            )
    
    def _build_classification_prompt(self, message: str, history: list[dict]) -> str:
        return f"""Clasifica la intención del siguiente mensaje de usuario en una conversación sobre homologación de vehículos.

Mensaje: "{message}"

Opciones:
- consulta_general: Preguntas sobre qué es homologación, proceso, legalidad
- evaluar_viabilidad: Preguntas tipo "¿Se puede homologar X?", "¿Es posible Y?"
- presupuesto_directo: Solicitudes de precio específico "¿Cuánto cuesta Z?"
- iniciar_expediente: Intención explícita de empezar trámite
- escalar: Solicitud de hablar con humano

Respondé SOLO en este formato:
intent: <opción>
confidence: <0.0-1.0>
"""
    
    def _intent_to_mode(self, intent: UserIntent) -> str:
        mapping = {
            UserIntent.CONSULTA_GENERAL: CONSULTA_MODE,
            UserIntent.EVALUAR_VIABILIDAD: VIABILIDAD_MODE,
            UserIntent.PRESUPUESTO_DIRECTO: PRESUPUESTO_MODE,
            UserIntent.INICIAR_EXPEDIENTE: EVALUACION_GATEWAY,  # Validar primero
            UserIntent.ESCALAR: "ESCALACION",
        }
        return mapping.get(intent, CONSULTA_MODE)
    
    def _generate_clarification_question(self, message: str) -> str:
        return (
            "No estoy seguro de entender qué necesitás. "
            "¿Buscás información general sobre homologación, "
            "evaluar si algo específico se puede homologar, "
            "o un presupuesto para una modificación?"
        )
```

#### Paso 2: Integrar en entry point

```python
# En entry point del grafo
async def conversation_entry(state: ConversationState):
    user_message = state.get("user_message", "")
    history = state.get("messages", [])
    
    # Clasificar intención
    intent_result = await intent_classifier.classify(user_message, history)
    
    if intent_result.intent == UserIntent.ESCALAR:
        # Escalación inmediata
        return await handle_escalation_request(state)
    
    elif intent_result.confidence >= 0.75:
        # Confianza alta: ir al modo sugerido
        return await transition_to_mode(state, intent_result.suggested_mode)
    
    else:
        # Confianza baja: CONSULTA_MODE con pregunta de clarificación
        return {
            "current_mode": CONSULTA_MODE,
            "messages": add_message(
                state["messages"],
                "assistant",
                intent_result.clarification_question
            ),
            "pending_intent_clarification": True,
        }
```

#### Paso 3: Manejar clarificación

```python
async def handle_intent_clarification(state: ConversationState):
    """Manejar respuesta a pregunta de clarificación."""
    user_response = state.get("user_message", "").lower()
    
    if any(word in user_response for word in ["información", "cómo", "qué es"]):
        return await transition_to_mode(state, CONSULTA_MODE)
    
    elif any(word in user_response for word in ["evaluar", "se puede", "posible"]):
        return await transition_to_mode(state, VIABILIDAD_MODE)
    
    elif any(word in user_response for word in ["presupuesto", "precio", "cuánto"]):
        return await transition_to_mode(state, PRESUPUESTO_MODE)
    
    else:
        # Todavía ambiguo, escalar o seguir en consulta
        return {
            "messages": add_message(
                state["messages"],
                "assistant",
                "Entiendo. Contame qué modificación Quieres hacer a tu vehículo y te ayudo."
            ),
        }
```

### Fallback cuando el LLM principal no entiende

```python
async def detect_nlu_failure(state: ConversationState, llm_response: str, tools_called: list):
    """Detectar si el LLM no entendió y no llamó herramientas relevantes."""
    
    current_mode = state.get("current_mode")
    expected_tools = MODE_TOOLS.get(current_mode, [])
    
    # Si no llamó ninguna herramienta esperada, probablemente no entendió
    if not any(tool in tools_called for tool in expected_tools):
        no_tool_count = state.get("no_tool_count", 0) + 1
        
        if no_tool_count >= 2:
            # Dos veces sin llamar herramientas: escalar o pedir clarificación
            return {
                "no_tool_count": 0,  # Resetear
                "messages": add_message(
                    state["messages"],
                    "assistant",
                    "No estoy seguro de entender bien. ¿Quieres que te conecte con un agente?"
                ),
            }
        else:
            return {
                "no_tool_count": no_tool_count,
                "messages": add_message(
                    state["messages"],
                    "assistant",
                    "¿Podés ser más específico sobre qué necesitás?"
                ),
            }
```

---

## 🟡 Gap #4: Sin Diferenciación Estados Bloqueantes

### Solución

Definición explícita en cada modo:

```python
MODE_PROPERTIES = {
    CONSULTA_MODE: {
        "blocking": False,
        "allows_digression": True,
        "can_transition_to": [VIABILIDAD_MODE, PRESUPUESTO_MODE],
        "required_progress": None,  # No requiere completitud
    },
    VIABILIDAD_MODE: {
        "blocking": False,
        "allows_digression": True,
        "can_transition_to": [CONSULTA_MODE, PRESUPUESTO_MODE],
        "required_progress": None,
    },
    PRESUPUESTO_MODE: {
        "blocking": False,
        "allows_digression": False,  # Foco en presupuesto
        "can_transition_to": [CONSULTA_MODE, VIABILIDAD_MODE, EVALUACION_GATEWAY],
        "required_progress": "tarifa_calculada",
    },
    EVALUACION_GATEWAY: {
        "blocking": True,  # Requiere decisión explícita
        "allows_digression": False,
        "can_transition_to": [PRESUPUESTO_MODE, EXPEDIENTE_MODE],
        "required_progress": "confirmacion_explicita",
    },
    EXPEDIENTE_MODE: {
        "blocking": True,
        "allows_digression": False,
        "can_transition_to": [],  # Navegación interna
        "required_progress": "case_complete",
    },
}
```

Filtrado de herramientas:
```python
def get_tools_for_mode(mode: str) -> list:
    base_tools = MODE_TOOLS[mode]
    props = MODE_PROPERTIES[mode]
    
    if props["blocking"]:
        # Estados bloqueantes: solo herramientas esenciales
        return [t for t in base_tools if t.name not in [
            "consulta_durante_expediente",
            "obtener_estado_expediente"
        ]]
    else:
        # Estados permisivos: todas las herramientas
        return base_tools
```

---

## 📁 Implementación y Testing

### Tests de Aceptación por Gap

#### Gap #1: Timeouts
```python
async def test_mode_timeout_nudge():
    # Simular inactividad de 11 minutos en CONSULTA_MODE
    state = create_test_state(mode=CONSULTA_MODE, inactive_minutes=11)
    result = await check_mode_timeout(state)
    assert result.action == TimeoutAction.NUDGE

async def test_mode_timeout_reset():
    # Simular inactividad de 25 minutos en CONSULTA_MODE
    state = create_test_state(mode=CONSULTA_MODE, inactive_minutes=25)
    result = await check_mode_timeout(state)
    assert result.action == TimeoutAction.RESET
    assert result.new_mode == CONSULTA_MODE
```

#### Gap #2: Reintentos
```python
async def test_retry_limit_escalation():
    # Simular 3 fallos consecutivos en EXPEDIENTE_MODE
    state = create_test_state(
        mode=EXPEDIENTE_MODE,
        retry_counts={EXPEDIENTE_MODE: 3}
    )
    result = await handle_mode_failure(state, EXPEDIENTE_MODE, "validation_error")
    assert result["escalation_triggered"] == True
```

#### Gap #3: Clasificación
```python
async def test_intent_classification_high_confidence():
    message = "¿Cuánto cuesta homologar un escape?"
    result = await intent_classifier.classify(message, [])
    assert result.intent == UserIntent.PRESUPUESTO_DIRECTO
    assert result.confidence >= 0.75
    assert result.suggested_mode == PRESUPUESTO_MODE

async def test_intent_classification_low_confidence():
    message = "Hola, tengo una duda"
    result = await intent_classifier.classify(message, [])
    assert result.intent == UserIntent.AMBIGUO
    assert result.confidence < 0.75
    assert result.clarification_question is not None
```

---

**Nota**: Estas soluciones son implementables de forma incremental. Se puede empezar con Gap #2 (reintentos) que es el más simple, y avanzar hacia Gap #3 (NLU) que requiere más diseño.
