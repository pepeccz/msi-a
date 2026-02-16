# Plan: Fix Expediente Prompt↔API Desynchronization & Related Issues

**Status**: Proposed
**Priority**: CRITICAL
**Created**: 2026-02-13
**Estimated effort**: 2-3 hours
**Risk level**: LOW (prompt changes + defensive guards, no architectural changes)

---

## 1. Overview

### Problem

A production conversation (ID: 1, Feb 13 2026) about homologating a motorcycle subchasis (Honda CBF600) failed to complete the expediente. Root cause analysis revealed **6 interconnected issues**, with a CRITICAL prompt↔API desynchronization as the primary cause.

The expedition flow broke because:
1. Mode prompts instruct the LLM to call `actualizar_datos_expediente(seccion="datos_personales", datos={...})`
2. The **real** tool signature is `actualizar_datos_expediente(datos_personales={...}, datos_vehiculo={...})`
3. The parameters `seccion` and `datos` **don't exist** — data is silently lost
4. The sub-mode never transitions forward → user stuck in a loop
5. The LLM eventually confessed "I don't have the necessary tools" to the user

### Solution

Multi-phase fix attacking all 6 issues from root cause to symptoms:

| Phase | What | Files Changed | Risk |
|-------|------|---------------|------|
| **1** | Fix prompt↔API desync (CRITICAL) | 2 prompt files | None |
| **2** | Add defensive guard in tool | 1 Python file | Very Low |
| **3** | Add anti-exposure rule in core prompts | 1 prompt file | None |
| **4** | Clean up stale references (VIABILIDAD, duplicate tool) | 2 files | Very Low |
| **5** | Inject image context to LLM | 2 Python files, 1 prompt | Low |
| **6** | Improve element field discovery prompt | 1 prompt file | None |

### Impact

- **Fixes**: Expediente data collection (affects ALL conversations entering EXPEDIENTE_MODE)
- **Fixes**: LLM exposing system internals to users
- **Fixes**: Images not acknowledged in collect_base_docs
- **Cleans**: Dead code and stale references
- **Does NOT change**: Architecture, database, API, frontend

---

## 2. Detailed Issue Analysis

### Issue #1 — CRITICAL: Prompt↔API Desync in `actualizar_datos_expediente`

**Files affected**:
- `agent/prompts/modes/expediente_datos_personales.md` (lines 11, 30, 37-39)
- `agent/prompts/modes/expediente_datos_vehiculo.md` (lines 11, 29, 35-37)

**Current (WRONG)**:
```markdown
`actualizar_datos_expediente(seccion="datos_personales", datos={...})`
```

**Real signature**:
```python
async def actualizar_datos_expediente(
    datos_personales: dict[str, str] | None = None,
    datos_vehiculo: dict[str, str] | None = None,
) -> dict[str, Any]:
```

**Contradiction**: The core prompt `05_tools_efficiency.md` (line 43) documents the CORRECT signature:
```
actualizar_datos_expediente(datos_personales, datos_vehiculo)
```
So the LLM receives **contradictory instructions** — core says one thing, mode prompt says another.

**Fix**: Update both mode prompts to match the real signature.

### Issue #2 — HIGH: No guard when both params are None

If the LLM passes wrong parameter names, `datos_personales` and `datos_vehiculo` are both `None`. The tool currently processes `None` silently — no data saved, no error, no transition.

**Fix**: Add explicit guard at the top of `actualizar_datos_expediente()` when both params are None.

### Issue #3 — HIGH: LLM exposes system limitations

The LLM said: *"necesitaría acceso a herramientas adicionales que actualmente no tengo disponibles"*

No anti-pattern exists for this in `04_anti_patterns.md`.

**Fix**: Add "Anti-Exposure of Internal Limitations" section.

### Issue #4 — MEDIUM: Stale VIABILIDAD_MODE references

`consulta_mode.md` references `VIABILIDAD_MODE` in lines 4, 12, 77, 85, 127, 153 — this mode was merged into PRESUPUESTO_MODE. Confusing for the LLM.

Also: `escalar_a_humano` is duplicated in both `shared_tools.py` and `tarifa_tools.py` with different signatures.

