# Arquitectura de Conversación - Estado: COLLECT_ELEMENT_DATA

## 📋 Metadatos del Estado

| Campo | Valor |
|-------|-------|
| **Nombre del Estado** | Recolección de Datos por Elemento |
| **Código del Estado** | `collect_element_data` |
| **Versión** | 1.0 |
| **Fecha de Creación** | Febrero 2026 |
| **Última Modificación** | Febrero 2026 |
| **Responsable** | Equipo de Conversación |
| **Estado de Implementación** | En producción |

---

## 🎯 Propósito y Alcance

### Objetivo Principal
Recopilar toda la información necesaria para cada elemento que el usuario desea homologar, incluyendo fotografías de evidencia y datos técnicos específicos, procesando los elementos de manera secuencial (uno por uno).

### Objetivos Secundarios
- Validar que la documentación fotográfica cumple con los requisitos
- Recolectar datos técnicos obligatorios para cada elemento (dimensiones, materiales, etc.)
- Mantener al usuario informado del progreso (elemento X de Y)
- Permitir correcciones y reintentos si la documentación es insuficiente

### Definición del Éxito
El estado se considera completado exitosamente cuando:
1. Todos los elementos de la lista han sido procesados completamente
2. Para cada elemento: se recibieron las fotos requeridas y los datos técnicos obligatorios
3. Cada elemento está marcado como "complete" en el estado de seguimiento
4. El sistema transiciona automáticamente a COLLECT_BASE_DOCS

---

## 🔄 Contexto de Navegación

### Estados Predecesores

| Estado Origen | Activador de Transición | Condiciones |
|---------------|------------------------|-------------|
| IDLE | `iniciar_expediente()` | Usuario confirmó presupuesto y se creó expediente en base de datos |

### Estados Sucesores

| Estado Destino | Activador de Transición | Condiciones |
|----------------|------------------------|-------------|
| COLLECT_ELEMENT_DATA | `completar_elemento_actual()` | Hay más elementos pendientes en la lista |
| COLLECT_BASE_DOCS | `completar_elemento_actual()` | Último elemento completado, todos los elementos en estado "complete" |
| (No permitido) | - | No se puede ir directamente a estados posteriores sin completar todos los elementos |

---

## 🎬 Activadores de Entrada

### Eventos que Inician este Estado

1. **Creación de Expediente**
   - **Descripción**: Usuario acepta iniciar expediente tras presupuesto
   - **Origen**: Usuario confirma explícitamente
   - **Datos asociados**: Lista de códigos de elementos, categoría, tarifa calculada, ID de caso creado

### Condiciones de Entrada

- Debe existir un expediente activo en base de datos con estado válido
- La lista de elementos a homologar debe tener al menos un elemento
- El primer elemento debe estar en estado "pending"
- La fase inicial debe ser "photos" (comenzar con fotos)

---

## 🛠️ Capacidades del Agente

### Herramientas Disponibles

#### Herramientas de Consulta

| Herramienta | Propósito | Datos Requeridos | Datos Producidos |
|-------------|-----------|------------------|------------------|
| `obtener_campos_elemento` | Consultar qué datos técnicos requiere un elemento | Código de elemento (opcional, usa current si no se especifica) | Lista de campos con tipos, validaciones y modos de colección |
| `obtener_progreso_elementos` | Verificar estado de recolección global | Ninguno | Progreso: completados, total, elemento actual, elementos pendientes |

#### Herramientas de Acción

| Herramienta | Propósito | Efecto en el Estado | Efecto en el Sistema |
|-------------|-----------|---------------------|---------------------|
| `confirmar_fotos_elemento` | Confirmar que se recibieron fotos del elemento actual | Cambia `element_phase` de "photos" a "data" | Persiste imágenes asociadas al caso |
| `guardar_datos_elemento` | Guardar valores de campos técnicos | Actualiza `element_data_status`, avanza campos recolectados | Persiste datos del elemento en base de datos |
| `completar_elemento_actual` | Marcar elemento actual como completo | Avanza `current_element_index`, resetea `element_phase` a "photos", actualiza `element_data_status` | Valida completitud antes de permitir |
| `reenviar_imagenes_elemento` | Reenviar fotos de ejemplo del elemento | Ninguno (solo coloca imágenes en cola de envío) | Ninguno |

#### Herramientas de Transición

| Herramienta | Propósito | Estado Resultante | Condiciones |
|-------------|-----------|-------------------|-------------|
| `completar_elemento_actual` | Finalizar elemento y avanzar | COLLECT_ELEMENT_DATA (si hay más) o COLLECT_BASE_DOCS (si era el último) | Todas las fotos recibidas y todos los campos requeridos completos |

