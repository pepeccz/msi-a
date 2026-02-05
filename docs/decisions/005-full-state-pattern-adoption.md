# ADR-005: Adopción del Full State Pattern en PRESUPUESTO_MODE

**Fecha**: 5 de Febrero de 2026  
**Estado**: Aceptado  
**Decisores**: Architect, Agent-dev  
**Relacionado con**: ADR-002 (Dynamic Prompts), ADR-004 (Fix Presupuesto Corrupted Text)

---

## Contexto

MSI-a v2.0 usa una arquitectura mode-based donde cada mode tiene su propio contexto local (`mode_context`) que persiste durante la conversación. Los tools acceden al estado vía ContextVars.

### Problema Detectado

El agente rechazaba enviar imágenes de ejemplo después de calcular correctamente el presupuesto:

**Flujo usuario**:
1. Usuario: "Holaaa quiero homologar el subchasis de mi moto"
2. Agente: "El presupuesto es de 410€ +IVA. (...) ¿Quieres A) fotos o B) expediente?"
3. Usuario: "A"
4. Agente: "Disculpa, primero necesito calcular el presupuesto (...)" ← ❌ ERROR

**Root Cause**:
- `PRESUPUESTO_MODE` detectaba el precio en la respuesta del LLM
- Actualizaba `mode_context["precio_comunicado"] = True`
- Tool `enviar_imagenes_ejemplo` buscaba `state["price_communicated_to_user"]` en el root state
- Como NO existía → Tool rechazaba el envío

**Evidencia de logs**:
```
17:41:23 [tool_call] enviar_imagenes_ejemplo
17:41:23 [WARNING] No tarifa_actual in state
17:41:30 [constraint_violation] price_requires_tool
```

### Inconsistencia Arquitectónica

**EXPEDIENTE_MODE** (línea 428) ya usaba el patrón correcto:
```python
full_state = {**cast(dict[str, Any], state), **mode_context}
set_current_state(full_state)
```

**PRESUPUESTO_MODE** (línea 120) NO lo usaba:
```python
state_dict = cast(dict[str, Any], state)
set_current_state(state_dict)  # ← mode_context NO incluido
```

Esto causaba que tools en PRESUPUESTO no pudieran acceder a datos en `mode_context`.

---

## Decisión

**Adoptar el Full State Pattern en PRESUPUESTO_MODE** para unificar la arquitectura:

1. **Pasar `mode_context` completo a tools** vía ContextVars
2. **Eliminar duplicación de datos** entre `mode_context` y root state
3. **Unificar nomenclatura** (español consistente en mode_context)
4. **Single source of truth**: Datos viven en `mode_context`, NO en root state

### Cambios Implementados

**5 cambios en 2 archivos**:

1. **PRESUPUESTO_MODE**: Adoptar full_state pattern (línea 117-122)
2. **IMAGE_TOOLS**: Leer `tarifa_calculada` desde mode_context (línea 166-214)
3. **IMAGE_TOOLS**: Protección duplicados desde mode_context (línea 135-137)
4. **PRESUPUESTO_MODE**: Eliminar propagación de `tarifa_actual` (línea 279-283)
5. **PRESUPUESTO_MODE**: Cleanup `extract_context_from_tool` (línea 448-452)

---

## Consecuencias

### Positivas

✅ **Arquitectura unificada**: PRESUPUESTO y EXPEDIENTE usan el mismo patrón  
✅ **Escalabilidad automática**: Nuevos campos en mode_context son automáticamente visibles para tools  
✅ **No duplicación**: Datos viven en UN solo lugar (mode_context)  
✅ **Nomenclatura consistente**: Español en mode_context, inglés en código  
✅ **Mantenibilidad**: Futuros desarrolladores entienden la arquitectura fácilmente  
✅ **Fix del bug**: Usuario puede pedir imágenes sin error  

### Negativas

⚠️ **Cambios en 2 archivos críticos**: Riesgo de regresiones (mitigado con tests)  
⚠️ **Testing extenso requerido**: Verificar que no se rompen otros flows  
⚠️ **Breaking change interno**: Tools que buscaban en root state deben adaptarse (solo image_tools afectado)  

### Neutras

