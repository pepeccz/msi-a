# Plan: variant-position — Fixes Pendientes y Migración de BD

**Creado por**: architect  
**Fecha**: 2026-02-24  
**Estado**: PENDIENTE DE APROBACIÓN  
**Rama sugerida**: `feature/variant-position` (ya existe)  
**Prerrequisito**: Plan anterior `variant-position-architecture.md` (la mayor parte ya implementada)

---

## 1. Resumen

Este plan completa los **6 cambios pendientes** para que la feature `variant_position` sea totalmente funcional en producción:

| # | Cambio | Severidad | Agente |
|---|--------|-----------|--------|
| 1 | Aplicar migración BD + re-seed | **CRÍTICO** | deploy-dev |
| 2 | Fix: `identificar_y_resolver_elementos` — formato A/B/C en `opciones` | **MEDIA** | agent-dev |
| 3 | Fix: ordenar hijos por `variant_position` en API | **MENOR** | backend-dev |
| 4 | Fix: recompactar posiciones después de eliminar variante | **MEDIA** | frontend-dev |
| 5 | UI: botones ↑/↓ para reordenar variantes | **MEDIA** | frontend-dev |
| 6 | Eliminar import muerto `GripVertical` | **TRIVIAL** | frontend-dev |

Los cambios 4, 5 y 6 son **exclusivamente frontend** y pueden ejecutarse en paralelo con el 3. El cambio 1 es el **único que afecta al servicio en producción** y debe ser el primero.

---

## 2. Risk Assessment

### Riesgo por cambio

| # | Riesgo | Impacto si falla |
|---|--------|-----------------|
| 1 | **ALTO** — Migración de BD en producción | Downtime del agente si la migración rompe algo. Bajo: la columna es NULL y el agente sigue funcionando sin `variant_position` (la Fase 0 posicional cae a keyword matching como fallback) |
| 2 | **MEDIO** — Cambio de comportamiento del agente | El LLM recibirá `["A - Delantera", "B - Trasera"]` en lugar de `["Delantera", "Trasera"]`. Esto es una mejora pero cambia el output del tool. Risk bajo: el formato es más claro |
| 3 | **BAJO** — Cambio de orden de elementos en respuesta API | Sólo afecta al admin panel (cómo se ordenan los hijos en la página de detalle). No afecta al agente, que ya ordena por `variant_position` desde `element_service.py` |
| 4 | **MEDIO** — Llama a endpoint `reorder` después del delete | Si el endpoint falla (edge case), la variante se elimina pero las posiciones quedan con gap. No es un error crítico; el agente sigue funcionando con la Fase 0 |
| 5 | **MEDIO** — Nueva funcionalidad de reordenamiento UI | Si hay un bug en la llamada al endpoint, las posiciones pueden quedar en estado incorrecto. El `reorder` es atómico (transacción), así que o funciona todo o nada |
| 6 | **TRIVIAL** — Eliminar import no utilizado | Sin riesgo funcional |

### Ventana de rotura del agente

**No existe ventana de rotura** entre la migración y el reinicio del agente:
- La lógica de Fase 0 ya usa `variant_position` (ya implementada en el código actual).
- Si una variante tiene `variant_position=NULL` (antes de la migración), la Fase 0 cae al keyword matching (fallback existente).
- Después de la migración, las 37 variantes activas tendrán `variant_position` asignado vía ROW_NUMBER.
- Los seeds son idempotentes: re-ejecutarlos actualiza los valores pero no borra datos.

---

## 3. Execution Order (Dependencias)

```
PASO 1: deploy-dev aplica migración 036 + re-seed
    ↓
PASO 2: agent-dev — fix formato A/B/C en identificar_y_resolver_elementos
PASO 3: backend-dev — fix orden de hijos por variant_position en API  (paralelo con 2)
    ↓
PASO 4+5+6: frontend-dev — botones ↑/↓, recompactar en delete, limpiar import
    (paralelo entre sí, pero DESPUÉS de que el endpoint reorder esté deployado → ya existe)
```

**Nota**: El endpoint `PUT /api/admin/elements/{parent_id}/variants/reorder` **ya existe** en el backend (implementado en el plan anterior). Los pasos 4 y 5 solo requieren cambios frontend.

---

## 4. Step-by-Step Tasks

---

### PASO 1 — Aplicar migración BD + seeds

