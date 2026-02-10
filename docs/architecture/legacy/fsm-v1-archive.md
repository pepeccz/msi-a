# FSM v1.0 Architecture - LEGACY ARCHIVE

**⚠️ IMPORTANT**: This architecture was **REPLACED** by the Mode-based v2.0 architecture in February 2026.

This document consolidates the FSM (Finite State Machine) v1.0 documentation for historical reference only.

---

## Overview

The v1.0 agent used a linear FSM with the following states:

```
START → IDLE → COLLECT_ELEMENT_DATA → COLLECT_BASE_DOCS → 
COLLECT_PERSONAL → COLLECT_VEHICLE → COLLECT_WORKSHOP → 
REVIEW_SUMMARY → COMPLETED
```

## Why It Was Replaced

### Critical Gaps Identified

1. **No Timeout Management**: States persisted indefinitely if user abandoned
2. **No Retry Policy**: `MAX_RETRIES_PER_STEP` existed but wasn't enforced
3. **No Digression Handling**: Couldn't handle off-topic questions gracefully
4. **Linear Flow Only**: Couldn't handle non-sequential conversations
5. **FSM Awareness in Prompts**: LLM had to "know" about state machine (cognitive load)

### Migration to v2.0

The v2.0 architecture replaced FSM with **Modes**:

- **CONSULTA_MODE**: Educational queries (~10% traffic)
- **VIABILIDAD_MODE**: Feasibility checks (merged with old PRESUPUESTO)
- **PRESUPUESTO_MODE**: Pricing + images (~90% traffic)
- **EVALUACION_GATEWAY**: Yes/no confirmation before expediente
- **EXPEDIENTE_MODE**: Formal case collection (redesigned with sub-modes)

See `docs/architecture/current/` for active architecture.

---

## Original Documentation (Archived)

The original FSM v1.0 documentation from `arquitectura-conversacion/` has been preserved below for reference.

# Arquitectura de Conversación - Índice

## 📚 Estructura de Documentación

Esta documentación describe la arquitectura de conversación del agente MSI-a utilizando un enfoque de **Finite State Machine (FSM)**. Cada estado representa una fase distinta en la interacción entre el usuario y el agente.

---

## 🗺️ Mapa de Estados

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MAQUINA DE ESTADOS                                │
└─────────────────────────────────────────────────────────────────────────────┘

    ┌─────────┐
    │  START  │
    └────┬────┘
         │
         ▼
    ┌─────────┐
    │  IDLE   │◄─────────────────────────────────────────┐
    │(Presup.)│                                          │
    └────┬────┘                                          │
         │ iniciar_expediente()                          │
         │                                               │
         ▼                                               │
┌─────────────────────┐                                  │
│ COLLECT_ELEMENT_DATA│                                  │
│(Fotos+Datos/elemento)│                                  │
└────┬────────────────┘                                  │
     │ completar_elemento_actual()                       │
     │ (por cada elemento)                               │
     │                                                   │
     ▼                                                   │
┌─────────────────────┐                                  │
│  COLLECT_BASE_DOCS  │                                  │
│(Doc. base vehículo) │                                  │
└────┬────────────────┘                                  │
     │                                                   │
     ▼                                                   │
┌─────────────────────┐                                  │
│  COLLECT_PERSONAL   │                                  │
│  (Datos personales) │                                  │
└────┬────────────────┘                                  │
     │                                                   │
     ▼                                                   │
┌─────────────────────┐                                  │
│  COLLECT_VEHICLE    │                                  │
│  (Datos vehículo)   │                                  │
└────┬────────────────┘                                  │
     │                                                   │
     ▼                                                   │
┌─────────────────────┐                                  │
│  COLLECT_WORKSHOP   │                                  │
│  (Taller: MSI/propio)│                                 │
└────┬────────────────┘                                  │
     │                                                   │
     ▼                                                   │
