# Agent Component Guidelines

MSI-a conversational agent built with LangGraph. Mode-based flow with a compiled subgraph for EXPEDIENTE.

> For deep patterns, invoke the skill: `msia-agent`. For prompt authoring, use `msia-prompts`.

---

## Directory Structure

See `AGENTS.md` in this directory for the full annotated tree. Top-level layout:

```
agent/
├── main.py                  # Redis Streams consumer (entry point)
├── graph/                   # Top-level StateGraph + expediente_subgraph
├── router/                  # Intent router, digression, transition whitelist
├── modes/                   # BaseModeNode + concrete modes + tool_loop subgraph + post_tool_hooks
│   └── submodos/            # EXPEDIENTE sub-mode handlers (6)
├── fallback/                # Per-mode retry policies
├── state/                   # ConversationState + reducers + checkpointer
├── tools/                   # 29 @tool decorators with Pydantic args_schema
├── services/                # Business logic (tariffs, elements, cases, escalation)
├── prompts/                 # core.md (XML tags) + modes/*.md + loader.py
└── utils/                   # Errors, validation, feature flags, tool helpers
```

---

## Architecture (current)

### 2 modes + escalation

| Mode | Traffic | Notes |
|------|---------|-------|
| `PRE_EXPEDIENTE_MODE` | ~90% | 3 phases resolved from state: `DISCOVERY` (no elements) → `PRICING` (elements identified) → `POST_PRICE` (price communicated) |
| `EXPEDIENTE_MODE` | Complex | Compiled subgraph with 6 sub-modes: `collect_element_data` → `collect_base_docs` → `collect_personal` → `collect_vehicle` → `collect_workshop` → `review_summary` |
| `ESCALATION` | Terminal | Deterministic 6-step flow via `escalation_service.py` (Chatwoot + DB) |

### Tool loop subgraph

All mode nodes share `build_mode_tool_loop()` (`modes/tool_loop.py`):

```
llm_node → tools_or_end ─┬─► custom tool_node ─► post_tool_node ─► llm_node
                          └─► END
```

- **Custom tool_node** (not `langgraph.prebuilt.ToolNode`) — adds per-turn dedup, `execute_and_log_tool()` (timing/classification/logging), and `_state_update` extraction. See AD-1 at `modes/tool_loop.py`.
- **post_tool_node** — single place where domain state gets merged into `mode_context` (`post_tool_hooks.py`). No parallel accumulators.

### State schema

`ConversationState` (`state/conversation_state.py`, 479 lines) uses `Annotated[T, reducer]`:
- `merge_dicts` for nested data (`mode_context`, `draft_contexts`, `user_profile`)
- `preserve_if_none` for simple values (`current_mode`, flags, timestamps)
- `append_unique_list` for `mode_history`
- `add_messages` for `messages` (LangGraph standard)

`ModeContextData` is a `TypedDict(total=False)` with ~30 keys across PRE_EXPEDIENTE and EXPEDIENTE. Mitigated by `draft_contexts` when switching modes.

---

## Critical Rules (BUSINESS CRITICAL)

### Flow rules

1. **Price before images** — `enviar_imagenes_ejemplo` should only fire after the LLM has communicated the price. Enforced via prompts (`core.md:<pricing>`, `pre_expediente_pricing.md:<images_before_price>`). No code gate today.
2. **Never re-identify** — when `pending_variants` exist, use `seleccionar_variante_por_respuesta`. Calling `identificar_y_resolver_elementos` triggers an infinite loop. Enforced via prompt `core.md:<principles><anti-loop>`.
3. **Skip validation after ID** — always `skip_validation=True` in `calcular_tarifa_con_elementos()` after identification.
4. **Exact field_key** — `guardar_datos_elemento(datos=...)` must use keys from `obtener_campos_elemento()`. No abbreviations, no accents removed, no invented keys.
5. **finalizar_expediente is the gatekeeper** — never declare "expediente enviado" unless it returns `success: true`.

### Code rules

