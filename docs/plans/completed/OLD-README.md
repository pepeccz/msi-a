# Plan de Migración v1.0 → v2.0 - Índice Maestro

## 📋 Resumen Ejecutivo

**Estrategia**: Big Bang (eliminación total v1.0, sin coexistencia)  
**Prioridad**: VIABILIDAD_MODE primero (65% tráfico)  
**Duración**: 8-10 semanas con IA asistida  
**Metodología**: 6 fases, Digression Manager desde Fase 1

---

## 📁 Documentos del Plan

### Plan General
| Documento | Contenido | Estado |
|-----------|-----------|--------|
| [migracion-v1-v2-bigbang.md](migracion-v1-v2-bigbang.md) | Visión general, qué eliminar, qué reciclar, estructura nueva | ✅ Completo |

### Fases Detalladas
| Fase | Documento | Enfoque | Estado |
|------|-----------|---------|--------|
| Fase 1 | [fase-1-foundation.md](fase-1-foundation.md) | State, Router, Fallback, Digression Manager | ✅ Completo |
| Fase 2 | [fase-2-viabilidad-mode.md](fase-2-viabilidad-mode.md) | VIABILIDAD_MODE (65% tráfico) | ✅ Completo |
| Fase 3 | fase-3-consulta-mode.md | CONSULTA_MODE (10% - simple) | ⏳ Pendiente |
| Fase 4 | fase-4-presupuesto-mode.md | PRESUPUESTO_MODE + EVALUACION_GATEWAY | ⏳ Pendiente |
| Fase 5 | fase-5-expediente-mode.md | EXPEDIENTE_MODE (rediseño completo) | ⏳ Pendiente |
| Fase 6 | fase-6-integracion-testing.md | Big Bang, eliminación v1, deploy | ⏳ Pendiente |

---

## 🎯 Decisones Clave Tomadas

### 1. Big Bang vs Feature Flags
**Decisión**: Big Bang (Opción B)  
**Justificación**: Evita mantener dos sistemas, fuerza a completar la migración.

### 2. System Prompt Dinámico
**Decisión**: Nueva estructura `agent/v2/prompts/`  
- Core modules reciclados (8 archivos)
- Mode modules nuevos (9 prompts por modo)
- Loader v2 nuevo

### 3. EXPEDIENTE_MODE: Reciclar o Rediseñar
**Decisión**: Rediseño COMPLETO  
- FSM v1 eliminado por completo
- Nueva estructura de sub-modos
- Nuevo servicio de expediente

### 4. Prioridad de Implementación
**Decisión**: VIABILIDAD_MODE primero (65% tráfico)  
Pero hacer los 4 modos en orden:
1. VIABILIDAD_MODE (Fase 2)
2. CONSULTA_MODE (Fase 3)
3. PRESUPUESTO_MODE (Fase 4)
4. EXPEDIENTE_MODE (Fase 5)

### 5. Digression Manager
**Decisión**: Fase 1 (desde el inicio)  
Implementación: Option B (Parallel listener nativo de LangGraph)

---

## 🗑️ ELIMINAR (Sin Rastro)

### Directorios Completos
```
agent/fsm/                          # FSM lineal completo
agent/prompts/phases/               # Prompts por fases v1
agent/prompts/core/09_fsm_awareness.md
agent/routing/                      # Placeholder vacío
```

### Archivos Específicos
```
agent/fsm/case_collection.py
agent/fsm/__init__.py

agent/prompts/phases/idle_quotation.md
agent/prompts/phases/collect_element_data.md
agent/prompts/phases/collect_base_docs.md
agent/prompts/phases/collect_personal.md
agent/prompts/phases/collect_vehicle.md
agent/prompts/phases/collect_workshop.md
agent/prompts/phases/review_summary.md
agent/prompts/phases/completed.md

agent/graphs/conversation_flow.py
agent/nodes/conversational_agent.py
agent/nodes/process_message.py

agent/services/prompt_service.py
agent/services/collection_mode.py → Reemplazar por element_collection_service.py

agent/tools/case_tools.py
agent/tools/element_data_tools.py → Reemplazar por element_collection_tools.py
agent/tools/tool_manager.py
```

---

## ♻️ RECICLAR (Adaptar)

### Servicios (100% reciclaje, sin cambios de API)
```
agent/services/tarifa_service.py
agent/services/element_service.py
agent/services/constraint_service.py
agent/services/tool_logging_service.py
agent/services/token_tracking.py
agent/services/element_required_fields_service.py
```

