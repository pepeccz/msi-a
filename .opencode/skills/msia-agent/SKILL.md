---
name: msia-agent
description: >
  MSI-a conversational agent patterns using LangGraph.
  Trigger: When working on agent conversation flow, nodes, state, tools, prompts, or FSM.
metadata:
  author: msi-automotive
  version: "3.0"
  scope: [root, agent]
  auto_invoke:
    - "Working on agent conversation flow"
    - "Creating/modifying graph nodes"
    - "Working with ConversationState"
    - "Creating/modifying agent tools"
    - "Working on system prompts"
    - "Working on FSM case collection"
---

## Agent Structure

```
agent/
├── main.py                    # Entry point, Redis stream consumer
├── graphs/
│   └── conversation_flow.py   # StateGraph definition, security delimiters
├── nodes/
│   ├── process_message.py     # Message preprocessing
│   └── conversational_agent.py  # LLM response generation (uses dynamic prompts)
├── tools/
│   ├── tarifa_tools.py        # Tariff calculation tools
│   ├── element_tools.py       # Element matching tools (identificar_y_resolver_elementos)
│   ├── element_data_tools.py  # Element data collection (per-element photos + fields)
│   ├── vehicle_tools.py       # Vehicle identification
│   ├── case_tools.py          # Case/expediente management (FSM transitions)
│   ├── image_tools.py         # Image sending tools (enviar_imagenes_ejemplo)
│   └── tool_manager.py        # Contextual tool selection (phase-aware)
├── services/
│   ├── tarifa_service.py      # Tariff business logic (cached)
│   ├── element_service.py     # Element matching service
│   ├── element_required_fields_service.py  # Required fields management
│   ├── token_tracking.py      # Token usage tracking
│   ├── collection_mode.py     # Smart collection mode (Sequential/Batch/Hybrid)
│   ├── constraint_service.py  # Response validation (anti-hallucination)
│   ├── tool_logging_service.py  # Persistent tool call logging
│   └── prompt_service.py      # Calculator prompt (legacy)
├── state/
│   ├── schemas.py             # ConversationState TypedDict
│   ├── checkpointer.py        # Redis checkpointer
│   └── helpers.py             # State utilities, message formatting
├── fsm/
│   └── case_collection.py     # Data collection FSM (7 phases)
├── utils/
│   └── validation.py          # Input validation (security)
├── routing/
│   └── __init__.py            # Placeholder for intent routing
└── prompts/
    ├── __init__.py            # Package exports
    ├── loader.py              # Dynamic prompt assembly (~40-60% token savings)
    ├── state_summary.py       # Real-time state summary generator
    ├── system.md              # Legacy static prompt (backup)
    ├── calculator_base.py     # Calculator prompt template
    ├── core/                  # ~2,200 tokens - ALWAYS included
    │   ├── 01_security.md     # Security, anti-jailbreak
    │   ├── 02_identity.md     # MSI-a identity
    │   ├── 03_format_style.md # Tone, format, categories
    │   ├── 04_anti_patterns.md # Anti-loop, anti-invention
    │   ├── 05_tools_efficiency.md # Tool usage rules
    │   ├── 06_escalation.md   # When to escalate
    │   ├── 07_pricing_rules.md # Price communication (CRITICAL)
    │   ├── 08_documentation.md # Doc rules (STRICT)
    │   └── 09_fsm_awareness.md # FSM context awareness
    └── phases/                # One per call based on FSM state
        ├── idle_quotation.md  # ~1,000 tokens - Presupuestación
        ├── collect_element_data.md  # ~700 tokens - Element photos + data
        ├── collect_base_docs.md  # ~730 tokens - Base vehicle docs
        ├── collect_personal.md # ~550 tokens - Personal data
        ├── collect_vehicle.md # ~450 tokens - Vehicle data
        ├── collect_workshop.md # ~550 tokens - Workshop data
        └── review_summary.md  # ~600 tokens - Final review
```

## Dynamic Prompts System

The agent uses a modular prompt system that reduces token usage by 40-60%:

```python
# In conversational_agent.py
from agent.prompts.loader import assemble_system_prompt
from agent.prompts.state_summary import generate_state_summary

# Generate dynamic prompt based on FSM state
state_summary = generate_state_summary(fsm_state, last_tariff_result)
system_prompt = assemble_system_prompt(
    fsm_state=fsm_state,
    state_summary=state_summary,
    client_context=client_context,
)
```