### Herramientas Universales (Disponibles en Todos los Estados)

| Herramienta | Propósito |
|-------------|-----------|
| `escalar_a_humano` | Solicitar agente humano |
| `cancelar_expediente` | Cancelar expediente y volver a IDLE |
| `obtener_estado_expediente` | Consultar progreso del expediente |
| `consulta_durante_expediente` | Responder preguntas off-topic |

---

## 📊 Datos del Estado

### Datos de Entrada (Desde Transición)

| Dato | Tipo | Obligatorio | Fuente | Descripción |
|------|------|-------------|--------|-------------|
| `case_id` | UUID | Sí | Creación de expediente | Identificador del caso en base de datos |
| `element_codes` | Lista de strings | Sí | Estado IDLE (tarifa calculada) | Códigos de elementos a homologar en orden |
| `category_slug` | String | Sí | Estado IDLE | Categoría del vehículo |
| `category_id` | UUID | Sí | Estado IDLE | ID de categoría en base de datos |
| `tariff_tier_id` | UUID | No | Estado IDLE | Nivel de tarifa calculada |
| `tariff_amount` | Decimal | No | Estado IDLE | Monto total del presupuesto |

### Datos Producidos (Para Siguiente Estado)

| Dato | Tipo | Obligatorio | Destino | Descripción |
|------|------|-------------|---------|-------------|
| `element_data_status` | Mapa | Sí | COLLECT_BASE_DOCS | Estado de cada elemento (pending/photos_done/complete) |
| `received_images` | Lista | Sí | Siguientes estados | Contador de imágenes recibidas (para resumen) |
| Todos los campos de elementos | Estructurado | Sí | Base de datos | Datos técnicos persistidos por elemento |

### Datos Temporales del Estado

| Dato | Tipo | Duración | Descripción |
|------|------|----------|-------------|
| `current_element_index` | Entero | Durante todo el estado | Índice del elemento actual (0-based) |
| `element_phase` | Categórico | Por elemento | "photos" o "data" - qué se está recolectando |
| Campos parciales | Estructurado | Durante elemento actual | Valores de campos ya recolectados para elemento actual |
| `collected_values` | Mapa | Durante fase "data" | Valores temporales antes de guardar |

### Estado Interno por Elemento

| Variable | Valores Posibles | Significado |
|----------|-------------------|-------------|
| `element_data_status[element]` | `pending` → `photos_done` → `complete` | Progreso del elemento |
| `collection_mode` | `sequential` / `batch` / `hybrid` | Estrategia de recolección de campos |

---

## 📜 Reglas de Negocio

### Reglas de Entrada

1. **Orden de Elementos Respetado**
   - **Condición**: Los elementos deben procesarse en el orden original de la lista
   - **Acción si falla**: No aplica (el índice se maneja automáticamente)

2. **Inicio en Fase Fotos**
   - **Condición**: Todo elemento debe comenzar con la fase "photos"
   - **Acción si falla**: No aplica (inicialización automática)

### Reglas de Ejecución

1. **Secuencia Fija: Fotos antes que Datos**
   - **Descripción**: Para cada elemento, primero se recolectan fotos, luego datos técnicos
   - **Prioridad**: Alta
   - **Consecuencia de incumplimiento**: No se puede guardar datos técnicos sin confirmar fotos primero

2. **No Saltarse Elementos**
   - **Descripción**: No se puede completar el elemento N sin haber completado el N-1
   - **Prioridad**: Alta
   - **Consecuencia de incumplimiento**: Error de validación, mensaje de error al usuario

3. **Validación de Campos Obligatorios**
   - **Descripción**: Todos los campos marcados como `is_required=true` deben tener valor
   - **Prioridad**: Crítica
   - **Consecuencia de incumplimiento**: `completar_elemento_actual` falla, no avanza

4. **Modo de Colección Inteligente**
   - **Descripción**: La estrategia de pregunta (secuencial/batch/híbrida) se determina automáticamente según cantidad y complejidad de campos
   - **Prioridad**: Media
   - **Consecuencia de incumplimiento**: Experiencia de usuario subóptima

5. **Uso Correcto de field_key**
   - **Descripción**: Los datos deben guardarse usando exactamente el `field_key` devuelto por `obtener_campos_elemento`
   - **Prioridad**: Alta
   - **Consecuencia de incumplimiento**: Datos no se persisten correctamente

