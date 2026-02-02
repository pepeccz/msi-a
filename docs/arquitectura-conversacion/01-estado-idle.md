# Arquitectura de Conversación - Estado: IDLE (Presupuestación)

## 📋 Metadatos del Estado

| Campo | Valor |
|-------|-------|
| **Nombre del Estado** | IDLE (Presupuestación) |
| **Código del Estado** | `idle` |
| **Versión** | 1.0 |
| **Fecha de Creación** | Febrero 2026 |
| **Última Modificación** | Febrero 2026 |
| **Responsable** | Equipo de Conversación |
| **Estado de Implementación** | En producción |

---

## 🎯 Propósito y Alcance

### Objetivo Principal
Atender solicitudes de presupuesto y consulta de homologación, identificar los elementos que el usuario quiere homologar, resolver ambigüedades mediante variantes, calcular tarifas y presentar propuestas claras al usuario.

### Objetivos Secundarios
- Clasificar el tipo de vehículo del usuario
- Responder consultas generales sobre homologación
- Preparar la transición hacia la creación de expedientes
- Gestionar escalaciones a agentes humanos cuando sea necesario

### Definición del Éxito
El estado se considera completado exitosamente cuando:
1. Se ha identificado al menos un elemento válido para homologación
2. Se ha calculado y comunicado una tarifa al usuario
3. Se ha mostrado la documentación requerida
4. El usuario ha sido informado de los siguientes pasos (crear expediente o hacer más preguntas)

---

## 🔄 Contexto de Navegación

### Estados Predecesores

| Estado Origen | Activador de Transición | Condiciones |
|---------------|------------------------|-------------|
| START | Primer mensaje del usuario | Ninguna (estado inicial por defecto) |
| COMPLETED | Expediente anterior finalizado | Usuario inicia nueva consulta |
| Cualquier estado | `cancelar_expediente()` | Usuario decide cancelar expediente en curso |

### Estados Sucesores

| Estado Destino | Activador de Transición | Condiciones |
|----------------|------------------------|-------------|
| COLLECT_ELEMENT_DATA | `iniciar_expediente()` | Usuario confirma que quiere proceder después del presupuesto |
| IDLE (loop) | N/A | Usuario hace más preguntas sin confirmar expediente |
| (Escalación) | `escalar_a_humano()` | Usuario solicita agente humano o caso complejo |

---

## 🎬 Activadores de Entrada

### Eventos que Inician este Estado

1. **Inicio de Conversación**
   - **Descripción**: Primer contacto del usuario con el agente
   - **Origen**: Usuario envía mensaje inicial por WhatsApp
   - **Datos asociados**: Número de teléfono, nombre de WhatsApp, posible mensaje de saludo

2. **Reinicio Post-Expediente**
   - **Descripción**: Usuario completa un expediente y vuelve a consultar
   - **Origen**: Usuario
   - **Datos asociados**: Historial previo, datos personales ya conocidos

3. **Cancelación de Expediente en Curso**
   - **Descripción**: Usuario abandona un expediente activo
   - **Origen**: Usuario (comando "cancelar" o similar)
   - **Datos asociados**: Datos parciales del expediente cancelado (pueden reutilizarse)

### Condiciones de Entrada

- El agente está habilitado globalmente (no hay "panic button" activo)
- No hay un expediente activo en curso para esta conversación
- La conversación no está escalada a un agente humano

---

## 🛠️ Capacidades del Agente

### Herramientas Disponibles

#### Herramientas de Consulta