┌─────────────────────┐                                  │
│  REVIEW_SUMMARY     │                                  │
│  (Resumen final)    │                                  │
└────┬────────────────┘                                  │
     │                                                   │
     ▼                                                   │
┌─────────────────────┐       cancelar_expediente()     │
│     COMPLETED       │─────────────────────────────────►│
│  (Escalado a humano)│                                  │
└─────────────────────┘                                  │

NOTA: Cualquier estado puede transicionar a IDLE mediante cancelar_expediente()
```

### ⚠️ Mecanismos Faltantes (Gaps Identificados)

| Mecanismo | Estado | Impacto |
|-----------|--------|---------|
| **Timeout de inactividad** | ❌ No implementado | Estados persisten indefinidamente si el usuario abandona |
| **Política de reintentos de usuario** | ⚠️ Parcial (`MAX_RETRIES_PER_STEP=3` pero sin acción definida al alcanzarlo) | Bucle potencial si usuario no coopera |
| **Estados bloqueantes vs permisivos** | ⚠️ No documentado explícitamente | Comportamiento inconsistente |
| **Recuperación de errores NLU** | ❌ No implementado | El agente puede quedar confundido sin escalación |
| **Nudge proactivo** | ❌ No implementado | No hay recordatorios si usuario abandona a mitad de proceso |

---

## 📖 Estados Documentados

### Estados Principales

| # | Estado | Nombre Técnico | Propósito | Complejidad |
|---|--------|---------------|-----------|-------------|
| 01 | **IDLE** | `idle` | Presupuestación y atención general | Media |
| 02 | **Recolección de Elementos** | `collect_element_data` | Fotos y datos técnicos por cada elemento a homologar | Alta |
| 03 | **Documentación Base** | `collect_base_docs` | Recolección de ficha técnica, permiso de circulación y vistas del vehículo | Media |
| 04 | **Datos Personales** | `collect_personal` | Nombre, DNI/CIF, email, domicilio, ITV | Media |
| 05 | **Datos del Vehículo** | `collect_vehicle` | Marca, modelo, matrícula, año, bastidor | Baja |
| 06 | **Taller** | `collect_workshop` | Decisión entre taller MSI o taller propio | Media |
| 07 | **Revisión Final** | `review_summary` | Resumen y confirmación antes de envío | Baja |

### Documentos de Soporte

| Documento | Propósito |
|-----------|-----------|
| [00-plantilla-estado.md](00-plantilla-estado.md) | Plantilla universal para definir estados |
| [08-transiciones-fsm.md](08-transiciones-fsm.md) | Matriz completa de transiciones válidas |
| [README.md](README.md) | Este documento - visión general |

---

## 🎯 Objetivos de la Arquitectura

### Objetivo Principal
Crear una experiencia de conversación robusta para la homologación de vehículos que:
1. Guíe al usuario paso a paso sin perder el contexto
2. Acumule toda la información necesaria antes de procesar
3. Permita correcciones y retrocesos controlados
4. Escalación fluida a agentes humanos cuando sea necesario

### Objetivos Secundarios
- **Validación progresiva**: Cada estado valida sus datos antes de continuar
- **Recuperación de errores**: Manejo graceful de entradas inválidas
- **Persistencia de contexto**: Mantener información entre estados
- **Flexibilidad de entrada**: Permitir diferentes formatos de respuesta del usuario

---

## 🏗️ Principios de Diseño

### 1. Inmutabilidad del Estado
Cada estado tiene definido claramente:
- Qué datos requiere para entrar
- Qué datos produce al salir
- Qué herramientas puede usar
- Qué no puede hacer

### 2. Validación en Frontera
Las validaciones ocurren:
- Al entrar (pre-condiciones)
- Durante (validación de datos)
- Al salir (post-condiciones)

### 3. Acoplamiento Controlado
- Estados solo conocen sus estados vecinos inmediatos
- No hay saltos arbitrarios entre estados no consecutivos
- Las transiciones reversas tienen restricciones específicas

### 4. Transparencia para el Usuario
- El usuario siempre sabe en qué punto del proceso está
- Los mensajes del agente reflejan el contexto actual
- Las instrucciones son específicas de cada estado

---

## 📊 Características por Estado

| Característica | IDLE | Collect Element | Collect Base Docs | Collect Personal | Collect Vehicle | Collect Workshop | Review Summary |
|----------------|------|-----------------|-------------------|------------------|-----------------|------------------|----------------|
| **Tiempo típico** | 2-5 min | 5-15 min total | 2-5 min | 3-5 min | 2-3 min | 2-3 min | 1-2 min |
| **Iteraciones esperadas** | 3-8 | Variable (por elemento) | 1-3 | 1-3 | 1-2 | 1-2 | 1 |
| **Datos producidos** | ~5 campos | Variable | Booleano + archivos | ~9 campos | ~5 campos | Booleano + ~8 campos | Confirmación |
| **Herramientas disponibles** | ~15 | ~8 | ~4 | ~4 | ~4 | ~3 | ~5 |
| **Rollback permitido** | N/A | No | No | Sí (desde Review) | Sí (desde Review) | Sí (desde Review) | Sí |

---

## 🔍 Consideraciones Transversales

### Contexto Persistente
Datos que atraviesan todos los estados:
- Identificación del usuario (teléfono, nombre, ID)
- Tipo de cliente (particular/profesional)
- Categoría de vehículo
- Lista de elementos a homologar
- Tarifa calculada
- Historial de mensajes

### Herramientas Universales
Disponibles en (casi) todos los estados:
- `escalar_a_humano` - Solicitar agente humano
- `cancelar_expediente` - Abandonar proceso
- `obtener_estado_expediente` - Consultar progreso
- `consulta_durante_expediente` - Responder preguntas off-topic

### Manejo de Digresiones
En cualquier estado, el usuario puede:
1. Hacer preguntas no relacionadas → `consulta_durante_expediente`
2. Preguntar por su progreso → `obtener_estado_expediente`
3. Solicitar humano → `escalar_a_humano`
4. Cancelar → `cancelar_expediente`

---

## 📈 Flujo de Datos

### Entrada al Sistema
```
WhatsApp → Chatwoot → Webhook → Redis Stream → Agent
                                    ↓
                              [process_incoming_message]
                                    ↓
                              [conversational_agent]
                                    ↓
                              Estado Actual (FSM)