### Prompt Assembly Flow

```
CORE modules (~2,200 tokens)     # Always included
    +
PHASE module (~500-1,000 tokens) # Based on current FSM state
    +
STATE_SUMMARY (~100 tokens)      # Dynamic context (price, elements, etc.)
    +
CLIENT_CONTEXT (~200 tokens)     # Client type, categories
    =
TOTAL: ~3,000-3,500 tokens       # vs ~7,000 tokens with legacy prompt
```

### Adding New Phases

1. Create `prompts/phases/new_phase.md`
2. Add to `loader.py` PHASE_MODULES dict
3. Map FSM CollectionStep to the new phase

---

## Contextual Tool Selection

**Token savings**: ~2,500-3,600 tokens per call (57-82% reduction in tool tokens)

Instead of sending all 27 tools on every LLM call, we only send tools relevant to the current FSM phase:

```python
from agent.tools.tool_manager import get_tools_for_phase

# Get current FSM phase
phase = get_current_step(fsm_state)  # → CollectionStep.COLLECT_PERSONAL

# Filter tools to only those relevant for this phase
contextual_tools = get_tools_for_phase(phase, all_tools)
# Returns: actualizar_datos_expediente, consulta_durante_expediente,
#          obtener_estado_expediente, cancelar_expediente, escalar_a_humano
```

**Universal tools** (always available):
- `escalar_a_humano` - User can always request human help

---

## Smart Collection Mode

**Purpose**: Automatically determines the optimal strategy for collecting element field data.

**Modes**:
- **SEQUENTIAL**: 1-2 fields OR complex conditionals → Ask one at a time (conversational)
- **BATCH**: 3+ fields without conditionals → Ask all at once (efficient)
- **HYBRID**: Mix → Ask base fields first, then conditional fields as a group

**Decision logic**:
```python
from agent.services.collection_mode import determine_collection_mode

# Analyze fields and determine mode
mode = determine_collection_mode(field_infos, collected_values)

# SEQUENTIAL if:
# - 0-2 fields total
# - OR nested conditionals (field depends on another conditional field)

# BATCH if:
# - 3+ fields
# - AND no conditionals at all

# HYBRID if:
# - 3+ fields
# - AND simple conditionals (1 level deep)
```

**Example**:
```python
# Element with 5 simple fields → BATCH
# "Dime la altura, anchura, longitud, peso y color"

# Element with 2 fields → SEQUENTIAL
# "¿Cuál es la altura?" → user responds → "¿Y la anchura?"

# Element with 3 base + 2 conditional → HYBRID
# "Dime tipo, altura, anchura" → user responds
# If tipo="fijo": "Ahora dime distancia_ejes y peso_soporte"
```

---

## ConversationState Schema

```python
class ConversationState(TypedDict, total=False):
    # Core Metadata
    conversation_id: str          # LangGraph thread_id
    user_phone: str               # E.164 format
    user_name: str | None
    user_id: str | None           # Database UUID
    client_type: str | None       # "particular" or "professional"
    
    # Messages
    messages: list[dict[str, Any]]  # Conversation history
    user_message: str | None        # Current message
    
    # FSM State
    fsm_state: dict[str, Any] | None  # Contains case_collection state
    
    # Flags
    is_first_interaction: bool
    escalation_triggered: bool
    agent_disabled: bool            # Panic button
    
    # Tool Results
    pending_images: dict[str, Any]    # Images to send + follow_up_message
    incoming_attachments: list[dict]  # User attachments
    tarifa_actual: dict[str, Any]     # Last tariff calculation result
```

---

## FSM Flow (Case Collection)

```
IDLE
  ↓ iniciar_expediente()
COLLECT_ELEMENT_DATA (per element: photos then data)
  ├─ photos phase: User sends photos → confirmar_fotos_elemento()
  └─ data phase: guardar_datos_elemento() + completar_elemento_actual()
  ↓ Auto transition after all elements
COLLECT_BASE_DOCS
  ↓ confirmar_documentacion_base()
COLLECT_PERSONAL
  ↓ actualizar_datos_expediente(datos_personales)
COLLECT_VEHICLE
  ↓ actualizar_datos_expediente(datos_vehiculo)
COLLECT_WORKSHOP
  ↓ actualizar_datos_taller()
REVIEW_SUMMARY
  ↓ finalizar_expediente()
COMPLETED
```