| Herramienta | Propósito | Datos Requeridos | Datos Producidos |
|-------------|-----------|------------------|------------------|
| `listar_categorias` | Mostrar tipos de vehículos soportados | Tipo de cliente (particular/profesional) | Lista de categorías con descripciones |
| `listar_tarifas` | Mostrar estructura de precios por categoría | Slug de categoría, tipo de cliente | Tiers de tarifas con rangos de precios |
| `listar_elementos` | Mostrar elementos homologables en una categoría | Slug de categoría | Lista de elementos con códigos y descripciones |
| `obtener_servicios_adicionales` | Informar sobre servicios extra (certificados, urgencias) | Opcional: categoría | Lista de servicios y precios adicionales |
| `identificar_tipo_vehiculo` | Determinar categoría a partir de marca/modelo | Marca, modelo | Tipo de vehículo, confianza, categoría sugerida |
| `obtener_documentacion_elemento` | Consultar documentación específica de un elemento | Categoría, código de elemento | Descripción de fotos requeridas, ejemplos |

#### Herramientas de Acción

| Herramienta | Propósito | Efecto en el Estado | Efecto en el Sistema |
|-------------|-----------|---------------------|---------------------|
| `identificar_y_resolver_elementos` | Identificar elementos desde descripción del usuario | Actualiza `pending_variants` si hay ambigüedades | Consulta a base de datos |
| `seleccionar_variante_por_respuesta` | Resolver variante pendiente | Actualiza elementos seleccionados | Ninguno (operación de estado) |
| `calcular_tarifa_con_elementos` | Calcular precio total | Actualiza `tarifa_actual` con precio, warnings, documentación | Ninguno (operación de estado) |
| `enviar_imagenes_ejemplo` | Enviar fotos de ejemplo de documentación | Marca `images_sent_for_current_quote` | Ninguno (cola de envío) |
| `iniciar_expediente` | Crear caso y transicionar a recolección de datos | Transiciona a COLLECT_ELEMENT_DATA | Persiste Case en base de datos |

#### Herramientas de Transición

| Herramienta | Propósito | Estado Resultante | Condiciones |
|-------------|-----------|-------------------|-------------|
| `iniciar_expediente` | Iniciar proceso de expediente | COLLECT_ELEMENT_DATA | Usuario confirmó, hay tarifa calculada |
| `escalar_a_humano` | Solicitar agente humano | (Fuera de FSM - escalación) | Solicitud explícita o caso complejo |

### Herramientas Restringidas

| Herramienta | Razón de Restricción | Alternativa Disponible |
|-------------|---------------------|------------------------|
| `confirmar_fotos_elemento` | Requiere expediente activo | No disponible en IDLE |
| `guardar_datos_elemento` | Requiere contexto de elemento | No disponible en IDLE |
| `actualizar_datos_expediente` | Requiere expediente creado | No disponible en IDLE |
| `finalizar_expediente` | Requiere estar en REVIEW_SUMMARY | No disponible en IDLE |

---

## 📊 Datos del Estado

### Datos de Entrada

| Dato | Tipo | Obligatorio | Fuente | Descripción |
|------|------|-------------|--------|-------------|
| Tipo de cliente | Categórico | Sí | Configuración de usuario | "particular" o "professional" - afecta precios |
| Historial de mensajes | Lista | No | Conversación previa | Contexto de interacciones anteriores |
| Datos personales previos | Estructurado | No | Expedientes anteriores | Para reutilizar en futuros expedientes |
| Preferencias de usuario | Estructurado | No | Perfil de usuario | Preferencias aprendidas del usuario |

### Datos de Salida

| Dato | Tipo | Obligatorio | Destino | Descripción |
|------|------|-------------|---------|-------------|
| Elementos identificados | Lista | Sí (para transición) | Transición a COLLECT_ELEMENT_DATA | Códigos de elementos a homologar |
| Tarifa calculada | Estructurado | Sí (para transición) | Transición a COLLECT_ELEMENT_DATA | Tier, precio, warnings, documentación |
| Variantes resueltas | Lista | No | Estado interno | Decisiones de variantes tomadas |
| Decisión de usuario | Booleano | No | Estado interno | Si quiere proceder con expediente |

### Datos Temporales

