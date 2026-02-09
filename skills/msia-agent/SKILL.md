---
name: msia-agent
description: >
  MSI-a conversational agent patterns using LangGraph.
  Trigger: When working on agent conversation flow, nodes, state, tools, prompts, or mode-based architecture.
metadata:
  author: msi-automotive
  version: "4.0"
  scope: [root, agent]
  auto_invoke:
    - "Working on agent conversation flow"
    - "Creating/modifying mode nodes"
    - "Working with ConversationState"
    - "Creating/modifying agent tools"
    - "Working on system prompts"
    - "Working on mode-based architecture"
---

## Agent Structure (v2.0 - Mode-Based)

```
agent/
├── main.py                      # Entry point (Redis Streams consumer)
├── state/
│   ├── conversation_state.py    # ConversationState TypedDict
│   ├── checkpointer.py          # Redis checkpointer (LangGraph persistence)
│   └── helpers.py               # State utilities (format_messages, etc.)
├── router/
│   ├── intent_router.py         # Intent classification (9 intents, keyword + LLM)
│   ├── digression_manager.py    # Off-topic detection in focused modes
│   └── mode_transitions.py      # Mode transition rules (whitelist + context preservation)
├── fallback/
│   └── fallback_handler.py      # Per-mode retry policies and fallback actions
├── modes/
│   ├── base_mode.py             # BaseModeNode (shared error handling + fallback integration)
│   ├── consulta_mode.py         # CONSULTA_MODE (~10% traffic) — educational queries
│   ├── presupuesto_mode.py      # PRESUPUESTO_MODE (~90% traffic) — pricing + images
│   ├── evaluacion_gateway.py    # EVALUACION_GATEWAY — yes/no confirmation (pattern-based)
│   └── expediente_mode.py       # EXPEDIENTE_MODE — formal case collection (6 sub-modes)
├── graph/
│   └── conversation_graph.py    # StateGraph definition (preprocess → router → modes)
├── prompts/
│   ├── loader.py                # Dynamic prompt assembly (core + mode + context)
│   ├── core/                    # Core prompts (always loaded, ~2,200 tokens)
│   │   ├── 01_security.md
│   │   ├── 02_identity.md
│   │   ├── 03_format_style.md
│   │   ├── 04_anti_patterns.md
│   │   ├── 05_tools_efficiency.md
│   │   ├── 06_escalation.md
│   │   ├── 07_pricing_rules.md
│   │   └── 08_documentation.md
│   └── modes/                   # Mode-specific prompts (~500-1,000 tokens each)
│       ├── consulta_mode.md
│       ├── presupuesto_mode.md
│       ├── evaluacion_gateway.md
│       └── expediente_*.md      # 6 sub-mode prompts
├── tools/                       # LangChain tools (26 total)
│   ├── element_tools.py         # Element identification & pricing (8 tools)
│   ├── tarifa_tools.py          # Tariff calculation (4 tools)
│   ├── case_tools.py            # Case management (8 tools)
│   ├── element_data_tools.py    # Element data collection (7 tools)
│   ├── image_tools.py           # Example image sending (1 tool)
│   ├── vehicle_tools.py         # Vehicle classification (1 tool)
│   └── shared_tools.py          # Universal tools (escalar_a_humano)
├── services/                    # Business logic
│   ├── tarifa_service.py        # Tariff calculation with Redis caching
│   ├── element_service.py       # Element matching (NLP + fuzzy + variants)
│   ├── collection_mode.py       # Smart collection mode (Sequential/Batch/Hybrid)
│   ├── element_required_fields_service.py  # Conditional field management
│   ├── constraint_service.py    # Response validation (anti-hallucination)
│   ├── tool_logging_service.py  # Persistent tool call logging
│   └── token_tracking.py        # Token usage tracking
└── utils/
    └── validation.py            # Input validation (whitelist-based)
```

---

## Architecture Overview

### Conversation Modes

