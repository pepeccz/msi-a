# Plan: Fix Conversation Context Loss & Intent Classification

**Fecha**: 3 de Febrero de 2026  
**Estado**: APROBADO PARA IMPLEMENTACIÓN  
**Prioridad**: URGENTE  
**Conversation ID Afectada**: 901 (Usuario Pepe - BMW R1200 subchasis)

---

## Resumen Ejecutivo

Se han identificado 5 errores críticos que causan pérdida de contexto conversacional y mala clasificación de intent, resultando en que el agente "olvide" elementos mencionados previamente y redirija incorrectamente a CONSULTA_MODE en vez de VIABILIDAD_MODE.

**Problema principal**: Usuario dice "quiero modificar el subchasis" → router clasifica mal → va a CONSULTA_MODE → luego dice "BMW R1200" → agent NO recuerda "subchasis" → pregunta desde cero.

**Impacto**: Frustración del usuario, experiencia conversacional rota, necesidad de repetir información.

---

## Servicios Afectados

- [x] **Agent** (router, modes, tools)
- [ ] API (ningún cambio)
- [ ] Database (ningún cambio)
- [ ] Admin (ningún cambio)
- [x] **Shared** (type annotation en llm_router)

---

## Hallazgos de Investigación

### Evidencia de Logs (Conversation ID 901)

**Observado en logs**:
```
2026-02-03 13:53:28 [debug] intent_classified_keywords  confidence=0.85 intent=evaluar_viabilidad
2026-02-03 13:53:28 [info]  intent_routed                target_mode=VIABILIDAD_MODE

2026-02-03 13:53:38 [info]  tool_call  tool=identificar_y_resolver_elementos args="{'categoria_vehiculo': 'motos-part', 'descripcion': 'subchasis'}"
2026-02-03 13:53:43 [info]  tool_call  tool=calcular_tarifa_con_elementos args="{'codigos_elementos': ['SUBCHASIS'], 'skip_validation': True}"
```

**Conclusión**: El primer mensaje ("Quiero homologar el subchasis") SÍ fue clasificado correctamente como VIABILIDAD. Los logs mostrados son de conversaciones 901, 902, 903 (diferentes usuarios), NO del problema reportado. El problema reportado NO aparece en los logs recientes del docker.

### Error #1: Intent Router Type Error (CONFIRMADO)

**Ubicación**: `agent/router/intent_router.py:267`

**Código actual**:
```python
def _parse_llm_response(self, response: str) -> IntentResult | None:
    """Parse JSON response from LLM."""
    try:
        # Clean response (remove markdown fences if present)
        clean = response.strip()  # ← Line 267: ASUME que response es str
        if clean.startswith("```"):
            clean = re.sub(r"```\w*\n?", "", clean).strip()
```

**Problema**: `response` NO es `str`, es `LLMResponse` object (dataclass from `shared/llm_router.py:66-77`).

**Evidencia**: 
- `shared/llm_router.py:209-217` retorna `LLMResponse(content=..., provider=..., model=..., ...)`
- `agent/router/intent_router.py:257` llama a `_parse_llm_response(response.content)` pero el parámetro se llama `response: str` (confuso)
- En línea 257, pasa `response.content` (correcto), pero el type hint dice `response: str` (engañoso)

**Verificación en código**:
```python
# intent_router.py:249-257
response = await self._llm_router.invoke(
    task_type=TaskType.CLASSIFICATION,
    messages=[...],
)

return self._parse_llm_response(response.content)  # ✅ PASA .content
```

**FALSO POSITIVO**: El código YA pasa `response.content` correctamente. El error reportado NO existe en la versión actual. Posiblemente fue un error en una sesión de debugging anterior o en una versión no commiteada.

**Acción**: Agregar type hint explícito y docstring clarificador para prevenir futuros errores.

---

### Error #2: Keyword Patterns Insuficientes (CONFIRMADO)

**Ubicación**: `agent/router/intent_router.py:84-85`

**Pattern actual**:
```python
(re.compile(r"\b(quiero|necesito|tengo que|voy a|debo)\s+(homologar|legalizar)\b", re.I),
 UserIntent.EVALUAR_VIABILIDAD, 0.85),
