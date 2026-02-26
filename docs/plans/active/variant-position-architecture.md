# Plan: Campo `variant_position` — Arquitectura de Presentación Canónica de Variantes

**Creado por**: architect  
**Fecha**: 2026-02-21  
**Estado**: PENDIENTE DE APROBACIÓN  
**Rama sugerida**: `feature/variant-position`

---

## Resumen Ejecutivo

Se añade el campo `variant_position: int | None` a la tabla `elements` para establecer un **contrato explícito** entre el orden en que el LLM presenta las opciones de variante al usuario y el mapeo posicional ("A", "B", "C") en `seleccionar_variante_por_respuesta`. La columna es independiente de `sort_order` (display en admin), se asigna automáticamente al crear variantes desde la API, y reemplaza la dependencia implícita de `sort_order` en la Fase 0 posicional del tool. Adicionalmente, se corrigen 6 inconsistencias de datos detectadas en BD.

---

## Tabla de Archivos a Modificar

| # | Archivo | Tipo de cambio | Riesgo |
|---|---------|----------------|--------|
| 1 | `database/alembic/versions/036_add_variant_position.py` | **Nuevo** | Medio |
| 2 | `database/models.py` | Modificado (1 campo) | Bajo |
| 3 | `database/seeds/data/common.py` | Modificado (1 campo en TypedDict) | Bajo |
| 4 | `database/seeds/seeders/element.py` | Modificado (poblar `variant_position`) | Bajo |
| 5 | `database/seeds/data/motos_part.py` | Modificado (añadir `variant_position` a variantes) | Bajo |
| 6 | `database/seeds/data/aseicars_prof.py` | Modificado (añadir `variant_position` a variantes) | Bajo |
| 7 | `agent/services/element_service.py` | Modificado (`get_element_variants`, ORDER BY, caché) | Medio |
| 8 | `agent/tools/element_tools.py` (tool `seleccionar_variante_por_respuesta`) | Modificado (Fase 0 posicional) | Medio |
| 9 | `agent/tools/element_tools.py` (tool `identificar_y_resolver_elementos`) | Modificado (incluir `variant_position` en `preguntas_variantes`) | Bajo |
| 10 | `api/routes/elements.py` | Modificado (auto-asignación en create, endpoint reorder) | Medio |
| 11 | `api/models/element.py` | Modificado (excluir `variant_position` de `ElementUpdate`) | Bajo |
| 12 | `agent/prompts/modes/presupuesto_mode.md` | Modificado (instrucción de formato A/B/C) | Bajo |
| 13 | `tests/test_variant_position_migration.py` | **Nuevo** | Bajo |
| 14 | `tests/test_variant_response_positional.py` | Modificado (actualizar a `variant_position`) | Bajo |

---

## Estimación de Riesgo por Sección

| Sección | Componente | Riesgo | Justificación |
|---------|-----------|--------|---------------|
| 1 | Migración BD | **Medio** | Afecta tabla `elements` con 106 filas. La columna es NULL=permitido; no rompe nada si falla a mitad |
| 2 | Modelo SQLAlchemy | **Bajo** | Un campo nullable, sin relaciones, sin lógica |
| 3 | Auto-asignación API | **Medio** | Introduce lógica transaccional. Un bug puede crear `variant_position=NULL` en variantes nuevas |
| 4 | Admin panel | **Bajo** | Cambios de UI no funcionales; el campo no aparece editable |
| 5 | `get_element_variants()` | **Medio** | Cambiar ORDER BY puede alterar el orden de variantes ya funcionales si `variant_position` queda NULL en alguna |
| 6 | Tool `identificar_y_resolver_elementos` | **Bajo** | Solo añade campo al dict de salida |
| 7 | Tool `seleccionar_variante_por_respuesta` | **Alto** | Reemplaza lógica posicional existente. Un bug rompe todas las respuestas A/B/C del agente |
| 8 | Prompt | **Bajo** | Solo añade una instrucción opcional |
| 9 | Seeds | **Bajo** | Idempotentes; corrigen inconsistencias sin borrar datos |
| 10 | Tests | **Bajo** | Nuevos tests, no afectan producción |
| 11 | Corrección inconsistencias | **Medio** | CAMBIO_CLASIF huérfano: borrar 2 registros de BD activa |

---

## Sección 1: Migración de BD

**Archivo**: `database/alembic/versions/036_add_variant_position.py`

### Cabecera y metadatos

```python
"""Add variant_position to elements for canonical presentation order

Revision ID: 036_add_variant_position
Revises: 035_restructure_motos_elements
Create Date: 2026-02-21 00:00:00.000000

Adds variant_position (INT NULL) to elements table.
Only used on child elements (parent_element_id IS NOT NULL).
Populated from relative sort_order rank among siblings.

Existing variants:
  - 37 variants across 13 parent elements
  - Populated via ROW_NUMBER() OVER (PARTITION BY parent_element_id ORDER BY sort_order)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "036_add_variant_position"
down_revision: Union[str, None] = "035_restructure_motos_elements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
```

### `upgrade()`

```python
def upgrade() -> None:
    # ── 1. Add column (nullable, no default) ──────────────────────────────
    op.add_column(
        "elements",
        sa.Column(
            "variant_position",
            sa.Integer(),
            nullable=True,
            comment=(
                "Canonical presentation order for this variant (1, 2, 3...). "
                "NULL for base elements. Independent of sort_order (which is for admin panel display). "
                "Used by agent to map positional responses (A→1, B→2, C→3)."
            ),
        ),
    )

    # ── 2. Populate for existing variants using ROW_NUMBER ─────────────────
    # Assigns 1,2,3... based on sort_order rank within siblings sharing the same parent.
    op.execute(sa.text("""
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY parent_element_id
                    ORDER BY sort_order ASC, code ASC
                ) AS pos
            FROM elements
            WHERE parent_element_id IS NOT NULL
              AND is_active = TRUE
        )
        UPDATE elements
        SET variant_position = ranked.pos
        FROM ranked
        WHERE elements.id = ranked.id
    """))

    # ── 3. Create index for efficient ORDER BY queries ─────────────────────
    op.create_index(
        op.f("ix_elements_variant_position"),
        "elements",
        ["parent_element_id", "variant_position"],
        unique=False,
    )
```

> **Nota sobre el ORDER BY de desempate**: Se usa `code ASC` como segundo criterio para que el resultado sea determinístico en casos donde dos hermanas tengan el mismo `sort_order`. En la práctica no ocurre, pero es una salvaguarda.

> **¿Incluir variantes `is_active=FALSE`?** No. Las variantes inactivas no se presentan al usuario y no deben ocupar posición. Si se reactivan, recibirán `variant_position=NULL` y la API las asignará al final en el próximo create/reorder.

### `downgrade()`

```python
def downgrade() -> None:
    # Nullify before dropping (for safety with constraints)
    op.execute(sa.text("""
        UPDATE elements SET variant_position = NULL
        WHERE parent_element_id IS NOT NULL
    """))
    op.drop_index(
        op.f("ix_elements_variant_position"),
        table_name="elements",
    )
    op.drop_column("elements", "variant_position")
```

### Verificación post-migración (SQL de diagnóstico, no ejecutar en prod sin supervisión)

```sql
-- Verificar que las 37 variantes activas tienen variant_position asignado
SELECT
    p.code AS parent_code,
    e.code AS variant_code,
    e.sort_order,
    e.variant_position
FROM elements e
JOIN elements p ON e.parent_element_id = p.id
WHERE e.is_active = TRUE
ORDER BY p.code, e.variant_position;

-- Verificar que ningún elemento base tiene variant_position
SELECT COUNT(*) FROM elements
WHERE parent_element_id IS NULL AND variant_position IS NOT NULL;
-- Esperado: 0
```

---

## Sección 2: Modelo SQLAlchemy

**Archivo**: `database/models.py` — clase `Element` (~línea 768, después de `multi_select_keywords`)

### Campo a añadir