**Agente**: deploy-dev  
**Archivos afectados**: Base de datos (no código)  
**Riesgo**: ALTO — Requiere supervisión

#### 1.1 Verificar estado antes de la migración

```sql
-- Verificar que la columna NO existe todavía
SELECT column_name 
FROM information_schema.columns 
WHERE table_name='elements' AND column_name='variant_position';
-- Resultado esperado: 0 filas

-- Contar variantes activas (debería ser ~37)
SELECT COUNT(*) FROM elements 
WHERE parent_element_id IS NOT NULL AND is_active = TRUE;
```

#### 1.2 Verificar que la migración 036 existe

```bash
ls -la database/alembic/versions/036_add_variant_position.py
# Debe existir
```

#### 1.3 Aplicar la migración

```bash
# DESDE el servicio api (tiene acceso a DB)
docker-compose exec api alembic upgrade head
```

**Qué hace la migración**:
1. Añade columna `variant_position INTEGER NULL` a la tabla `elements`
2. Popula variantes activas con ROW_NUMBER() OVER (PARTITION BY parent_element_id ORDER BY sort_order ASC, code ASC)
3. Crea índice compuesto `(parent_element_id, variant_position)`

#### 1.4 Verificar la migración

```sql
-- Todas las variantes activas deben tener variant_position
SELECT COUNT(*) FROM elements 
WHERE parent_element_id IS NOT NULL 
  AND is_active = TRUE 
  AND variant_position IS NULL;
-- Esperado: 0

-- Ver los valores asignados
SELECT p.code AS parent, e.code AS variant, e.sort_order, e.variant_position
FROM elements e
JOIN elements p ON e.parent_element_id = p.id
WHERE e.is_active = TRUE
ORDER BY p.code, e.variant_position;
```

#### 1.5 Re-ejecutar seeds (opcional pero recomendado)

Los seeds actualizarán los valores de `variant_position` en BD para que coincidan con los definidos en código. Si la migración ya los asignó correctamente con ROW_NUMBER, este paso confirma la consistencia.

```bash
docker-compose exec api python -m database.seeds.run_all_seeds
```

#### 1.6 Reiniciar el agente para aplicar cambios en memoria

```bash
docker-compose restart agent
```

**Criterios de aceptación**:
- [ ] Columna `variant_position` existe en tabla `elements`
- [ ] Todas las variantes activas (37) tienen `variant_position` no nulo
- [ ] Los valores empiezan en 1 por familia de variantes
- [ ] El agente arranca sin errores en los logs
- [ ] Una conversación de prueba con "quiero homologar la suspensión" retorna pregunta A/B/C

---

### PASO 2 — Fix: formato A/B/C en `preguntas_variantes`

**Agente**: agent-dev  
**Archivo**: `agent/tools/element_tools.py`  
**Riesgo**: MEDIO  
**Dependencia**: Requiere que el PASO 1 esté completado (variantes deben tener `variant_position`)

#### El problema

En `identificar_y_resolver_elementos()`, línea ~1579-1583, el campo `opciones` de `preguntas_variantes` actualmente contiene solo los nombres:

```python
# ACTUAL (línea ~1582):
"opciones": [v["name"] for v in variants],
# → ["Delantera", "Trasera"]
```

Esto hace que el LLM no tenga guía explícita sobre usar el formato A/B/C, lo cual es inconsistente con la Fase 0 de `seleccionar_variante_por_respuesta` que ya usa `variant_position`.

#### El fix

**Cambiar la lista `opciones`** para que incluya la letra correspondiente a cada `variant_position`:

```python
# NUEVO (línea ~1582):
"opciones": [
    f"{chr(64 + v['variant_position'])} - {v['name']}"
    if v.get("variant_position") is not None
    else v["name"]
    for v in variants
],
# → ["A - Delantera", "B - Trasera"]
```

**Por qué el `if` condicional**: Manejo defensivo por si alguna variante tiene `variant_position=NULL` (no debería ocurrir después del PASO 1, pero es buena práctica). En ese caso, muestra el nombre solo sin letra.

**Archivo**: `agent/tools/element_tools.py`  
**Función**: `identificar_y_resolver_elementos` (tool, decorado con `@tool`)  
**Localización exacta**: Buscar la función `identificar_y_resolver_elementos`, dentro del bloque que construye `preguntas_variantes` (~línea 1579-1583).

