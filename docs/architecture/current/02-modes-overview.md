# Modos de Conversación - Visión General

## 🎯 Propósito de esta Arquitectura

La arquitectura v2.0 divide la conversación en **4 modos especializados** que reflejan la realidad del negocio:

- **65% de usuarios** vienen a evaluar viabilidad ("¿Se puede homologar X?")
- **25% de usuarios** vienen directo a presupuesto ("¿Cuánto cuesta Y?")
- **10% de usuarios** vienen a información general ("¿Qué es homologación?")

La arquitectura v1.0 intentaba tratar a todos igual en IDLE, generando confusión.

---

## 🗺️ Mapa de Modos

```
┌─────────────────────────────────────────────────────────────────┐
│                     FLUJO DE MODOS                              │
└─────────────────────────────────────────────────────────────────┘

Usuario entra con cualquier consulta
                │
                ▼
    ┌───────────────────────┐
    │   CLASIFICADOR_DE     │
    │      INTENCIÓN        │
    │  (Confidence >= 75%)  │
    └───────────┬───────────┘
                │
     ┌──────────┼──────────┐
     │          │          │
     ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐
│CONSULTA│ │VIABILID│ │PRESUP. │
│  10%   │ │  65%   │ │  25%   │
└───┬────┘ └───┬────┘ └────┬───┘
    │          │           │
    │          │◄──────────┘
    │◄─────────┘
    │
    └──────┐
           ▼
    ┌──────────────┐
    │VIABILIDAD    │
    │CONFIRMADA    │
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ PRESUPUESTO  │
    │  ACEPTADO    │
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ EVALUACIÓN   │
    │  GATEWAY     │
    │ (Bloqueante) │
    └──────┬───────┘
           │ SÍ explícito
           ▼
    ┌──────────────┐
    │  EXPEDIENTE  │
    │    MODE      │
    │  (Recolección│
    │   de datos)  │
    └──────────────┘
```

---

## 📊 Comparativa de Modos

| Aspecto | CONSULTA | VIABILIDAD | PRESUPUESTO | EXPEDIENTE |
|---------|----------|------------|-------------|------------|
| **% Tráfico** | 10% | 65% | 25% | 100% de conversiones |
| **Objetivo** | Educar | Evaluar | Calcular | Formalizar |
| **Datos recogidos** | Ninguno | Tentativos | Confirmados | Legales |
| **Timeout** | 10 min | 15 min | 20 min | 30 min/submodo |
| **Bloqueante** | No | No | No | Sí |
| **Digresiones** | Sí | Sí | Limitado | No |
| **Herramientas** | 5 | 7 | 9 | 4-8 por submodo |

---

## 🔄 Transiciones Principales

### Entrada al Sistema (Clasificador)

```python
if intent == "consulta_general":
    target_mode = CONSULTA_MODE
elif intent == "evaluar_viabilidad":
    target_mode = VIABILIDAD_MODE
elif intent == "presupuesto_directo":
    target_mode = PRESUPUESTO_MODE
else:
    target_mode = CONSULTA_MODE  # Default seguro
```

### Navegación entre Modos

| De | A | Cuándo |
|----|---|--------|
| CONSULTA | VIABILIDAD | Usuario pregunta "¿Se puede X?" |
| CONSULTA | PRESUPUESTO | Usuario pide precio específico |
| VIABILIDAD | CONSULTA | Usuario tiene más dudas generales |
| VIABILIDAD | PRESUPUESTO | Viabilidad OK + quiere presupuesto |
| PRESUPUESTO | CONSULTA | Rechaza presupuesto, vuelve a dudas |
| PRESUPUESTO | VIABILIDAD | Quiere evaluar otra cosa |
| PRESUPUESTO | EVALUACIÓN | Acepta presupuesto |
| EVALUACIÓN | PRESUPUESTO | Tiene dudas último momento |
| EVALUACIÓN | EXPEDIENTE | Confirma explícitamente |

---

## 🛠️ Herramientas por Modo

### CONSULTA_MODE (5 herramientas)
```python
[
    responder_consulta_general,      # RAG sobre documentación
    explicar_proceso_homologacion,   # Flujo paso a paso
    listar_categorias,               # Qué vehículos soportamos
    listar_elementos_generales,      # Qué se puede homologar
    escalar_a_humano,                # Siempre disponible
]
```

