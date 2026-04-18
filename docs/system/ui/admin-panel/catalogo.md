---
titulo: Panel admin — catálogo
ambito: ui
ultima_verificacion_commit:
ultima_verificacion_fecha: 2026-04-17
---

# Panel admin — catálogo

## Resumen

El área de catálogo es donde el admin gestiona toda la estructura de precios y homologación: categorías de vehículos, tiers de precio (básico/premium), elementos homologables con sus variantes, documentación requerida y warnings asociados. Es el área más compleja del panel por la profundidad del modelo de datos — un elemento puede tener imágenes, variantes, campos requeridos y múltiples warnings.

## Escenarios

### 4. Admin crea una nueva categoría de tarifas
- CUANDO hace click en **Reformas** → botón "Crear Categoría" (abre un Dialog)
- ENTONCES form con campos: nombre, tipo de vehículo (auto/moto/otro), descripción. Click "Guardar" → toast verde "Creado correctamente" → dialog cierra → tabla se refresca.

### 5. Admin edita una tarifa existente
- CUANDO hace click en categoría en la tabla de Reformas → abre `/reformas/[categoryId]`
- ENTONCES ve secciones desplegables: Tiers de precio (básico/premium), Elementos incluidos en cada tier, Documentación requerida, Servicios adicionales. Click "Editar" en cada sección abre un Dialog. Guardar → toast → refresco.

### 6. Admin gestiona elementos del catálogo
- CUANDO hace click en **Elementos** → ver catálogo plano O jerárquico (toggle)
- ENTONCES tabla con elemento, categoría, precio. Click "Nuevo Elemento" abre Dialog con form. Click fila → `/elementos/[id]` con editor completo (imágenes, variantes, campos requeridos, warnings asociados). Save → toast.

### 7. Admin asigna o revoca warnings / requisitos
- CUANDO abre `/advertencias` o desde `/elementos/[id]` botón "Gestionar Warnings"
- ENTONCES Dialog o página donde ve warnings (ej. "Faro debe tener fotos desde 3 ángulos"). Click "Crear Warning" form → CRUD estándar Dialog-based. Asocialos a elementos con checkboxes.

## Reglas duras

Ver "Reglas compartidas (aplican a todo el panel)" en [conversaciones.md](./conversaciones.md) para las 13 reglas base del panel.

Reglas propias de catálogo:

- El editor de `/elementos/[id]` es el componente más grande del panel (~1400 líneas). Cualquier cambio en él requiere atención especial a la gestión de estado local y la sincronización post-save.
- El sistema de warnings tiene asociación dual en base de datos (ver `../../core/documentacion-requerida/sistema-dual.md`). La UI debe operar sobre ambas tablas via el API — no asignar warnings solo desde la tabla de elementos.
- El toggle catálogo plano / jerárquico es puramente visual: no cambia qué datos se cargan, solo cómo se presentan.

## Mapeo al código

| Ruta | Archivo | Líneas | Qué hace |
|------|---------|--------|----------|
| `/reformas` | `admin-panel/src/app/(authenticated)/reformas/page.tsx` | 312 | Categorías agrupadas por vehículo |
| `/reformas/[categoryId]` | `admin-panel/src/app/(authenticated)/reformas/[categoryId]/page.tsx` | 910 | Editor tiers, elementos, docs |
| `/elementos` | `admin-panel/src/app/(authenticated)/elementos/page.tsx` | 726 | Catálogo elementos, create/delete |
| `/elementos/[id]` | `admin-panel/src/app/(authenticated)/elementos/[id]/page.tsx` | 1400+ | Editor grande: imágenes, variantes, warnings |

Hooks relevantes:

- `admin-panel/src/hooks/use-category-data.ts` — fetch categoría con tiers/elementos/docs

API client:

- `admin-panel/src/lib/api.ts` — `api.getVehicleCategories()`, `api.createElement()`, `api.updateElement()`, `api.getWarnings()`

## Fuera de alcance

- `agent/**` — lógica de uso del catálogo en tiempo de conversación
- `api/**` — endpoints de catálogo, validaciones de negocio
- `database/**` — modelos ORM de categorías, elementos, warnings, variantes
- `shared/**` — librerías compartidas
