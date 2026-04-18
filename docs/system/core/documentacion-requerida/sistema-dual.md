---
titulo: Documentación requerida — sistema dual de warnings
ambito: core
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Documentación requerida por elemento — sistema de warnings

## Resumen

La documentación requerida se determina mediante **warnings asociados a elementos**, con **sistema dual**: `warnings.element_id` (inline, para el agente) + `element_warning_associations` (many-to-many, para el admin). Cada elemento puede tener N warnings (advertencias sobre documentación, validaciones, etc.); cuando el agente presenta un elemento al cliente, carga los warnings, los traduce a requerimientos de foto/documentación, y los presenta:

> *"Para {elemento}, necesitarás: fotos de frente y lado, certificado de origen."*

Los warnings viven en BD (soft-deleted con `is_active=False`), se seedean con cada categoría, y nunca se duplican en múltiples turnos (una sola advertencia por elemento por conversación).

## Escenarios

### 1. Elemento con documentación estándar
- CUANDO el cliente identifica "Escape" en motos-part
- ENTONCES el bot consulta warnings para `element_id=ESCAPE_UUID`. Warnings encontrados: `[ESCAPE_MUST_BE_HOMOLOG, ESCAPE_PHOTO_REQUIREMENT]` (2 warnings). El bot renderiza: *"Para el escape necesitarás: (1) Foto de frente, (2) Acta de homologación"* (traduce codes a mensajes)

### 2. Elemento con warnings específicos (trigger conditions)
- CUANDO el cliente especifica "Escape tuning" (keywords=["escape", "tuning"])
- ENTONCES el bot carga warnings DONDE `trigger_conditions.keywords` contiene "tuning". Warning adicional: `ESCAPE_TUNING_CERT` (requiere certificado de taller especializado). El bot renderiza: *"...además, por ser tuning, necesitarás certificado de taller autorizado"*

### 3. Elemento heredando warnings del padre
- CUANDO el cliente describe "Suspensión delantera" (parent_element_id=SUSPENSION_ID)
- ENTONCES el bot carga warnings de SUSPENSION_ID + warnings específicos de SUSPENSION_DELANTERA. Warnings heredados: `[SUSPENSION_PHOTO_x2_ANGLES, SUSPENSION_COMPLIANCE_DOC]`. Se presenta jerarquía clara, no duplica.

### 4. Presentación al cliente (flujo conversacional)
- CUANDO el bot entra a EXPEDIENTE mode, sub-modo `collect_element_data` para ESCAPE
- ENTONCES: *"¿Tenés las fotos del escape? Recordá que necesitás: frente, lado izquierdo, lado derecho, y acta de homologación."* Cliente envía 4 imágenes. Bot valida: 4 imágenes OK, documento texto/PDF OK. Element completado, pasa a siguiente.

### 5. Modificación de warnings (admin)
- CUANDO el admin en el panel actualiza warning `ESCAPE_MUST_BE_HOMOLOG` message
- ENTONCES el cambio persiste en BD (update `warnings.message`). Próximas conversaciones ven el mensaje nuevo. Warnings viejos (deleted con `is_active=False`) NO aparecen.

### 6. Dual system sync post-seed
- CUANDO se corre `run_all_seeds.py` para motos-part
- ENTONCES `ElementSeeder` crea: (1) Warning con element_id inline, (2) ElementWarningAssociation many-to-many. Ambas apuntan al mismo Warning ID, manteniendo sincronización. Script `verify_warning_sync.py` valida: inline count == association count.

### 7. Prohibición de duplicar advertencia en múltiples turnos
- CUANDO el bot entra a elemento ESCAPE, muestra warning "foto de frente"
- CLIENTE luego escribe "¿necesito foto de lado?"
- ENTONCES el bot NO repite warning. Referencia el previo: *"Ya lo mencioné: necesitás frente, lado izquierdo, lado derecho. Subí las 3 fotos."*. Conversación limpia, sin redundancia.

### 8. Warnings globales vs scoped
- CUANDO warning tiene `category_id=NULL, tier_id=NULL, element_id=NULL` → GLOBAL. Ejemplo: "Toda homologación requiere DNI/NIF del cliente"
- ENTONCES el bot lo presenta al inicio, no por elemento. Warnings con `category_id=motos-part_id` → solo para esa categoría. Scoping correcto, no spam global.

## Reglas duras

1. **Dual existence MUST hold**: cada warning asociado a un elemento DEBE existir en BOTH `warnings.element_id` AND `element_warning_associations`. El seed lo verifica; query puede usar cualquiera.

2. **Fuente única de verdad = BD**: no hardcodear warnings en prompts. Siempre load de BD en el turno. Cambios del admin son inmediatos.

3. **Prohibido duplicar advertencias en múltiples turnos**: una sola presentación por warning en una conversación (rastrear vía state o context).

4. **`is_active=False` = soft delete**: warnings viejos no se queryean. Para borrar del UI, setear `is_active=False`, no DELETE.

5. **`trigger_conditions` JSONB = filtro dinámico**: si warning tiene `trigger_conditions.keywords=["tuning"]`, solo se muestra si el cliente menciona "tuning".

6. **Scoping XOR check**: warning tiene EXACTAMENTE ONE de: `category_id`, `tier_id`, o `element_id` (DB constraint CHECK).

7. **UUIDs v5 determinísticos en seeds**: warning codes mapeados a UUIDs fijos para idempotencia.

8. **Lazy load con selectinload**: cuando cargás un elemento, eager load de warnings (async selectinload).

## Mapeo al código

- `database/models.py` — Modelos `Warning` (id, code, message, severity, `category_id/tier_id/element_id` XOR, `trigger_conditions` JSONB, `is_active`), `ElementWarningAssociation` (`element_id` FK, `warning_id` FK, `show_condition`, `threshold_quantity`, unique constraint element_id+warning_id).
- `database/seeds/seeders/element.py` — `ElementSeeder._seed_warnings()` crea inline Warning + ElementWarningAssociation en dos pasos.
- `database/seeds/verify_warning_sync.py` — Script de validación post-seed, compara counts inline vs association.
- `agent/services/tarifa_service.py:248-257` — `get_category_data()` carga warnings globales + category-scoped.
- `agent/services/element_service.py` — `get_element_warnings()` queries `ElementWarningAssociation`, loads Warning message + conditions.
- `api/routes/elements.py` — Admin endpoints para CRUD de warnings, valida dual existence vía trigger.
- `agent/prompts/modes/expediente_*.md` — Prompts que presentan warnings al cliente, evita re-presentación.
- State tracking: `mode_context.warnings_shown_codes` (set de codes ya presentados) previene dup.

## Fuera de alcance

- Lógica de validación de foto (es `agent/services/image_handling.py`)
- Aprobación manual de fotos (`agent/modes/expediente_nodes.py`)
- Generación de documentos finales (`api/routes/cases.py`)
- Notificación a cliente si falta algo (`agent/modes/expediente_nodes.py`)