### Reglas de Salida

1. **Completitud de Todos los Elementos**
   - **Condición de completitud**: Todos los elementos en `element_data_status` deben estar en estado "complete"
   - **Validación requerida**: Verificación de lista completa
   - **Rollback posible**: No, una vez completado no se puede volver a este estado

---

## 🎭 Casos de Uso

### Caso de Uso Principal: Elemento Simple sin Campos Técnicos

**Nombre**: Procesar elemento con solo fotos requeridas

**Descripción**: Elemento que solo requiere fotos de evidencia, sin datos técnicos adicionales

**Actores**: Usuario, Agente MSI-a

**Precondiciones**: Expediente creado, lista de elementos definida

**Flujo Normal**:
1. Agente: "Elemento 1 de 3: Escape. Envíame las fotos necesarias. Cuando termines escribe 'listo'."
2. Usuario: [Envía 2 fotos del escape]
3. Usuario: "Listo"
4. Agente: [Llama `confirmar_fotos_elemento`]
5. Sistema: [Verifica que no hay campos requeridos para este elemento]
6. Agente: [Llama `completar_elemento_actual` automáticamente]
7. Agente: "Perfecto. Pasamos al siguiente elemento: Manillar..."

**Postcondiciones**: Elemento marcado como "complete", avance a siguiente elemento

### Caso de Uso 2: Elemento con Campos Técnicos (Modo Batch)

**Nombre**: Recolección batch de datos técnicos

**Descripción**: Elemento con múltiples campos simples, recolectados todos juntos

**Flujo**:
1. Agente: "Elemento 2 de 3: Soporte. Envíame las fotos..."
2. Usuario: [Envía fotos] + "Listo"
3. Agente: [Llama `confirmar_fotos_elemento`]
4. Agente: "Ahora necesito los datos técnicos. Dime:
           • Altura en mm
           • Anchura en mm
           • Profundidad en mm
           • Peso en kg"
5. Usuario: "Altura 120, anchura 80, profundidad 40, peso 2.5"
6. Agente: [Llama `guardar_datos_elemento` con todos los campos]
7. Agente: [Llama `completar_elemento_actual`]
8. Agente: "Perfecto. Pasamos al siguiente elemento..."

### Caso de Uso 3: Elemento con Campos Condicionales (Modo Híbrido)

**Nombre**: Recolección híbrida con campos condicionales

**Descripción**: Elemento donde algunos campos dependen del valor de otros

**Flujo**:
1. Agente: "Elemento 1 de 2: Asideros. Envíame las fotos..."
2. Usuario: [Envía fotos] + "Listo"
3. Agente: "Ahora los datos técnicos. Primero dime:
           • Tipo de asidero (fijo o abatible)
           • Material"
4. Usuario: "Fijo y aluminio"
5. Agente: [Guarda campos base]
6. Agente: [Detecta que tipo="fijo" activa campos adicionales]
7. Agente: "Como es fijo, también necesito:
           • Distancia entre ejes
           • Peso máximo soportado"
8. Usuario: "Distancia 300mm, peso 50kg"
9. Agente: [Guarda campos condicionales]
10. Agente: [Completa elemento]

### Caso de Uso 4: Reenvío de Imágenes de Ejemplo

**Nombre**: Usuario solicita ver ejemplos nuevamente

**Descripción**: Durante la recolección de fotos, usuario pide ver ejemplos

**Flujo**:
1. Agente: "Elemento 1 de 2: Escape. Envíame las fotos..."
2. Usuario: "¿Puedes mostrarme de nuevo cómo deben ser las fotos?"
3. Agente: [Llama `reenviar_imagenes_elemento`]
4. Agente: [Muestra imágenes de ejemplo del escape]
5. Agente: "Estas son las fotos que necesito. Cuando las tengas, envíamelas."
6. Usuario: [Envía fotos] + "Listo"
7. [Continúa flujo normal]

### Caso de Uso 5: Validación Fallida de Campos

**Nombre**: Manejo de datos inválidos

**Descripción**: Usuario proporciona datos que no pasan validación

**Flujo**:
1. Agente: "Dime la altura en milímetros"
2. Usuario: "Doce centímetros"
3. Agente: [Intenta guardar, validación falla]
4. Agente: "Por favor, indica solo el número en milímetros. Por ejemplo: 120"
5. Usuario: "120"
6. Agente: [Guarda exitosamente]
7. [Continúa flujo normal]

---

## 💬 Interacciones Típicas

