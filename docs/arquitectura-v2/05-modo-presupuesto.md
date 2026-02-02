# Modo: PRESUPUESTO_MODE

## 📋 Metadatos

| Campo | Valor |
|-------|-------|
| **Nombre del Modo** | PRESUPUESTO_MODE |
| **Código Técnico** | `presupuesto_mode` |
| **Versión** | 1.0 (v2.0) |
| **Fecha** | Febrero 2026 |
| **% Tráfico Esperado** | 25% |
| **Complejidad** | Media-Alta |
| **Tipo** | Permisivo con foco (no bloqueante, pero enfocado) |

---

## 🎯 Propósito y Alcance

### Objetivo Principal
Calcular presupuesto exacto para homologación, incluyendo:
1. Identificación precisa de elementos (con resolución de variantes)
2. Cálculo de tarifa exacta según tier
3. Presentación de documentación requerida con ejemplos visuales
4. Gestión de iteraciones (agregar/quitar elementos)
5. Preparación para decisión de expediente

### Definición de Éxito
- Usuario tiene **precio exacto** comunicado claramente
- Usuario conoce **documentación necesaria** (con fotos de ejemplo)
- Usuario está informado de **warnings** y condiciones
- Usuario puede **aceptar o rechazar** presupuesto

---

## 🔄 Contexto de Navegación

### Predecesores
- **VIABILIDAD_MODE**: Viabilidad confirmada, interés en precio exacto
- **START**: Usuario pide directamente "¿Cuánto cuesta X?"
- **PRESUPUESTO_MODE** (loop): Agregar/quitar elementos

### Sucesores
- **EVALUACIÓN_GATEWAY**: Presupuesto aceptado
- **CONSULTA_MODE**: Rechazado, vuelve a dudas generales
- **VIABILIDAD_MODE**: Quiere evaluar otra cosa

---

## 🛠️ Herramientas (9 herramientas)

### 1. `identificar_y_resolver_elementos`
**Entrada**: `descripcion`, `categoria_slug`  
**Salida**: `elementos_listos`, `elementos_con_variantes`, `preguntas_variantes`

### 2. `seleccionar_variante_por_respuesta`
**Entrada**: `categoria`, `codigo_base`, `respuesta_usuario`  
**Salida**: `variante_resuelta` (ej: "ESCAPE_MOTO")

### 3. `agregar_elemento`
**Entrada**: `elemento_codigo`, `contexto_actual`  
**Salida**: Contexto actualizado con nuevo elemento

### 4. `quitar_elemento`
**Entrada**: `elemento_codigo`, `contexto_actual`  
**Salida**: Contexto actualizado sin elemento

### 5. `recalcular_tarifa`
**Entrada**: `elementos_codigos[]`, `categoria`  
**Salida**: `tarifa_resultado` actualizado

### 6. `calcular_tarifa_con_elementos`
**Entrada**: `categoria`, `codigos[]`, `skip_validation`  
**Salida**: `tier_name`, `price`, `warnings`, `documentacion`

### 7. `enviar_imagenes_ejemplo`
**Entrada**: `tipo`, `codigo_elemento`, `follow_up_message`  
**Salida**: Imágenes encoladas para envío

### 8. `explicar_desglose_precio`
**Entrada**: `tarifa_resultado`  
**Salida**: Desglose detallado de componentes del precio

### 9. `iniciar_expediente` (→ EVALUACIÓN_GATEWAY)
**Entrada**: Confirmación de interés  
**Salida**: Transición a gateway de evaluación

---

## 📊 Datos del Modo

### Contexto Temporal
| Dato | Tipo | Descripción |
|------|------|-------------|
| `elementos_seleccionados` | list[dict] | Elementos con variantes resueltas |
| `tarifa_calculada` | dict | Resultado completo de cálculo |
| `images_sent` | bool | Si ya se enviaron imágenes |
| `price_communicated` | bool | Si se comunicó precio oralmente |
| `iteracion_count` | int | Cuántas vueltas de agregar/quitar |