```python
    variant_position: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment=(
            "Canonical presentation order for this variant when offered as options to the user "
            "(1=first option, 2=second, 3=third...). "
            "NULL for base elements (parent_element_id IS NULL). "
            "Independent of sort_order (admin panel display order). "
            "Set automatically by API when a variant is created. "
            "Used by agent to resolve positional responses: A→position=1, B→position=2, C→position=3."
        ),
    )
```

**Posición en la clase**: Insertar entre `multi_select_keywords` y `inherit_parent_data`, en el bloque de campos de variante:

```python
    # Hierarchy fields for variants/sub-elements
    parent_element_id: Mapped[uuid.UUID | None] = ...   # existente
    variant_type: Mapped[str | None] = ...               # existente
    variant_code: Mapped[str | None] = ...               # existente
    question_hint: Mapped[str | None] = ...              # existente
    multi_select_keywords: Mapped[list[str] | None] = ...# existente
    variant_position: Mapped[int | None] = mapped_column(# ← NUEVO
        Integer,
        nullable=True,
        comment="Canonical presentation order..."
    )
    # Inheritance control for child elements
    inherit_parent_data: Mapped[bool] = ...              # existente
```

---

## Sección 3: Auto-asignación en la API

**Archivo**: `api/routes/elements.py`

### 3.1 Endpoint `POST /api/admin/elements` — crear variante

En el handler `create_element` (~línea 232), **antes de** `element = Element(**data.model_dump())`, insertar:

```python
# ── Auto-assign variant_position if this is a variant ─────────────────────
if data.parent_element_id:
    # Get max variant_position among active siblings
    max_pos_result = await session.execute(
        select(func.max(Element.variant_position)).where(
            Element.parent_element_id == data.parent_element_id,
            Element.is_active == True,
        )
    )
    current_max: int | None = max_pos_result.scalar()
    data_dict = data.model_dump()
    data_dict["variant_position"] = (current_max or 0) + 1
else:
    data_dict = data.model_dump()
    data_dict["variant_position"] = None  # Base elements never have variant_position

element = Element(**data_dict)
```

> **Por qué `is_active=True` en el MAX**: No queremos que variantes inactivas "reserven" posiciones. Las posiciones son para las opciones que se presentan al usuario. Si se desactiva la variante 2 de 3, las posiciones quedan 1, 3 (gap aceptable). Se re-secuencian solo mediante el endpoint de reorder.

### 3.2 Endpoint nuevo: `PUT /api/admin/elements/{parent_id}/variants/reorder`

**Propósito**: Permite al admin reordenar variantes para cambiar qué opción es A, B, C.

```python
@router.put(
    "/elements/{parent_id}/variants/reorder",
    response_model=dict,
    summary="Reorder variants of a parent element",
    description=(
        "Sets variant_position for each variant according to the provided ordered list. "
        "The first element in the list gets position=1, the second position=2, etc. "
        "Only variants belonging to parent_id are accepted. "
        "All active variants of the parent must be included in the list."
    ),
)
async def reorder_variants(
    parent_id: UUID,
    variant_ids: list[UUID],  # Body: ordered list of variant element_ids
    _: AdminUser = Depends(get_current_user),
) -> dict:
    """
    Reorder variants of a parent element by assigning canonical variant_position.
    
    Body: JSON array of variant element IDs in desired order.
    Example: ["uuid-b", "uuid-a", "uuid-c"]
    → uuid-b gets variant_position=1 (option A)
    → uuid-a gets variant_position=2 (option B)
    → uuid-c gets variant_position=3 (option C)
    """
    async with get_async_session() as session:
        # 1. Verify parent exists
        parent = await session.get(Element, parent_id)
        if not parent:
            raise HTTPException(404, "Parent element not found")
        
        # 2. Get all active variants of parent
        result = await session.execute(
            select(Element).where(
                Element.parent_element_id == parent_id,
                Element.is_active == True,
            )
        )
        db_variants = result.scalars().all()
        db_variant_ids = {v.id for v in db_variants}
        
        # 3. Validate: all provided IDs must belong to this parent
        provided_ids = set(variant_ids)
        foreign_ids = provided_ids - db_variant_ids
        if foreign_ids:
            raise HTTPException(
                400,
                f"These IDs do not belong to parent {parent_id}: {foreign_ids}",
            )
        
        # 4. Validate: no duplicate IDs
        if len(variant_ids) != len(provided_ids):
            raise HTTPException(400, "Duplicate variant IDs in request")
        
        # 5. Update variant_position for each provided variant
        for pos, variant_id in enumerate(variant_ids, start=1):
            variant = next(v for v in db_variants if v.id == variant_id)
            variant.variant_position = pos
        
        # 6. Variants not in the list: push to the end (they keep their old position or get max+1)
        # These are active variants that the caller forgot to include — we don't hard-error,
        # but we do log a warning.
        missing_from_list = db_variant_ids - provided_ids
        if missing_from_list:
            logger.warning(
                "reorder_variants_incomplete_list",
                extra={
                    "parent_id": str(parent_id),
                    "missing_count": len(missing_from_list),
                    "missing_ids": [str(i) for i in missing_from_list],
                },
            )
            max_pos = len(variant_ids)
            for variant in db_variants:
                if variant.id in missing_from_list:
                    max_pos += 1
                    variant.variant_position = max_pos
        
        await session.commit()
        
        # Invalidate variants cache for this parent
        redis = get_redis_client()
        try:
            # Invalidate all variant cache keys for this parent
            await redis.delete(f"elements:variants:{parent.code}:{parent.category_id}")
            await redis.delete(f"elements:variants:{parent_id}:{parent.category_id}")
            await redis.delete(f"elements:category:{parent.category_id}:active=True")
            await redis.delete(f"elements:category:{parent.category_id}:active=False")
        except Exception as e:
            logger.warning(f"Cache invalidation failed after reorder: {e}")
        
        return {
            "success": True,
            "parent_id": str(parent_id),
            "reordered_count": len(variant_ids),
            "message": f"Variants reordered. {len(missing_from_list)} variants not in list were pushed to end.",
        }
```

**Pydantic schema** (en `api/models/element.py`):

```python
class VariantReorderRequest(BaseModel):
    """Request body for reordering variants."""
    variant_ids: list[UUID] = Field(
        ...,
        min_length=1,
        description="Ordered list of variant element IDs. First = position 1 (option A).",
    )
```

### 3.3 Decisión: ¿Re-numerar hermanas al eliminar una variante?

**Decisión: NO re-numerar.**

**Justificación**:
- Re-numerar en cascada al borrar requiere un lock de la tabla o race conditions con el agente que esté leyendo simultáneamente.
- Los gaps en la secuencia (1, 3 si se borra la 2) no son un problema funcional: el mapeo posicional del agente usa el campo `variant_position` del registro, no un índice de array.
- Si el admin quiere compactar, usa `PUT /variants/reorder`.
- Borrar una variante es raro (soft-delete preferido con `is_active=False`).

**Decisión: ¿Qué pasa cuando se cambia `parent_element_id` de una variante?**

**Decisión: Reasignar al final del nuevo padre.**

En el endpoint `PUT /api/admin/elements/{element_id}`, si `parent_element_id` cambia, añadir:

```python
# In update_element handler, after applying updates:
if "parent_element_id" in data.model_dump(exclude_unset=True):
    new_parent_id = data.parent_element_id
    if new_parent_id:
        # Assign next available position in new parent's family
        max_pos_result = await session.execute(
            select(func.max(Element.variant_position)).where(
                Element.parent_element_id == new_parent_id,
                Element.is_active == True,
                Element.id != element_id,  # Exclude self
            )
        )
        current_max = max_pos_result.scalar()
        element.variant_position = (current_max or 0) + 1
    else:
        # Being promoted to base element
        element.variant_position = None
```

---

## Sección 4: Admin Panel

**Archivos**: `admin-panel/src/components/` (diálogos de elementos)

### 4.1 `CreateVariantDialog` — sin cambios en el formulario

