# Agent Component Guidelines

This directory contains the MSI-a conversational agent built with LangGraph.

> **Architecture**: Mode-based conversation flow with intent routing, digression management, and per-mode fallback handling. EXPEDIENTE runs as a compiled subgraph with 6 sub-modes. All modes share a custom `tool_node` (dedup + logging + `_state_update` extraction) driven by `build_mode_tool_loop()`.

---

## Directory Structure

```
agent/
├── main.py                      # Entry point (Redis Streams consumer)
├── state/
│   ├── conversation_state.py    # ConversationState TypedDict + reducers (merge_dicts, preserve_if_none)
│   ├── context_models.py        # Typed context models
│   ├── mode_context_keys.py     # Enumeration of valid mode_context keys
│   ├── checkpointer.py          # Redis checkpointer (LangGraph persistence)
│   ├── helpers.py               # State utilities
│   └── mutation_config.py       # Reducer strategy configuration
├── router/
│   ├── intent_router.py         # Intent classification (keyword + LLM, manual JSON parse)
│   ├── digression_manager.py    # Off-topic detection in focused modes
│   └── mode_transitions.py      # Mode transition rules (whitelist)
├── fallback/
│   └── fallback_handler.py      # Per-mode retry policies and fallback actions
├── modes/
│   ├── base_mode.py             # BaseModeNode (retry state, fallback, telemetry, tool classification)
│   ├── pre_expediente_mode.py   # PRE_EXPEDIENTE_MODE — 3 phases (discovery/pricing/post_price) via state
│   ├── presupuesto_mode.py      # Backward-compat alias → pre_expediente_mode
│   ├── expediente_mode.py       # EXPEDIENTE_MODE — subgraph dispatch for 6 sub-modes
│   ├── expediente_nodes.py      # Factory `_build_expediente_node()` for each sub-mode
│   ├── expediente_state.py      # ExpedienteState (subgraph-local, no reducers)
│   ├── tool_loop.py             # `build_mode_tool_loop()` — custom tool_node + llm_node + post_tool_node subgraph
│   ├── tool_loop_state.py       # ToolLoopState schema (inside mode_tool_loop subgraph)
│   ├── tool_executor.py         # `execute_and_log_tool()` — dedup, timing, classification, logging
│   ├── post_tool_hooks.py       # `pre_expediente_post_tool_hook()` + `expediente_post_tool_hook()`
│   └── submodos/                # Sub-mode handlers (collect_element_data, base_docs, personal, vehicle, workshop, review_summary)
├── graph/
│   ├── conversation_graph.py    # Top-level StateGraph (preprocess → router → modes → escalation)
│   ├── expediente_subgraph.py   # Compiled subgraph for EXPEDIENTE with 7 nodes
│   ├── summarize_node.py        # Conversation summary reducer
│   └── user_profile_store.py    # User profile persistence
├── prompts/
│   ├── loader.py                # Dynamic prompt assembly: core.md + mode file + mode_context
│   ├── core.md                  # Single core file with semantic XML tags (identity, execution_model, security, principles, voice, format, pricing, photos_model, escalation)
│   ├── modes/                   # Mode/sub-mode prompts
│   │   ├── pre_expediente_discovery.md
│   │   ├── pre_expediente_pricing.md
│   │   ├── pre_expediente_post_price.md
│   │   ├── expediente_elements.md
│   │   ├── expediente_base_docs.md
│   │   ├── expediente_personal.md
│   │   ├── expediente_vehicle.md
│   │   ├── expediente_workshop.md
│   │   ├── expediente_review.md
│   │   └── session_recovery.md
│   ├── calculator_base.py       # Admin-only preview prompt template (used by api/routes/tariffs.py)
│   └── prompt_lint.py           # Prompt linting utility
├── tools/                       # 29 LangChain tools (all @tool with Pydantic args_schema)
│   ├── element_tools.py         # Element identification, variant resolution, tariff (5 tools)
│   ├── tarifa_tools.py          # Tariff helpers (3 tools)
│   ├── case_tools.py            # Case/expediente management (10 tools)
│   ├── element_data_tools.py    # Element data collection (7 tools)
│   ├── image_tools.py           # Example image sending (1 tool)
│   ├── vehicle_tools.py         # Vehicle classification (1 tool)
│   ├── shared_tools.py          # Universal tools — escalar_a_humano (1 tool)
│   ├── transition_tools.py      # confirmar_presupuesto (1 tool, signals mode transition via _state_update._transition_to)
│   ├── schemas.py               # Pydantic args_schema per tool
│   ├── types.py                 # ToolResult types, _state_update/_internal_flags contract
│   ├── tool_manager.py          # Contextual tool filtering per FSM phase / mode
│   └── draft_quote_service.py   # Draft quote persistence
├── services/                    # Business logic
│   ├── tarifa_service.py        # Tariff calculation with Redis caching
│   ├── element_service.py       # Element matching (NLP + fuzzy + variants)
│   ├── element_state_service.py # Element collection state (v2 COLLECTION_CONTEXT)
│   ├── element_data_service.py  # Element data persistence
│   ├── element_required_fields_service.py  # Conditional field management
│   ├── variant_interpretation_service.py   # Multi-unit variant interpretation
│   ├── case_service.py          # Case lifecycle
│   ├── case_image_batch_service.py         # Photo batch tracking
│   ├── case_lifecycle_worker.py            # Background lifecycle worker
│   ├── case_helpers.py          # Case helpers
│   ├── collection_mode.py       # Sequential/Batch/Hybrid collection strategy
│   ├── constraint_service.py    # Response validation (anti-hallucination, regex-driven)
│   ├── entity_extraction_service.py        # Named entity extraction
│   ├── escalation_service.py    # 6-step escalation flow (Chatwoot + DB)
│   ├── expediente_constants.py  # CERT_SUPPLEMENT_EUR, _SUBMODE_STEP_MAP
│   ├── expediente_guards.py     # Kickoff / phase guards
│   ├── expediente_helpers.py    # Expediente helpers
│   ├── expediente_init.py       # Case initialization
│   ├── expediente_onboarding.py # Onboarding copy
│   ├── image_handling.py        # Image intake
│   ├── image_service.py         # Image dispatch
│   ├── intent_classifier.py     # Intent classification service
│   ├── tool_logging_service.py  # Persistent tool call logging
│   ├── token_tracking.py        # Token usage tracking
│   ├── turn_telemetry.py        # Per-turn telemetry
│   ├── vehicle_classification_service.py   # Vehicle classification
│   └── prompt_service.py        # Admin-only preview service (used by api/routes/tariffs.py)
└── utils/
    ├── validation.py            # Input validation (whitelist-based)
    ├── errors.py                # Error types + classification
    ├── feature_flags.py         # Runtime feature flags
    ├── text_utils.py            # Text normalization
    ├── tool_context_contract.py # Tool context contract
    ├── tool_decorators.py       # Tool decorators (handle_tool_errors)
    ├── tool_helpers.py          # Tool helpers
    ├── tool_validation.py       # Tool argument semantic validation
    ├── validation_metrics.py    # Validation metrics
    ├── expediente_transition_adapter.py    # FSM ↔ sub-mode name canonicalization
    ├── expediente_types.py      # Expediente type aliases
    └── expediente_validators.py # Expediente field validators
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
│  preprocess  │ (message extraction, first-interaction flag, recovery detection)
└──────┬───────┘
       │
┌──────▼───────┐
│    router    │ (intent classification OR digression detection)
└──────┬───────┘
       │ (conditional edge: current_mode dispatch)
       │
       ├────────────────────────┬──────────────┐
       ▼                        ▼              ▼
┌─────────────────────┐  ┌─────────────────┐  ┌──────────────┐
│ pre_expediente_mode │  │ expediente_mode │  │  escalation  │───► END
│  (3 phases via      │  │  (subgraph,     │  └──────────────┘
│   state:            │  │   6 sub-modes)  │
│   DISCOVERY /       │  └────┬────────────┘
│   PRICING /         │       │
│   POST_PRICE)       │       │ transition via _state_update._transition_to
└──────────┬──────────┘       │
           │                   │
           └─── confirmar_presupuesto() ──► EXPEDIENTE_MODE
```