### FSM Tools

| Tool | Purpose | When to Use |
|------|---------|-------------|
| **Quotation Phase** | | |
| `identificar_y_resolver_elementos()` | Identify elements from user description | First tool for quotation |
| `seleccionar_variante_por_respuesta()` | Resolve variant questions | ONLY for variant answers |
| `calcular_tarifa_con_elementos()` | Calculate price | After element identification |
| `enviar_imagenes_ejemplo()` | Send documentation examples | After giving price |
| `iniciar_expediente()` | Create case, start collection | User agrees to proceed |
| **Element Data Collection** | | |
| `obtener_campos_elemento()` | Get required fields for element | Check what to ask |
| `confirmar_fotos_elemento()` | Confirm element photos received | User says "listo" after photos |
| `guardar_datos_elemento()` | Save element technical data | User provides field values |
| `completar_elemento_actual()` | Mark element complete, move to next | All required fields collected |
| `obtener_progreso_elementos()` | Get collection progress | Check completion status |
| `reenviar_imagenes_elemento()` | Resend example images | User asks to see photos again |
| **Base Documentation** | | |
| `confirmar_documentacion_base()` | Confirm base docs received | User says "listo" after base docs |
| **Personal/Vehicle Data** | | |
| `actualizar_datos_expediente()` | Update personal or vehicle data | User provides info |
| **Workshop Data** | | |
| `actualizar_datos_taller()` | Update workshop info | Workshop decision made |
| **Review & Completion** | | |
| `finalizar_expediente()` | Complete and escalate | User confirms summary |
| **Utility** | | |
| `obtener_estado_expediente()` | Get case status | User asks about progress |
| `cancelar_expediente()` | Cancel case | User wants to stop |
| `consulta_durante_expediente()` | Answer off-topic questions | User asks unrelated questions |
| `escalar_a_humano()` | Escalate to human | User requests or complex issue |

---

## Key Tools

### Element Identification (CRITICAL)

```python
# ALWAYS use this first for quotation
identificar_y_resolver_elementos(
    categoria="motos-part",
    descripcion="escape y amortiguador delantero"
)
# Returns: elementos_listos, elementos_con_variantes, preguntas_variantes

# ONLY use when resolving variant questions
seleccionar_variante_por_respuesta(
    categoria="motos-part",
    codigo_base="SUSPENSION",
    respuesta_usuario="delantera"
)

# Calculate price (ALWAYS skip_validation=True after identification)
calcular_tarifa_con_elementos(
    categoria="motos-part",
    codigos=["ESCAPE", "SUSPENSION_DEL"],
    skip_validation=True
)
```

### Element Data Collection Tools

```python
# Get required fields for current element
campos_info = obtener_campos_elemento()
# Returns: {
#   "fields": [
#     {
#       "field_key": "altura_mm",
#       "field_label": "Altura",
#       "field_type": "number",
#       "is_required": true,
#       "instruction": "¿Cuál es la altura del elemento en milímetros?",
#       "validation": {"min_value": 1, "max_value": 5000}
#     },
#     ...
#   ],
#   "collection_mode": "batch",  # or "sequential" or "hybrid"
#   ...
# }

# Save field values (use EXACT field_key from obtener_campos_elemento!)
result = guardar_datos_elemento({
    "altura_mm": "1230",
    "anchura_mm": "850",
    "profundidad_mm": "420"
})
# Returns validation results, next fields to ask (if any)

# Confirm photos received
result = confirmar_fotos_elemento()
# Transitions from photos phase to data phase
# Returns next fields to ask using Smart Collection Mode

# Complete current element
result = completar_elemento_actual()
# Validates all required fields collected
# Transitions to next element or COLLECT_BASE_DOCS
```

### Image Tools

```python
# Send example images AFTER giving the price
enviar_imagenes_ejemplo(
    tipo="presupuesto",
    follow_up_message="¿Te gustaría que te abriera un expediente?"
)
```

---

## Node Pattern