### Tools (Reciclar con adaptaciones menores)
```
agent/tools/element_tools.py:
  - identificar_y_resolver_elementos
  - seleccionar_variante_por_respuesta
  - listar_categorias, listar_elementos
  - buscar_elemento_por_nombre, obtener_elemento_por_codigo

agent/tools/tarifa_tools.py:
  - obtener_tarifas_por_categoria
  - obtener_servicios_adicionales
  - obtener_documentacion_elemento

agent/tools/image_tools.py:
  - enviar_imagenes_ejemplo

agent/tools/vehicle_tools.py:
  - identificar_tipo_vehiculo
```

### Prompts Core (Reciclar contenido)
```
agent/prompts/core/01_security.md → agent/v2/prompts/core/01_security.md
agent/prompts/core/02_identity.md → agent/v2/prompts/core/02_identity.md
agent/prompts/core/03_format_style.md → agent/v2/prompts/core/03_format_style.md
agent/prompts/core/04_anti_patterns.md → agent/v2/prompts/core/04_anti_patterns.md
agent/prompts/core/05_tools_efficiency.md → agent/v2/prompts/core/05_tools_efficiency.md
agent/prompts/core/06_escalation.md → agent/v2/prompts/core/06_escalation.md
agent/prompts/core/07_pricing_rules.md → agent/v2/prompts/core/07_pricing_rules.md
agent/prompts/core/08_documentation.md → agent/v2/prompts/core/08_documentation.md
# ELIMINAR: 09_fsm_awareness.md
```

### Utilidades (100% reciclaje)
```
agent/utils/validation.py
agent/utils/text_utils.py
agent/utils/errors.py
agent/utils/tool_helpers.py
agent/state/helpers.py
agent/state/checkpointer.py
```

---

## 🆕 CREAR (Nuevo en v2.0)

### Estructura de Directorios
```
agent/v2/
├── __init__.py
├── state/
│   ├── __init__.py
│   ├── conversation_state_v2.py      # Nuevo schema
│   ├── retry_state.py                # Retry tracking
│   └── mode_context.py               # Contexto por modo
├── router/
│   ├── __init__.py
│   ├── intent_router.py              # Clasificador
│   ├── digression_manager.py         # Parallel listener
│   └── mode_transitions.py           # Reglas
├── fallback/
│   ├── __init__.py
│   └── fallback_handler.py           # Centralizado
├── modes/
│   ├── __init__.py
│   ├── base_mode.py                  # Clase base
│   ├── consulta_mode.py
│   ├── viabilidad_mode.py
│   ├── presupuesto_mode.py
│   ├── evaluacion_gateway.py
│   └── expediente_mode.py            # + submodos/
├── prompts/
│   ├── __init__.py
│   ├── loader_v2.py                  # Loader dinámico
│   ├── core/                         # Copiado de prompts/core/
│   └── modes/                        # NUEVOS: 9 archivos
├── tools/
│   ├── __init__.py
│   ├── consulta_tools.py
│   ├── viabilidad_tools.py
│   ├── presupuesto_tools.py
│   ├── expediente_tools.py
│   └── shared_tools.py
├── graph/
│   ├── __init__.py
│   └── conversation_graph_v2.py      # StateGraph v2
└── main_v2.py                        # Entry point

tests/v2/                             # Tests de todos los módulos
```

---

## 📊 Timeline de Fases

### FASE 1: Foundation (2 semanas)
**Output**: Módulos testeables independientes
- [x] `conversation_state_v2.py` - Schema completo
- [x] `intent_router.py` - Clasificador (6 intenciones, threshold 0.75)
- [x] `digression_manager.py` - Option B, parallel listener
- [x] `fallback_handler.py` - Retry policies por modo
- [x] `base_mode.py` - Clase base abstracta
- [x] `loader_v2.py` - Dynamic prompt assembly
- [x] Core prompts copiados

**Tests**: `tests/v2/test_*.py`

### FASE 2: VIABILIDAD_MODE (1.5 semanas)
**Output**: Modo funcional, integrado al grafo
- [x] `viabilidad_mode.py` - Nodo completo
- [x] `viabilidad_mode.md` - System prompt
- [x] `viabilidad_tools.py` - Tools específicas
- [x] Integración al grafo v2

**Tests**: E2E de flujos completos

### FASE 3: CONSULTA_MODE (1 semana)
**Output**: Modo simple para validar arquitectura
- [ ] `consulta_mode.py`
- [ ] `consulta_mode.md`
- [ ] `consulta_tools.py`

### FASE 4: PRESUPUESTO_MODE (1.5 semanas)
**Output**: Modo presupuesto + gateway
- [ ] `presupuesto_mode.py`
- [ ] `evaluacion_gateway.py`
- [ ] Prompts y tools

### FASE 5: EXPEDIENTE_MODE (2 semanas)
**Output**: Rediseño completo de expediente
- [ ] `expediente_mode.py` + submodos/
- [ ] Nuevo servicio de expediente
- [ ] ELIMINAR: `agent/fsm/` completo