Every mode node internally wraps `build_mode_tool_loop()` which produces a subgraph:

```
llm_node → tools_or_end (conditional) ─┬─► custom tool_node ─► post_tool_node ─► llm_node (loop)
                                        └─► END
```

- **llm_node**: Calls the LLM with filtered tools (`get_tools_for_phase()`)
- **tools_or_end**: Conditional edge — tool_calls present → tool_node, else → END
- **custom tool_node**: `execute_and_log_tool()` with per-turn dedup, timing, classification, logging
- **post_tool_node**: `pre_expediente_post_tool_hook` or `expediente_post_tool_hook` — extracts `_state_update` and merges into `mode_context`

### Mode Architecture

Each mode is a self-contained `BaseModeNode` subclass with:
- **Dedicated prompt file** (`core.md` + `modes/<mode>.md`, assembled at runtime)
- **Filtered tools** (`tool_manager.get_tools_for_phase()` — only relevant tools per phase/sub-mode)
- **LLM-driven flow** via `build_mode_tool_loop()` subgraph
- **Transitions** via `_state_update._transition_to` from tool results

| Mode             | Traffic  | Purpose                                                              | Prompts                                                                          |
| ---------------- | -------- | -------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| PRE_EXPEDIENTE   | ~90%     | Discovery, pricing, example images. 3 phases resolved from state.    | `pre_expediente_discovery.md`, `pre_expediente_pricing.md`, `pre_expediente_post_price.md` |
| EXPEDIENTE       | Complex  | Formal case collection (6 sub-modes via compiled subgraph)           | `expediente_elements.md`, `expediente_base_docs.md`, `expediente_personal.md`, `expediente_vehicle.md`, `expediente_workshop.md`, `expediente_review.md` |
| ESCALATION       | Terminal | Human handoff (no LLM loop, deterministic escalation)                | —                                                                                |

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

