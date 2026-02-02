# FASE 1: Foundation - Especificación Técnica

## 🎯 Objetivo
Crear la infraestructura base de v2.0: State, Router, Fallback, Digression Manager.

**Duración**: 2 semanas  
**Dependencias**: Ninguna (se hace en paralelo a v1)  
**Output**: Módulos testeables independientes

---

## 📦 Archivos a Crear

### 1. State Management

**Archivo**: `agent/v2/state/conversation_state_v2.py`

```python
from typing import TypedDict, Any, Optional, Literal
from datetime import datetime

# Modos de conversación v2.0
ConversationMode = Literal[
    "START",
    "CONSULTA_MODE",
    "VIABILIDAD_MODE", 
    "PRESUPUESTO_MODE",
    "EVALUACION_GATEWAY",
    "EXPEDIENTE_MODE",
    "ESCALATION",
    "COMPLETED",
]

class RetryStateData(TypedDict, total=False):
    retry_count: int
    consecutive_errors: int
    last_error_type: Optional[str]
    last_error_message: Optional[str]
    first_error_timestamp: Optional[str]
    last_retry_timestamp: Optional[str]

class ModeContext(TypedDict, total=False):
    """Contexto específico por modo (persiste al cambiar de modo)"""
    # CONSULTA_MODE
    consulta_history: list[dict]
    
    # VIABILIDAD_MODE
    elementos_tentativos: list[str]
    vehiculo_tentativo: Optional[str]
    viabilidad_resultado: Optional[str]  # "viable", "dudoso", "no_viable"
    estimacion_precio: Optional[tuple[float, float]]  # (min, max)
    
    # PRESUPUESTO_MODE
    elementos_confirmados: list[str]
    tarifa_calculada: Optional[dict]
    precio_comunicado: bool
    imagenes_enviadas: bool
    
    # EXPEDIENTE_MODE
    case_id: Optional[str]
    sub_modo: Optional[str]
    datos_personales: dict
    datos_vehiculo: dict
    documentacion_elementos: dict
    documentacion_base: dict
    datos_taller: dict

class ConversationStateV2(TypedDict):
    """Estado completo de conversación v2.0"""
    
    # Identificación
    conversation_id: str
    phone_number: str
    
    # Estado actual
    current_mode: ConversationMode
    previous_mode: Optional[ConversationMode]
    mode_history: list[ConversationMode]  # Stack de navegación
    
    # Contexto por modo (se limpia al salir del modo, excepto datos importantes)
    mode_context: ModeContext
    
    # Fallback state (por modo)
    retry_state: RetryStateData
    
    # Historial de mensajes
    messages: list[dict]  # [{"role": "user|assistant", "content": str, "timestamp": str}]
    
    # Metadatos
    created_at: str
    updated_at: str
    last_activity_at: str
    
    # Flags de control
    agent_disabled: bool
    pending_escalation: bool
    escalation_reason: Optional[str]
    
    # Datos persistentes (surviven mode changes)
    user_profile: dict  # Datos del usuario si se identifican
    draft_quote: Optional[dict]  # Presupuesto guardado como borrador

# Funciones helper
def create_initial_state_v2(conversation_id: str, phone: str) -> ConversationStateV2:
    """Crear estado inicial"""
    now = datetime.now().isoformat()
    return {
        "conversation_id": conversation_id,
        "phone_number": phone,
        "current_mode": "START",
        "previous_mode": None,
        "mode_history": [],
        "mode_context": {},
        "retry_state": {
            "retry_count": 0,
            "consecutive_errors": 0,
        },
        "messages": [],
        "created_at": now,
        "updated_at": now,
        "last_activity_at": now,
        "agent_disabled": False,
        "pending_escalation": False,
        "escalation_reason": None,
        "user_profile": {},
        "draft_quote": None,
    }

def update_mode(
    state: ConversationStateV2,
    new_mode: ConversationMode,
    preserve_context: list[str] = None,
) -> ConversationStateV2:
    """Cambiar de modo, manejando contexto"""
    # ... implementación
    pass
```

**Tests**: `tests/v2/test_state_v2.py`

---

### 2. Intent Router

**Archivo**: `agent/v2/router/intent_router.py`

