# Plan de Implementación: Opción 1 - Fix Mode_Context Persistence

**Fecha**: 6 de Febrero de 2026  
**Arquitect**: Backend Agent  
**Estado**: APROBADO para implementación  
**Prioridad**: ALTA (sistema roto en producción)

---

## Resumen Ejecutivo

### Problema
El `mode_context` no persiste entre turnos de conversación. Cuando el usuario envía un mensaje de texto (ej: "A"), el agente pierde el contexto previo (precio_comunicado, elementos confirmados, etc.) y entra en un loop de errores.

### Solución
**Opción 1 Validada**: Cargar explícitamente el `mode_context` del checkpoint y pasarlo en `state_input` al invocar el graph.

### Validación
✅ Funcionará técnicamente  
✅ Es consistente con patrón existente (imágenes)  
✅ Edge cases mitigados  
✅ Riesgo bajo  

---

## Análisis Técnico

### Causa Raíz Confirmada

LangGraph NO está restaurando automáticamente campos con reducers cuando no están en `state_input`. El comentario en `conversation_state.py` (líneas 248-253) documenta este comportamiento:

```python
# LangGraph behavior: Fields WITHOUT reducers get REPLACED by state_input.
# Fields WITH reducers get MERGED according to the reducer function.
#
# CRITICAL: Without reducers, mode_context and other fields are lost between
# conversation turns because main.py doesn't include them in state_input.
```

### Evidencia de Funcionamiento

La función `get_mode_context_from_checkpoint()` ya existe y se usa para manejo de imágenes (líneas 169-173 de `main.py`), demostrando que el patrón funciona.

---

## Plan de Implementación

### Fase 1: Preparación (5 minutos)

**Objetivo**: Entender el código existente y preparar el entorno

**Acciones**:
1. Revisar líneas 280-291 de `agent/main.py`
2. Confirmar que `get_mode_context_from_checkpoint` está importada
3. Verificar que el checkpointer está disponible en el scope

**Archivo**: `agent/main.py`

---

### Fase 2: Implementación del Fix (15 minutos)

**Objetivo**: Modificar `main.py` para cargar `mode_context` explícitamente

#### Cambio 1: Importar función (si no está importada)

**Ubicación**: Líneas 1-30 de `agent/main.py`

**Verificar que existe**:
```python
from agent.services.image_handling import (
    get_chatwoot_image_service,
    get_mode_context_from_checkpoint,  # ← Debe existir
)
```

**Si NO existe, agregar**:
```python
from agent.services.image_handling import get_mode_context_from_checkpoint
```

#### Cambio 2: Modificar construcción de state_input

**Ubicación**: Líneas 280-291 de `agent/main.py`

**Código ANTES**:
```python
            # Build initial state
            # Note: Only pass transient fields. Persistent fields like current_mode
            # will be restored from checkpoint (if exists) or initialized by router.
            state_input = {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "user_name": user_name,
                "user_message": user_message,
                "client_type": client_type,
                "messages": [],  # History loaded from checkpointer
                # current_mode intentionally NOT set here — let checkpoint restore it
            }
```

**Código DESPUÉS**:
```python
            # Build initial state
            # Note: Only pass transient fields. Persistent fields like current_mode
            # will be restored from checkpoint (if exists) or initialized by router.
            
            # ✅ FIX: Load mode_context from checkpoint to ensure context persistence
            # This prevents losing context (elements, pricing flags, etc.) between turns
            checkpointer = get_redis_checkpointer()
            existing_mode_context = await get_mode_context_from_checkpoint(
                checkpointer, conversation_id
            )
            
            state_input = {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "user_name": user_name,
                "user_message": user_message,
                "client_type": client_type,
                "messages": [],  # History loaded from checkpointer
                "mode_context": existing_mode_context or {},  # Ensure context persists
            }
```

**Notas de implementación**:
- El `checkpointer` ya está disponible en el scope (se usa en líneas 169, 267)
- Si queremos optimizar, podemos mover la obtención del checkpointer al inicio de la función
- El valor por defecto `{}` asegura que nunca sea `None`

---

### Fase 3: Optimización Opcional (10 minutos)

**Objetivo**: Evitar doble llamada al checkpointer cuando hay imágenes

**Ubicación**: Líneas 165-205 y 280-291 de `agent/main.py`

**Análisis**:
Actualmente, cuando hay imágenes, se obtiene el `mode_context` dos veces:
1. Líneas 169-173: Para manejo de imágenes
2. Líneas 283-286 (nuevo): Para el state_input

**Optimización sugerida** (opcional):
Mover la obtención del `mode_context` al inicio de `process_message()`:

```python
async def process_message(...):
    # ... código existente ...
    
    # ✅ OPTIMIZACIÓN: Obtener mode_context una sola vez
    checkpointer = get_redis_checkpointer()
    existing_mode_context = await get_mode_context_from_checkpoint(
        checkpointer, conversation_id
    )
    
    # Usar existing_mode_context tanto para imágenes como para state_input
    # ... resto del código ...
```

**Nota**: Esta optimización es OPCIONAL. El fix funciona sin ella, pero mejora la eficiencia.

---

### Fase 4: Agregar Logging de Debug (5 minutos)

**Objetivo**: Facilitar debugging futuro

**Ubicación**: Después de cargar el mode_context (líneas 283-286)

**Código a agregar**:
```python
            # Log para debugging
            logger.debug(
                "Loaded mode_context from checkpoint",
                extra={
                    "conversation_id": conversation_id,
                    "has_existing_context": existing_mode_context is not None,
                    "precio_comunicado": existing_mode_context.get("precio_comunicado") if existing_mode_context else None,
                }
            )
```

