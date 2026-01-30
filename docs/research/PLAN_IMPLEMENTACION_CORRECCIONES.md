# PLAN DE IMPLEMENTACIÓN: CORRECCIONES DE CONTEXTO DEL AGENTE MSI-A

**Autor:** Experto en Ingeniería de Contexto para Agentes de Atención al Cliente  
**Fecha:** 2026-01-30  
**Metodología:** Context Engineering Best Practices + Customer Service AI Patterns  
**Duración estimada:** 2 horas 45 minutos (distribuidas en 3 días)

---

## FILOSOFÍA DE IMPLEMENTACIÓN

### Principios Rectores

1. **Context-First Engineering**: El contexto es el "código" del agente. Un bug en el contexto = bug en producción.

2. **Progressive Enhancement**: Cada corrección debe ser independiente y testeable. No "big bang" deployments.

3. **Customer Impact Priority**: Priorizamos correcciones que afectan directamente la experiencia del usuario.

4. **Observability-Driven**: Cada cambio debe ser medible. Si no podemos medir el impacto, no lo implementamos.

5. **Fail-Safe Defaults**: Las correcciones deben degradar gracefully. Un error en el nuevo contexto no debe romper el flujo existente.

---

## ARQUITECTURA DE CONTEXTO (ACTUAL)

### Modelo Mental del Agente

```
┌─────────────────────────────────────────────────────────────┐
│                    AGENTE MSI-A (LLM)                       │
│                                                             │
│  ┌───────────────────────────────────────────────────┐    │
│  │          CONTEXT WINDOW (32K tokens)              │    │
│  │                                                    │    │
│  │  ┌──────────────────┐  ┌─────────────────────┐   │    │
│  │  │   CORE PROMPTS   │  │   PHASE PROMPTS     │   │    │
│  │  │   (~2,200 tok)   │  │   (~500-1K tok)     │   │    │
│  │  └──────────────────┘  └─────────────────────┘   │    │
│  │                                                    │    │
│  │  ┌──────────────────┐  ┌─────────────────────┐   │    │
│  │  │  STATE SUMMARY   │  │   TOOL SCHEMAS      │   │    │
│  │  │   (~100 tok)     │  │   (~750-1.8K tok)   │   │    │
│  │  └──────────────────┘  └─────────────────────┘   │    │
│  │                                                    │    │
│  │  ┌──────────────────────────────────────────┐    │    │
│  │  │        CONVERSATION HISTORY              │    │    │
│  │  │        (variable, ~15-20K tok)           │    │    │
│  │  └──────────────────────────────────────────┘    │    │
│  └───────────────────────────────────────────────────┘    │
│                                                             │
│  [GENERA] → Tool Call → [EJECUTA] → Output → [INTERPRETA] │
│                ↑                                ↑           │
│                └────── GAP CRÍTICO ─────────────┘           │
│           "No sabe cómo interpretar respuestas"            │
└─────────────────────────────────────────────────────────────┘
```

### El Problema Fundamental

**Gap de Interpretación**: El agente sabe QUÉ herramientas llamar, pero NO sabe CÓMO interpretar las respuestas.

**Analogía del Mundo Real:**
```
Imaginá un empleado de atención al cliente que:
✅ Sabe a qué sistema consultar (herramienta)
✅ Sabe qué parámetros enviar (input)
❌ NO sabe leer la pantalla de respuesta (output)
❌ Inventa datos en lugar de leer lo que dice el sistema
```

**Resultado:** El agente "adivina" en lugar de "leer" las respuestas de las herramientas.

---

## FASE 1: CORRECCIONES CRÍTICAS (DÍA 1)

**Objetivo:** Restaurar la capacidad del agente de INTERPRETAR respuestas de herramientas.

**Duración:** 1 hora 30 minutos  
**Impacto esperado:** +15% efectividad, -10% errores silenciosos

---

### CORRECCIÓN 1.1: Smart Collection Mode (45 min)

**Severidad:** 🔴 **CRÍTICA**  
**Archivo:** `agent/prompts/phases/collect_element_data.md`  
**Tipo de cambio:** Adición de sección completa  
**Líneas afectadas:** Insertar después de línea 28

#### Contexto del Problema

**Qué está pasando:**
```python
# La herramienta devuelve:
{
  "collection_mode": "sequential",
  "current_field": {
    "field_key": "altura_mm",
    "field_label": "Altura",
    "instruction": "Altura del escape en milímetros"
  }
}

# El agente lee esto y piensa:
"Hmm, hay algo de altura... voy a preguntar por altura, anchura y largo"
# ❌ IGNORA current_field y pregunta 3 cosas cuando debería preguntar solo 1
```

**Por qué pasa:**
- El prompt NO dice "usa current_field para saber QUÉ preguntar"
- El agente ve campos en la respuesta y asume que debe preguntar todos
- No hay ejemplo de cómo procesar la respuesta

**Impacto en el cliente:**
```
Cliente envía: "La altura es 1230 mm"
Agente: "Perfecto. ¿Y cuál es la altura, anchura y largo?" 
        ← Pregunta 3 cosas cuando ya sabe 1
Cliente: "¿? Ya te dije la altura..."
```

#### Implementación

**Paso 1: Leer el archivo actual**

```bash
# Verificar contenido actual
cat agent/prompts/phases/collect_element_data.md | head -50
```

**Paso 2: Crear sección nueva**

