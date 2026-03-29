# Agent Component Guidelines

This directory contains the MSI-a conversational agent built with LangGraph.

> **Architecture**: Mode-based conversation flow with intent routing, digression management, and per-mode fallback handling.

> **Note**: v1 (FSM-based) has been archived to `archive/agent-v1/`. This is the current production architecture.

---

## Directory Structure

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
│   ├── presupuesto_mode.py      # PRESUPUESTO_MODE (~90% traffic) — pricing + images (fusionado con viabilidad)
│   ├── evaluacion_gateway.py    # EVALUACION_GATEWAY — yes/no confirmation (pattern-based)
│   └── expediente_mode.py       # EXPEDIENTE_MODE — formal case collection (6 sub-modes)
├── graph/
│   └── conversation_graph.py    # StateGraph definition (preprocess → router → modes)
├── prompts/
│   ├── loader.py                # Dynamic prompt assembly (core + mode + context)
│   ├── core/                    # Core prompts (always loaded, ~7,900 tokens)
│   │   ├── 01_security.md
│   │   ├── 02_identity.md
│   │   ├── 03_format_style.md
│   │   ├── 04_anti_patterns.md
│   │   ├── 05_tools_efficiency.md
│   │   ├── 06_escalation.md
│   │   ├── 07_pricing_rules.md
│   │   ├── 08_documentation.md
│   │   ├── 09_inline_questions.md
│   │   └── 10_expediente_universal.md
│   └── modes/                   # Mode-specific prompts (~500-1,000 tokens each)
│       ├── consulta_mode.md
│       ├── presupuesto_mode.md
│       ├── presupuesto_mode_post_price.md
│       ├── expediente_documentacion_elementos.md
│       ├── expediente_documentacion_base.md
│       ├── expediente_datos_personales.md
│       ├── expediente_datos_vehiculo.md
│       ├── expediente_taller.md
│       └── expediente_revision.md
├── tools/                       # LangChain tools (recycled from v1, battle-tested)
│   ├── element_tools.py         # Element identification & pricing (8 tools)
│   ├── tarifa_tools.py          # Tariff calculation (4 tools)
│   ├── case_tools.py            # Case management (8 tools)
│   ├── element_data_tools.py    # Element data collection (7 tools)
│   ├── image_tools.py           # Example image sending (1 tool)
│   ├── vehicle_tools.py         # Vehicle classification (1 tool)
│   └── shared_tools.py          # Universal tools (escalar_a_humano)
├── services/                    # Business logic (recycled from v1)
│   ├── tarifa_service.py        # Tariff calculation with Redis caching
│   ├── element_service.py       # Element matching (NLP + fuzzy + variants)
│   ├── collection_mode.py       # Smart collection mode (Sequential/Batch/Hybrid)
│   ├── element_required_fields_service.py  # Conditional field management
│   ├── constraint_service.py    # Response validation (anti-hallucination)
│   ├── tool_logging_service.py  # Persistent tool call logging
│   ├── token_tracking.py        # Token usage tracking
│   └── prompt_service.py        # Legacy calculator prompts
└── utils/
    └── validation.py            # Input validation (whitelist-based)
```

---

## Architecture Overview

### Conversation Flow

```
┌──────────────┐
│    START     │ (user message arrives via Redis Streams)
└──────┬───────┘
       │
┌──────▼───────┐
│  preprocess  │ (extract message, update counters, check panic button)
└──────┬───────┘
       │
┌──────▼───────┐
│    router    │ (intent classification OR digression detection)
└──────┬───────┘
       │ (conditional edge based on current_mode)
       │
   ┌───┴──────────────────┐
   │                      │
   ▼                      ▼
┌──────────────┐    ┌──────────────┐
│ consulta_mode│    │presupuesto   │ ← Main entry (90% traffic)
└──────────────┘    └──────┬───────┘
   │                       │
   │                ┌──────▼───────┐
   │                │ eval_gateway │
   │                └──────┬───────┘
   │                       │
   └───────────────────────┼────────────┐
                           │            │
                           ▼            ▼
                    ┌──────────────┐   ┌──────────────┐
                    │ expediente   │   │  escalation  │───► END
                    └──────────────┘   └──────────────┘
                    (6 sub-modes)
