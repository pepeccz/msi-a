# Modo: CONSULTA_MODE

## 📋 Metadatos

| Campo | Valor |
|-------|-------|
| **Nombre del Modo** | CONSULTA_MODE |
| **Código Técnico** | `consulta_mode` |
| **Versión** | 1.0 (v2.0) |
| **Fecha** | Febrero 2026 |
| **% Tráfico Esperado** | 10% |
| **Complejidad** | Baja |
| **Tipo** | Permisivo (no bloqueante) |

---

## 🎯 Propósito y Alcance

### Objetivo Principal
Educar al usuario sobre homologación y responder preguntas informativas generales antes de que decida explorar viabilidad o presupuesto.

### Definición de Éxito
El modo se considera exitoso cuando el usuario:
1. Obtiene respuesta satisfactoria a su consulta, **O**
2. Expresa interés en evaluar viabilidad de una modificación específica, **O**
3. Solicita directamente un presupuesto

### Qué NO Hace Este Modo
- ❌ No calcula presupuestos (va a PRESUPUESTO_MODE)
- ❌ No evalúa viabilidad técnica detallada (va a VIABILIDAD_MODE)
- ❌ No recolecta datos personales
- ❌ No inicia expedientes
- ❌ No valida elementos contra base de datos

---

## 🔄 Contexto de Navegación

### Modos Predecesores

| Modo Origen | Activador | Condición |
|-------------|-----------|-----------|
| **START** | Clasificador de intención | Intent=consulta_general (confidence ≥75%) |
| **START** | Clasificador de intención | Intent=ambiguo (confidence <75%, default seguro) |
| **VIABILIDAD_MODE** | Transición manual | Usuario tiene dudas generales durante evaluación |
| **PRESUPUESTO_MODE** | Transición manual | Usuario rechaza presupuesto y vuelve a preguntar |

### Modos Sucesores

| Modo Destino | Activador | Condición |
|--------------|-----------|-----------|
| **VIABILIDAD_MODE** | Intent detectado | Usuario pregunta "¿Se puede homologar X?" |
| **VIABILIDAD_MODE** | Transición manual | Usuario dice "Quiero saber si se puede..." |
| **PRESUPUESTO_MODE** | Intent detectado | Usuario pide directamente "¿Cuánto cuesta Y?" |
| **(END)** | Conversación terminada | Usuario dice "Gracias, eso es todo" |

### Transiciones PROHIBIDAS desde CONSULTA_MODE

| A | Razón |
|---|-------|
| **EXPEDIENTE_MODE** | Falta evaluación de viabilidad y cálculo de presupuesto |
| **EVALUACIÓN_GATEWAY** | No hay presupuesto calculado para confirmar |

---

## 🛠️ Capacidades y Herramientas

### Herramientas Disponibles (5 herramientas)

#### 1. `responder_consulta_general`

**Tipo**: Consulta RAG  
**Propósito**: Responder preguntas informativas usando documentación regulatoria

**Entrada**:
```python
{
    "consulta": str,           # Pregunta del usuario en lenguaje natural
    "contexto_usuario": str,   # Contexto opcional (tipo de vehículo si se mencionó)
}
```

**Salida**:
```python
{
    "respuesta": str,          # Respuesta generada por LLM basada en RAG
    "fuentes": list[str],      # IDs de documentos usados (para verificación)
    "confianza": float,        # Score de relevancia (0.0-1.0)
    "sugerencias": list[str]   # Preguntas relacionadas sugeridas
}
```

**Reglas de Negocio**:
- Si confianza < 0.6, agregar disclaimer: "Según la documentación disponible..."
- No inventar información no presente en documentos
- Citar fuentes cuando sea relevante

**Modelo de Datos Usado**:
- `RegulatoryDocument` (búsqueda por similitud semántica)
- `DocumentChunk` (chunks relevantes recuperados)

---

#### 2. `explicar_proceso_homologacion`

**Tipo**: Consulta estructurada  
**Propósito**: Explicar paso a paso el proceso de homologación

**Entrada**:
```python
{
    "nivel_detalle": str       # "basico", "detallado", "completo"
}
```