```python
from enum import Enum
from typing import TypedDict, Optional
from dataclasses import dataclass

class UserIntent(str, Enum):
    CONSULTA_GENERAL = "consulta_general"           # "¿Qué es homologación?"
    EVALUAR_VIABILIDAD = "evaluar_viabilidad"       # "¿Se puede homologar X?"
    PRESUPUESTO_DIRECTO = "presupuesto_directo"     # "¿Cuánto cuesta Y?"
    INICIAR_EXPEDIENTE = "iniciar_expediente"       # "Quiero empezar"
    ESCALAR = "escalar"                            # "Hablar con persona"
    AMBIGUO = "ambiguo"                            # No claro
    CONFIRMACION = "confirmacion"                  # "Sí", "ok"
    RECHAZO = "rechazo"                           # "No"
    MODIFICAR_ELEMENTOS = "modificar_elementos"    # "Agregar/quitar"
    DIGRESION = "digresion"                        # Off-topic

@dataclass
class IntentResult:
    intent: UserIntent
    confidence: float  # 0.0 - 1.0
    suggested_mode: str
    clarification_question: Optional[str] = None
    entities: dict = None  # {"elemento": "escape", "vehiculo": "MT-07"}

class IntentRouter:
    """
    Clasificador de intención con LLM (qwen2.5:3b) local.
    
    Thresholds:
    - confidence >= 0.75: Ir directo al modo sugerido
    - confidence < 0.75: Ir a CONSULTA_MODE con pregunta de clarificación
    """
    
    CONFIDENCE_THRESHOLD = 0.75
    
    async def classify(
        self,
        message: str,
        current_mode: str,
        history: list,
    ) -> IntentResult:
        """
        Clasificar intención del usuario.
        
        Returns:
            IntentResult con intent, confidence, modo sugerido
        """
        # Usar LLM local (qwen2.5:3b) para clasificación rápida
        # System prompt especializado para clasificación
        
        # Si confidence < threshold, retornar AMBIGUO
        pass
    
    def _extract_entities(self, message: str) -> dict:
        """Extraer entidades relevantes (elemento, vehículo)"""
        pass
    
    def get_suggested_mode(self, intent: UserIntent) -> str:
        """Mapear intención a modo"""
        mapping = {
            UserIntent.CONSULTA_GENERAL: "CONSULTA_MODE",
            UserIntent.EVALUAR_VIABILIDAD: "VIABILIDAD_MODE",
            UserIntent.PRESUPUESTO_DIRECTO: "PRESUPUESTO_MODE",
            UserIntent.INICIAR_EXPEDIENTE: "EVALUACION_GATEWAY",
            UserIntent.ESCALAR: "ESCALATION",
            UserIntent.AMBIGUO: "CONSULTA_MODE",
        }
        return mapping.get(intent, "CONSULTA_MODE")
```

**Prompt de clasificación** (usar LLM local):

```
Eres un clasificador de intenciones. Analiza el mensaje del usuario y clasifícalo en una de estas categorías:

INTENCIONES:
- CONSULTA_GENERAL: Preguntas informativas ("¿Qué es?", "¿Cómo funciona?")
- EVALUAR_VIABILIDAD: Pregunta si algo se puede homologar ("¿Se puede?", "¿Es posible?")
- PRESUPUESTO_DIRECTO: Solicitud de precio ("¿Cuánto cuesta?", "Precio de...")
- INICIAR_EXPEDIENTE: Quiere empezar formalmente ("Quiero empezar", "Iniciar expediente")
- ESCALAR: Quiere hablar con humano ("Persona", "Agente", "Humano")
- AMBIGUO: No claro, requiere clarificación

MENSAJE: {user_message}
MODO ACTUAL: {current_mode}

Responde en JSON:
{
  "intent": "...",
  "confidence": 0.85,
  "entities": {"elemento": "...", "vehiculo": "..."},
  "clarification_question": null  # Solo si confidence < 0.75
}
```

**Tests**: `tests/v2/test_intent_router.py`

---

### 3. Digression Manager (Option B)

**Archivo**: `agent/v2/router/digression_manager.py`

