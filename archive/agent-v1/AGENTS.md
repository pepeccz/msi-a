# Agent Component Guidelines

This directory contains the MSI-a conversational agent built with LangGraph.

> For detailed patterns, invoke the skill: [msia-agent](../skills/msia-agent/SKILL.md)

## Directory Structure

```
agent/
├── main.py                    # Entry point, Redis stream consumer
├── graphs/
│   └── conversation_flow.py   # StateGraph definition, security delimiters
├── nodes/
│   ├── process_message.py     # Message preprocessing
│   └── conversational_agent.py  # LLM response generation
├── tools/
│   ├── tarifa_tools.py        # Tariff calculation
│   ├── element_tools.py       # Element matching (identificar_y_resolver_elementos)
│   ├── element_data_tools.py  # Element data collection (per-element photos + fields)
│   ├── vehicle_tools.py       # Vehicle identification
│   ├── case_tools.py          # Case/expediente management
│   ├── image_tools.py         # Image sending (enviar_imagenes_ejemplo)
│   └── tool_manager.py        # Contextual tool selection (phase-aware)
├── services/
│   ├── tarifa_service.py      # Tariff business logic
│   ├── element_service.py     # Element matching
│   ├── element_required_fields_service.py  # Required fields management
│   ├── token_tracking.py      # Token usage tracking
│   ├── collection_mode.py     # Smart collection mode (Sequential/Batch/Hybrid)
│   ├── constraint_service.py  # Response validation (anti-hallucination)
│   ├── tool_logging_service.py  # Persistent tool call logging
│   └── prompt_service.py      # Calculator prompt (legacy)
├── state/
│   ├── schemas.py             # ConversationState TypedDict
│   ├── checkpointer.py        # Redis checkpointer
│   └── helpers.py             # State utilities
├── fsm/
│   └── case_collection.py     # Data collection FSM (7 phases)
├── utils/
│   └── validation.py          # Input validation (security)
├── routing/
│   └── __init__.py            # Placeholder for intent routing
└── prompts/
    ├── loader.py              # Dynamic prompt assembly
    ├── state_summary.py       # Real-time state summary
    ├── calculator_base.py     # Calculator prompt template
    ├── system.md              # Legacy prompt (backup)
    ├── core/                  # ~2,200 tokens - Always included
    │   ├── 01_security.md
    │   ├── 02_identity.md
    │   ├── 03_format_style.md
    │   ├── 04_anti_patterns.md
    │   ├── 05_tools_efficiency.md
    │   ├── 06_escalation.md
    │   ├── 07_pricing_rules.md
    │   ├── 08_documentation.md
    │   └── 09_fsm_awareness.md
    └── phases/                # One per call (~500-1000 tokens each)
        ├── idle_quotation.md
        ├── collect_element_data.md
        ├── collect_base_docs.md
        ├── collect_personal.md
        ├── collect_vehicle.md
        ├── collect_workshop.md
        └── review_summary.md
```

---

## Dynamic Prompts System

The agent uses modular prompts that reduce token usage by 40-60%:

```
CORE modules (always)  +  PHASE module (by FSM state)  +  STATE_SUMMARY (dynamic)
    ~2,200 tokens              ~500-1,000 tokens               ~100 tokens
```

**Key files:**
- `prompts/loader.py` - `assemble_system_prompt()` function
- `prompts/state_summary.py` - `generate_state_summary()` function

**Core modules** (496 lines total):
- `01_security.md` - Security, anti-jailbreak (21 lines)
- `02_identity.md` - MSI-a identity (18 lines)
- `03_format_style.md` - Tone, format (15 lines)
- `04_anti_patterns.md` - Anti-loop, anti-invention (82 lines)
- `05_tools_efficiency.md` - Tool usage rules (144 lines)
- `06_escalation.md` - When to escalate (26 lines)
- `07_pricing_rules.md` - Price communication (124 lines)
- `08_documentation.md` - Documentation rules (27 lines)
- `09_fsm_awareness.md` - FSM context awareness (39 lines)