**Salida**:
```python
{
    "explicacion": str,        # Texto explicativo estructurado
    "pasos": list[dict],       # Lista de pasos con descripciones
    "tiempo_estimado": str,    # "2-4 semanas típicamente"
    "costos_indirectos": list  # Certificados, ITV, etc. (conceptuales, no precios)
}
```

**Reglas de Negocio**:
- NUNCA dar plazos garantizados (siempre estimaciones)
- Costos indirectos mencionados sin precios específicos
- Ofrecer escalación a humano si quiere detalles de un caso específico

**Modelo de Datos Usado**:
- `BaseDocumentation` (documentación base requerida, genérica)
- `AdditionalService` (servicios adicionales disponibles, sin precios)

---

#### 3. `listar_categorias`

**Tipo**: Consulta de catálogo  
**Propósito**: Mostrar tipos de vehículos soportados

**Entrada**:
```python
{
    "tipo_cliente": str | None  # "particular" | "professional" | None (ambos)
}
```

**Salida**:
```python
{
    "categorias": list[{
        "slug": str,           # Ej: "motos-part"
        "nombre": str,         # Ej: "Motocicletas"
        "descripcion": str,    # Ej: "Homologaciones para motos particulares"
        "icono": str,          # Emoji: 🏍️
        "tipo_cliente": str    # "particular" | "professional"
    }],
    "total": int
}
```

**Reglas de Negocio**:
- Ordenar por `sort_order` definido en base de datos
- Filtrar por tipo de cliente si se especifica
- Incluir conteo de elementos disponibles por categoría (opcional)

**Modelo de Datos Usado**:
- `VehicleCategory` (filtrado por `client_type`, ordenado por `sort_order`)

---

#### 4. `listar_elementos_generales`

**Tipo**: Consulta de catálogo  
**Propósito**: Mostrar qué elementos se pueden homologar (lista genérica, no específica)

**Entrada**:
```python
{
    "categoria_slug": str | None,  # Filtrar por categoría específica
    "limite": int                  # Máximo elementos a retornar (default 20)
}
```

**Salida**:
```python
{
    "elementos": list[{
        "codigo": str,         # Ej: "ESCAPE"
        "nombre": str,         # Ej: "Escape"
        "descripcion": str,    # Descripción general
        "categoria": str,      # "motos-part"
        "variantes": bool      # True si tiene variantes
    }],
    "total_categoria": int,
    "mas_disponibles": bool
}
```

**Reglas de Negocio**:
- NO incluir información de precios (eso es PRESUPUESTO_MODE)
- NO resolver variantes (solo indicar si tiene o no)
- Mostrar elementos activos (`is_active=True`) únicamente

**Modelo de Datos Usado**:
- `Element` (filtrado por `category_id`, `is_active=True`)

---

#### 5. `escalar_a_humano` (Herramienta Universal)

**Tipo**: Transición / Escalación  
**Propósito**: Transferir conversación a agente humano

**Entrada**:
```python
{
    "motivo": str,             # Descripción del motivo
    "es_error_tecnico": bool,  # False (modo consulta no tiene errores técnicos)
    "contexto": str            # Resumen de la consulta realizada
}
```

**Salida**:
```python
{
    "escalation_id": uuid.UUID,
    "mensaje_confirmacion": str,
    "tiempo_estimado_respuesta": str  # "Un agente te responderá pronto"
}
```

**Modelo de Datos Usado**:
- `Escalation` (crear registro de escalación)

---

### Herramientas NO Disponibles (Intencionalmente)

| Herramienta | Razón de Exclusión | Dónde Está Disponible |
|-------------|-------------------|----------------------|
| `identificar_y_resolver_elementos` | Requiere contexto de presupuesto | VIABILIDAD_MODE, PRESUPUESTO_MODE |
| `calcular_tarifa_con_elementos` | No hay elementos seleccionados | PRESUPUESTO_MODE |
| `enviar_imagenes_ejemplo` | No hay presupuesto calculado | PRESUPUESTO_MODE |
| `iniciar_expediente` | Falta evaluación y presupuesto | EVALUACIÓN_GATEWAY |
| `actualizar_datos_expediente` | No estamos recolectando datos | EXPEDIENTE_MODE |

---

## 📊 Datos del Modo

### Datos de Entrada (Contexto Inicial)