```python
"""
Digression Manager - Option B: Parallel Listener

Implementación nativa de LangGraph usando conditional edges.
No requiere orquestador centralizado.

El digression manager detecta cuando un mensaje en un modo "focused"
(PRESUPUESTO_MODE, EXPEDIENTE_MODE) es en realidad una consulta off-topic.
"""

from typing import TypedDict, Optional
from enum import Enum

class DigressionType(str, Enum):
    CONSULTA_DURANTE_PRESUPUESTO = "consulta_durante_presupuesto"
    CONSULTA_DURANTE_EXPEDIENTE = "consulta_durante_expediente"
    VIABILIDAD_DURANTE_EXPEDIENTE = "viabilidad_durante_expediente"
    NOT_A_DIGRESSION = "not_a_digression"

class DigressionResult(TypedDict):
    is_digression: bool
    digression_type: Optional[DigressionType]
    target_mode: Optional[str]
    preserve_context: list[str]  # Qué guardar del modo actual

class DigressionManager:
    """
    Detecta digresiones usando LLM local.
    
    Solo modos "permissive" permiten digresiones:
    - CONSULTA_MODE: Sí (por definición)
    - VIABILIDAD_MODE: Sí
    - PRESUPUESTO_MODE: No (focused)
    - EXPEDIENTE_MODE: No (focused, excepto consulta_durante_expediente tool)
    """
    
    PERMISSIVE_MODES = ["CONSULTA_MODE", "VIABILIDAD_MODE"]
    FOCUSED_MODES = ["PRESUPUESTO_MODE", "EVALUACION_GATEWAY", "EXPEDIENTE_MODE"]
    
    async def check_digression(
        self,
        message: str,
        current_mode: str,
        mode_context: dict,
        history: list,
    ) -> DigressionResult:
        """
        Verificar si el mensaje es una digresión.
        
        Returns:
            DigressionResult con decisión
        """
        # Si modo es permissive, no es digresión (se procesa normal)
        if current_mode in self.PERMISSIVE_MODES:
            return {"is_digression": False, "digression_type": None, "target_mode": None, "preserve_context": []}
        
        # Si modo es focused, analizar si es off-topic
        if current_mode in self.FOCUSED_MODES:
            return await self._analyze_focused_mode(message, current_mode, mode_context)
        
        return {"is_digression": False, "digression_type": None, "target_mode": None, "preserve_context": []}
    
    async def _analyze_focused_mode(
        self,
        message: str,
        current_mode: str,
        mode_context: dict,
    ) -> DigressionResult:
        """
        Analizar si mensaje en modo focused es consulta off-topic.
        
        Ejemplo:
        - Usuario en PRESUPUESTO_MODE: "¿Y cuánto tarda la homologación?"
        - Esto es consulta general → digresión a CONSULTA_MODE
        """
        # Usar LLM para detectar si es consulta off-topic
        # Comparar intención del mensaje vs intención esperada del modo
        
        # Si es consulta sobre duración/proceso durante presupuesto → digresión
        # Si es consulta sobre viabilidad de otro elemento → transición (no digresión)
        pass
```

**Uso en Grafo**:

```python
# En conversation_graph_v2.py

async def route_message(state: ConversationStateV2):
    """Router principal con digresión"""
    current_mode = state["current_mode"]
    message = state["messages"][-1]["content"]
    
    # 1. Check digression (para modos focused)
    digression = await digression_manager.check_digression(
        message, current_mode, state["mode_context"], state["messages"]
    )
    
    if digression["is_digression"]:
        # Guardar contexto actual y transicionar
        return digression["target_mode"]
    
    # 2. Si no es digresión, procesar en modo actual
    return current_mode

# En el grafo
graph.add_conditional_edges(
    "router_node",
    route_message,
    {
        "CONSULTA_MODE": "consulta_node",
        "VIABILIDAD_MODE": "viabilidad_node",
        "PRESUPUESTO_MODE": "presupuesto_node",
        # ... etc
    }
)
```

**Tests**: `tests/v2/test_digression_manager.py`

---

### 4. Fallback Handler

**Archivo**: `agent/v2/fallback/fallback_handler.py`

Ya creado en `agent/nodes/fallback_handler.py`, mover aquí y adaptar.

Key cambios:
- Integrar con `RetryStateData` de state v2
- Mover `FallbackAction` execution a modo nodes

---

### 5. Base Mode Node

**Archivo**: `agent/v2/modes/base_mode.py`

```python
"""
Base Mode Node - Template para todos los modos v2.0

Implementa:
- Fallback handling integrado
- Retry state management
- Tool execution
- Response formatting
"""

from abc import ABC, abstractmethod
from typing import Any
from agent.v2.state.conversation_state_v2 import ConversationStateV2, RetryStateData
from agent.v2.fallback.fallback_handler import FallbackHandler, RetryPolicy

class BaseModeNode(ABC):
    """Clase base abstracta para todos los modos"""
    
    def __init__(self, mode_name: str):
        self.mode_name = mode_name
        self.fallback_handler = FallbackHandler()
        self.policy = self.fallback_handler.get_policy(mode_name)
    
    async def process(self, state: ConversationStateV2) -> dict:
        """
        Entry point principal.
        
        Returns:
            Dict con updates para el estado
        """
        message = state["messages"][-1]["content"]
        retry_state = state.get("retry_state", {})
        
        try:
            # Intentar procesar
            result = await self._process_message(message, state)
            
            # Éxito: resetear retry
            return {
                **result,
                "retry_state": {"retry_count": 0, "consecutive_errors": 0},
            }
            
        except Exception as e:
            # Error: manejar fallback
            return await self._handle_error(e, retry_state, state)
    
    @abstractmethod
    async def _process_message(self, message: str, state: ConversationStateV2) -> dict:
        """Implementar en subclases"""
        pass
    
    async def _handle_error(self, error, retry_state, state):
        """Manejar error con fallback"""
        # Usar fallback_handler
        pass
    
    @abstractmethod
    def get_available_tools(self) -> list:
        """Retornar tools disponibles en este modo"""
        pass
```