```python
# ANTES:
preguntas_variantes.append({
    "codigo_base": elem_code,
    "pregunta": question_hint,
    "opciones": [v["name"] for v in variants],
})

# DESPUÉS:
preguntas_variantes.append({
    "codigo_base": elem_code,
    "pregunta": question_hint,
    "opciones": [
        f"{chr(64 + v['variant_position'])} - {v['name']}"
        if v.get("variant_position") is not None
        else v["name"]
        for v in variants
    ],
})
```

**Criterios de aceptación**:
- [ ] El tool retorna `"opciones": ["A - Delantera", "B - Trasera"]` cuando las variantes tienen `variant_position`
- [ ] Si alguna variante tiene `variant_position=NULL`, el name se incluye sin letra (no rompe)
- [ ] El LLM presenta las opciones en formato `A) Delantera\nB) Trasera` al usuario (verificar en conversación)
- [ ] La Fase 0 de `seleccionar_variante_por_respuesta` sigue funcionando cuando el usuario responde "A" o "B"

---

### PASO 3 — Fix: ordenar hijos por `variant_position` en API

**Agente**: backend-dev  
**Archivo**: `api/routes/elements.py`  
**Riesgo**: BAJO  
**Dependencia**: Ninguna (puede ejecutarse en paralelo con PASO 2)

#### El problema

En el endpoint `GET /api/admin/elements/{element_id}` (~línea 341 de `api/routes/elements.py`), los hijos se ordenan solo por `sort_order`:

```python
# ACTUAL (línea ~341):
for child in sorted(element.children, key=lambda x: x.sort_order)
```

Esto hace que en el admin panel, las variantes se muestren en orden de `sort_order` en lugar de `variant_position`. En la mayoría de los casos son equivalentes, pero si un admin reordena las variantes (cambia `variant_position`), el panel no reflejaría el orden correcto hasta que también cambie `sort_order`.

#### El fix

Cambiar el criterio de ordenación a `(variant_position, sort_order)`:

```python
# NUEVO:
for child in sorted(
    element.children,
    key=lambda x: (x.variant_position or 999, x.sort_order)
)
```

**Localización exacta**: `api/routes/elements.py` línea ~341, dentro del endpoint `get_element`.

```python
# ANTES:
response["children"] = [
    ElemImgResp.model_validate(child).model_dump()
    for child in sorted(element.children, key=lambda x: x.sort_order)
]

# DESPUÉS:
response["children"] = [
    ElemImgResp.model_validate(child).model_dump()
    for child in sorted(
        element.children,
        key=lambda x: (x.variant_position or 999, x.sort_order)
    )
]
```

**Nota sobre `or 999`**: Si `variant_position` es NULL (no debería ocurrir tras la migración en variantes activas), la variante se coloca al final. Es un fallback seguro.

**Criterios de aceptación**:
- [ ] El endpoint `GET /api/admin/elements/{id}` retorna los hijos ordenados por `variant_position` (A primero, B después, etc.)
- [ ] Los hijos con `variant_position=NULL` aparecen al final
- [ ] El admin panel muestra las variantes en el orden A, B, C correcto

---

### PASO 4 — Fix: recompactar posiciones después de eliminar variante

**Agente**: frontend-dev  
**Archivo**: `admin-panel/src/app/(authenticated)/elementos/[id]/page.tsx`  
**Riesgo**: MEDIO  
**Dependencia**: Ninguna (el endpoint de reorder ya existe en el backend)

#### El problema

Cuando se elimina una variante, las posiciones quedan con un "gap":
- Antes: A(1), B(2), C(3)
- Se elimina B(2)
- Resultado: A(1), C(3) — gap en la posición 2
- Correcto sería: A(1), B(2) (renombrado desde C)

El agente seguiría funcionando (la Fase 0 busca por `variant_position`, no por índice), pero el usuario vería en el panel que "C se convierte en B" de forma inesperada si no se recompacta.

#### El fix

Después de eliminar la variante con éxito en `handleDeleteVariant`, llamar al endpoint de reorder con las variantes restantes reindexadas:

**Localización**: `admin-panel/src/app/(authenticated)/elementos/[id]/page.tsx`  
Función `handleDeleteVariant` (~línea 222-238).

