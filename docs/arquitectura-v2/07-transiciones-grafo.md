# Matriz de Transiciones del Grafo

## 🎯 Reglas Generales de Transiciones

### Principios

1. **Progresión natural**: Usuario avanza según su propio ritmo e interés
2. **Retroceso permitido**: Puede volver a modos anteriores sin perder progreso
3. **Saltos prohibidos**: No se puede saltar etapas críticas (ej: a expediente sin presupuesto)
4. **Escape siempre disponible**: `escalar_a_humano` en cualquier punto

---

## 📊 Matriz Completa de Transiciones

### Transiciones desde START (Entry Point)

| Condición de Entrada | Modo Destino | Lógica del Clasificador |
|---------------------|--------------|------------------------|
| Pregunta general sobre homologación | **CONSULTA_MODE** | Keywords: "qué es", "cómo funciona", "para qué sirve" |
| Pregunta de viabilidad | **VIABILIDAD_MODE** | Keywords: "se puede", "es posible", "está permitido" |
| Solicitud directa de precio | **PRESUPUESTO_MODE** | Keywords: "cuánto cuesta", "precio de", "presupuesto para" |
| Intención ambigua (confidence < 75%) | **CONSULTA_MODE** | Default seguro con pregunta de clarificación |

---

### Transiciones desde CONSULTA_MODE

| Evento | Modo Destino | Condición | Preserva Contexto |
|--------|-------------|-----------|-------------------|
| Usuario pregunta viabilidad específica | **VIABILIDAD_MODE** | "¿Se puede X?" | Sí (historial de consulta) |
| Usuario pide presupuesto directo | **PRESUPUESTO_MODE** | "¿Cuánto cuesta Y?" | Sí |
| Usuario satisfecho, termina | **(END)** | "Gracias, eso es todo" | Guardar en analytics |
| Usuario solicita humano | **ESCALACIÓN** | "Hablar con persona" | Sí (resumen de consulta) |
| Timeout (10 min) | **NUDGE → Reset** | Inactividad | Ofrecer volver luego |

**Transiciones PROHIBIDAS desde CONSULTA_MODE**:
- ❌ A EXPEDIENTE_MODE (falta presupuesto)
- ❌ A EVALUACIÓN_GATEWAY (no hay decisión de presupuesto)

---

### Transiciones desde VIABILIDAD_MODE

| Evento | Modo Destino | Condición | Preserva Contexto |
|--------|-------------|-----------|-------------------|
| Viabilidad confirmada + interés | **PRESUPUESTO_MODE** | "Sí, dame presupuesto" | Sí (elementos tentativos) |
| Usuario tiene más dudas | **CONSULTA_MODE** | "Tengo otra pregunta" | Sí |
| Viabilidad dudosa/compleja | **ESCALACIÓN** | Sistema detecta caso complejo | Sí (transcripción completa) |
| Usuario rechaza | **CONSULTA_MODE** | "No me interesa" | Sí |
| Timeout (15 min) | **NUDGE** | "¿Querés que busque presupuesto?" | - |

**Transiciones PROHIBIDAS desde VIABILIDAD_MODE**:
- ❌ A EXPEDIENTE_MODE (presupuesto no calculado)
- ❌ A EVALUACIÓN_GATEWAY (falta presupuesto detallado)

---

### Transiciones desde PRESUPUESTO_MODE

| Evento | Modo Destino | Condición | Acción Adicional |
|--------|-------------|-----------|------------------|
| Presupuesto aceptado | **EVALUACIÓN_GATEWAY** | "Sí, me interesa" | Guardar presupuesto en contexto |
| Usuario quiere agregar elementos | **(LOOP)** | "También quiero X" | Recalcular, permanecer en modo |
| Usuario quiere quitar elementos | **(LOOP)** | "Saca el Y" | Recalcular, permanecer en modo |
| Usuario rechaza, vuelve a dudas | **CONSULTA_MODE** | "Tengo dudas" | Preservar presupuesto como borrador |
| Usuario quiere evaluar otra cosa | **VIABILIDAD_MODE** | "Y esto otro, ¿se puede?" | Iniciar nueva evaluación |
| Timeout (20 min) | **NUDGE** | "¿Guardo este presupuesto?" | Ofrecer borrador |

