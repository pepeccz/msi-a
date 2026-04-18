---
titulo: Catálogo — categorías, tiers, elementos, variantes
ambito: core
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Catálogos de negocio

## Resumen

Los **catálogos** son repositorios maestros de datos de negocio: qué vehículos se pueden homologar (categorías), qué elementos dentro de cada categoría (escape, manillar, etc.), variantes de elementos (colores, tamaños), tiers de precios, y servicios adicionales. Todos residen en BD con **UUIDs v5 determinísticos** en seeds para idempotencia. **Soft-delete con `is_active=False`** preserva historial. Las slugs de categoría son únicas por `client_type` (ej. `motos-part` vs `motos-prof`). Las relaciones usan FK con `lazy="selectin"` para async correctness.

## Escenarios

### 1. Cliente consulta categorías disponibles
- CUANDO el cliente dice "¿Qué motos se pueden homologar?"
- ENTONCES `listar_categorias()` queries `SELECT * FROM vehicle_categories WHERE is_active=True AND client_type={ctx.client_type}`. Devuelve lista: `[motos-part, aseicars-part, ...]`. El bot renderiza: *"Podemos homologar motocicletas, autocaravanas y más"*.

### 2. Cliente describe elemento dentro de categoría
- CUANDO el cliente dice "Escape de moto"
- ENTONCES el sistema identifica: categoria=motos-part, element_code=ESCAPE. Query: `SELECT * FROM elements WHERE category_slug='motos-part' AND code='ESCAPE' AND is_active=True`. Si elemento tiene keywords=["escape", "tubo escape", "silenciador"], matched. Elemento resuelto, precio disponible.

### 3. Resolución de variante
- CUANDO elemento SUSPENSION tiene variantes (delantera, trasera, ambas). Cliente responde "trasera"
- ENTONCES el sistema selecciona: `variant_code=SUSPENSION_TRASERA, parent_id=SUSPENSION_UUID`. Variante resuelta, hereda datos del padre.

### 4. Oferta de servicio adicional
- CUANDO el cliente confirma presupuesto
- ENTONCES el bot ofrece: *"¿Necesitás servicios adicionales? (Certificado taller +50€, Urgente +100€)"*. Query: `SELECT * FROM additional_services WHERE category_id IS NULL OR category_id={cat_id} AND is_active=True`. Cliente: "Sí, urgente" → cálculo `base_price + urgente_service.price`.

### 5. Tier matching por clasificación
- CUANDO el cliente describe "Escape deportivo tuning"
- ENTONCES Tier T3 tiene `classification_rules.applies_if_any=["tuning", "racing", "deportivo"]`. Matcher en LLM detecta "tuning" → aplica T3. Tier correcto automáticamente.

### 6. Catálogo actualizado sin redeploy
- CUANDO el admin agrega un nuevo elemento vía panel
- ENTONCES INSERT → tabla `elements`, nuevo UUID generado, `is_active=True`. Próximo seed/cache-clear respeta el nuevo elemento. Agilidad, no redeploy por cada cambio de catálogo.

### 7. Soft delete de elemento obsoleto
- CUANDO el elemento "SEAT_ANTIGUO" ya no se homologa
- ENTONCES el admin soft-delete → `is_active=False`. Queries: `WHERE is_active=True` → el elemento desaparece. Historial preservado en BD (audit trail). Trazabilidad, reversible.

### 8. Relaciones FK con lazy="selectin"
- CUANDO el bot carga category motos-part
- ENTONCES ORM eagerly loads: tiers, elements, warnings, services vía selectinload. No N+1 queries, single async batch. Performance optimizado.

## Reglas duras

1. **UUIDs v5 determinísticos en seeds**: namespace `SEED_NAMESPACE`, combinado con `category:slug:element_code` → UUID fijo. Re-run seed = mismo UUID, upsert actualiza.

2. **Soft delete `is_active=False`**: no hard-delete. Setear `is_active=False`, preserva FK chain, historial.

3. **Slugs únicos por categoría + client_type**: constraint `UNIQUE(slug, client_type)` en `vehicle_categories`. Evita `motos-part` duplicado.

4. **FK con `lazy="selectin"` obligatorio**: async loader. Ningún `lazy="joined"` (no async compatible).

5. **`ondelete` FK policy explícita**: Categories → Tiers: CASCADE. Tiers → Elements: CASCADE. Preserva integridad.

6. **`is_active=True` default**: nuevos records siempre activos por defecto.

7. **`sort_order` numérico para UI**: categories y base docs usan `sort_order` para control visual (no alfabético).

8. **No hard-delete de seed data**: si seed intenta DELETE, debe ser `downgrade()` de migration (eso sí borra), nunca application-level DELETE.

## Mapeo al código

- `database/models.py` — Modelos: `VehicleCategory` (slug VARCHAR UNIQUE per client_type, name, client_type, is_active, sort_order, icon), `Element` (code, parent_id FK self-referential, variant_type, inherit_parent_data, keywords JSONB, is_active), `TariffTier` (code, price, min/max_elements, classification_rules JSONB), `AdditionalService` (code, price, category_id FK nullable), `TierElementInclusion` (tier_id, element_id OR included_tier_id para herencia).
- `database/seeds/data/motos_part.py`, `aseicars_prof.py`, etc. — Datos constantes, TypedDict definitions, CATEGORY/TIERS/ELEMENTS/SERVICES lists.
- `database/seeds/seed_utils.py` — `element_uuid(category_slug, element_code)` → deterministic UUID v5.
- `database/seeds/seeders/category.py` — `CategorySeeder` seedea category + tiers + warnings + services.
- `database/seeds/seeders/element.py` — `ElementSeeder` seedea elements + images + warnings (2-pass para parent resolution).
- `database/seeds/seeders/inclusion.py` — `InclusionSeeder` seedea relaciones tier-element desde `tier_mappings.py`.
- `agent/services/tarifa_service.py` — `TarifaService.get_active_categories()`, `get_category_data()` (eager loading).
- `agent/services/element_service.py` — Element queries, keyword matching.
- Redis cache keys: `tariffs:categories:{client_type}`, `tariffs:supported:{client_type}`, `tariffs:{category_slug}` (TTL 300s).

## Fuera de alcance

- Validación de elementos contra regulaciones externas (futura integración)
- Integración con proveedores de precios (futura)
- Replicación de catálogos a terceros (futura)
- Sincronización histórica desde legacy system (migration one-time)
