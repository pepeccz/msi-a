# Plan de Implementación: Fix Mode_Context Opción 3

**Fecha**: 6 de Febrero de 2026  
**Arquitect**: Backend Agent  
**Opción Seleccionada**: 3 - Mover lógica condicional fuera del método estático  
**Objetivo**: Corregir el error `name 'mode_context' is not defined` en `_extract_context_from_tool` manteniendo la funcionalidad del Fix 2

---

## 1. Análisis de Cambios

### 1.1 Archivos Afectados

| Archivo | Líneas Afectadas | Tipo de Cambio |
|---------|------------------|----------------|
| `agent/modes/presupuesto_mode.py` | ~526-560 | Modificar (simplificar) |
| `agent/modes/presupuesto_mode.py` | ~305-306 | Agregar (nueva lógica) |

### 1.2 Líneas Específicas

**Archivo Principal**: `agent/modes/presupuesto_mode.py`

| Sección | Líneas | Descripción |
|---------|--------|-------------|
| `_extract_context_from_tool` | 462-578 | Método estático con el bug |
| Llamada al método | 302-305 | Donde se llama desde `_process_message` |
| ContextVar sync | 316-320 | Fix 1 - **NO MODIFICAR** |

### 1.3 Dependencias

- **Ningún otro archivo** se ve afectado directamente
- **Tools dependientes**: `calcular_tarifa_con_elementos` retorna datos que se procesan
- **State**: `mode_context` contiene `precio_calculado`, `precio_comunicado`, `imagenes_enviadas`

### 1.4 Diagrama de Flujo del Cambio

```
ANTES (bug):
  _process_message()
    → _extract_context_from_tool()  [usa mode_context ❌]
    → context_updates.update()
    → ContextVar sync

DESPUÉS (fix):
  _process_message()
    → _extract_context_from_tool()  [solo extrae datos básicos ✅]
    → context_updates.update()
    → LÓGICA CONDICIONAL (nueva)     [compara precios aquí ✅]
    → ContextVar sync
```

---

## 2. Cambios Detallados por Archivo

### 2.1 Archivo: `agent/modes/presupuesto_mode.py`

#### Cambio A: Simplificar `_extract_context_from_tool` (líneas ~526-560)

**UBICACIÓN**: Dentro del método `@staticmethod _extract_context_from_tool`

**CÓDIGO ANTES** (con bug):

```python
        elif tool_name == "calcular_tarifa_con_elementos":
            # Handle nested structure: tool returns {texto, datos: {price, ...}, ...}
            datos = data.get("datos", {})
            precio = datos.get("price") or data.get("precio_final") or data.get("price") or data.get("total")
            if precio:
                current_precio = mode_context.get("precio_calculado")  # ❌ ERROR: mode_context no existe
                new_precio = float(precio)
                updates["precio_calculado"] = new_precio
                updates["tarifa_calculada"] = data  # Store full response including imagenes_ejemplo
                
                # FIX: Only reset flags if this is a NEW quote (different price)
                # This prevents resetting on retry/constraint validation cycles
                if current_precio is None or abs(current_precio - new_precio) > 0.01:
                    # New quote detected - reset flags
                    updates["precio_comunicado"] = False
                    updates["imagenes_enviadas"] = False
                    # Log for debugging
                    import logging
                    logging.getLogger(__name__).info(
                        "new_quote_detected_resetting_flags",
                        current_precio=current_precio,
                        new_precio=new_precio,
                    )
                else:
                    # Same quote (retry/constraint cycle) - preserve existing flags
                    import logging
                    logging.getLogger(__name__).info(
                        "same_quote_preserving_flags",
                        current_precio=current_precio,
                        precio_comunicado=mode_context.get("precio_comunicado"),  # ❌ ERROR aquí también
                        imagenes_enviadas=mode_context.get("imagenes_enviadas"),  # ❌ Y aquí
                    )
                
                # NOTE: NO longer propagate to root state (_tarifa_actual removed)
                # Tools access tarifa_calculada directly from mode_context
```

