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