```

### Salida del Sistema
```
Estado Actual → Herramienta → Persistencia DB → Respuesta → Chatwoot → WhatsApp
      ↓
  Transición → Nuevo Estado
```

---

## 🔴 Gaps Críticos del Sistema Actual

Esta documentación refleja la **realidad** del sistema MSI-a, incluyendo sus debilidades. Los siguientes gaps han sido identificados mediante análisis de código:

### 1. Timeouts de Estado (🔴 Crítico)

**Problema**: No hay mecanismo de timeout por inactividad del usuario.

**Evidencia en código**:
- No existe `STATE_TIMEOUT` ni similar en `case_collection.py`
- El campo `retry_count` existe pero solo cuenta intentos, no tiempo

**Impacto**: 
- Si un usuario abandona a mitad de COLLECT_ELEMENT_DATA, el estado permanece allí indefinidamente
- Al volver días después, la conversación continúa desde donde la dejó sin contexto de tiempo
- Ocupación innecesaria de memoria en Redis

**Posible solución**:
```python
# Implementar en case_collection.py
STATE_TIMEOUT_MINUTES = 20

async def check_state_timeout(fsm_state):
    last_activity = fsm_state.get("last_activity_timestamp")
    if last_activity and (now - last_activity) > STATE_TIMEOUT_MINUTES:
        return TimeoutAction.RESET_TO_IDLE