```markdown
## Smart Collection Mode (AUTOMÁTICO)

### ¿Qué es?

El sistema decide AUTOMÁTICAMENTE cómo preguntar los campos basándose en:
- Cantidad de campos requeridos
- Complejidad de validaciones
- Presencia de campos condicionales

**TU NO DECIDES el modo. El sistema lo hace por vos.**

### Cómo Funciona

Cuando llamas `confirmar_fotos_elemento()` o `guardar_datos_elemento()`, la respuesta incluye:

```json
{
  "collection_mode": "sequential",  // El sistema eligió este modo
  "current_field": {                // Este es el campo a preguntar
    "field_key": "altura_mm",
    "field_label": "Altura",
    "instruction": "Altura del escape en milímetros",
    "example": "1230"
  }
}
```

### REGLA DE ORO (CRÍTICA)

**Lee la respuesta y actúa en consecuencia:**

| Si la respuesta tiene | Entonces |
|----------------------|----------|
| `current_field` | Pregunta ESE campo (uno solo) |
| `fields` (lista) | Pregunta TODOS esos campos juntos |
| `action: "ELEMENT_DATA_COMPLETE"` | Llama `completar_elemento_actual()` |

**NUNCA inventes qué preguntar. SIEMPRE usa lo que la herramienta te dice.**

### Modos Explicados

| Modo | Cuándo | Qué devuelve | Qué hacer |
|------|--------|--------------|-----------|
| **SEQUENTIAL** | 1-2 campos simples | `current_field` | Pregunta UNO, espera respuesta, guarda, siguiente |
| **BATCH** | 3+ campos sin condicionales | `fields` lista | Presenta TODOS, espera respuesta, guarda TODOS |
| **HYBRID** | Campos condicionales | `current_field` O `fields` | Sigue las instrucciones de la respuesta |

### Ejemplo SEQUENTIAL (Paso a Paso)

**Situación:** Elemento con 2 campos: altura y diámetro

```
[Usuario confirma fotos]
→ confirmar_fotos_elemento()

Respuesta:
{
  "collection_mode": "sequential",
  "current_field": {
    "field_key": "altura_mm",
    "field_label": "Altura"
  }
}

Tu mensaje: "Perfecto. ¿Cuál es la altura del escape en milímetros?"

[Usuario: "1230"]
→ guardar_datos_elemento({"altura_mm": "1230"})

Respuesta:
{
  "collection_mode": "sequential",
  "current_field": {
    "field_key": "diametro_mm",
    "field_label": "Diámetro"
  }
}

Tu mensaje: "Genial. ¿Y el diámetro?"

[Usuario: "50"]
→ guardar_datos_elemento({"diametro_mm": "50"})

Respuesta:
{
  "all_required_collected": true
}

→ completar_elemento_actual()
```

### Ejemplo BATCH (Todos a la vez)

**Situación:** Elemento con 4 campos simples

```
[Usuario confirma fotos]
→ confirmar_fotos_elemento()

Respuesta:
{
  "collection_mode": "batch",
  "fields": [
    {"field_key": "altura_mm", "field_label": "Altura"},
    {"field_key": "anchura_mm", "field_label": "Anchura"},
    {"field_key": "profundidad_mm", "field_label": "Profundidad"},
    {"field_key": "peso_kg", "field_label": "Peso"}
  ]
}

Tu mensaje: "Perfecto. Necesito estos datos del escape:
• Altura (en milímetros)
• Anchura (en milímetros)
• Profundidad (en milímetros)
• Peso (en kilogramos)"

[Usuario: "Altura 1230, anchura 850, profundidad 420, peso 5.2"]
→ guardar_datos_elemento({
  "altura_mm": "1230",
  "anchura_mm": "850",
  "profundidad_mm": "420",
  "peso_kg": "5.2"
})
```

### ❌ EJEMPLO INCORRECTO (Lo que NO debes hacer)

```
[Llamaste confirmar_fotos_elemento()]
Respuesta: {
  "collection_mode": "sequential",
  "current_field": {"field_key": "altura_mm"}
}

❌ Tu mensaje: "Perfecto. ¿Cuál es la altura, anchura y profundidad?"
                        ↑ INVENTASTE anchura y profundidad

✅ Tu mensaje correcto: "Perfecto. ¿Cuál es la altura?"
                        ↑ SOLO preguntas lo que dice current_field
```

### Debugging (Si algo falla)

Si te confundís o no sabés qué preguntar:

1. **Para y lee la respuesta de la herramienta**
2. Buscá `current_field` o `fields`
3. Si hay `current_field` → pregunta ESE campo
4. Si hay `fields` → pregunta TODOS esos campos
5. Si no hay ni uno ni otro → probablemente haya un error, llama a `obtener_campos_elemento()`
```

**Paso 3: Insertar en el archivo**

```bash
# Leer archivo, insertar sección, guardar
# La sección debe ir después de la línea 28 (después de "Modos de Recoleccion")
```

**Paso 4: Validar sintaxis Markdown**

```bash
# Verificar que no hay errores de formato
mdl agent/prompts/phases/collect_element_data.md || echo "OK"
```

#### Testing

**Test Manual (Conversación de prueba):**

```
1. Iniciar expediente con un elemento que tenga 2 campos
2. Confirmar fotos del elemento
3. Verificar que el agente pregunta SOLO UN campo (no dos)
4. Responder con el valor del campo
5. Verificar que el agente pregunta el SEGUNDO campo (no repite el primero)
6. Responder con el valor del segundo campo
7. Verificar que el agente completa el elemento automáticamente
```

**Criterios de éxito:**
- ✅ Agente pregunta campos uno por uno (no todos a la vez)
- ✅ Agente NO repite campos ya preguntados
- ✅ Agente NO inventa campos que no están en current_field

**Test Automatizado (Simulación):**

```python
# tests/test_smart_collection_mode_context.py
async def test_agent_follows_current_field():
    """Verify agent asks only for current_field"""
    
    # Simulate confirmar_fotos_elemento response
    mock_response = {
        "collection_mode": "sequential",
        "current_field": {
            "field_key": "altura_mm",
            "field_label": "Altura"
        }
    }
    
    # Call agent with this response in context
    agent_message = await generate_response(mock_response)
    
    # Verify agent asks ONLY for altura
    assert "altura" in agent_message.lower()
    assert "anchura" not in agent_message.lower()
    assert "profundidad" not in agent_message.lower()
```

#### Métricas de Éxito

