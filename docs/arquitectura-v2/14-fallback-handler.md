# Fallback Handler en Arquitectura v2.0

## 🎯 Propósito

El **Fallback Handler** es el mecanismo de recuperación cuando el agente no entiende al usuario después de múltiples intentos. Reemplaza el `MAX_RETRIES` actual que no tiene acción definida.

**Principio clave**: Cada modo decide su propia política de recuperación.

---

## 🏗️ Arquitectura

### Diseño: "El Nodo Decide"

A diferencia de un handler externo, cada **nodo de modo** implementa su propia lógica de fallback:

```python
# En cada nodo de modo (consulta_mode.py, viabilidad_mode.py, etc.)

class ConsultaModeNode(BaseModeNode):
    async def process(self, message, context, history):
        try:
            # Intentar procesar
            result = await self._process_message(...)
            
            # Éxito: resetear contador de reintentos
            self.record_success()
            return result
            
        except Error as e:
            # Error: incrementar contador y verificar fallback
            self.record_error(e)
            
            if self.should_fallback():
                # Ejecutar acción definida por el modo
                return self.execute_fallback_action()
            else:
                # Repreguntar con mensaje progresivo
                return self.get_reprompt_message()
```

---

## 📋 Políticas por Modo

Cada modo define su `RetryPolicy`:

| Modo | Max Retries | Acción al Límite | Estrategia Reprompt |
|------|-------------|------------------|---------------------|
| **CONSULTA_MODE** | 3 | `OFFER_HUMAN_HELP` | Progresiva |
| **VIABILIDAD_MODE** | 3 | `ESCALATE_TO_HUMAN` | Progresiva |
| **PRESUPUESTO_MODE** | 5 | `RESET_TO_VIABILIDAD` | Simplificar |
| **EVALUACION_GATEWAY** | 2 | `RESET_TO_PRESUPUESTO` | Misma pregunta |
| **EXPEDIENTE_MODE** | 3 | `OFFER_HUMAN_HELP` | Progresiva |

### ¿Por qué PRESUPUESTO_MODE tiene 5 reintentos?

Los usuarios en modo presupuesto **exploran opciones**:
- "Agregá el filtro"
- "No, sacá el escape"
- "¿Y si solo homologo el manillar?"
- "Cuánto era sin IVA?"

Necesitamos más tolerancia antes de considerar que "no entendemos".

---

## 🔄 Flujo de Fallback

### Secuencia Normal (Sin Errores)

```
Usuario: "¿Qué es homologación?"
         ↓
    [CONSULTA_MODE]
         ↓
Agente: "La homologación es el proceso de..."
         ↓
Usuario: "¿Es obligatoria?"
         ↓
    [CONSULTA_MODE]
         ↓
Agente: "Sí, es obligatoria cuando..."
```

### Secuencia con Errores (Trigger Fallback)

```
Usuario: "¿Es homologable?"
         ↓
    [CONSULTA_MODE - Retry 1/3]
         ↓
Agente: "Perdón, no entendí bien. ¿Podés reformular tu pregunta?"
         ↓
Usuario: "El escape, se puede?"
         ↓
    [CONSULTA_MODE - Retry 2/3]
         ↓
Agente: "No estoy entendiendo bien. ¿Podés ser más específico sobre qué querés saber de homologación?"
         ↓
Usuario: "El de antes"
         ↓
    [CONSULTA_MODE - Retry 3/3 - FALLBACK TRIGGERED]
         ↓
    ┌─────────────────────────────────────┐
    │  Action: OFFER_HUMAN_HELP           │
    │  Mensaje: "¿Preferís hablar con      │
    │   una persona? Respondé SÍ o NO"    │
    └─────────────────────────────────────┘
```

### Secuencia de Fallback con Acciones Diferentes

#### VIABILIDAD_MODE → Escalar (caso complejo)

```
Usuario: "¿Se puede poner un turbo en mi moto?"
         ↓
    [VIABILIDAD_MODE]
         ↓
Agente: "Déjame verificar..."
         ↓
Usuario: "??" (3 errores consecutivos)
         ↓
    [FALLBACK - ESCALATE_TO_HUMAN]
         ↓
Agente: "Este caso parece complejo. Te voy a conectar con un especialista."
         ↓
    [ESCALACIÓN A HUMANO]
```

#### PRESUPUESTO_MODE → Reset a Viabilidad

```
Usuario: "Quiero el de antes" (5 intentos fallidos)
         ↓
    [FALLBACK - RESET_TO_VIABILIDAD]
         ↓
Agente: "Parece que hay confusión. Volvamos a evaluar qué querés homologar."
         ↓
    [VIABILIDAD_MODE]
Agente: "¿Qué elemento querés evaluar y en qué vehículo?"
```

---

## 🛠️ Tipos de Acciones de Fallback