**Phase modules** (448 lines total):
- `idle_quotation.md` - Presupuestación (103 lines)
- `collect_element_data.md` - Element photos + data (71 lines)
- `collect_base_docs.md` - Base vehicle docs (73 lines)
- `collect_personal.md` - Personal data (51 lines)
- `collect_vehicle.md` - Vehicle data (40 lines)
- `collect_workshop.md` - Workshop data (48 lines)
- `review_summary.md` - Final review (62 lines)

---

## Services (Organized by Functionality)

### Core Services

#### `tarifa_service.py` - Tariff Calculation
- **Purpose**: Business logic for tariff calculation with Redis caching
- **Key functions**:
  - `calculate_tariff_with_elements()` - Calculate price for element codes
  - `get_tariff_tier_by_code()` - Get tier details
  - `classify_elements_to_tier()` - Match elements to tariff tier
- **Caching**: 5 minutes TTL in Redis

#### `element_service.py` - Element Matching
- **Purpose**: Element identification and variant resolution
- **Key functions**:
  - `match_elements_with_unmatched()` - NLP-based element matching with unmatched term detection
  - `match_elements_from_description()` - Simplified matching (wrapper around match_elements_with_unmatched)
  - `get_element_variants()` - Get variants for a base element
  - `get_element_with_images()` - Fetch element details with images
- **Features**: Fuzzy matching, synonym support, variant handling, quantity extraction, negation detection

#### `token_tracking.py` - Token Usage Tracking
- **Purpose**: Track LLM token consumption per conversation
- **Storage**: Redis with 24h TTL
- **Metrics**: Input tokens, output tokens, total tokens, cost estimation

### Collection Services

#### `collection_mode.py` - Smart Collection Mode ⭐ NEW
- **Purpose**: Determines optimal data collection strategy for element fields
- **Modes**:
  - **SEQUENTIAL**: 1-2 fields or complex conditionals → ask one at a time
  - **BATCH**: 3+ fields without conditionals → ask all at once
  - **HYBRID**: Mix → base fields first, then conditionals as a group
- **Decision logic**:
  ```python
  determine_collection_mode(fields, collected_values) → CollectionMode
  ```
- **Benefits**: More conversational for simple cases, efficient for complex ones
- **Example**:
  ```python
  # For 5 fields without conditionals
  mode = determine_collection_mode(fields)  # → BATCH
  fields_structure = get_fields_for_mode(mode, fields)
  # Returns all 5 fields to ask at once
  
  # For 2 fields with nested conditionals
  mode = determine_collection_mode(fields)  # → SEQUENTIAL
  # Returns current_field (one at a time)
  ```

#### `element_required_fields_service.py` - Required Fields Management ⭐ NEW
- **Purpose**: Manage element-specific required fields during case collection
- **Key functions**:
  - `get_fields_for_element()` - Get all required fields for an element
  - `evaluate_field_condition()` - Check if conditional field should be shown
  - `validate_field_value()` - Validate field value against type and rules
  - `get_missing_required_fields()` - Get list of missing required fields
- **Features**:
  - Conditional field evaluation (show/hide based on other fields)
  - Type validation (number, text, boolean, select)
  - Validation rules (min/max, pattern, options)
- **Example**:
  ```python
  # Get applicable fields based on what's already collected
  fields = await service.get_applicable_fields(
      element_id="uuid",
      collected_values={"tipo_montaje": "fijo"}
  )
  # Returns only fields that apply (conditional evaluation)
  
  # Validate a field value
  is_valid, error = service.validate_field_value(
      value="1230",
      field=field_obj  # ElementRequiredField
  )
  ```

### Security & Validation Services

#### `constraint_service.py` - Response Validation ⭐ NEW
- **Purpose**: Database-driven validation of LLM responses to prevent hallucinations
- **How it works**:
  1. Load constraints from `response_constraints` table
  2. Check agent response against regex patterns
  3. If pattern matches, verify required tool was called
  4. If not, inject error message to force re-generation
- **Example constraint**:
  ```python
  # Constraint: price_requires_tool
  # Pattern: \d+\s*(€|EUR|euros?)
  # Required tool: calcular_tarifa_con_elementos
  
  # If agent mentions "410 EUR" without calling the tool → BLOCKED
  ```
- **Caching**: 5 minutes TTL per category
- **Skip conditions**: Some constraints skipped during active case collection