**Lógica del fix**:
1. Eliminar la variante como actualmente
2. Obtener las variantes restantes del elemento padre (ya actualizado con `refreshElement`)
3. Enviar la lista reordenada al endpoint `PUT /api/admin/elements/{parent_id}/variants/reorder`

```typescript
// ANTES:
const handleDeleteVariant = async () => {
  if (!deletingVariant) return;
  try {
    setIsDeletingVariant(true);
    await api.deleteElement(deletingVariant.id);
    toast.success(`Variante "${deletingVariant.name}" eliminada`);
    setDeletingVariant(null);
    await refreshElement();
  } catch (error) {
    console.error("Error deleting variant:", error);
    const message = error instanceof Error ? error.message : "Error desconocido";
    toast.error(`Error al eliminar variante: ${message}`);
  } finally {
    setIsDeletingVariant(false);
  }
};

// DESPUÉS:
const handleDeleteVariant = async () => {
  if (!deletingVariant) return;
  const parentId = element?.id;   // The current element IS the parent
  try {
    setIsDeletingVariant(true);
    await api.deleteElement(deletingVariant.id);
    
    // Recompact positions: get remaining active children and re-number 1,2,3...
    if (parentId && element?.children) {
      const remainingVariants = element.children
        .filter(
          (c) => c.id !== deletingVariant.id && c.is_active !== false
        )
        .sort((a, b) => (a.variant_position ?? 999) - (b.variant_position ?? 999));
      
      if (remainingVariants.length > 0) {
        try {
          await api.reorderVariants(
            parentId,
            remainingVariants.map((v) => v.id)
          );
        } catch (reorderError) {
          // Non-blocking: log but don't fail the delete operation
          console.error("Failed to recompact variant positions:", reorderError);
        }
      }
    }
    
    toast.success(`Variante "${deletingVariant.name}" eliminada`);
    setDeletingVariant(null);
    await refreshElement();
  } catch (error) {
    console.error("Error deleting variant:", error);
    const message = error instanceof Error ? error.message : "Error desconocido";
    toast.error(`Error al eliminar variante: ${message}`);
  } finally {
    setIsDeletingVariant(false);
  }
};
```

**Nota importante**: El `reorderError` es non-blocking — si falla la recompactación, la variante ya fue eliminada correctamente. El gap queda pero el agente sigue funcionando.

**También requiere**: Añadir el método `reorderVariants` al API client (ver PASO 5).

**Criterios de aceptación**:
- [ ] Eliminar la variante B de {A, B, C} resulta en {A(1), B(2)} (antes era C, ahora se llama B)
- [ ] Si la recompactación falla, la delete sigue funcionando (error non-blocking)
- [ ] El panel se refresca después de la operación mostrando las posiciones actualizadas

---

### PASO 5 — UI: botones ↑/↓ para reordenar variantes

**Agente**: frontend-dev  
**Archivos**: 
- `admin-panel/src/lib/api.ts` (añadir método `reorderVariants`)
- `admin-panel/src/app/(authenticated)/elementos/[id]/page.tsx` (añadir botones ↑/↓)

**Riesgo**: MEDIO  
**Dependencia**: Ninguna (el endpoint ya existe)

#### 5.1 Añadir `reorderVariants` al API client

**Archivo**: `admin-panel/src/lib/api.ts`  
**Dónde**: Después del método `deleteElement` (~línea 579-581).

```typescript
// En api.ts, añadir después de deleteElement():
async reorderVariants(parentId: string, variantIds: string[]): Promise<{ success: boolean; message: string }> {
  return this.request(`/api/admin/elements/${parentId}/variants/reorder`, {
    method: "PUT",
    body: JSON.stringify({ variant_ids: variantIds }),
  });
}
```

**Nota**: El endpoint espera `{"variant_ids": [uuid1, uuid2, ...]}` en el body (tipo `VariantReorderRequest` del backend).

#### 5.2 Añadir botones ↑/↓ en la lista de variantes

**Archivo**: `admin-panel/src/app/(authenticated)/elementos/[id]/page.tsx`  
**Dónde**: En la sección de variantes (~línea 821-880), en el bloque `.map((child) => ...)`.

**Handler** a añadir en el componente (antes del return):