```python
class FallbackAction(str, Enum):
    RESET_TO_MODE_START = "reset_to_mode_start"      # Empezar de nuevo en mismo modo
    RESET_TO_CONSULTA = "reset_to_consulta"          # Volver a CONSULTA_MODE
    RESET_TO_VIABILIDAD = "reset_to_viabilidad"      # Volver a VIABILIDAD_MODE
    RESET_TO_PRESUPUESTO = "reset_to_presupuesto"    # Volver a PRESUPUESTO_MODE
    ESCALATE_TO_HUMAN = "escalate_to_human"          # Escalar inmediatamente
    OFFER_HUMAN_HELP = "offer_human_help"            # Ofrecer (no forzar)
    SAVE_DRAFT_AND_EXIT = "save_draft_and_exit"      # Guardar y salir
```

### Cuándo usar cada una

| Acción | Modo Recomendado | Caso de Uso |
|--------|------------------|-------------|
| `RESET_TO_MODE_START` | EXPEDIENTE_MODE | Datos incompletos, empezar sub-modo de nuevo |
| `RESET_TO_CONSULTA` | PRESUPUESTO_MODE (fallback suave) | Confusión total, volver a básico |
| `RESET_TO_VIABILIDAD` | PRESUPUESTO_MODE (default) | Presupuesto no tiene sentido, re-evaluar |
| `ESCALATE_TO_HUMAN` | VIABILIDAD_MODE, casos complejos | Necesita experto técnico |
| `OFFER_HUMAN_HELP` | CONSULTA_MODE, EXPEDIENTE_MODE | Opción al usuario |

---

## 📊 Estados de Retry

### RetryState (por modo)

```python
@dataclass
class RetryState:
    retry_count: int = 0              # Total de reintentos en este modo
    consecutive_errors: int = 0       # Errores consecutivos (resetea en éxito)
    last_error_type: RetryErrorType   # Tipo de último error
    last_error_message: str           # Mensaje de error
    first_error_timestamp: datetime   # Cuándo empezó la cadena de errores
    last_retry_timestamp: datetime    # Último intento
```

**Importante**: El contador es **por modo**, no global. Cambiar de modo resetea el contador.

### Tipos de Error Trackeados

```python
class RetryErrorType(str, Enum):
    INTENT_NOT_UNDERSTOOD = "intent_not_understood"    # No entendemos intención
    TOOL_CALL_FAILED = "tool_call_failed"              # Herramienta falló
    VALIDATION_ERROR = "validation_error"              # Datos inválidos
    LLM_PARSE_ERROR = "llm_parse_error"               # LLM no parseó bien
    USER_CONFUSION = "user_confusion"                 # Usuario confundido (detectado)
```

---

## 🎨 Estrategias de Reprompt

### 1. Progressive Clarity (default)

Cada reintento da más contexto:

```
Retry 1: "No entendí bien. ¿Podés ser más específico?"
Retry 2: "¿Buscás información general, evaluar si algo se puede homologar, o un presupuesto?"
Retry 3: [Fallback action]
```

### 2. Simplify

Ofrece opciones claras:

```
Retry 3: 
"Te resumo las opciones:
1. Ver presupuesto actual
2. Agregar/quitar elementos
3. Volver a evaluar viabilidad
4. Hablar con una persona

¿Cuál preferís?"
```

### 3. Same Message

Para decisiones binarias:

```
Retry 1: "¿Confirmás iniciar el expediente? Respondé: SÍ o NO"
Retry 2: "¿Confirmás iniciar el expediente? Respondé: SÍ o NO"
```

---

## 🔧 Implementación

### Archivos Creados

```
agent/
├── nodes/
│   ├── fallback_handler.py         # Lógica central + policies
│   └── mode_node_template.py       # Template para implementar en cada modo
```

### Uso en Nodo de Modo

```python
# agent/nodes/consulta_mode.py

from agent.nodes.fallback_handler import BaseModeNode, RetryErrorType

class ConsultaModeNode(BaseModeNode):
    def __init__(self):
        super().__init__("CONSULTA_MODE")  # Carga policy automáticamente
    
    async def _process_message(self, message, context, history):
        try:
            # Lógica del modo...
            result = await process_with_tools(message)
            
            # Éxito: base class resetea contador
            return {"success": True, "response": result}
            
        except Exception as e:
            # Error: base class maneja fallback
            raise  # Se convierte en retry o fallback automáticamente
```

### En el Grafo (conversation.py)

```python
# El fallback NO es un nodo separado en el grafo
# Cada nodo de modo maneja su propio fallback internamente

graph.add_conditional_edges(
    "consulta_node",
    route_based_on_result,  # Puede retornar modo nuevo o "ESCALATE"
    {
        "CONSULTA_MODE": "consulta_node",      # Stay
        "VIABILIDAD_MODE": "viabilidad_node",  # Transition
        "ESCALATE": "escalation_node",         # Fallback action
    }
)
```

---

## 🧪 Testing del Fallback