**Fix**: Replace VIABILIDAD references with PRESUPUESTO. Remove duplicate tool.

### Issue #5 — HIGH: Images not injected into LLM context

When users send images during `collect_base_docs` or `collect_element_data`:
1. Images are saved to DB via `save_images_silently()` ✅
2. But `state_input` (main.py line 282-288) does NOT include `incoming_attachments` ❌
3. `format_mode_context()` in `loader.py` does NOT inject image count ❌
4. The LLM has NO WAY to know images were received ❌

**Fix**: Pass image metadata to the graph and inject it into the LLM context.

### Issue #6 — LOW: LLM guesses element fields wrong

The LLM tried `guardar_datos_elemento(datos={modificacion: ..., longitud_total: ...})` — fields that don't exist in the SUBCHASIS schema. It auto-corrected by calling `obtener_campos_elemento()` afterward, but wasted a tool iteration.

**Fix**: Update `expediente_documentacion_elementos.md` to instruct LLM to ALWAYS call `obtener_campos_elemento()` BEFORE `guardar_datos_elemento()`.

---

## 3. Implementation Plan

### Phase 1: Fix Prompt↔API Desync (CRITICAL — Do First)

**Agent**: agent-dev

#### File: `agent/prompts/modes/expediente_datos_personales.md`

**Change 1** — Line 11: Replace
```markdown
- Si proporciona datos → usa `actualizar_datos_expediente(seccion="datos_personales", datos={...})`
```
With:
```markdown
- Si proporciona datos → usa `actualizar_datos_expediente(datos_personales={...})`
```

**Change 2** — Line 30: Replace
```markdown
3. **Guardar datos**: `actualizar_datos_expediente(seccion="datos_personales", datos={...})`
```
With:
```markdown
3. **Guardar datos**: `actualizar_datos_expediente(datos_personales={...})`
```

**Change 3** — Lines 37-39: Replace entire tools section
```markdown
- `actualizar_datos_expediente(seccion, datos)`: Guardar datos personales
  - `seccion` DEBE ser `"datos_personales"`
  - `datos` es un dict con los campos: `nombre`, `apellidos`, `email`, `telefono`, `dni_cif`, `domicilio_calle`, `domicilio_localidad`, `domicilio_provincia`, `domicilio_cp`, `itv_nombre`
```
With:
```markdown
- `actualizar_datos_expediente(datos_personales={...})`: Guardar datos personales
  - `datos_personales` es un dict con los campos: `nombre`, `apellidos`, `email`, `telefono`, `dni_cif`, `domicilio_calle`, `domicilio_localidad`, `domicilio_provincia`, `domicilio_cp`, `itv_nombre`
  - NO uses `seccion` ni `datos` — esos parámetros no existen
```

#### File: `agent/prompts/modes/expediente_datos_vehiculo.md`

**Change 1** — Line 11: Replace
```markdown
- Si proporciona datos → usa `actualizar_datos_expediente(seccion="datos_vehiculo", datos={...})`
```
With:
```markdown
- Si proporciona datos → usa `actualizar_datos_expediente(datos_vehiculo={...})`
```

**Change 2** — Line 29: Replace
```markdown
3. **Guardar datos**: `actualizar_datos_expediente(seccion="datos_vehiculo", datos={...})`
```
With:
```markdown
3. **Guardar datos**: `actualizar_datos_expediente(datos_vehiculo={...})`
```

**Change 3** — Lines 35-37: Replace
```markdown
- `actualizar_datos_expediente(seccion, datos)`: Guardar datos del vehículo
  - `seccion` DEBE ser `"datos_vehiculo"`
  - `datos`: `marca`, `modelo`, `anio`, `matricula`, `bastidor`
```
With:
```markdown
- `actualizar_datos_expediente(datos_vehiculo={...})`: Guardar datos del vehículo
  - `datos_vehiculo` es un dict con los campos: `marca`, `modelo`, `anio`, `matricula`, `bastidor`
  - NO uses `seccion` ni `datos` — esos parámetros no existen
```

---

### Phase 2: Add Defensive Guard in Tool (HIGH)

**Agent**: backend-dev

#### File: `agent/tools/case_tools.py`

Add guard after the existing defensive validations (line ~814), BEFORE the FSM state check (line 815):