#### `tool_logging_service.py` - Tool Call Logging ⭐ NEW
- **Purpose**: Persistent logging of agent tool invocations to PostgreSQL
- **Storage**: `tool_call_logs` table (persists indefinitely)
- **Data logged**:
  - Conversation ID
  - Tool name
  - Parameters (sanitized)
  - Result summary (truncated to 500 chars)
  - Result type (success/error/blocked)
  - Execution time (ms)
  - Iteration number
- **Features**:
  - Fire-and-forget (errors never block agent)
  - Automatic result classification
  - Parameter sanitization (removes sensitive data)
- **Use case**: Post-hoc debugging, conversation analysis

### Legacy Services

#### `prompt_service.py` - Calculator Prompt (Legacy)
- **Purpose**: Generates calculator prompts for tariff calculation (pre-dynamic prompts)
- **Status**: Mostly superseded by dynamic prompts system
- **Still used for**: Certain admin preview endpoints

---

## Tools (Contextual Selection)

### Tool Manager - Contextual Tool Selection ⭐ NEW

**File**: `tools/tool_manager.py`

**Purpose**: Reduces token usage by sending only phase-relevant tools to the LLM.

**Token savings**:
- **Before**: 27 tools × ~150 tokens = ~4,050 tokens per call
- **After**: 5-12 tools × ~150 tokens = ~750-1,800 tokens per call
- **Savings**: ~2,500-3,600 tokens per call (57-82% reduction in tool tokens)

**How it works**:
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

**Tools by phase**:

| Phase | Tool Count | Tools |
|-------|------------|-------|
| **IDLE** | 13 | identificar_y_resolver_elementos, seleccionar_variante_por_respuesta, calcular_tarifa_con_elementos, listar_categorias, listar_tarifas, listar_elementos, obtener_servicios_adicionales, obtener_documentacion_elemento, identificar_tipo_vehiculo, enviar_imagenes_ejemplo, iniciar_expediente, escalar_a_humano |
| **COLLECT_ELEMENT_DATA** | 9 | confirmar_fotos_elemento, guardar_datos_elemento, completar_elemento_actual, obtener_progreso_elementos, obtener_campos_elemento, reenviar_imagenes_elemento, enviar_imagenes_ejemplo, consulta_durante_expediente, obtener_estado_expediente, cancelar_expediente, escalar_a_humano |
| **COLLECT_BASE_DOCS** | 5 | confirmar_documentacion_base, enviar_imagenes_ejemplo, consulta_durante_expediente, obtener_estado_expediente, cancelar_expediente, escalar_a_humano |
| **COLLECT_PERSONAL** | 4 | actualizar_datos_expediente (datos_personales), consulta_durante_expediente, obtener_estado_expediente, cancelar_expediente, escalar_a_humano |
| **COLLECT_VEHICLE** | 4 | actualizar_datos_expediente (datos_vehiculo), consulta_durante_expediente, obtener_estado_expediente, cancelar_expediente, escalar_a_humano |
| **COLLECT_WORKSHOP** | 4 | actualizar_datos_taller, consulta_durante_expediente, obtener_estado_expediente, cancelar_expediente, escalar_a_humano |
| **REVIEW_SUMMARY** | 4 | finalizar_expediente, editar_expediente, consulta_durante_expediente, obtener_estado_expediente, escalar_a_humano |

### Element Data Collection Tools ⭐ NEW

**File**: `tools/element_data_tools.py`

**Purpose**: Element-by-element data collection (photos + required fields per element).

**Flow per element**:
1. Show example images → `enviar_imagenes_ejemplo()`
2. User sends photos (auto-saved by main.py)
3. User says "listo" → `confirmar_fotos_elemento()`
4. Ask required data fields → Uses Smart Collection Mode
5. User provides data → `guardar_datos_elemento(datos)`
6. Mark element complete → `completar_elemento_actual()`
7. Repeat for next element

**Tools** (7 total):

#### `obtener_campos_elemento(element_code?)`
Get required fields for current or specified element.
- **Returns**: Field list with types, labels, instructions, validation rules
- **Use case**: Check what data to ask for an element