→ **LSP warnings pre-existentes**: No introducidos por este cambio  
→ **Compatibilidad con checkpointer**: No afecta persistencia en Redis  
→ **Otros modes**: No afectados (CONSULTA, VIABILIDAD solo leen, no escriben estos flags)  

---

## Alternativas Consideradas

### Opción 1: Propagar flags al root state (Rechazada)

**Pros**: Cambio mínimo (3 líneas)  
**Contras**: Duplicación de datos, no escalable, deuda técnica  
**Razón de rechazo**: Usuario priorizó "sistema más abierto a futuras modificaciones"

### Opción 2: Full State Pattern (Aceptada)

**Pros**: Arquitectura limpia, escalable, consistente  
**Contras**: Más cambios (5), testing extenso  
**Razón de aceptación**: Mejor arquitectura a largo plazo

### Opción 3: Unificar todo en root state (Rechazada)

**Pros**: Simplicidad conceptual  
**Contras**: Rompe arquitectura mode-based, mode_context pierde propósito  
**Razón de rechazo**: Va contra el diseño de v2.0

---

## Verificación

### Tests Requeridos

- [ ] **Unit**: `test_presupuesto_passes_mode_context_to_tools`
- [ ] **Unit**: `test_enviar_imagenes_ejemplo_reads_from_mode_context`
- [ ] **Integration**: `test_user_flow_presupuesto_to_images_e2e`
- [ ] **Manual**: Flujo completo en desarrollo con Chatwoot

### Criterios de Aceptación

- [x] Código implementado según especificación
- [x] Comentarios explicativos agregados
- [x] Nomenclatura consistente (español en mode_context)
- [ ] Tests pasan (pending)
- [ ] No regresiones detectadas (pending)

---

## Implementación

**Commits**:
1. `refactor(agent): implement full_state pattern in PRESUPUESTO_MODE`
2. `refactor(agent): update image_tools to read from mode_context`
3. `docs(decisions): add ADR-005 full_state pattern adoption`

**Archivos modificados**:
- `agent/modes/presupuesto_mode.py` (~30 líneas)
- `agent/tools/image_tools.py` (~35 líneas)

**Líneas totales**: ~65 líneas cambiadas

---

## Siguientes Pasos

### Corto Plazo (1-2 semanas)

- [ ] Monitorear logs en producción
- [ ] Recopilar feedback de usuarios
- [ ] Verificar tasa de éxito de envío de imágenes

### Mediano Plazo (1 mes)

- [ ] Evaluar aplicar pattern a otros modes si existen
- [ ] Refactor para eliminar flags legacy de root state
- [ ] Actualizar documentación de desarrollo

### Largo Plazo (3 meses)

- [ ] ADR-006: Unificar nomenclatura a inglés en root state
- [ ] Migrar todos los modes a full_state pattern
- [ ] Suite de tests arquitectónicos

---

## Referencias

- **Plan**: `docs/plans/fix-precio-comunicado-full-state-pattern.md`
- **AGENTS.md**: `agent/AGENTS.md` (Mode-Based Architecture)
- **Coding Standards**: `docs/coding-standards/03-agent-architecture.md`
- **Patrón establecido**: EXPEDIENTE_MODE línea 428
- **Issue reportado**: Usuario en conversación Chatwoot (5 Feb 2026)

---

## Notas

### Datos Migrados de Root State a mode_context

| Dato (Antes en root)          | Dato (Ahora en mode_context) |
| ----------------------------- | ---------------------------- |
| `tarifa_actual`                 | `tarifa_calculada`             |
| `price_communicated_to_user`    | `precio_comunicado`            |
| `images_sent_for_current_quote` | `imagenes_enviadas`            |

### Patrón Aplicable a Otros Modes

Este patrón es replicable en cualquier mode que necesite pasar `mode_context` completo a tools:

```python
# En cualquier mode node:
full_state = {**cast(dict[str, Any], state), **mode_context}
set_current_state(full_state)
set_current_state_for_image_tools(full_state)

# En cualquier tool:
mode_context = state.get("mode_context", {})
my_flag = mode_context.get("my_flag", False)
```

---

**Autor**: Architect Agent  
**Implementado por**: Agent-dev  
**Revisado por**: Usuario  
**Fecha de aprobación**: 5 de Febrero de 2026
