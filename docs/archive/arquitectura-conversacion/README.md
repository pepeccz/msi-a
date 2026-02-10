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