```

### 2. Política de Reintentos de Usuario (🔴 Crítico)

**Problema**: `MAX_RETRIES_PER_STEP = 3` existe pero no tiene acción definida al alcanzar el límite.

**Evidencia en código** (`case_collection.py:88`):
```python
MAX_RETRIES_PER_STEP = 3  # Está definido
# Pero no hay lógica que use este valor para forzar escalación
```

**Comportamiento actual**:
- El contador `retry_count` se incrementa (línea 83)
- Se resetea a 0 en cada transición (línea 741, 607)
- **PERO**: Nunca se verifica si `retry_count >= MAX_RETRIES_PER_STEP`

**Impacto**:
- Usuario puede fallar validación infinitamente sin escalación forzada
- Bucle de "dato inválido → repreguntar" sin escape

### 3. Manejo de Errores NLU (🟡 Medio)

**Problema**: No hay detección de "no entendimiento" del modelo.

**Evidencia**:
- `conversational_agent.py` tiene `MAX_VALIDATION_RETRIES` para constraints
- Pero no hay `MAX_NLU_FAILURES` o similar
- No hay detección de "intent confidence" bajo

**Impacto**:
- Si el LLM no entiende lo que quiere el usuario, intenta responder igual
- Puede resultar en respuestas irrelevantes o ciclos de confusión

### 4. Estados Bloqueantes vs Permisivos (🟡 Medio)

**Problema**: No hay distinción formal entre estados que requieren respuesta específica vs estados flexibles.

**Evidencia**:
- `consulta_durante_expediente()` está disponible en todos los estados
- Pero el comportamiento real varía según el prompt de fase
- No hay flag `is_blocking` en `CollectionStep`

**Impacto**:
- Comportamiento inconsistente: a veces se permite digresión, a veces no
- Depende de la "interpretación" del LLM en cada momento

### 5. Recuperación de Fallos de Herramientas (🟢 Bajo)

**Estado**: ✅ Parcialmente implementado

**Evidencia**:
- `handle_tool_errors` decorator existe (`utils/errors.py:164`)
- Muestra mensaje genérico: "Lo siento, hubo un problema técnico. ¿Puedes intentarlo de nuevo?"
- **PERO**: No hay backoff progresivo ni escalación tras N fallos consecutivos

---

## 🎓 Glosario de Términos

|Término | Definición |
|---------|------------|
| **Estado** | Una fase definida en la conversación con propósito, datos y herramientas específicas |
| **Transición** | El cambio de un estado a otro, disparado por eventos o condiciones |
| **FSM** | Finite State Machine - Máquina de estados finitos que define los estados y transiciones válidas |
| **Slot** | Un campo de datos específico que debe llenarse (ej: "nombre", "matrícula") |
| **Slot Filling** | Proceso de solicitar y validar datos hasta que todos los slots requeridos estén completos |
| **Herramienta** | Una acción que el agente puede ejecutar para consultar información o modificar estado |
| **Activador** | Evento o condición que inicia una transición de estado |
| **Digresión** | Desviación temporal de la conversación principal para responder una consulta secundaria |
| **Anáfora** | Referencia a algo mencionado anteriormente (ej: "el primero", "ese") |
| **Validación** | Verificación de que los datos cumplen formatos y reglas de negocio |
| **Gap** | Deficiencia o funcionalidad faltante identificada en el sistema actual |

---

## 🚀 Cómo Usar Esta Documentación

### Para Diseñar un Nuevo Estado
1. Copiar [00-plantilla-estado.md](00-plantilla-estado.md)
2. Completar cada sección siguiendo las guías
3. Revisar [08-transiciones-fsm.md](08-transiciones-fsm.md) para entender conectividad
4. Validar con el equipo de negocio los casos de uso

### Para Entender un Estado Existente
1. Ir al documento del estado específico
2. Revisar "Propósito y Alcance" para entender qué hace
3. Revisar "Capacidades del Agente" para saber qué puede hacer
4. Revisar "Interacciones Típicas" para ver ejemplos de uso

### Para Modificar un Estado
1. Leer el documento completo del estado
2. Revisar "Reglas de Negocio" para entender restricciones
3. Revisar "Dependencias" para entender impactos
4. Actualizar la sección "Historial de Cambios"

---

## 📞 Contacto y Soporte

Para dudas sobre la arquitectura:
- **Área técnica**: [Equipo de desarrollo]
- **Área de negocio**: [Equipo de operaciones]
- **Documentación técnica detallada**: Ver código fuente y comentarios

---

**Última actualización**: Febrero 2026  
**Versión**: 1.0  
**Estado**: En producción


---

## State Diagrams

# Arquitectura de Conversación - Transiciones de la FSM

## 📋 Matriz de Transiciones

Esta documentación define todas las transiciones válidas entre estados de la máquina de estados finitos (FSM) del agente MSI-a.

---

## 🗺️ Diagrama de Transiciones

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    MATRIZ DE TRANSICIONES VÁLIDAS                            │
└──────────────────────────────────────────────────────────────────────────────┘

Estado Actual ───────────────────────────────────────────────────────────────►
│
│
▼
┌─────────┐
│  IDLE   │─────iniciar_expediente()────► COLLECT_ELEMENT_DATA
│         │
│         │─────escalar_a_humano()──────► (ESCALACIÓN)
│         │
│         │─────cancelar_expediente()───► (queda en IDLE, limpia estado)
└────┬────┘
     │
     │ reset_explícito o nueva_conversación
     ▼
   [START]

┌─────────────────────┐
│ COLLECT_ELEMENT_DATA│─────completar_elemento_actual()──┬──► COLLECT_ELEMENT_DATA
│                     │                                    │   (si hay más elementos)
│                     │                                    │
│                     │                                    └──► COLLECT_BASE_DOCS
│                     │                                        (si era último elemento)
│                     │─────escalar_a_humano()──────────► (ESCALACIÓN)
│                     │
│                     │─────cancelar_expediente()───────► IDLE
└─────────────────────┘

┌─────────────────────┐
│  COLLECT_BASE_DOCS  │─────confirmar_documentacion_base()──► COLLECT_PERSONAL
│                     │
│                     │─────escalar_a_humano()──────────► (ESCALACIÓN)
│                     │
│                     │─────cancelar_expediente()───────► IDLE
└─────────────────────┘

┌─────────────────────┐
│  COLLECT_PERSONAL   │─────actualizar_datos_expediente()──► COLLECT_VEHICLE
│                     │   (todos los campos válidos)
│                     │
│                     │─────escalar_a_humano()──────────► (ESCALACIÓN)
│                     │
│                     │─────cancelar_expediente()───────► IDLE
│                     │
│                     │◄────editar_expediente()────────── REVIEW_SUMMARY
└─────────────────────┘

┌─────────────────────┐
│  COLLECT_VEHICLE    │─────actualizar_datos_expediente()──► COLLECT_WORKSHOP
│                     │   (todos los campos válidos)
│                     │
│                     │─────escalar_a_humano()──────────► (ESCALACIÓN)
│                     │
│                     │─────cancelar_expediente()───────► IDLE
│                     │
│                     │◄────editar_expediente()────────── REVIEW_SUMMARY
└─────────────────────┘

┌─────────────────────┐
│  COLLECT_WORKSHOP   │─────actualizar_datos_taller()─────► REVIEW_SUMMARY
│                     │   (taller guardado, MSI o propio)
│                     │
│                     │─────escalar_a_humano()──────────► (ESCALACIÓN)
│                     │
│                     │─────cancelar_expediente()───────► IDLE
│                     │
│                     │◄────editar_expediente()────────── REVIEW_SUMMARY
└─────────────────────┘

┌─────────────────────┐
│  REVIEW_SUMMARY     │─────finalizar_expediente()───────► COMPLETED
│                     │   + confirmación_usuario()
│                     │
│                     │─────editar_expediente("personal")──► COLLECT_PERSONAL
│                     │
│                     │─────editar_expediente("vehiculo")──► COLLECT_VEHICLE
│                     │
│                     │─────editar_expediente("taller")────► COLLECT_WORKSHOP
│                     │
│                     │─────editar_expediente("documentacion")
│                     │                                    ► COLLECT_BASE_DOCS
│                     │
│                     │─────cancelar_expediente()───────► IDLE
│                     │
│                     │─────escalar_a_humano()──────────► (ESCALACIÓN)
└─────────────────────┘

┌──────────────┐
│  COMPLETED   │─────nueva_interacción()─────────────► IDLE
│              │   (usuario inicia nueva conversación)
│              │
│              │─────escalar_a_humano()──────────► (ya está escalado)
│              │   (no-op, ya está en revisión humana)
└──────────────┘

ESCALACIÓN: Transición especial que desactiva el agente y transfiere
            a agente humano vía Chatwoot. Puede ocurrir desde cualquier estado.
```

