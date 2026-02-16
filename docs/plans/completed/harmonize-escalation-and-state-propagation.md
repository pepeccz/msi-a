# Plan: Harmonize Escalation Paths & State Propagation

**Date**: 2026-02-15
**Status**: PROPOSED
**Priority**: CRITICAL + HIGH (mixed — 2 broken paths, 4 improvements)
**Predecessor**: `fix-escalation-and-expediente-stubs.md` (Phase 1-2 done)

---

## Executive Summary

Deep audit of the agent after Phase 1-2 fixes revealed **2 critical gaps** where escalation is promised to the user but never reaches Chatwoot, **1 runtime error** being silently swallowed, and **3 hygiene improvements** to prevent future regressions. All changes funnel through the existing `escalation_service.perform_escalation()`.

---

## Changes Overview

| #  | Priority   | Description                                              | Files                        | Risk  |
|----|------------|----------------------------------------------------------|------------------------------|-------|
| P1 | 🔴 CRITICAL | Validation max-retries escalation doesn't reach Chatwoot | `base_mode.py`               | LOW   |
| P2 | 🔴 CRITICAL | `_escalate_image_receipt_issue` crashes silently          | `element_data_tools.py`      | LOW   |
| P3 | 🟡 HIGH     | Rewrite legacy `escalar_a_humano` as wrapper              | `tarifa_tools.py`            | LOW   |
| P4 | 🟡 HIGH     | Fix `__init__.py` to import from `shared_tools`            | `__init__.py`                | LOW   |
| P5 | 🟡 HIGH     | `finalizar_expediente` → Chatwoot notification           | `case_tools.py`              | LOW   |
| P6 | 🟢 MEDIUM   | Unify digression_manager keys with CONTEXT_PRESERVE_RULES | `digression_manager.py`     | LOW   |

---

## P1: Validation Max-Retries Escalation (CRITICAL)

### Problem

When LLM tool validation fails repeatedly (2-3 times), all 3 modes return:
```python
return {
    "current_mode": "ESCALATION",
    "escalation_triggered": True,
    ...
}
```

This return exits `_process_message()` **successfully** (line 90 in `base_mode.py`). The check at line 125 (`if error_result.get("escalation_triggered")`) only runs in the `except` path. So `escalation_triggered: True` is NEVER acted upon.

The `escalation_node` would fire on the **next** user message — but after receiving "Te voy a conectar con un especialista", the user may never send another message.

### Fix

Add an `escalation_triggered` check in the **success path** of `base_mode.process()`, between lines 117-118.

### File: `agent/modes/base_mode.py`

**Current** (lines 107-118):
```python
        # Merge retry update into result
        result["retry_state"] = updated_retry
        result["last_node"] = self.mode_name
        result["updated_at"] = now
        result["last_activity_at"] = now

        # Persist conversation history to LangGraph checkpoint (Bug A fix)
        result["messages"] = self._build_turn_messages(
            message, result.get("ai_response", ""), now,
        )

        return result
```

**New** (insert between retry update and messages):
```python
        # Merge retry update into result
        result["retry_state"] = updated_retry
        result["last_node"] = self.mode_name
        result["updated_at"] = now
        result["last_activity_at"] = now

        # If _process_message signaled escalation (e.g. validation
        # max retries), perform it NOW so Chatwoot is notified
        # immediately — don't depend on the user sending another msg.
        if result.get("escalation_triggered"):
            result = await self._perform_immediate_escalation(
                result, state,
            )

        # Persist conversation history to LangGraph checkpoint (Bug A fix)
        result["messages"] = self._build_turn_messages(
            message, result.get("ai_response", ""), now,
        )

        return result
```

**Why this works**: `_perform_immediate_escalation` already exists (we added it in Phase 1.4). It calls `perform_escalation()` and replaces the `ai_response` with the escalation confirmation message. The check is the same as line 125 in the error path. Reusing the exact same method.

