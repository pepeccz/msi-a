# fix-expediente-anticipation

| Campo | Valor |
|---|---|
| **Fecha** | 2026-02-26 |
| **Estado** | PENDIENTE APROBACIÓN |
| **Autor** | architect |
| **Revisión** | investigator-dev |
| **Prioridad** | ALTA |
| **Estimación** | 3–4 horas de implementación |

---

## Resumen Ejecutivo

El `EXPEDIENTE_MODE` del agente MSI-a recorre seis sub-modos en secuencia para recopilar la información necesaria para un expediente de homologación. Cuando una tool señala que el sub-modo actual ha terminado (devolviendo `next_step` o `all_elements_complete`), el LLM ve en ese mismo turno tanto la señal de transición como el `message` de la tool, que describe el siguiente sub-modo. Como consecuencia, el LLM **anticipa** el contenido del sub-modo siguiente en la misma respuesta donde debería limitarse a confirmar que el paso actual se completó.

El impacto en la experiencia del usuario es significativo: el cliente recibe en un único mensaje la confirmación del paso actual mezclada con las preguntas del siguiente, sin separación conversacional. En el caso real documentado, al completar la documentación base, el LLM listó de golpe los datos personales **y** los datos del vehículo en un solo bloque, lo que resulta confuso y poco profesional.

La estrategia de solución aplica **tres capas defensivas** complementarias. La primera (F-1) neutraliza el `message` público de las tools de transición para que no describan el paso siguiente. La segunda (F-2) añade instrucciones explícitas de cierre en los prompts de cada sub-modo origen, enseñando al LLM el patrón correcto de respuesta ante una transición. La tercera (F-3) implementa un fast-path break en el bucle de tool calls de `expediente_mode.py` que interrumpe el turno inmediatamente al detectar un cambio de sub-modo, garantizando que el LLM del sub-modo destino sea quien gestione el turno siguiente.

El riesgo de estos cambios es **bajo**. F-1 y F-2 afectan solo strings de mensajes y archivos Markdown de prompts. F-3 añade una detección de transición en el bucle existente sin alterar la lógica de routing de sub-modos. Ningún cambio modifica el esquema de estado, las migraciones de base de datos ni la lógica de identificación de elementos.

---

## Alcance

### Archivos afectados

| Archivo | Cambio | Fase |
|---|---|---|
| `agent/tools/element_data_tools.py` | Neutralizar `message` en transiciones de elemento → base docs | F-1 |
| `agent/tools/case_tools.py` | Neutralizar `message` en transiciones base→personal, personal→vehículo, vehículo→taller, taller→review | F-1 |
| `agent/prompts/modes/expediente_documentacion_elementos.md` | Añadir sección "Al Completar Este Sub-Modo" | F-2 |
| `agent/prompts/modes/expediente_documentacion_base.md` | Añadir sección "Al Completar Este Sub-Modo" | F-2 |
| `agent/prompts/modes/expediente_datos_personales.md` | Añadir sección "Al Completar Este Sub-Modo" | F-2 |
| `agent/prompts/modes/expediente_datos_vehiculo.md` | Añadir sección "Al Completar Este Sub-Modo" | F-2 |
| `agent/prompts/modes/expediente_taller.md` | Añadir sección "Al Completar Este Sub-Modo" | F-2 |
| `agent/modes/expediente_mode.py` | Fast-path break al detectar cambio de sub-modo en el bucle de tool calls | F-3 |

### Archivos NO afectados

Los siguientes archivos **no deben modificarse** — la lógica de routing de sub-modos es correcta y no es la causa del problema:

- `agent/modes/submodos/` — Los handlers de sub-modo no cambian
- `agent/state/conversation_state.py` — El esquema de estado no cambia
- `agent/router/` — El router de intención no cambia
- `agent/graph/conversation_graph.py` — El grafo no cambia
- `database/models.py` — Sin cambios de modelo
- `api/` — Sin cambios de API

> **Importante**: `_extract_context_from_tool()` en `expediente_mode.py` **no cambia**. Usa `success`, `next_step` y `fsm_state_update` para tomar decisiones de routing, **nunca** el campo `message`. Los cambios de F-1 sobre `message` no afectan el routing interno.