| Dato | Tipo | Duración | Descripción |
|------|------|----------|-------------|
| `tarifa_actual` | Estructurado | Durante estado IDLE | Última tarifa calculada (se borra al iniciar expediente) |
| `pending_variants` | Lista | Hasta resolución | Variantes de elementos pendientes de decisión |
| `images_sent_for_current_quote` | Booleano | Durante estado IDLE | Evita reenvío de imágenes |
| `price_communicated_to_user` | Booleano | Durante estado IDLE | Valida que precio fue mencionado antes de imágenes |
| `pending_action` | Categórico | Hasta confirmación/rechazo | Acción esperando confirmación (ej: "iniciar_expediente") |

### Estado Interno

| Variable | Valores Posibles | Significado | Transiciones Internas |
|----------|-------------------|-------------|----------------------|
| Fase de presupuestación | `identifying` → `calculating` → `presenting` → `confirming` | Progreso dentro del estado | Cambia herramientas disponibles y mensajes |
| Número de iteraciones | 0, 1, 2, 3... | Cuántas vueltas de identificación | Si > 3, sugerir escalación |
| Última acción fallida | Código de herramienta | Qué herramienta falló última | Afecta mensaje de error siguiente |

---

## 📜 Reglas de Negocio

### Reglas de Ejecución

1. **Identificación antes que Precio**
   - **Descripción**: No se puede calcular tarifa sin identificar elementos primero
   - **Prioridad**: Alta
   - **Consecuencia de incumplimiento**: Error de secuencia, usuario confundido

2. **Variantes deben Resolverse**
   - **Descripción**: Si hay elementos con variantes pendientes, deben resolverse antes de calcular precio
   - **Prioridad**: Alta
   - **Consecuencia de incumplimiento**: Precio incompleto o incorrecto

3. **Comunicación de Precio antes de Imágenes**
   - **Descripción**: El precio debe mencionarse explícitamente antes de enviar fotos de ejemplo
   - **Prioridad**: Crítica
   - **Consecuencia de incumplimiento**: Bloqueo de herramienta `enviar_imagenes_ejemplo`

4. **No Reenvío de Imágenes**
   - **Descripción**: Las imágenes de ejemplo solo se envían una vez por presupuesto
   - **Prioridad**: Media
   - **Consecuencia de incumplimiento**: Spam de imágenes al usuario

5. **Validación de Categoría**
   - **Descripción**: Solo categorías soportadas para el tipo de cliente
   - **Prioridad**: Alta
   - **Consecuencia de incumplimiento**: Error técnico, confusión del usuario

6. **Precisión en Warnings**
   - **Descripción**: Todos los warnings de la tarifa calculada deben comunicarse al usuario
   - **Prioridad**: Alta
   - **Consecuencia de incumplimiento**: Usuario desinformado, problemas legales

### Reglas de Confirmación

1. **Confirmación Explícita para Expediente**
   - **Condición**: El usuario debe confirmar explícitamente (no ambigua) antes de iniciar expediente
   - **Validación requerida**: Detección de confirmación vía patterns, fuzzy matching o LLM
   - **Rollback posible**: No aplica (no hay cambio de estado aún)

2. **Confirmación Clara vs Ambigua**
   - Palabras confirmadoras claras: "sí", "dale", "vale", "ok", "adelante"
   - Contextos ambiguos: "vale la pena", "eso sí", preguntas
   - En caso de duda: Preguntar confirmación explícita

---

## 🎭 Casos de Uso

### Caso de Uso Principal: Presupuesto Simple

**Nombre**: Solicitud directa de presupuesto

**Descripción**: Usuario sabe qué quiere homologar y solicita presupuesto directamente

**Actores**: Usuario particular, Agente MSI-a

**Precondiciones**: Usuario no tiene expediente activo

**Flujo Normal**:
1. Usuario: "Quiero homologar el escape de mi moto"
2. Agente: Identifica elemento "ESCAPE"
3. Agente: Calcula tarifa (ej: 280 EUR + IVA)
4. Agente: Menciona warnings si los hay
5. Agente: Envía imágenes de ejemplo (después de mencionar precio)
6. Agente: Pregunta si quiere abrir expediente
7. Usuario: "Sí, adelante"
8. Agente: Transiciona a COLLECT_ELEMENT_DATA

