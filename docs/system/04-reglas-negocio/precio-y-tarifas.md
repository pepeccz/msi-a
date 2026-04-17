---
titulo: Cálculo de precio y tarifas
ambito: reglas-negocio
ultima_verificacion_commit: a54d35c
ultima_verificacion_fecha: 2026-04-17
---

# Cálculo de precio y tarifas

## Resumen

El precio de una homologación se calcula mediante fórmula: **base (tier) + variación por cantidad de elementos + servicios adicionales + IVA (siempre)**. La tarifa se define por **tier** (T1 a T6) en la categoría (ej. `motos-part`), cada tier tiene `price` (EUR sin IVA), y se clasifica automáticamente según keywords que el cliente menciona (AI-driven vía `classification_rules` JSON en cada tier).

Una vez identificados los elementos, se llama `calcular_tarifa_con_elementos()` con `skip_validation=True`, se devuelve precio final + URLs de imágenes ejemplo, y ese precio se comunica al cliente. Cambios posteriores (agregar elementos) disparan recálculo automático, y la diferencia se comunica explícitamente.

## Escenarios

### 1. Cálculo simple — 1 elemento, 1 tier
- CUANDO el cliente describe "escape de moto" → el bot identifica `code=ESCAPE`, categoría `motos-part`, aplica T3 (por keywords)
- ENTONCES el service calcula: `T3.price = 245€` + IVA (245 × 1.21 = 296.45€), devuelve precio + imágenes de escape
- RESULTADO: *"El presupuesto es 245€ +IVA."*

### 2. Multi-elemento (base + acumulativo)
- CUANDO el cliente añade "escape + manillar" después del precio anterior
- ENTONCES: escape sigue en T3, manillar también T3 (mismo tier). Los elementos dentro del mismo tier no multiplican precio. Cálculo: `T3.price = 245€` +IVA
- RESULTADO: *"Al añadir manillar, sigues en T3: 245€ +IVA"* (o si pasa a T4, entonces sube).

### 3. Tier escalation por cantidad
- CUANDO el cliente acumula 3 elementos: escape (T3), carenado (T4), asiento (T4)
- ENTONCES se selecciona T4 (el tier máximo requerido). `T4.price = 380€` +IVA = 459.80€
- RESULTADO: *"Con estos cambios, necesitas Tier 4: 380€ +IVA."*

### 4. Servicio adicional (certificado de taller)
- CUANDO el cliente dice "Necesito certificado de instalación profesional"
- ENTONCES el bot ofrece `AdditionalService` con `code=CERT_TALLER, price=50€`. Cálculo final: `T3 (245€) + CERT_TALLER (50€) = 295€` + IVA = 356.95€
- RESULTADO: *"Presupuesto ajustado: escape + certificado taller, 295€ +IVA."*

### 5. Tier base vs tier premium (upgrade forzado)
- CUANDO el cliente está en T1 (solo 1 elemento permitido) e intenta agregar un segundo
- ENTONCES el service detecta constraint violated, escala a T2 (más capacidad, más caro). Cálculo: `T2.price = 180€` + IVA
- RESULTADO: *"Necesitás Tier 2 para 2 elementos: 180€ +IVA."*

### 6. Recálculo tras adición (diferencia delta)
- CUANDO el cliente había aceptado presupuesto T3=245€, luego añade otro elemento que lleva a T4
- ENTONCES el bot calcula delta: 380 - 245 = 135€ más
- RESULTADO: *"Al añadir {elemento}, sube de 245€ a 380€ +IVA (135€ más)."*

### 7. Tarifa inválida / slug inexistente
- CUANDO el cliente describe algo que no mapea a categoría (ej. "automático de coches" pero solo tenemos motos)
- ENTONCES `get_category_data()` retorna None. El bot responde: *"No tenemos esa categoría. ¿Qué te gustaría homologar?"*. NO se calcula precio (evita default o zero-price).

### 8. Inclusiones y merge aditivo
- CUANDO el tier tiene `TierElementInclusion` que hereda otro tier (ej. T3 hereda de T2)
- ENTONCES al calcular T3 se incluyen todos los elementos de T2 automáticamente. Cálculo: usa `T3.price` (una sola vez), elementos heredados se normalizan. Precio único, sin duplicación.

### 9. Skip validation post-ID (verdad operativa)
- CUANDO el bot identifica elementos y llama `calcular_tarifa(skip_validation=True)`
- ENTONCES el service salta validaciones estrictas de integridad (porque el LLM ya validó). Beneficio: respuesta rápida, confianza en el estado conversacional previo. Resultado: tarifa calculada en < 500ms.