```python
    # === GUARD: Detect incorrect parameter usage ===
    if datos_personales is None and datos_vehiculo is None:
        logger.warning(
            "actualizar_datos_expediente_no_data",
            message="Both datos_personales and datos_vehiculo are None. "
                    "The LLM may have used incorrect parameter names (e.g., 'seccion'/'datos').",
        )
        return tool_error_response(
            message="No se recibieron datos para guardar. "
                    "Usa datos_personales={...} para datos del titular "
                    "o datos_vehiculo={...} para datos del vehículo.",
            error_category=ErrorCategory.VALIDATION_ERROR,
            error_code="NO_DATA_PROVIDED",
            guidance="Llama a la herramienta con datos_personales={nombre: '...', apellidos: '...', ...} "
                     "o datos_vehiculo={marca: '...', modelo: '...', ...}. "
                     "NO uses los parámetros 'seccion' ni 'datos' — no existen.",
        )
    
    # === EXISTING IMPLEMENTATION BELOW ===
    state = get_current_state()
```

**Why this is important**: Even with the prompt fix, we need a safety net. If the LLM ever ignores the prompt and uses wrong params again, this guard will:
1. Log a warning (so we detect it in monitoring)
2. Return a clear error with guidance (so the LLM self-corrects)

---

### Phase 3: Add Anti-Exposure Rule (HIGH)

**Agent**: agent-dev

#### File: `agent/prompts/core/04_anti_patterns.md`

Add new section at the end of the file (after line 103):

```markdown

## Anti-Exposición de Limitaciones Internas (CRÍTICO)

NUNCA digas al usuario que te faltan herramientas, que no tienes acceso a funcionalidades,
o que necesitas "herramientas adicionales". Eres el asistente de MSI Automotive, no un sistema con limitaciones.

**Prohibido decir:**
- "No tengo acceso a herramientas para..."
- "Necesitaría herramientas adicionales que..."
- "No puedo completar esta acción por limitaciones técnicas"
- "Actualmente no tengo la capacidad de..."
- "No tengo disponible la funcionalidad de..."

**En su lugar:**
- Si no puedes hacer algo → Escala a humano: `escalar_a_humano(motivo="Necesito asistencia para completar esta gestión", es_error_tecnico=true)`
- Si falta contexto → Pide la información al usuario
- Si algo falla → "Voy a conectarte con un especialista para completar este paso"

**Regla**: De cara al usuario, TÚ PUEDES hacer todo lo relacionado con homologaciones.
Si algo se sale de tu alcance, transfieres a un especialista humano (escalación).
NUNCA menciones herramientas, limitaciones del sistema ni detalles técnicos internos.
```

---

### Phase 4: Clean Up Stale References (MEDIUM)

**Agent**: agent-dev

#### File: `agent/prompts/modes/consulta_mode.md`

**Change 1** — Line 5: Replace
```markdown
Representa ~10% del trafico. Es el punto de entrada para usuarios que quieren informarse ANTES de evaluar viabilidad o pedir presupuesto.
```
With:
```markdown
Representa ~10% del trafico. Es el punto de entrada para usuarios que quieren informarse ANTES de pedir presupuesto.
```

**Change 2** — Line 12: Replace
```markdown
4. Detectar interes especifico y ofrecer transicion a VIABILIDAD o PRESUPUESTO
```
With:
```markdown
4. Detectar interes especifico y ofrecer transicion a PRESUPUESTO_MODE
```

**Change 3** — Line 77: Replace
```markdown
4. **NO identifiques elementos especificos** — eso es VIABILIDAD_MODE
```
With:
```markdown
4. **NO identifiques elementos especificos** — eso es PRESUPUESTO_MODE
```

**Change 4** — Line 85: Replace
```markdown
- Usuario pregunta "Se puede homologar X?" (elemento especifico) → VIABILIDAD_MODE
```
With:
```markdown
- Usuario pregunta "Se puede homologar X?" (elemento especifico) → PRESUPUESTO_MODE
```

**Change 5** — Line 127: Replace
```markdown
- Cierra siempre con una oferta abierta: "¿Quieres que profundice en algo más?" o "¿Te interesa evaluar la viabilidad de alguna modificación?"
```
With:
```markdown
- Cierra siempre con una oferta abierta: "¿Quieres que profundice en algo más?" o "¿Te interesa un presupuesto para alguna modificación?"
```

