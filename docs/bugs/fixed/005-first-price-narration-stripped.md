# Bug 005: First-Price Narration Stripped by `no_reprice_post_price` Guard

**Severity**: 🔴 CRITICAL
**Date Fixed**: 2026-04-22
**Status**: Fixed
**Component**: `agent/modes/pre_expediente_mode.py`

---

## Impact

On the first turn where the tariff is computed (variant resolution → `calcular_tarifa_con_elementos` → LLM narrates price + docs), the guard `no_reprice_post_price` (R-5) stripped the price paragraphs. User received only the documentation section — no price, no warnings, no footer.

Repro conversation (conversation_id=1, 2026-04-22 12:03:30):

```
User: "B"  (variant selection for placa solar)
Agent: (intended) "Documentación + Presupuesto 75€ +IVA + CTA"
Agent: (actual)   "Documentación + CTA"   ← price paragraph gone
```

Telemetry:
```
guard_fired guard_name=no_reprice_post_price
  precio_comunicado=True  reprice_allowed_this_turn=False
  stripped_paragraph_count=4  reason=post_price_reprice
```

---

## Root Cause

Ordering bug in `_process_message` (PreExpedienteModeNode):

1. Tool loop finishes → `calcular_tarifa_con_elementos` populated `tarifa_calculada`.
2. Block at `pre_expediente_mode.py:2000-2008` flips `precio_comunicado=False→True` BEFORE the output guard pipeline runs.
3. Guard `no_reprice_post_price` at step 3.5 (~line 2075) reads `precio_comunicado=True` and `reprice_allowed_this_turn=False` (the tool only sets `reprice_allowed_this_turn=True` when `precio_comunicado` was ALREADY True at call time — i.e. on a second-price/reprice turn).
4. Guard interprets the first-price narration as a POST_PRICE reprice and strips 4 paragraphs.

The flag `reprice_allowed_this_turn` was designed for legitimate reprices (adding/removing elements after a price was already communicated). It was never set for the first-price turn because, from the tool's point of view, `precio_comunicado` was still False — correct at tool time, wrong by the time the guard runs.

---

## Solution

In the block that flips `precio_comunicado` False→True after the LLM response, also set `reprice_allowed_this_turn=True` for the current turn. Semantics: "the LLM response I am about to guard IS the first price communication — authorize the narration."

`_reset_reprice_flag_if_set` already tombstones the flag (ADR-010) at turn boundary, so it cannot leak to the next turn.

```python
if (
    _tarifa_called_this_turn
    and updated_context.get("tarifa_calculada")
    and not updated_context.get("precio_comunicado")
):
    updated_context["precio_comunicado"] = True
    sc = result_dict.get("shared_context") or {}
    sc["precio_comunicado"] = True
    # First-price turn: authorize narration through R-5/R-11 guards.
    updated_context["reprice_allowed_this_turn"] = True
    sc["reprice_allowed_this_turn"] = True
    result_dict["shared_context"] = sc
```

---

## Verification

- Unit: `tests/unit/guards/test_guard_no_reprice_post_price.py` — must keep asserting that guard does NOT fire when `reprice_allowed_this_turn=True`.
- Integration: `tests/integration/test_pre_expediente_post_price_flow.py` — first-price turn must preserve price paragraphs.
- Manual: replay "placa solar → B" flow in agent; verify price `75€ +IVA` present in delivered response.

---

## Outstanding Technical Debt

The fix is a targeted patch. The broader flag lifecycle still has holes. Filed as follow-up:

### TD-01: `precio_comunicado` lifecycle is decoupled from real delivery

`precio_comunicado=True` is flipped post-LLM-response based on `tools_called`, not on actual delivery to the user. The guards run AFTER the flip, so any pre-delivery censorship (future guards, channel failures, external post-processing) leaves the flag inconsistent with what the user saw.

Scenarios not covered by the current fix:

1. **Legitimate reprices on element delta** (user adds/removes element post-price). Tool already sets `reprice_allowed_this_turn=True` when `precio_comunicado=True` at call time — this is covered. But if the new tarifa is identical (no-op delta), the guard still allows full re-narration, which may not be desired.
2. **Guard-stripped price that the user never saw** — flag stays True next turn; next legitimate retry blocked by guard. No reconciliation between flag state and delivery truth.
3. **Downgrade reprice** (variant B→A, price goes down). Same path as (1); behavior is the same, but no test asserts it.
4. **Multi-element staged identification across turns** — each addition is a legitimate reprice; relies on the tool set-point being correct at each call. No holistic test.
5. **`cta_policy` guard interaction** — disparó vacío en el repro, pero comparte fase; posible interacción futura con el fix.

### Refactor candidate

Separate two concepts currently collapsed into `precio_comunicado`:

- `tarifa_calculada` — internal (tool-authoritative).
- `precio_entregado_a_usuario` — flipped only AFTER the outbound message pipeline completes (post-guards, post-send). This is what the reprice guard should read.

Proposed shape:
- Move the `precio_comunicado` flip to after `strip_markdown_for_whatsapp` + Chatwoot send in `main.py` (or wherever the delivery contract closes).
- Introduce `precio_comunicado_pending` for the in-flight turn so guards can distinguish "first communication in progress" from "already delivered".
- Reprice guard compares `precio_anterior` vs `precio_actual` on tarifa delta, not on a single boolean flag.

Priority: medium. Current patch resolves the user-facing regression; refactor is structural.

---

## Related

- Guard definition: `agent/modes/pre_expediente_mode.py:625` (`guard_no_reprice_post_price`)
- Flag flip site: `agent/modes/pre_expediente_mode.py:2000`
- Tool set-point (reprice): `agent/tools/element_tools.py:1283`
- Tombstone reset: `agent/modes/pre_expediente_mode.py:426` (`_reset_reprice_flag_if_set`)
- ADR-010: Expediente state integrity (tombstone pattern)
- ADR-005: Tool-driven state management