#### `guardar_datos_elemento(datos, element_code?)`
Save technical data for current element.
- **Input**: `{"field_key": value, ...}`
- **Validation**: Type checking, range checking, conditional evaluation
- **Returns**: Validation results per field, next field(s) to ask
- **Features**:
  - Multi-field save (save multiple fields at once)
  - Automatic field key normalization (handles ñ → n, accents)
  - Smart Collection Mode integration
  - Error recovery guidance

#### `confirmar_fotos_elemento()`
Confirm user has sent all photos for current element.
- **Use**: When user says "listo" after sending photos
- **Action**: Marks photos as done, transitions to data phase
- **Smart behavior**: Uses Smart Collection Mode to determine how to ask for fields

#### `completar_elemento_actual()`
Mark current element as complete, move to next element.
- **Validation**: Checks all required fields are collected
- **Action**: Transitions to next element or COLLECT_BASE_DOCS if all done

#### `obtener_progreso_elementos()`
Get collection progress for all elements.
- **Returns**: Completed count, total count, current element, current phase

#### `confirmar_documentacion_base(usuario_confirma?)`
Confirm base vehicle documentation received.
- **Validation**: Checks image count in database
- **Reconciliation**: If user confirms but no images → silent escalation
- **Action**: Transitions to COLLECT_PERSONAL

#### `reenviar_imagenes_elemento(element_code?)`
Resend example images for current or specified element.
- **Use**: When user asks to see photos again

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

### FSM Phase Details

| Phase | Tool to Advance | Data Collected | Smart Features |
|-------|-----------------|----------------|----------------|
| **IDLE → COLLECT_ELEMENT_DATA** | `iniciar_expediente()` | - | Creates case, stores tariff |
| **COLLECT_ELEMENT_DATA (photos)** | `confirmar_fotos_elemento()` | Element photos (per element) | Auto-saved by main.py, batch tracking |
| **COLLECT_ELEMENT_DATA (data)** | `guardar_datos_elemento()` + `completar_elemento_actual()` | Element technical data (per element) | Smart Collection Mode, conditional fields |
| **COLLECT_ELEMENT_DATA → COLLECT_BASE_DOCS** | Auto after all elements | - | Automatic transition |
| **COLLECT_BASE_DOCS → COLLECT_PERSONAL** | `confirmar_documentacion_base()` | Ficha técnica, permiso, vistas | Image count validation, reconciliation |
| **COLLECT_PERSONAL → COLLECT_VEHICLE** | `actualizar_datos_expediente(datos_personales)` | Personal data (nombre, apellidos, email, teléfono, DNI/CIF, domicilio, ITV) | Validation rules |
| **COLLECT_VEHICLE → COLLECT_WORKSHOP** | `actualizar_datos_expediente(datos_vehiculo)` | Vehicle data (marca, modelo, año, matrícula, bastidor) | Matrícula validation |
| **COLLECT_WORKSHOP → REVIEW_SUMMARY** | `actualizar_datos_taller()` | Workshop data (if taller_propio=True) | Optional section |
| **REVIEW_SUMMARY → COMPLETED** | `finalizar_expediente()` | Confirmation | Creates escalation, sends to admin |

### Element-by-Element Collection Flow

**For each element in `element_codes`:**

1. **Photos Phase** (`element_phase="photos"`):
   - Agent sends example images with `enviar_imagenes_ejemplo()`
   - User sends photos via WhatsApp (auto-saved by `main.py`)
   - User says "listo" → Agent calls `confirmar_fotos_elemento()`
   - FSM updates: `element_phase="data"`, `element_data_status[code]="photos_done"`

2. **Data Phase** (`element_phase="data"`):
   - Agent calls `obtener_campos_elemento()` to check required fields
   - **Smart Collection Mode** determines how to ask:
     - Sequential: Ask one field at a time (1-2 fields)
     - Batch: Ask all fields at once (3+ fields, no conditionals)
     - Hybrid: Ask base fields, then conditional fields
   - User provides data → Agent calls `guardar_datos_elemento(datos)`
   - Validation happens (type, range, conditionals)
   - If all required fields collected → Agent calls `completar_elemento_actual()`
   - FSM updates: `element_data_status[code]="complete"`, move to next element