```typescript
// Añadir cerca de handleDeleteVariant (~línea 220):
const handleMoveVariant = async (variantId: string, direction: "up" | "down") => {
  if (!element?.children || !element.id) return;
  
  // Get sorted active children
  const sortedChildren = [...element.children]
    .filter((c) => c.is_active !== false)
    .sort((a, b) => (a.variant_position ?? 999) - (b.variant_position ?? 999));
  
  const currentIdx = sortedChildren.findIndex((c) => c.id === variantId);
  if (currentIdx === -1) return;
  
  const targetIdx = direction === "up" ? currentIdx - 1 : currentIdx + 1;
  if (targetIdx < 0 || targetIdx >= sortedChildren.length) return;
  
  // Swap elements
  const newOrder = [...sortedChildren];
  [newOrder[currentIdx], newOrder[targetIdx]] = [newOrder[targetIdx], newOrder[currentIdx]];
  
  try {
    await api.reorderVariants(
      element.id,
      newOrder.map((v) => v.id)
    );
    await refreshElement();
    toast.success("Orden actualizado");
  } catch (error) {
    console.error("Error reordering variants:", error);
    toast.error("Error al reordenar variantes");
  }
};
```

**UI** — modificar el bloque de botones en cada variante (~línea 851-866):

```tsx
// ANTES (solo tiene Edit + Delete):
<div className="flex items-center gap-1 flex-shrink-0">
  <Link href={`/elementos/${child.id}`}>
    <Button variant="ghost" size="sm" className="h-8 w-8 p-0" title="Editar variante">
      <Edit className="h-4 w-4" />
    </Button>
  </Link>
  <Button
    variant="ghost"
    size="sm"
    className="h-8 w-8 p-0 text-destructive hover:text-destructive hover:bg-destructive/10"
    onClick={() => setDeletingVariant(child)}
    title="Eliminar variante"
  >
    <Trash2 className="h-4 w-4" />
  </Button>
</div>

// DESPUÉS (añadir ↑/↓ antes del edit):
<div className="flex items-center gap-1 flex-shrink-0">
  <Button
    variant="ghost"
    size="sm"
    className="h-8 w-8 p-0"
    title="Mover arriba"
    disabled={sortedChildren.indexOf(child) === 0}
    onClick={() => handleMoveVariant(child.id, "up")}
  >
    <ChevronUp className="h-4 w-4" />
  </Button>
  <Button
    variant="ghost"
    size="sm"
    className="h-8 w-8 p-0"
    title="Mover abajo"
    disabled={sortedChildren.indexOf(child) === sortedChildren.length - 1}
    onClick={() => handleMoveVariant(child.id, "down")}
  >
    <ChevronDown className="h-4 w-4" />
  </Button>
  <Link href={`/elementos/${child.id}`}>
    <Button variant="ghost" size="sm" className="h-8 w-8 p-0" title="Editar variante">
      <Edit className="h-4 w-4" />
    </Button>
  </Link>
  <Button
    variant="ghost"
    size="sm"
    className="h-8 w-8 p-0 text-destructive hover:text-destructive hover:bg-destructive/10"
    onClick={() => setDeletingVariant(child)}
    title="Eliminar variante"
  >
    <Trash2 className="h-4 w-4" />
  </Button>
</div>
```

**Iconos a añadir al import**:  
`ChevronUp` y `ChevronDown` de `lucide-react`. Ya existen en lucide-react (no requiere instalación).

**Variable auxiliar** — antes del `.map()` de variantes, derivar `sortedChildren` para los índices:

```typescript
// Añadir antes del .map de variantes:
const sortedChildren = element.children
  ? [...element.children]
      .filter((c) => c.is_active !== false)
      .sort((a, b) => (a.variant_position ?? 999) - (b.variant_position ?? 999))
  : [];
```

**Nota**: Si `sortedChildren` ya se calcula en el handler `handleMoveVariant`, se puede extraer a una variable de componente para evitar recalcular. Mejor como variable derivada dentro del bloque de render de variantes.

**Criterios de aceptación**:
- [ ] Los botones ↑/↓ aparecen junto a cada variante
- [ ] El botón ↑ está deshabilitado para la primera variante
- [ ] El botón ↓ está deshabilitado para la última variante
- [ ] Hacer click en ↑/↓ actualiza el `variant_position` en BD (vía endpoint reorder)
- [ ] El panel se refresca mostrando el nuevo orden con las letras A/B/C actualizadas
- [ ] `toast.success` y `toast.error` funcionan correctamente

---

### PASO 6 — Eliminar import muerto `GripVertical`