### Escenario 1: Flujo Completo - 2 Elementos

```
Agente: ¡Perfecto! Tu expediente está creado. Vamos a recopilar la 
       información de cada elemento.

       Elemento 1 de 2: Escape
       Envíame las fotos del escape (vista general, detalle de 
       marca/modelo, y vista de instalación). Cuando hayas terminado, 
       escribe "listo".

Usuario: [Envía 3 fotos]
Usuario: Listo

Agente: [Procesa fotos] 
       
       Gracias. Ahora necesito algunos datos técnicos:
       • ¿Es escape homologado o específico para tu modelo?
       • ¿Tiene catalizador? (sí/no)

Usuario: Es específico, sí tiene catalizador

Agente: [Guarda datos]
       
       Perfecto. Pasamos al siguiente elemento.

       Elemento 2 de 2: Manillar
       Envíame las fotos del manillar...
       [...]
```

### Escenario 2: Consulta Off-topic Durante Recolección

```
Agente: Elemento 1 de 3: Escape. Envíame las fotos...

Usuario: ¿Cuánto tiempo tarda la homologación en general?

Agente: [Detecta digresión]
       
       El tiempo de homologación varía según la ITV y la carga de trabajo,
       pero generalmente toma entre 2 y 4 semanas desde que entregamos 
       la documentación.

       Volviendo a tu expediente: necesito las fotos del escape.
       Cuando las tengas, escribe "listo".

Usuario: [Envía fotos]
       [...]
```

**Resultado**: Digresión manejada, contexto recuperado

### Escenario 3: Usuario Intenta Saltarse Paso

```
Agente: Elemento 1 de 2: Escape. Envíame las fotos primero...

Usuario: La altura es 120mm y el peso 3kg

Agente: Gracias por la información, pero primero necesito las fotos 
       del escape. Los datos técnicos los pediré después.

       Por favor, envíame las fotos y luego escribe "listo".

Usuario: Ah perdón, aquí van las fotos [envía fotos]
       Listo

Agente: [Procesa fotos]
       
       Gracias. Ahora sí, dime los datos técnicos:
       • Altura: 120mm
       • Peso: 3kg
       
       ¿Hay algo más que deba saber sobre el escape?
       [...]
```

**Resultado**: Recuperación de secuencia, información reutilizada

---

## ⚠️ Consideraciones de Diseño

### Decisiones Arquitectónicas

1. **Procesamiento Secuencial vs Paralelo**
   - **Contexto**: ¿Procesar todos los elementos simultáneamente o uno por uno?
   - **Opciones consideradas**: Paralelo (todas las fotos juntas) vs Secuencial (uno por uno)
   - **Decisión tomada**: Secuencial con índice y tracking de estado por elemento
   - **Justificación**: Menor carga cognitiva para el usuario, mejor organización de datos
   - **Consecuencias**: Conversación más larga pero más clara y manejable

2. **Fase de Fotos antes que Datos**
   - **Contexto**: ¿Permitir enviar datos técnicos antes de fotos?
   - **Decisión tomada**: Fotos primero obligatoriamente
   - **Justificación**: Evita expedientes incompletos, documentación es prioridad legal
   - **Consecuencias**: Secuencia rígida pero más robusta

3. **Smart Collection Mode**
   - **Contexto**: ¿Cómo optimizar la recolección de múltiples campos?
   - **Decisión tomada**: Tres modos según análisis de campos (SEQUENTIAL, BATCH, HYBRID)
   - **Justificación**: Equilibrio entre eficiencia (menos mensajes) y claridad (no abrumar)
   - **Consecuencias**: Lógica más compleja pero mejor UX

4. **Auto-completado sin Campos**
   - **Contexto**: ¿Qué hacer si un elemento no tiene campos técnicos requeridos?
   - **Decisión tomada**: Auto-completar después de fotos
   - **Justificación**: Evita bucles innecesarios de "listo" → "no hay más que preguntar"
   - **Consecuencias**: Flujo variable según elemento, menos predecible

### Limitaciones y Restricciones

- No se pueden agregar elementos adicionales una vez iniciado el estado (debe cancelarse y reiniciar)
- No se puede cambiar el orden de elementos ya establecido
- No hay "undo" de fotos ya confirmadas (debe escalarse a humano para correcciones)
- Los campos condicionales solo soportan un nivel de anidamiento
- No se pueden recolectar datos de múltiples elementos simultáneamente

### Supuestos