**Change 6** — Line 153: Replace
```markdown
→ Si dice si → transicion a VIABILIDAD_MODE
```
With:
```markdown
→ Si dice si → transicion a PRESUPUESTO_MODE
```

#### File: `agent/prompts/modes/expediente_taller.md`

**Change 7** — Line 22: Replace (voseo → castellano España)
```markdown
1. **Preguntar**: "¿Tenés taller propio o Quieres que MSI te proporcione uno?"
```
With:
```markdown
1. **Preguntar**: "¿Tienes taller propio o quieres que MSI te proporcione uno?"
```

#### File: `agent/tools/tarifa_tools.py` — Evaluate removal of duplicate `escalar_a_humano`

**Action**: Verify that NO import in the codebase references `escalar_a_humano` from `tarifa_tools`. If confirmed, delete the duplicate function (lines ~222-280 approx).

**Verification command**:
```bash
rg "from.*tarifa_tools.*import.*escalar" agent/
rg "tarifa_tools.*escalar" agent/
```

If no references → delete. If references exist → update imports to point to `shared_tools.py`.

---

### Phase 5: Inject Image Context to LLM (HIGH)

**Agent**: agent-dev + backend-dev

This is the most complex change but still low-risk.

#### File: `agent/main.py`

**Change**: In the `state_input` construction (around line 282), add image metadata:

```python
# Build initial state
state_input = {
    "conversation_id": conversation_id,
    "user_id": user_id,
    "user_name": user_name,
    "user_message": user_message,
    "client_type": client_type,
    "messages": [],
    "incoming_attachments": [
        {"type": "image", "data_url": a.get("data_url", "")}
        for a in (attachments or [])
        if a.get("data_url")
    ],
}
```

#### File: `agent/modes/expediente_mode.py`

**Change**: In the LLM message construction for expediente sub-modes, prepend image info to the user message when attachments are present:

```python
# In _run_llm_loop or _build_messages (the method that constructs LLM messages):
user_msg = state.get("user_message", "")
attachments = state.get("incoming_attachments", [])
image_count = len(attachments)

if image_count > 0:
    user_msg = f"[El usuario ha enviado {image_count} imagen(es) junto con este mensaje]\n{user_msg}"
```