### FASE 6: Big Bang (2 semanas)
**Output**: v1 eliminado, v2 en producción
- [ ] Eliminar TODOS los archivos v1
- [ ] Actualizar `agent/main.py` dispatcher
- [ ] Tests E2E completos
- [ ] Deploy con rollback plan

---

## 🎨 System Prompt Dinámico v2.0

### Estructura
```
1. CORE (siempre)
   ├── 01_security.md
   ├── 02_identity.md
   ├── 03_format_style.md
   ├── 04_anti_patterns.md
   ├── 05_tools_efficiency.md
   ├── 06_escalation.md
   ├── 07_pricing_rules.md
   └── 08_documentation.md

2. MODE-SPECIFIC (uno por conversación)
   ├── consulta_mode.md          ← 10%
   ├── viabilidad_mode.md        ← 65%
   ├── presupuesto_mode.md       ← 25%
   ├── evaluacion_gateway.md
   └── expediente_*.md           ← 6 prompts

3. MODE CONTEXT (dinámico)
   └── Estado actual del modo

4. CONVERSATION HISTORY
   └── Últimos N mensajes
```

### Loader v2
```python
# agent/v2/prompts/loader_v2.py

MODE_MODULES = {
    "CONSULTA_MODE": "modes/consulta_mode.md",
    "VIABILIDAD_MODE": "modes/viabilidad_mode.md",
    "PRESUPUESTO_MODE": "modes/presupuesto_mode.md",
    "EVALUACION_GATEWAY": "modes/evaluacion_gateway.md",
    "EXPEDIENTE_DATOS_PERSONALES": "modes/expediente_datos_personales.md",
    # ... etc
}

def assemble_system_prompt_v2(mode, mode_context, history, tools):
    parts = [
        load_core_modules(),
        load_mode_module(mode),
        format_tools_section(tools),
        format_mode_context(mode_context),
        format_history(history),
    ]
    return "\n\n---\n\n".join(parts)
```

---

## ✅ Checklist Global

### Pre-Implementación
- [x] Plan completo creado (este documento)
- [ ] Aprobación de arquitectura por equipo
- [ ] Definición de tests de aceptación por modo
- [ ] Setup de environment de desarrollo v2

### Por Fase
- [ ] Fase 1: Todos los tests pasan
- [ ] Fase 2: VIABILIDAD_MODE funciona E2E
- [ ] Fase 3: CONSULTA_MODE funciona E2E
- [ ] Fase 4: PRESUPUESTO_MODE funciona E2E
- [ ] Fase 5: EXPEDIENTE_MODE funciona E2E
- [ ] Fase 6: Big Bang ejecutado exitosamente

### Post-Implementación
- [ ] Métricas de fallback < 15%
- [ ] Tasa de escalación estable o mejorada
- [ ] Documentación de operaciones actualizada
- [ ] Equipo de soporte entrenado en nuevos modos

---

## 🚀 Comandos para IA

```bash
# Setup inicial
mkdir -p agent/v2/{state,router,fallback,modes,prompts/{core,modes},tools,graph}
mkdir -p tests/v2

# Copiar core prompts
cp agent/prompts/core/0{1..8}*.md agent/v2/prompts/core/
# (no copiar 09_fsm_awareness.md)

# Fase 1 - Tests
pytest tests/v2/test_state_v2.py -v
pytest tests/v2/test_intent_router.py -v
pytest tests/v2/test_digression_manager.py -v
pytest tests/v2/test_fallback_handler.py -v

# Fase 2 - Tests
pytest tests/v2/test_viabilidad_mode.py -v
pytest tests/v2/e2e/test_viabilidad_flows.py -v
```

---

## 📈 Métricas de Éxito

| Métrica | Objetivo |
|---------|----------|
| Fallback rate por modo | < 15% |
| Tasa de escalación | Estable o -20% |
| Tiempo promedio conversación | Similar o mejor |
| Tasa de conversión (viabilidad→presupuesto) | +10% |
| Tasa de conversión (presupuesto→expediente) | +5% |

---

## 📞 Contacto y Decisiones Pendientes

Si surge alguna duda durante la implementación:

1. **¿Eliminar o reciclar?** → Revisar sección ♻️ de este documento
2. **¿Cómo implementar X?** → Revisar documento de fase específica
3. **¿Prioridad de features?** → VIABILIDAD > PRESUPUESTO > CONSULTA > EXPEDIENTE
4. **¿Dudas de arquitectura?** → Consultar `docs/arquitectura-v2/`

---

**Estado del Plan**: 33% completado (Fases 1-2 documentadas)  
**Próximo paso**: Crear documentos de Fases 3-6 o empezar implementación de Fase 1  
**Fecha de Plan**: Febrero 2026