| Dato | Tipo | Obligatorio | Fuente | Descripción |
|------|------|-------------|--------|-------------|
| `user_phone` | str | Sí | Metadata WhatsApp | Teléfono del usuario (E.164) |
| `user_name` | str | No | Metadata WhatsApp | Nombre de WhatsApp |
| `client_type` | str | Sí | Config usuario | "particular" o "professional" |
| `conversation_id` | UUID | Sí | Sistema | ID de conversación Chatwoot |
| `intent_classification` | IntentResult | No | Clasificador | Resultado de clasificación de entrada |

### Datos de Salida (Para Siguiente Modo)

| Dato | Tipo | Destino | Descripción |
|------|------|---------|-------------|
| `temas_consultados` | list[str] | Analytics | Temas que consultó (para mejorar RAG) |
| `categoria_interes` | str | VIABILIDAD_MODE | Categoría que mostró interés |
| `elementos_mencionados` | list[str] | VIABILIDAD_MODE | Elementos mencionados en consultas |
| `satisfaccion` | bool | Analytics | Si quedó satisfecho o pidió más info |

### Datos Temporales (Durante el Modo)

| Dato | Tipo | Duración | Descripción |
|------|------|----------|-------------|
| `consulta_actual` | str | Sesión | Consulta que está respondiendo ahora |
| `rag_queries_made` | list[UUID] | Sesión | IDs de queries RAG realizadas |
| `sugerencias_mostradas` | list[str] | Sesión | Sugerencias que ya mostró |

---

## 📜 Reglas de Negocio

### Reglas de Entrada

1. **Bienvenida Personalizada** (solo primera vez)
   - Si `is_first_interaction=True`: Saludo completo + oferta de ayuda
   - Mensaje: "¡Hola! Soy el asistente virtual de MSI Automotive. Te ayudo con información sobre homologaciones de vehículos. ¿Qué te gustaría saber?"

2. **Detección de Intención de Salida**
   - Si usuario dice "gracias", "eso es todo", "adiós": Ofrecer cerrar o ir a evaluación
   - NO forzar continuación

### Reglas de Ejecución

1. **Prioridad de Respuesta Directa**
   - Si la consulta tiene respuesta clara en RAG: Responder directamente
   - Si es ambigua: Preguntar clarificación antes de buscar
   
2. **Límite de Iteraciones**
   - Máximo 5 consultas generales antes de sugerir evaluación específica
   - Mensaje sugerido: "Veo que tenés varias dudas. ¿Te gustaría que evaluemos una modificación específica para darte información más precisa?"

3. **No Inundar de Información**
   - Respuestas máximo 3 párrafos cortos
   - Ofrecer "¿Querés que profundice en algo específico?"

4. **Transición Proactiva**
   - Detectar cuando el usuario menciona elemento específico
   - Ofrecer: "¿Te gustaría que vea si se puede homologar ese escape para tu moto?"

### Reglas de Salida

1. **Confirmación de Satisfacción**
   - Antes de transicionar: "¿Te quedó claro? ¿Necesitás saber algo más?"
   
2. **Preservación de Contexto**
   - Si mencionó categoría/elementos, pasarlos al siguiente modo
   - Ej: "Veo que te interesa homologar un escape. ¿Te gustaría que evaluemos eso?"

---

## 🚨 Política de Reintentos y Timeouts

### Timeout de Inactividad

| Tiempo | Acción | Mensaje |
|--------|--------|---------|
| **10 minutos** | Nudge primero | "¿Sigues ahí? Respondé cualquier cosa para continuar." |
| **20 minutos** | Reset a CONSULTA_MODE | "Reiniciamos la conversación por inactividad. ¿En qué puedo ayudarte?" |

**Comportamiento en Reset**:
- Limpiar `consulta_actual` temporal
- Mantener `temas_consultados` en analytics
- Resetear contadores de retry

### Política de Reintentos (Errores NLU)

| Situación | Máximo Reintentos | Acción al Alcanzar |
|-----------|-------------------|-------------------|
| No entiende consulta | 3 | Escalar a humano |
| Consulta ambigua | 3 | Ofrecer opciones específicas o escalar |

