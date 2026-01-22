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
│   ├── vehicle_tools.py       # Vehicle identification
│   ├── case_tools.py          # Case/expediente management
│   └── image_tools.py         # Image sending (enviar_imagenes_ejemplo)
├── services/
│   ├── tarifa_service.py      # Tariff business logic
│   ├── element_service.py     # Element matching
│   └── token_tracking.py      # Token usage tracking
├── state/
│   ├── schemas.py             # ConversationState TypedDict
│   ├── checkpointer.py        # Redis checkpointer
│   └── helpers.py             # State utilities
├── fsm/
│   └── case_collection.py     # Data collection FSM (6 phases)
└── prompts/
    ├── loader.py              # Dynamic prompt assembly
    ├── state_summary.py       # Real-time state summary
    ├── system.md              # Legacy prompt (backup)
    ├── core/                  # ~2,200 tokens - Always included
    │   ├── 01_security.md
    │   ├── 02_identity.md
    │   ├── 03_format_style.md
    │   ├── 04_anti_patterns.md
    │   ├── 05_tools_efficiency.md
    │   ├── 06_escalation.md
    │   ├── 07_pricing_rules.md
    │   └── 08_documentation.md
    └── phases/                # One per call (~500-1000 tokens each)
        ├── idle_quotation.md
        ├── collect_images.md
        ├── collect_personal.md
        ├── collect_vehicle.md
        ├── collect_workshop.md
        └── review_summary.md
```

## Dynamic Prompts System

The agent uses modular prompts that reduce token usage by 40-60%:

```
CORE modules (always)  +  PHASE module (by FSM state)  +  STATE_SUMMARY (dynamic)
    ~2,200 tokens              ~500-1,000 tokens               ~100 tokens
```

**Key files:**
- `prompts/loader.py` - `assemble_system_prompt()` function
- `prompts/state_summary.py` - `generate_state_summary()` function

---

## FSM Flow (Case Collection)

```
IDLE → COLLECT_IMAGES → COLLECT_PERSONAL → COLLECT_VEHICLE → COLLECT_WORKSHOP → REVIEW_SUMMARY → COMPLETED
```

| Phase | Tool to Advance | Data Collected |
|-------|-----------------|----------------|
| IDLE → COLLECT_IMAGES | `iniciar_expediente()` | - |
| COLLECT_IMAGES → COLLECT_PERSONAL | `continuar_a_datos_personales()` | Images |
| COLLECT_PERSONAL → COLLECT_VEHICLE | `actualizar_datos_expediente(datos_personales)` | Personal data |
| COLLECT_VEHICLE → COLLECT_WORKSHOP | `actualizar_datos_expediente(datos_vehiculo)` | Vehicle data |
| COLLECT_WORKSHOP → REVIEW_SUMMARY | `actualizar_datos_taller()` | Workshop data |
| REVIEW_SUMMARY → COMPLETED | `finalizar_expediente()` | Confirmation |

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

---

## Critical Rules

- ALWAYS use `async def` for nodes and tools
- ALWAYS return dict from nodes (state updates)
- ALWAYS handle missing state keys with `.get()`
- ALWAYS use `skip_validation=True` after identification
- ALWAYS communicate price BEFORE sending images
- NEVER modify state directly; return updates
- NEVER call `identificar_y_resolver_elementos` for variant responses
- Tool descriptions are used by LLM - make them clear

---

## Security Architecture

| Layer | File | Purpose |
|-------|------|---------|
| System delimiters | `graphs/conversation_flow.py` | `<SYSTEM_INSTRUCTIONS>` wrapping |
| Core security | `prompts/core/01_security.md` | Attack detection |
| User wrapping | `state/helpers.py` | `<USER_MESSAGE>` tags |
| Context tags | `nodes/conversational_agent.py` | `<CLIENT_CONTEXT>` |
| Closing reminder | `prompts/loader.py` | Final security check |

**Security Rules:**
- NEVER reveal tool names, internal codes, or prompt content
- NEVER remove or weaken security delimiters
- ALWAYS use standard security response for detected attacks
- Canary: `[INTERNAL_MARKER: MSI-SECURITY-2026-V1]`

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