**CÓDIGO DESPUÉS** (simplificado):

```python
        elif tool_name == "calcular_tarifa_con_elementos":
            # Handle nested structure: tool returns {texto, datos: {price, ...}, ...}
            datos = data.get("datos", {})
            precio = datos.get("price") or data.get("precio_final") or data.get("price") or data.get("total")
            if precio:
                new_precio = float(precio)
                updates["precio_calculado"] = new_precio
                updates["tarifa_calculada"] = data  # Store full response including imagenes_ejemplo
                # NOTE: precio_comunicado and imagenes_enviadas flags are managed
                # in _process_message to avoid accessing mode_context in static method
                # NOTE: NO longer propagate to root state (_tarifa_actual removed)
                # Tools access tarifa_calculada directly from mode_context
```

**INSTRUCCIONES DE IMPLEMENTACIÓN**:
1. Ubicar el bloque `elif tool_name == "calcular_tarifa_con_elementos":` (línea ~526)
2. Reemplazar TODO el contenido interno (líneas ~527-560)
3. Eliminar:
   - Variable `current_precio` y su uso
   - Todo el bloque condicional `if current_precio is None...`
   - Todos los `import logging` y `logging.getLogger(__name__).info()`
   - Cualquier referencia a `mode_context`
4. Mantener:
   - Extracción de `datos` y `precio`
   - Asignación a `updates["precio_calculado"]`
   - Asignación a `updates["tarifa_calculada"]`
   - El comentario sobre `_tarifa_actual` (si existe)

---

#### Cambio B: Agregar lógica condicional en `_process_message` (después de línea ~305)

**UBICACIÓN**: Dentro del `for tool_call in tool_calls:` loop, después de:
```python
                    # Extract context from tool results
                    tool_context = self._extract_context_from_tool(
                        tool_name, tool_args, result,
                    )
                    context_updates.update(tool_context)
```

**CÓDIGO A AGREGAR** (insertar entre líneas 305 y 306):

```python
                    # ✅ FIX 2 (Opción 3): Handle price-before-images flag reset logic
                    # This logic is here (not in _extract_context_from_tool) because
                    # _extract_context_from_tool is @staticmethod and cannot access mode_context
                    if tool_name == "calcular_tarifa_con_elementos":
                        new_precio = tool_context.get("precio_calculado")
                        if new_precio is not None:
                            current_precio = mode_context.get("precio_calculado")
                            
                            # Only reset flags if this is a NEW quote (different price)
                            # This prevents resetting on retry/constraint validation cycles
                            if current_precio is None or abs(current_precio - new_precio) > 0.01:
                                # New quote detected - reset communication flags
                                context_updates["precio_comunicado"] = False
                                context_updates["imagenes_enviadas"] = False
                                self._logger.info(
                                    "new_quote_detected_resetting_flags",
                                    current_precio=current_precio,
                                    new_precio=new_precio,
                                    conversation_id=conversation_id,
                                )
                            else:
                                # Same quote (retry/constraint cycle) - preserve existing flags
                                # Don't modify precio_comunicado or imagenes_enviadas
                                self._logger.info(
                                    "same_quote_preserve_flags",
                                    current_precio=current_precio,
                                    precio_comunicado=mode_context.get("precio_comunicado"),
                                    imagenes_enviadas=mode_context.get("imagenes_enviadas"),
                                    conversation_id=conversation_id,
                                )
```

**INSTRUCCIONES DE IMPLEMENTACIÓN**:
1. Localizar la línea 305: `context_updates.update(tool_context)`
2. Insertar el nuevo bloque de código **INMEDIATAMENTE DESPUÉS**
3. Asegurar que:
   - La indentación sea correcta (16 espacios para estar alineado con el contexto)
   - Se use `self._logger` (NO `logging.getLogger(__name__)`)
   - Se incluya `conversation_id` en todos los logs
   - La condición `abs(current_precio - new_precio) > 0.01` maneje correctamente el umbral