3. **Next Element**:
   - FSM increments `current_element_index`
   - Resets `element_phase="photos"`
   - Repeat for next element

4. **All Elements Done**:
   - FSM auto-transitions to `COLLECT_BASE_DOCS`

---

## Security & Validation

### Input Validation ⭐ NEW

**File**: `utils/validation.py`

**Purpose**: Whitelist-based input validation to prevent injection attacks.

**Function**: `validate_category_slug(slug: str) -> str`

**Validation rules**:
- Only lowercase letters (a-z)
- Numbers (0-9)
- Hyphens (-)
- Maximum 50 characters
- Non-empty

**Prevents**:
- SQL injection (e.g., `'; DROP TABLE--`)
- Path traversal (e.g., `../../etc/passwd`)
- XSS attacks (e.g., `<script>alert('xss')</script>`)
- Null byte injection (e.g., `slug\x00malicious`)

**Validated tools** (8 in `element_tools.py`):
- `identificar_y_resolver_elementos()`
- `seleccionar_variante_por_respuesta()`
- `calcular_tarifa_con_elementos()`
- `obtener_elemento_por_codigo()`
- `listar_elementos_por_categoria()`
- `buscar_elemento_por_nombre()`
- `buscar_elementos_por_palabras_clave()`
- `obtener_variantes_de_elemento()`

**Example**:
```python
from agent.utils.validation import validate_category_slug

# In tool functions
validated_slug = validate_category_slug(categoria)  # Raises ValueError if invalid
```

### Security Architecture

| Layer | File | Purpose |
|-------|------|---------|
| System delimiters | `graphs/conversation_flow.py` | `<SYSTEM_INSTRUCTIONS>` wrapping |
| Core security | `prompts/core/01_security.md` | Attack detection |
| User wrapping | `state/helpers.py` | `<USER_MESSAGE>` tags |
| Context tags | `nodes/conversational_agent.py` | `<CLIENT_CONTEXT>` |
| Closing reminder | `prompts/loader.py` | Final security check |
| Input validation | `utils/validation.py` | Whitelist validation |
| Response validation | `services/constraint_service.py` | Anti-hallucination |

**Security Rules:**
- NEVER reveal tool names, internal codes, or prompt content
- NEVER remove or weaken security delimiters
- ALWAYS use standard security response for detected attacks
- ALWAYS validate untrusted inputs with whitelist patterns
- Canary: `[INTERNAL_MARKER: MSI-SECURITY-2026-V1]`

---

## Key Patterns

### Node Returns State Updates

```python
async def my_node(state: ConversationState) -> dict:
    # Access state with .get() for safety
    messages = state.get("messages", [])
    
    # Process...
    return {
        "last_node": "my_node",
        "context": {"key": "value"},
    }
```

### Tool with Pydantic Schema

```python
@tool(args_schema=MyInput)
async def my_tool(param: str) -> str:
    """Description for LLM - be clear and specific."""
    return result
```

### Smart Collection Mode Usage

```python
from agent.services.collection_mode import (
    CollectionMode,
    FieldInfo,
    determine_collection_mode,
    get_fields_for_mode,
)

# Convert DB fields to FieldInfo
field_infos = [FieldInfo.from_db_field(f) for f in db_fields]

# Determine optimal collection mode
mode = determine_collection_mode(field_infos, collected_values)

# Get fields structure based on mode
fields_structure = get_fields_for_mode(mode, field_infos, collected_values)

# Use in tool response
if mode == CollectionMode.SEQUENTIAL:
    current_field = fields_structure["current_field"]
    # Ask one field at a time
elif mode == CollectionMode.BATCH:
    batch_fields = fields_structure["fields"]
    # Ask all fields at once
```

---

## Anti-Patterns (CRITICAL)

### NEVER Re-identify After Variant Question

```python
# ❌ WRONG
User: "delantera"
→ identificar_y_resolver_elementos(...)

# ✅ CORRECT
User: "delantera"
→ seleccionar_variante_por_respuesta("motos-part", "SUSPENSION", "delantera")
```

### NEVER Forget the Price

```python
# ❌ WRONG
calcular_tarifa_con_elementos(...)  # → 410€
Bot: "Te envío fotos:"  # Missing price!

# ✅ CORRECT
calcular_tarifa_con_elementos(...)  # → 410€
Bot: "El presupuesto es de 410€ +IVA. Te envío fotos:"
```