**Agente**: frontend-dev (incluir en el mismo commit que PASO 5)  
**Archivo**: `admin-panel/src/app/(authenticated)/elementos/[id]/page.tsx`  
**Riesgo**: TRIVIAL

#### El fix

En el bloque de imports de lucide-react (~línea 44-60), eliminar `GripVertical` que no se usa en ningún lugar del componente:

```typescript
// ANTES:
import {
  ArrowLeft,
  Plus,
  Trash2,
  Edit,
  Upload,
  X,
  GripVertical,   // ← ELIMINAR
  Image as ImageIcon,
  AlertTriangle,
  GitBranch,
  ExternalLink,
  Network,
  Layers,
  ListChecks,
  ChevronRight,
} from "lucide-react";

// DESPUÉS:
import {
  ArrowLeft,
  Plus,
  Trash2,
  Edit,
  Upload,
  X,
  ChevronUp,      // ← AÑADIR (para PASO 5)
  ChevronDown,    // ← AÑADIR (para PASO 5)
  Image as ImageIcon,
  AlertTriangle,
  GitBranch,
  ExternalLink,
  Network,
  Layers,
  ListChecks,
  ChevronRight,
} from "lucide-react";
```

**Nota**: Este cambio va en el mismo commit que el PASO 5, ya que ambos modifican los imports.

**Criterios de aceptación**:
- [ ] No hay warnings de TypeScript por imports no utilizados
- [ ] Los nuevos iconos `ChevronUp` y `ChevronDown` importados correctamente

---

## 5. Rollback Strategy

### Rollback PASO 1 (migración BD)

Si la migración rompe algo:

```bash
# Revertir migración (downgrade)
docker-compose exec api alembic downgrade 035_restructure_motos_elements

# La migración 036 downgrade hace:
# 1. UPDATE elements SET variant_position = NULL WHERE parent_element_id IS NOT NULL
# 2. DROP INDEX ix_elements_variant_position
# 3. DROP COLUMN elements.variant_position
```

**Impacto del rollback**: El código del agente que usa `variant_position` tiene fallback:
- En `seleccionar_variante_por_respuesta`, la Fase 0 busca por `v.get("variant_position") == target_position`. Si todos son NULL, cae a keyword matching. No rompe.
- En `element_service.py`, el ORDER BY `variant_position NULLS LAST` ordena todos al final y usa `sort_order` como fallback. Sigue funcionando.

### Rollback PASO 2 (fix agent)

Si el cambio de formato causa problemas:

```bash
# Revertir el cambio en element_tools.py (git revert o editar manualmente)
# Volver a: "opciones": [v["name"] for v in variants]
# Reiniciar agente
docker-compose restart agent
```

### Rollback PASO 3 (fix API)

```bash
# Revertir el cambio en elements.py (git revert o editar manualmente)
# Volver a: key=lambda x: x.sort_order
# Reiniciar API
docker-compose restart api
```

### Rollback PASOS 4-6 (frontend)

```bash
# Hacer rollback del commit frontend
# O revertir manualmente los cambios en page.tsx y api.ts
# Rebuild y reiniciar admin-panel
docker-compose restart admin-panel
```

---

## 6. Testing Checklist

### Después del PASO 1

- [ ] **DB**: `SELECT variant_position, code FROM elements WHERE parent_element_id IS NOT NULL AND is_active=TRUE ORDER BY parent_element_id, variant_position;` → todas las variantes tienen valores 1, 2, 3...
- [ ] **DB**: Ningún elemento base tiene `variant_position` (deberían ser todos NULL para parent_element_id IS NULL)
- [ ] **Agente**: Iniciar conversación en WhatsApp/Chatwoot: "quiero homologar la suspensión de mi moto" → el agente pregunta "¿Delantera o trasera?" (o similar con A/B)
- [ ] **Agente**: Responder "A" → el agente selecciona correctamente `SUSPENSION_DEL` (posición 1)
- [ ] **Agente**: Responder "b" → el agente selecciona correctamente `SUSPENSION_TRAS` (posición 2)

### Después del PASO 2

- [ ] **Tool output**: En los logs del agente, verificar que `preguntas_variantes[0].opciones` contiene `["A - Delantera", "B - Trasera"]` (no solo los nombres)
- [ ] **LLM behavior**: El LLM presenta las opciones con letras mayúsculas al usuario

### Después del PASO 3