4. **NO MODIFICAR** las líneas 316-320 (el Fix 1 del ContextVar sync)

---

## 3. Lógica de Negocio a Implementar

### 3.1 Pseudo-código Detallado

```python
# Este código se ejecuta en cada llamada a calcular_tarifa_con_elementos

IF tool_name == "calcular_tarifa_con_elementos":
    new_precio = precio_extraído_del_tool
    
    IF new_precio is not None:
        current_precio = mode_context.get("precio_calculado")
        
        # Caso 1: Primera vez que calculamos precio
        IF current_precio is None:
            SET precio_comunicado = False
            SET imagenes_enviadas = False
            LOG "new_quote_first_calculation"
        
        # Caso 2: Precio diferente (nueva cotización)
        ELSE IF abs(current_precio - new_precio) > 0.01:
            SET precio_comunicado = False
            SET imagenes_enviadas = False
            LOG "new_quote_price_changed"
        
        # Caso 3: Mismo precio (retry/validación)
        ELSE:
            # NO MODIFICAR flags - preservar estado actual
            LOG "same_quote_preserve_flags"
```

### 3.2 Escenarios Cubiertos

| Escenario | current_precio | new_precio | Acción | Flags |
|-----------|---------------|------------|--------|-------|
| Primera cotización | `None` | `410.00` | Reset | `precio_comunicado=False, imagenes_enviadas=False` |
| Cambio de precio | `350.00` | `410.00` | Reset | `precio_comunicado=False, imagenes_enviadas=False` |
| Retry (mismo precio) | `410.00` | `410.00` | Preserve | Mantener valores actuales |
| Constraint cycle | `410.00` | `410.00` | Preserve | Mantener valores actuales |
| Tiny diff (<=0.01) | `410.00` | `410.005` | Preserve | Considerado mismo precio |

### 3.3 Casos Edge

| Caso | Manejo |
|------|--------|
| `mode_context` vacío | `current_precio` será `None`, se resetean flags (correcto) |
| `tool_context` sin precio | No entra al bloque, no hace nada (correcto) |
| Precio = 0 | Se procesa normalmente (0 es válido) |
| Precio negativo | Se valida en la tool, no llega aquí |
| Float precision issues | Usar `abs(a - b) > 0.01` como threshold |

---

## 4. Logs Requeridos

### 4.1 Log: Nueva Cotización Detectada

```python
self._logger.info(
    "new_quote_detected_resetting_flags",
    current_precio=current_precio,  # None o float
    new_precio=new_precio,          # float
    conversation_id=conversation_id,
)
```

**Nivel**: `info`  
**Trigger**: Cuando `current_precio is None` o `abs(current_precio - new_precio) > 0.01`  
**Campos**:
- `current_precio`: Precio anterior (None si es primera vez)
- `new_precio`: Nuevo precio calculado
- `conversation_id`: ID de conversación para trazabilidad

### 4.2 Log: Misma Cotización (Preservar Flags)

```python
self._logger.info(
    "same_quote_preserve_flags",
    current_precio=current_precio,           # float
    precio_comunicado=mode_context.get("precio_comunicado"),    # bool
    imagenes_enviadas=mode_context.get("imagenes_enviadas"),    # bool
    conversation_id=conversation_id,
)
```

**Nivel**: `info`  
**Trigger**: Cuando el precio es el mismo (dentro del threshold de 0.01)  
**Campos**:
- `current_precio`: Precio actual (siempre float aquí)
- `precio_comunicado`: Estado actual del flag
- `imagenes_enviadas`: Estado actual del flag
- `conversation_id`: ID de conversación

### 4.3 Log: Extracción de Contexto (ya existe, mantener)

```python
self._logger.info(
    "tool_call",
    tool=tool_name,
    args_preview=str(tool_args)[:100],
    iteration=iteration + 1,
)
```

**Nota**: Este log ya existe en líneas 286-291, NO modificar.

---

## 5. Plan de Testing