**Mode-based architecture** (replaced FSM in v2.0):

| Mode              | Traffic | Purpose                             | Tools    |
| ----------------- | ------- | ----------------------------------- | -------- |
| CONSULTA          | ~10%    | Educational queries, catalog browse | 5 tools  |
| PRESUPUESTO       | ~90%    | Direct pricing + images (fusionado) | 10 tools |
| EVALUACION_GATEWAY| Entry   | Yes/no confirmation (pattern-based) | 0 tools  |
| EXPEDIENTE        | Complex | Formal case collection (6 sub-modes)| 26 tools |
| ESCALATION        | Terminal| Human handoff                       | 0 tools  |

### Key Changes from v1 (FSM-based)

| Aspect              | v1 (FSM-based)                | v2 (Mode-based)              |
| ------------------- | ----------------------------- | ---------------------------- |
| **Flow control**        | FSM states + transitions      | Modes + intent routing       |
| **Tool availability**   | Phase-based filtering         | Mode-based filtering         |
| **Prompt assembly**     | Core + phase prompts          | Core + mode prompts          |
| **Digression handling** | Not supported                 | Digression manager           |
| **Fallback**            | Global only                   | Per-mode retry policies      |
| **Entry point**         | `graphs/conversation_flow.py` | `graph/conversation_graph.py`|

---

## Mode Node Pattern

```python
from agent.modes.base_mode import BaseModeNode

class MyModeNode(BaseModeNode):
    def __init__(self):
        super().__init__("MY_MODE")
    
    async def _process_message(self, message: str, state: dict) -> dict:
        """Core processing logic for this mode."""
        
        # 1. Build system prompt
        from agent.prompts.loader import assemble_system_prompt
        system_prompt = assemble_system_prompt(
            mode="MY_MODE",
            mode_context=state.get("mode_context"),
        )
        
        # 2. Build LLM messages
        llm_messages = [
            {"role": "system", "content": system_prompt},
            # ... conversation history
        ]
        
        # 3. Get LLM with tools
        tools = self.get_tools()
        llm = self._get_llm(tools)
        
        # 4. Tool calling loop
        MAX_TOOL_ITERATIONS = 10
        for iteration in range(MAX_TOOL_ITERATIONS):
            response = await llm.ainvoke(llm_messages)
            
            # Handle tool calls
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    result = await self._execute_and_log_tool(tool_call, state)
                    # Update context...
            else:
                break  # No more tools to call
        
        # 5. Return state updates
        return {
            "ai_response": response.content,
            "mode_context": updated_context,
        }
    
    def get_tools(self) -> list:
        """Return tools available in this mode."""
        return [tool1, tool2, tool3]
```

---

## Dynamic Prompts System

**Structure**:
```
CORE modules (always)  +  MODE module (by mode)  +  MODE CONTEXT (dynamic)
    ~2,200 tokens            ~500-1,000 tokens         ~100 tokens
```

**Token savings vs. v1**: ~40-60% reduction (context-aware loading)

### Loading Prompts

```python
from agent.prompts.loader import assemble_system_prompt

# For top-level modes
system_prompt = assemble_system_prompt(
    mode="PRESUPUESTO_MODE",
    mode_context=state.get("mode_context"),
)

# For expediente sub-modes
system_prompt = assemble_system_prompt(
    mode="EXPEDIENTE_MODE",
    expediente_sub_mode="DATOS_PERSONALES",  # Loads expediente_datos_personales.md
    mode_context=state.get("mode_context"),
)
```

---

## Intent Router

**Purpose**: Classify user intent from START mode and route to appropriate mode.

**Strategy**:
1. **Keyword patterns** (fast, no LLM cost) → 9 intents
2. **LLM classification** (qwen2.5:3b, local, cheap) → fallback
3. **AMBIGUO** → clarification question to CONSULTA_MODE

