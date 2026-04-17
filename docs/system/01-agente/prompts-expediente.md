---
titulo: Prompts de EXPEDIENTE
ambito: expediente
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Prompts de EXPEDIENTE

## Resumen

Los prompts de EXPEDIENTE se organizan **por sub-modo**. Hay 6 prompts temáticos (1 por sub-modo) que conforman las instrucciones del sistema para cada fase. Todos cargan desde `agent/prompts/modes/expediente_*.md` y se inyectan dinámicamente por `assemble_system_prompt()` según el sub_mode actual.

Además existe un prompt transversal `core.md` que define principios universales (identidad, voz, anti-patrones) aplicables a TODO el agente (PRE y EXPEDIENTE).

## Escenarios

### 1. Entrada a COLLECT_ELEMENT_DATA (primer turno)
- CUANDO entry_router despacha a `collect_element_data_node`, build_mode_tool_loop invoca `assemble_system_prompt(mode="EXPEDIENTE_MODE", sub_mode="collect_element_data")`
- ENTONCES se cargan: `core.md` (principios, voz, identidad MSI) + `expediente_elements.md` (instrucciones específicas: "solicita fotos del [elemento], espera confirmación") + inyección de modo_context (`current_element_code`, `element_display_names`, `element_phase`).

### 2. Carga de prompt por sub-modo
- CUANDO `_resolve_mode_key(sub_mode="collect_personal")` se invoca en `loader.py`
- ENTONCES retorna `"modes/expediente_personal"`, loader construye la ruta, carga el Markdown, parsea bloques `<instruction>`, y lo inyecta en el system prompt.

### 3. Inyección de client_context (profesional vs particular)
- CUANDO el client_type es "professional"
- ENTONCES `_build_client_context(state)` inserta "Cliente: **PROFESIONAL**" en el prompt para que el bot ajuste el tono (más formal, referencias a CIF en lugar de DNI).

### 4. Phase-specific instructions (fotos vs datos)
- CUANDO `element_phase == "photos"` en COLLECT_ELEMENT_DATA
- ENTONCES el prompt inyecta sección "Fase actual: Recolección de FOTOS", y desactiva las herramientas de datos (`obtener_campos_elemento`, `guardar_datos_elemento`) para forzar que el bot hable de fotos.

### 5. Prompt para REVIEW_SUMMARY
- CUANDO entry_router despacha a `review_summary_node`
- ENTONCES `expediente_review.md` proporciona formato de resumen (línea por línea: ✅ Personal, ✅ Vehículo, etc.), y fuerza que el bot presente un resumen estructurado antes de llamar a `finalizar_expediente`.

### 6. Prompt de recuperación tras error
- CUANDO `guardar_datos_elemento` retorna error (ej. field_key inválido)
- ENTONCES el post_tool_hook inyecta en el system prompt: "Error anterior: [campo rechazado], por favor reintenta con: [sugerencia]", y el bot reformula.

## Reglas duras

1. **core.md es la fuente de verdad de voz y principios**: nunca se contradicen con los prompts de sub-modo. Si un sub-modo necesita variar la voz, debe hacerlo dentro de bloques `<sub_mode_specific>`, no reemplazando core.

2. **Variables inyectadas son read-only desde el prompt**: el prompt NUNCA asigna valores a `{case_id}`, `{current_element_code}`, etc.; solo LOS LEE. Cambios a estos valores vienen de tools y reducers, no del prompt.

3. **Los 6 sub-modos tienen EXACTAMENTE 1 prompt cada uno**: no hay branches internas tipo `if phase=="photos" then ...` dentro del Markdown. Eso se hace vía inyección de variables o vía remover tools del toolset.

4. **Fase "photos" no menciona tools de datos**: `expediente_elements.md` NO contiene referencias a `obtener_campos_elemento` o `guardar_datos_elemento` mientras `phase=="photos"`, aunque las herramientas estén disponibles. El LLM es instruido a ignorarlas.

5. **Transiciones de sub-modo son transparentes en el prompt**: cuando `expediente_sub_mode` cambia (ej. "collect_element_data" → "collect_base_docs"), el siguiente turno carga un prompt completamente distinto automáticamente.

## Catálogo de prompts

| Archivo | Sub-modo | Líneas (~) | Propósito |
|---------|----------|------------|-----------|
| `agent/prompts/core.md` | N/A (transversal) | 400+ | Identidad MSI, principios (sin re-identificación, price-before-images), anti-patrones, voz |
| `agent/prompts/modes/expediente_elements.md` | COLLECT_ELEMENT_DATA | 61 | Instrucciones para foto + datos técnicos por elemento; fases fotos vs datos |
| `agent/prompts/modes/expediente_base_docs.md` | COLLECT_BASE_DOCS | 42 | Cómo solicitar documentación técnica, permiso circulación, vistas 360° |
| `agent/prompts/modes/expediente_personal.md` | COLLECT_PERSONAL | 43 | Recolección de nombre, DNI, email, teléfono, domicilio |
| `agent/prompts/modes/expediente_vehicle.md` | COLLECT_VEHICLE | 42 | Recolección de marca, modelo, matrícula, bastidor, año |
| `agent/prompts/modes/expediente_workshop.md` | COLLECT_WORKSHOP | 42 | Recolección de datos del taller (si `taller_propio=True`): instalador, RAE, teléfono |
| `agent/prompts/modes/expediente_review.md` | REVIEW_SUMMARY | 61 | Presentación de resumen final, validación pre-finalización, instrucciones para `finalizar_expediente` |
| `agent/prompts/modes/session_recovery.md` | Todas (fallback) | 20 | Mensaje de bienvenida cálida cuando se recupera sesión tras timeout |

## Mapeo al código

### Loader y assembly
- `agent/prompts/loader.py:107-172` — `assemble_system_prompt(mode, sub_mode, mode_context, client_context)`
- `agent/prompts/loader.py:192-230` — `_resolve_mode_key(mode, sub_mode)` → ruta de archivo Markdown
- `agent/prompts/loader.py:260-320` — parseo de bloques `<instruction>`, `<tools>`, etc.

### Inyección en tool loop
- `agent/modes/expediente_nodes.py:717-725` — factory `_build_expediente_node` invoca `assemble_system_prompt` en el loop_config

### Variables inyectadas disponibles
- `mode_context["current_element_code"]`, `element_phase`, `element_display_names[code]`
- `client_type` (para "PROFESIONAL" vs "PARTICULAR")
- `case_id` (para auditoría en el prompt)
- `element_data_status` (para progreso: "1/5 completados")

## Fuera de alcance

- `agent/prompts/modes/pre_expediente_*.md` — prompts de PRE_EXPEDIENTE (otro scope)
- `agent/prompts/calculator_base.py` — lógica de cálculos (otro scope)
- Modificaciones a `core.md` que afecten a PRE_EXPEDIENTE — cambio transversal, requiere aprobación