### Test Cases Recomendados

```python
# tests/test_fallback_handler.py

async def test_consulta_mode_fallback_after_3_errors():
    """Should offer human help after 3 consecutive errors."""
    node = ConsultaModeNode()
    context = {"retry_state": {"retry_count": 2, "consecutive_errors": 2}}
    
    # 3rd error triggers fallback
    result = await node.process("Mensaje incomprensible", context, [])
    
    assert result["response"].contains("¿Preferís hablar con una persona?")
    assert result["context_updates"]["human_offered"] is True

async def test_presupuesto_mode_tolerates_5_errors():
    """PRESUPUESTO_MODE should allow 5 errors before fallback."""
    node = PresupuestoModeNode()
    context = {"retry_state": {"retry_count": 4}}
    
    # 5th error should trigger RESET_TO_VIABILIDAD
    result = await node.process("Mensaje confuso", context, [])
    
    assert result["should_transition"] is True
    assert result["transition_target"] == "VIABILIDAD_MODE"

async def test_retry_counter_resets_on_success():
    """Successful interaction should reset consecutive counter."""
    node = ConsultaModeNode()
    context = {"retry_state": {"retry_count": 2, "consecutive_errors": 2}}
    
    # Successful message
    result = await node.process("¿Qué es homologación?", context, [])
    
    # Consecutive errors should be 0
    assert result["context_updates"]["retry_state"]["consecutive_errors"] == 0
```

---

## 📈 Métricas y Observabilidad

### Logs Estructurados

```json
{
  "event": "error_recorded",
  "mode": "CONSULTA_MODE",
  "error_type": "intent_not_understood",
  "retry_count": 2,
  "max_retries": 3
}

{
  "event": "fallback_triggered",
  "action": "offer_human_help",
  "mode": "CONSULTA_MODE",
  "retry_count": 3,
  "time_since_first_error": "45s"
}
```

### Métricas a Trackear

| Métrica | Descripción | Alerta |
|---------|-------------|--------|
| `fallback_rate_by_mode` | % de conversaciones que llegan a fallback | >15% en cualquier modo |
| `avg_retries_before_fallback` | Promedio de reintentos antes de acción | <2 (política muy estricta) |
| `escalation_rate_from_fallback` | % de fallbacks que terminan en escalación | >50% (revisar políticas) |
| `recovery_success_rate` | % de usuarios que se recuperan tras reprompt | <30% (mensajes no claros) |

---

## 🔗 Integración con Digression Manager (Option B)

El Fallback Handler y el Digression Manager trabajan en capas diferentes:

```
┌─────────────────────────────────────┐
│  Digression Manager (Option B)      │  ← Detecta off-topic
│  - Parallel listener in graph       │  - "¿Se puede turbo?" durante expediente
└─────────────┬───────────────────────┘
              │ Decide: process here or pass to mode
              ▼
┌─────────────────────────────────────┐
│  Mode Node (CONSULTA_MODE, etc.)    │  ← Procesa intención
│  - Intent classification            │
└─────────────┬───────────────────────┘
              │ Success / Error
              ▼
┌─────────────────────────────────────┐
│  Fallback Handler (dentro del nodo) │  ← Maneja errores
│  - Track retries                    │  - 3rd error → action
│  - Progressive reprompts            │
└─────────────────────────────────────┘
```

**Flujo combinado**:

```
Usuario (en EXPEDIENTE_MODE): "¿Se puede homologar un turbo?"
         ↓
    [Digression Manager detecta consulta de viabilidad]
         ↓
    [Ruta a CONSULTA_MODE]
         ↓
Usuario: "????" (3 errores)
         ↓
    [Fallback Handler en CONSULTA_MODE]
         ↓
    [Action: OFFER_HUMAN_HELP]
```

---

## ✅ Checklist de Implementación

- [ ] Crear `fallback_handler.py` con policies por modo
- [ ] Crear `mode_node_template.py` con base class
- [ ] Implementar `ConsultaModeNode` con fallback
- [ ] Implementar `ViabilidadModeNode` con fallback
- [ ] Implementar `PresupuestoModeNode` con fallback (5 retries)
- [ ] Implementar `EvaluacionGateway` con fallback (2 retries)
- [ ] Implementar `ExpedienteModeNode` con fallback
- [ ] Agregar tests para cada modo
- [ ] Configurar métricas y alerting
- [ ] Documentar políticas para equipo de soporte

---

## 📁 Archivos Relacionados

- `agent/nodes/fallback_handler.py` - Lógica central
- `agent/nodes/mode_node_template.py` - Template de implementación
- `docs/arquitectura-v2/00-propuesta-maestra.md` - Contexto de modos
- `docs/arquitectura-v2/07-transiciones-grafo.md` - Transiciones

---

**Nota**: Esta implementación elimina el problema de "bucles infinitos" de v1.0 y da a cada modo control sobre su recuperación.