**Transiciones PROHIBIDAS desde PRESUPUESTO_MODE**:
- ❌ A EXPEDIENTE_MODE (debe pasar por EVALUACIÓN_GATEWAY)
- ❌ A START (siempre hay modo válido)

---

### Transiciones desde EVALUACIÓN_GATEWAY (Bloqueante)

| Evento | Modo Destino | Condición | Validación Requerida |
|--------|-------------|-----------|---------------------|
| Confirmación explícita positiva | **EXPEDIENTE_MODE** | "Sí", "Confirmo", "Adelante" | Intención clara sin ambigüedad |
| Rechazo último momento | **PRESUPUESTO_MODE** | "No", "Tengo dudas", "Mejor no" | Volver a modo anterior |
| Intención ambigua | **(LOOP)** | "Ok", "Vale" | Pedir confirmación explícita sí/no |
| Solicitud de humano | **ESCALACIÓN** | "Hablar con persona" | Escalar con contexto completo |
| Timeout (5 min) | **PRESUPUESTO_MODE** | Sin respuesta | "¿Tenés dudas? Volvamos al presupuesto" |

**Transiciones PROHIBIDAS desde EVALUACIÓN_GATEWAY**:
- ❌ A CONSULTA_MODE (ya hay presupuesto calculado, debe decidirse)
- ❌ A VIABILIDAD_MODE (retroceso muy grande, pierde contexto)
- ❌ Directo a EXPEDIENTE sin confirmación explícita

---

### Transiciones dentro de EXPEDIENTE_MODE (Sub-modos)

**Secuencia estándar**:
```
DATOS_PERSONALES → DATOS_VEHICULO → DOC_ELEMENTOS → DOC_BASE → TALLER → REVISION → COMPLETED
```

**Transiciones entre sub-modos**:

| Desde | A | Evento |
|-------|---|--------|
| DATOS_PERSONALES | DATOS_VEHICULO | Datos personales válidos guardados |
| DATOS_VEHICULO | DOC_ELEMENTOS | Datos vehículo válidos guardados |
| DOC_ELEMENTOS | DOC_ELEMENTOS | (Loop por cada elemento) |
| DOC_ELEMENTOS | DOC_BASE | Todos los elementos completados |
| DOC_BASE | TALLER | Documentación base confirmada |
| TALLER | REVISION | Datos de taller guardados |
| REVISION | COMPLETED | `finalizar_expediente()` + confirmación usuario |

**Retrocesos permitidos desde REVISION**:
| Desde | A | Evento |
|-------|---|--------|
| REVISION | DATOS_PERSONALES | Usuario quiere corregir datos personales |
| REVISION | DATOS_VEHICULO | Usuario quiere corregir vehículo |
| REVISION | DOC_ELEMENTOS | Usuario quiere rehacer fotos de elementos |
| REVISION | DOC_BASE | Usuario quiere reenviar documentación base |
| REVISION | TALLER | Usuario quiere cambiar taller |

**Transiciones PROHIBIDAS en EXPEDIENTE_MODE**:
- ❌ Saltar sub-modos (ej: PERSONALES → TALLER)
- ❌ Salir a CONSULTA/VIABILIDAD/PRESUPUESTO (pierde datos parciales)
- ❌ Volver a START (sin cancelar explícitamente)

---

### Transiciones a ESCALACIÓN (desde cualquier modo)

| Desde | Activador | Contexto Enviado |
|-------|-----------|------------------|
| Cualquier modo | `escalar_a_humano()` llamada explícita | Resumen completo de conversación |
| Cualquier modo | 3+ fallos consecutivos (retry limit) | Logs de errores + contexto |
| VIABILIDAD_MODE | Caso detectado como complejo | Transcripción + elementos evaluados |
| PRESUPUESTO_MODE | Usuario frustrado con iteraciones | Historial de cambios de presupuesto |
| EXPEDIENTE_MODE | Usuario no puede proporcionar datos | Qué datos faltan + por qué |

---

## 🚫 Matriz de Transiciones PROHIBIDAS

### Saltos que NUNCA están permitidos