**Purpose**: Per-mode retry policies and progressive reprompts. Integrated into `BaseModeNode.process()` via retry-state (consecutive_errors counter). On limit exceeded → escalation.

**Progressive reprompts**: Each retry incrementally adds more context/guidance to the LLM input.

---

### 4. Mode Nodes (`modes/*.py`)

**BaseModeNode** (`base_mode.py`, ~1,200 lines):
- Abstract base — concrete modes implement `_process_message(state)`
- Orthogonal concerns: fallback handling, retry state, telemetry envelope, tool result classification, turn timeout defense (`AGENT_TURN_TIMEOUT_SECONDS`), state update validation
- Shared pattern: all concrete modes extend this

**Concrete modes**:
- **PreExpedienteModeNode** (`pre_expediente_mode.py`, ~1,000 lines): Delegates to `build_mode_tool_loop()`. Applies dynamic tool filtering (variant / images / confirmar / calcular gates) based on state flags.
- **ExpedienteModeNode** (`expediente_mode.py`, ~1,370 lines): Coordinator that dispatches to the compiled `expediente_subgraph`. Each sub-mode node (built via `_build_expediente_node()` factory in `expediente_nodes.py`) internally calls `build_mode_tool_loop()`.

**Tool loop subgraph** (`tool_loop.py`, ~670 lines): Custom tool_node (NOT `langgraph.prebuilt.ToolNode`) because it needs per-turn dedup guard, `execute_and_log_tool()` for timing/classification/logging, and `_state_update` extraction. See AD-1 at the top of `tool_loop.py`.

---

### 5. Dynamic Prompts (`prompts/`)

**Structure**:
```
core.md (XML tags)  +  modes/<mode>.md  +  mode_context (dynamic)
```

**Core** (`core.md`, single file with semantic tags):
- `<identity>`, `<execution_model>`, `<security>`, `<principles>`, `<voice>`, `<format>`, `<pricing>`, `<photos_model>`, `<escalation>`

**Mode files** (`modes/*.md`): One prompt per resolved mode key. `loader._resolve_mode_key()` picks the right file based on `current_mode`, `expediente_sub_mode`, and mode_context flags (e.g., `precio_comunicado` → `pre_expediente_post_price.md`).

**Runtime substitution**: `{cert_supplement_eur}` gets replaced with `CERT_SUPPLEMENT_EUR` from `services/expediente_constants.py` at load time.

---

### 6. Tools

**29 tools total**, all decorated with `@tool(args_schema=<PydanticModel>)` (schemas in `tools/schemas.py`). Tools declare state changes via `_state_update` (canonical channel, ADR-005):