---

## 📊 Tabla de Transiciones

### Transiciones de IDLE

| A | Evento / Condición | Acción | Notas |
|---|-------------------|--------|-------|
| COLLECT_ELEMENT_DATA | `iniciar_expediente()` + confirmación usuario | Crea Case en DB, inicializa tracking | Solo si hay tarifa calculada |
| (ESCALACIÓN) | `escalar_a_humano()` | Crea Escalation, desactiva bot | Desde cualquier intento del usuario |
| IDLE | `cancelar_expediente()` | Limpia estado FSM | No-op si ya está en IDLE |

### Transiciones de COLLECT_ELEMENT_DATA

| A | Evento / Condición | Acción | Notas |
|---|-------------------|--------|-------|
| COLLECT_ELEMENT_DATA | `completar_elemento_actual()` + hay más elementos | Avanza índice, resetea fase a "photos" | Loop interno del estado |
| COLLECT_BASE_DOCS | `completar_elemento_actual()` + era último elemento | Marca todos elementos "complete" | Transición de salida del estado |
| (ESCALACIÓN) | `escalar_a_humano()` | Crea Escalation | Puede ocurrir en cualquier momento |
| IDLE | `cancelar_expediente()` | Limpia estado, descarta imágenes | Borrado completo del progreso |

### Transiciones de COLLECT_BASE_DOCS

