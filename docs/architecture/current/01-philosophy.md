# Arquitectura de Conversación v2.0 - Filosofía y Principios

## 📋 Visión General

La arquitectura v2.0 representa un cambio fundamental en cómo el agente MSI-a gestiona conversaciones. En lugar de un estado IDLE monolítico que intenta hacer todo, proponemos **4 modos especializados** que reflejan la realidad del negocio.

### El Problema con v1.0

El sistema actual tiene un **estado IDLE que hace demasiado**:
- Responder consultas informativas (10%)
- Evaluar viabilidad técnica (65%) ← Mayoría
- Calcular presupuestos (25%)
- Iniciar expedientes

Esto genera confusión porque no hay claridad de "en qué modo estamos conversando".

### La Solución: Centros de Gravedad

```
┌─────────────────────────────────────────────────────────────────┐
│                    CENTROS DE GRAVEDAD                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   CONSULTA        VIABILIDAD         PRESUPUESTO      EXPEDIENTE│
│     10%             65%                  25%           Conversión│
│      │               │                    │               │     │
│      ▼               ▼                    ▼               ▼     │
│  ┌──────┐      ┌──────────┐        ┌──────────┐    ┌─────────┐ │
│  │Educar│ ──▶  │¿Se puede?│  ──▶   │¿Cuánto?  │ ──▶│Formalizar│ │
│  └──────┘      └──────────┘        └──────────┘    └─────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎯 Principios Arquitectónicos

### 1. Claridad de Propósito
**Cada modo tiene UN objetivo claro y medible:**

| Modo | Propósito | Éxito = |
|------|-----------|---------|
| CONSULTA | Educar al usuario | Usuario entiende y quiere evaluar viabilidad |
| VIABILIDAD | Determinar si es homologable | Usuario sabe si se puede + estimación de precio |
| PRESUPUESTO | Calcular precio exacto | Usuario tiene precio + documentación necesaria |
| EXPEDIENTE | Recolectar datos legales | Expediente completo listo para revisión |

### 2. Navegabilidad (Grafo vs Línea)
**El usuario puede moverse entre modos según necesidad:**

```
CONSULTA ◄────► VIABILIDAD ◄────► PRESUPUESTO ────► EXPEDIENTE
   │                │                  ▲                │
   │                └──────────────────┘                │
   │                                                    │
   └────────────────────────────────────────────────────┘
              (El usuario SIEMPRE puede volver)
```

### 3. Progresividad
**No se piden datos hasta que hay intención confirmada:**

```
Pasos de intención:
1. "¿Qué es homologación?" → Ningún dato
2. "¿Se puede homologar X?" → Solo descripción tentativa  
3. "¿Cuánto cuesta Y?" → Elementos confirmados
4. "Quiero iniciar expediente" → Datos personales/legales
```

### 4. Recuperación
**Cada modo define cómo manejar errores y timeouts:**

| Modo | Error típico | Estrategia |
|------|--------------|------------|
| CONSULTA | NLU no entiende pregunta | Escalar a humano rápido |
| VIABILIDAD | Caso complejo técnico | Escalar a técnico experto |
| PRESUPUESTO | Usuario iterando mucho | Permitir loops, timeout largo |
| EXPEDIENTE | Validación de datos falla | Asistencia humana proactiva |

### 5. Herramientas Contextuales
**Solo herramientas relevantes disponibles por modo:**

```
CONSULTA_MODE: [responder_consulta, listar_categorias, ...]
              ❌ NO: calcular_tarifa (no hay elementos aún)

PRESUPUESTO_MODE: [calcular_tarifa, agregar_elemento, ...]
                 ❌ NO: consulta_general (foco en presupuesto)
```

---

## 🗺️ Modelo de Datos por Modo

### Qué se almacena en cada modo

| Modo | Datos Recolectados | Persistencia |
|------|-------------------|--------------|
| CONSULTA | Preguntas frecuentas, temas de interés | Analytics (RAG queries) |
| VIABILIDAD | Elementos tentativos, vehículo mencionado | Contexto temporal |
| PRESUPUESTO | Elementos confirmados, tarifa calculada | Borrador persistente |
| EXPEDIENTE | Datos personales, vehículo, documentación | Case en base de datos |

### Relación con Modelos de Base de Datos

```
CONSULTA_MODE
└── Lee: VehicleCategory, Element (descripciones)
└── Escribe: RAGQuery (analytics)

VIABILIDAD_MODE
├── Lee: Element, VehicleCategory, TariffTier (rangos)
├── Usa: ElementService (identificación tentativa)
└── Contexto: elementos_tentativos[], vehiculo_tentativo

PRESUPUESTO_MODE
├── Lee: Element, TariffTier, Warning
├── Usa: TarifaService (cálculo exacto)
├── Usa: ElementImage (fotos de ejemplo)
└── Contexto: elementos_confirmados[], tarifa_calculada{}

EXPEDIENTE_MODE
├── Lee/Escribe: Case (expediente formal)
├── Escribe: CaseImage (fotos del usuario)
├── Escribe: CaseElementData (datos técnicos)
├── Lee: User (datos previos para autocompletar)
└── Escribe: Escalation (al completar)
```

---

## 🔄 Transiciones y Estado

### Máquina de Estados vs Grafo de Modos

**v1.0 (FSM Lineal):**
```
IDLE → ELEMENT_DATA → BASE_DOCS → PERSONAL → VEHICLE → WORKSHOP → REVIEW → COMPLETED
```
Problema: Secuencial forzada, no permite exploración.

**v2.0 (Grafo de Modos):**
```
                    ┌──► CONSULTA ──┐
                    │      ▲        │
