# Arquitectura de Conversación v2.0 - Índice

## 📚 Documentación Completa

Esta carpeta contiene la **arquitectura de conversación v2.0** del agente MSI-a, rediseñada desde cero para reflejar la realidad del negocio.

### 🎯 Propósito del Rediseño

La arquitectura v1.0 tenía un **estado IDLE monolítico** que intentaba hacer todo (consultas, presupuestos, viabilidad, expedientes). Esto generaba confusión.

La v2.0 propone **4 modos especializados**:

| Modo | % Tráfico | Propósito |
|------|-----------|-----------|
| **CONSULTA_MODE** | 10% | Educar y responder dudas generales |
| **VIABILIDAD_MODE** | 65% | Evaluar si se puede homologar |
| **PRESUPUESTO_MODE** | 25% | Calcular precios exactos |
| **EXPEDIENTE_MODE** | Conversión | Recolectar datos formales |

---

## 📁 Estructura de Documentos

### Documentos Maestros

| Archivo | Contenido |
|---------|-----------|
| [00-propuesta-maestra.md](00-propuesta-maestra.md) | Visión general y propuesta de alto nivel |
| [01-filosofia-arquitectura.md](01-filosofia-arquitectura.md) | Principios y decisiones arquitectónicas |
| [02-modos-overview.md](02-modos-overview.md) | Comparativa de los 4 modos |

### Documentos por Modo (Detalle Completo)

| Archivo | Modo | % Tráfico | Complejidad |
|---------|------|-----------|-------------|
| [03-modo-consulta.md](03-modo-consulta.md) | CONSULTA_MODE | 10% | Baja |
| [04-modo-viabilidad.md](04-modo-viabilidad.md) | VIABILIDAD_MODE | **65%** | Media |
| [05-modo-presupuesto.md](05-modo-presupuesto.md) | PRESUPUESTO_MODE | 25% | Media-Alta |
| [06-modo-expediente.md](06-modo-expediente.md) | EXPEDIENTE_MODE | - | Alta |

Cada documento de modo incluye:
- ✅ Propósito y alcance detallado
- ✅ Herramientas disponibles (entrada/salida especificaciones)
- ✅ Modelos de datos de base de datos utilizados
- ✅ Reglas de negocio críticas
- ✅ Políticas de timeout y reintentos
- ✅ Transiciones permitidas/prohibidas
- ✅ Casos de uso con ejemplos de conversación
- ✅ Prompt del sistema para el modo

### Documentos Técnicos

| Archivo | Contenido |
|---------|-----------|
| [07-transiciones-grafo.md](07-transiciones-grafo.md) | Matriz completa de transiciones entre modos |
| [09-solucion-gaps.md](09-solucion-gaps.md) | Soluciones a gaps críticos identificados |
| [12-migracion-v1-v2.md](12-migracion-v1-v2.md) | Plan de migración de 7 semanas |
| [14-fallback-handler.md](14-fallback-handler.md) | **NUEVO**: Manejo de errores y recuperación por modo |

---

## 🚀 Cómo Usar Esta Documentación

### Para Entender la Arquitectura
1. Empezar por [00-propuesta-maestra.md](00-propuesta-maestra.md)
2. Leer [01-filosofia-arquitectura.md](01-filosofia-arquitectura.md)
3. Revisar [02-modos-overview.md](02-modos-overview.md)
4. Profundizar en modos específicos según interés

### Para Implementar
1. Revisar [12-migracion-v1-v2.md](12-migracion-v1-v2.md) para plan
2. Leer documento de modo específico que se va a implementar
3. Verificar [07-transiciones-grafo.md](07-transiciones-grafo.md) para conectividad
4. Revisar [09-solucion-gaps.md](09-solucion-gaps.md) para mecanismos de robustez

### Para Onboarding de Equipo
1. [01-filosofia-arquitectura.md](01-filosofia-arquitectura.md) - Visión conceptual
2. [02-modos-overview.md](02-modos-overview.md) - Comparativa rápida
3. Modos individuales según área de trabajo

---

## 🎓 Diferencias Clave v1 vs v2

| Aspecto | v1.0 | v2.0 |
|---------|------|------|
| **Estructura** | FSM lineal (IDLE → ELEMENTS → ... → COMPLETED) | Grafo de modos (navegable) |
| **Estado inicial** | IDLE (hace todo) | Clasificador → Modo específico |
| **Timeout** | No existe | Por modo (10-30 min) |
| **Reintentos** | Contador sin acción | Política definida por modo |
| **NLU** | Implícito | Clasificador explícito |
| **Herramientas** | Todas disponibles | Filtradas por modo |

---

## 📊 Métricas de Éxito Esperadas

| Métrica | v1 Actual | Objetivo v2 |
|---------|-----------|-------------|
| Tasa de conversión | ? | +10% |
| Escalaciones | ? | -20% |
| Abandono | ? | -15% |
| Tiempo promedio | ? | Similar o mejor |

---

## ⚠️ Estado de Implementación

**Estado**: Documentación completa, lista para desarrollo

**Próximo paso**: Priorizar modo inicial para implementar (recomendación: VIABILIDAD_MODE - 65% del tráfico)

**Duración estimada**: 7 semanas (ver [12-migracion-v1-v2.md](12-migracion-v1-v2.md))

---

**Arquitectura de Conversación v2.0**  
**Versión**: 1.0  
**Fecha**: Febrero 2026  
**Estado**: Propuesta aprobada, lista para desarrollo