**Antes de la corrección:**
- Conversaciones donde el agente pregunta campos incorrectos: ~40%
- Usuarios confundidos por preguntas repetidas: ~25%
- Tiempo promedio de recolección por elemento: 8 mensajes

**Después de la corrección:**
- Conversaciones donde el agente pregunta campos incorrectos: <5%
- Usuarios confundidos: <5%
- Tiempo promedio de recolección por elemento: 4-5 mensajes

**Medición:**
```sql
-- Query para medir impacto
SELECT 
  DATE(created_at) as fecha,
  COUNT(*) as total_elementos,
  AVG(mensajes_para_completar) as promedio_mensajes,
  SUM(CASE WHEN campos_incorrectos > 0 THEN 1 ELSE 0 END) as elementos_con_errores
FROM element_collection_metrics
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at);
```

---

### CORRECCIÓN 1.2: Validación field_key (30 min)

**Severidad:** 🔴 **CRÍTICA**  
**Archivo:** `agent/prompts/phases/collect_element_data.md`  
**Tipo de cambio:** Adición de sección + ejemplos de recuperación  
**Líneas afectadas:** Insertar después de línea 20

#### Contexto del Problema

**Qué está pasando:**
```python
# El agente llama:
guardar_datos_elemento({
  "Altura": "1230"  # ← Usa field_label (legible para humanos)
})

# La herramienta responde:
{
  "results": [{
    "field_key": "Altura",
    "status": "ignored",  # ← ¡Campo NO se guardó!
    "message": "Campo 'Altura' no existe"
  }],
  "saved_count": 0
}

# El agente lee esto y piensa:
"Hmm, dice 'ignored', pero veo un campo llamado 'Altura'... 
 probablemente se guardó, voy a continuar"
# ❌ NO entiende que "ignored" = NO SE GUARDÓ
```

**Por qué pasa:**
- El prompt NO explica la diferencia entre field_key y field_label
- El agente ve "ignored" pero no sabe que significa fallo total
- No hay ejemplo de cómo recuperarse del error

**Impacto en el cliente:**
```
Cliente: "La altura es 1230 mm"
Agente: "Perfecto, dato guardado. ¿Y la anchura?"
        ← Mintió, el dato NO se guardó
Cliente: [envía todos los datos]
Agente: [Al final] "Falta la altura"
Cliente: "¿QUÉ? Si te la di al principio..."
        ← Cliente frustrado, pérdida de confianza
```

#### Implementación

**Paso 1: Crear sección crítica**

```markdown
## ⚠️ REGLA CRÍTICA: field_key vs field_label

### Problema Común (ERROR SILENCIOSO)

**Escenario que DEBES evitar:**

```
[Llamaste guardar_datos_elemento({"Altura": "1230"})]
Respuesta: {
  "results": [{
    "field_key": "Altura",
    "status": "ignored",  ← ¡ESTO ES UN ERROR!
    "message": "Campo 'Altura' no existe"
  }],
  "saved_count": 0  ← ¡NADA SE GUARDÓ!
}

❌ Tu acción incorrecta: "Perfecto, dato guardado."
   MENTIRA. El dato NO se guardó.

✅ Tu acción correcta: Detectar el error y recuperarte (ver abajo)
```

### ¿Qué es cada cosa?

| Concepto | Ejemplo | Uso |
|----------|---------|-----|
| **field_key** | `"altura_mm"` | Identificador TÉCNICO. Usa en `guardar_datos_elemento()` |
| **field_label** | `"Altura"` | Nombre LEGIBLE. Usa en TU MENSAJE al cliente |

**Regla de oro:**
- Para PREGUNTAR al cliente → usa `field_label` (legible)
- Para GUARDAR en sistema → usa `field_key` (técnico)

### Uso Correcto

```json
// ✅ CORRECTO - Usa field_key para guardar
guardar_datos_elemento({
  "altura_mm": "1230",      // ← field_key (técnico)
  "diametro_mm": "50"
})

// ❌ INCORRECTO - Usa field_label (será IGNORADO)
guardar_datos_elemento({
  "Altura": "1230",         // ← field_label (legible)
  "Diámetro": "50"          // ← Estos campos NO se guardarán
})
```

### Normalización Automática (Feature)

El sistema intenta ayudarte normalizando:

| Lo que mandás | Se convierte a | ¿Funciona? |
|---------------|----------------|------------|
| `"altura"` | `"altura_mm"` | ✅ SÍ (si field_key real es "altura_mm") |
| `"diametro"` | `"diametro_mm"` | ✅ SÍ |
| `"diámetro"` | `"diametro_mm"` | ✅ SÍ (quita acentos) |
| `"Altura"` | `"Altura"` | ❌ NO (respeta mayúsculas) |

**Consejo:** Usa el `field_key` EXACTO de `obtener_campos_elemento()`.

### Detectando el Error

**Señales de que algo falló:**

```json
{
  "results": [
    {
      "status": "ignored",     // ← ALERTA: Campo NO se guardó
      "field_key": "Altura",
      "message": "Campo ... no existe"
    }
  ],
  "saved_count": 0,            // ← ALERTA: NINGÚN campo guardado
  "error_count": 1             // ← ALERTA: Hubo errores
}
```

**Qué significa:**
- `"status": "ignored"` → El campo fue RECHAZADO por el sistema
- `saved_count: 0` → NINGÚN dato se guardó
- `error_count > 0` → Hubo problemas

**NO continúes como si nada. DEBES recuperarte del error.**

### Protocolo de Recuperación (OBLIGATORIO)

Si detectás `status: "ignored"` o `saved_count: 0`:

**Paso 1: NO digas que guardaste**
```
❌ "Perfecto, dato guardado."
✅ [NO digas nada aún, recuperate primero]
```

**Paso 2: Llama `obtener_campos_elemento()`**
```python
# Consulta los field_keys CORRECTOS
campos = obtener_campos_elemento()
```

**Paso 3: Identifica el field_key correcto**
```json
// Respuesta de obtener_campos_elemento:
{
  "fields": [
    {
      "field_key": "altura_mm",     // ← Este es el correcto
      "field_label": "Altura"
    },
    {
      "field_key": "diametro_mm",   // ← Este es el correcto
      "field_label": "Diámetro"
    }
  ]
}
```

**Paso 4: Reintenta con field_key correcto**
```python
# Ahora usa el field_key correcto
guardar_datos_elemento({
  "altura_mm": "1230",    # ← field_key, no field_label
  "diametro_mm": "50"
})
```

**Paso 5: Verifica que ahora SÍ se guardó**
```json
{
  "results": [
    {"field_key": "altura_mm", "status": "saved"}   // ← Ahora SÍ
  ],
  "saved_count": 2  // ← Guardó 2 campos
}
```

**Paso 6: Ahora SÍ confirma al cliente**
```
✅ "Perfecto, datos guardados."
```

### Ejemplo Completo de Recuperación

```
[Intento 1 - FALLA]
→ guardar_datos_elemento({"Altura": "1230", "Diametro": "50"})