| A | Evento / Condición | Acción | Notas |
|---|-------------------|--------|-------|
| COLLECT_PERSONAL | `confirmar_documentacion_base()` + confirmación usuario | Marca base_docs_received | Usuario debe decir "listo" |
| (ESCALACIÓN) | `escalar_a_humano()` | Crea Escalation | - |
| IDLE | `cancelar_expediente()` | Limpia estado | - |

### Transiciones de COLLECT_PERSONAL

| A | Evento / Condición | Acción | Notas |
|---|-------------------|--------|-------|
| COLLECT_VEHICLE | `actualizar_datos_expediente()` + validación OK | Persiste datos personales | Todos los campos obligatorios |
| REVIEW_SUMMARY | `editar_expediente("personal")` | Carga datos actuales | Edición desde review |
| (ESCALACIÓN) | `escalar_a_humano()` | Crea Escalation | - |
| IDLE | `cancelar_expediente()` | Limpia estado | - |

### Transiciones de COLLECT_VEHICLE

| A | Evento / Condición | Acción | Notas |
|---|-------------------|--------|-------|
| COLLECT_WORKSHOP | `actualizar_datos_expediente()` + validación OK | Persiste datos vehículo | - |
| REVIEW_SUMMARY | `editar_expediente("vehiculo")` | Carga datos actuales | - |
| (ESCALACIÓN) | `escalar_a_humano()` | Crea Escalation | - |
| IDLE | `cancelar_expediente()` | Limpia estado | - |

### Transiciones de COLLECT_WORKSHOP