El campo `variant_position` **NO se añade** al formulario de creación. La API lo asigna automáticamente. El usuario del panel nunca tiene que pensar en él.

**Única comunicación al usuario**: Una nota en el UI junto a la lista de variantes:

```tsx
// En la sección de variantes del elemento padre, añadir tooltip/badge:
<p className="text-xs text-muted-foreground">
  El orden de las opciones A, B, C se asigna automáticamente. 
  Usa los botones ↑↓ para cambiarlo.
</p>
```

### 4.2 `ElementUpdate` en Pydantic — excluir `variant_position`

En `api/models/element.py`, la clase `ElementUpdate` debe excluir `variant_position` de los campos editables directamente. Solo el endpoint `/reorder` puede modificarlo:

```python
class ElementUpdate(BaseModel):
    """Fields editable via PUT /elements/{id}. variant_position is NOT here."""
    name: str | None = None
    description: str | None = None
    keywords: list[str] | None = None
    aliases: list[str] | None = None
    is_active: bool | None = None
    sort_order: int | None = None
    variant_type: str | None = None
    variant_code: str | None = None
    question_hint: str | None = None
    multi_select_keywords: list[str] | None = None
    inherit_parent_data: bool | None = None
    parent_element_id: UUID | None = None
    # variant_position: ← NEVER editable directly from ElementUpdate
```

### 4.3 Mostrar orden de variantes en la página del elemento padre

En la página de detalle del elemento padre (donde se lista `children`), añadir una columna "Posición" que muestre `variant_position` y botones ↑↓:

```tsx
// En el componente de lista de variantes (dentro de get_element response):
{element.children
  .sort((a, b) => (a.variant_position ?? 999) - (b.variant_position ?? 999))
  .map((variant, idx) => (
    <div key={variant.id} className="flex items-center gap-2 p-2 border rounded">
      <Badge variant="outline">
        {variant.variant_position 
          ? String.fromCharCode(64 + variant.variant_position)  // 1→A, 2→B, 3→C
          : "?"
        }
      </Badge>
      <span className="flex-1">{variant.name}</span>
      <div className="flex gap-1">
        <Button
          variant="ghost"
          size="icon"
          disabled={variant.variant_position === 1}
          onClick={() => handleMoveVariantUp(variant.id)}
        >
          ↑
        </Button>
        <Button
          variant="ghost"
          size="icon"
          disabled={idx === element.children.length - 1}
          onClick={() => handleMoveVariantDown(variant.id)}
        >
          ↓
        </Button>
      </div>
    </div>
  ))
}
```

**`handleMoveVariantUp` / `handleMoveVariantDown`**: llaman a `PUT /elements/{parent_id}/variants/reorder` con la lista reordenada.

**Nota de implementación**: El frontend puede hacer el swap localmente en el estado y enviar la lista completa ordenada a `/reorder`. No necesita lógica especial: construye `[...variants].sort()`, hace swap de los dos elementos adyacentes, extrae los IDs en orden, llama al endpoint.

---

## Sección 5: `get_element_variants()` en `element_service.py`

**Archivo**: `agent/services/element_service.py`

### 5.1 Cambiar ORDER BY

En el método `get_element_variants` (~línea 241), cambiar:

```python
# ANTES:
.order_by(Element.sort_order)

# DESPUÉS:
.order_by(
    Element.variant_position.asc().nulls_last(),  # Primary: canonical order
    Element.sort_order.asc(),                      # Fallback: display order
)
```

**Justificación del `NULLS LAST`**: Si alguna variante tiene `variant_position=NULL` (por ejemplo, creada antes de la migración o por un bug), no debe aparecer primera. Va al final y el keyword matching de Fases 1-3 la puede rescatar igual.

### 5.2 Añadir `variant_position` al dict de retorno

```python
data = [
    {
        "id": str(variant.id),
        "code": variant.code,
        "name": variant.name,
        "variant_type": variant.variant_type,
        "variant_code": variant.variant_code,
        "description": variant.description or "",
        "keywords": variant.keywords or [],
        "variant_position": variant.variant_position,  # ← NUEVO
    }
    for variant in variants
]
```

### 5.3 Invalidación de caché al modificar `variant_position`

El endpoint `/reorder` ya invalida las claves de caché relevantes (ver Sección 3.2). Adicionalmente, en el endpoint `PUT /elements/{element_id}`, si se detecta que `variant_position` cambió (o si cambia `parent_element_id`), invalidar:

```python
# Invalidate variant cache for parent
await redis.delete(f"elements:variants:{parent_code}:{category_id}")
```

Las claves de caché afectadas son:
- `elements:variants:{element_code}:{category_id}` — resultado de `get_element_variants`
- `elements:category:{category_id}:active=True` — lista completa de elementos
- `elements:base:category:{category_id}:active=True` — elementos base

---

## Sección 6: Tool `identificar_y_resolver_elementos`

**Archivo**: `agent/tools/element_tools.py`

Este tool construye la lista `preguntas_variantes` con la estructura:

```python
preguntas_variantes = [{
    "codigo_base": "PLACA_SOLAR",
    "pregunta": question_hint,
    "opciones": [v["name"] for v in variants],  # actualmente ordenado por sort_order
}]
```

### Cambio requerido

Dado que `get_element_variants()` ahora ordena por `variant_position ASC NULLS LAST`, el orden del array `opciones` ya vendrá correcto automáticamente. **No se requiere ningún cambio de ordenación adicional** en este tool.

Lo único que añadir es el `variant_position` en el detalle de `elementos_con_variantes` para que el LLM tenga contexto explícito:

```python
# En la sección que construye elementos_con_variantes:
"opciones": [
    {
        "name": v["name"],
        "code": v["code"],
        "variant_position": v["variant_position"],  # ← NUEVO
        "letter": chr(64 + v["variant_position"]) if v["variant_position"] else None,  # 1→A, 2→B
    }
    for v in variants
],
```

**Ejemplo de salida del tool con el cambio**:
```json
{
  "elementos_con_variantes": [{
    "codigo_base": "PLACA_SOLAR",
    "pregunta": "¿Dónde está ubicado el regulador de la placa solar?",
    "opciones": [
      {"name": "Regulador interior", "code": "PLACA_SOLAR_REG_INT", "variant_position": 1, "letter": "A"},
      {"name": "Regulador en maletero", "code": "PLACA_SOLAR_REG_MAL", "variant_position": 2, "letter": "B"},
      {"name": "Regulador en portón exterior", "code": "PLACA_SOLAR_REG_PORT", "variant_position": 3, "letter": "C"}
    ]
  }]
}
```

---

## Sección 7: Tool `seleccionar_variante_por_respuesta`

**Archivo**: `agent/tools/element_tools.py` (~línea 653)

### El problema actual

La Fase 0 actual mapea por **índice de array** (0-based):

```python
POSITIONAL_MAP: dict[str, int] = {"a": 0, "b": 1, "c": 2, "d": 3, "e": 4}
if respuesta_stripped in POSITIONAL_MAP:
    idx = POSITIONAL_MAP[respuesta_stripped]
    if idx < len(variants):
        positional_match = variants[idx]  # Frágil: depende del orden del array
```

### La nueva lógica

Reemplazar la Fase 0 completa con búsqueda por `variant_position`:

```python
# === PHASE 0: Positional matching via variant_position ===
# When the user answers "A", "B", "C" (or "1", "2", "3" with caution),
# map to the variant with variant_position == N.
# This is EXPLICIT and independent of array order.
#
# NOTE: Numbers (1/2/3) remain excluded from POSITIONAL_MAP to avoid conflicts
# with variants that use digit keywords (e.g., FAROS_LA_2F uses "2" as a keyword).
POSITIONAL_MAP: dict[str, int] = {
    "a": 1,   # variant_position=1
    "b": 2,   # variant_position=2
    "c": 3,   # variant_position=3
    "d": 4,   # variant_position=4
    "e": 5,   # variant_position=5
}

respuesta_stripped = respuesta_lower.strip()
if respuesta_stripped in POSITIONAL_MAP:
    target_position = POSITIONAL_MAP[respuesta_stripped]
    
    # Find variant by variant_position (explicit, not by array index)
    positional_match = next(
        (v for v in variants if v.get("variant_position") == target_position),
        None,
    )
    
    if positional_match:
        logger.info(
            f"[seleccionar_variante] Positional match via variant_position: "
            f"'{respuesta_usuario}' → position={target_position} → '{positional_match['code']}'",
        )
        return json.dumps({
            "selected_variant": positional_match["code"],
            "confidence": 0.95,  # High confidence: explicit positional match
            "name": positional_match["name"],
            "variant_code": positional_match.get("variant_code", ""),
            "match_method": "variant_position",
            "variant_position": target_position,
            "instrucciones": (
                f"Usa el código '{positional_match['code']}' en lugar de '{codigo_elemento_base}' "
                "para calcular_tarifa_con_elementos."
            ),
        }, ensure_ascii=False, indent=2)
    else:
        # No variant found with that position (could be a NULL position or out-of-range)
        # Log and fall through to keyword matching
        logger.warning(
            f"[seleccionar_variante] Positional letter '{respuesta_stripped}' "
            f"maps to position={target_position} but no variant has that position. "
            f"Falling through to keyword matching.",
            extra={
                "variants_positions": [v.get("variant_position") for v in variants],
                "codigo_base": codigo_elemento_base,
            },
        )
        # INTENTIONAL FALL-THROUGH to Phase 1 (keyword matching)
        # This is a safety net for variants with variant_position=NULL
```

### Diferencias clave respecto a la lógica anterior

| Aspecto | Antes | Después |
|---------|-------|---------|
| Mapeo | `"a": 0` (índice de array) | `"a": 1` (valor de `variant_position`) |
| Confianza | `0.85` | `0.95` (más alta, porque es explícito) |
| Dependencia | Orden del array (frágil) | Campo de BD (explícito) |
| `match_method` | `"positional"` | `"variant_position"` |
| Fallback si NULL | No existe | Cae a keyword matching |

### Compatibilidad durante la transición

Durante el período entre que se aplica la migración y que el agente se reinicia, podría haber requests que usen la lógica antigua (basada en índice). El comportamiento es idéntico mientras `variant_position` coincida con el índice del array, lo cual es el caso inmediatamente después de la migración (el ROW_NUMBER los asigna en el mismo orden que el sort_order que ya existía). **No hay ventana de rotura.**

---

## Sección 8: Prompt del Agente

**Archivo**: `agent/prompts/modes/presupuesto_mode.md`

### Análisis de la situación actual

El prompt NO instruye explícitamente al LLM a usar A/B/C para presentar variantes. El formato A/B/C es comportamiento emergente: el LLM lo adopta por convención basándose en cómo el texto de la pregunta llega en `preguntas_variantes["pregunta"]`.

El keyword matching (Fases 1-3) funciona perfectamente cuando el usuario responde en texto libre ("la interior", "el maletero"). El mapeo posicional (Fase 0) es un *bonus* para cuando el LLM usa A/B/C.

### Decisión: Añadir una instrucción de consistencia

El sistema funciona sin necesidad de forzar A/B/C. Sin embargo, para aumentar la consistencia y reducir el riesgo de que el LLM use formatos inconsistentes (a veces "1)", a veces "A)", a veces viñetas), se añade una instrucción:

**Añadir al final de la sección "Paso 2: Resolver variantes"** en `presupuesto_mode.md`:

```markdown
### Formato de opciones de variante

Cuando `identificar_y_resolver_elementos` devuelva variantes pendientes, preséntale al usuario
las opciones usando el formato letra mayúscula:

```
A) [nombre de la primera opción]
B) [nombre de la segunda opción]
C) [nombre de la tercera opción]
```

El orden es FIJO: usa siempre el orden en que las opciones aparecen en la respuesta de la herramienta
(campo `variant_position` interno). No reordenes las opciones según tu criterio.

Si el usuario responde "A", "B" o "C", usa directamente `seleccionar_variante_por_respuesta()`.
Si el usuario responde en texto libre ("la interior", "el de maletero"), también usa 
`seleccionar_variante_por_respuesta()` — la herramienta maneja ambos casos.
```

**Impacto en tokens**: ~80 tokens adicionales en el prompt de presupuesto_mode. Aceptable.

**Por qué esta instrucción mejora el sistema**:
1. El LLM sabrá que el usuario puede responder "A", "B", "C" — no inventará formatos mezclados.
2. La instrucción "no reordenes" evita que el LLM reordene las opciones según su criterio, lo cual rompería el mapeo posicional.
3. El keyword matching sigue funcionando para respuestas en texto libre.

---

## Sección 9: Seeds

### 9.1 Actualizar `ElementData` TypedDict

**Archivo**: `database/seeds/data/common.py`

Añadir `variant_position` al TypedDict `ElementData`:

```python
class ElementData(TypedDict):
    """Element data structure."""
    code: str
    name: str
    description: str
    keywords: list[str]
    aliases: list[str]
    sort_order: int
    images: NotRequired[list[ElementImageData]]
    warnings: NotRequired[list[WarningData]]
    required_fields: NotRequired[list[RequiredFieldData]]
    # Variant support
    is_base: NotRequired[bool]
    is_active: NotRequired[bool]
    parent_code: NotRequired[str]
    variant_type: NotRequired[str]
    variant_code: NotRequired[str]
    variant_position: NotRequired[int]  # ← NUEVO: canonical order (1, 2, 3...)
    question_hint: NotRequired[str]
    multi_select_keywords: NotRequired[list[str]]
```

### 9.2 Actualizar `ElementSeeder`

**Archivo**: `database/seeds/seeders/element.py`

En `_seed_elements_first_pass`, en la sección de creación de elementos nuevos y actualización de existentes, incluir `variant_position`:

```python
# En la sección de update existing:
existing.variant_position = elem_data.get("variant_position")  # None if not specified

# En la sección de create new:
element = Element(
    id=element_id,
    # ... campos existentes ...
    variant_position=elem_data.get("variant_position"),  # ← NUEVO
)
```

### 9.3 Valores de `variant_position` para seeds existentes

#### `database/seeds/data/motos_part.py`

**SUSPENSION** (parent, `sort_order=30`):
```python
# SUSPENSION_DEL (sort_order=31) → variant_position=1
{"code": "SUSPENSION_DEL", "variant_position": 1, ...}
# SUSPENSION_TRAS (sort_order=32) → variant_position=2
{"code": "SUSPENSION_TRAS", "variant_position": 2, ...}
```

**INTERMITENTES** (parent, `sort_order=10`):
```python
# INTERMITENTES_DEL (sort_order=11) → variant_position=1
{"code": "INTERMITENTES_DEL", "variant_position": 1, ...}
# INTERMITENTES_TRAS (sort_order=12) → variant_position=2
{"code": "INTERMITENTES_TRAS", "variant_position": 2, ...}
```

**LUCES** (parent, `sort_order=5`):
```python
# Verificar orden actual en BD. Asumir sort_order: LUCES_FARO_DEL=6, LUCES_PILOTO=7, etc.
# → las 5 variantes reciben variant_position=1,2,3,4,5 según sort_order actual
```

**FRENADO** (parent, `sort_order=39`):
```python
# FRENADO_DISCOS → variant_position=1
# FRENADO_PINZAS → variant_position=2
# FRENADO_BOMBAS → variant_position=3
# FRENADO_LATIGUILLOS → variant_position=4
# FRENADO_DEPOSITO → variant_position=5
```

**CARROCERIA_EXT** (parent, `sort_order=49`):
```python
# CARENADO → variant_position=1
# GUARDABARROS_DEL → variant_position=2
# GUARDABARROS_TRAS → variant_position=3
# CARROCERIA → variant_position=4
```

#### `database/seeds/data/aseicars_prof.py`