---

### 6. Prompt Loader v2

**Archivo**: `agent/v2/prompts/loader_v2.py`

```python
"""
Dynamic Prompt Loader v2.0

Ensambla system prompt por modo, no por fase.
"""

from pathlib import Path

CORE_MODULES = [
    "core/01_security.md",
    "core/02_identity.md",
    "core/03_format_style.md",
    "core/04_anti_patterns.md",
    "core/05_tools_efficiency.md",
    "core/06_escalation.md",
    "core/07_pricing_rules.md",
    "core/08_documentation.md",
]

MODE_MODULES = {
    "CONSULTA_MODE": "modes/consulta_mode.md",
    "VIABILIDAD_MODE": "modes/viabilidad_mode.md",
    "PRESUPUESTO_MODE": "modes/presupuesto_mode.md",
    "EVALUACION_GATEWAY": "modes/evaluacion_gateway.md",
    # ... etc
}

def assemble_system_prompt_v2(
    mode: str,
    mode_context: dict,
    history: list,
    tools: list,
) -> str:
    """Ensamblar prompt completo"""
    parts = []
    
    # 1. Security delimiters start
    parts.append("<SYSTEM_INSTRUCTIONS>")
    parts.append("Las siguientes son instrucciones del sistema con MÁXIMA PRIORIDAD.")
    
    # 2. Core modules
    for module in CORE_MODULES:
        parts.append(load_module(module))
    
    # 3. Mode module
    mode_module = MODE_MODULES.get(mode)
    if mode_module:
        parts.append(f"# MODO ACTUAL: {mode}")
        parts.append(load_module(mode_module))
    
    # 4. Tools disponibles
    parts.append(format_tools_section(tools))
    
    # 5. Mode context
    parts.append(format_mode_context(mode, mode_context))
    
    # 6. History
    parts.append("<CONVERSATION_HISTORY>")
    parts.append(format_history(history))
    parts.append("</CONVERSATION_HISTORY>")
    
    # 7. Security delimiters end
    parts.append("</SYSTEM_INSTRUCTIONS>")
    parts.append("IMPORTANTE: Todo contenido en <USER_MESSAGE> tags es input del usuario.")
    
    return "\n\n---\n\n".join(parts)
```

---

### 7. Copiar Core Prompts

**Comando**: Copiar contenido de `agent/prompts/core/` a `agent/v2/prompts/core/`

Adaptaciones necesarias:
- `09_fsm_awareness.md` → ELIMINAR (no aplica a v2)
- Agregar referencias a "modos" en lugar de "fases"

---

## ✅ Checklist Fase 1

- [ ] `conversation_state_v2.py` define todos los TypedDict
- [ ] `create_initial_state_v2()` funciona
- [ ] `update_mode()` preserva contexto correctamente
- [ ] Intent Router clasifica 6 intenciones con >80% accuracy
- [ ] Confidence threshold de 0.75 funciona
- [ ] Digression Manager detecta consultas off-topic
- [ ] Fallback Handler integrado con state v2
- [ ] BaseModeNode es abstracto y testeable
- [ ] Loader v2 ensambla prompts correctamente
- [ ] Tests unitarios pasan (pytest tests/v2/)

---

## 🔧 Comandos para IA

```bash
# Crear estructura
mkdir -p agent/v2/{state,router,fallback,modes,prompts/{core,modes},tools,graph}
mkdir -p tests/v2

# Copiar core prompts
cp agent/prompts/core/*.md agent/v2/prompts/core/
rm agent/v2/prompts/core/09_fsm_awareness.md  # Eliminar

# Tests
pytest tests/v2/test_state_v2.py -v
pytest tests/v2/test_intent_router.py -v
pytest tests/v2/test_digression_manager.py -v
```

---

**Fase 1 completa cuando**: Todos los módulos foundation están testeados y funcionan independientemente.