**Mensajes de Recuperación**:
- Intento 1: "No estoy seguro de entender. ¿Podés reformular?"
- Intento 2: "¿Te referís a información general o a una modificación específica?"
- Intento 3 (último): "Parece que estamos teniendo dificultades para entendernos. ¿Te gustaría que te conecte con un agente?"

---

## 🎭 Casos de Uso e Interacciones

### Caso 1: Consulta General Básica

```
Usuario: ¿Qué es la homologación?
Agente: [CONSULTA_MODE - responder_consulta_general]
       La homologación es el proceso legal que certifica que las 
       modificaciones en tu vehículo cumplen con la normativa de 
       seguridad y medioambiental.

       ¿Querés saber más sobre el proceso o tenés una modificación 
       específica en mente?

Usuario: ¿Es obligatoria?
Agente: [CONSULTA_MODE - responder_consulta_general]
       Sí, es obligatoria para cualquier modificación que afecte 
       la estructura, motor, escape, o seguridad del vehículo.

       Sin homologación, podrías tener problemas en la ITV o incluso 
       multas de tráfico.

Usuario: Ah, gracias, eso es todo
Agente: [CONSULTA_MODE - detectar fin de conversación]
       ¡De nada! Si en el futuro pensás en hacer alguna modificación 
       a tu vehículo, acá estoy para ayudarte a evaluarla.

       ¡Que tengas buen día!
```

**Resultado**: Consulta resuelta, usuario satisfecho, conversación termina.

---

### Caso 2: Consulta → Evaluación de Viabilidad

```
Usuario: ¿Qué tipos de motos pueden homologar?
Agente: [CONSULTA_MODE - listar_categorias]
       Trabajamos con varias categorías:
       • Motocicletas (particulares)
       • Autocaravanas
       • Vehículos de tuning
       
       ¿Qué tipo de vehículo tenés?

Usuario: Tengo una moto
Agente: [CONSULTA_MODE - listar_elementos_generales]
       Perfecto. Para motos podemos homologar:
       • Escape y sistemas de escape
       • Suspensión y amortiguación
       • Manillares y controles
       • Iluminación LED
       • Y 35 elementos más...

       ¿Tenés pensado hacer alguna modificación específica?

Usuario: Quiero ponerle un escape nuevo
Agente: [DETECCIÓN DE TRANSICIÓN]
       ¡Entendido! Un escape es una de las modificaciones más comunes.

       ¿Te gustaría que evalúe si se puede homologar ese escape para 
       tu moto específica?
       
       [TRANSICIÓN → VIABILIDAD_MODE]
```

**Resultado**: Usuario informado, ahora quiere evaluar específicamente.

---

### Caso 3: Recuperación de Error NLU

```
Usuario: La verdad que no sé muy bien qué necesito
Agente: [CONSULTA_MODE - NLU ambiguo, confidence 0.45]
       No hay problema, te ayudo a clarificar.

       ¿Buscás información general sobre cómo funciona la homologación, 
       o tenés una modificación específica en mente y querés saber si 
       se puede homologar?

Usuario: Mmm, no sé, algo así
Agente: [CONSULTA_MODE - Intento 2 de clarificación]
       ¿Tenés una moto, coche, o autocaravana? ¿Y pensás en hacerle 
       algún cambio como un escape, suspensiones, o algo de iluminación?

Usuario: Ah sí, tengo una moto y quiero cambiar el escape
Agente: [CONSULTA_MODE - Ahora sí, entendido]
       ¡Perfecto! Entonces evaluemos eso.
       
       ¿Qué marca y modelo es tu moto? Así veo si el escape que querés 
       se puede homologar.
       [TRANSICIÓN → VIABILIDAD_MODE]
```

**Resultado**: Recuperación exitosa después de 2 intentos de clarificación.

---

### Caso 4: Timeout y Nudge

```
Usuario: ¿Cuánto tarda la homologación?
Agente: [CONSULTA_MODE - responder_consulta_general]
       Generalmente el proceso completo tarda entre 2 y 4 semanas desde 
       que entregamos la documentación, dependiendo de la carga de la ITV.

       ¿Tenés alguna fecha límite en mente?

[11 minutos de silencio]

Agente: [NUDGE POR TIMEOUT]
       ¿Sigues ahí? Respondé cualquier cosa para continuar.

[Usuario no responde en 9 minutos más - total 20 min]

Agente: [RESET POR TIMEOUT]
       Reiniciamos la conversación por inactividad. ¿En qué puedo 
       ayudarte hoy?
```