### 10. IVA siempre — regla inquebrantable
- CUANDO sea, el precio comunicado al cliente es SIEMPRE con IVA
- ENTONCES: `final_price = base_price × 1.21` (España, IVA = 21%). El bot siempre dice "€ +IVA", nunca oculta el IVA.

### 11. Validez temporal del presupuesto — 30 días
- CUANDO el bot comunica cualquier precio al cliente (sea primera vez en PRICING, sea recálculo en POST_PRICE tras añadir o quitar elementos)
- ENTONCES el mensaje incluye al final, en línea separada, la frase exacta: *"Precios válidos por 30 días."*
- RESULTADO: cliente ve claramente el timeframe de validez antes de decidir.

## Reglas duras

1. **IVA siempre incluido en el comunicado final**: fórmula `precio_final = tier.price × 1.21`. Nunca comunicar precio sin "+IVA" suffix. Configurable en settings (hoy 1.21).

2. **Skip validation post-ID = operativa post-identificación**: una vez que `element_codes` están rellenados vía identificación, `calcular_tarifa(..., skip_validation=True)`. Evita re-validar elementos que el LLM ya certificó.

3. **Tarifa calculada = fuente de verdad de códigos (RC-2b)**: cuando `calcular_tarifa()` devuelve, sus codes en la response SOBRESCRIBEN `mode_context.element_codes` (sincronización). Garantiza normalización.

4. **Merge aditivo de elementos (RC-2a)**: al agregar elemento post-precio: NO reemplazar codes, UNIÓN. Ejemplo: `["ESCAPE"] + ["MANILLAR"] = ["ESCAPE", "MANILLAR"]`.

5. **Inclusiones normalizan automáticamente**: si T3 hereda T2, el precio es `T3.price` UNA sola vez, no suma T2+T3.

6. **Tier se selecciona por max requerido**: si necesitás T3 + T4 elementos, usá T4 (el superior).

7. **Servicios adicionales suman linealmente**: cada servicio es +X€, luego se suma al tier base antes de IVA.

8. **UUIDs v5 determinísticos en seeds**: tiers, elementos y servicios usan UUID v5 con namespace fijo para idempotencia de seed.

9. **Soft delete `is_active=False`**: tiers/elementos inactivos no aparecen en cálculos (`WHERE is_active=True`).

10. **Redis cache 5min en categorías/tarifas**: lecturas frecuentes cacheadas; mutaciones invalidan key automáticamente.

11. **Validez 30 días obligatoria en toda comunicación de precio**: cada vez que se comunica un precio (primera vez o recálculo), DEBE incluirse al final en línea separada la frase *"Precios válidos por 30 días."*. Sin excepciones. Protege al negocio de reclamos por cambios de tarifa cuando el cliente demora su decisión. **No aplica** a respuestas que referencian un precio previo sin re-comunicarlo (ej. *"¿cuánto era?"* → *"era 410€ +IVA"* no necesita el disclaimer de nuevo).

## Mapeo al código

- `agent/services/tarifa_service.py:45-300+` — clase `TarifaService`, métodos: `get_active_categories()`, `get_supported_categories_for_client()`, `get_category_data()`, `_fetch_category_from_db()`. Redis caching con TTL=300s.
- `agent/tools/tarifa_tools.py` — tools `listar_categorias`, `listar_tarifas`, `obtener_servicios_adicionales`. Validación de slug, manejo de errores.
- `agent/tools/element_tools.py` — `calcular_tarifa_con_elementos()` tool, Pydantic schema con `skip_validation`, devuelve `{"success", "precio", "imagenes_url", "_state_update"}`.
- `database/models.py` — `VehicleCategory`, `TariffTier` (code, price Numeric, classification_rules JSONB, min/max_elements), `AdditionalService` (code, price, category_id FK optional), `TierElementInclusion` (FK tier + FK element OR FK included_tier para herencia).
- `database/seeds/data/motos_part.py` — Seed data: TIERS dict con T1-T6, ELEMENTS list, classification_rules.
- `database/models.py` — `DraftQuote`: tabla que cachea el presupuesto actual (conversation_id, tier_id, precio_final), fire-and-forget write post `calcular_tarifa`.
- Fórmula IVA: `final = base * Decimal("1.21")` (settings IVA_RATE configurable).
- `agent/prompts/modes/pre_expediente_pricing.md` — sección `<rules>`: directiva de validez 30 días al LLM en fase PRICING.
- `agent/prompts/modes/pre_expediente_post_price.md` — sección `<rules>`: directiva de validez 30 días al LLM en caso de recálculo post-adición.

## Fuera de alcance

- Impuestos por región (hoy solo ES IVA 21%)
- Descuentos / promociones (no implementados)
- Splits de pago (todo de una sola vez)
- Historial de cambios de tarifas (audit log existe pero no versionado por fecha)
