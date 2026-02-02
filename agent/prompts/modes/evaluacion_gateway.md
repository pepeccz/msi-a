# MODO: EVALUACION GATEWAY

Punto de decision: el usuario confirma si quiere iniciar expediente formal.
Este nodo NO usa LLM — es un clasificador por patrones rapido y predecible.

## Objetivo

Obtener una respuesta clara SI/NO del usuario sobre iniciar el expediente.
Este modo es BLOQUEANTE — no se puede salir sin responder.

## Comportamiento

1. Primera invocacion: Presentar resumen del presupuesto + preguntar
2. Invocaciones siguientes: Clasificar respuesta como SI / NO / AMBIGUO

## Herramientas Disponibles

Ninguna. Este nodo usa clasificacion por patrones, no LLM.

## Respuestas Esperadas

### SI (→ EXPEDIENTE_MODE):
- "si", "dale", "vale", "adelante", "perfecto", "ok", "venga", "claro", "genial", "vamos", "por supuesto", "correcto"

### NO (→ PRESUPUESTO_MODE):
- "no", "todavia no", "mejor no", "lo pienso", "ahora no", "luego", "despues", "paso", "cancel"

### AMBIGUO (→ Reprompt, max 2 intentos):
- Cualquier otra cosa que no sea claramente SI o NO
- Despues de 2 intentos ambiguos → volver a PRESUPUESTO_MODE

## Reglas CRITICAS

1. **NO iniciar expediente sin confirmacion explicita**
2. **NO ofrecer opciones adicionales** — es SI o NO
3. **NO recalcular precio** — ya esta calculado
4. **Maximo 2 reintentos** antes de devolver a presupuesto
5. **Preservar contexto completo** en todas las transiciones

## Transiciones

- SI → EXPEDIENTE_MODE (preservar: categoria_slug, element_codes, precio_exacto, tarifa_calculada, vehiculo)
- NO → PRESUPUESTO_MODE (preservar todo el contexto)
- 2x AMBIGUO → PRESUPUESTO_MODE (preservar todo el contexto)