**Intents**:
- `CONSULTA_GENERAL` → CONSULTA_MODE
- `PRESUPUESTO_DIRECTO` → PRESUPUESTO_MODE (most common)
- `INICIAR_EXPEDIENTE` → EVALUACION_GATEWAY
- `VER_IMAGENES` → Context-dependent (PRESUPUESTO handles it)
- `ABRIR_EXPEDIENTE` → EVALUACION_GATEWAY
- `MODIFICAR_ELEMENTOS` → PRESUPUESTO_MODE
- `CONFIRMACION`, `RECHAZO` → Context-dependent
- `AMBIGUO` → CONSULTA_MODE with clarification

**Usage**:
```python
from agent.router.intent_router import get_intent_router

router = get_intent_router()
result = await router.classify(
    message="Quiero homologar un escape",
    current_mode="START",
)
# → IntentResult(intent=PRESUPUESTO_DIRECTO, confidence=0.90, suggested_mode="PRESUPUESTO_MODE")
```

---

## Digression Manager

**Purpose**: Detect off-topic messages in **focused modes** (PRESUPUESTO, EXPEDIENTE).

**Permissive modes** (CONSULTA) → skip digression check  
**Focused modes** → regex patterns + LLM detection

**Digression types**:
- `OFF_TOPIC` → General conversation
- `GREETING` → User says hello mid-flow
- `QUESTION` → Asks about process
- `ESCALATION` → Wants human help

**Usage**:
```python
from agent.router.digression_manager import get_digression_manager

dgr_mgr = get_digression_manager()
digression = await dgr_mgr.check(
    message="¿Cuánto tarda esto?",
    current_mode="PRESUPUESTO_MODE",
    mode_context=state.get("mode_context"),
)

if digression.is_digression:
    # Transition to target mode (e.g., CONSULTA_MODE)
    target = digression.target_mode or "CONSULTA_MODE"
```

---

## Mode Transitions

**Allowed transitions** (whitelist):

```
START → [CONSULTA, PRESUPUESTO]
CONSULTA → [PRESUPUESTO, ESCALATION]
PRESUPUESTO → [EVALUACION_GATEWAY, ESCALATION]
EVALUACION_GATEWAY → [PRESUPUESTO, EXPEDIENTE, ESCALATION]
EXPEDIENTE → [PRESUPUESTO (from REVISION only), ESCALATION]
ESCALATION → [] (terminal)
```

**Context preservation**: When transitioning, specific keys are preserved:

```python
from agent.router.mode_transitions import transition_mode

updates = transition_mode(
    state,
    target_mode="EVALUACION_GATEWAY",
    preserve_keys=["categoria_slug", "element_codes", "tarifa_calculada"],
)
# Returns: {"current_mode": "EVALUACION_GATEWAY", "mode_context": {...preserved...}}
```

---

## Fallback Handler

**Per-mode retry policies**:

- `CONSULTA_MODE`: 2 retries → escalate
- `PRESUPUESTO_MODE`: 4 retries → escalate (blocking mode)
- `EXPEDIENTE_MODE`: 5 retries → escalate (blocking mode)
- `EVALUACION_GATEWAY`: 2 retries → reset mode

**Progressive reprompts**: Each retry adds more context/guidance.

**Usage** (automatic in BaseModeNode):
```python
# In base_mode.py, wraps _process_message()
try:
    result = await self._process_message(message, state)
except Exception as e:
    # Record error in retry_state
    # Check if retry limit exceeded → execute fallback
    fallback_handler.handle_error(state, error)
```

---

## Tool-Driven State Management (REFACTOR-001)

**Pattern**: Tools explicitly declare state changes via `_internal_flags`.

**Tool Flag Contract**:
```python
# In a tool (e.g., calcular_tarifa_con_elementos)
return {
    "success": True,
    "precio_final": 410.0,
    "elementos": ["ESCAPE"],
    "_internal_flags": {
        "precio_comunicado": True,      # State change declared
        "imagenes_enviadas": False,     # Reset for new quote
    }
}
```