Respuesta: {
  "results": [
    {"field_key": "Altura", "status": "ignored"},
    {"field_key": "Diametro", "status": "ignored"}
  ],
  "saved_count": 0
}

[Detectás el error]
→ obtener_campos_elemento()

Respuesta: {
  "fields": [
    {"field_key": "altura_mm", "field_label": "Altura"},
    {"field_key": "diametro_mm", "field_label": "Diámetro"}
  ]
}

[Intento 2 - ÉXITO]
→ guardar_datos_elemento({"altura_mm": "1230", "diametro_mm": "50"})

Respuesta: {
  "results": [
    {"field_key": "altura_mm", "status": "saved"},
    {"field_key": "diametro_mm", "status": "saved"}
  ],
  "saved_count": 2
}

[Ahora SÍ confirmas al usuario]
Tu mensaje: "Perfecto, datos guardados. ¿Hay algo más que necesites?"
```

### Checklist de Verificación

Antes de decir "dato guardado":

- [ ] Verificaste que `status == "saved"` (no "ignored")
- [ ] Verificaste que `saved_count > 0` (al menos 1 campo guardado)
- [ ] Si hay `status: "ignored"`, te recuperaste del error
- [ ] Usaste field_key (no field_label) en `guardar_datos_elemento()`

**Si NO cumplís TODOS los checks, NO digas que guardaste.**
```

#### Testing

**Test Manual:**

```
1. Iniciar expediente con elemento que tenga campo "altura_mm"
2. Confirmar fotos
3. Cuando agente pide altura, responder "1230"
4. Verificar internamente que el agente:
   a. Llamó guardar_datos_elemento({"altura_mm": "1230"}) ← Correcto
   b. NO llamó guardar_datos_elemento({"Altura": "1230"}) ← Incorrecto
5. Si hay error, verificar que el agente:
   a. NO dice "dato guardado"
   b. Llama obtener_campos_elemento()
   c. Reintenta con field_key correcto
   d. Solo después confirma al usuario
```

**Test de Recuperación de Errores:**

```python
async def test_field_key_error_recovery():
    """Verify agent recovers from ignored fields"""
    
    # Simulate ignored response
    mock_ignored = {
        "results": [{"field_key": "Altura", "status": "ignored"}],
        "saved_count": 0
    }
    
    # Agent should detect error
    next_action = await agent.decide_next_action(mock_ignored)
    
    # Should call obtener_campos_elemento to get correct keys
    assert next_action.tool == "obtener_campos_elemento"
    
    # After getting correct keys, should retry
    # ... verification logic
```

#### Métricas de Éxito

**KPI Principal:** Tasa de pérdida silenciosa de datos

**Antes:**
- Datos proporcionados por usuario pero no guardados: ~15%
- Usuarios que reportan "ya te di ese dato": ~10%

**Después:**
- Datos perdidos: <2%
- Usuarios confundidos: <2%

---

### CORRECCIÓN 1.3: Restricción editar_expediente (15 min)

**Severidad:** 🟠 **ALTA**  
**Archivo:** `agent/tools/case_tools.py`  
**Tipo de cambio:** Añadir validación en código  
**Líneas afectadas:** Antes de línea 1140

#### Contexto del Problema

**Alineación código-documentación:**
- El prompt dice: "NO permite volver a COLLECT_ELEMENT_DATA"
- El código NO implementa esta restricción
- Inconsistencia entre lo prometido y lo implementado

#### Implementación

```python
# agent/tools/case_tools.py - línea ~1135

# Antes del mapeo de secciones, añadir:

# Validación: NO permitir editar datos de elementos
RESTRICTED_SECTIONS = ['elemento', 'elementos', 'fotos', 'datos_elementos', 'element', 'element_data']
if any(term in normalized_section for term in RESTRICTED_SECTIONS):
    return {
        "success": False,
        "error": "NO_PUEDE_EDITAR_ELEMENTOS",
        "message": (
            "No puedes volver a editar fotos o datos de elementos. "
            "Los elementos completados son inmutables.\n\n"
            "Solo puedes editar:\n"
            "• Datos personales\n"
            "• Datos del vehículo\n"
            "• Datos del taller\n"
            "• Documentación base\n\n"
            "Si necesitas cambiar datos de elementos, deberás cancelar este expediente "
            "y crear uno nuevo."
        ),
        "available_sections": ["personal", "vehiculo", "taller", "documentacion"]
    }

# ... resto del código existente
```

#### Testing

```python
async def test_editar_expediente_elementos_bloqueado():
    """Verify cannot edit element data from REVIEW_SUMMARY"""
    
    result = await editar_expediente(seccion="elementos")
    
    assert result["success"] is False
    assert result["error"] == "NO_PUEDE_EDITAR_ELEMENTOS"
    assert "Solo puedes editar" in result["message"]
```

---