**BOLA_REMOLQUE** (parent):
```python
# BOLA_SIN_MMR → variant_position=1
# BOLA_CON_MMR → variant_position=2
```

**BOLA_SIN_MMR** (también tiene hijo: árbol de 3 niveles):
```python
# BRAZO_PORTA → variant_position=1 (único hijo)
```

**GLP_INSTALACION** (parent):
```python
# Variante 1 → variant_position=1
# Variante 2 → variant_position=2
# Variante 3 → variant_position=3
```

**PLACA_SOLAR** (parent, 3 variantes en BD):
```python
# PLACA_SOLAR_REG_INT → variant_position=1
# PLACA_SOLAR_REG_MAL → variant_position=2
# PLACA_SOLAR_REG_PORT → variant_position=3
```

**CAMBIO_CLASIF** (parent):
```python
# CAMBIO_CLASIF_CON → variant_position=1
# CAMBIO_CLASIF_SIN → variant_position=2
```

**FAROS_LA** (parent):
```python
# FAROS_LA_1F → variant_position=1
# FAROS_LA_2F → variant_position=2
```

**SUSP_NEUM** (parent):
```python
# Variante 1 → variant_position=1
# Variante 2 → variant_position=2
```

**TOLDO_LAT** (parent, en ambas categorías aseicars-prof y aseicars-part):
```python
# Variante 1 → variant_position=1
# Variante 2 → variant_position=2
```

> **Nota**: Los valores exactos de `variant_position` en los seeds deben coincidir con los asignados por la migración (ROW_NUMBER ordenado por `sort_order ASC`). El implementador debe verificar los `sort_order` actuales en BD antes de escribir los seeds, o ejecutar la migración primero y leer los valores resultantes.

### 9.4 Corrección de inconsistencias en seeds/BD

#### Inconsistencia 1 — CRÍTICA: `CAMBIO_CLASIF_CON/SIN` huérfanos en `aseicars-part`

**Problema**: Existen en BD variantes `CAMBIO_CLASIF_CON` y `CAMBIO_CLASIF_SIN` con `parent_element_id` apuntando a un elemento padre `CAMBIO_CLASIF` que **no existe** en la categoría `aseicars-part` (solo existe en `aseicars-prof`). Son huérfanos de facto.

**Solución**: Eliminarlos de BD con `is_active=False` (soft-delete para preservar integridad referencial con posibles casos o logs existentes):

```sql
-- Verificar que no tienen casos activos antes de soft-delete:
SELECT COUNT(*) FROM case_element_data
WHERE element_code IN ('CAMBIO_CLASIF_CON', 'CAMBIO_CLASIF_SIN')
AND case_id IN (SELECT id FROM cases WHERE category_id = <aseicars-part-id>);

-- Si COUNT=0, soft-delete:
UPDATE elements
SET is_active = FALSE, updated_at = now()
WHERE code IN ('CAMBIO_CLASIF_CON', 'CAMBIO_CLASIF_SIN')
  AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-part');
```

Esta corrección se hace en la **migración 036** o en un script SQL manual previo al deploy. Se recomienda hacerla en la migración para que sea atómica con el resto de cambios.

**En seeds**: Eliminar las entradas de `CAMBIO_CLASIF_CON` y `CAMBIO_CLASIF_SIN` del módulo de datos de `aseicars-part`. Si no existe ese módulo separado (los datos pueden estar en `aseicars_prof.py` únicamente), verificar y ajustar.

#### Inconsistencia 2 — MEDIA: `BOLA_REMOLQUE` y `PLACA_SOLAR` en `aseicars-part` con `question_hint` sin hijos

**Problema**: Estos dos elementos tienen `question_hint` configurado (como si fueran padres de variantes) pero tienen `children = []`. El `question_hint` confunde al agente que pensaría que hay variantes que resolver.

**Solución**: Limpiar `question_hint = NULL` para esos dos registros en `aseicars-part`:

```sql
UPDATE elements
SET question_hint = NULL, updated_at = now()
WHERE code IN ('BOLA_REMOLQUE', 'PLACA_SOLAR')
  AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-part')
  AND NOT EXISTS (
      SELECT 1 FROM elements children
      WHERE children.parent_element_id = elements.id
        AND children.is_active = TRUE
  );
```

#### Inconsistencia 3 — MEDIA: Seeds divergidos de BD en `PLACA_SOLAR` de `aseicars-prof`

**Problema**: El seed dice 2 variantes, la BD tiene 3. Esto indica que alguien añadió una variante desde el admin panel sin actualizar el seed.

**Solución**:
1. Leer la tercera variante de BD: `SELECT * FROM elements WHERE parent_element_id = <placa_solar_aseicars_prof_id> ORDER BY sort_order;`
2. Añadir la variante faltante al seed `aseicars_prof.py` con `variant_position=3`.
3. Verificar que el `deterministic_element_uuid` generado en el seed coincide con el UUID real en BD. Si no coincide (el registro fue creado desde el panel y tiene UUID aleatorio), el seed hará un `INSERT` que fallará por el `UNIQUE(category_id, code)`. En ese caso, actualizar el UUID en BD o en el seed para que coincidan.

#### Inconsistencia 4 — BAJA: `CLARABOYA` en `aseicars-prof` con `question_hint` sin hijos

**Misma solución que Inconsistencia 2**: `UPDATE elements SET question_hint = NULL WHERE code = 'CLARABOYA' AND category_id = <aseicars-prof-id> AND NOT EXISTS (SELECT 1 FROM elements c WHERE c.parent_element_id = elements.id AND c.is_active = TRUE)`.

#### Inconsistencia 5 — BAJA: Naming `PLACA_SOLAR_PLACA_SOLAR_REGULADOR_INTERIOR`

**Problema**: El código tiene doble prefijo.

**Solución**: Renombrar con una migración o script:

```sql
UPDATE elements
SET code = 'PLACA_SOLAR_REG_INT',
    updated_at = now()
WHERE code = 'PLACA_SOLAR_PLACA_SOLAR_REGULADOR_INTERIOR'
  AND category_id = (SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof');
```

> **Precaución**: Si algún `case_element_data.element_code` referencia el código antiguo, actualizarlo también:
> ```sql
> UPDATE case_element_data SET element_code = 'PLACA_SOLAR_REG_INT'
> WHERE element_code = 'PLACA_SOLAR_PLACA_SOLAR_REGULADOR_INTERIOR';
> ```

#### Inconsistencia 6 — Árbol 3 niveles: `BOLA_REMOLQUE → BOLA_SIN_MMR → BRAZO_PORTA`

**Problema**: El sistema fue diseñado para jerarquías de 2 niveles. Un tercer nivel funciona si `BOLA_SIN_MMR` aparece como variante seleccionable Y también como padre de `BRAZO_PORTA`.

**Solución propuesta**: No modificar este árbol ahora. El `variant_position` simplemente se asigna:
- `BOLA_SIN_MMR.variant_position = 1` (dentro de `BOLA_REMOLQUE`)
- `BRAZO_PORTA.variant_position = 1` (dentro de `BOLA_SIN_MMR`)

El agente manejará el tercer nivel normalmente: si el usuario elige `BOLA_SIN_MMR`, el sistema detectará que esa variante a su vez tiene hijos y presentará la pregunta de variante de segundo nivel. Esto ya funciona con la lógica actual. Verificar en tests.

---

## Sección 10: Tests

### 10.1 `tests/test_variant_position_migration.py` (Nuevo)