---

## Fases de Implementación

---

### FASE 1 — Neutralizar messages de tools (F-1 + F-5)

**Prioridad**: ALTA  
**Dificultad**: BAJA  
**Agente**: `agent-dev`

Esta fase modifica los strings de `message` que las tools devuelven en su resultado público. El objetivo es que los mensajes de transición sean confirmaciones neutras del paso completado, sin describir el siguiente.

---

#### 1.1 — `agent/tools/element_data_tools.py`

**Transición T-1 / T-2**: `completar_elemento_actual()` cuando es el último elemento

```python
# ANTES
"message": "Todos los elementos están listos. Ahora necesito la documentación base del vehículo."

# DESPUÉS
"message": "Todos los elementos registrados correctamente."
```

**Transición T-7**: `completar_elemento_actual()` cuando quedan más elementos (anti-anticipación de elemento siguiente)

```python
# ANTES
"message": f"Pasamos al siguiente: {nombre}."

# DESPUÉS
"message": f"{element.name} completado ✅"
```

**Transición T-2 (alternativa)**: `confirmar_fotos_elemento()` cuando no hay campos adicionales y es el último elemento

```python
# ANTES
"message": "Ahora necesito la documentación base del vehículo."

# DESPUÉS
"message": "Todos los elementos están completos."
```

**Criterio de éxito**: En ningún result de estas tools aparece la palabra "documentación base" ni referencia al siguiente sub-modo.

---

#### 1.2 — `agent/tools/case_tools.py`

**Transición T-3**: `confirmar_documentacion_base()` → COLLECT_PERSONAL

```python
# ANTES
"message": "Ahora necesito tus datos personales."

# DESPUÉS
"message": "Documentación base recibida y registrada correctamente."
```

**Transición T-4**: `actualizar_datos_expediente()` cuando personal → vehículo

```python
# ANTES
"message": get_step_prompt(COLLECT_VEHICLE, ...)   # Pregunta completa del vehículo

# DESPUÉS
"message": "Datos personales guardados correctamente."
```

**Transición T-5**: `actualizar_datos_expediente()` cuando vehículo → taller

```python
# ANTES
"message": get_step_prompt(COLLECT_WORKSHOP, ...)  # Pregunta completa del taller

# DESPUÉS
"message": "Datos del vehículo guardados correctamente."
```

**Transición T-6**: `actualizar_datos_taller()` → REVIEW_SUMMARY

```python
# ANTES
"message": get_step_prompt(REVIEW_SUMMARY, ...)    # Resumen completo

# DESPUÉS
"message": "Información del taller guardada correctamente."
```

**Criterio de éxito**: Al revisar los tool results de transición en logs, el campo `message` no contiene ninguna pregunta ni referencia al sub-modo siguiente.

---

### FASE 2 — Instrucciones anti-anticipación en prompts (F-2)

**Prioridad**: ALTA  
**Dificultad**: BAJA  
**Agente**: `agent-dev`

Esta fase añade al final de cada prompt de sub-modo origen una sección que explica al LLM cómo responder cuando la tool devuelve una señal de transición. Incluye un ejemplo CORRECTO y un ejemplo de ERROR para que el LLM reconozca el patrón a evitar.

---

#### 2.1 — `agent/prompts/modes/expediente_documentacion_elementos.md`

Añadir al final del archivo:

```markdown
---

## Al Completar Este Sub-Modo

Cuando una tool devuelve éxito con señal de transición (por ejemplo, `all_elements_complete: true` o `next_step: "COLLECT_BASE_DOCS"`), **tu única tarea es confirmar el cierre de este paso**. No preguntes nada del siguiente sub-modo.

**CORRECTO ✅**
> "Perfecto, todos los elementos quedan registrados. Ahora continuamos con el siguiente paso."

**INCORRECTO ❌ (anticipación)**
> "Perfecto, todos los elementos quedan registrados. Ahora necesito la documentación base del vehículo: el permiso de circulación, la ficha técnica y..."

La presentación del siguiente sub-modo es responsabilidad del turno siguiente, no de este turno.
```

---