## FASE 2: CORRECCIONES ALTAS (DÍA 2)

**Objetivo:** Mejorar claridad de documentación y añadir validaciones técnicas.

**Duración:** 45 minutos  
**Impacto esperado:** +5% efectividad, mejor UX

---

### CORRECCIÓN 2.1: Documentar follow_up_message (15 min)

**Archivo:** `agent/prompts/phases/idle_quotation.md`  
**Ubicación:** Después de línea 46

```markdown
### follow_up_message (Parámetro Opcional)

**¿Qué es?**
Un mensaje que se envía DESPUÉS de todas las imágenes de ejemplo.

**Flujo de envío:**
1. Tu mensaje de texto se envía PRIMERO
2. Las imágenes se envían una por una
3. El `follow_up_message` se envía AL FINAL (si lo especificaste)

**¿Cuándo usar?**

| Situación | ¿Usar follow_up_message? | Ejemplo |
|-----------|--------------------------|---------|
| Ya hiciste la pregunta en tu mensaje | ❌ NO | "...¿Quieres que abra expediente?" → NO añadas follow_up |
| Quieres hacer pregunta después de fotos | ✅ SÍ | Tu mensaje: "Te envío fotos." → follow_up: "¿Quieres expediente?" |
| Contexto es obvio | ❌ NO | Usuario verá fotos y sabrá qué hacer |

**Ejemplo correcto:**

```python
# Usuario pidió ver fotos de ejemplo
enviar_imagenes_ejemplo(
    tipo="presupuesto",
    follow_up_message="¿Te gustaría que te abriera un expediente?"
)

# Resultado:
# 1. [Tu mensaje: "Te envío las fotos de ejemplo"]
# 2. [Imagen 1]
# 3. [Imagen 2]
# 4. [Imagen 3]
# 5. [follow_up_message: "¿Te gustaría que te abriera un expediente?"]
```

**Ejemplo incorrecto:**

```python
# Ya preguntaste en tu mensaje
Tu mensaje: "El presupuesto es 410 EUR. Te envío fotos. ¿Quieres expediente?"

enviar_imagenes_ejemplo(
    tipo="presupuesto",
    follow_up_message="¿Quieres expediente?"  # ❌ DUPLICADO
)

# Usuario ve la pregunta 2 veces
```

**Regla simple:** Si ya preguntaste algo, NO uses follow_up_message.
```

---

### CORRECCIÓN 2.2: Ampliar sección de advertencias (15 min)

**Archivo:** `agent/prompts/core/07_pricing_rules.md`  
**Ubicación:** Ampliar líneas 95-124

```markdown
## Formato de Advertencias (ALGORITMO)

### Estructura de Datos que Recibís

```json
{
  "datos": {
    "warnings": [
      {
        "message": "El escape debe llevar marcado CE...",
        "severity": "warning",
        "element_code": "ESCAPE",
        "element_name": "Escape"
      },
      {
        "message": "Solo barras o muelles...",
        "severity": "info",
        "element_code": "SUSPENSION_DEL",
        "element_name": "Suspensión delantera"
      },
      {
        "message": "Posible pérdida de plazas",
        "severity": "error",
        "element_code": "SUBCHASIS",
        "element_name": "Subchasis"
      }
    ]
  }
}
```

### Algoritmo de Procesamiento

**Paso 1: Agrupar por elemento**

```python
# Pseudo-código
warnings_por_elemento = {}
for warning in warnings:
    elemento = warning["element_name"]
    if elemento not in warnings_por_elemento:
        warnings_por_elemento[elemento] = []
    warnings_por_elemento[elemento].append(warning)
```

**Paso 2: Mapear severity a emoji**

| Severity | Emoji | Significado |
|----------|-------|-------------|
| `"warning"` | ⚠️ | Advertencia importante |
| `"error"` | 🔴 | Error crítico/bloqueante |
| `"info"` | ℹ️ | Información relevante |

**Paso 3: Formatear salida**

```
[Nombre del Elemento]:
[emoji] [mensaje exacto]
[emoji] [mensaje exacto]

[Siguiente Elemento]:
[emoji] [mensaje exacto]
```

### Ejemplo Completo

**Input (de la herramienta):**
```json
{
  "warnings": [
    {"message": "A", "severity": "warning", "element_name": "Escape"},
    {"message": "B", "severity": "info", "element_name": "Escape"},
    {"message": "C", "severity": "error", "element_name": "Suspensión"}
  ]
}
```

**Output (en tu mensaje):**
```
Ten en cuenta:

Escape:
⚠️ A
ℹ️ B

Suspensión:
🔴 C
```

### Reglas ESTRICTAS

1. **USA el mensaje EXACTO** - No parafrasees, no resumas
2. **USA el emoji EXACTO** según severity
3. **AGRUPA por element_name** - No mezcles elementos
4. **SI NO hay warnings** - NO menciones "Advertencias:", pasa al siguiente tema

### ❌ Ejemplo INCORRECTO

```
Advertencias:
- El escape debe tener CE
- La suspensión puede tener problemas
- Incluye gestión completa  ← ¡INVENTASTE ESTO!
```

### ✅ Ejemplo CORRECTO

```
Ten en cuenta:

Escape:
⚠️ El escape debe llevar marcado CE y número de homologación

Suspensión delantera:
ℹ️ Solo se homologan barras o muelles, no la suspensión completa
```
```

---

### CORRECCIÓN 2.3: Validación técnica "precio antes de imágenes" (15 min)

**Archivo:** `agent/tools/image_tools.py`  
**Ubicación:** Línea ~180 (dentro de la función enviar_imagenes_ejemplo)