START ──► CLASIFICADOR ──► VIABILIDAD ◄──┤
                    │      ▲        │
                    └──► PRESUPUESTO ──┘
                              │
                              ▼
                    ┌──► EVALUACIÓN_GATEWAY
                    │         │
                    │         ▼
                    │    EXPEDIENTE_MODE
                    │    (sub-modos internos)
                    │         │
                    │         ▼
                    └──── COMPLETED
```

Ventaja: El usuario controla el flujo, el sistema adapta.

---

## 🛠️ Componentes Reciclados vs Nuevos

### Reciclar (Sin cambios)

| Componente | Uso en v2 | Ubicación en v2 |
|------------|-----------|-----------------|
| TarifaService | PRESUPUESTO_MODE | Servicio transversal |
| ElementService | VIABILIDAD, PRESUPUESTO | Servicio transversal |
| CollectionMode | EXPEDIENTE_MODE (DOC_ELEMENTOS) | Servicio transversal |
| ConstraintService | Todos los modos | Middleware de validación |
| Validation | Todos los modos | Utilidad transversal |
| ImageTools | PRESUPUESTO, EXPEDIENTE | Tools compartidas |

### Adaptar (Cambios menores)

| Componente | Cambio | Detalle |
|------------|--------|---------|
| ToolManager | Mapeo por modo, no por fsm_state | Agregar modo a key de selección |
| PromptLoader | Nuevos phase modules | Agregar 4 prompts de modo |
| FSM State | Expandir para modos | Agregar current_mode, modo_context |

### Crear Nuevo (Alto riesgo)

| Componente | Complejidad | Testing crítico |
|------------|-------------|-----------------|
| IntentClassifier | Media | Threshold 75%, fallback correcto |
| TimeoutManager | Baja | Nudge progresivo, no intrusivo |
| RetryPolicy | Baja | Acciones al límite definidas |
| ModeTransition | Media | Transiciones permitidas/bloqueadas |

---

## 📊 Métricas de Éxito por Modo

### Indicadores Clave (KPIs)

| KPI | v1 Actual | Objetivo v2 | Cómo Medir |
|-----|-----------|-------------|------------|
| **Tiempo en consulta** | ? | <3 min promedio | Mode entry/exit timestamps |
| **Conversión consulta→viabilidad** | ? | >40% | Transiciones CONSULTA→VIABILIDAD |
| **Conversión viabilidad→presupuesto** | ? | >60% | Transiciones VIABILIDAD→PRESUPUESTO |
| **Conversión presupuesto→expediente** | ? | >30% | Casos creados / presupuestos |
| **Abandono en expediente** | ? | <20% | Cases incompletos / casos totales |
| **Escalaciones** | ? | <15% | Escalations / conversaciones |

### Métricas Técnicas

| Métrica | Objetivo | Alerta si |
|---------|----------|-----------|
| **Timeout rate** | <10% | >20% timeouts |
| **Retry limit reached** | <5% | >10% alcanzan límite |
| **NLU confidence <75%** | <15% | >30% baja confianza |
| **Tool errors por modo** | <2% | >5% errores |

---

## 🎓 Glosario de Términos v2

| Término | Definición v2 | Equivalente v1 |
|---------|---------------|----------------|
| **Modo** | Centro de gravedad conversacional | Estado FSM |
| **Sub-modo** | Fase interna de un modo (ej: DATOS_PERSONALES dentro de EXPEDIENTE) | Fase de estado FSM |
| **Clasificador** | Determina modo inicial basado en intención | Entrada a IDLE |
| **Gateway** | Punto de decisión bloqueante (ej: EVALUACIÓN_GATEWAY) | Transición automática |
| **Borrador** | Presupuesto calculado no confirmado | tarifa_actual temporal |
| **Contexto de modo** | Datos específicos del modo actual | fsm_state monolítico |

---

## 📁 Estructura de Documentación

Cada modo tiene su propio documento detallado:

```
docs/arquitectura-v2/
├── 00-propuesta-maestra.md          # Este documento y visión general
├── 01-filosofia-arquitectura.md     # Principios y decisiones (este archivo)
├── 02-modos-overview.md             # Comparativa de modos
├── 03-modo-consulta.md              # Detalle CONSULTA_MODE ⭐
├── 04-modo-viabilidad.md            # Detalle VIABILIDAD_MODE ⭐
├── 05-modo-presupuesto.md           # Detalle PRESUPUESTO_MODE ⭐
├── 06-modo-expediente.md            # Detalle EXPEDIENTE_MODE ⭐
├── 07-transiciones-grafo.md         # Matriz de transiciones
├── 08-herramientas-por-modo.md      # Inventario de tools
├── 09-solucion-gaps.md              # Cómo resolvemos críticos
├── 10-reciclaje-componentes.md      # Qué se recicla de v1
├── 11-nuevos-componentes.md         # Qué hay que crear nuevo
├── 12-migracion-v1-v2.md            # Plan de migración
└── 13-casos-uso-flujos.md           # Ejemplos de conversaciones
```

---

## 🚀 Próximos Pasos

1. **Revisar documentos de modos individuales** (03, 04, 05, 06)
2. **Validar matriz de transiciones** (07)
3. **Confirmar plan de migración** (12)
4. **Priorizar implementación** (¿empezar por VIABILIDAD_MODE que es el 65%?)

---

**Documento base para toda la arquitectura v2.0**  
**Versión**: 1.0  
**Estado**: Propuesta para revisión