**What changes for the 3 modes**: Nothing. They keep returning `escalation_triggered: True`. The parent (`base_mode.process()`) now catches it in BOTH paths (success + error).

### Verification
- The escalation will: disable bot, add labels, post private note, assign team, create DB record
- Duplicate protection (5-min window) prevents double-escalation if `escalation_node` also fires later

---

## P2: Fix `_escalate_image_receipt_issue` (CRITICAL)

### Problem

`element_data_tools.py:1219-1249` creates `Escalation(case_id=..., is_technical_error=True)` but the `Escalation` model has NEITHER column. This raises `TypeError` which is silently caught by `except Exception`. The escalation never gets saved.

### Fix

Rewrite to call `perform_escalation()` from the centralized service.

### File: `agent/tools/element_data_tools.py`

**Current** (lines 1219-1249):
```python
async def _escalate_image_receipt_issue(case_id: str, conversation_id: str) -> None:
    try:
        from database.models import Escalation
        async with get_async_session() as session:
            escalation = Escalation(
                case_id=uuid.UUID(case_id),         # ← BUG
                conversation_id=conversation_id,
                reason="El usuario ha enviado...",
                is_technical_error=True,             # ← BUG
                status="pending",
            )
            session.add(escalation)
            await session.commit()
            ...
    except Exception as e:
        logger.error(...)
```

**New**:
```python
async def _escalate_image_receipt_issue(case_id: str, conversation_id: str) -> None:
    """
    Silently escalate when user says they sent images but we didn't receive any.

    Creates a real escalation in Chatwoot (private note only, no user-facing
    message) so a human agent can follow up on the missing images.
    """
    try:
        from agent.services.escalation_service import perform_escalation

        await perform_escalation(
            conversation_id=conversation_id,
            reason=(
                "El usuario indica que ha enviado imágenes pero el sistema "
                "no las ha recibido. Posible problema técnico de Chatwoot/WhatsApp."
            ),
            source="auto",
            metadata={
                "case_id": case_id,
                "issue_type": "images_not_received",
                "is_technical_error": True,
            },
        )
    except Exception as e:
        logger.error(
            "failed_to_escalate_image_receipt_issue",
            case_id=case_id,
            conversation_id=conversation_id,
            error=str(e),
            exc_info=True,
        )
```

**Key differences**:
- Uses `perform_escalation()` → Chatwoot gets notified (private note, labels, team assignment)
- `case_id` and `is_technical_error` go in `metadata` dict (JSONB column) instead of non-existent columns
- The escalation is NOT silent to the team anymore — they get a Chatwoot notification
- Still silent to the USER (no response message returned — the calling function handles user-facing response)

### Note
The calling code (`confirmar_fotos_elemento`, around line 1180) handles user messaging separately. This function only handles the backend escalation.

---

## P3: Rewrite Legacy `escalar_a_humano` as Wrapper (HIGH)

### Problem

