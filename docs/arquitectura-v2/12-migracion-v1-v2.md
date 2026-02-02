# Plan de Migración v1 → v2

## 🎯 Resumen de la Migración

**Origen**: Arquitectura v1.0 (FSM lineal con IDLE monolítico)  
**Destino**: Arquitectura v2.0 (Grafo de 4 modos especializados)  
**Duración estimada**: 7 semanas  
**Riesgo**: Medio (cambio arquitectónico significativo pero componentes reciclables)

---

## 📊 Análisis de Impacto

### Qué se Recicla (Bajo riesgo)

| Componente | Esfuerzo de migración | Notas |
|------------|----------------------|-------|
| `tarifa_service.py` | Ninguno | Funciona igual en PRESUPUESTO_MODE |
| `element_service.py` | Ninguno | Usado en VIABILIDAD y PRESUPUESTO |
| `collection_mode.py` | Ninguno | EXPEDIENTE_MODE lo usa igual |
| `constraint_service.py` | Ninguno | Aplica a todos los modos |
| `validation.py` | Ninguno | Validaciones persisten |
| `image_tools.py` | Menor | Solo cambia cuándo se llama |
| `prompts/core/*.md` | Menor | Core se mantiene |

### Qué se Refactoriza (Riesgo medio)

| Componente | Esfuerzo | Cambio principal |
|------------|----------|------------------|
| `fsm/case_collection.py` | 3 días | De FSM lineal a modos con sub-modos |
| `tools/tool_manager.py` | 2 días | Mapear herramientas a modos, no solo fsm_state |
| `prompts/loader.py` | 2 días | Agregar prompts de modo a PHASE_MODULES |
| `prompts/phases/*.md` | 4 días | Nuevos prompts por cada modo |
| `conversational_agent.py` | 3 días | Lógica de entry point y modo switching |

### Qué se Crea Nuevo (Alto riesgo - requiere testing)

| Componente | Esfuerzo | Complejidad |
|------------|----------|-------------|
| `intent_classifier.py` | 3 días | Clasificador de intención con modelo ligero |
| `mode_transitions.py` | 2 días | Lógica de transición entre modos |
| `timeout_manager.py` | 2 días | Gestión de timeouts por modo |
| `retry_policy.py` | 1 día | Política de reintentos por modo |
| Nuevas herramientas | 3 días | ~5 herramientas nuevas por modo |

---

## 🗓️ Plan de Implementación por Fases

### Fase 0: Preparación (Semana 0)

**Objetivo**: Preparar infraestructura y documentación

**Tareas**:
- [ ] Setup de feature flags (v1/v2 switch)
- [ ] Tests de integración existentes pasando
- [ ] Documentación v2 aprobada por equipo
- [ ] Definir métricas de éxito (conversion rate, satisfacción, etc.)

**Entregable**: Branch `feature/v2-migration` lista para desarrollo

---

### Fase 1: Componentes Base (Semana 1)

**Objetivo**: Crear componentes transversales nuevos

**Días 1-2: Intent Classifier**
```python
# Crear agent/services/intent_classifier.py
# - Modelo ligero (qwen2.5:3b) para clasificación rápida
# - Threshold 0.75
# - Tests unitarios
```

**Días 3-4: Timeout Manager**
```python
# Crear agent/services/timeout_manager.py
# - MODE_TIMEOUTS configuración
# - Lógica de nudge y reset
# - Tests unitarios
```

**Día 5: Retry Policy**
```python
# Crear agent/services/retry_policy.py
# - MODE_RETRY_POLICIES
# - Lógica de acciones por límite
# - Tests unitarios
```

**Entregable**: Servicios base implementados y testeados (no integrados)

---

### Fase 2: Modos Consulta + Viabilidad (Semana 2)

**Objetivo**: Implementar dos modos iniciales con transiciones

**Días 1-2: CONSULTA_MODE**
- [ ] Crear prompt `prompts/phases/consulta_mode.md`
- [ ] Definir herramientas del modo
- [ ] Implementar lógica del modo
- [ ] Tests de integración