```python
"""
Tests to verify that variant_position is correctly populated after migration 036.
Run after: alembic upgrade head
"""
import pytest
from sqlalchemy import select, func
from database.models import Element
from database.connection import get_async_session

@pytest.mark.asyncio
async def test_all_active_variants_have_variant_position():
    """All active child elements must have a non-null variant_position."""
    async with get_async_session() as session:
        result = await session.execute(
            select(func.count(Element.id)).where(
                Element.parent_element_id.is_not(None),
                Element.is_active == True,
                Element.variant_position.is_(None),
            )
        )
        count_null_positions = result.scalar()
        assert count_null_positions == 0, (
            f"{count_null_positions} active variants have NULL variant_position"
        )

@pytest.mark.asyncio
async def test_base_elements_have_null_variant_position():
    """Base elements (no parent) must have variant_position=NULL."""
    async with get_async_session() as session:
        result = await session.execute(
            select(func.count(Element.id)).where(
                Element.parent_element_id.is_(None),
                Element.variant_position.is_not(None),
            )
        )
        count_non_null = result.scalar()
        assert count_non_null == 0, (
            f"{count_non_null} base elements incorrectly have variant_position set"
        )

@pytest.mark.asyncio
async def test_variant_positions_start_at_1_per_family():
    """For each parent, the minimum variant_position among active variants must be 1."""
    async with get_async_session() as session:
        result = await session.execute(
            select(
                Element.parent_element_id,
                func.min(Element.variant_position).label("min_pos"),
                func.count(Element.id).label("variant_count"),
            )
            .where(
                Element.parent_element_id.is_not(None),
                Element.is_active == True,
                Element.variant_position.is_not(None),
            )
            .group_by(Element.parent_element_id)
        )
        rows = result.fetchall()
        
        assert len(rows) > 0, "No variant families found"
        
        for row in rows:
            assert row.min_pos == 1, (
                f"Parent {row.parent_element_id}: minimum variant_position is "
                f"{row.min_pos} instead of 1"
            )

@pytest.mark.asyncio
async def test_variant_positions_are_unique_per_family():
    """Within each parent family, variant_position values must be unique."""
    async with get_async_session() as session:
        result = await session.execute(
            select(
                Element.parent_element_id,
                Element.variant_position,
                func.count(Element.id).label("count"),
            )
            .where(
                Element.parent_element_id.is_not(None),
                Element.is_active == True,
                Element.variant_position.is_not(None),
            )
            .group_by(Element.parent_element_id, Element.variant_position)
            .having(func.count(Element.id) > 1)
        )
        duplicates = result.fetchall()
        
        assert len(duplicates) == 0, (
            f"Duplicate variant_positions found: {[(str(r.parent_element_id), r.variant_position) for r in duplicates]}"
        )

@pytest.mark.asyncio
@pytest.mark.parametrize("category_slug,parent_code,expected_count", [
    ("motos-part", "SUSPENSION", 2),
    ("motos-part", "FRENADO", 5),
    ("motos-part", "INTERMITENTES", 2),
    ("aseicars-prof", "BOLA_REMOLQUE", 2),
    ("aseicars-prof", "PLACA_SOLAR", 3),
])
async def test_known_variant_counts(category_slug, parent_code, expected_count):
    """Verify known variant counts for key elements."""
    async with get_async_session() as session:
        from database.models import VehicleCategory
        
        cat_result = await session.execute(
            select(VehicleCategory).where(VehicleCategory.slug == category_slug)
        )
        category = cat_result.scalar_one_or_none()
        assert category is not None, f"Category {category_slug} not found"
        
        parent_result = await session.execute(
            select(Element).where(
                Element.code == parent_code,
                Element.category_id == category.id,
            )
        )
        parent = parent_result.scalar_one_or_none()
        assert parent is not None, f"Element {parent_code} not found in {category_slug}"
        
        variants_result = await session.execute(
            select(Element).where(
                Element.parent_element_id == parent.id,
                Element.is_active == True,
            )
        )
        variants = variants_result.scalars().all()
        
        assert len(variants) == expected_count, (
            f"{parent_code} in {category_slug}: expected {expected_count} variants, "
            f"found {len(variants)}"
        )
        
        # All variants must have variant_position
        for v in variants:
            assert v.variant_position is not None, (
                f"Variant {v.code} of {parent_code} has NULL variant_position"
            )
```

### 10.2 `tests/test_variant_response_positional.py` (Modificar)

Actualizar los tests existentes que usaban índice de array para usar `variant_position`:

```python
"""
Tests for positional variant response mapping using variant_position field.
Replaces the previous index-based positional tests.
"""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_respuesta_A_mapea_a_variant_position_1():
    """
    User responds 'A' → maps to variant with variant_position=1.
    Must use variant_position field, NOT array index.
    """
    # Mock variants in non-sort_order order (to prove we're NOT using array index)
    mock_variants = [
        {
            "id": "uuid-c",
            "code": "SUSPENSION_TRAS",
            "name": "Suspensión trasera",
            "variant_type": "position",
            "variant_code": "TRAS",
            "description": "",
            "keywords": ["trasera", "tras", "posterior"],
            "variant_position": 2,  # This is position 2 (option B), but appears FIRST in array
        },
        {
            "id": "uuid-a",
            "code": "SUSPENSION_DEL",
            "name": "Suspensión delantera",
            "variant_type": "position",
            "variant_code": "DEL",
            "description": "",
            "keywords": ["delantera", "del", "anterior"],
            "variant_position": 1,  # This is position 1 (option A), but appears SECOND in array
        },
    ]
    
    with patch("agent.services.element_service.ElementService.get_element_variants",
               new_callable=AsyncMock,
               return_value=mock_variants):
        with patch("agent.tools.element_tools.get_or_fetch_category_id",
                   new_callable=AsyncMock,
                   return_value="fake-category-id"):
            with patch("agent.services.element_service.ElementService.get_element_by_code",
                       new_callable=AsyncMock,
                       return_value={"multi_select_keywords": []}):
                
                from agent.tools.element_tools import seleccionar_variante_por_respuesta
                result_raw = await seleccionar_variante_por_respuesta.ainvoke({
                    "categoria_vehiculo": "motos-part",
                    "codigo_elemento_base": "SUSPENSION",
                    "respuesta_usuario": "A",
                })
                result = json.loads(result_raw)
                
                # MUST select SUSPENSION_DEL (variant_position=1), NOT SUSPENSION_TRAS
                assert result["selected_variant"] == "SUSPENSION_DEL", (
                    f"Expected SUSPENSION_DEL (variant_position=1) but got {result['selected_variant']}"
                )
                assert result["match_method"] == "variant_position"
                assert result["variant_position"] == 1

@pytest.mark.asyncio
async def test_respuesta_B_mapea_a_variant_position_2():
    """User responds 'B' → maps to variant with variant_position=2."""
    mock_variants = [
        {"code": "OPT_A", "name": "Opción primera", "variant_position": 1,
         "keywords": [], "variant_type": None, "variant_code": "A", "description": "", "id": "u1"},
        {"code": "OPT_B", "name": "Opción segunda", "variant_position": 2,
         "keywords": [], "variant_type": None, "variant_code": "B", "description": "", "id": "u2"},
        {"code": "OPT_C", "name": "Opción tercera", "variant_position": 3,
         "keywords": [], "variant_type": None, "variant_code": "C", "description": "", "id": "u3"},
    ]
    
    with patch("agent.services.element_service.ElementService.get_element_variants",
               new_callable=AsyncMock,
               return_value=mock_variants):
        with patch("agent.tools.element_tools.get_or_fetch_category_id",
                   new_callable=AsyncMock,
                   return_value="fake-id"):
            with patch("agent.services.element_service.ElementService.get_element_by_code",
                       new_callable=AsyncMock,
                       return_value={"multi_select_keywords": []}):
                
                from agent.tools.element_tools import seleccionar_variante_por_respuesta
                result_raw = await seleccionar_variante_por_respuesta.ainvoke({
                    "categoria_vehiculo": "aseicars-prof",
                    "codigo_elemento_base": "PLACA_SOLAR",
                    "respuesta_usuario": "B",
                })
                result = json.loads(result_raw)
                
                assert result["selected_variant"] == "OPT_B"
                assert result["variant_position"] == 2

@pytest.mark.asyncio
async def test_fallback_to_keyword_when_position_null():
    """
    If the matched letter has no variant with that variant_position,
    fall through to keyword matching.
    """
    mock_variants = [
        # No variant has variant_position=1; all are NULL (legacy data)
        {"code": "DELANTERA", "name": "Delantera", "variant_position": None,
         "keywords": ["delantera", "del"], "variant_type": None, "variant_code": "DEL",
         "description": "", "id": "u1"},
        {"code": "TRASERA", "name": "Trasera", "variant_position": None,
         "keywords": ["trasera", "tras"], "variant_type": None, "variant_code": "TRAS",
         "description": "", "id": "u2"},
    ]
    
    with patch("agent.services.element_service.ElementService.get_element_variants",
               new_callable=AsyncMock,
               return_value=mock_variants):
        with patch("agent.tools.element_tools.get_or_fetch_category_id",
                   new_callable=AsyncMock,
                   return_value="fake-id"):
            with patch("agent.services.element_service.ElementService.get_element_by_code",
                       new_callable=AsyncMock,
                       return_value={"multi_select_keywords": []}):
                
                from agent.tools.element_tools import seleccionar_variante_por_respuesta
                
                # "A" won't find variant_position=1, falls through to keyword matching
                # "delantera" in response text should match DELANTERA via keywords
                result_raw = await seleccionar_variante_por_respuesta.ainvoke({
                    "categoria_vehiculo": "motos-part",
                    "codigo_elemento_base": "SUSPENSION",
                    "respuesta_usuario": "delantera",
                })
                result = json.loads(result_raw)
                
                # Should match DELANTERA via keyword (not positional since it's text)
                assert result.get("selected_variant") == "DELANTERA"

@pytest.mark.asyncio
async def test_text_libre_sigue_funcionando():
    """
    Text-free answers still work via keyword matching (Phases 1-3).
    """
    mock_variants = [
        {"code": "BOLA_SIN_MMR", "name": "Sin aumento de MMR", "variant_position": 1,
         "keywords": ["sin mmr", "sin aumento", "sin incremento"],
         "variant_type": "mmr_option", "variant_code": "SIN_MMR", "description": "", "id": "u1"},
        {"code": "BOLA_CON_MMR", "name": "Con aumento de MMR", "variant_position": 2,
         "keywords": ["con mmr", "con aumento", "ampliar mmr", "aumentar mmr"],
         "variant_type": "mmr_option", "variant_code": "CON_MMR", "description": "", "id": "u2"},
    ]
    
    with patch("agent.services.element_service.ElementService.get_element_variants",
               new_callable=AsyncMock,
               return_value=mock_variants):
        with patch("agent.tools.element_tools.get_or_fetch_category_id",
                   new_callable=AsyncMock,
                   return_value="fake-id"):
            with patch("agent.services.element_service.ElementService.get_element_by_code",
                       new_callable=AsyncMock,
                       return_value={"multi_select_keywords": []}):
                
                from agent.tools.element_tools import seleccionar_variante_por_respuesta
                result_raw = await seleccionar_variante_por_respuesta.ainvoke({
                    "categoria_vehiculo": "aseicars-prof",
                    "codigo_elemento_base": "BOLA_REMOLQUE",
                    "respuesta_usuario": "sí, quiero aumentar el MMR",
                })
                result = json.loads(result_raw)
                
                assert result["selected_variant"] == "BOLA_CON_MMR"
                assert result.get("match_method") != "variant_position"  # keyword match
```