- El usuario tiene acceso al vehículo para tomar fotos durante la conversación
- El usuario conoce o puede medir las especificaciones técnicas requeridas
- Las fotos serán enviadas en un número razonable de mensajes (< 10 por elemento)
- El usuario responderá "listo" explícitamente (no se detecta automáticamente por imágenes solas)

---

## 🔗 Dependencias

### Dependencias de Entrada

| Dependencia | Tipo | Descripción | Crítica |
|-------------|------|-------------|---------|
| Expediente creado | Estado | Debe existir caso en DB con ID válido | Sí |
| Lista de elementos | Datos | Códigos de elementos a procesar | Sí |
| Definición de elementos | Servicio | Sistema de elementos debe conocer campos requeridos por código | Sí |
| Sistema de imágenes | Servicio | Debe procesar y almacenar fotos recibidas | Sí |

### Dependencias de Salida

| Dependencia | Tipo | Descripción | Consumidor |
|-------------|------|-------------|------------|
| Datos de elementos completos | Datos | Todos los campos técnicos recolectados | Revisión por agente humano |
| Imágenes asociadas | Datos | Fotos vinculadas al caso | Revisión por agente humano |
| Estado de completitud | Evento | Confirmación de que todos los elementos están listos | Estado COLLECT_BASE_DOCS |

### Acoplamiento

- **Acoplamiento de entrada**: Alto - Depende completamente de datos del estado IDLE
- **Acoplamiento de salida**: Alto - Produce datos esenciales para todo el flujo posterior
- **Acoplamiento temporal**: Alto - Debe completarse antes de continuar

---

## 📈 Métricas y Monitoreo

### Indicadores de Éxito

| Métrica | Definición | Objetivo | Frecuencia |
|---------|------------|----------|------------|
| Tiempo por elemento | Tiempo promedio desde inicio hasta completar un elemento | < 5 min | Diaria |
| Tasa de completitud | % de elementos que se completan sin escalación | > 85% | Semanal |
| Reintentos de fotos | Promedio de veces que se reenvían fotos por elemento | < 1.2 | Diaria |
| Validaciones fallidas | % de intentos de guardar_datos_elemento que fallan validación | < 20% | Diaria |

### Indicadores de Problemas

| Señal | Descripción | Umbral | Acción |
|-------|-------------|--------|--------|
| Abandono en recolección | Usuarios que no completan todos los elementos | > 25% | Revisar complejidad de campos |
| Tiempo excesivo | Elementos que toman > 15 min | > 10% | Revisar modo de colección |
| Errores de campo | Campos que siempre fallan validación | > 30% | Revisar reglas de validación |
| Solicitudes de reenvío | Usuarios que piden ver ejemplos múltiples veces | > 15% | Mejorar calidad de imágenes de ejemplo |

---

## 📝 Glosario Específico

|Término | Definición |
|--------|------------|
| **Elemento** | Componente específico a homologar dentro de un expediente |
| **Fase** | Sub-estado dentro de la recolección: "photos" o "data" |
| **Campo técnico** | Dato específico requerido para un elemento (ej: altura, peso, material) |
| **field_key** | Identificador técnico de un campo (ej: "altura_mm", "peso_kg") |
| **Modo de colección** | Estrategia de preguntas: SECUENCIAL (uno por uno), BATCH (todos juntos), HYBRID (mixto) |
| **Campos condicionales** | Campos que solo se muestran si otro campo tiene cierto valor |
| **Current element index** | Posición (0-based) del elemento que se está procesando actualmente |
| **Element data status** | Mapa que indica el estado de completitud de cada elemento |

---

## 📚 Referencias

### Documentación Relacionada
- [01-estado-idle.md](01-estado-idle.md) - Estado anterior (origen de datos)
- [03-estado-collect-base-docs.md](03-estado-collect-base-docs.md) - Siguiente estado
- [08-transiciones-fsm.md](08-transiciones-fsm.md) - Matriz de transiciones

### Historial de Cambios

| Versión | Fecha | Autor | Cambios |
|---------|-------|-------|---------|
| 1.0 | Febrero 2026 | Equipo de Arquitectura | Creación inicial basada en sistema actual |

---

## 🤔 Preguntas Abiertas

1. ¿Deberíamos permitir pausar la recolección y continuar después (guardar borrador)?
2. ¿Cómo manejar elementos que requieren mediciones que el usuario no puede hacer (necesita taller)?
3. ¿Deberíamos permitir agregar elementos adicionales durante este estado?

---

**Nota**: Este es el estado más complejo de la FSM. Requiere especial atención en testing debido a la variabilidad de elementos y campos.