**Flujos Alternativos**:
- **A1**: Elemento tiene variantes → Agente pregunta por variante específica → Usuario responde → Continúa
- **A2**: Varios elementos mencionados → Agente identifica múltiples → Calcula tarifa combinada → Continúa
- **A3**: Usuario pregunta algo no relacionado → Agente responde consulta → Vuelve a presupuestación

**Excepciones**:
- **E1**: Elemento no encontrado → Agente pide aclaración o sugiere consulta a humano
- **E2**: Usuario insiste sin dar información clara → Agente sugiere escalación

**Postcondiciones**: Tarifa calculada, usuario informado, listo para iniciar expediente

### Caso de Uso 2: Presupuesto con Variantes

**Nombre**: Resolución de variantes de elemento

**Descripción**: Usuario menciona elemento que tiene múltiples variantes (ej: "suspensión")

**Flujo**:
1. Usuario: "Quiero homologar la suspensión"
2. Agente: Identifica elemento con variantes (SUSPENSION)
3. Agente: Presenta opciones (delantera/trasera) y pregunta cuál
4. Usuario: "La delantera"
5. Agente: Resuelve variante usando `seleccionar_variante_por_respuesta`
6. Agente: Procede a calcular tarifa con SUSPENSION_DEL
7. Agente: Presenta presupuesto

### Caso de Uso 3: Consulta General

**Nombre**: Usuario no sabe qué puede homologar

**Descripción**: Usuario pregunta qué opciones tiene para su vehículo

**Flujo**:
1. Usuario: "¿Qué puedo homologar en mi moto?"
2. Agente: Lista categorías o elementos disponibles
3. Usuario: Elige o pregunta más detalles
4. Agente: Proporciona información específica
5. (Opcional) Usuario solicita presupuesto de elementos específicos

---

## 💬 Interacciones Típicas

### Escenario 1: Flujo Ideal Simple

```
Usuario: Hola, quiero homologar el escape de mi Kawasaki Z900
Agente: ¡Hola! Te ayudo con el presupuesto para homologar el escape
       de tu Kawasaki Z900.

       El presupuesto es de 280 EUR + IVA (No se incluye el certificado 
       del taller de montaje).

       [Envía 3 imágenes de ejemplo del escape]

       ¿Te gustaría que te abriera un expediente para gestionar 
       tu homologación?

Usuario: Sí, perfecto
Agente: ¡Excelente! Voy a crear tu expediente ahora...
       [Transiciona a COLLECT_ELEMENT_DATA]
```

**Resultado**: Presupuesto entregado, expediente iniciado

### Escenario 2: Variantes de Elemento

```
Usuario: Quiero homologar la suspensión
Agente: Perfecto. Veo que hay diferentes opciones de suspensión:
       
       ¿Es la suspensión delantera o trasera?

Usuario: La delantera
Agente: [Resuelve variante]

       El presupuesto para homologar la suspensión delantera es de 
       450 EUR + IVA...
       [...]
```

**Resultado**: Variante resuelta, presupuesto específico entregado

### Escenario 3: Varios Elementos

```
Usuario: Quiero homologar el escape, el manillar y el subchasis
Agente: Entiendo que quieres homologar:
       • Escape
       • Manillar
       • Subchasis

       Déjame calcular el presupuesto...

       El presupuesto total es de 890 EUR + IVA...
       [...]
```

**Resultado**: Múltiples elementos identificados, presupuesto combinado

### Escenario 4: Manejo de Error (Elemento No Encontrado)