### 10.3 Test de integración del flujo completo

```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_variant_flow_end_to_end():
    """
    Integration test: full variant selection flow with variant_position.
    Requires real DB with migration applied.
    """
    from agent.services.element_service import ElementService
    
    service = ElementService()
    
    # Get real variants from DB
    from database.connection import get_async_session
    from database.models import VehicleCategory, Element
    from sqlalchemy import select
    
    async with get_async_session() as session:
        cat = (await session.execute(
            select(VehicleCategory).where(VehicleCategory.slug == "motos-part")
        )).scalar_one_or_none()
        assert cat is not None
        
    variants = await service.get_element_variants(
        element_code="SUSPENSION",
        category_id=str(cat.id),
    )
    
    # Variants must be ordered by variant_position
    positions = [v["variant_position"] for v in variants if v["variant_position"] is not None]
    assert positions == sorted(positions), "Variants not ordered by variant_position"
    
    # First variant must be SUSPENSION_DEL (position=1)
    assert variants[0]["variant_position"] == 1
    assert "DEL" in variants[0]["code"] or "delantera" in variants[0]["name"].lower()
```

---

## Sección 11: Orden de Implementación

### Paso 1 — Preparación (sin downtime)

```
1.1  Leer valores actuales de sort_order y variant_position (NULL) desde BD
     → Confirmar que la migración ROW_NUMBER producirá el orden esperado
     → Query de diagnóstico (ver Sección 1)
```

### Paso 2 — Código Python (sin downtime, sin deploy)

```
2.1  database/models.py
     → Añadir campo variant_position (nullable, sin default en Python)
     → NO reiniciar agente todavía

2.2  database/seeds/data/common.py
     → Añadir variant_position a ElementData TypedDict

2.3  database/seeds/seeders/element.py
     → Añadir variant_position en create/update de elementos

2.4  database/seeds/data/motos_part.py y aseicars_prof.py
     → Añadir variant_position a todos los elementos variante
     → NO ejecutar seeds todavía

2.5  agent/services/element_service.py
     → Cambiar ORDER BY en get_element_variants
     → Añadir variant_position al dict de retorno

2.6  agent/tools/element_tools.py
     → Modificar tool identificar_y_resolver_elementos (añadir letter/variant_position en opciones)
     → Modificar tool seleccionar_variante_por_respuesta (nueva Fase 0)

2.7  api/routes/elements.py
     → Auto-asignación en create_element
     → Nuevo endpoint reorder_variants

2.8  api/models/element.py
     → Excluir variant_position de ElementUpdate

2.9  agent/prompts/modes/presupuesto_mode.md
     → Añadir instrucción de formato A/B/C

2.10 Tests (nuevos y modificados)
```

### Paso 3 — Migración BD (requiere acceso a servidor, breve downtime opcional)

```
3.1  OPCIONAL pero recomendado: detener agente durante migración
     → docker-compose stop agent
     → (La API puede seguir corriendo; la migración solo añade una columna nullable)

3.2  Aplicar migración:
     → docker-compose exec api alembic upgrade head

3.3  Verificar migración con queries de diagnóstico (Sección 1)

3.4  Reiniciar agente:
     → docker-compose start agent
```

> **¿Por qué detener el agente?** Estrictamente no es necesario. La migración es additive (`ADD COLUMN NULL`) y PostgreSQL no bloquea lecturas. Sin embargo, durante los milisegundos de transición el agente podría recibir `variant_position=NULL` y usar el fallback del array index. Detenerlo 30 segundos es la opción más segura.

### Paso 4 — Corregir inconsistencias BD

```
4.1  Ejecutar SQL de corrección de inconsistencias (Sección 9.4)
     → Se puede hacer en la migración 036 como parte de upgrade()
     → O en un script manual supervisado

4.2  Verificar correcciones:
     SELECT code, question_hint FROM elements
     WHERE code IN ('BOLA_REMOLQUE', 'PLACA_SOLAR', 'CLARABOYA')
     AND category_id IN (SELECT id FROM vehicle_categories WHERE slug IN ('aseicars-part', 'aseicars-prof'));
```

### Paso 5 — Deploy y validación

```
5.1  Rebuild y restart de servicios:
     → docker-compose build api agent
     → docker-compose up -d api agent

5.2  Smoke test manual:
     → Enviar mensaje de WhatsApp: "quiero homologar la suspensión de mi moto"
     → Verificar que el agente pregunta correctamente con opciones A/B
     → Responder "A" y verificar que selecciona SUSPENSION_DEL
     → Responder "B" en una segunda conversación y verificar SUSPENSION_TRAS

5.3  Ejecutar tests automáticos:
     → pytest tests/test_variant_position_migration.py -v
     → pytest tests/test_variant_response_positional.py -v

5.4  Verificar logs del agente para errores de variant_position
```