**Días 3-4: VIABILIDAD_MODE**
- [ ] Crear prompt `prompts/phases/viabilidad_mode.md`
- [ ] Definir herramientas del modo
- [ ] Implementar lógica del modo
- [ ] Tests de integración

**Día 5: Transiciones**
- [ ] Implementar transiciones CONSULTA ↔ VIABILIDAD
- [ ] Tests de transición

**Entregable**: Modos CONSULTA y VIABILIDAD funcionando con transiciones

---

### Fase 3: Modo Presupuesto + Gateway (Semana 3)

**Objetivo**: Completar flujo de presupuesto con decisión

**Días 1-2: PRESUPUESTO_MODE**
- [ ] Crear prompt `prompts/phases/presupuesto_mode.md`
- [ ] Adaptar herramientas existentes (reciclar de v1)
- [ ] Implementar lógica de loop (agregar/quitar elementos)
- [ ] Tests de integración

**Días 3-4: EVALUACIÓN_GATEWAY**
- [ ] Crear estado bloqueante de confirmación
- [ ] Lógica de sí/no explícito
- [ ] Tests de validación

**Día 5: Integración y transiciones**
- [ ] Transiciones desde VIABILIDAD
- [ ] Transiciones hacia EXPEDIENTE (mock)

**Entregable**: Flujo completo hasta confirmación de presupuesto

---

### Fase 4: Modo Expediente (Semana 4)

**Objetivo**: Implementar recolección de datos formal

**Días 1-2: Sub-modos de datos**
- [ ] DATOS_PERSONALES sub-modo
- [ ] DATOS_VEHICULO sub-modo
- [ ] Transiciones entre ellos

**Días 3-4: Sub-modos de documentación**
- [ ] DOC_ELEMENTOS (reciclar lógica v1)
- [ ] DOC_BASE (reciclar lógica v1)

**Día 5: Taller y Revisión**
- [ ] TALLER sub-modo
- [ ] REVISION sub-modo
- [ ] Finalización

**Entregable**: EXPEDIENTE_MODE completo con todos los sub-modos

---

### Fase 5: Integración de Gaps (Semana 5)

**Objetivo**: Integrar soluciones a gaps críticos

**Días 1-2: Timeouts**
- [ ] Integrar timeout_manager en entry point
- [ ] Configurar timeouts por modo
- [ ] Mensajes de nudge personalizados

**Días 3-4: Reintentos**
- [ ] Integrar retry_policy en cada modo
- [ ] Configurar políticas por modo
- [ ] Acciones al alcanzar límites

**Día 5: NLU + Testing**
- [ ] Integrar intent_classifier en entry point
- [ ] Tests end-to-end de clasificación
- [ ] Fallbacks funcionando

**Entregable**: Sistema completo v2 con todos los mecanismos de robustez

---

### Fase 6: Testing y Validación (Semana 6)

**Objetivo**: Testing exhaustivo y paralelo con v1

**Días 1-2: Tests unitarios**
- [ ] Cobertura >80% de nuevos componentes
- [ ] Tests de transiciones
- [ ] Tests de edge cases

**Días 3-4: Tests de integración**
- [ ] Flujos completos de conversación
- [ ] Escenarios de error
- [ ] Escenarios de timeout

**Día 5: Pruebas A/B (opcional)**
- [ ] 10% de tráfico a v2
- [ ] Métricas: conversión, satisfacción, tiempo
- [ ] Rollback plan definido

**Entregable**: Sistema testeado, listo para rollout

---

### Fase 7: Rollout y Monitoreo (Semana 7)

**Objetivo**: Despliegue gradual y monitoreo

**Rollout gradual**:
- [ ] Día 1: 25% de tráfico
- [ ] Día 2: 50% de tráfico
- [ ] Día 3: 75% de tráfico
- [ ] Día 4: 100% de tráfico

**Monitoreo**:
- [ ] Dashboard de errores por modo
- [ ] Métricas de conversión comparadas con v1
- [ ] Alertas de timeout/reintentos
- [ ] Feedback de usuarios