| A | Evento / Condición | Acción | Notas |
|---|-------------------|--------|-------|
| REVIEW_SUMMARY | `actualizar_datos_taller()` + validación OK | Persiste decisión de taller | MSI o taller propio completo |
| REVIEW_SUMMARY | `editar_expediente("taller")` | Carga decisión actual | - |
| (ESCALACIÓN) | `escalar_a_humano()` | Crea Escalation | - |
| IDLE | `cancelar_expediente()` | Limpia estado | - |

### Transiciones de REVIEW_SUMMARY

| A | Evento / Condición | Acción | Notas |
|---|-------------------|--------|-------|
| COMPLETED | `finalizar_expediente()` + confirmación explícita usuario | Crea Escalation, marca completed | Punto de no retorno |
| COLLECT_PERSONAL | `editar_expediente("personal")` | Navega con datos pre-llenos | Para correcciones |
| COLLECT_VEHICLE | `editar_expediente("vehiculo")` | Navega con datos pre-llenos | - |
| COLLECT_WORKSHOP | `editar_expediente("taller")` | Navega con datos pre-llenos | - |
| COLLECT_BASE_DOCS | `editar_expediente("documentacion")` | Navega con datos pre-llenos | - |
| (ESCALACIÓN) | `escalar_a_humano()` | Crea Escalation | - |
| IDLE | `cancelar_expediente()` | Limpia estado, descarta todo | - |

**IMPORTANTE**: No se permite `editar_expediente("elementos")` desde REVIEW_SUMMARY porque:
- Modificar elementos requeriría re-validar toda la tarifa
- Podría invalidar datos técnicos ya recopilados
- Complejidad alta, mejor cancelar y reiniciar

### Transiciones de COMPLETED

| A | Evento / Condición | Acción | Notas |
|---|-------------------|--------|-------|
| IDLE | Nueva interacción del usuario | Trata como nueva conversación | Inicia nuevo ciclo |
| (N/A) | No hay más transiciones | Estado terminal | - |

---

## ⚠️ Transiciones INVÁLIDAS (Prohibidas)

Las siguientes transiciones NO están permitidas:

| Desde | Hacia | Razón |
|-------|-------|-------|
| IDLE | COLLECT_BASE_DOCS | Debe pasar por COLLECT_ELEMENT_DATA primero |
| IDLE | REVIEW_SUMMARY | No hay datos para revisar |
| COLLECT_ELEMENT_DATA | COLLECT_PERSONAL | Debe pasar por COLLECT_BASE_DOCS |
| COLLECT_BASE_DOCS | COLLECT_VEHICLE | Debe pasar por COLLECT_PERSONAL |
| COLLECT_PERSONAL | REVIEW_SUMMARY | Debe pasar por COLLECT_VEHICLE y WORKSHOP |
| Cualquiera | COLLECT_ELEMENT_DATA (excepto IDLE) | Elementos se recolectan al inicio |
| REVIEW_SUMMARY | COLLECT_ELEMENT_DATA | No se permite editar elementos desde review |
| COMPLETED | Cualquiera (excepto nueva conversación) | Estado terminal |

---

## 🔄 Transiciones Especiales

### Escalación (Desde Cualquier Estado)

**Activador**: `escalar_a_humano()`

**Efecto**:
1. Crea registro de Escalation en base de datos
2. Actualiza Chatwoot: desactiva atención automática
3. Envía mensaje al usuario confirmando escalación
4. Marca conversación como escalada
5. Desactiva procesamiento del agente para esta conversación

**Nota**: La escalación es efectivamente un "estado terminal" que desactiva la FSM.

### Cancelación (Desde Cualquier Estado)

**Activador**: `cancelar_expediente()`

**Efecto**:
1. Resetea FSM a estado inicial (IDLE)
2. Limpia todos los datos temporales
3. Descarta imágenes no procesadas
4. Opcionalmente: persistir como "cancelado" en base de datos (para analytics)

**Nota**: El usuario puede reiniciar desde IDLE sin problema.

### Edición (Desde REVIEW_SUMMARY)