```python
async def my_node(state: ConversationState) -> dict:
    """
    Node documentation.
    
    Args:
        state: Current conversation state
        
    Returns:
        State updates to merge
    """
    # Access state with .get() for safety
    messages = state.get("messages", [])
    fsm_state = state.get("fsm_state")
    
    # Process logic
    result = await process_something()
    
    # Return state updates (will be merged)
    return {
        "last_node": "my_node",
        "fsm_state": updated_fsm_state,  # If FSM changed
    }
```

---

## Anti-Patterns (NEVER Do This)

### Identification Loop
```python
# ❌ WRONG: Re-calling after variant question
User: "delantera"
→ identificar_y_resolver_elementos(...)  # WRONG!

# ✅ CORRECT: Use variant selector
User: "delantera"
→ seleccionar_variante_por_respuesta("motos-part", "SUSPENSION", "delantera")
```

### Inventing Variants
```python
# ❌ WRONG: Asking for variants not in data
Bot: "¿Es de barras o muelles?"  # If not in elementos_con_variantes

# ✅ CORRECT: Only ask from preguntas_variantes
Bot: "¿Es la suspensión delantera o trasera?"  # From actual data
```

### Forgetting the Price
```python
# ❌ WRONG: Send images without price
calcular_tarifa_con_elementos(...)  # → 410€
Bot: "Te envío las fotos:"
enviar_imagenes_ejemplo(...)

# ✅ CORRECT: ALWAYS say price first
calcular_tarifa_con_elementos(...)  # → 410€
Bot: "El presupuesto es de 410€ +IVA (No se incluye el certificado del taller de montaje). Te envío fotos:"
enviar_imagenes_ejemplo(...)
```

### Repeating Images
```python
# ❌ WRONG: Send images again after user confirms
User: "Dale, adelante"
→ enviar_imagenes_ejemplo(...)  # WRONG! Already sent

# ✅ CORRECT: Start expediente
User: "Dale, adelante"
→ iniciar_expediente(...)
```

### Omitting Warnings
```python
# ❌ WRONG: Not mentioning warnings from tool
calcular_tarifa_con_elementos(...)  # → 410 EUR + warnings
Bot: "El presupuesto es de 410 EUR +IVA (No se incluye el certificado del taller de montaje)"  # NO warnings mentioned!

# ✅ CORRECT: ALWAYS mention warnings
calcular_tarifa_con_elementos(...)  # → 410 EUR + warnings
Bot: "El presupuesto es de 410 EUR +IVA (No se incluye el certificado del taller de montaje).

Ten en cuenta:
- [warning 1 from tool]
- [warning 2 from tool]"
```

### Inventing Content
```python
# ❌ WRONG: Adding text not from database
Bot: "Incluye: gestión completa, informe técnico y tasas de ITV."
# This is INVENTED - not from any tool result!

# ✅ CORRECT: Only use data from tools
Bot: "El presupuesto es de 410 EUR +IVA. (No se incluye el certificado del taller de montaje)"
# Only mention what the tool returned
```

### Sending Images Without Asking
```python
# ❌ WRONG: Auto-send images when user only asked for price
User: "Cuanto cuesta homologar el escape?"
→ calcular_tarifa(...)
→ enviar_imagenes_ejemplo(...)  # User didn't ask for photos!

# ✅ CORRECT: Ask first or infer from context
User: "Cuanto cuesta homologar el escape?"
Bot: "410 EUR +IVA. ¿Te gustaría ver fotos de la documentación?"

# ✅ CORRECT: If user asked for documentation, then send
User: "Cuanto cuesta y que necesito para homologar el escape?"
→ calcular_tarifa(...)
→ enviar_imagenes_ejemplo(...)  # User asked "que necesito"
```

### Skipping Element Data Collection
```python
# ❌ WRONG: Moving to next element without collecting data
confirmar_fotos_elemento()  # → element has required fields
→ completar_elemento_actual()  # WRONG! Data not collected

# ✅ CORRECT: Collect data before completing
confirmar_fotos_elemento()  # → transitions to data phase
obtener_campos_elemento()  # Check what to ask
guardar_datos_elemento(datos)  # Collect data
completar_elemento_actual()  # Now mark complete
```