`tarifa_tools.py:222-488` has a 270-line legacy implementation of `escalar_a_humano` that:
- Has its own Chatwoot integration (doesn't use `escalation_service`)
- Is still a `@tool` decorator (could confuse LLM if loaded)
- Is excluded from `ALL_TOOLS` (line 496) but still importable

### Fix (Option C — wrapper)

Replace the 270-line implementation with a thin wrapper that delegates to `perform_escalation()`. Keep the `@tool` decorator and docstring so it remains a valid tool if accidentally loaded.

### File: `agent/tools/tarifa_tools.py`

**Replace lines 216-488** with:
```python
@tool
async def escalar_a_humano(motivo: str, es_error_tecnico: bool = False) -> dict[str, Any]:
    """
    Escala la conversación a un agente humano.

    DEPRECATED: This is a compatibility wrapper. The canonical version
    lives in agent.tools.shared_tools. Both delegate to
    agent.services.escalation_service.perform_escalation().

    Args:
        motivo: Reason for escalation
        es_error_tecnico: Whether this is a technical error escalation
    """
    from agent.services.escalation_service import perform_escalation
    from agent.state.helpers import get_current_state

    state = get_current_state()
    conversation_id = str(state.get("conversation_id", "unknown"))

    result = await perform_escalation(
        conversation_id=conversation_id,
        reason=motivo,
        source="tool_call",
        metadata={
            "is_technical_error": es_error_tecnico,
            "via": "tarifa_tools_compat_wrapper",
        },
    )

    return {
        "success": result.get("success", False),
        "message": result.get("message", "Error en la escalación"),
        "terminate_processing": True,
        "tool_name": "escalar_a_humano",
    }
```

**Why wrapper, not delete**: Keeps backward compatibility. If any future code accidentally imports from `tarifa_tools`, it still works correctly via the centralized service.

---

## P4: Fix `__init__.py` Imports (HIGH)

### Problem

`agent/tools/__init__.py` line 14 imports `escalar_a_humano` from `tarifa_tools` (legacy). `shared_tools` is not imported at all.

### Fix

Change the import source. Add `shared_tools` imports.

### File: `agent/tools/__init__.py`

**Current** (lines 11-17):
```python
from agent.tools.tarifa_tools import (
    listar_categorias,
    listar_tarifas,
    obtener_servicios_adicionales,
    escalar_a_humano,
    get_tarifa_tools,
    ALL_TOOLS as GENERAL_TOOLS,
)
```

**New**:
```python
from agent.tools.tarifa_tools import (
    listar_categorias,
    listar_tarifas,
    obtener_servicios_adicionales,
    get_tarifa_tools,
    ALL_TOOLS as GENERAL_TOOLS,
)

from agent.tools.shared_tools import (
    escalar_a_humano,
)
```

**Also update `__all__`**: Move `"escalar_a_humano"` out of the "General tools" comment block into a new "Shared tools" block for clarity.

---

## P5: `finalizar_expediente` → Chatwoot Notification (HIGH)

### Problem

When `finalizar_expediente` marks a case as `pending_review`, no notification reaches Chatwoot. The human team only discovers pending cases by checking the admin panel or database.

### Fix

After marking the case as `pending_review`, post a **private note** in Chatwoot (visible only to agents) and add a label. Do NOT disable the bot (the user can continue chatting about other topics).

### File: `agent/tools/case_tools.py`

**Insert AFTER** the `case.status = "pending_review"` block and `await session.commit()` (around line 1630), BEFORE `new_fsm_state = reset_fsm(...)`:

```python
    # Notify human agents via Chatwoot (private note + label)
    try:
        from shared.chatwoot_client import ChatwootClient
        from shared.config import get_settings

        settings = get_settings()
        chatwoot = ChatwootClient()
        conv_id = int(conversation_id)

        # Build summary for the private note
        element_summary = ", ".join(element_codes) if element_codes else "N/A"
        note_content = (
            "📋 **Expediente completado y pendiente de revisión**\n\n"
            f"- **Caso ID**: `{case_id}`\n"
            f"- **Categoría**: {categoria_slug}\n"
            f"- **Elementos**: {element_summary}\n"
            f"- **Precio**: {tarifa_amount}€ + IVA\n"
            f"- **Completado**: {datetime.now(UTC).strftime('%d/%m/%Y %H:%M')}\n\n"
            "El expediente necesita revisión humana antes de proceder."
        )

        await chatwoot.add_private_note(
            conversation_id=conv_id,
            content=note_content,
        )
        await chatwoot.add_labels(
            conversation_id=conv_id,
            labels=["expediente-pendiente"],
        )

        logger.info(
            "finalizar_expediente_chatwoot_notified",
            case_id=case_id,
            conversation_id=conversation_id,
        )
    except Exception as e:
        # Non-critical: case is already saved, Chatwoot notification is best-effort
        logger.warning(
            "finalizar_expediente_chatwoot_notification_failed",
            case_id=case_id,
            error=str(e),
        )
```

**Key decisions**:
- Private note (not public) — user doesn't see the technical summary
- Label `expediente-pendiente` — human agents can filter by this in Chatwoot
- Bot stays active — user can continue chatting (this is NOT an escalation)
- Best-effort — if Chatwoot fails, the case is already saved in DB (no data loss)
- Variables `element_codes`, `categoria_slug`, `tarifa_amount` are available from the FSM state read earlier in the function

### Note on variable availability

The `finalizar_expediente` function already reads `case_state = get_case_fsm_state(fsm_state)` near the top. The variables needed are:
- `conversation_id` — function parameter
- `case_id` — function parameter
- `element_codes` — from `case_state.get("element_codes", [])`
- `categoria_slug` — from `case_state.get("category_slug", "N/A")`
- `tarifa_amount` — from `case_state.get("tariff_amount", "N/A")`

These should be extracted at the top of the function alongside the existing reads.

---

## P6: Unify Digression Manager Keys (MEDIUM)

### Problem

`digression_manager.py:179-193` has hardcoded preserve keys independent of `CONTEXT_PRESERVE_RULES` in `mode_transitions.py`. This creates two sources of truth.

**Current inconsistencies**:
- Digression from PRESUPUESTO doesn't preserve `imagenes_enviadas`
- Digression from EXPEDIENTE doesn't preserve `tarifa_calculada`, `categoria_slug`

### Fix

Replace the hardcoded lists with a call to `get_preserve_keys()` from `mode_transitions.py`.

### File: `agent/router/digression_manager.py`

**Current** (lines 179-193):
```python
@staticmethod
def _get_preserve_keys(mode: str) -> list[str]:
    """Keys to preserve when temporarily leaving a mode."""
    if mode == "PRESUPUESTO_MODE":
        return [
            "element_codes",
            "tarifa_calculada", "categoria_slug",
            "precio_comunicado",
        ]
    if mode == "EXPEDIENTE_MODE":
        return [
            "case_id", "expediente_sub_mode", "datos_personales",
            "datos_vehiculo", "element_codes",
        ]
    return []
```

**New**:
```python
@staticmethod
def _get_preserve_keys(mode: str, target_mode: str = "") -> list[str]:
    """Keys to preserve when temporarily leaving a mode.

    Delegates to CONTEXT_PRESERVE_RULES for transitions with known
    targets. Falls back to a broad set for unknown targets (e.g.
    digression to ESCALATION where we want to keep everything).
    """
    from agent.router.mode_transitions import get_preserve_keys

    # Try specific rules first
    specific = get_preserve_keys(mode, target_mode)
    if specific:
        return specific

    # Fallback: broad preservation for unknown targets
    if mode == "PRESUPUESTO_MODE":
        return [
            "element_codes", "tarifa_calculada", "categoria_slug",
            "precio_comunicado", "imagenes_enviadas",
        ]
    if mode == "EXPEDIENTE_MODE":
        return [
            "case_id", "expediente_sub_mode", "element_codes",
            "tarifa_calculada", "categoria_slug",
            "datos_personales", "datos_vehiculo",
        ]
    return []
```

**Also update the call site** in `digression_manager.py` where `_get_preserve_keys` is called — pass the `target_mode` from the detected digression:

The call site is in the method that processes digressions. It currently calls `self._get_preserve_keys(current_mode)`. Update to `self._get_preserve_keys(current_mode, target_mode)`.

**Also need to verify** that `get_preserve_keys()` is exported from `mode_transitions.py`. Check if the function exists:

```python
# mode_transitions.py — this function should exist or be created
def get_preserve_keys(source_mode: str, target_mode: str) -> list[str]:
    """Get context keys to preserve for a specific transition."""
    source_rules = CONTEXT_PRESERVE_RULES.get(source_mode, {})
    return source_rules.get(target_mode, [])
```

---

## Execution Order

The changes have minimal interdependencies. Execute in this order:

1. **P1** (base_mode.py) — One insertion, 6 lines. Fixes ALL validation-escalation paths at once.
2. **P2** (element_data_tools.py) — Rewrite one function. Independent.
3. **P3** (tarifa_tools.py) — Replace legacy function with wrapper. Independent.
4. **P4** (__init__.py) — Change import source. Depends on P3 existing.
5. **P5** (case_tools.py) — Add notification block. Independent.
6. **P6** (digression_manager.py + mode_transitions.py) — Refactor keys. Independent.

**Parallelizable**: P1, P2, P3+P4, P5, P6 can all be done in parallel.

---

## Files Modified Summary

| File                                     | Change Type    | Lines Changed |
|------------------------------------------|----------------|---------------|
| `agent/modes/base_mode.py`              | INSERT         | ~6 lines      |
| `agent/tools/element_data_tools.py`     | REWRITE        | ~30 lines     |
| `agent/tools/tarifa_tools.py`           | REPLACE        | -250, +30     |
| `agent/tools/__init__.py`               | MODIFY         | ~8 lines      |
| `agent/tools/case_tools.py`             | INSERT         | ~40 lines     |
| `agent/router/digression_manager.py`    | REWRITE        | ~20 lines     |
| `agent/router/mode_transitions.py`      | INSERT (maybe) | ~5 lines      |

**Net change**: ~-110 lines (mostly from removing legacy `escalar_a_humano`)

---

## Verification Checklist

After all changes, verify these scenarios work end-to-end:

### Escalation Paths (all should reach Chatwoot)
- [ ] LLM calls `escalar_a_humano` tool → Chatwoot notified
- [ ] Fallback ESCALATE_TO_HUMAN (error path) → Chatwoot notified
- [ ] Validation max retries (success path) → Chatwoot notified (**P1**)
- [ ] User images not received → Chatwoot notified (**P2**)
- [ ] Digression "quiero hablar con una persona" → Chatwoot notified
- [ ] Panic button (agent_disabled) → Chatwoot notified

### Non-Escalation Notifications
- [ ] `finalizar_expediente` → Private note + label in Chatwoot (**P5**)

### Import Correctness
- [ ] `from agent.tools import escalar_a_humano` → gets `shared_tools` version (**P4**)
- [ ] `from agent.tools.tarifa_tools import escalar_a_humano` → works (wrapper) (**P3**)
- [ ] All modes import from `shared_tools` directly (already correct)

### Context Preservation
- [ ] Digression from PRESUPUESTO preserves `imagenes_enviadas` (**P6**)
- [ ] Digression from EXPEDIENTE preserves `tarifa_calculada` (**P6**)

### No Regressions
- [ ] Normal conversation flow (PRESUPUESTO → EVAL → EXPEDIENTE) works
- [ ] Tool calling in EXPEDIENTE_MODE works (fsm_state propagation)
- [ ] Duplicate escalation prevention (5-min window) still works
- [ ] `escalar_a_humano` from tarifa_tools returns same response format

---

## ADR Update

Update `docs/decisions/008-restore-escalation-integration.md` to include these additional fixes as Phase 2 of the same ADR (no new ADR needed — same decision, extended scope).

---

## Risk Assessment

| Change | Risk Level | Reasoning                                                          |
|--------|------------|--------------------------------------------------------------------|
| P1     | LOW        | Reuses existing `_perform_immediate_escalation`, 6 lines           |
| P2     | LOW        | Replaces broken code with working service call                     |
| P3     | LOW        | Wrapper preserves same interface, delegates to tested service      |
| P4     | LOW        | Import path change, all modes already use `shared_tools` directly  |
| P5     | LOW        | Best-effort notification, wrapped in try/except                    |
| P6     | LOW        | Fallback to broad keys if specific rules not found                 |

**Overall risk**: LOW — All changes are additive or replace broken code. No change to core conversation flow.