| Desde | A | Razón |
|-------|---|-------|
| START | EXPEDIENTE_MODE | Imposible sin pasar por presupuesto |
| START | EVALUACIÓN_GATEWAY | No hay decisión previa |
| CONSULTA_MODE | EXPEDIENTE_MODE | Falta evaluación y presupuesto |
| CONSULTA_MODE | EVALUACIÓN_GATEWAY | Sin presupuesto calculado |
| VIABILIDAD_MODE | EXPEDIENTE_MODE | Sin presupuesto detallado |
| VIABILIDAD_MODE | EVALUACIÓN_GATEWAY | Falta cálculo exacto |
| PRESUPUESTO_MODE | EXPEDIENTE_MODE | Debe confirmar en gateway |
| EVALUACIÓN_GATEWAY | CONSULTA_MODE | Ya tiene presupuesto, decide sí/no |
| EVALUACIÓN_GATEWAY | VIABILIDAD_MODE | Retroceso excesivo |
| EXPEDIENTE_MODE | CONSULTA_MODE | Perdería datos del caso |
| EXPEDIENTE_MODE | VIABILIDAD_MODE | Contexto incompatible |
| EXPEDIENTE_MODE | START | Sin cancelar explícitamente |

---

## 🔄 Transiciones Especiales

### Transición con Preservación de Contexto

Cuando usuario vuelve de PRESUPUESTO_MODE a CONSULTA_MODE:
```python
# Guardar presupuesto como "borrador"
context["draft_quote"] = {
    "elements": current_elements,
    "price": calculated_price,
    "timestamp": now(),
}

# Al volver a PRESUPUESTO_MODE, ofrecer recuperar
if context.get("draft_quote"):
    message = "Veo que tenías un presupuesto guardado de $X. ¿Querés recuperarlo o hacer uno nuevo?"
```

### Transición de Loop (Iteración)

En PRESUPUESTO_MODE, agregar/quitar elementos:
```python
# No cambia de modo, actualiza contexto
if user_says("Agregar elemento X"):
    new_elements = add_element(current_elements, "X")
    new_price = recalculate_tarifa(new_elements)
    
    return {
        "context_update": {
            "elements": new_elements,
            "price": new_price,
        },
        "stay_in_mode": PRESUPUESTO_MODE,
    }
```

### Transición por Timeout

```python
if inactive_for > MODE_TIMEOUTS[current_mode]:
    if current_mode in [CONSULTA_MODE, VIABILIDAD_MODE]:
        # Nudge primero
        return {
            "message": "¿Sigues ahí? Respondé cualquier cosa para continuar.",
            "stay_in_mode": current_mode,
        }
    elif inactive_for > MODE_TIMEOUTS[current_mode] * 2:
        # Reset después de 2x timeout
        return {
            "mode_change": CONSULTA_MODE,
            "message": "Reiniciamos la conversación por inactividad...",
            "context_reset": True,
        }
```

---

## 🎨 Representación Visual del Grafo

```
                         ┌─────────┐
                         │  START  │
                         └────┬────┘
                              │
           ┌──────────────────┼──────────────────┐
           │                  │                  │
           ▼                  ▼                  ▼
   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
   │  CONSULTA    │  │ VIABILIDAD   │  │ PRESUPUESTO  │
   │    MODE      │  │    MODE      │  │    MODE      │
   └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
          │                 │                 │
          │◄────────────────┼─────────────────┘
          │                 │
          └────────────────►│
                            │
                            ▼
                   ┌──────────────┐
                   │ EVALUACIÓN   │
                   │   GATEWAY    │
                   └──────┬───────┘
                          │
              ┌───────────┴───────────┐
              │                       │
              ▼                       ▼
     ┌──────────────┐        ┌──────────────┐
     │ EXPEDIENTE   │        │  (vuelve a   │
     │    MODE      │        │ presupuesto) │
     └──────┬───────┘        └──────────────┘
            │
     ┌──────┴──────┐
     ▼             ▼
┌─────────┐  ┌─────────┐
│COMPLETED│  │ESCALADO │
└─────────┘  └─────────┘

NOTA: ESCALADO puede ocurrir desde cualquier nodo
```

---

## 📁 Documentación Relacionada

- [00-propuesta-maestra.md](00-propuesta-maestra.md) - Visión general
- [02-modos-overview.md](02-modos-overview.md) - Descripción de modos
- [09-solucion-gaps.md](09-solucion-gaps.md) - Cómo resolvemos problemas
- [12-migracion-v1-v2.md](12-migracion-v1-v2.md) - Plan de migración

---

**Nota**: Este grafo es la fuente de verdad para implementación. Cualquier transición no listada aquí está prohibida.