```
Usuario: Quiero homologar el turbo
Agente: Lo siento, no encontré "turbo" en nuestra lista de elementos 
       homologables para motos.

       ¿Quizás te refieres a alguno de estos?
       • Escape
       • Admisión de aire
       • Sistema de refrigeración

       O si prefieres, puedo conectarte con un agente humano que 
       te asesore mejor.

Usuario: Mejor hablo con una persona
Agente: Perfecto, te conecto ahora mismo con uno de nuestros agentes...
       [Escalación iniciada]
```

**Resultado**: Error manejado graceful, escalación ofrecida y aceptada

### Escenario 5: Confirmación Ambigua

```
Usuario: Vale la pena hacer la homologación?
Agente: Depende de tus necesidades. La homologación es obligatoria 
       para modificaciones en el vehículo. Sin ella, podrías tener 
       problemas en la ITV.

       ¿Te gustaría que calcule el presupuesto para tu caso específico?

Usuario: Sí, cuánto sería
Agente: [Procede a identificar elementos]
       ...
       ¿Te gustaría que te abriera un expediente?

Usuario: Vale
Agente: Perdón, no estoy seguro de entender. ¿Quieres que abra 
       el expediente para gestionar tu homologación? 
       Responde "sí" para confirmar o "no" para cancelar.
```

**Resultado**: Confirmación ambigua detectada, aclaración solicitada

---

## ⚠️ Consideraciones de Diseño

### Decisiones Arquitectónicas

1. **Separación de Identificación y Cálculo**
   - **Contexto**: ¿Debería una sola herramienta identificar elementos Y calcular precio?
   - **Opciones consideradas**: Herramienta única vs herramientas separadas
   - **Decisión tomada**: Herramientas separadas (`identificar_y_resolver_elementos` y `calcular_tarifa_con_elementos`)
   - **Justificación**: Permite validar elementos antes de calcular, mejor manejo de errores
   - **Consecuencias**: Flujo más largo pero más robusto

2. **Gestión de Variantes como Estado Temporal**
   - **Contexto**: ¿Cómo manejar elementos que requieren decisión adicional?
   - **Opciones consideradas**: Prompt dinámico vs estado persistente
   - **Decisión tomada**: `pending_variants` como dato temporal del estado
   - **Justificación**: Necesario recordar variantes pendientes entre mensajes
   - **Consecuencias**: Complejidad adicional pero mejor UX

3. **Bloqueo de Imágenes sin Precio**
   - **Contexto**: ¿Permitir enviar fotos antes de dar precio?
   - **Opciones consideradas**: Libre vs restringido
   - **Decisión tomada**: Bloquear si `price_communicated_to_user` es falso
   - **Justificación**: Contexto de negocio: usuario debe saber precio antes de ver requisitos
   - **Consecuencias**: Validación adicional, posible frustración si se olvida mencionar precio

### Limitaciones y Restricciones

- No se pueden identificar elementos de múltiples categorías simultáneamente (ej: moto Y coche)
- No hay manejo de descuentos o promociones dinámicas en este estado
- No se pueden modificar elementos ya identificados sin reiniciar el proceso
- Las variantes deben resolverse una por una (no hay selección múltiple de variantes)

### Supuestos

- El usuario generalmente sabe qué tipo de vehículo tiene (o lo proporcionará)
- Las descripciones de elementos serán en español
- El usuario entiende conceptos básicos de homologación
- La base de datos de elementos está actualizada y completa

---

## 🔗 Dependencias

### Dependencias de Entrada

| Dependencia | Tipo | Descripción | Crítica |
|-------------|------|-------------|---------|
| Sistema de Categorías | Servicio | Debe conocer qué categorías existen | Sí |
| Sistema de Tarifas | Servicio | Debe poder calcular precios | Sí |
| Sistema de Elementos | Servicio | Debe identificar elementos de descripciones | Sí |
| Base de Datos de Imágenes | Datos | Debe tener ejemplos de fotos | No (fallback a descripción textual) |
| Configuración de Cliente | Datos | Tipo de cliente (particular/pro) | Sí |

### Dependencias de Salida