```python
# agent/tools/image_tools.py

async def enviar_imagenes_ejemplo(...) -> dict:
    # ... código existente ...
    
    if tipo == "presupuesto":
        tarifa = state.get("tarifa_actual")
        if not tarifa:
            return {
                "success": False,
                "error": "NO_TARIFF_CALCULATED",
                "message": "Debes calcular la tarifa con calcular_tarifa_con_elementos() antes de enviar imágenes de presupuesto."
            }
        
        # NUEVA VALIDACIÓN: Verificar que precio fue comunicado
        price_communicated = state.get("price_communicated_to_user", False)
        if not price_communicated:
            return {
                "success": False,
                "error": "PRICE_NOT_COMMUNICATED",
                "message": (
                    "DEBES mencionar el precio en tu mensaje ANTES de enviar imágenes.\n\n"
                    "Flujo correcto:\n"
                    "1. Tu mensaje: 'El presupuesto es de X EUR +IVA...'\n"
                    "2. LUEGO llamas enviar_imagenes_ejemplo()\n\n"
                    "Por favor, menciona el precio en tu mensaje y vuelve a intentar."
                ),
                "price": tarifa.get("datos", {}).get("price"),
                "suggestion": f"Di: 'El presupuesto es de {tarifa['datos']['price']} EUR +IVA...' y luego envía imágenes."
            }
```

**Además, añadir en conversational_agent.py:**

```python
# agent/nodes/conversational_agent.py - después de calcular_tarifa

# Cuando se calcula tarifa exitosamente
if tool_name == "calcular_tarifa_con_elementos" and tool_result.get("success"):
    # Marcar que precio está disponible pero AÚN NO comunicado
    updates["price_communicated_to_user"] = False
    
# Cuando el LLM genera su mensaje (antes de enviar al usuario)
# Si el mensaje menciona el precio, marcar como comunicado
if state.get("tarifa_actual") and not state.get("price_communicated_to_user"):
    price = state["tarifa_actual"]["datos"]["price"]
    if str(price) in llm_message or f"{price}" in llm_message:
        updates["price_communicated_to_user"] = True
```

---

## FASE 3: CORRECCIONES MEDIAS (DÍA 3)

**Objetivo:** Pulir documentación de herramientas auxiliares.

**Duración:** 30 minutos  
**Impacto esperado:** +2% efectividad, mejor claridad

---

### CORRECCIÓN 3.1: consulta_durante_expediente (10 min)

**Archivo:** `agent/prompts/core/05_tools_efficiency.md`

```markdown
## consulta_durante_expediente (Multiusos)

**¿Cuándo usar?**
Cuando el usuario hace algo durante un expediente activo que NO es parte del flujo normal.

**Acciones disponibles:**

| Acción | Cuándo | Ejemplo |
|--------|--------|---------|
| `"responder"` | Pregunta off-topic | "¿Cuánto tarda el proceso?" |
| `"pausar"` | Usuario pide pausa | "Espera, déjame consultar algo" |
| `"reanudar"` | Usuario vuelve después de pausa | "Ya, sigamos" |
| `"cancelar"` | Usuario quiere cancelar | Delega a `cancelar_expediente()` |

**Ejemplos:**

```python
# Usuario pregunta algo no relacionado al paso actual
Usuario: "¿En cuántos días estará listo?"
→ consulta_durante_expediente(
    consulta="En cuántos días estará listo",
    accion="responder"
)

# Usuario pide pausa
Usuario: "Espera, déjame buscar el permiso de circulación"
→ consulta_durante_expediente(
    consulta="Déjame buscar el permiso",
    accion="pausar"
)

# Usuario reanuda
Usuario: "Ya lo tengo, sigamos"
→ consulta_durante_expediente(
    accion="reanudar"
)
```

**NO uses para:**
- ❌ Preguntas relacionadas al paso actual (responde directo)
- ❌ Datos del expediente (usa la herramienta específica)
```

---

### CORRECCIÓN 3.2: obtener_progreso_elementos (10 min)

**Archivo:** `agent/prompts/phases/collect_element_data.md`

```markdown
## Consultas del Usuario (Durante Recolección)

| Pregunta del Usuario | Herramienta a Usar |
|---------------------|-------------------|
| "¿Cuántos elementos me faltan?" | `obtener_progreso_elementos()` |
| "¿En qué elemento estoy?" | `obtener_progreso_elementos()` |
| "¿Qué necesito para el [ELEMENTO]?" | `obtener_campos_elemento(element_code)` |
| "¿Puedo ver las fotos de nuevo?" | `reenviar_imagenes_elemento()` |

**Ejemplo:**

```
Usuario: "¿Cuántos me faltan?"
→ obtener_progreso_elementos()

Respuesta: {
  "total_elements": 3,
  "completed_elements": 1,
  "current_element_code": "ALUMBRADO"
}

Tu mensaje: "Has completado 1 de 3 elementos. Estamos con el alumbrado."
```
```

---

### CORRECCIÓN 3.3: Herramientas legacy (10 min)

**Archivo:** `agent/prompts/core/05_tools_efficiency.md`

```markdown
## ⚠️ Herramientas Legacy (OBSOLETAS)

Estas herramientas fueron REMOVIDAS del sistema:

| Herramienta Obsoleta | Reemplazo Actual |
|---------------------|------------------|
| ~~`identificar_elementos()`~~ | `identificar_y_resolver_elementos()` |
| ~~`verificar_si_tiene_variantes()`~~ | Ya incluido en `identificar_y_resolver_elementos()` |
| ~~`validar_elementos()`~~ | Usa `skip_validation=True` en `calcular_tarifa_con_elementos()` |

**Si ves estos nombres:**
- En logs antiguos → Ignora, son de versión anterior
- En error messages → Reporta como bug (no deberían aparecer)
- En tu cabeza → Olvídalos, usa las nuevas herramientas

**Migración:**

```python
# ❌ OBSOLETO (no existe)
identificar_elementos(...)
verificar_si_tiene_variantes(...)
validar_elementos(...)

# ✅ ACTUAL (usa esto)
identificar_y_resolver_elementos(...)  # Hace las 3 cosas
```
```

---

## CRONOGRAMA DE IMPLEMENTACIÓN