6. **Tool-driven state** — tools declare state changes via `_state_update` dict. `post_tool_node` merges into `mode_context`. Never mutate state from inside a tool. ADR-005.
7. **Mode transitions** — return `{"_state_update": {"_transition_to": "MODE_NAME"}}` from a tool. The conditional edge in `conversation_graph.py` consumes this.
8. **No direct state mutation in nodes** — return state-update dicts; let reducers merge.
9. **Parse tool results** — `execute_and_log_tool()` returns `json.dumps(result)`. Callers must `json.loads()` before treating as dict.
10. **Tombstone protocol** — to clear a `mode_context` key, assign `None` after `pop()`. Otherwise `merge_dicts` resurrects it from the Redis checkpoint. See ADR-010.
11. **No stale ContextVar reads** — after `await _update_fsm_state(...)`, use the dict you just wrote (`updates_for_fsm`), NOT `_get_mode_context()` again. The snapshot is stale after a DB write. See ADR-010.
12. **finalizar_expediente reads DB truth** — read `element_codes`, `categoria_slug`, `taller_propio`, `tariff_amount` from the `Case` ORM row (`selectinload`), NOT from `case_fsm_state`. See ADR-010.

### Python rules

13. **Async everywhere** — `async def` for all I/O (DB, Redis, HTTP, files).
14. **Type hints required** — complete annotations on all functions.
15. **Pydantic for tool schemas** — every `@tool` has `args_schema=<PydanticModel>` (schemas in `tools/schemas.py`).
16. **Structlog JSON** — never `print()`.
17. **Pydantic Settings** — `get_settings()` from `shared/config.py`. Never `os.getenv()`.

---

## Key Patterns

### Mode node delegation

Concrete modes do NOT hand-roll the LLM loop — they delegate to `build_mode_tool_loop()`:

```python
class MyModeNode(BaseModeNode):
    async def _process_message(self, state):
        config = ModeLoopConfig(
            mode="MY_MODE",
            prompt_assembler=self._assemble_prompt,
            get_tools=lambda s: get_tools_for_phase(phase, ALL_TOOLS),
            post_tool_hook=my_post_tool_hook,
        )
        subgraph = build_mode_tool_loop(config)
        return await subgraph.ainvoke(state)
```

### Tool with state update

```python
@tool(args_schema=CalcularTarifaInput)
async def calcular_tarifa_con_elementos(...) -> dict:
    # business logic
    return {
        "success": True,
        "texto": "...",
        "datos": {...},
        "_state_update": {
            "tarifa_calculada": {...},
        },
    }
```

### Mode transition via tool

```python
# transition_tools.py
@tool(args_schema=ConfirmarPresupuestoInput)
async def confirmar_presupuesto(...) -> dict:
    # precondition check (precio_comunicado, tarifa_calculada)
    return {
        "success": True,
        "message": "...",
        "_state_update": {
            "_transition_to": "EXPEDIENTE_MODE",
            "expediente_kickoff_pending": True,
        },
    }
```

---

## Anti-patterns (see AGENTS.md for full list)

- ❌ Generate long explanatory text without calling tools — causes "corrupted text" regression (ADR-004)
- ❌ Re-identify after a variant question — use `seleccionar_variante_por_respuesta`
- ❌ Forget the price — always communicate before sending images
- ❌ Skip element data — `confirmar_fotos_elemento` → `obtener_campos_elemento` → `guardar_datos_elemento` → `completar_elemento_actual`
- ❌ Invent `field_key` — always use exact keys from `obtener_campos_elemento()`
- ❌ `pop()` a `mode_context` key without tombstone — it resurrects from the checkpoint
- ❌ Reread `_get_mode_context()` after a DB write — it's stale
- ❌ Read finalization fields from `case_fsm_state` in `finalizar_expediente()` — use DB truth
- ❌ Skip semantic validation silently when `categoria_slug` is missing — fail-closed, not fail-open

---

## Auto-invoke Skills

| Action | Skill |
|--------|-------|
| Creating/modifying agent tools | `msia-agent` |
| Creating/modifying mode nodes or graph nodes | `msia-agent` |
| Working on system prompts (`prompts/`) | `msia-prompts` |
| Working on LangGraph `StateGraph`, reducers, checkpointer | `langgraph` + `langgraph-persistence` |
| Working with `ConversationState` | `msia-agent` |
| Tariffs or elements | `msia-tariffs` |
| Writing tests | `pytest-async`, `msia-test` |