| Category           | File                        | Tools                                                                                                          |
| ------------------ | --------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Element            | `element_tools.py`          | `identificar_y_resolver_elementos`, `seleccionar_variante_por_respuesta`, `calcular_tarifa_con_elementos`, `obtener_documentacion_elemento`, `listar_elementos` |
| Tariff             | `tarifa_tools.py`           | `listar_categorias`, `listar_tarifas`, `obtener_servicios_adicionales`                                          |
| Case               | `case_tools.py`             | `iniciar_expediente`, `actualizar_datos_personales`, `actualizar_datos_vehiculo`, `actualizar_datos_taller`, `obtener_estado_expediente`, `finalizar_expediente`, `editar_expediente`, `cancelar_expediente`, `consulta_durante_expediente`, `reactivar_expediente_abandonado` |
| Element Data       | `element_data_tools.py`     | `obtener_campos_elemento`, `confirmar_fotos_elemento`, `guardar_datos_elemento`, `completar_elemento_actual`, `obtener_progreso_elementos`, `reenviar_imagenes_elemento`, `confirmar_documentacion_base` |
| Image              | `image_tools.py`            | `enviar_imagenes_ejemplo`                                                                                      |
| Vehicle            | `vehicle_tools.py`          | `identificar_tipo_vehiculo`                                                                                    |
| Transition         | `transition_tools.py`       | `confirmar_presupuesto` (gated — only available when `precio_comunicado=True` and `tarifa_calculada` exists)   |
| Shared             | `shared_tools.py`           | `escalar_a_humano`                                                                                             |

**Tool filtering**: `tool_manager.get_tools_for_phase()` returns only relevant tools per FSM phase / mode / sub-mode, reducing token cost from ~4,000 → ~750–1,800 per LLM call.

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

Concrete mode nodes delegate to `build_mode_tool_loop()` — they do NOT hand-roll the LLM loop.

```python
class MyModeNode(BaseModeNode):
    def __init__(self):
        super().__init__("MY_MODE")

    async def _process_message(self, state):
        config = ModeLoopConfig(
            mode="MY_MODE",
            prompt_assembler=self._assemble_prompt,
            get_tools=lambda s: get_tools_for_phase(phase, ALL_TOOLS),
            post_tool_hook=my_post_tool_hook,  # merges _state_update into mode_context
        )
        subgraph = build_mode_tool_loop(config)
        return await subgraph.ainvoke(state)
```

### Tool Return Contract (`_state_update`)

Tools declare state changes via `_state_update` (canonical channel, ADR-005). The `post_tool_node` extracts and merges into parent `mode_context`. NEVER mutate state from inside a tool.

```python
# In a tool (e.g., calcular_tarifa_con_elementos)
return {
    "success": True,
    "precio_final": 410.0,
    "elementos": ["ESCAPE"],
    "_state_update": {
        "price_authority_confirmed": True,    # State change declared
    },
}
```

The `post_tool_node` (in `post_tool_hooks.py`) is the SINGLE place for domain state merging (price authority, variant detection, mode transitions). Do not add accumulators elsewhere.

### Sub-mode and Mode Transitions

Transitions are signaled from tools via `_state_update`:

```python
# transition_tools.py — confirmar_presupuesto
return {
    "success": True,
    "message": "El usuario ha confirmado el presupuesto.",
    "resumen": {...},
    "_state_update": {
        "_transition_to": "EXPEDIENTE_MODE",
    },
}
```

The conditional edge in `conversation_graph.py` inspects `_transition_to` and routes to the target mode node. This is the only mechanism for cross-mode transitions — no direct state mutation from mode nodes.

**Sub-mode transitions within EXPEDIENTE** work the same way: tools (e.g., `completar_elemento_actual`) return `_state_update.expediente_sub_mode` which the `post_tool_hook` merges into `mode_context`.

**See**: `docs/decisions/005-tool-driven-state-management.md` for full contract.

---

## Critical Rules