### 5.1 Testing Manual - Flujo Paso a Paso

#### Test 1: Primera Cotización

**Precondiciones**:
- Conversación nueva
- Sin cotizaciones previas

**Pasos**:
1. Usuario: "Quiero homologar mi escape"
2. Agente identifica elemento
3. Agente calcula tarifa: `calcular_tarifa_con_elementos` → 410€

**Verificación**:
```bash
docker-compose logs -f agent | grep "new_quote_detected_resetting_flags"
# Debe aparecer:
# {"event": "new_quote_detected_resetting_flags", "current_precio": null, "new_precio": 410.0}
```

**Comportamiento Esperado**:
- `precio_comunicado` se establece en `False`
- `imagenes_enviadas` se establece en `False`
- El agente comunica el precio al usuario

#### Test 2: Cambio de Cotización

**Precondiciones**:
- Ya existe cotización de 350€
- Usuario agrega otro elemento

**Pasos**:
1. Usuario: "También quiero homologar el manillar"
2. Agente recalcula: `calcular_tarifa_con_elementos` → 410€

**Verificación**:
```bash
docker-compose logs -f agent | grep "new_quote_detected_resetting_flags"
# Debe aparecer:
# {"event": "new_quote_detected_resetting_flags", "current_precio": 350.0, "new_precio": 410.0}
```

**Comportamiento Esperado**:
- Flags se resetean
- El agente comunica el NUEVO precio

#### Test 3: Retry (Mismo Precio)

**Precondiciones**:
- Cotización existente: 410€
- Flags: `precio_comunicado=True`, `imagenes_enviadas=True`

**Pasos**:
1. Tool falla o necesita retry
2. Se llama `calcular_tarifa_con_elementos` nuevamente → 410€

**Verificación**:
```bash
docker-compose logs -f agent | grep "same_quote_preserve_flags"
# Debe aparecer:
# {"event": "same_quote_preserve_flags", "current_precio": 410.0, 
#  "precio_comunicado": true, "imagenes_enviadas": true}
```

**Comportamiento Esperado**:
- Flags NO se modifican
- El agente NO repite el precio ni re-envía imágenes

#### Test 4: Constraint Validation Cycle

**Precondiciones**:
- Cotización: 410€
- `precio_comunicado=True`

**Pasos**:
1. Agente valida constraint (ej: precio mencionado antes de imágenes)
2. Se re-calcula tarifa: 410€ (mismo precio)

**Verificación**:
```bash
docker-compose logs -f agent | grep "same_quote_preserve_flags"
```

**Comportamiento Esperado**:
- Flags se preservan
- No se genera un loop infinito

### 5.2 Logs a Monitorear

Durante las pruebas, monitorear:

```bash
docker-compose logs -f agent | grep -E "(new_quote_detected|same_quote_preserve|tool_call|calcular_tarifa)"
```

**Patrones Esperados**:
- ✅ `"new_quote_detected_resetting_flags"` - Cuando hay nueva cotización
- ✅ `"same_quote_preserve_flags"` - Cuando es retry/ciclo de validación
- ❌ NINGÚN `"name 'mode_context' is not defined"` - Error debe estar corregido
- ❌ NINGÚN `"Error in mode processing"` - Nodo no debe fallar

### 5.3 Verificación del Fix 1

Confirmar que Fix 1 sigue funcionando:

```bash
docker-compose logs -f agent | grep "contextvar_synced_after_price_detection"
# Debe aparecer después de cada cálculo de tarifa
```

---

## 6. Criterios de Aceptación

### 6.1 Checklist de Verificación

- [ ] **Fix 2 completo**: No hay errores `mode_context is not defined` en logs
- [ ] **Fix 1 intacto**: `contextvar_synced_after_price_detection` aparece en logs
- [ ] **Nueva cotización**: Flags se resetean cuando hay nueva cotización
- [ ] **Mismo precio**: Flags se preservan en retry/constraint cycles
- [ ] **Primera vez**: Flags se resetean correctamente en primera cotización
- [ ] **Precio cambiado**: Flags se resetean cuando el precio cambia
- [ ] **Logs correctos**: Todos los logs tienen `conversation_id` y niveles apropiados
- [ ] **No regression**: El agente sigue comportándose correctamente en flujo normal