#### 2.2 — `agent/prompts/modes/expediente_documentacion_base.md`

Añadir al final del archivo:

```markdown
---

## Al Completar Este Sub-Modo

Cuando `confirmar_documentacion_base()` devuelve éxito y señal de transición a datos personales, **limítate a confirmar el registro de la documentación**. No listes los datos personales que se pedirán a continuación.

**CORRECTO ✅**
> "Documentación base registrada. Continuamos con el siguiente paso."

**INCORRECTO ❌ (anticipación)**
> "Documentación base registrada. Ahora necesito tus datos personales: nombre completo, DNI, dirección y teléfono de contacto..."

El sub-modo de datos personales se encargará de solicitar esa información en el turno siguiente.
```

---

#### 2.3 — `agent/prompts/modes/expediente_datos_personales.md`

Añadir al final del archivo:

```markdown
---

## Al Completar Este Sub-Modo

Cuando `actualizar_datos_expediente()` devuelve éxito y señal de transición a datos del vehículo, **confirma solo que los datos personales han sido guardados**. No anticipes las preguntas del vehículo.

**CORRECTO ✅**
> "Datos personales guardados. Seguimos con el siguiente paso."

**INCORRECTO ❌ (anticipación)**
> "Datos personales guardados. Ahora dime los datos del vehículo: matrícula, marca, modelo, año de fabricación y número de bastidor..."

Esas preguntas corresponden al sub-modo siguiente, que las gestionará en el próximo turno.
```

---

#### 2.4 — `agent/prompts/modes/expediente_datos_vehiculo.md`

Añadir al final del archivo:

```markdown
---

## Al Completar Este Sub-Modo

Cuando `actualizar_datos_expediente()` devuelve éxito y señal de transición a datos del taller, **confirma solo que los datos del vehículo han sido guardados**. No anticipes las preguntas del taller.

**CORRECTO ✅**
> "Datos del vehículo registrados. Continuamos."

**INCORRECTO ❌ (anticipación)**
> "Datos del vehículo registrados. Ahora necesito los datos del taller: nombre, dirección, teléfono y número de autorización..."

El sub-modo de taller gestionará esa solicitud en el turno siguiente.
```

---

#### 2.5 — `agent/prompts/modes/expediente_taller.md`

Añadir al final del archivo:

```markdown
---

## Al Completar Este Sub-Modo

Cuando `actualizar_datos_taller()` devuelve éxito y señal de transición a la revisión final, **confirma solo que la información del taller ha sido guardada**. No anticipies el resumen del expediente.

**CORRECTO ✅**
> "Información del taller guardada. Ya tenemos todo lo necesario."

**INCORRECTO ❌ (anticipación)**
> "Información del taller guardada. A continuación te muestro el resumen completo del expediente: nombre, DNI, matrícula, taller..."

El sub-modo de revisión presentará el resumen en el turno siguiente con el formato adecuado.
```

---

### FASE 3 — Fast-path break en sub-mode transitions (F-3)

**Prioridad**: MEDIA  
**Dificultad**: MEDIA  
**Agente**: `agent-dev`

Esta fase añade una guardia en el bucle de tool calls de `expediente_mode.py`. Si durante la ejecución de una tool el sub-modo cambia, el bucle se interrumpe inmediatamente usando el `message` neutral de la tool como `ai_response`. Esto garantiza que el LLM del sub-modo destino sea quien tome el turno siguiente.

---

#### 3.1 — Ubicación del cambio

Archivo: `agent/modes/expediente_mode.py`

El bucle de tool calls en `_process_message()` (o equivalente en `BaseModeNode`) tiene una estructura aproximada de:

```python
for iteration in range(MAX_ITERATIONS):
    response = await llm.ainvoke([...])
    
    if not response.tool_calls:
        break
    
    for tool_call in response.tool_calls:
        tool_result = await self._execute_tool(tool_call)
        context_updates = self._extract_context_from_tool(tool_call.name, tool_result)
        mode_context.update(context_updates)
        
        # ← INSERTAR AQUÍ (después de mode_context.update)
```