1. **NEVER re-identify after variant question** — Use `seleccionar_variante_por_respuesta()`, not `identificar_y_resolver_elementos()`
2. **PRICE BEFORE IMAGES** — `enviar_imagenes_ejemplo` blocks if price not mentioned first
3. **Skip validation after ID** — Always use `skip_validation=True` in `calcular_tarifa_con_elementos()` after identification
4. **Exact field_key** — Use exact `field_key` from `obtener_campos_elemento()` in `guardar_datos_elemento()`
5. **No hardcoded flow** — LLM decides, system prompt guides (not Python logic)
6. **Async everywhere** — All I/O operations use `async def`
7. **Mode context updates** — Tools return updates, nodes apply them to `mode_context`
8. **Tool-driven state** — Tools declare state changes via `_state_update`, NOT pattern matching. Extracted by `post_tool_node` (ADR-005)
9. **Tombstone protocol** — Never use `pop()` alone to clear a `mode_context` key. Always assign `None` after pop so `merge_dicts()` overwrites the checkpoint. See ADR-010.
10. **Tool validation source** — Tools MUST validate/transition from locally-built `updates_for_fsm`, not from a second `_get_mode_context()` call after saving. The ContextVar snapshot is stale after a DB write. See ADR-010.
11. **obtener_estado_expediente** — Queries DB with `selectinload` for authoritative state. `mode_context` is a fallback only (used when DB is unavailable). See ADR-010.
12. **Kickoff phase guard** — `_SUBMODE_STEP_MAP` maps sub-modes to their step numbers. No-tool kickoff turns are validated for step-number mismatch and advancement language. See ADR-010.
13. **review_summary pre-call pattern** — ALWAYS call `obtener_estado_expediente()` deterministically before the LLM loop in `_handle_review()`. This is a pre-call, not a `tool_choice`. Implemented via `**kwargs` (`pre_call_tool_result`, `pre_call_tool_name`) passed to `_run_llm_loop()`. Prevents the LLM from using stale prices from PRESUPUESTO_MODE history. See ADR-010.
14. **Taller domain guard** — The kickoff guard in `expediente_mode.py` has a THIRD layer: semantic domain vocabulary isolation. Sub-modes `collect_personal` and `collect_vehicle` block taller-related vocabulary (taller, certificado, 85€, MSI gestione) on no-tool kickoff turns. Do NOT add taller vocabulary to `collect_personal`/`collect_vehicle` prompts. See ADR-010.
15. **`expediente_revision.md` price field** — Use `precio_total` exclusively in the review summary. NEVER use `tariff_amount` directly (it is the base tariff without certificate). `precio_certificado` (85€ +IVA) is documented separately for `taller_propio=False` cases. See ADR-010.
16. **PRESUPUESTO_MODE S4 price-authority injection** — After `calcular_tarifa_con_elementos()` succeeds, `presupuesto_mode.py` appends a `role:system` message with the EXACT price (S4 block, ~line 957). This prevents the LLM from using stale prices from prior turns. Never remove this block. The pattern mirrors the review_summary pre-call but is inline in the loop (not via `**kwargs`).

---

## Hybrid LLM Architecture

Routed via `TaskType` enum in `shared/llm_router.py`. See that module for current tier mapping, model IDs, and fallback chain.

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

Tool results come back from `execute_and_log_tool()` as a serialized string (via `json.dumps`). Callers must parse before treating as dict.

```python
# ❌ WRONG - Assumes result is dict
result = await execute_and_log_tool(...)
updates = result.get("_state_update", {})   # AttributeError — result is str

# ✅ CORRECT - Parse explicitly
result = await execute_and_log_tool(...)
data = json.loads(result) if isinstance(result, str) else result
if not isinstance(data, dict):
    logger.warning("unexpected_tool_result_type", type=type(data).__name__)
    return
updates = data.get("_state_update", {})
```

**Why This Matters**: `tool_executor.execute_and_log_tool()` returns `json.dumps(result)`. Anything downstream expecting a dict must parse first.

**See**: `docs/decisions/005-tool-driven-state-management.md`

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

## Testing & Development

**Start agent**:
```bash
python -m agent.main
```

**Dependencies**:
- Redis (Streams + LangGraph checkpointer)
- PostgreSQL (case persistence, tool call logs, escalations)
- Ollama (local models for classification/extraction)
- OpenRouter (cloud LLM for conversation)
- Chatwoot (WhatsApp integration)

**Environment variables**: See `shared/config.py` for complete list (46+ vars)

---

## Further Reading

- `../docs/decisions/` — Architecture Decision Records (ADRs)
- `../skills/msia-agent/` — Detailed agent patterns skill

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