### 6.2 Comportamiento Esperado por Escenario

| Escenario | Precio Anterior | Precio Nuevo | precio_comunicado | imagenes_enviadas | Log Esperado |
|-----------|-----------------|--------------|-------------------|-------------------|--------------|
| 1. Inicio | `None` | 410€ | `False` | `False` | `new_quote_detected` |
| 2. Comunicado | 410€ | 410€ | `True` | `False` | `same_quote_preserve` |
| 3. Imágenes enviadas | 410€ | 410€ | `True` | `True` | `same_quote_preserve` |
| 4. Cambio elemento | 410€ | 450€ | `False` | `False` | `new_quote_detected` |
| 5. Retry (mismo) | 450€ | 450€ | `True` | `True` | `same_quote_preserve` |

### 6.3 Anti-regression Checks

- [ ] El agente NO entra en loop infinito
- [ ] Las imágenes se envían SOLO después del precio
- [ ] El precio se comunica UNA VEZ por cotización
- [ ] No hay fugas de estado entre conversaciones (ContextVar limpio)

---

## 7. Timeline Estimado

### Fases del Trabajo

| Fase | Descripción | Archivos | Tiempo Est. |
|------|-------------|----------|-------------|
| **1. Análisis** | Revisar código actual, confirmar líneas | `presupuesto_mode.py` | 10 min |
| **2. Implementación A** | Simplificar `_extract_context_from_tool` | `presupuesto_mode.py` | 15 min |
| **3. Implementación B** | Agregar lógica en `_process_message` | `presupuesto_mode.py` | 20 min |
| **4. Review** | Verificar cambios, asegurar Fix 1 intacto | `presupuesto_mode.py` | 10 min |
| **5. Testing** | Ejecutar tests manuales, verificar logs | Docker logs | 30 min |
| **6. Documentación** | Actualizar comentarios si es necesario | `presupuesto_mode.py` | 5 min |

**Total Estimado**: **1 hora 30 minutos**

### Secuencia Recomendada

```
┌─────────────────────────────────────────────────────────────┐
│  Fase 1: Análisis (10 min)                                  │
│  - Revisar líneas exactas del archivo                       │
│  - Confirmar ubicación de Fix 1 (líneas 251-262)            │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Fase 2: Implementación A (15 min)                          │
│  - Editar _extract_context_from_tool                        │
│  - Simplificar lógica de calcular_tarifa_con_elementos      │
│  - Eliminar todas las referencias a mode_context            │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Fase 3: Implementación B (20 min)                          │
│  - Agregar lógica condicional en _process_message           │
│  - Después de línea 305, antes del ContextVar sync          │
│  - Usar self._logger correctamente                          │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Fase 4: Review (10 min)                                    │
│  - Verificar Fix 1 intacto                                  │
│  - Revisar indentación                                      │
│  - Confirmar no hay referencias a mode_context en static    │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Fase 5: Testing (30 min)                                   │
│  - Ejecutar agente                                          │
│  - Probar flujo completo                                    │
│  - Verificar logs                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 8. Notas de Implementación

### 8.1 Puntos Críticos

1. **NO modificar Fix 1**: Las líneas 251-262 del ContextVar sync deben permanecer intactas
2. **Indentación correcta**: El nuevo código en `_process_message` debe estar alineado con el contexto del for loop
3. **Usar self._logger**: Nunca usar `logging.getLogger(__name__)` en modo nodes
4. **Threshold 0.01**: Mantener el margen de 0.01 para comparación de floats

### 8.2 Rollback Plan

Si algo sale mal:

```bash
# Revertir cambios
git checkout -- agent/modes/presupuesto_mode.py