**Why this approach**: Instead of modifying `format_mode_context()` (which is synchronous and can't query DB), we inject the image info directly into the user message. This is simple, deterministic, and gives the LLM immediate awareness of images.

#### File: `agent/prompts/modes/expediente_documentacion_base.md`

**Change**: Add clarification about image awareness:

After the existing content about receiving documents, add:
```markdown
## Reconocimiento de Imágenes

Cuando el usuario envía fotos, verás `[El usuario ha enviado N imagen(es)]` al inicio de su mensaje.
SIEMPRE confirma la recepción: "He recibido tus {N} fotos. ¿Son todas o tienes más por enviar?"
NO ignores las imágenes — el usuario espera confirmación de que las recibiste.
```

---

### Phase 6: Improve Element Field Discovery (LOW)

**Agent**: agent-dev

#### File: `agent/prompts/modes/expediente_documentacion_elementos.md`

Add explicit instruction to check fields BEFORE trying to save:

Search for the section about `guardar_datos_elemento` and add/modify:

```markdown
## Orden OBLIGATORIO para datos técnicos

1. PRIMERO: `obtener_campos_elemento()` → Ver qué campos necesita este elemento
2. SEGUNDO: Pedir al usuario los datos según los campos retornados
3. TERCERO: `guardar_datos_elemento(datos={...})` → Con los field_key exactos

**NUNCA** llames a `guardar_datos_elemento` sin haber consultado primero `obtener_campos_elemento`.
Los campos varían según el tipo de elemento — NO asumas qué campos existen.
```

---

## 4. Testing Plan

### Manual Testing (Required)

After all phases are deployed, run a full expediente flow via WhatsApp:

1. **Test: Basic presupuesto → expediente flow**
   - Send: "Quiero homologar el escape de mi moto"
   - Verify: Price communicated, images offered
   - Confirm: Open expediente
   - Verify: Element data collection works
   - Verify: Base docs collection acknowledges images
   - Verify: Personal data saved correctly
   - Verify: Vehicle data saved correctly
   - Verify: Workshop data collected
   - Verify: Review summary shows all data
   - Confirm: Expediente finalized

2. **Test: User sends data out of order**
   - In `collect_personal`, send vehicle data ("Honda CBF600, 6384BRN")
   - Verify: Agent asks for personal data (doesn't crash)
   - Verify: Helpful error message, not system exposure

3. **Test: Image awareness**
   - In `collect_base_docs`, send images without text
   - Verify: Next LLM response acknowledges images received
   - Send "listo"
   - Verify: Transition to collect_personal

### Log Monitoring (After Deploy)

Watch agent logs for 24 hours after deploy:
```bash
docker-compose logs -f agent 2>&1 | grep "actualizar_datos_expediente_no_data"
```

If this warning appears → the LLM is STILL using wrong params somewhere. Investigate immediately.

---

## 5. Deployment Plan

### Pre-deployment Checklist

- [ ] All 6 phases implemented
- [ ] Prompt files reviewed for consistency with `05_tools_efficiency.md`
- [ ] No other prompt files reference `seccion` or `datos` as params
- [ ] `escalar_a_humano` duplicate resolved (if applicable)
- [ ] VIABILIDAD_MODE references eliminated

### Deployment Steps

1. Stop agent service: `docker-compose stop agent`
2. Deploy code changes (prompts + Python)
3. Start agent service: `docker-compose start agent`
4. Verify agent health: `docker-compose logs -f agent --tail=50`
5. Run manual test flow (Test 1 above)

### Rollback Plan

All changes are prompt text or defensive guards. If issues arise:
1. Revert prompt files to previous version
2. Remove defensive guard from `case_tools.py`
3. Restart agent

No database migrations. No API changes. No frontend changes.

---

## 6. Acceptance Criteria

- [ ] `expediente_datos_personales.md` uses `datos_personales={...}` (no `seccion`/`datos`)
- [ ] `expediente_datos_vehiculo.md` uses `datos_vehiculo={...}` (no `seccion`/`datos`)
- [ ] `actualizar_datos_expediente()` returns clear error when both params are None
- [ ] Core prompt `04_anti_patterns.md` includes anti-exposure rule
- [ ] `consulta_mode.md` has zero references to VIABILIDAD_MODE
- [ ] User images are acknowledged by the LLM during expediente collection
- [ ] A full expediente flow completes without getting stuck
- [ ] No references to `seccion` param exist in any expediente-related prompt

### Verification Command

After implementation, run:
```bash
rg "seccion.*datos_personales|seccion.*datos_vehiculo|seccion=\"datos" agent/prompts/
```
Expected output: **zero results**.

---

## 7. Summary of All Changes

| # | File | Change Type | Lines Changed (est.) |
|---|------|-------------|---------------------|
| 1 | `agent/prompts/modes/expediente_datos_personales.md` | Prompt fix | ~10 |
| 2 | `agent/prompts/modes/expediente_datos_vehiculo.md` | Prompt fix | ~10 |
| 3 | `agent/tools/case_tools.py` | Defensive guard | ~15 |
| 4 | `agent/prompts/core/04_anti_patterns.md` | New anti-pattern | ~20 |
| 5 | `agent/prompts/modes/consulta_mode.md` | Stale refs cleanup | ~6 |
| 6 | `agent/prompts/modes/expediente_taller.md` | Voseo fix | ~1 |
| 7 | `agent/tools/tarifa_tools.py` | Dead code removal | ~60 (delete) |
| 8 | `agent/main.py` | Image context injection | ~5 |
| 9 | `agent/modes/expediente_mode.py` | Image context in LLM msg | ~5 |
| 10 | `agent/prompts/modes/expediente_documentacion_base.md` | Image awareness prompt | ~5 |
| 11 | `agent/prompts/modes/expediente_documentacion_elementos.md` | Field discovery order | ~8 |

**Total**: ~11 files, ~145 lines changed (mostly prompt text)
**Risk**: LOW — primarily prompt changes with one defensive Python guard