### VIABILIDAD_MODE (7 herramientas)
```python
[
    identificar_elemento,            # Buscar elemento
    evaluar_compatibilidad,          # Elemento + vehículo
    verificar_restricciones,         # Legal/regulatorio
    consultar_documentacion,         # Qué docs necesitaría
    listar_elementos,                # Alternativas
    calcular_estimacion_rapida,      # Rango de precio
    transicion_a_presupuesto,        # Cuando confirma interés
    escalar_a_humano,
]
```

### PRESUPUESTO_MODE (9 herramientas)
```python
[
    identificar_y_resolver_elementos,
    seleccionar_variante_por_respuesta,
    agregar_elemento,
    quitar_elemento,
    recalcular_tarifa,
    calcular_tarifa_con_elementos,
    enviar_imagenes_ejemplo,
    explicar_desglose_precio,
    iniciar_expediente,              # A evaluación gateway
    escalar_a_humano,
]
```

### EXPEDIENTE_MODE (varía por submodo)

**Submodo DATOS_PERSONALES** (4 herramientas):
```python
[
    actualizar_datos_personales,
    obtener_estado_expediente,
    escalar_a_humano,
]
```

**Submodo DOCUMENTACION_ELEMENTOS** (8 herramientas):
```python
[
    confirmar_fotos_elemento,
    guardar_datos_elemento,
    completar_elemento_actual,
    obtener_campos_elemento,
    obtener_progreso_elementos,
    reenviar_imagenes_elemento,
    escalar_a_humano,
]
```

---

## 🎭 Casos de Uso Típicos

### Caso 1: Consulta General (10%)

```
Usuario: ¿Qué es la homologación?
Agente: [CONSULTA_MODE] Es el proceso de...

Usuario: ¿Y para qué sirve?
Agente: [CONSULTA_MODE] Sirve para...

Usuario: ¿Se puede homologar un escape?
Agente: [TRANSICIÓN → VIABILIDAD_MODE]
       Déjame evaluar eso para tu caso específico...
```

### Caso 2: Evaluación de Viabilidad (65%)

```
Usuario: ¿Se puede homologar un turbo en una MT-07?
Agente: [VIABILIDAD_MODE] 
       Analizando... Encontrado:
       • Turbo: SÍ es homologable
       • Requiere mods adicionales
       • Complejidad: Alta
       
       Estimación: 1.200€ - 1.800€
       
       ¿Quieres un presupuesto detallado exacto?

Usuario: Sí
Agente: [TRANSICIÓN → PRESUPUESTO_MODE]
```

### Caso 3: Presupuesto Directo (25%)

```
Usuario: Quiero homologar escape y filtro para mi MT-07
Agente: [PRESUPUESTO_MODE]
       Elementos identificados: Escape + Filtro
       Precio: 890€ + IVA
       [Envía imágenes]
       
       ¿Iniciamos expediente?

Usuario: Sí
Agente: [TRANSICIÓN → EVALUACIÓN_GATEWAY]
       ¿Confirmás que Quieres iniciar el expediente? (sí/no)

Usuario: Sí
Agente: [TRANSICIÓN → EXPEDIENTE_MODE]
       Perfecto, vamos a necesitar tus datos...
```

---

## 🚧 Estados Bloqueantes vs Permisivos

### Modos Permisivos (Navegación libre)

- **CONSULTA_MODE**: Usuario puede preguntar lo que quiera
- **VIABILIDAD_MODE**: Puede volver a consultas generales
- **PRESUPUESTO_MODE**: Puede iterar, agregar/quitar elementos

### Estados Bloqueantes (Decisión requerida)

- **EVALUACIÓN_GATEWAY**: Requiere sí/no explícito
- **EXPEDIENTE_MODE**: Requiere completar datos (secuencial)

---

## 📁 Documentación Relacionada

- [03-modo-consulta.md](03-modo-consulta.md) - Detalle de CONSULTA_MODE
- [04-modo-viabilidad.md](04-modo-viabilidad.md) - Detalle de VIABILIDAD_MODE
- [05-modo-presupuesto.md](05-modo-presupuesto.md) - Detalle de PRESUPUESTO_MODE
- [06-modo-expediente.md](06-modo-expediente.md) - Detalle de EXPEDIENTE_MODE
- [07-transiciones-grafo.md](07-transiciones-grafo.md) - Matriz completa

---

**Nota**: Cada modo está documentado en detalle en su propio archivo.
