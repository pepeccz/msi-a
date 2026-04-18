---
titulo: DraftQuote — presupuesto borrador, validez y rehidratación
ambito: core
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# DraftQuote — presupuesto borrador, validez y rehidratación

## Resumen

`DraftQuote` es la entidad que persiste el presupuesto calculado durante PRE_EXPEDIENTE antes de que el cliente lo confirme. Se crea o actualiza automáticamente cada vez que el agente llama a `calcular_tarifa_con_elementos()`, almacenando el tier, el precio final con IVA, y los elementos confirmados. Solo puede existir un `DraftQuote` activo por conversación a la vez: al calcular uno nuevo, el anterior se desactiva (`is_active=False`).

Su razón de existir es la continuidad de sesión: si el cliente cierra WhatsApp y vuelve horas o días después, el agente carga el `DraftQuote` activo y rehidrata el contexto de precio sin pedirle al cliente que repita su consulta. La validez del presupuesto es de 30 días desde la última comunicación del precio.

## Escenarios

### Escenario 1 — Creación automática al calcular tarifa
CUANDO el agente llama a `calcular_tarifa_con_elementos()` con los elementos identificados
ENTONCES `_upsert_draft_quote()` crea o actualiza el `DraftQuote` activo para esa conversación: se registran `tier_id`, `precio_final`, `element_codes`, `categoria_slug`, y `calculated_at`. Si había un `DraftQuote` activo previo, se setea `is_active=False` antes de insertar el nuevo.

### Escenario 2 — Rehidratación al retorno del cliente
CUANDO el cliente vuelve a escribir después de horas o días y el checkpoint Redis ya no tiene el precio en `mode_context`
ENTONCES `_load_active_draft_quote_into_context()` consulta DB por el `DraftQuote` activo para esa `conversation_id`, lo inyecta en `mode_context` (campos: `precio_comunicado`, `tarifa_calculada`, `element_codes`, `categoria_slug`), y el agente puede continuar la conversación de precio sin pedir al cliente que repita su consulta.

### Escenario 3 — Recálculo tras agregar elemento
CUANDO el cliente ya tiene un presupuesto y agrega un elemento nuevo en PRE_EXPEDIENTE_POST_PRICE
ENTONCES el agente llama nuevamente a `calcular_tarifa_con_elementos()` con los elementos acumulados (merge aditivo). Se crea un nuevo `DraftQuote`, el anterior se desactiva. El mensaje al cliente incluye el delta de precio: "Al añadir {elemento}, sube de {precio anterior} a {nuevo precio} +IVA."

### Escenario 4 — Validez de 30 días
CUANDO el cliente consulta el presupuesto más de 30 días después de que fue comunicado
ENTONCES el `DraftQuote` sigue existiendo en DB pero el agente advierte que el presupuesto puede no estar vigente y ofrece recalcular con las tarifas actuales.

### Escenario 5 — Confirmación del presupuesto (consumo del DraftQuote)
CUANDO el cliente confirma el presupuesto
ENTONCES la herramienta `confirmar_presupuesto` lee el `DraftQuote` activo para heredar los datos al `Case` que se crea en EXPEDIENTE. El `DraftQuote` no se borra; queda con `is_active=False` tras la creación del Case como registro histórico.

### Escenario 6 — Múltiples recálculos en la misma sesión
CUANDO el cliente agrega y quita elementos varias veces en la misma conversación
ENTONCES cada llamada a `calcular_tarifa_con_elementos()` desactiva el `DraftQuote` anterior y crea uno nuevo. Solo el más reciente tiene `is_active=True`. El historial de drafts queda en DB para trazabilidad.

## Reglas duras

1. **Un solo `DraftQuote` activo por conversación**: `_upsert_draft_quote()` desactiva los previos con `is_active=False` antes de insertar el nuevo. Es invariante.
2. **El `DraftQuote` no es fuente de verdad para finalización**: cuando el cliente confirma y se crea el `Case`, la herramienta `finalizar_expediente` lee de `Case` en DB, no del `DraftQuote`. El DraftQuote sirve para rehidratación de contexto en PRE_EXPEDIENTE, no para el cierre formal.
3. **Validez comunicada = 30 días**: toda comunicación de precio incluye al final la frase "Precios válidos por 30 días." El `DraftQuote` en DB no tiene fecha de expiración técnica; la validez es una regla de negocio comunicada al cliente.
4. **Merge aditivo de elementos**: al recalcular, los `element_codes` del nuevo `DraftQuote` son la unión de los anteriores más el nuevo. No se reemplaza la lista, se acumula.

## Mapeo al código

- `agent/tools/draft_quote_service.py:47-108` — `_upsert_draft_quote()`, `_deactivate_draft_quote()`, `_load_active_draft_quote_into_context()`.
- `database/models.py` — modelo `DraftQuote` (id UUID, conversation_id FK → ConversationHistory, tier_id FK, precio_final Numeric, element_codes JSONB, categoria_slug, is_active, calculated_at).
- `agent/tools/element_tools.py` — `calcular_tarifa_con_elementos()` — llama a `_upsert_draft_quote()` internamente tras calcular.
- `agent/state/conversation_state.py` — campo `mode_context.tarifa_calculada` y `mode_context.precio_comunicado` se hidratan desde `DraftQuote` al retomar sesión.

## Fuera de alcance

- Cálculo de la tarifa en sí (→ `../tarifas/calculo.md`).
- Ciclo de vida del Case que nace a partir del DraftQuote confirmado (→ `../expedientes/ciclo-de-vida.md`).
- Historial de presupuestos para el operador en el panel (no existe aún).
