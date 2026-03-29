# ADR-011: PRESUPUESTO_MODE Price Integrity via S4 Injection

## Status

Accepted

## Context

`PRESUPUESTO_MODE` generates the final price text freely after `calcular_tarifa_con_elementos()` runs. The LLM can anchor on a price that appears earlier in message history — for example, "410 EUR" from a prior turn — even after a recalculation yields a different price (e.g., 65 EUR). `constraint_service` validates that a tariff tool was called (preventing hallucinated prices from scratch), but does **not** verify that the number the LLM chose to quote matches the tool result.

This means a wrong price can reach the customer silently, without any detection or error log.

**Concrete failure scenario**: A user requests a presupuesto (410 EUR). They then change elements; the agent recalculates and `calcular_tarifa_con_elementos()` returns 65 EUR. The prior "410 EUR" message is still in the LLM conversation window. The LLM, guided only by the system prompt, generates a response quoting "410 EUR" instead of 65 EUR. The `constraint_service` check passes because a tool was called this turn.

## Decision

Two-part fix:

### Fix A — S4 price-authority injection (`presupuesto_mode.py`)

After the tool result for `calcular_tarifa_con_elementos()` is appended to `llm_messages`, and before the next LLM pass that generates the user-facing response, inject a deterministic `role: "system"` message ("S4 block") containing the exact `datos["price"]` from the tool result:

```python
{
    "role": "system",
    "content": (
        f"[SISTEMA]: PRECIO AUTORITATIVO de este cálculo: "
        f"{_s4_price} EUR +IVA. "
        f"Usa EXACTAMENTE este número. "
        f"Ignora precios de turnos anteriores del historial."
    ),
}
```

The block fires only when:
- `tool_name == "calcular_tarifa_con_elementos"`
- `result_dict.get("success") is not False`
- `datos.get("price") is not None`

The S4 block is placed after the S3 category-not-found injection block (line ~957) and follows the same `[SISTEMA]:` + `role: "system"` pattern already present in `presupuesto_mode.py`.

### Fix B — Prompt hardening (`agent/prompts/core/07_pricing_rules.md`)

Add explicit reinforcement rules to the pricing rules prompt module:

```
- Si recalculas, el resultado MAS RECIENTE es el unico valido — ignora precios de turnos anteriores
- Si ves "[SISTEMA]: PRECIO AUTORITATIVO", usa EXACTAMENTE ese numero
```

This creates a prompt-level defence that works alongside the code-level injection. Both layers are required: the prompt provides general-purpose guidance, the injected system message provides the exact authoritative number for the current turn.

## Consequences

**Positive**:
- Price shown to the user is always anchored to the most recent `calcular_tarifa_con_elementos()` result, regardless of what is in conversation history.
- Both defences are additive and low-risk: the S4 injection fires only on success, the prompt change adds ~23 tokens.
- Follows the existing pattern of deterministic pre-call/mid-loop system message injection already used for review_summary (via `**kwargs`) and S3 category-not-found injection.
- Structured log `price_authority_injected` makes the injection observable and debuggable.

**Negative / Trade-offs**:
- S4 adds one additional system message per tariff call, increasing context token usage slightly (bounded by the size of the injected string, ~30-40 tokens).
- Tests cover injection logic (unit) but not end-to-end LLM response fidelity to the injected number (no integration test with real LLM).

## Alternatives Considered

| Alternative | Why Not Chosen |
|-------------|----------------|
| **Post-response numeric validation** — Parse the LLM response after generation and reject/retry if the quoted number differs from `datos.price`. | Fragile: requires reliable number extraction from natural-language Spanish text (e.g., "65€", "65 euros", "65,00 EUR", "sesenta y cinco euros"). Adds latency on every tariff turn. Also reactive — does not prevent the problem, only catches it. |
| **Full deterministic render bypass** — Replace the LLM-generated price text entirely with a Python-rendered string. | Too invasive: would require changes to the response assembly pipeline, mode prompt structure, and constraint_service checks. Deferred unless S4 injection proves insufficient. |
| **Invalidation message only (without exact price)** — Inject "the previous price is no longer valid" without stating the new price. | Probabilistic: the LLM still has to infer the correct price from the tool result message. Does not directly anchor the number. |
| **`constraint_service` numeric comparison** — Extend constraint validation to compare the quoted price with `tarifa_calculada`. | Valid secondary defence but requires string-to-number parsing of the LLM response. Does not prevent the wrong price from being sent if detection fails. |

## Implementation

- **File changed**: `agent/modes/presupuesto_mode.py` — S4 block at lines 957–993
- **File changed**: `agent/prompts/core/07_pricing_rules.md` — 2 lines added (lines 8–9)
- **Tests added**: `tests/unit/test_presupuesto_price_integrity.py` — 6 unit tests (all pass)
- **Verify status**: PASS — 6/6 tests pass; static code verification confirms S4 block and prompt rule

## Related

- `docs/decisions/005-tool-driven-state-management.md` — Tool flag contract (`_internal_flags`)
- `docs/decisions/010-expediente-state-integrity.md` — review_summary pre-call pattern (parallel pattern)
- `agent/AGENTS.md` — Critical Rule 16