El fast-path break ya existente para transiciones `_transition_to` se encuentra alrededor de las líneas 1262–1283 (verificar en el código actual). El nuevo código debe insertarse **antes** de ese bloque para que ambos mecanismos no se dupliquen.

---

#### 3.2 — Lógica a insertar

```python
# Fast-path break: sub-mode transition detected during tool execution
new_sub_mode = context_updates.get("expediente_sub_mode")
if new_sub_mode and new_sub_mode != current_sub_mode:
    logger.info(
        "sub_mode_transition_fast_path_break",
        from_sub_mode=current_sub_mode,
        to_sub_mode=new_sub_mode,
        tool_name=tool_call.name,
        iteration=iteration,
    )
    # Use the neutral tool message as the closing response for this turn
    closing_message = tool_result.get("message", "Paso completado correctamente.")
    return {
        "ai_response": closing_message,
        "mode_context": mode_context,
    }
```

**Variables a verificar en el código actual**:
- `current_sub_mode`: se obtiene de `mode_context.get("expediente_sub_mode")` **antes** del bucle
- `context_updates`: resultado de `_extract_context_from_tool()`
- `tool_result`: el dict devuelto por la tool

---

#### 3.3 — Integración con fast-path break existente

El bloque existente (líneas ~1262–1283) detecta transiciones de **modo** (e.g., EXPEDIENTE_MODE → ESCALATION_MODE) mediante `_transition_to`. El nuevo bloque detecta transiciones de **sub-modo dentro de EXPEDIENTE_MODE**. Son complementarios y no duplican lógica. El orden correcto es:

1. Detectar cambio de sub-modo → break (nuevo F-3)
2. Detectar cambio de modo → break (existente)
3. Continuar con siguiente iteración del bucle

---

#### 3.4 — Log esperado

En cada transición de sub-modo, los logs del agente deben mostrar:

```json
{
  "event": "sub_mode_transition_fast_path_break",
  "from_sub_mode": "COLLECT_BASE_DOCS",
  "to_sub_mode": "COLLECT_PERSONAL",
  "tool_name": "confirmar_documentacion_base",
  "iteration": 0
}
```

---

## Criterios de Éxito

### FASE 1 — Verificación de messages neutrales

| Criterio | Cómo verificar |
|---|---|
| `completar_elemento_actual()` no menciona sub-modo siguiente | Buscar en `element_data_tools.py`: `rg "documentación base\|base docs\|siguiente sub" agent/tools/element_data_tools.py` |
| `confirmar_documentacion_base()` no menciona datos personales | Buscar en `case_tools.py`: `rg "datos personales\|personal" agent/tools/case_tools.py` |
| `actualizar_datos_expediente()` no incluye `get_step_prompt()` en el return | Revisar que el return de transición no llama a `get_step_prompt` |
| `actualizar_datos_taller()` no incluye `get_step_prompt(REVIEW_SUMMARY)` | Ídem |

### FASE 2 — Verificación de prompts

| Criterio | Cómo verificar |
|---|---|
| Los 5 prompts tienen sección "Al Completar Este Sub-Modo" | `rg "Al Completar Este Sub-Modo" agent/prompts/modes/expediente_*.md` |
| Cada sección contiene ejemplos CORRECTO e INCORRECTO | Revisión visual de cada archivo |

### FASE 3 — Verificación de logs

| Criterio | Cómo verificar |
|---|---|
| Log `sub_mode_transition_fast_path_break` aparece en cada transición | Buscar en logs del agente: `grep "sub_mode_transition_fast_path_break" logs/agent.log` |
| El log incluye `from_sub_mode`, `to_sub_mode`, `tool_name` | Revisión del formato JSON del log |
| El LLM del sub-modo destino recibe el turno en la iteración siguiente | Revisar conversaciones en Chatwoot: la respuesta del turno de transición es corta y neutra |

### Verificación end-to-end (sin ejecutar tests)

1. **Chatwoot**: Iniciar un expediente completo manualmente y verificar que en cada transición de sub-modo el mensaje del agente es una confirmación corta, sin listar preguntas del siguiente paso.
2. **Logs del agente**: Verificar que `sub_mode_transition_fast_path_break` aparece exactamente 5 veces por expediente completo (una por cada transición T-3 a T-7; T-1/T-2 también si hay elementos).
3. **Caso real**: Reproducir el caso documentado (completar documentación base) y confirmar que el LLM NO lista datos personales + vehículo juntos.