---

### Fase 5: Pruebas (20 minutos)

#### Test 1: Flujo Completo A/B
**Pasos**:
1. Enviar: "Holaaa quiero homologar el subchasis de mi moto"
2. Esperar respuesta con precio (410€) y opciones A/B
3. Verificar logs: `Loaded mode_context from checkpoint: has_existing_context=False`
4. Enviar: "A"
5. Verificar logs: `Loaded mode_context from checkpoint: has_existing_context=True, precio_comunicado=True`
6. Verificar que el agente envía las imágenes sin loop

**Resultado esperado**: ✅ Imágenes enviadas correctamente

#### Test 2: Primera Interacción
**Pasos**:
1. Iniciar conversación nueva
2. Enviar: "Hola"
3. Verificar que el agente responde correctamente
4. Verificar logs: `has_existing_context=False`

**Resultado esperado**: ✅ Conversación inicia correctamente

#### Test 3: Persistencia de Contexto
**Pasos**:
1. Identificar elemento "subchasis"
2. Verificar que el contexto tiene `elemento_confirmado`
3. Enviar mensaje de follow-up
4. Verificar que el agente recuerda el elemento

**Resultado esperado**: ✅ Contexto preservado

#### Test 4: Mode Transition
**Pasos**:
1. Estar en PRESUPUESTO_MODE
2. Iniciar expediente
3. Verificar que el modo cambia a EXPEDIENTE_MODE
4. Verificar que el contexto se preserva correctamente

**Resultado esperado**: ✅ Transición funciona correctamente

---

## Criterios de Aceptación

### Checklist de Verificación

- [ ] No hay errores de sintaxis
- [ ] Agente reinicia correctamente
- [ ] Primera interacción funciona (nueva conversación)
- [ ] Segunda interacción preserva contexto (conversación existente)
- [ ] Logs muestran `has_existing_context: True` en segundo turno
- [ ] Logs muestran `precio_comunicado: True` después de recibir precio
- [ ] Flujo A/B funciona: opción "A" envía imágenes sin loop
- [ ] No hay errores `mode_context is not defined`
- [ ] No hay errores `Attempt to send images without communicating price first` en loop
- [ ] Modo expediente funciona correctamente

### Logs Esperados

**Primer turno**:
```
Loaded mode_context from checkpoint: has_existing_context=False
contextvar_set_initial: precio_comunicado=None
new_quote_detected_resetting_flags: current_precio=None, new_precio=410.0
contextvar_synced_after_price_detection: precio_comunicado=True
```

**Segundo turno**:
```
Loaded mode_context from checkpoint: has_existing_context=True, precio_comunicado=True
contextvar_set_initial: precio_comunicado=True, waiting_for_image_choice=True
same_quote_preserve_flags: current_precio=410.0, precio_comunicado=True
```

---

## Rollback Plan

Si algo sale mal:

1. **Revertir cambios en `main.py`**:
   ```bash
   git checkout agent/main.py
   ```

2. **Reiniciar agente**:
   ```bash
   docker-compose restart agent
   ```

3. **Verificar estado**:
   ```bash
   docker-compose logs agent | tail -20
   ```

---

## Notas para el Implementador

### Consideraciones Importantes

1. **Fix 1 y Fix 2 permanecen intactos**: Este es un fix ADICIONAL en `main.py`, no reemplaza los fixes anteriores en `presupuesto_mode.py`

2. **No hay breaking changes**: Este cambio es aditivo, no modifica APIs ni firmas de métodos

3. **Consistencia con patrón existente**: Estamos extendiendo el patrón que ya funciona para imágenes (líneas 169-173)

4. **Logging**: Los logs de debug ayudarán a diagnosticar problemas futuros

### Potenciales Problemas y Soluciones

| Problema | Síntoma | Solución |
|----------|---------|----------|
| Checkpointer no disponible | Error `get_redis_checkpointer` no definido | Verificar importación en líneas 19-20 |
| Función no importada | Error `get_mode_context_from_checkpoint` no definido | Agregar importación de `image_handling` |
| Mode_context es None | Logs muestran `has_existing_context: None` | Asegurar fallback a `{}` en state_input |

---

## Timeline

| Fase | Tiempo Estimado | Total Acumulado |
|------|-----------------|-----------------|
| Fase 1: Preparación | 5 min | 5 min |
| Fase 2: Implementación | 15 min | 20 min |
| Fase 3: Optimización (opcional) | 10 min | 30 min |
| Fase 4: Logging | 5 min | 35 min |
| Fase 5: Pruebas | 20 min | 55 min |
| **TOTAL** | **55 min** | ~**1 hora** |

---

## Próximos Pasos

1. ✅ **APROBADO**: Plan validado por investigación técnica
2. ⏳ **SIGUIENTE**: Implementar Fase 2 (modificación de `main.py`)
3. ⏳ **DESPUÉS**: Ejecutar tests manuales
4. ⏳ **FINAL**: Verificar criterios de aceptación

---

## Referencias

- Investigación original: Ver reporte de `investigator-dev` (task_id: ses_3ccdf14a2ffe86WQ4CCQ93JySB)
- Patrón existente: `agent/main.py` líneas 169-173 (manejo de imágenes)
- Reducer: `agent/state/conversation_state.py` líneas 55-80 (`merge_dicts`)
- Función auxiliar: `agent/services/image_handling.py` líneas 115-138

---

**Arquitect**: Backend Agent  
**Fecha**: 6 de Febrero de 2026  
**Estado**: ✅ APROBADO - Listo para implementación