- [ ] **Admin panel**: Abrir `/elementos/{id_de_suspension}` → los hijos aparecen en orden A(1)=Delantera, B(2)=Trasera
- [ ] **API**: `curl /api/admin/elements/{id}?include_children=true` → los children están en orden de `variant_position`

### Después de los PASOS 4-6

- [ ] **UI delete**: Crear 3 variantes (A, B, C). Eliminar B. Resultado debe ser A(1) y B(2) (antes era A(1) y C(3))
- [ ] **UI reorder**: Crear 3 variantes. Hacer click en ↑ en la segunda variante → se convierte en la primera
- [ ] **UI reorder**: El botón ↑ está deshabilitado en la primera variante
- [ ] **UI reorder**: El botón ↓ está deshabilitado en la última variante
- [ ] **TypeScript**: `npm run build` en admin-panel sin errores de tipo
- [ ] **Import check**: No hay import de `GripVertical` en la página
- [ ] **Agent consistency**: Después de reordenar desde el panel, el agente presenta las opciones en el nuevo orden (refresca caché de Redis al llamar reorder)

### Test de regresión general

- [ ] **Flujo completo presupuesto**: "quiero homologar escape y suspensión delantera de mi moto" → identificar elementos → calcular tarifa → precio comunicado → imágenes
- [ ] **Selección de variante en texto libre**: "trasera" → selecciona `SUSPENSION_TRAS` (keyword matching sigue funcionando)
- [ ] **Multi-select**: "ambos" en suspensión → selecciona `SUSPENSION_DEL` y `SUSPENSION_TRAS`

---

## 7. Notas de Implementación

### Sobre la caché de Redis

El endpoint `PUT /api/admin/elements/{parent_id}/variants/reorder` ya invalida las claves de caché relevantes:
- `elements:variants:{parent_code}:{category_id}`
- `elements:category:{category_id}:active=True`

Esto significa que después de reordenar desde el panel, el agente verá el nuevo orden en la siguiente conversación (la caché tiene TTL de 5 minutos). No se requiere reiniciar el agente para aplicar cambios de orden.

### Sobre el TypedDict en seeds

El `ElementData` TypedDict en `database/seeds/data/common.py` ya incluye `variant_position: NotRequired[int]` (añadido en el plan anterior). Los seeds de `motos_part.py` y `aseicars_prof.py` deben ser actualizados para incluir los valores de `variant_position` si aún no lo están.

Si los seeds no tienen `variant_position` definido, el seeder usará `elem_data.get("variant_position")` que retorna `None`, y la migración habrá llenado los valores correctamente de todas formas. No es crítico para el funcionamiento del sistema.

### Sobre el campo `variant_position` en TypeScript

El tipo `Element` en `admin-panel/src/lib/types.ts` debe incluir `variant_position: number | null`. Verificar que ya esté incluido (debería estarlo desde el plan anterior). Si no, añadir:

```typescript
// En la interfaz Element (o ElementWithImagesAndChildren) en types.ts:
variant_position?: number | null;
```

### Sobre los elementos padre vs hijos en la página

En `handleDeleteVariant`, la variable `element` es el padre (la página actual es de un elemento padre que tiene children/variantes). La llamada a `api.reorderVariants(element.id, ...)` es correcta.

Sin embargo, hay que verificar: si el elemento actual ES una variante (tiene `parent_element_id`), el bloque de variantes no se muestra. La función `handleDeleteVariant` solo se invoca desde la sección de variantes del padre. Es seguro usar `element.id` como `parentId`.

---

## 8. Resumen de Archivos a Modificar

| Archivo | Tipo | Cambio |
|---------|------|--------|
| `agent/tools/element_tools.py` | Python | Fix formato `opciones` A/B/C (PASO 2) |
| `api/routes/elements.py` | Python | Fix `sorted()` por `variant_position` (PASO 3) |
| `admin-panel/src/lib/api.ts` | TypeScript | Añadir método `reorderVariants()` (PASO 5) |
| `admin-panel/src/app/(authenticated)/elementos/[id]/page.tsx` | TSX | Recompactar en delete + botones ↑/↓ + limpiar import (PASOS 4, 5, 6) |

**NO se requieren nuevas migraciones.** La migración 036 ya existe y solo necesita aplicarse.

---

**Aprobación requerida antes de ejecutar el PASO 1 (migración de BD en producción).**