# Verificar estado
git status
```

### 8.3 Validación de Sintaxis

Antes de hacer restart al agente:

```bash
# Validar sintaxis Python
python -m py_compile agent/modes/presupuesto_mode.py

# Si no hay errores, reiniciar
docker-compose restart agent
```

---

## 9. Referencias

### Código Relacionado

- **Fix 1 (ContextVar sync)**: Líneas 252-261 de `presupuesto_mode.py`
- **Llamada a tool**: Líneas 302-305 de `presupuesto_mode.py`
- **Re-inyección ContextVar**: Líneas 316-320 de `presupuesto_mode.py`

### Documentación

- `docs/decisions/004-fix-presupuesto-corrupted-text.md` - Contexto del Fix 1
- `agent/AGENTS.md` - Guía de arquitectura de modos
- `docs/coding-standards/03-agent-architecture.md` - Anti-patterns y patrones

### Issues Relacionados

- Bug introducido en Fix 2 para evitar reset de flags innecesario
- Error: `name 'mode_context' is not defined`

---

## 10. Aprobación

### Checklist Pre-implementación

- [ ] Plan revisado y entendido
- [ ] Archivos de respaldo creados (si es necesario)
- [ ] Entorno de testing listo
- [ ] Logs monitoreables configurados

### Post-implementación

- [ ] Código implementado según especificación
- [ ] Tests manuales ejecutados y pasados
- [ ] Logs revisados sin errores
- [ ] Fix 1 verificado intacto
- [ ] Documentación actualizada (si aplica)

---

**Plan Creado Por**: Architect Agent  
**Fecha**: 6 de Febrero de 2026  
**Versión**: 1.0  
**Estado**: Listo para implementación

---

## Anexos

### A. Código Completo del Nuevo Bloque

Para copiar y pegar:

```python
                    # ✅ FIX 2 (Opción 3): Handle price-before-images flag reset logic
                    # This logic is here (not in _extract_context_from_tool) because
                    # _extract_context_from_tool is @staticmethod and cannot access mode_context
                    if tool_name == "calcular_tarifa_con_elementos":
                        new_precio = tool_context.get("precio_calculado")
                        if new_precio is not None:
                            current_precio = mode_context.get("precio_calculado")
                            
                            # Only reset flags if this is a NEW quote (different price)
                            # This prevents resetting on retry/constraint validation cycles
                            if current_precio is None or abs(current_precio - new_precio) > 0.01:
                                # New quote detected - reset communication flags
                                context_updates["precio_comunicado"] = False
                                context_updates["imagenes_enviadas"] = False
                                self._logger.info(
                                    "new_quote_detected_resetting_flags",
                                    current_precio=current_precio,
                                    new_precio=new_precio,
                                    conversation_id=conversation_id,
                                )
                            else:
                                # Same quote (retry/constraint cycle) - preserve existing flags
                                # Don't modify precio_comunicado or imagenes_enviadas
                                self._logger.info(
                                    "same_quote_preserve_flags",
                                    current_precio=current_precio,
                                    precio_comunicado=mode_context.get("precio_comunicado"),
                                    imagenes_enviadas=mode_context.get("imagenes_enviadas"),
                                    conversation_id=conversation_id,
                                )
```

### B. Bloque Simplificado para `_extract_context_from_tool`

```python
        elif tool_name == "calcular_tarifa_con_elementos":
            # Handle nested structure: tool returns {texto, datos: {price, ...}, ...}
            datos = data.get("datos", {})
            precio = datos.get("price") or data.get("precio_final") or data.get("price") or data.get("total")
            if precio:
                new_precio = float(precio)
                updates["precio_calculado"] = new_precio
                updates["tarifa_calculada"] = data  # Store full response including imagenes_ejemplo
                # NOTE: precio_comunicado and imagenes_enviadas flags are managed
                # in _process_message to avoid accessing mode_context in static method
                # NOTE: NO longer propagate to root state (_tarifa_actual removed)
                # Tools access tarifa_calculada directly from mode_context
```