**Activador**: `editar_expediente(seccion)`

**Comportamiento**:
1. Navega al estado correspondiente (PERSONAL, VEHICLE, WORKSHOP, BASE_DOCS)
2. Carga datos actuales como valores iniciales
3. Permite modificación
4. Al completar, retorna a REVIEW_SUMMARY (NO avanza por el flujo normal)

**Por qué no desde otros estados**:
- Permitir edición desde estados intermedios crearía bucles complejos
- El punto de revisión está diseñado específicamente para correcciones

---

## 📝 Diagrama de Secuencia Típico

```
Usuario                Agente                    FSM                      DB
  │                      │                        │                       │
  │───"Quiero homologar"─┤                        │                       │
  │                      │───identificar()───────►│                       │
  │                      │◄──elementos────────────│                       │
  │                      │                        │                       │
  │◄──"Presupuesto: X€"──┤                        │                       │
  │                      │                        │                       │
  │───"Sí, adelante"─────┤                        │                       │
  │                      │───iniciar_expediente()─►│                       │
  │                      │                        │────crear_case()──────►│
  │                      │◄───────────────────────┤◄──case_id─────────────│
  │◄──"Expediente creado"┤                        │                       │
  │                      │                        │                       │
  │                      │    [COLLECT_ELEMENT_DATA - Itera por elementos]
  │                      │                        │                       │
  │                      │    [... otros estados ...]
  │                      │                        │                       │
  │                      │    [REVIEW_SUMMARY]
  │                      │                        │                       │
  │◄──"Resumen completo"─┤                        │                       │
  │                      │                        │                       │
  │───"Sí, correcto"─────┤                        │                       │
  │                      │───finalizar_expediente()►│                      │
  │                      │                        │────crear_escalation()─►│
  │                      │◄───────────────────────┤◄──escalation_id───────│
  │◄──"Enviado a revisión"┤                        │                       │
  │                      │                        │                       │
  │                      │                    [COMPLETED]                  │
```

---

## 🎯 Criterios de Transición

### Siempre Requiere Confirmación Explícita

- `iniciar_expediente()`: Usuario debe confirmar tras presupuesto
- `confirmar_documentacion_base()`: Usuario debe decir "listo"
- `finalizar_expediente()`: Usuario debe confirmar resumen

### Transición Automática (Sin Confirmación Explícita)

- `completar_elemento_actual()`: Si hay más elementos, avanza automáticamente
- `actualizar_datos_expediente()`: Si validación OK, avanza automáticamente
- `actualizar_datos_taller()`: Si datos completos, avanza automáticamente

### Transiciones Reversibles (Edición)

- Desde REVIEW_SUMMARY puede ir a estados anteriores y volver
- Los datos se preservan durante la edición
- Al completar edición, retorna a REVIEW_SUMMARY (no avanza)

---

## 📚 Glosario de Transiciones

|Término | Definición |
|--------|------------|
| **Transición Forward** | Avanza hacia adelante en el flujo normal (hacia COMPLETED) |
| **Transición Backward** | Retrocede para edición (solo desde REVIEW_SUMMARY) |
| **Transición Lateral** | Cambio a estado no adyacente (ej: edición desde review) |
| **Transición Terminal** | Finaliza la FSM (COMPLETED o ESCALACIÓN) |
| **Auto-transición** | Permanece en el mismo estado pero con datos actualizados |
| **Validación de Guardia** | Condición que debe cumplirse para permitir la transición |

---

## 📞 Referencias

- Estados individuales: Ver documentos 01-07
- Plantilla de estados: [00-plantilla-estado.md](00-plantilla-estado.md)
- Visión general: [README.md](README.md)

---

**Nota**: Esta matriz de transiciones es la fuente de verdad para la validación de la FSM. Cualquier cambio en transiciones debe actualizar este documento.


---

## Individual States (v1.0)

For detailed state definitions, see original files in `docs/archive/arquitectura-conversacion/`