---

## Orden de Ejecución

```
FASE 1 (F-1 + F-5)
    ↓
FASE 2 (F-2)
    ↓
Verificación manual en Chatwoot (si F-1+F-2 son suficientes → done)
    ↓
FASE 3 (F-3) — Capa extra de garantía
```

**Justificación del orden**:

- F-1 y F-2 son suficientes para resolver el **caso real documentado** (T-3). Si el mensaje de la tool es neutral y el prompt instruye al LLM sobre el patrón correcto, la anticipación desaparece.
- F-3 es la capa de garantía para casos edge donde F-1+F-2 no sean suficientes (e.g., LLM ignorando instrucciones de prompt bajo cierta presión de contexto).
- **F-4 (separar `_next_step` del `message` público)** se pospone como mejora futura. La refactorización interna de la estructura de tool returns tiene complejidad media y beneficio menor dado que F-1+F-2+F-3 ya resuelven el problema. Se puede abordar en un sprint de refactoring posterior.

---

## Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Al neutralizar `message` de tools, el LLM del sub-modo destino no sabe que hubo transición | BAJA | MEDIO | El mecanismo `just_transitioned_from` ya existente inyecta contexto de transición al sub-modo destino en el turno N+1. No requiere el `message` de la tool. |
| F-3 rompe casos donde la tool devuelve múltiples señales en el mismo turno | MUY BAJA | BAJO | La guardia solo actúa si `expediente_sub_mode` en `context_updates` **difiere** del sub-modo actual. Si la tool devuelve el mismo sub-modo, no se interrumpe. |
| Alguna parte del sistema depende del `message` de transición para lógica interna | MUY BAJA | ALTO | Verificar que `_extract_context_from_tool()` usa `success`, `next_step` y `fsm_state_update`, no `message`. El campo `message` es solo para el LLM, no para routing. Validar con `rg "tool_result\[.message.\]" agent/modes/expediente_mode.py`. |
| El LLM ignora las instrucciones del prompt de F-2 bajo alta presión de contexto | BAJA | MEDIO | F-3 actúa como fallback: aunque el LLM anticipe, el fast-path break interrumpe el turno antes de que el LLM pueda generar la respuesta anticipada. |
| F-2 rompe el flujo normal del sub-modo por instrucciones confusas | MUY BAJA | BAJO | Las instrucciones añadidas son condicionadas ("cuando la tool devuelve señal de transición"). No afectan el flujo normal de recopilación de datos dentro del sub-modo. |

---

## Dependencias

- **Sin dependencias externas**: Todos los cambios son internos al agente.
- **Sin migraciones de base de datos**: El esquema no cambia.
- **Sin cambios de API**: No hay endpoints nuevos ni modificados.
- **Reinicio del agente requerido** tras los cambios para que los nuevos prompts sean cargados en memoria.

---

## Notas para el Implementador (`agent-dev`)

1. **Lee el skill `msia-agent`** antes de empezar. Especialmente las reglas sobre tool returns y mode transitions.
2. **Verifica las líneas exactas** de `expediente_mode.py` antes de aplicar F-3 — el informe del investigador indica aprox. líneas 1245 y 1262–1283, pero puede variar.
3. **Para F-1**, busca primero las funciones con `rg "def completar_elemento_actual\|def confirmar_documentacion_base\|def actualizar_datos_expediente\|def actualizar_datos_taller" agent/tools/` para localizar las líneas exactas.
4. **Para F-2**, añade las secciones al **final** de cada archivo Markdown, después del último bloque existente, separadas por `---`.
5. **No modifiques** `_extract_context_from_tool()` — solo trabaja con el campo `message` en los returns de las tools y con el bucle de tool calls para F-3.
6. **Loguea antes de implementar**: Haz un `git diff` al finalizar cada fase para confirmar que solo se han tocado los archivos del alcance.

---

*Documento generado por architect. Pendiente de aprobación antes de iniciar implementación.*