### Paso 6 — Seeds (no requiere downtime)

```
6.1  Ejecutar seeds con los nuevos datos de variant_position:
     → docker-compose exec api python -m database.seeds.run_all_seeds

6.2  Verificar que los seeds no generaron conflictos UUID
     → Los elementos creados manualmente desde el panel tienen UUIDs aleatorios
     → Los seeds usarán el UUID determinístico → puede haber CONFLICT si el code ya existe
     → El seeder debe usar ON CONFLICT DO UPDATE (upsert idempotente)
```

### Dependencias entre pasos

```
Paso 1 (diagnóstico)
    ↓
Paso 2 (código) — puede hacerse en cualquier orden internamente
    ↓
Paso 3 (migración BD) — REQUIERE que Paso 2 esté completo
    ↓
Paso 4 (correcciones BD) — puede hacerse en Paso 3 (mismo upgrade())
    ↓
Paso 5 (deploy + validación) — REQUIERE Paso 3 completo
    ↓
Paso 6 (seeds) — puede hacerse después del deploy
```

### Plan de Rollback

| Problema | Acción | Tiempo estimado |
|----------|--------|----------------|
| Migración falla a mitad | `alembic downgrade -1` | 30 segundos |
| Agente no arranca tras deploy | `docker-compose restart agent` (vuelve imagen anterior) | 1 minuto |
| Mapeo posicional incorrecto | Revertir cambios en `element_tools.py`, rebuild agent | 5 minutos |
| Variante no encontrada por position | El fallback a keyword matching lo rescata; log en agente | Sin downtime |
| Seeds generan conflictos UUID | Los seeds son idempotentes; no hay rollback necesario | N/A |

---

## Sección 12: Corrección de Inconsistencias (Resumen Ejecutivo)

Esta tabla resume TODAS las inconsistencias y sus acciones:

| # | Inconsistencia | Prioridad | Acción | Dónde |
|---|---------------|-----------|--------|-------|
| 1 | `CAMBIO_CLASIF_CON/SIN` huérfanos en `aseicars-part` | 🔴 CRÍTICA | `is_active=FALSE` en BD | Migración 036 `upgrade()` |
| 2 | `BOLA_REMOLQUE`+`PLACA_SOLAR` en `aseicars-part` con `question_hint` sin hijos | 🟡 MEDIA | `question_hint=NULL` | Migración 036 `upgrade()` |
| 3 | `CLARABOYA` en `aseicars-prof` con `question_hint` sin hijos | 🟢 BAJA | `question_hint=NULL` | Migración 036 `upgrade()` |
| 4 | Seeds divergidos `PLACA_SOLAR` (2 seed vs 3 BD) | 🟡 MEDIA | Verificar + añadir 3ª variante al seed | `aseicars_prof.py` |
| 5 | Naming `PLACA_SOLAR_PLACA_SOLAR_REGULADOR_INTERIOR` | 🟢 BAJA | `UPDATE elements SET code=...` | Migración 036 `upgrade()` |
| 6 | Árbol 3 niveles `BOLA_REMOLQUE→BOLA_SIN_MMR→BRAZO_PORTA` | 🟢 BAJA | Asignar `variant_position` correctamente; verificar en tests | Seeds |

### SQL completo para todas las correcciones en `upgrade()`

```sql
-- Corrección 1: CAMBIO_CLASIF_CON/SIN huérfanos en aseicars-part
UPDATE elements
SET is_active = FALSE, updated_at = now()
WHERE code IN ('CAMBIO_CLASIF_CON', 'CAMBIO_CLASIF_SIN')
  AND category_id = (
      SELECT id FROM vehicle_categories WHERE slug = 'aseicars-part'
  );

-- Corrección 2: Limpiar question_hint en elementos sin hijos en aseicars-part
UPDATE elements
SET question_hint = NULL, updated_at = now()
WHERE code IN ('BOLA_REMOLQUE', 'PLACA_SOLAR')
  AND category_id = (
      SELECT id FROM vehicle_categories WHERE slug = 'aseicars-part'
  );

-- Corrección 3: CLARABOYA sin hijos en aseicars-prof
UPDATE elements e
SET question_hint = NULL, updated_at = now()
WHERE e.code = 'CLARABOYA'
  AND e.category_id = (
      SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof'
  )
  AND NOT EXISTS (
      SELECT 1 FROM elements c
      WHERE c.parent_element_id = e.id AND c.is_active = TRUE
  );

-- Corrección 5: Renombrar elemento con doble prefijo
UPDATE elements
SET code = 'PLACA_SOLAR_REG_INT', updated_at = now()
WHERE code = 'PLACA_SOLAR_PLACA_SOLAR_REGULADOR_INTERIOR'
  AND category_id = (
      SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof'
  );

-- También actualizar case_element_data si existe:
UPDATE case_element_data
SET element_code = 'PLACA_SOLAR_REG_INT'
WHERE element_code = 'PLACA_SOLAR_PLACA_SOLAR_REGULADOR_INTERIOR';
```

Y el correspondiente `downgrade()` para las correcciones:

```sql
-- Revert Corrección 1: Re-activar CAMBIO_CLASIF_CON/SIN
UPDATE elements
SET is_active = TRUE, updated_at = now()
WHERE code IN ('CAMBIO_CLASIF_CON', 'CAMBIO_CLASIF_SIN')
  AND category_id = (
      SELECT id FROM vehicle_categories WHERE slug = 'aseicars-part'
  );

-- Revert Corrección 5: Restaurar nombre original (si es necesario)
UPDATE elements
SET code = 'PLACA_SOLAR_PLACA_SOLAR_REGULADOR_INTERIOR', updated_at = now()
WHERE code = 'PLACA_SOLAR_REG_INT'
  AND category_id = (
      SELECT id FROM vehicle_categories WHERE slug = 'aseicars-prof'
  );
UPDATE case_element_data
SET element_code = 'PLACA_SOLAR_PLACA_SOLAR_REGULADOR_INTERIOR'
WHERE element_code = 'PLACA_SOLAR_REG_INT';

-- Correcciones 2, 3: No se puede restaurar question_hint (valor desconocido)
-- → Documentar en downgrade() como warning
```

---

## Notas Finales para el Implementador

1. **Antes de ejecutar la migración**: correr el SQL de diagnóstico (Sección 1) y verificar que los 37 ROW_NUMBERs producirán el orden esperado.

2. **Para `PLACA_SOLAR` (3 variantes en BD vs 2 en seed)**: Antes de tocar el seed, ejecutar `SELECT code, name, sort_order FROM elements WHERE parent_element_id = <placa_solar_aseicars_prof_id>` para conocer la tercera variante y su UUID real. Si el UUID es aleatorio (fue creado desde el admin panel), el seed necesita ser actualizado con ese UUID fijo para que sea idempotente.

3. **Fase 0 en `seleccionar_variante_por_respuesta`**: El `POSITIONAL_MAP` cambia de valores `0,1,2,3,4` a `1,2,3,4,5`. Esto NO es un off-by-one: antes `"a": 0` significaba "el elemento en el índice 0 del array", ahora `"a": 1` significa "el elemento con `variant_position=1`". Son semánticas distintas.

4. **Confianza de 0.85 → 0.95**: La confianza sube porque el nuevo mapeo es explícito (campo de BD) en lugar de implícito (posición en array). El threshold de confianza en el tool es 0.7 para mostrar `instrucciones` normales vs "Confidence bajo. Pregunta al usuario". A 0.95 nunca cae en el mensaje de baja confianza.

5. **El `is_base` en el modelo**: Se observa en la migración 035 que los INSERT usan el campo `is_base`. Este campo no aparece en el modelo SQLAlchemy actual (`database/models.py`). Verificar si existe en la tabla real o fue un error en la migración. Si no existe, los INSERT de la migración 035 fallaron silenciosamente o el campo fue añadido en alguna migración intermedia. Esto es un hallazgo adicional a verificar.