**Resultado**: Timeout manejado graceful, conversación reinicia.

---

## 📁 Prompt del Sistema para Este Modo

### System Prompt (CORE + CONSULTA_PHASE)

```markdown
## MODO: CONSULTA_GENERAL

Eres un asistente de MSI Automotive en modo CONSULTA.
Tu objetivo: Educar y responder preguntas sobre homologación.

### Herramientas Disponibles
- responder_consulta_general: Para preguntas específicas sobre homologación
- explicar_proceso_homologacion: Para explicar el proceso paso a paso
- listar_categorias: Para mostrar tipos de vehículos soportados
- listar_elementos_generales: Para mostrar qué se puede homologar
- escalar_a_humano: Siempre disponible

### Reglas CRÍTICAS
1. NO calcules presupuestos (no tienes elementos confirmados)
2. NO pidas datos personales
3. Mantené respuestas cortas (máx 3 párrafos)
4. Detectá cuándo el usuario menciona elemento específico
5. Ofrecé transición a evaluación cuando mencione elemento específico

### Transiciones Permitidas
- Usuario pregunta "¿Se puede X?" → VIABILIDAD_MODE
- Usuario pide "¿Cuánto cuesta Y?" → PRESUPUESTO_MODE  
- Usuario dice "gracias, eso es todo" → Fin conversación

### Estilo
- Amable, educativo, paciente
- Si no sabés: "No tengo esa información específica, pero puedo conectarte con un agente"
- NUNCA inventes plazos o precios exactos
```

---

## 📊 Métricas y Monitoreo

### Métricas Clave

| Métrica | Objetivo | Alerta si |
|---------|----------|-----------|
| **Tiempo promedio en modo** | <3 min | >5 min |
| **Consultas por sesión** | 2-4 | >6 (bucle?) |
| **Tasa de transición a viabilidad** | >40% | <20% |
| **Tasa de escalación** | <5% | >10% |
| **Satisfacción (implícita)** | >80% | <60% |

### Logs Importantes

```python
# Entry al modo
logger.info(f"Entered CONSULTA_MODE | user_phone={user_phone} | intent={intent}")

# Query RAG
logger.info(f"RAG query | query={consulta[:50]} | confidence={result.confianza}")

# Transición saliente
logger.info(f"Transition CONSULTA→{target_mode} | reason={reason}")

# Timeout
logger.warning(f"Timeout in CONSULTA_MODE | inactive_minutes={minutes}")
```

---

## 🧪 Tests de Aceptación

### Tests Unitarios

```python
async def test_consulta_basica():
    state = create_state(mode=CONSULTA_MODE, user_message="¿Qué es homologación?")
    result = await consulta_mode_handler(state)
    assert result.contains_explanation_about_homologation()
    assert result.mode == CONSULTA_MODE  # Permanece en modo

async def test_transicion_a_viabilidad():
    state = create_state(mode=CONSULTA_MODE, user_message="¿Se puede homologar un escape?")
    result = await consulta_mode_handler(state)
    assert result.mode == VIABILIDAD_MODE
    assert result.context.elementos_mencionados == ["escape"]

async def test_timeout_nudge():
    state = create_state(mode=CONSULTA_MODE, inactive_minutes=11)
    result = await check_timeout(state)
    assert result.action == "NUDGE"
    assert "Sigues ahí" in result.message

async def test_retry_limit():
    state = create_state(mode=CONSULTA_MODE, retry_count=3, last_error="nlu_ambiguous")
    result = await handle_mode_failure(state)
    assert result.escalation_triggered == True
```

---

## 📚 Documentación Relacionada

- [04-modo-viabilidad.md](04-modo-viabilidad.md) - Siguiente modo típico
- [09-solucion-gaps.md](09-solucion-gaps.md) - Timeouts y reintentos
- [Database: VehicleCategory](../../database/models.py) - Modelo de categorías
- [Database: RegulatoryDocument](../../database/models.py) - Documentos RAG

---

**Documento detallado para implementación de CONSULTA_MODE**  
**Estado**: Listo para desarrollo