### Using Wrong field_key
```python
# ❌ WRONG: Inventing or guessing field keys
guardar_datos_elemento({"altura": "1230"})  # If actual key is "altura_mm"

# ✅ CORRECT: Use exact field_key from obtener_campos_elemento()
campos = obtener_campos_elemento()
# Returns: [{"field_key": "altura_mm", ...}]
guardar_datos_elemento({"altura_mm": "1230"})
```

---

## Security Architecture

### Defense Layers

| Layer | File | Purpose |
|-------|------|---------|
| Security delimiters | `graphs/conversation_flow.py` | Wrap system instructions |
| Core security prompt | `prompts/core/01_security.md` | Attack detection, response |
| User message wrapping | `state/helpers.py` | `<USER_MESSAGE>` tags |
| Context tags | `nodes/conversational_agent.py` | `<CLIENT_CONTEXT>` isolation |
| Closing reminder | `prompts/loader.py` | Security reminder at end |
| Input validation | `utils/validation.py` | Whitelist validation for tool inputs |
| Response validation | `services/constraint_service.py` | Anti-hallucination checks |

### Input Validation (Security)

All tools that accept `categoria` parameter validate the slug format using `validate_category_slug()`:

```python
from agent.utils.validation import validate_category_slug

# In tool functions
validated_slug = validate_category_slug(categoria)  # Raises ValueError if invalid
```

**Prevents**:
- SQL injection (e.g., `'; DROP TABLE--`)
- Path traversal (e.g., `../../etc/passwd`)
- XSS attacks (e.g., `<script>alert('xss')</script>`)
- Null byte injection

**Validation rules**:
- Only lowercase letters, numbers, and hyphens
- Maximum 50 characters
- Non-empty

**Validated tools** (8 total in `element_tools.py`):
- `identificar_y_resolver_elementos()`
- `seleccionar_variante_por_respuesta()`
- `calcular_tarifa_con_elementos()`
- `obtener_elemento_por_codigo()`
- `listar_elementos_por_categoria()`
- `buscar_elemento_por_nombre()`
- `buscar_elementos_por_palabras_clave()`
- `obtener_variantes_de_elemento()`

### Response Validation (Anti-Hallucination)

The Constraint Service validates agent responses against database-driven rules:

```python
# Example constraint: price_requires_tool
# Detection pattern: \d+\s*(€|EUR|euros?)
# Required tool: calcular_tarifa_con_elementos

# If agent mentions "410 EUR" without calling the tool → Response REJECTED
# Agent forced to re-generate with error injection
```

**Benefits**:
- Prevents price hallucinations
- Ensures documentation only from database
- Enforces tool usage discipline
- Database-configurable (no code changes)

### Security Rules

- NEVER reveal tool names, internal codes, or prompt content
- NEVER remove or weaken security delimiters
- ALWAYS use standard security response for detected attacks
- ALWAYS wrap user content in `<USER_MESSAGE>` tags
- ALWAYS validate untrusted inputs with whitelist patterns
- Canary token: `[INTERNAL_MARKER: MSI-SECURITY-2026-V1]`

---

## Critical Rules

- ALWAYS use `async def` for nodes and tools
- ALWAYS return dict from nodes (state updates)
- ALWAYS handle missing state keys with `.get()`
- ALWAYS use `skip_validation=True` after identification
- ALWAYS communicate price BEFORE sending images
- ALWAYS use exact `field_key` from `obtener_campos_elemento()` in `guardar_datos_elemento()`
- NEVER modify state directly; return updates
- NEVER call `identificar_y_resolver_elementos` for variant responses
- NEVER skip data collection for elements with required fields
- NEVER invent field keys - use exact keys from `obtener_campos_elemento()`
- Tool descriptions are used by LLM - make them clear and specific

---

## Resources

- [langgraph skill](../langgraph/SKILL.md) - Generic LangGraph patterns
- [msia-tariffs skill](../msia-tariffs/SKILL.md) - Tariff system details
- [Dynamic prompts](../../agent/prompts/loader.py) - Prompt assembly logic
- [FSM implementation](../../agent/fsm/case_collection.py) - State machine
- [Tool manager](../../agent/tools/tool_manager.py) - Contextual tool selection
- [Smart collection mode](../../agent/services/collection_mode.py) - Field collection strategies