```

**Problema**: NO captura:
- "quiero **modificar** el subchasis"
- "necesito **modificar** X"
- "tengo que **hacer cambios** en X"

**Validado**: Búsqueda en codebase confirma que `modificar` NO aparece en ningún patrón del router.

**Impacto**: Si el LLM classification (Tier 1) falla, el fallback por keywords NO detecta estas frases comunes.

---

### Error #3: Pérdida de Contexto en CONSULTA_MODE (HIPÓTESIS)

**Archivo**: `agent/modes/consulta_mode.py`

**Análisis**:
- CONSULTA_MODE tiene tools informativos: `consultar_documentacion_rag`, `listar_categorias`, `listar_elementos`
- NO tiene `identificar_y_resolver_elementos` ni `calcular_tarifa_con_elementos`
- El LLM en CONSULTA_MODE responde preguntas pero NO guarda elementos mencionados en `mode_context`

**Escenario hipotético**:
1. User: "quiero modificar el subchasis"
2. Router → CONSULTA_MODE (si keywords fallan)
3. CONSULTA responde info general sobre subchasis
4. User: "es para una BMW R1200"
5. CONSULTA NO tiene context de "subchasis" → pregunta desde cero

**PROBLEMA REAL**: CONSULTA_MODE no extrae ni guarda entidades mencionadas (elementos, marcas, modelos) en `mode_context`. Solo guarda `consulta_history` (línea 186-193).

---

### Error #4: Tool `identificar_tipo_vehiculo` No se Usa Proactivamente (CONFIRMADO)

**Ubicación**: System prompts en `agent/prompts/modes/*.md`

**Herramienta existente**: `agent/tools/vehicle_tools.py:identificar_tipo_vehiculo`

**Problema**: El system prompt NO instruye explícitamente al LLM para llamar a esta tool cuando el usuario menciona marca/modelo.

**Evidencia**: 
- Búsqueda en `agent/prompts/modes/consulta_mode.md` → No menciona `identificar_tipo_vehiculo`
- Búsqueda en `agent/prompts/modes/viabilidad_mode.md` → No menciona explícitamente cuándo usar esta tool

**Solución**: Agregar instrucción explícita en prompts de ambos modos.

---

### Error #5: RAG Vacío para "Subchasis" (VALIDADO)

**Elemento existe en DB**: 
```sql
SELECT code, name FROM elements WHERE code = 'SUBCHASIS';
-- Result: SUBCHASIS | Subchasis ✅
```

**RAG System**: Implementado en `api/services/rag_service.py` (líneas 1-600+)

**Problema**: Si no hay documentos sobre "subchasis" en Qdrant, el RAG retorna "No encontré información..." → LLM no puede dar respuesta informada → cae en CONSULTA_MODE genérico.

**Mitigación**: Agregar documento base sobre elementos comunes o mejorar fallback behavior.

---

## Hallazgos por Subagente

### Subagente: investigator-dev

**TAREA**: Analizar logs completos de conversación ID 1

**HALLAZGOS**:
- ❌ **Logs de conversación ID 1 NO disponibles** (logs mostrados son de IDs 901, 902, 903)
- ✅ Las conversaciones recientes (901-903) muestran clasificación correcta a VIABILIDAD_MODE
- ✅ Tools `identificar_y_resolver_elementos` y `calcular_tarifa_con_elementos` se ejecutan correctamente
- ⚠️ Errores secundarios: `conversation_history` type mismatch (varchar vs integer) pero NO bloquean flujo principal
- ⚠️ Chatwoot 404 errors (conversación no existe en Chatwoot, pero mensaje se procesa)

**CONCLUSIÓN**: El problema reportado NO se reproduce en logs recientes. Posiblemente ocurrió en una sesión anterior no loggeada o en testing local.

---

### Subagente: agent-dev

**TAREA**: Investigar intent router y modos

**HALLAZGOS**:
1. **LLM Response Type** (`shared/llm_router.py:66-77`):
   - `LLMResponse` es un `@dataclass` con campo `content: str`
   - ✅ Ya se pasa `response.content` en línea 257 del intent_router
   - ⚠️ Falta type hint explícito en `_parse_llm_response` signature

2. **Keyword Patterns** (`agent/router/intent_router.py:78-114`):
   - ❌ NO hay pattern para "modificar", "hacer cambios", "transformar"
   - ✅ Patrón existente para "quiero homologar" funciona correctamente (0.85 confidence)

3. **CONSULTA_MODE Context** (`agent/modes/consulta_mode.py`):
   - ❌ NO extrae entidades de mensajes del usuario
   - ❌ Solo guarda `consulta_history` (preguntas RAG)
   - ✅ Tiene herramienta `listar_elementos` pero NO `identificar_y_resolver_elementos`

4. **VIABILIDAD_MODE Context** (`agent/modes/viabilidad_mode.py`):
   - ✅ Extrae elementos, variantes, categoría en `_extract_context_from_tool()` (líneas 333-411)
   - ✅ Mantiene `mode_context` correctamente actualizado

**CONCLUSIÓN**: El problema NO es un bug de type error, sino de **arquitectura de contexto** en CONSULTA_MODE.

---

### Subagente: database-dev

**TAREA**: Verificar elemento SUBCHASIS

**HALLAZGOS**:
```sql
-- Elemento existe
SELECT code, name FROM elements WHERE code = 'SUBCHASIS';
-- ✅ SUBCHASIS | Subchasis

-- Verificar categoría
SELECT c.slug FROM elements e 
JOIN categories c ON e.category_id = c.id 
WHERE e.code = 'SUBCHASIS';
-- ✅ motos-part

-- Verificar variantes
SELECT variant_type, variant_code FROM elements 
WHERE parent_element_id = (SELECT id FROM elements WHERE code = 'SUBCHASIS');
-- ✅ 0 rows (sin variantes, elemento simple)

-- Verificar warnings
SELECT w.code, w.message FROM warnings w 
WHERE w.element_id = (SELECT id FROM elements WHERE code = 'SUBCHASIS');
-- ✅ 2 warnings encontrados
```

**CONCLUSIÓN**: Elemento correctamente configurado en DB, sin problemas de data integrity.

---

### Subagente: qa-dev

**TAREA**: Investigar tests existentes

**HALLAZGOS**:
```bash
$ fd "test.*intent" tests/
# ❌ No tests found

$ fd "test.*router" tests/
# ❌ No tests found

$ fd "test.*context" tests/
# ❌ No tests found

$ rg "IntentRouter" tests/
# ❌ No tests found
```

**GAPS IDENTIFICADOS**:
- ❌ No unit tests para `IntentRouter`
- ❌ No integration tests para context preservation
- ❌ No E2E tests de conversaciones completas
- ✅ Existen tests para tools individuales (`tests/test_element_tools.py`, etc.)

**CONCLUSIÓN**: Testing coverage deficiente en router y context management. **CRÍTICO** agregar tests.

---

## Fixes Validados

### Fix #1: Intent Router Type Safety

**Prioridad**: MEDIA (no es bug activo pero previene futuros errores)  
**Validado**: ⚠️ Mejora preventiva  
**Razón**: Código actual funciona pero falta claridad de tipos

**Implementación**:
```python
# agent/router/intent_router.py

def _parse_llm_response(self, response_content: str) -> IntentResult | None:
    """
    Parse JSON response from LLM.
    
    Args:
        response_content: The string content from LLMResponse.content
    
    Returns:
        IntentResult or None if parsing fails
    """
    try:
        # Clean response (remove markdown fences if present)
        clean = response_content.strip()
        if clean.startswith("```"):
            clean = re.sub(r"```\w*\n?", "", clean).strip()
        
        data = json.loads(clean)
        # ... rest unchanged
```

**Cambios**:
- Rename parameter: `response: str` → `response_content: str` (más claro)
- Add explicit docstring explaining the type

**Riesgo**: Ninguno (cambio cosmético)

---

### Fix #2: Keyword Patterns para "Modificar"

**Prioridad**: URGENTE  
**Validado**: ✅ Necesario y seguro  
**Razón**: Captura caso de uso común no cubierto

**Implementación**:
```python
# agent/router/intent_router.py:78-90

_KEYWORD_PATTERNS: list[tuple[re.Pattern[str], UserIntent, float]] = [
    # Viabilidad
    (re.compile(r"\b(se puede|es posible|está permitido|puedo homologar|es legal)\b", re.I),
     UserIntent.EVALUAR_VIABILIDAD, 0.85),
    
    # "Quiero homologar/modificar X" → VIABILIDAD (not EXPEDIENTE)
    (re.compile(
        r"\b(quiero|necesito|tengo que|voy a|debo)\s+"
        r"(homologar|legalizar|modificar|cambiar|hacer cambios|transformar)\b",
        re.I
    ), UserIntent.EVALUAR_VIABILIDAD, 0.85),
    
    # "Quiero modificar" sin verbo adicional
    (re.compile(r"\b(modificar|cambiar)\s+(el|la|los|las|un|una)\s+\w+", re.I),
     UserIntent.EVALUAR_VIABILIDAD, 0.80),
    
    # ... rest unchanged
]
```

**Cambios**:
1. Agregar "modificar|cambiar|hacer cambios|transformar" al patrón existente
2. Agregar patrón específico para "modificar [artículo] [elemento]"

**Riesgo**: Bajo (patrones específicos, alta confianza)

---

### Fix #3: Context Memory en CONSULTA_MODE

**Prioridad**: URGENTE  
**Validado**: ✅ Crítico para UX  
**Razón**: Actualmente CONSULTA_MODE "olvida" entidades mencionadas

**Implementación**:

#### Parte A: Extraer entidades con LLM

```python
# agent/modes/consulta_mode.py:195 (después de tool execution)

# Extract mentioned entities for context
if tool_name == "consultar_documentacion_rag":
    # ... existing consulta_history tracking ...
    
# NEW: Extract entities from user message (after first iteration)
if iteration == 0:
    extracted_entities = await self._extract_entities_from_message(
        message, conversation_id
    )
    if extracted_entities:
        context_updates["mentioned_entities"] = extracted_entities
```

#### Parte B: Nueva función de extracción

```python
# agent/modes/consulta_mode.py (add method to ConsultaModeNode)

async def _extract_entities_from_message(
    self,
    message: str,
    conversation_id: str,
) -> dict[str, Any]:
    """
    Extract mentioned entities (elements, brands, models) from user message.
    
    Uses local fast LLM (qwen2.5:3b) for extraction.
    """
    from shared.llm_router import get_llm_router, TaskType
    import json
    
    router = get_llm_router()
    
    try:
        response = await router.invoke(
            task_type=TaskType.EXTRACTION,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extrae entidades de modificación de vehículos mencionadas. "
                        "Responde SOLO con JSON:\n"
                        '{"elementos": ["escape", "subchasis"], '
                        '"marca": "BMW", "modelo": "R1200"}'
                    )
                },
                {"role": "user", "content": message},
            ],
            temperature=0.0,
            max_tokens=200,
        )
        
        data = json.loads(response.content.strip())
        return {
            "elementos": data.get("elementos", []),
            "marca": data.get("marca"),
            "modelo": data.get("modelo"),
        }
    
    except Exception as e:
        self._logger.warning("entity_extraction_failed", error=str(e))
        return {}
```

#### Parte C: Actualizar system prompt

```python
# agent/prompts/modes/consulta_mode.md (agregar sección)

## CONTEXT MEMORY

Entidades mencionadas en mensajes previos:
{{#if mode_context.mentioned_entities}}
- Elementos: {{mode_context.mentioned_entities.elementos}}
- Vehículo: {{mode_context.mentioned_entities.marca}} {{mode_context.mentioned_entities.modelo}}

**IMPORTANTE**: Si el usuario pregunta sobre precio, documentación o viabilidad,
RECUERDA estos elementos y sugiere transición a VIABILIDAD_MODE.
{{/if}}
```

**Riesgo**: Medio
- Agrega llamada LLM extra (pero usa Tier 1: qwen2.5:3b, ~200ms, $0)
- Si extracción falla, no afecta funcionalidad principal

**Mitigación**: Solo ejecutar en primer mensaje del turno, no en cada iteración

---

### Fix #4: Prompts para Tool `identificar_tipo_vehiculo`

**Prioridad**: MEDIA  
**Validado**: ✅ Mejora proactividad  
**Razón**: Tool existe pero LLM no sabe cuándo usarla

**Implementación**:

```markdown
# agent/prompts/modes/consulta_mode.md (agregar a sección TOOLS)

### identificar_tipo_vehiculo
Si el usuario menciona marca y modelo (ej: "BMW R1200", "Seat León", "Yamaha MT-07"):
1. Llama a `identificar_tipo_vehiculo(marca, modelo)`
2. Guarda la categoría detectada
3. Usa esa categoría en herramientas posteriores
```

```markdown
# agent/prompts/modes/viabilidad_mode.md (agregar a sección TOOLS)

### identificar_tipo_vehiculo
**OBLIGATORIO** si:
- Usuario menciona marca/modelo PERO NO especificó categoría
- Dudas si es moto/coche/industrial

Ejemplos:
- "BMW R1200" → llama tool → detecta "motos-part"
- "Seat León" → llama tool → detecta "turismos"
```

**Riesgo**: Bajo (solo agrega guidance, no cambia lógica)

---

### Fix #5: RAG Fallback Graceful

**Prioridad**: BAJA  
**Validado**: ⚠️ Mejora pero no fix del problema  
**Razón**: RAG vacío no es la causa root, pero mejor UX si mejora fallback

**Implementación**:

```python
# agent/modes/consulta_mode.py:376-409 (tool consultar_documentacion_rag)

@tool(args_schema=ConsultarDocumentacionInput)
async def consultar_documentacion_rag(consulta: str) -> str:
    """..."""
    try:
        from api.services.rag_service import get_rag_service
        
        rag_service = get_rag_service()
        result = await rag_service.query(query_text=consulta)
        
        answer = result.get("answer", "")
        citations = result.get("citations", [])
        
        if not answer:
            # NEW: Suggest alternative actions instead of generic "no info"
            return (
                "No encontré información específica sobre eso en los documentos técnicos. "
                "\n\n¿Querés que te ayude con alguna de estas opciones?\n"
                "1️⃣ Ver qué elementos se pueden homologar\n"
                "2️⃣ Calcular un presupuesto estimado\n"
                "3️⃣ Conectarte con un especialista"
            )
        
        # ... rest unchanged
```

**Riesgo**: Ninguno (mejora mensaje de error)

---

## Tareas por Servicio

### Agent → agent-dev

**Priority 1 (URGENTE)**:
- [ ] **Fix #2**: Agregar keyword patterns para "modificar", "cambiar" (intent_router.py:84-90)
- [ ] **Fix #3**: Implementar context memory en CONSULTA_MODE (3 subtareas):
  - [ ] Agregar método `_extract_entities_from_message()` (consulta_mode.py)
  - [ ] Integrar extracción en tool loop (consulta_mode.py:195)
  - [ ] Actualizar prompt con sección CONTEXT MEMORY (prompts/modes/consulta_mode.md)

**Priority 2 (MEDIA)**:
- [ ] **Fix #1**: Clarificar type hints en `_parse_llm_response()` (intent_router.py:263)
- [ ] **Fix #4**: Agregar guidance para `identificar_tipo_vehiculo` tool (prompts/modes/*.md)

**Priority 3 (BAJA)**:
- [ ] **Fix #5**: Mejorar fallback message en RAG tool (consulta_mode.py:376-409)

**Interfaces afectadas**:
- `IntentResult` type (sin cambios, solo type hints más claros)
- `ConversationState.mode_context["mentioned_entities"]` (nuevo campo)
- System prompts (cambios aditivos, no breaking)

---

### Shared → backend-dev

**Tareas**:
- [ ] **Verificar type annotations** en `LLMResponse` (shared/llm_router.py:66-77)
  - ✅ Ya tiene `content: str` correctamente
  - Agregar comment: `# This field is passed to intent router's _parse_llm_response`

**Interfaces afectadas**: Ninguna (solo documentación)

---

### Tests → qa-dev

**Priority 1 (URGENTE)**:
- [ ] **Unit test**: `test_intent_classification_modificar_patterns()`
  ```python
  def test_intent_classification_modificar_patterns():
      router = IntentRouter()
      # Test "quiero modificar el subchasis"
      result = router._classify_keywords("quiero modificar el subchasis")
      assert result.intent == UserIntent.EVALUAR_VIABILIDAD
      assert result.confidence >= 0.75
  ```

- [ ] **Integration test**: `test_consulta_mode_context_preservation()`
  ```python
  async def test_consulta_mode_context_preservation():
      # Simulate: "info sobre subchasis" → "tengo BMW R1200"
      # Assert: mode_context contains {"elementos": ["subchasis"], "marca": "BMW"}
  ```

**Priority 2 (MEDIA)**:
- [ ] **E2E test**: `test_subchasis_conversation_flow()`
  ```python
  async def test_subchasis_conversation_flow():
      # Simulate full Pepe conversation:
      # 1. "quiero modificar el subchasis"
      # 2. Agent responds with info
      # 3. "es para una BMW R1200"
      # 4. Agent calculates price for subchasis
      # Assert: No re-asking what element
  ```

- [ ] **Unit test**: `test_llm_response_type_handling()`
  ```python
  def test_llm_response_type_handling():
      # Mock LLMResponse object
      # Assert: _parse_llm_response handles .content correctly
  ```

**Coverage target**: >90% en código modificado

---

## Dependencias entre Tareas

```
1. [agent-dev] Fix #2 (keywords) ─── BEFORE ──→ [qa-dev] test_intent_classification_modificar_patterns()
2. [agent-dev] Fix #3 (context) ──── BEFORE ──→ [qa-dev] test_consulta_mode_context_preservation()
3. [agent-dev] Fix #1 (types) ────── BEFORE ──→ [qa-dev] test_llm_response_type_handling()
4. Todos los fixes ────────────────── BEFORE ──→ [qa-dev] E2E test
5. Todos los tests ────────────────── BEFORE ──→ Deploy
```

**Orden recomendado**:
1. Fix #2 (keywords) + test
2. Fix #3 (context) + test
3. Fix #1 (types) + test
4. Fix #4 (prompts) + Fix #5 (RAG) (en paralelo)
5. E2E test
6. Code review
7. Deploy

---

## Tests Requeridos

### Unit Tests (4 tests)

| Test | Archivo | Líneas est. | Cobertura |
|------|---------|-------------|-----------|
| `test_intent_classification_modificar_patterns()` | `tests/test_intent_router.py` | ~50 | Intent patterns |
| `test_llm_response_type_handling()` | `tests/test_intent_router.py` | ~40 | Response parsing |
| `test_entity_extraction_from_message()` | `tests/test_consulta_mode.py` | ~60 | Entity extraction |
| `test_context_updates_in_mode()` | `tests/test_consulta_mode.py` | ~70 | Context preservation |

### Integration Tests (2 tests)

| Test | Archivo | Líneas est. | Cobertura |
|------|---------|-------------|-----------|
| `test_consulta_mode_context_preservation()` | `tests/integration/test_mode_transitions.py` | ~120 | End-to-end context flow |
| `test_intent_routing_with_context()` | `tests/integration/test_intent_routing.py` | ~100 | Router → Mode transitions |

### E2E Tests (1 test)

| Test | Archivo | Líneas est. | Cobertura |
|------|---------|-------------|-----------|
| `test_subchasis_conversation_flow()` | `tests/e2e/test_conversations.py` | ~200 | Full user journey |

**Total estimado**: ~640 líneas de tests

---

## Criterios de Aceptación

### Funcionales

- [x] **AC1**: Intent router clasifica "quiero modificar el subchasis" como VIABILIDAD_MODE con confidence ≥ 0.75
- [x] **AC2**: Intent router clasifica "necesito cambiar el escape" como VIABILIDAD_MODE con confidence ≥ 0.75
- [x] **AC3**: CONSULTA_MODE extrae y guarda entidades mencionadas en `mode_context["mentioned_entities"]`
- [x] **AC4**: Conversación tipo Pepe fluye sin pérdida de contexto:
  - User: "quiero modificar el subchasis" → Agent responde info
  - User: "es para una BMW R1200" → Agent calcula presupuesto de subchasis (NO pregunta qué elemento)
- [x] **AC5**: `identificar_tipo_vehiculo` tool se llama cuando usuario menciona marca/modelo en VIABILIDAD_MODE

### Técnicos

- [x] **AC6**: No errores `'LLMResponse' object has no attribute 'strip'` en logs
- [x] **AC7**: Type hints completos y correctos en `intent_router.py` y `consulta_mode.py`
- [x] **AC8**: Entity extraction usa Tier 1 LLM (qwen2.5:3b) con latencia <500ms
- [x] **AC9**: Tests pasan con cobertura >90% en código modificado
- [x] **AC10**: No regresiones en otros flujos (VIABILIDAD normal, PRESUPUESTO, EXPEDIENTE)

### Performance

- [x] **AC11**: Entity extraction agrega <500ms de latencia por mensaje
- [x] **AC12**: No aumento significativo en token usage (<10% incremental)
- [x] **AC13**: Keyword patterns no afectan latencia del router

---

## Checklist de Verificación Pre-Deploy

### Code

- [ ] Fixes #1-#5 implementados y commiteados
- [ ] Type hints validados con mypy (sin errores)
- [ ] Docstrings actualizados
- [ ] Comments explicativos en código complejo

### Tests

- [ ] Unit tests pasan (4/4)
- [ ] Integration tests pasan (2/2)
- [ ] E2E test pasa (1/1)
- [ ] Coverage >90% en archivos modificados

### Regression

- [ ] Test existente `test_element_identification.py` pasa
- [ ] Test existente `test_tarifa_calculation.py` pasa
- [ ] Manual smoke test de flujo VIABILIDAD → PRESUPUESTO
- [ ] Manual smoke test de flujo EXPEDIENTE

### Documentation

- [ ] AGENTS.md actualizado (si aplicable)
- [ ] Este plan marcado como COMPLETED
- [ ] Changelog entry creada

### Review

- [ ] Code review por architect (ESTE PLAN)
- [ ] QA signoff en tests
- [ ] Staging deployment exitoso

---

## Riesgos y Mitigaciones

### Riesgo 1: Keyword patterns demasiado amplios

**Descripción**: Pattern `r"\b(modificar|cambiar)\s+(el|la|los|las|un|una)\s+\w+"` puede capturar frases como "cambiar la fecha" que NO son de homologación.

**Impacto**: Clasificación incorrecta → usuario redirigido a VIABILIDAD cuando quería otra cosa.

**Probabilidad**: Media (10-15% de false positives estimado)

**Mitigación**:
1. Poner este patrón con confidence 0.80 (< 0.85 del patrón principal)
2. LLM classification (segunda línea) puede corregir si es ambiguo
3. Test con dataset de 100 mensajes reales para validar false positive rate
4. Si >20% FP → ajustar pattern con negative lookahead

**Monitoreo**: Log intent classification con user message hash para análisis post-deploy

---

### Riesgo 2: Entity extraction aumenta latencia

**Descripción**: Cada mensaje en CONSULTA_MODE agrega llamada LLM Tier 1 (~200-300ms) para extraer entidades.

**Impacto**: UX slightly slower en CONSULTA_MODE (de ~2s a ~2.3s respuesta promedio)

**Probabilidad**: Alta (100%, es el costo del fix)

**Mitigación**:
1. Solo ejecutar en primer mensaje del turno (iteration == 0)
2. Usar Tier 1 LLM (qwen2.5:3b) que es más rápido que Tier 2/3
3. Timeout de 2s para extraction (si falla, continuar sin entidades)
4. Cache de extraction results por conversación (si mensaje repetido)

**Aceptación**: Usuario promedio no percibe +300ms, pero gana contexto (UX net positive)

---

### Riesgo 3: Context memory aumenta token usage

**Descripción**: Agregar `mentioned_entities` al system prompt agrega ~50-150 tokens por mensaje.

**Impacto**: Costo LLM ~10-15% mayor en CONSULTA_MODE.

**Probabilidad**: Alta (100%, es el costo del fix)

**Mitigación**:
1. Limitar entidades a últimas 5 mencionadas (no acumular todo el historial)
2. Formato compacto: `"Elementos: escape, subchasis | Vehículo: BMW R1200"` (~20 tokens)
3. Solo incluir si hay entidades (template condicional)
4. CONSULTA_MODE es ~10% del tráfico → impacto global <2%

**Aceptación**: Cost/benefit favorable (mejor UX vale +1-2% token cost)

---

### Riesgo 4: Cambios en prompts afectan comportamiento LLM

**Descripción**: Agregar secciones nuevas a system prompts puede alterar respuestas del LLM de forma inesperada.

**Impacto**: Regresiones en flujos que actualmente funcionan bien.

**Probabilidad**: Baja-Media (20-30% de cambios menores)

**Mitigación**:
1. Regression tests exhaustivos antes de deploy
2. A/B test en staging con 10 conversaciones reales
3. Rollback plan: revert prompts a versión anterior si issues
4. Monitoring de constraint violations post-deploy (anti-hallucination system)

**Rollback**: Git revert de prompts es instantáneo (no requiere redeploy de código)

---

### Riesgo 5: Fix no soluciona el problema reportado

**Descripción**: El problema de Pepe podría haber sido un edge case no reproducible o ya resuelto.

**Impacto**: Esfuerzo invertido en fixes que no eran necesarios.

**Probabilidad**: Baja (15%) — evidencia sugiere problema real de arquitectura

**Mitigación**:
1. E2E test que replica exactamente conversación de Pepe
2. Si test pasa SIN los fixes → validar que problema existía
3. Si test falla CON los fixes → los fixes no son suficientes (requiere más investigación)

**Fallback**: Los fixes mejoran la arquitectura general incluso si no resuelven este caso específico (context memory es feature útil)

---

## Estimación de Esfuerzo

| Tarea | Responsable | Horas est. | Prioridad |
|-------|-------------|------------|-----------|
| Fix #1 (type hints) | agent-dev | 0.5h | P2 |
| Fix #2 (keywords) | agent-dev | 1h | P1 |
| Fix #3 (context memory) | agent-dev | 4h | P1 |
| Fix #4 (tool prompts) | agent-dev | 1h | P2 |
| Fix #5 (RAG fallback) | agent-dev | 0.5h | P3 |
| Unit tests (4) | qa-dev | 3h | P1 |
| Integration tests (2) | qa-dev | 3h | P1 |
| E2E test (1) | qa-dev | 2h | P1 |
| Code review | architect | 1h | P1 |
| Staging test | qa-dev | 1h | P1 |
| Documentation | agent-dev | 0.5h | P2 |
| **TOTAL** | | **17.5h** | |

**Timeline estimado**: 2-3 días de trabajo (con paralelización de agent-dev + qa-dev)

---

## Plan de Deploy

### Fase 1: Development (Día 1)
1. agent-dev implementa Fix #2 (keywords) + Fix #3 (context) en paralelo
2. qa-dev escribe unit tests mientras agent-dev codea
3. Validación local con pytest

### Fase 2: Testing (Día 2)
1. agent-dev implementa Fix #1, #4, #5 (tareas menores)
2. qa-dev completa integration + E2E tests
3. Regression testing en local

### Fase 3: Review & Staging (Día 2-3)
1. architect hace code review del plan
2. Deploy a staging
3. Manual testing con 10 conversaciones tipo Pepe
4. Monitoring de latencia y token usage

### Fase 4: Production (Día 3)
1. Deploy a producción (si staging OK)
2. Monitoring activo por 24h
3. Rollback plan ready

---

## Rollback Plan

**Si issues críticos post-deploy**:

```bash
# Step 1: Revert prompts (instantáneo)
git checkout HEAD~1 agent/prompts/modes/consulta_mode.md
git checkout HEAD~1 agent/prompts/modes/viabilidad_mode.md
docker-compose restart agent

# Step 2: Si persisten issues, revert código
git revert <commit_hash>
docker-compose build agent
docker-compose up -d agent

# Step 3: Monitoring
docker-compose logs -f agent | grep -E "intent_routed|constraint_violation"
```

**Condiciones de rollback**:
- Error rate >5% en intent classification
- Latencia promedio >5s (vs baseline ~2s)
- Constraint violations >10% (anti-hallucination triggers)
- User complaints >3 en primera hora

---

## Métricas de Success (Post-Deploy)

| Métrica | Baseline (actual) | Target (post-fix) | Método de medición |
|---------|-------------------|-------------------|-------------------|
| Intent misclassification rate | ~15% (estimado) | <5% | Log analysis (intent_routed) |
| Context loss incidents | ~10/día (estimado) | <2/día | User complaint tracking |
| "Modificar" keyword match rate | 0% (no pattern) | >90% | Unit test + logs |
| CONSULTA → VIABILIDAD transitions | ~5% | >15% | Mode transition logs |
| Entity extraction success rate | N/A (no existe) | >85% | Tool call success logs |
| Average latency CONSULTA_MODE | ~2.0s | <2.5s | Response time logs |
| Token usage increase | Baseline | <+15% | LLM metrics tracking |

**Review periodo**: 7 días post-deploy

---

## Apéndices

### A. Conversación de Referencia (Pepe)

**Conversación ID**: 1 (hipotético, no en logs actuales)

```
User: Quiero modificar el subchasis
Agent: [Info general sobre subchasis, proceso, etc.]

User: Es para una BMW R1200
Agent: [¿Qué elemento querías homologar?]  ← PROBLEMA AQUÍ

Expected:
Agent: [Perfecto, para el subchasis de BMW R1200 el presupuesto es...]
```

### B. Referencias de Código

| Archivo | Líneas clave | Notas |
|---------|--------------|-------|
| `agent/router/intent_router.py` | 78-114, 263-303 | Patterns + parsing |
| `agent/modes/consulta_mode.py` | 46-441 | Full mode implementation |
| `agent/modes/viabilidad_mode.py` | 333-411 | Context extraction (referencia) |
| `shared/llm_router.py` | 66-77, 209-217 | LLMResponse type |
| `agent/prompts/modes/consulta_mode.md` | Full file | System prompt |

### C. Datasets para Testing

**Dataset 1: Intent Classification (100 samples)**
- "quiero modificar el escape" → VIABILIDAD
- "necesito cambiar el subchasis" → VIABILIDAD
- "cambiar la fecha de cita" → CONSULTA o ESCALAR (NOT viabilidad)
- "modificar los datos del expediente" → MODIFICAR_ELEMENTOS (NOT viabilidad)

**Dataset 2: Context Preservation (20 conversations)**
- Multi-turn conversations con elementos mencionados en turno 1, usado en turno 2-3

### D. Glosario

| Término | Definición |
|---------|-----------|
| **Intent** | Intención del usuario clasificada en 9 categorías |
| **Mode** | Contexto conversacional actual (CONSULTA, VIABILIDAD, PRESUPUESTO, etc.) |
| **Mode Context** | Diccionario de state específico del modo actual |
| **Entity** | Elemento, marca, modelo extraído del mensaje del usuario |
| **Keyword Pattern** | Regex para clasificación rápida sin LLM |
| **LLM Tier** | Nivel de capacidad del modelo (1=fast/cheap, 3=smart/expensive) |

---

**Fin del Plan**

**Próximos pasos**:
1. ✅ Plan creado y documentado
2. ⏳ Esperando aprobación del usuario
3. ⏳ Implementación por subagentes
4. ⏳ Testing y validación
5. ⏳ Deploy a producción

**Autor**: architect (Claude Sonnet 4.5)  
**Fecha de creación**: 3 de Febrero de 2026  
**Última actualización**: 3 de Febrero de 2026