**Rollback plan**:
- [ ] Feature flag para revertir a v1 en <5 minutos
- [ ] Datos de v2 compatibles con v1 (o migración definida)

**Entregable**: v2 en producción, v1 en modo mantenimiento

---

## 🔧 Estrategia de Implementación

### Feature Flags

```python
# En config.py
class MigrationConfig:
    USE_V2_ARCHITECTURE = True  # Master switch
    
    # Flags por modo (para rollout gradual)
    V2_CONSULTA_MODE = True
    V2_VIABILIDAD_MODE = True
    V2_PRESUPUESTO_MODE = True
    V2_EXPEDIENTE_MODE = True
    
    # Flags de mecanismos
    V2_INTENT_CLASSIFIER = True
    V2_TIMEOUTS = True
    V2_RETRY_POLICY = True
```

### Entry Point con Fallback

```python
async def conversation_entry(state: ConversationState):
    if not MigrationConfig.USE_V2_ARCHITECTURE:
        return await v1_entry_point(state)
    
    try:
        return await v2_entry_point(state)
    except Exception as e:
        logger.error(f"V2 failed, falling back to V1: {e}")
        return await v1_entry_point(state)
```

### Datos Compatibles

```python
# ConversationState v2 es superset de v1
class ConversationState(TypedDict, total=False):
    # Campos v1 (mantener para compatibilidad)
    fsm_state: dict[str, Any] | None  # Legacy, usado en transición
    
    # Campos v2 (nuevos)
    current_mode: str  # Modo actual
    mode_entry_timestamp: datetime
    mode_retry_counts: dict[str, int]
    last_activity_timestamp: datetime
    intent_classification: IntentResult | None
```

---

## 📈 Métricas de Éxito

### Métricas Técnicas

| Métrica | v1 Actual | Objetivo v2 | Cómo medir |
|---------|-----------|-------------|------------|
| **Conversaciones huérfanas** | ? | <5% | Timeout tracking |
| **Bucles de validación** | ? | 0 | Retry limit alcanzado |
| **Tiempo promedio** | ? | Similar o menor | Analytics |
| **Errores 500** | ? | Igual o menor | Logs |

### Métricas de Negocio

| Métrica | v1 Actual | Objetivo v2 | Cómo medir |
|---------|-----------|-------------|------------|
| **Tasa de conversión** | ? | +10% | Casos completados / conversaciones |
| **Satisfacción usuario** | ? | +15% | Feedback post-conversación |
| **Escalaciones** | ? | -20% | Casos escalados / total |
| **Abandono** | ? | -15% | Conversaciones sin completar |

---

## ⚠️ Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| **Regresión en conversión** | Media | Alto | Feature flags + rollback rápido |
| **Problemas de NLU** | Media | Alto | Threshold conservador + fallback a v1 |
| **Timeout muy agresivo** | Baja | Medio | Configuración gradual, empezar conservador |
| **Complejidad de modo** | Media | Medio | Documentación clara + training equipo |
| **Datos corruptos en migración** | Baja | Alto | Backward compatibility + tests |

---

## 🎓 Capacitación del Equipo

### Para desarrolladores
- [ ] Workshop: Arquitectura v2 (2 horas)
- [ ] Code review de componentes nuevos
- [ ] Documentación de troubleshooting por modo

### Para operaciones
- [ ] Guía de diagnóstico por modo
- [ ] Dashboard de monitoreo v2
- [ ] Playbook de rollback

### Para negocio
- [ ] Demo de flujos nuevos
- [ ] Guía de interpretación de métricas
- [ ] Proceso de ajuste de timeouts/reintentos

---

## 📁 Checklist de Go-Live

- [ ] Todos los tests pasando (>80% cobertura)
- [ ] Feature flags configurados
- [ ] Rollback plan documentado y probado
- [ ] Dashboard de monitoreo listo
- [ ] Equipo capacitado
- [ ] Métricas baseline de v1 registradas
- [ ] Runbook de troubleshooting
- [ ] Comunicación a stakeholders

---

**Nota**: Este plan es una guía. Ajustar según complejidad real encontrada durante desarrollo.