**Mode Flag Application**:
```python
# In presupuesto_mode.py
from agent.modes.presupuesto_mode import _apply_tool_flags

result = await self._execute_and_log_tool(tool_call, state)
result_dict = json.loads(result) if isinstance(result, str) else result

_apply_tool_flags(mode_context, result_dict, logger)
# mode_context["precio_comunicado"] = True (applied immediately)
# Persists to Redis checkpoint via mode_context reducer
```

**Why**: Eliminates fragile pattern matching on LLM responses. State changes are explicit, testable, and persist reliably.

---

## Critical Anti-Patterns

### ❌ NEVER Re-identify After Variant Question
```python
User: "delantera"
→ seleccionar_variante_por_respuesta("motos-part", "SUSPENSION", "delantera")  # ✅ CORRECT

# NOT:
→ identificar_y_resolver_elementos(...)  # ❌ WRONG
```

### ✅ ALWAYS Price Before Images
```python
calcular_tarifa_con_elementos(...)  # → 410€
Bot: "El presupuesto es de 410€ +IVA. Te envío fotos:"  # ✅ CORRECT

# NOT:
Bot: "Te envío fotos:"  # ❌ Missing price!
```

### ✅ ALWAYS skip_validation After Identification
```python
# After identificar_y_resolver_elementos():
await calcular_tarifa_con_elementos(
    elementos=["ESCAPE"],
    categoria="motos-part",
    skip_validation=True,  # ✅ CORRECT
)
```

### ✅ ALWAYS Parse Tool Results
```python
result = await self._execute_and_log_tool(...)
result_dict = json.loads(result) if isinstance(result, str) else result  # ✅ Parse first
_apply_tool_flags(mode_context, result_dict, logger)
```

---

## Expediente Sub-Modes

**6 sub-modes** for formal case collection:

1. **DATOS_PERSONALES**: Nombre, DNI, email, domicilio, ITV
2. **DATOS_VEHICULO**: Marca, modelo, matrícula, bastidor
3. **DOCUMENTACION_ELEMENTOS**: Photos + technical data per element (element-by-element)
4. **DOCUMENTACION_BASE**: Ficha técnica, permiso, vistas
5. **TALLER**: Decision (MSI vs. propio) + workshop data if needed
6. **REVISION**: Present summary, confirm or edit

**Sub-mode storage**: `mode_context["sub_modo"]` (string)

**Transitions**: Automatic via tool returns (e.g., `completar_elemento_actual()` → next element or DOCUMENTACION_BASE)

---

## Testing Patterns

```python
import pytest
from agent.modes.presupuesto_mode import PresupuestoModeNode

@pytest.mark.asyncio
async def test_presupuesto_calculates_price():
    mode = PresupuestoModeNode()
    
    state = {
        "conversation_id": "test-001",
        "current_mode": "PRESUPUESTO_MODE",
        "user_message": "Quiero homologar un escape",
        "mode_context": {},
    }
    
    with patch.object(mode, '_get_llm') as mock_llm:
        # Mock LLM response with tool calls
        mock_response = AsyncMock()
        mock_response.content = "El precio es 410 EUR +IVA"
        mock_response.tool_calls = []
        mock_llm.return_value.ainvoke = AsyncMock(return_value=mock_response)
        
        result = await mode._process_message("Quiero homologar un escape", state)
        
        assert result["ai_response"]
        assert "410" in result["ai_response"]
```

---

## References

- `agent/AGENTS.md` — Full component documentation
- `docs/decisions/005-tool-driven-state-management.md` — ADR for _internal_flags
- `docs/plans/completed/fusion-viabilidad-presupuesto.md` — Mode fusion details
- `skills/langgraph/SKILL.md` — LangGraph generic patterns

---

**Version**: 4.0 (Mode-based architecture, post-VIABILIDAD fusion)  
**Last Updated**: Febrero 2026