```

### Mode-Based Architecture

**Modes** replace v1's FSM. Each mode is a self-contained conversation context with:
- **Dedicated prompt** (core + mode-specific instructions)
- **Filtered tools** (only relevant tools per mode)
- **LLM-driven flow** (system prompt guides the LLM, not hardcoded Python logic)
- **Automatic transitions** (tools return updates to `current_mode`)

| Mode              | Traffic | Purpose                             | Tools    |
| ----------------- | ------- | ----------------------------------- | -------- |
| CONSULTA          | ~10%    | Educational queries, catalog browse | 5 tools  |
| PRESUPUESTO       | ~90%    | Direct pricing + images (fusionado VIABILIDAD) | 10 tools |
| EVALUACION_GATEWAY| Entry   | Yes/no confirmation (pattern-based, **sin prompt dedicado** — lógica en `evaluacion_gateway.py`, no usa LLM) | 0 tools  |
| EXPEDIENTE        | Complex | Formal case collection (6 sub-modes)| 26 tools |
| ESCALATION        | Terminal| Human handoff                       | 0 tools  |

---

## Key Components

### 1. Intent Router (`router/intent_router.py`)

**Purpose**: Classify user intent from START mode.

**Strategy**:
1. **Keyword patterns** (fast, 9 intents)
2. **LLM classification** (qwen2.5:3b, local, cheap)
3. **AMBIGUO fallback** (clarification question)

**Intents**: `CONSULTA_GENERAL`, `PRESUPUESTO_DIRECTO`, `INICIAR_EXPEDIENTE`, `CONFIRMACION`, `RECHAZO`, `VER_IMAGENES`, `ABRIR_EXPEDIENTE`, `MODIFICAR_ELEMENTOS`, `AMBIGUO`

**Confidence threshold**: 0.75 (below → clarification)

---

### 2. Digression Manager (`router/digression_manager.py`)

**Purpose**: Detect off-topic messages in **focused modes** (PRESUPUESTO, EXPEDIENTE).

**Strategy**:
1. **Permissive modes** (CONSULTA) → skip digression check
2. **Focused modes** (PRESUPUESTO, EXPEDIENTE) → regex patterns + in-context detection
3. **Detected** → transition to target mode (if allowed by transition rules)

**Digression types**: `OFF_TOPIC`, `GREETING`, `QUESTION`, `ESCALATION`

---

### 3. Fallback Handler (`fallback/fallback_handler.py`)

**Purpose**: Per-mode retry policies and progressive reprompts.

**Retry policies**:
- `CONSULTA_MODE`: 2 retries, escalate on limit
- `PRESUPUESTO_MODE`: 4 retries, escalate on limit (blocking mode) — increased for higher traffic
- `EXPEDIENTE_MODE`: 5 retries, escalate on limit (blocking mode)
- `EVALUACION_GATEWAY`: 2 retries, reset mode on limit

**Progressive reprompts**: Each retry incrementally adds more context/guidance.

---

### 4. Mode Nodes (`modes/*.py`)

**BaseModeNode** (`base_mode.py`):
- **Entry point**: `process(state)` — wraps `_process_message()` with error handling
- **Fallback integration**: Records errors, checks retry limits, executes fallback
- **Shared pattern**: All modes extend this

**Mode implementations**:
- **CONSULTA** (~430 lines): LLM loop with RAG tool
- **PRESUPUESTO** (~800 lines): Direct pricing + images (fusionado con viabilidad, price-before-images enforced)
- **EVALUACION_GATEWAY** (~240 lines): Pattern-based yes/no (NO LLM)
- **EXPEDIENTE** (~1,000 lines): Sub-mode orchestration (6 handlers)

---

### 5. Dynamic Prompts (`prompts/`)

**Structure**:
```
CORE modules (always)  +  MODE module (by mode)  +  MODE CONTEXT (dynamic)
    ~7,900 tokens            ~500-1,000 tokens         ~200-500 tokens
```

**Token savings vs. v1**: ~40-60% reduction (context-aware loading)

**Core modules** (10 files):
- Security, identity, format, anti-patterns, tools, escalation, pricing, documentation, inline questions, expediente universal

**Mode modules** (varies):
- One prompt per mode (10 files total: 3 top-level modes + 1 post-price variant + 6 expediente sub-modes)

---

### 6. Tools (Recycled from v1)

**26 tools total**, organized by category:

| Category           | Tools                                                           |
| ------------------ | --------------------------------------------------------------- |
| Element Tools      | `identificar_y_resolver_elementos`, `seleccionar_variante`, ... |
| Tariff Tools       | `calcular_tarifa_con_elementos`, `listar_categorias`, ...       |
| Case Tools         | `iniciar_expediente`, `actualizar_datos_expediente`, ...        |
| Element Data Tools | `guardar_datos_elemento`, `confirmar_fotos_elemento`, ...       |
| Image Tools        | `enviar_imagenes_ejemplo`                                       |
| Vehicle Tools      | `identificar_tipo_vehiculo`                                     |
| Shared Tools       | `escalar_a_humano`                                              |

**Tool filtering**: Each mode loads only relevant tools (reduces token usage)

---

## EXPEDIENTE Mode (Sub-modes)

**6 sub-modes** for formal case collection:

1. **COLLECT_ELEMENT_DATA**: Photos + technical data per element (element-by-element)
2. **COLLECT_BASE_DOCS**: Ficha técnica, permiso, vistas
3. **COLLECT_PERSONAL**: Nombre, DNI, email, domicilio, ITV
4. **COLLECT_VEHICLE**: Marca, modelo, matrícula, bastidor
5. **COLLECT_WORKSHOP**: Decision (MSI vs. propio) + workshop data if needed
6. **REVIEW_SUMMARY**: Present summary, confirm or edit

**Sub-mode storage**: `mode_context["expediente_sub_mode"]` (string)

**Transitions**: Automatic via tool returns (e.g., `completar_elemento_actual()` → next element or COLLECT_BASE_DOCS)

---

## Key Patterns

### Mode Node Pattern

```python
class MyModeNode(BaseModeNode):
    def __init__(self):
        super().__init__("MY_MODE")
    
    async def _process_message(self, message, state):
        # 1. Build system prompt
        system_prompt = assemble_system_prompt(mode="MY_MODE", ...)
        
        # 2. Build LLM messages
        llm_messages = [{"role": "system", "content": system_prompt}, ...]
        
        # 3. Get LLM with tools
        tools = self.get_tools()
        llm = self._get_llm(tools)
        
        # 4. Tool calling loop
        for iteration in range(MAX_TOOL_ITERATIONS):
            response = await llm.ainvoke(llm_messages)
            # Execute tools, update context, etc.
        
        # 5. Return state updates
        return {"ai_response": response, "mode_context": updated_context}
    
    def get_tools(self):
        return [tool1, tool2, ...]
```

### Tool Return Pattern (Sub-mode Transitions)

```python
# In a tool (e.g., completar_elemento_actual)
return {
    "success": True,
    "all_elements_complete": True,  # Signals transition
    # ... other data
}

# In mode's _extract_context_from_tool():
if tool_name == "completar_elemento_actual":
    if data.get("all_elements_complete"):
        updates["expediente_sub_mode"] = "collect_base_docs"
```

### Tool-Driven State Management (REFACTOR-001)

**NEW**: Tools explicitly declare state changes via `_internal_flags` (ADR-005).

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

# After tool execution
_apply_tool_flags(mode_context, tool_result, logger)
# mode_context["precio_comunicado"] = True (applied immediately)
# Persists to Redis checkpoint via mode_context reducer
```

**Why**: Eliminates fragile pattern matching on LLM responses. State changes are explicit, testable, and persist reliably.

**Affected tools**:
- `calcular_tarifa_con_elementos` → Sets `precio_comunicado`, resets `imagenes_enviadas`
- `enviar_imagenes_ejemplo` → Sets `imagenes_enviadas`
- `identificar_y_resolver_elementos` → Resets flags for new identification

**See**: `docs/decisions/005-tool-driven-state-management.md` for full details.

---

## Critical Rules

1. **NEVER re-identify after variant question** — Use `seleccionar_variante_por_respuesta()`, not `identificar_y_resolver_elementos()`
2. **PRICE BEFORE IMAGES** — `enviar_imagenes_ejemplo` blocks if price not mentioned first
3. **Skip validation after ID** — Always use `skip_validation=True` in `calcular_tarifa_con_elementos()` after identification
4. **Exact field_key** — Use exact `field_key` from `obtener_campos_elemento()` in `guardar_datos_elemento()`
5. **No hardcoded flow** — LLM decides, system prompt guides (not Python logic)
6. **Async everywhere** — All I/O operations use `async def`
7. **Mode context updates** — Tools return updates, nodes apply them to `mode_context`
8. **Tool flags explicit** — Tools declare state changes via `_internal_flags`, NOT pattern matching (REFACTOR-001)
9. **Tombstone protocol** — Never use `pop()` alone to clear a `mode_context` key. Always assign `None` after pop so `merge_dicts()` overwrites the checkpoint. See ADR-010.
10. **Tool validation source** — Tools MUST validate/transition from locally-built `updates_for_fsm`, not from a second `_get_mode_context()` call after saving. The ContextVar snapshot is stale after a DB write. See ADR-010.
11. **obtener_estado_expediente** — Queries DB with `selectinload` for authoritative state. `mode_context` is a fallback only (used when DB is unavailable). See ADR-010.
12. **Kickoff phase guard** — `_SUBMODE_STEP_MAP` maps sub-modes to their step numbers. No-tool kickoff turns are validated for step-number mismatch and advancement language. See ADR-010.
13. **review_summary pre-call pattern** — ALWAYS call `obtener_estado_expediente()` deterministically before the LLM loop in `_handle_review()`. This is a pre-call, not a `tool_choice`. Implemented via `**kwargs` (`pre_call_tool_result`, `pre_call_tool_name`) passed to `_run_llm_loop()`. Prevents the LLM from using stale prices from PRESUPUESTO_MODE history. See ADR-010.
14. **Taller domain guard** — The kickoff guard in `expediente_mode.py` has a THIRD layer: semantic domain vocabulary isolation. `_TALLER_DOMAIN_GUARD_SUBMODES = {collect_personal, collect_vehicle}` blocks taller-related vocabulary (taller, certificado, 85€, MSI gestione) in those sub-modes on no-tool kickoff turns. Do NOT add taller vocabulary to `collect_personal`/`collect_vehicle` prompts. See ADR-010.
15. **`expediente_revision.md` price field** — Use `precio_total` exclusively in the review summary. NEVER use `tariff_amount` directly (it is the base tariff without certificate). `precio_certificado` (85€ +IVA) is documented separately for `taller_propio=False` cases. See ADR-010.
16. **PRESUPUESTO_MODE S4 price-authority injection** — After `calcular_tarifa_con_elementos()` succeeds, `presupuesto_mode.py` appends a `role:system` message with the EXACT price (S4 block, ~line 957). This prevents the LLM from using stale prices from prior turns. Never remove this block. The pattern mirrors the review_summary pre-call but is inline in the loop (not via `**kwargs`).

---

## Hybrid LLM Architecture (Recycled)

**3-tier system** for cost optimization:

| Tier | Model                       | Purpose             | Cost |
| ---- | --------------------------- | ------------------- | ---- |
| 1    | Ollama: `qwen2.5:3b`        | Fallback, fast      | $0   |
| 2    | Ollama: `llama3:8b`         | Simple RAG          | $0   |
| 3    | OpenRouter: `deepseek-chat` | Conversation, cloud | ~$0.27/1M tokens |

**Routing**: By `TaskType` (defined in `shared/llm_router.py`)

### Variant Interpretation Rollout

- `agent/services/variant_interpretation_service.py` interpreta respuestas de variantes multi-unidad.
- Flujo: intento local (Tier 1) y escalado a cloud (Tier 3) solo si baja confianza/errores.
- Métricas estructuradas: `variant_interpretation_started`, `variant_interpretation_escalated`, `variant_interpretation_completed`, `variant_interpretation_clarification_needed`.
- Feature flag: `ENABLE_LLM_VARIANT_INTERPRETATION` (en `shared/config.py`).
- Si está en `False`, el servicio devuelve aclaración inmediata y no ejecuta interpretación LLM.
- `seleccionar_variante_por_respuesta` salta la rama LLM y usa matching legacy por keywords.
- Rollback: poner `ENABLE_LLM_VARIANT_INTERPRETATION=false` y reiniciar servicio `agent`.

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

### NEVER Skip Element Data Collection
```python
# ❌ WRONG
confirmar_fotos_elemento()  # → has required fields
→ completar_elemento_actual()  # WRONG! Data not collected

# ✅ CORRECT
confirmar_fotos_elemento()
obtener_campos_elemento()  # Check fields
guardar_datos_elemento(datos)  # Collect
completar_elemento_actual()  # Mark complete
```

### NEVER Ignore Greetings in First Interaction
```python
# ❌ WRONG
User: "Holaaa quiero homologar el subchasis de mi moto"
Bot: "Para darte un presupuesto necesito más información sobre tu vehículo.
      ¿Me podrías decir qué tipo de moto es? También necesitaría saber..."
[Generates long explanatory text WITHOUT calling tools → CORRUPTED TEXT]

# ✅ CORRECT
User: "Holaaa quiero homologar el subchasis de mi moto"
Bot: "¡Hola! Vas a homologar el subchasis de tu moto."
→ identificar_y_resolver_elementos("motos-part", "subchasis")
→ calcular_tarifa_con_elementos(...)
Bot: "El presupuesto es de 350€ +IVA. Esto incluye..."
```

**Key Rules**:
- Greeting + intention → Greet BRIEFLY (≤5 words) + process IMMEDIATELY
- NEVER generate long explanatory text without calling tools
- If user mentions an element → Identify and calculate price RIGHT AWAY
- See [ADR-004](../../docs/decisions/004-fix-presupuesto-corrupted-text.md) for details

### NEVER Assume Tool Result Type Without Parsing

```python
# ❌ WRONG - Assumes result is dict
result = await self._execute_and_log_tool(...)
_apply_tool_flags(mode_context, result, logger)
# BUG: result is JSON STRING, not dict!
# Flags never applied → precio_comunicado stays False

# ✅ CORRECT - Parse explicitly
result = await self._execute_and_log_tool(...)
result_dict = json.loads(result) if isinstance(result, str) else result
_apply_tool_flags(mode_context, result_dict, logger)
# Flags applied correctly → precio_comunicado = True
```

**Why This Matters**:
- `_execute_and_log_tool()` in `base_mode.py` line 315 returns `json.dumps(result)` (STRING)
- Functions expecting dict must parse first
- This bug broke tool-driven state management completely (all flags ignored)
- See [ADR-005 Known Issues](../../docs/decisions/005-tool-driven-state-management.md#known-issues--fixes) for full details

**Pattern to Follow** (defensive programming):
```python
# Always parse tool results before using as dict
data = json.loads(result) if isinstance(result, str) else result

# Always add type guard after parsing
if not isinstance(data, dict):
    logger.warning("unexpected_type", type=type(data).__name__)
    return

# Now safe to use
flags = data.get("_internal_flags", {})
```

### NEVER Use pop() Alone to Clear mode_context Keys (Tombstone Protocol)

`merge_dicts()` does `{**current, **update}`. A key absent from `update` survives from `current` (the Redis checkpoint). `pop()` only removes from the local dict — the checkpoint still has the key, so it resurects on the next turn.

```python
# ❌ WRONG — key resurrects from checkpoint on next turn
updated_context.pop("expediente_transition_marker", None)
updated_context.pop("just_transitioned_from", None)

# ✅ CORRECT — tombstone overwrites the checkpoint value
updated_context.pop("expediente_transition_marker", None)
updated_context["expediente_transition_marker"] = None   # TOMBSTONE
updated_context.pop("just_transitioned_from", None)
updated_context["just_transitioned_from"] = None         # TOMBSTONE
```

**Rule**: Mark every cleanup site with a `# TOMBSTONE` comment. `None` is safe for all callers that use `.get(key)` or `.get(key, default)` — they treat `None` identically to absent.

**See**: `docs/decisions/010-expediente-state-integrity.md`

### NEVER Reread _get_mode_context() After a DB Write in Tools

`_get_mode_context()` returns a ContextVar snapshot captured BEFORE the tool ran. After writing data to DB, calling `_get_mode_context()` again returns stale state (missing the data just saved), causing wrong `missing_fields` and wrong sub-mode transitions.

```python
# ❌ WRONG — stale reread after DB commit
merged_personal = merge_personal_data(existing, incoming)
await _update_fsm_state(case_id, {"personal_data": merged_personal}, session)
case_fsm_state = _get_mode_context()  # ← STALE! Doesn't contain merged_personal
personal_data = case_fsm_state.get("personal_data", {})
is_valid, missing = validate_personal_data(personal_data)

# ✅ CORRECT — use locally-available data for validation
merged_personal = merge_personal_data(existing, incoming)
updates_for_fsm["personal_data"] = merged_personal
await _update_fsm_state(case_id, updates_for_fsm, session)
# Use updates_for_fsm (or its sub-key) for validation — it IS the truth
is_valid, missing = validate_personal_data(
    updates_for_fsm.get("personal_data", case_fsm_state.get("personal_data", {}))
)
```

**Rule**: After `await _update_fsm_state(...)`, use `updates_for_fsm` (or the dict you just built) for any completeness/transition decision. Never call `_get_mode_context()` again.

**See**: `docs/decisions/010-expediente-state-integrity.md`

### NEVER Read Chatwoot Note Fields from `case_fsm_state` in `finalizar_expediente()`

`finalizar_expediente()` builds a private Chatwoot note when a case is submitted. It MUST read `element_codes`, `categoria_slug`, `taller_propio`, and `tariff_amount` from the `Case` ORM row (DB truth), NOT from `case_fsm_state` (stale ContextVar snapshot).

```python
# ❌ WRONG — stale ContextVar snapshot, may be empty or outdated
element_codes = case_fsm_state.get("element_codes", [])
categoria_slug = case_fsm_state.get("category_slug", "N/A")
taller_propio_fin = case_fsm_state.get("taller_propio")
tarifa_raw = case_fsm_state.get("tariff_amount")

# ✅ CORRECT — DB truth via eager-loaded ORM row
result = await session.execute(
    select(Case).options(selectinload(Case.category)).where(Case.id == uuid.UUID(case_id))
)
case = result.scalar_one_or_none()
element_codes = case.element_codes or []
categoria_slug = case.category.slug if case.category else "N/A"
taller_propio_fin = case.taller_propio
tarifa_raw = case.tariff_amount
```

**Why**: `case_fsm_state` is a snapshot captured before the tool ran. Fields like `element_codes` are saved to DB by earlier tools; reading from `case_fsm_state` returns empty/stale values that produce incorrect Chatwoot notes at case finalization.

**See**: `docs/decisions/010-expediente-state-integrity.md` (Follow-up fixes: p0-state-integrity-fixes)

### NEVER Let `tool_validation.py` Silently Skip Validation When `categoria_slug` Is Missing

`SemanticValidator.validate()` validates `element_code` and `tier_id` params against the database. When `categoria_slug` is absent from params/state, it MUST return `(False, [error])` — it MUST NOT silently skip (`continue`) and let the call pass.

```python
# ❌ WRONG — fail-open: missing context causes silent validation skip
if not categoria_slug:
    logger.warning("element_code_validation_skipped_no_category", ...)
    continue  # BUG: element_code passes without any validation!

# ✅ CORRECT — fail-closed: missing context is itself a validation error
if not categoria_slug:
    logger.warning("element_code_validation_skipped_no_category", ...)
    errors.append(f"Cannot validate element_code '{param_value}': categoria_slug is required")
    continue
```

**Why**: A `continue` after warning silently accepts calls with invalid/unknown element codes when the category context is missing. The LLM should receive an explicit error so it can self-correct by providing `categoria_slug`.

**See**: `docs/decisions/010-expediente-state-integrity.md` (Follow-up fixes: p0-state-integrity-fixes)

### `ENABLE_CANONICAL_TRANSITION_ADAPTER` Is Now Safe to Enable

The `expediente_transition_adapter.py` sub-mode names have been corrected to match the canonical names used throughout the codebase. When this flag is enabled, the adapter correctly maps to `collect_workshop` (not `collect_taller`) and `review_summary` (not `review`).

```python
# expediente_constants.py — canonical names (source of truth)
_SUBMODE_STEP_MAP = {
    "collect_element_data": 1,
    "collect_base_docs": 2,
    "collect_personal": 3,
    "collect_vehicle": 4,
    "collect_workshop": 5,   # ← was "collect_taller" in adapter (BUG)
    "review_summary": 6,     # ← was "review" in adapter (BUG)
}
```

**Status**: `ENABLE_CANONICAL_TRANSITION_ADAPTER` defaults to `False`. After p0-state-integrity-fixes, enabling it will no longer cause routing failures.

**See**: `docs/decisions/010-expediente-state-integrity.md` (Follow-up fixes: p0-state-integrity-fixes)

### NEVER Let Kickoff No-Tool Turns Claim a Different Phase

On kickoff turns where no tools were called, the LLM can hallucinate content from a different phase (e.g., "Paso 5/6 - Taller" when in `collect_personal`). The step-mismatch guard catches this.

```python
# The mapping is defined as _SUBMODE_STEP_MAP in expediente_mode.py:
_SUBMODE_STEP_MAP = {
    "collect_element_data": 1,
    "collect_base_docs": 2,
    "collect_personal": 3,
    "collect_vehicle": 4,
    "collect_workshop": 5,
    "review_summary": 6,
}
# Guard fires when:
# 1. No tools called this turn (_is_kickoff_no_tool_turn = True)
# 2. Response contains "Paso X/6" where X != _SUBMODE_STEP_MAP[sub_mode]
#    OR response contains advancement language without tool evidence
# Behavior: strip the hallucinated content and log a warning (not full reject)
```

**See**: `docs/decisions/010-expediente-state-integrity.md`

---

## Differences from v1

| Aspect              | v1 (FSM-based)                | Current (Mode-based)         |
| ------------------- | ----------------------------- | ---------------------------- |
| **Flow control**        | FSM states + transitions      | Modes + intent routing       |
| **Tool availability**   | Phase-based filtering         | Mode-based filtering         |
| **Prompt assembly**     | Core + phase prompts          | Core + mode prompts          |
| **Digression handling** | Not supported                 | Digression manager           |
| **Fallback**            | Global only                   | Per-mode retry policies      |
| **Entry point**         | `graphs/conversation_flow.py` | `graph/conversation_graph.py`|
| **State schema**        | `ConversationState`           | `ConversationState` (updated)|
| **Expediente**          | FSM with 7 phases             | Sub-modes (6 phases)         |

**Migration**: v1 archived to `archive/agent-v1/` (complete snapshot for reference)

---

## Testing & Development

**Start agent**:
```bash
python -m agent.main
```

**Dependencies**:
- Redis (Streams + checkpointer)
- PostgreSQL (state persistence, case data)
- Ollama (local models: qwen2.5:3b, llama3:8b, nomic-embed-text)
- OpenRouter (cloud fallback: deepseek-chat)
- Chatwoot (WhatsApp integration)

**Environment variables**: See `shared/config.py` for complete list (46+ vars)

---

## Further Reading

- `../docs/decisions/` — Architecture Decision Records (ADRs)
- `../skills/msia-agent/` — Detailed agent patterns skill
- `archive/agent-v1/AGENTS.md` — v1 documentation (for reference)

### Auto-invoke Skills

When performing these actions, ALWAYS invoke the corresponding skill FIRST:

| Action | Skill |
|--------|-------|
| Creating/modifying agent tools | `msia-agent` |
| Creating/modifying mode nodes | `msia-agent` |
| Working on LangGraph graphs/nodes | `langgraph` |
| Working on agent conversation flow | `msia-agent` |
| Working on mode-based architecture | `msia-agent` |
| Working on system prompts | `msia-agent` |
| Editing agent system prompts | `msia-prompts` |
| Modifying files in agent/prompts/ | `msia-prompts` |
| Adding rules to prompt modules | `msia-prompts` |
| Working with ConversationState | `msia-agent` |
| Working with tariffs or elements | `msia-tariffs` |
| Writing Python tests | `pytest-async` |
| Writing tests for MSI-a | `msia-test` |