| Dependencia | Tipo | Descripción | Consumidor |
|-------------|------|-------------|------------|
| Elementos seleccionados | Datos | Lista final de códigos | Estado COLLECT_ELEMENT_DATA |
| Tarifa calculada | Datos | Precio, warnings, documentación | Estado COLLECT_ELEMENT_DATA |
| Decisión de expediente | Evento | Si el usuario quiere proceder | Transición de estado |

### Acoplamiento

- **Acoplamiento de entrada**: Bajo - Solo requiere tipo de cliente y mensaje del usuario
- **Acoplamiento de salida**: Alto - Produce datos cruciales para todo el flujo posterior
- **Acoplamiento temporal**: Medio - La tarifa debe calcularse antes de iniciar expediente

---

## 📈 Métricas y Monitoreo

### Indicadores de Éxito

| Métrica | Definición | Objetivo | Frecuencia |
|---------|------------|----------|------------|
| Tasa de Identificación | % de mensajes donde se identifican elementos válidos | > 70% | Diaria |
| Tiempo de Presupuesto | Tiempo promedio desde consulta hasta presupuesto entregado | < 3 min | Diaria |
| Tasa de Conversión | % de presupuestos que resultan en expediente iniciado | > 40% | Semanal |
| Satisfacción de Usuario | Feedback implícito (reintentos vs confirmación) | < 20% reintentos | Diaria |

### Indicadores de Problemas

| Señal | Descripción | Umbral | Acción |
|-------|-------------|--------|--------|
| Alta tasa de "elemento no encontrado" | Elementos solicitados no existen en DB | > 15% | Revisar cobertura de catálogo |
| Múltiples intentos de identificación | Usuario reintenta descripciones | > 2 por conversación | Revisar calidad de matching |
| Confirmaciones ambiguas frecuentes | Usuario usa lenguaje no claro | > 30% | Mejorar detección de intención |
| Bloqueos de imágenes | Herramienta rechaza envío por falta de precio | > 10% | Entrenar prompt de precio |

---

## 📝 Glosario Específico

|Término | Definición |
|--------|------------|
| **Elemento** | Componente de vehículo que puede ser homologado (ej: escape, suspensión) |
| **Variante** | Subtipo de elemento que requiere especificación (ej: suspensión delantera vs trasera) |
| **Variante Pendiente** | Variante que necesita decisión del usuario antes de continuar |
| **Tarifa** | Estructura de precios para una combinación de elementos |
| **Tier** | Nivel de precios según cantidad/complejidad de elementos |
| **Warning** | Advertencia específica sobre un elemento o combinación |
| **Categoría** | Clasificación del vehículo (moto, autocaravana, etc.) |
| **Slug** | Identificador técnico de categoría (ej: "motos-part") |

---

## 📚 Referencias

### Documentación Relacionada
- [02-estado-collect-element-data.md](02-estado-collect-element-data.md) - Siguiente estado en el flujo
- [08-transiciones-fsm.md](08-transiciones-fsm.md) - Matriz de transiciones completa

### Decisiones de Arquitectura
- ADR-002: Dynamic Prompts (Optimización de tokens)
- ADR-001: Redis Streams (Arquitectura de mensajería)

### Historial de Cambios

| Versión | Fecha | Autor | Cambios |
|---------|-------|-------|---------|
| 1.0 | Febrero 2026 | Equipo de Arquitectura | Creación inicial basada en sistema actual |

---

## 🤔 Preguntas Abiertas

1. ¿Deberíamos soportar presupuestos de múltiples categorías simultáneamente (ej: usuario tiene moto Y coche)?
2. ¿Cómo manejar elementos que el usuario quiere "quizás" homologar (presupuesto opcional)?
3. ¿Deberíamos permitir guardar presupuestos para recuperarlos después?

---

**Nota**: Esta es una definición arquitectónica. La implementación técnica debe alinearse con estas especificaciones pero puede incluir detalles adicionales propios de la tecnología utilizada.
