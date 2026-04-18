---
titulo: Prompts de PRE_EXPEDIENTE
ambito: agente
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Prompts de PRE_EXPEDIENTE

## Resumen

El agente carga prompts de texto dinámicamente según el modo activo y la fase interna. En PRE_EXPEDIENTE se cargan **siempre** el prompt core (`core.md`) más **exactamente uno** de los tres prompts de fase (DISCOVERY / PRICING / POST_PRICE). El sistema no permite mezclar dos prompts de fase al mismo tiempo.

La selección de fase es automática, basada en el contenido de `mode_context`. El LLM **no sabe** explícitamente en qué fase está — solo ve el prompt de esa fase como su guía.

## Escenarios

### Primer turno, cliente nuevo
- CUANDO el state es fresco (sin elementos, sin precio)
- ENTONCES el loader selecciona `pre_expediente_discovery.md` + `core.md` + el bloque especial de "🚨 PRIMERA INTERACCIÓN" que obliga a incluir la identificación EU AI Act.

### Ya hay elementos pero no precio
- CUANDO `element_codes` no vacío y `precio_comunicado=False`
- ENTONCES el loader selecciona `pre_expediente_pricing.md` + `core.md`. Las CTAs 3 y 4 están disponibles, las 1/2/5 no.

### Precio ya comunicado
- CUANDO `precio_comunicado=True`
- ENTONCES el loader selecciona `pre_expediente_post_price.md` + `core.md`. Las CTAs 4 (refresco) y 5 están disponibles.

### DraftQuote recuperado
- CUANDO existe un DraftQuote activo al empezar el turno
- ENTONCES los campos `draft_*` se inyectan en `mode_context` antes del render del prompt, y el prompt de fase los ve como parte de su contexto sin necesidad de llamar tools.

## Reglas duras

1. **Siempre exactamente un prompt de fase**. El loader selecciona uno de los tres — nunca dos ni cero.
2. **`core.md` siempre se carga**. Es la identidad, voz, reglas transversales (EU AI Act, precio antes que imágenes, etc.).
3. **Identidad EU AI Act en primer turno**. El bloque `🚨 PRIMERA INTERACCIÓN` solo aparece si `_is_first_interaction=True` en mode_context.
4. **Las 5 CTAs canónicas son inmutables** dentro de los prompts. Cualquier cambio a una CTA es un cambio de spec: modifica [`../flujos/pre-expediente/flujo.md`](../flujos/pre-expediente/flujo.md) → modifica el prompt.
5. **Las CTAs por fase están restringidas**: no todas las CTAs están disponibles en todas las fases (ver tabla abajo).
6. **Ningún prompt de fase duplica lo que está en `core.md`**. Si un concepto está en core, no se repite.

## Catálogo de prompts

### `core.md` (siempre cargado)
**Rol**: identidad del bot, EU AI Act compliance, modelo de ejecución, seguridad, principios de conversación, voz, formato de mensajes, reglas de precio, reglas de fotos, criterios de escalado.

**Mapeo**: `agent/prompts/core.md:1-111`

### `pre_expediente_discovery.md`
**Rol**: guía de comportamiento en fase DISCOVERY — sin elementos identificados. Incluye: inferencia de categoría, presentación de documentación, routing de intenciones, CTAs 1 y 2, comportamiento de nudge suave.

**Cuándo se carga**: `element_codes` vacío.

**Mapeo**: `agent/prompts/modes/pre_expediente_discovery.md:1-101`

### `pre_expediente_pricing.md`
**Rol**: guía en fase PRICING — elementos identificados, precio por comunicar. Incluye: reglas de resolución de variantes, confirmación multi-elemento, timing del cálculo de tarifa, formato de comunicación del precio, excepción de imágenes-antes-de-precio, CTAs 3 y 4.

**Cuándo se carga**: `element_codes` no vacío Y `precio_comunicado=False`.

**Mapeo**: `agent/prompts/modes/pre_expediente_pricing.md:1-81`

### `pre_expediente_post_price.md`
**Rol**: guía en fase POST_PRICE — precio ya comunicado. Incluye: separación de responsabilidades (qué sigue en PRE vs qué pasa a EXPEDIENTE), manejo de imágenes, rama de expedición, añadir/quitar elementos, edge cases, CTAs 4 y 5.

**Cuándo se carga**: `precio_comunicado=True`.

**Mapeo**: `agent/prompts/modes/pre_expediente_post_price.md:1-97`

## Matriz fase × CTA

|                  | CTA 1 | CTA 2 | CTA 3 | CTA 4 | CTA 5 |
|------------------|-------|-------|-------|-------|-------|
| **DISCOVERY**    | ✅    | ✅    | ❌    | ❌    | ❌    |
| **PRICING**      | ❌    | ❌    | ✅    | ✅    | ❌    |
| **POST_PRICE**   | ❌    | ❌    | ❌    | ✅*   | ✅    |

\* En POST_PRICE la CTA 4 se refresca, no se emite por primera vez.

## Assembly del prompt final

```
┌─────────────────────────────────────┐
│  core.md                            │  ← siempre
├─────────────────────────────────────┤
│  [🚨 PRIMERA INTERACCIÓN si aplica] │  ← solo 1er turno
├─────────────────────────────────────┤
│  pre_expediente_<FASE>.md           │  ← uno de los 3
├─────────────────────────────────────┤
│  mode_context (rendered)            │  ← state + draft_* si aplica
└─────────────────────────────────────┘
```

Formato final es un mensaje de `SystemMessage` que se antepone a los mensajes del historial de conversación antes de llamar al LLM.

## Mapeo al código

- `agent/prompts/loader.py:107-172` — `assemble_system_prompt` arma el bloque completo
- `agent/prompts/loader.py:49-61` — `_resolve_mode_key` selecciona la fase
- `agent/prompts/loader.py:180-196` — inyección del bloque "🚨 PRIMERA INTERACCIÓN"
- `agent/prompts/loader.py:227-241` — `format_mode_context` renderiza el state
- `agent/prompts/core.md` — contenido del prompt core
- `agent/prompts/modes/pre_expediente_discovery.md` — fase DISCOVERY
- `agent/prompts/modes/pre_expediente_pricing.md` — fase PRICING
- `agent/prompts/modes/pre_expediente_post_price.md` — fase POST_PRICE
- `agent/prompts/prompt_lint.py` — tests estructurales que validan presencia de CTAs canónicas y ausencia de patrones prohibidos

## Fuera de alcance

- `agent/prompts/modes/expediente_*.md` — prompts de EXPEDIENTE, scope distinto
- `agent/prompts/calculator_base.py` — calculadora de templates, infraestructura del loader (tocar solo si se cambia la mecánica de assembly)
- Cambiar la estructura de secciones canónicas dentro de los prompts sin actualizar [`../flujos/pre-expediente/flujo.md`](../flujos/pre-expediente/flujo.md) — los escenarios y reglas duras de ese archivo son la fuente de verdad; los prompts deben seguirlos, no al revés
