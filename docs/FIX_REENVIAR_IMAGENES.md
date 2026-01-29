# Fix: reenviar_imagenes_elemento No Enviaba Imágenes

## Problema Identificado

Cuando el usuario pedía ver las imágenes de ejemplo de un elemento (por ejemplo, "Si" para ver ejemplos del subchasis), el agente ejecutaba `reenviar_imagenes_elemento` pero **no enviaba ninguna imagen**.

### Causa Raíz

La herramienta `reenviar_imagenes_elemento` usaba `_get_element_by_code()` que devolvía un objeto SQLAlchemy "detached" (sesión cerrada). Al intentar acceder a `element.images` fuera de la sesión activa, SQLAlchemy devolvía una lista vacía.

```python
# ❌ ANTES (línea 1309-1327):
element = await _get_element_by_code(element_code, category_id, load_images=True)
# ^ Sesión cerrada aquí

# Build example images list from element.images relationship
example_images = []
if element.images:  # ← Lista vacía (sesión cerrada)
    for img in element.images:
        # Nunca se ejecuta...
```

### Comparación con `enviar_imagenes_ejemplo`

| Herramienta                | Método usado                              | ¿Sesión activa? | ¿Funciona? |
| -------------------------- | ----------------------------------------- | --------------- | ---------- |
| `enviar_imagenes_ejemplo`    | `element_service.get_element_with_images()` | ✅ Sí           | ✅ Sí      |
| `reenviar_imagenes_elemento` | `_get_element_by_code()`                    | ❌ No           | ❌ No      |

`element_service.get_element_with_images()` serializa las imágenes a diccionarios Python **dentro de la sesión activa**, evitando el problema de objetos detached.

---

## Solución Implementada

### Archivo Modificado
`agent/tools/element_data_tools.py` (líneas 1308-1343)

### Cambios Principales

1. **Obtener ID del elemento primero** (sin cargar imágenes):
   ```python
   element_basic = await _get_element_by_code(element_code, category_id, load_images=False)
   ```

2. **Usar element_service para serializar imágenes correctamente**:
   ```python
   from agent.services.element_service import get_element_service
   element_service = get_element_service()
   element_details = await element_service.get_element_with_images(str(element_basic.id))
   ```

3. **Procesar imágenes desde el dict serializado**:
   ```python
   for img in element_details.get("images", []):
       if img.get("status") == "active":  # ← Campo correcto (no is_active)
           example_images.append({
               "url": img["image_url"],
               "tipo": "elemento",
               "elemento": element_details["name"],
               "descripcion": img.get("description") or "",
               "display_order": img.get("sort_order", 0),
               "status": "active",
           })
   ```

4. **Agregar logging para debugging**:
   ```python
   logger.info(
       f"[reenviar_imagenes_elemento] Found {len(example_images)} active images for {element_code}",
       extra={"conversation_id": conversation_id, "element_code": element_code}
   )
   ```

---

## Verificación del Fix

### Prueba Manual

1. Iniciar una conversación pidiendo presupuesto para subchasis de moto
2. Cuando el agente pregunte si quieres ver ejemplos de fotos, responder **"Si"**
3. **Resultado esperado**: El agente debe enviar 1 imagen de ejemplo del subchasis

### Logs Esperados

Antes del fix:
```
{"message": "Executing tool: reenviar_imagenes_elemento with args: {'element_code': 'SUBCHASIS'}"}
{"message": "Case tool returned message | tool=reenviar_imagenes_elemento | success=True"}
# ← No hay log de "Queued X images"
```

Después del fix:
```
{"message": "Executing tool: reenviar_imagenes_elemento with args: {'element_code': 'SUBCHASIS'}"}
{"message": "[reenviar_imagenes_elemento] Found 1 active images for SUBCHASIS"}
{"message": "[reenviar_imagenes_elemento] Queued 1 images"}
{"message": "Image 1/1 sent | tipo=elemento, message_id=..."}
```

---

## Archivos Afectados

- `agent/tools/element_data_tools.py` - Función `reenviar_imagenes_elemento()` refactorizada

---

## Notas Técnicas

### SQLAlchemy Detached Instances

Un objeto SQLAlchemy queda "detached" cuando se accede fuera de su sesión:

```python
async with get_async_session() as session:
    element = await session.execute(query)
# ← Sesión cerrada aquí

element.images  # ← Puede devolver lista vacía o lanzar DetachedInstanceError
```

### Solución: Serializar Dentro de la Sesión

```python
async with get_async_session() as session:
    element = await session.execute(query)
    
    # Serializar a dict ANTES de cerrar sesión
    images = [{"url": img.image_url, ...} for img in element.images]
# ← Ahora podemos usar `images` fuera de la sesión
```

### Por Qué `selectinload` No es Suficiente

Aunque `selectinload(Element.images)` carga las imágenes eagerly, **los objetos siguen ligados a la sesión**. Acceder a atributos fuera de la sesión puede fallar silenciosamente.

---

## Fecha de Fix

2026-01-29

## Autor

Claude (Anthropic) - Análisis y solución del bug