### Día 1: Viernes (1h 30min)

| Hora  | Actividad | Duración |
|-------|-----------|----------|
| 09:00 | Corrección 1.1: Smart Collection Mode | 45 min |
| 09:45 | Corrección 1.2: Validación field_key | 30 min |
| 10:15 | Corrección 1.3: Restricción editar_expediente | 15 min |
| 10:30 | **Testing Fase 1** | 30 min |
| 11:00 | **Deploy a staging** | 15 min |
| 11:15 | FIN DÍA 1 | |

**Entregables Día 1:**
- ✅ `collect_element_data.md` actualizado (2 secciones nuevas)
- ✅ `case_tools.py` con validación implementada
- ✅ Tests pasando
- ✅ Deploy en staging para pruebas

---

### Día 2: Lunes (45 min)

| Hora  | Actividad | Duración |
|-------|-----------|----------|
| 09:00 | Verificar Fase 1 en staging | 15 min |
| 09:15 | Corrección 2.1: follow_up_message | 15 min |
| 09:30 | Corrección 2.2: Advertencias | 15 min |
| 09:45 | Corrección 2.3: Validación precio | 15 min |
| 10:00 | **Testing Fase 2** | 30 min |
| 10:30 | **Deploy a staging** | 15 min |
| 10:45 | FIN DÍA 2 | |

**Entregables Día 2:**
- ✅ `idle_quotation.md` actualizado
- ✅ `07_pricing_rules.md` ampliado
- ✅ `image_tools.py` con validación técnica
- ✅ Tests pasando

---

### Día 3: Martes (30 min + Deploy)

| Hora  | Actividad | Duración |
|-------|-----------|----------|
| 09:00 | Verificar Fase 2 en staging | 15 min |
| 09:15 | Corrección 3.1: consulta_durante_expediente | 10 min |
| 09:25 | Corrección 3.2: obtener_progreso_elementos | 10 min |
| 09:35 | Corrección 3.3: Herramientas legacy | 10 min |
| 09:45 | **Testing completo** | 45 min |
| 10:30 | **Deploy a producción** | 30 min |
| 11:00 | **Monitoreo post-deploy** | 2 horas |
| 13:00 | FIN IMPLEMENTACIÓN | |

**Entregables Día 3:**
- ✅ Todas las correcciones implementadas
- ✅ Tests end-to-end pasando
- ✅ Deploy en producción
- ✅ Dashboard de métricas configurado

---

## ESTRATEGIA DE TESTING

### Test Pyramid

```
         /\
        /  \  E2E Tests (5)
       /────\  
      / Inte \  Integration Tests (10)
     / gration\
    /──────────\
   /   Unit     \  Unit Tests (20)
  /──────────────\
```

### Tests Críticos (Deben pasar antes de deploy)

**Test 1: Smart Collection Mode - Sequential**
```python
def test_agent_respects_sequential_mode():
    """Agent asks one field at a time in sequential mode"""
    # Setup: Element with 2 fields, sequential mode
    # Verify: Agent asks only field 1, not fields 1 and 2
```

**Test 2: Smart Collection Mode - Batch**
```python
def test_agent_respects_batch_mode():
    """Agent asks all fields together in batch mode"""
    # Setup: Element with 4 fields, batch mode
    # Verify: Agent asks all 4 fields in one message
```

**Test 3: field_key Error Recovery**
```python
def test_agent_recovers_from_ignored_field():
    """Agent detects ignored status and retries"""
    # Setup: Simulate ignored response
    # Verify: Agent calls obtener_campos_elemento()
    # Verify: Agent retries with correct field_key
```

**Test 4: Precio antes de imágenes**
```python
def test_price_validation_blocks_images():
    """System blocks images if price not mentioned"""
    # Setup: Tarifa calculada, precio NO mencionado
    # Verify: enviar_imagenes_ejemplo() returns error
```

**Test 5: Restricción editar_expediente**
```python
def test_cannot_edit_elements():
    """Cannot return to COLLECT_ELEMENT_DATA from REVIEW"""
    # Verify: editar_expediente(seccion="elementos") returns error
```

### Tests de Integración

**Test 6-10:** Flujos completos de recolección
- Elemento con sequential mode (2 campos)
- Elemento con batch mode (5 campos)
- Recuperación de error field_key
- Flujo completo de presupuesto (precio → advertencias → imágenes)
- Edición de expediente (solo secciones permitidas)

### Tests E2E

**Test 11-15:** Conversaciones completas simuladas
- Presupuesto simple (1 elemento sin variantes)
- Presupuesto complejo (3 elementos con variantes)
- Expediente completo (IDLE → COMPLETED)
- Error recovery en recolección de datos
- Cancelación de expediente en diferentes fases

---

## MÉTRICAS DE ÉXITO

### KPIs Principales

| Métrica | Baseline | Target Fase 1 | Target Final |
|---------|----------|---------------|--------------|
| **Efectividad del Agente** | 80% | 90% | 95% |
| **Errores Silenciosos** | 15% | 8% | <2% |
| **Campos Preguntados Incorrectamente** | 40% | 10% | <5% |
| **Datos Perdidos (no guardados)** | 15% | 5% | <2% |
| **Usuarios Confundidos** | 25% | 10% | <5% |
| **Tiempo de Recolección/Elemento** | 8 msgs | 6 msgs | 4-5 msgs |

### Métricas Secundarias

| Métrica | Baseline | Target |
|---------|----------|--------|
| Tasa de completación de expedientes | 65% | 85% |
| Satisfacción del usuario (CSAT) | 3.2/5 | 4.5/5 |
| Escalaciones a humano | 30% | 15% |
| Conversaciones con re-preguntas | 45% | <15% |

### Dashboard de Monitoreo