### NEVER Repeat Images

```python
# ❌ WRONG - images already sent
User: "Dale, adelante"
→ enviar_imagenes_ejemplo(...)

# ✅ CORRECT
User: "Dale, adelante"
→ iniciar_expediente(...)
```

### NEVER Skip Element Data Collection

```python
# ❌ WRONG - moving to next element without data
confirmar_fotos_elemento()  # → has required fields
→ completar_elemento_actual()  # WRONG! Data not collected

# ✅ CORRECT
confirmar_fotos_elemento()  # → transitions to data phase
obtener_campos_elemento()  # Check what to ask
guardar_datos_elemento(datos)  # Collect data
completar_elemento_actual()  # Now mark complete
```

### NEVER Use Incorrect field_key

```python
# ❌ WRONG - inventing field keys
guardar_datos_elemento({"altura": "1230"})  # If field_key is "altura_mm"

# ✅ CORRECT - use exact field_key from obtener_campos_elemento()
campos = obtener_campos_elemento()
# Returns: [{"field_key": "altura_mm", "field_label": "Altura", ...}]
guardar_datos_elemento({"altura_mm": "1230"})
```

### NEVER Use Wrong FSM State Key ⚠️ CRITICAL BUG

```python
# ❌ WRONG - state update will be silently ignored by the node
@tool
async def my_fsm_tool():
    new_fsm_state = update_case_fsm_state(fsm_state, {...})
    return {
        "success": True,
        "fsm_state": new_fsm_state,  # WRONG KEY! Node won't recognize this
    }

# ✅ CORRECT - use "fsm_state_update" (with _update suffix)
@tool
async def my_fsm_tool():
    new_fsm_state = update_case_fsm_state(fsm_state, {...})
    return {
        "success": True,
        "fsm_state_update": new_fsm_state,  # Correct key
    }
```

**Why this matters**: The `conversational_agent.py` node only checks for `"fsm_state_update"` (line 1255). If you return `"fsm_state"` (without `_update`), the state update will be **silently ignored**, causing the FSM to get stuck in the current phase.

**Affected tools**: All FSM-modifying tools (`iniciar_expediente`, `completar_elemento_actual`, `confirmar_fotos_elemento`, `confirmar_documentacion_base`, `actualizar_datos_expediente`, `actualizar_datos_taller`, `finalizar_expediente`, `cancelar_expediente`)

---

## Critical Rules

- ALWAYS use `async def` for nodes and tools
- ALWAYS return dict from nodes (state updates)
- ALWAYS handle missing state keys with `.get()`
- ALWAYS use `skip_validation=True` after identification
- ALWAYS communicate price BEFORE sending images
- ALWAYS use exact `field_key` from `obtener_campos_elemento()` in `guardar_datos_elemento()`
- ALWAYS return `"fsm_state_update"` (NOT `"fsm_state"`) from FSM-modifying tools — the node only recognizes `"fsm_state_update"`
- NEVER modify state directly; return updates
- NEVER call `identificar_y_resolver_elementos` for variant responses
- NEVER skip data collection for elements with required fields
- Tool descriptions are used by LLM - make them clear

---

## Routing (Placeholder)

**File**: `routing/__init__.py`

**Status**: Empty placeholder for future intent routing and classification.

**Planned features**:
- Intent classification (quotation, expediente, question, escalation)
- Multi-intent detection
- Confidence scoring

---

### Auto-invoke Skills

When performing these actions, ALWAYS invoke the corresponding skill FIRST:

| Action | Skill |
|--------|-------|
| Creating/modifying agent tools | `msia-agent` |
| Creating/modifying graph nodes | `msia-agent` |
| Working on FSM case collection | `msia-agent` |
| Working on LangGraph graphs/nodes | `langgraph` |
| Working on agent conversation flow | `msia-agent` |
| Working on system prompts | `msia-agent` |
| Working with ConversationState | `msia-agent` |
| Working with tariffs or elements | `msia-tariffs` |
| Writing Python tests | `pytest-async` |
| Writing tests for MSI-a | `msia-test` |