### Datos de Salida
- `presupuesto_final`: Elementos + tarifa confirmada
- `aceptacion`: bool | None (None = aún no decide)

---

## 📜 Reglas de Negocio

### CRÍTICAS
1. **Precio ANTES de imágenes**: Siempre comunicar precio textualmente antes de `enviar_imagenes_ejemplo`
2. **No re-enviar imágenes**: Una vez enviadas, no repetir para mismo presupuesto
3. **Warnings obligatorios**: Todos los warnings del resultado deben comunicarse
4. **Sin invención**: Solo usar datos de `calcular_tarifa_con_elementos`

### Flujo
1. Identificar elementos → Resolver variantes → Calcular tarifa
2. Comunicar precio + warnings
3. Enviar imágenes de ejemplo (una vez)
4. Preguntar: "¿Te gustaría iniciar el expediente?"
5. Si acepta → EVALUACIÓN_GATEWAY

---

## 🚨 Timeouts y Reintentos

| Timeout | Acción |
|---------|--------|
| 20 min | Nudge: "¿Guardo este presupuesto y volvés luego?" |
| 40 min | Reset: Presupuesto guardado como borrador, vuelve a CONSULTA_MODE |

| Reintento | Situación | Acción |
|-----------|-----------|--------|
| 5 | Iteraciones de elementos | Permitir, es exploración válida |
| 3 | Validación fallida | Ofrecer ayuda humana |

---

## 🎭 Casos de Uso

### Caso 1: Presupuesto Simple
```
Usuario: [de VIABILIDAD_MODE] Sí, quiero el presupuesto
Agente: [PRESUPUESTO_MODE - identificar_y_resolver_elementos]
       Identificando elementos...
Agente: [seleccionar_variante] "¿Es escape para moto o quad?"
Usuario: "Moto"
Agente: [calcular_tarifa] "Precio: 280€ + IVA (Tier T2)"
       [enviar_imagenes_ejemplo] "Acá tenés ejemplos de la documentación"
       "¿Iniciamos el expediente?"
```

### Caso 2: Iteración - Agregar Elementos
```
Usuario: "También quiero agregar el manillar"
Agente: [agregar_elemento("MANILLAR")]
       "Agregado. Recalculando..."
       [recalcular_tarifa]
       "Nuevo precio: 450€ + IVA (Tier T3)"
       "¿Seguimos con el expediente?"
```

### Caso 3: Rechazo → Vuelta a Consulta
```
Usuario: "Me parece caro, voy a pensarlo"
Agente: "Entendido. Guardé tu presupuesto (280€ + IVA para escape).
       Si querés revisar otras opciones o tenés dudas, avisame."
       [Transición → CONSULTA_MODE]
```

---

## 📁 Prompt del Sistema

```markdown
## MODO: PRESUPUESTO

Objetivo: Calcular y presentar presupuesto exacto.

### Reglas CRÍTICAS
1. Siempre comunicar precio ANTES de enviar imágenes
2. No enviar imágenes dos veces para mismo presupuesto
3. Incluir SIEMPRE todos los warnings de la tarifa
4. Solo usar datos de calcular_tarifa_con_elementos (no inventar)

### Flujo
1. Identificar elementos (resolver variantes si hay)
2. Calcular tarifa exacta
3. Comunicar precio + warnings + desglose
4. Enviar imágenes de ejemplo (una sola vez)
5. Ofrecer iniciar expediente

### Transiciones
- Acepta → EVALUACIÓN_GATEWAY
- Rechaza/dundas → CONSULTA_MODE o VIABILIDAD_MODE
- Agregar elementos → Loop en PRESUPUESTO_MODE
```

---

**Documento detallado para PRESUPUESTO_MODE**  
**Estado**: Listo para desarrollo