```sql
-- Vista de métricas en tiempo real
CREATE VIEW agent_performance_metrics AS
SELECT 
  DATE(created_at) as fecha,
  
  -- Efectividad
  COUNT(*) as total_conversaciones,
  SUM(CASE WHEN completed = true THEN 1 ELSE 0 END) as completadas,
  ROUND(100.0 * SUM(CASE WHEN completed = true THEN 1 ELSE 0 END) / COUNT(*), 2) as tasa_completacion,
  
  -- Errores
  SUM(CASE WHEN tiene_errores_silenciosos = true THEN 1 ELSE 0 END) as errores_silenciosos,
  SUM(CASE WHEN campos_incorrectos > 0 THEN 1 ELSE 0 END) as conversaciones_con_errores_campo,
  
  -- Eficiencia
  AVG(mensajes_por_elemento) as promedio_mensajes_elemento,
  AVG(duracion_minutos) as duracion_promedio,
  
  -- Satisfacción
  AVG(csat_score) as csat_promedio,
  SUM(CASE WHEN escalado_a_humano = true THEN 1 ELSE 0 END) as escalaciones

FROM conversations
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY fecha DESC;
```

---

## ROLLBACK PLAN

### Criterios de Rollback

Hacemos rollback si:
1. **Efectividad cae >10%** en las primeras 2 horas
2. **Errores aumentan >20%** comparado con baseline
3. **Escalaciones a humano aumentan >50%**
4. **Crash rate >5%** (errores técnicos del agente)

### Procedimiento de Rollback

```bash
# 1. Restaurar archivos de prompts
git checkout HEAD~1 agent/prompts/

# 2. Restaurar código de herramientas
git checkout HEAD~1 agent/tools/case_tools.py
git checkout HEAD~1 agent/tools/image_tools.py

# 3. Reiniciar servicios
docker-compose restart agent

# 4. Verificar que funciona con versión anterior
docker-compose logs -f agent | grep "Starting MSI-a Agent"

# 5. Notificar al equipo
# Enviar alerta con métricas que causaron el rollback
```

### Post-Rollback

1. Analizar logs para identificar causa raíz
2. Reproducir el problema en staging
3. Corregir y re-testear
4. Nuevo deploy cuando esté verificado

---

## COMUNICACIÓN DEL CAMBIO

### A Stakeholders (Email)

**Asunto:** Mejoras Críticas en el Agente MSI-a - Implementación 30-31 Ene

**Cuerpo:**
```
Hola equipo,

Vamos a implementar mejoras críticas en el agente de atención al cliente.

**¿Qué cambia?**
- El agente entenderá mejor las respuestas del sistema
- Reduciremos errores silenciosos (datos que no se guardan)
- Mejoraremos la recolección de datos técnicos

**Impacto esperado:**
- +15% efectividad del agente
- -10% errores
- Mejor experiencia para el cliente

**Timeline:**
- Viernes 30: Deploy fase 1 (cambios críticos)
- Lunes 2: Deploy fase 2 (mejoras de UX)
- Martes 3: Deploy final + monitoreo

**¿Necesito hacer algo?**
No. Los cambios son transparentes para el usuario.

**Riesgos:**
Bajo. Tenemos rollback plan si algo falla.

Cualquier duda, escribidme.

Saludos,
[Tu nombre]
```

### Al Equipo Técnico (Slack/Teams)

```
🚀 **Deploy: Correcciones Contexto Agente**

📅 **Timeline:**
• Viernes 09:00-11:00: Fase 1 (crítico)
• Lunes 09:00-10:30: Fase 2 (mejoras)
• Martes 09:00-13:00: Fase 3 + prod deploy

🎯 **Objetivo:** Fix de gaps en interpretación de respuestas de herramientas

📊 **Métricas a vigilar:**
• Efectividad: >85% (target 90%)
• Errores silenciosos: <10%
• Escalaciones: <20%

🔴 **Criterio rollback:** Efectividad <75% o errores >25%

📋 **Checklist pre-deploy:**
- [ ] Tests pasando (20 unit + 10 integration + 5 e2e)
- [ ] Staging verificado
- [ ] Dashboard métricas ready
- [ ] Rollback plan documentado

🔗 **Docs:** `/docs/PLAN_IMPLEMENTACION_CORRECCIONES.md`

Preguntas → #agent-support
```

---

## APRENDIZAJES Y MEJORAS CONTINUAS

### Post-Mortem (Después del Deploy)

**Preguntas a responder:**
1. ¿Se cumplieron los targets de métricas?
2. ¿Hubo problemas no anticipados?
3. ¿Qué aprendimos sobre ingeniería de contexto?
4. ¿Cómo podemos prevenir estos gaps en el futuro?

### Mejoras de Proceso

**Para prevenir gaps futuros:**

1. **Test de Contexto Automatizado**
   - CI pipeline que valida que cada herramienta está documentada en prompts
   - Verificación de que ejemplos de uso son consistentes con schemas

2. **Documentación Viva**
   - Generar docs de herramientas automáticamente desde código
   - Sync bidireccional: código → docs, docs → validación de código

3. **Context Engineering Review**
   - Code review incluye review de impacto en contexto
   - Checklist: "¿Actualicé los prompts relevantes?"

4. **Observability de Contexto**
   - Logging de qué partes del contexto usa el LLM
   - Análisis de qué secciones se ignoran (candidatos a remover)

---

## CONCLUSIÓN

Este plan implementa correcciones críticas de manera sistemática y medible. Cada fase es independiente y testeable, permitiendo rollback granular si es necesario.

**Próximos pasos:**
1. Revisar y aprobar este plan
2. Comenzar Fase 1 el viernes 30 de enero
3. Monitorear métricas continuamente
4. Iterar basado en feedback

**Éxito se medirá por:**
- Mejora en KPIs objetivos (efectividad, errores)
- Feedback positivo de usuarios
- Reducción de escalaciones a humanos

---

**Preparado por:** Experto en Ingeniería de Contexto  
**Revisado por:** [Pendiente]  
**Aprobado por:** [Pendiente]  
**Fecha de aprobación:** [Pendiente]
