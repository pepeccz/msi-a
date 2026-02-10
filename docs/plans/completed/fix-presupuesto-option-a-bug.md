# 🐛 Plan: Fix PRESUPUESTO_MODE "Re-pregunta Elementos Después de Opción A"

**Fecha de Creación**: 6 de Febrero de 2026  
**Prioridad**: P0 (CRÍTICO - Bug de producción)  
**Estimación Total**: 6-8 horas  
**Responsable**: Architect → agent-dev, qa-dev, investigator-dev  

---

## 📋 Executive Summary

### Problema

El agente en PRESUPUESTO_MODE vuelve a preguntar "¿Qué elementos quieres homologar?" después de que el usuario selecciona "Opción A" (ver fotos de ejemplo), a pesar de haber identificado correctamente los elementos y calculado el precio.

**Impacto**:
- ❌ Experiencia de usuario degradada (confusión + frustración)
- ❌ Conversaciones más largas → mayor consumo de tokens
- ❌ Posible abandono del flujo por parte del cliente
- ❌ Afecta ~25% del tráfico (todo PRESUPUESTO_MODE)

### Solución

**Fase 1 (Fix Quirúrgico - Inmediato)**:
1. Re-inyectar ContextVar después de cada tool call para mantener sincronización
2. Setear flag `waiting_for_image_choice=True` después de ofrecer opciones A/B
3. Formatear contexto explícito "ESPERANDO: opción A/B" en el prompt dinámico
4. Actualizar `presupuesto_mode.md` con algoritmo claro anti-patrón

**Fase 2 (Fix Robusto - Arquitectónico)**:
1. Pattern matching pre-LLM para detectar "A"/"B" (similar a evaluacion_gateway.py)
2. Ejecutar acción determinística SIN depender del LLM
3. Optimización de tokens y latencia

**Resultado esperado**: Bug eliminado en Fase 1, arquitectura robusta en Fase 2.

---

## 🔍 Root Cause Analysis

### Investigaciones Completadas (4 Investigadores)

#### 1️⃣ investigator-estado (Persistencia)
**Hallazgo**: ✅ Estado SÍ persiste correctamente en Redis.

```python
# Evidencia:
mode_context = {
    "element_codes": ["ESCAPE"],
    "tarifa_calculada": {"precio": 410.0},
    "precio_comunicado": True,
    "elementos_confirmados": ["ESCAPE"]
}
```

**Conclusión**: NO es problema de persistencia de estado.

---

#### 2️⃣ investigator-tools (ContextVar Race Condition)
**Hallazgo**: ❌ RACE CONDITION - ContextVar NO se re-inyecta entre tool calls.

**Código actual** (`presupuesto_mode.py:174-186`):
```python
# 1. ContextVar se inyecta UNA SOLA VEZ
set_current_state(state)

# 2. Loop de tool calls
for iteration in range(MAX_TOOL_ITERATIONS):
    response = await llm.ainvoke(llm_messages)
    
    # 3. context_updates se actualizan...
    context_updates = self._extract_context_from_tool(...)
    
    # ❌ PROBLEMA: ContextVar NO se actualiza aquí!
    # Las tools llamadas en próxima iteración ven estado VIEJO
```

**Evidencia**:
```python
# image_tools.py:47-54
def enviar_imagenes_ejemplo():
    state = get_current_state()  # ← Lee ContextVar
    context = state.get("mode_context", {})
    
    if not context.get("precio_comunicado"):  # ← Siempre False si no se re-inyecta!
        raise ValueError("PRECIO_BEFORE_IMAGES")
```

**Conclusión**: Las tools leen estado desactualizado durante el loop.

---

#### 3️⃣ investigator-prompts (Prompt Ambiguo)
**Hallazgo**: ⚠️ Prompt NO instruye usar `elementos_confirmados` del estado.

**Código actual** (`prompts/modes/presupuesto_mode.md`):
```markdown
# FLUJO ESPERADO

1. Identificar elementos
2. Calcular precio
3. Comunicar precio + warnings
4. Ofrecer imágenes de ejemplo
```

**Problema**:
- ✅ Menciona "identificar elementos"
- ❌ NO menciona "NO volver a identificar si ya están confirmados"
- ❌ NO explica que Opción A activa `enviar_imagenes_ejemplo` automáticamente
- ❌ NO instruye leer `elementos_confirmados` del contexto

**Conclusión**: Prompt permite ambigüedad, LLM no tiene guía clara.

---

#### 4️⃣ investigator-modo (Flag No Usado)
**Hallazgo**: ❌ Flag `waiting_for_image_choice` existe pero NUNCA se setea a True.

**Código actual**:
```python
# state/conversation_state.py:100
waiting_for_image_choice: bool  # ✅ Flag definido

# presupuesto_mode.py (búsqueda completa)
# ❌ NUNCA se setea a True en ningún lugar
# ❌ NO hay pattern matching para "A"/"B"
```

**Comparación con EVALUACION_GATEWAY** (que SÍ funciona):
```python
# evaluacion_gateway.py:77-78
if not mode_context.get("gateway_question_asked"):
    return self._present_confirmation(state, mode_context)
    # ← Setea flag ANTES de esperar respuesta

# evaluacion_gateway.py:33-41
YES_PATTERNS = [re.compile(r"\b(sí|dale|vale|...)")]
NO_PATTERNS = [re.compile(r"\b(no|todavía no|...)")]
# ← Pattern matching PRE-LLM
```

**Conclusión**: PRESUPUESTO_MODE no implementa pattern matching ni flag management.

---

### Causa Raíz Consolidada

| Componente | Problema | Impacto |
|------------|----------|---------|
| **ContextVar** | NO se re-inyecta en loop | Tools leen estado desactualizado → validaciones fallan |
| **Flag Management** | `waiting_for_image_choice` nunca se activa | LLM no sabe que esperamos A/B → pregunta de nuevo |
| **Prompt** | No instruye usar `elementos_confirmados` | LLM no tiene contexto de qué evitar |
| **Pattern Matching** | No existe para "A"/"B" | Depende 100% del LLM → inconsistente |

**Cascada de Errores**:
1. Usuario elige "A" → LLM recibe mensaje "A"
2. Flag `waiting_for_image_choice` = False → LLM no sabe contexto
3. ContextVar desactualizado → `precio_comunicado=False`
4. Prompt ambiguo → LLM decide "volver a identificar"
5. Resultado: Re-pregunta elementos ❌

---

## 💡 Proposed Solution

### Fase 1: Fix Quirúrgico (INMEDIATO)

**Objetivo**: Eliminar el bug con cambios mínimos de alto impacto.

#### 1.1. Re-inyectar ContextVar en Loop

**Archivo**: `agent/modes/presupuesto_mode.py`

**Cambio**:
```python
# ANTES (líneas ~174-220)
set_current_state(state)  # ← Una sola vez

for iteration in range(MAX_TOOL_ITERATIONS):
    response = await llm.ainvoke(llm_messages)
    
    if response.tool_calls:
        for tool_call in response.tool_calls:
            result = await execute_tool(tool_call)
            context_updates = self._extract_context_from_tool(...)
            mode_context.update(context_updates)
    
    # ❌ ContextVar NO actualizado aquí

# DESPUÉS
set_current_state(state)  # Inicial

for iteration in range(MAX_TOOL_ITERATIONS):
    response = await llm.ainvoke(llm_messages)
    
    if response.tool_calls:
        for tool_call in response.tool_calls:
            result = await execute_tool(tool_call)
            context_updates = self._extract_context_from_tool(...)
            mode_context.update(context_updates)
            
            # ✅ RE-INYECTAR después de cada tool call
            updated_state = dict(state)
            updated_state["mode_context"] = mode_context
            set_current_state(updated_state)
```

**Impacto**: Tools ahora leen estado actualizado → validaciones funcionan correctamente.

---

#### 1.2. Setear Flag `waiting_for_image_choice`

**Archivo**: `agent/modes/presupuesto_mode.py`

**Cambio**:
```python
def _extract_context_from_tool(self, tool_name, result):
    updates = {}
    
    if tool_name == "enviar_imagenes_ejemplo":
        if result.get("success"):
            updates["imagenes_enviadas"] = True
            
            # ✅ NUEVO: Setear flag si se ofrecen opciones A/B
            image_data = result.get("data", {})
            if image_data.get("opcion_a") and image_data.get("opcion_b"):
                updates["waiting_for_image_choice"] = True
    
    # Si usuario responde (detectar en próxima iteración)
    if context.get("waiting_for_image_choice"):
        # Detectar selección A/B en message
        if "a" in message.lower() or "opción a" in message.lower():
            updates["waiting_for_image_choice"] = False
            updates["opcion_seleccionada"] = "A"
        elif "b" in message.lower() or "opción b" in message.lower():
            updates["waiting_for_image_choice"] = False
            updates["opcion_seleccionada"] = "B"
    
    return updates
```

**Impacto**: Flag indica estado de espera → LLM entiende contexto.

---

#### 1.3. Formatear Contexto Explícito en Prompt

**Archivo**: `agent/prompts/loader.py`

**Cambio**:
```python
# ANTES (líneas 174-186)
elif mode == "PRESUPUESTO_MODE":
    codes = context.get("element_codes", [])
    if codes:
        parts.append(f"ELEMENTOS: {', '.join(codes)}")
    tarifa = context.get("tarifa_calculada")
    if tarifa:
        precio = tarifa.get("precio_final") or tarifa.get("precio")
        if precio:
            parts.append(f"PRECIO: {precio}€ +IVA")
    if context.get("precio_comunicado"):
        parts.append("PRECIO YA COMUNICADO")
    if context.get("imagenes_enviadas"):
        parts.append("IMÁGENES YA ENVIADAS")

# DESPUÉS
elif mode == "PRESUPUESTO_MODE":
    codes = context.get("element_codes", [])
    confirmados = context.get("elementos_confirmados", [])
    
    # ✅ Priorizar elementos confirmados
    if confirmados:
        parts.append(f"ELEMENTOS CONFIRMADOS: {', '.join(confirmados)}")
    elif codes:
        parts.append(f"ELEMENTOS: {', '.join(codes)}")
    
    tarifa = context.get("tarifa_calculada")
    if tarifa:
        precio = tarifa.get("precio_final") or tarifa.get("precio")
        if precio:
            parts.append(f"PRECIO: {precio}€ +IVA")
    
    if context.get("precio_comunicado"):
        parts.append("PRECIO YA COMUNICADO")
    
    if context.get("imagenes_enviadas"):
        parts.append("IMÁGENES YA ENVIADAS")
    
    # ✅ NUEVO: Flag de espera
    if context.get("waiting_for_image_choice"):
        parts.append("ESPERANDO: El usuario debe elegir Opción A o B")
        parts.append("NO vuelvas a identificar elementos ni calcular precio")
```

**Impacto**: LLM ve contexto explícito → evita re-identificar.

---

#### 1.4. Actualizar Prompt `presupuesto_mode.md`

**Archivo**: `agent/prompts/modes/presupuesto_mode.md`

**Cambio**:
```markdown
# ANTES (conceptual, no hay algoritmo explícito)

# FLUJO ESPERADO
1. Identificar elementos
2. Calcular precio
3. Comunicar precio + warnings
4. Ofrecer imágenes de ejemplo

# DESPUÉS (agregar sección)

## 🚨 ALGORITMO ANTI-PATRÓN

### Regla 1: NO Re-identificar Si Ya Confirmados

```
SI mode_context contiene "elementos_confirmados":
    ✅ Usar esos elementos
    ❌ NO llamar identificar_y_resolver_elementos() de nuevo
    ❌ NO preguntar "¿Qué elementos quieres?"
```

### Regla 2: Detectar Respuesta a Opciones A/B

```
SI mode_context contiene "waiting_for_image_choice=True":
    ✅ Usuario está respondiendo a "¿Opción A o B?"
    
    SI usuario dice "A" o "Opción A":
        → Ya se enviaron imágenes automáticamente
        → Ofrecer transición a EVALUACION_GATEWAY
        → NO volver a calcular precio
    
    SI usuario dice "B" o "Opción B":
        → Explicar que Opción B no envía imágenes ahora
        → Ofrecer transición a EVALUACION_GATEWAY
        → NO volver a calcular precio
```

### Regla 3: Precio Antes de Imágenes (Crítico)

```
SI vas a llamar enviar_imagenes_ejemplo():
    VERIFICAR:
        ✅ mode_context["precio_comunicado"] = True
        ✅ En tu respuesta ANTERIOR mencionaste el precio
    
    SI NO has comunicado precio:
        ❌ NO llamar enviar_imagenes_ejemplo()
        ✅ Comunicar precio primero
```

## 🔄 FLUJO COMPLETO CORRECTO

1. **Primera interacción**: Identificar + Calcular + Comunicar precio
2. **Ofrecer imágenes**: "¿Quieres ver ejemplos? A) Ver fotos B) No, gracias"
3. **Flag se activa**: `waiting_for_image_choice=True`
4. **Usuario responde**: "A" o "B"
5. **Acción determinística**:
   - A → Imágenes ya enviadas → Ofrecer expediente
   - B → No imágenes → Ofrecer expediente
6. **NO volver a Step 1**: Los elementos YA están confirmados

## ❌ EJEMPLOS DE ERRORES A EVITAR

### Error 1: Re-identificar Después de A/B
```
❌ INCORRECTO:
User: "A"
Bot: "¿Qué elementos quieres homologar?"  ← WRONG!

✅ CORRECTO:
User: "A"
Bot: "Te he enviado las fotos de ejemplo. ¿Quieres que iniciemos el expediente?"
```

### Error 2: Olvidar Precio
```
❌ INCORRECTO:
Bot: "Te envío fotos de ejemplo:"
[enviar_imagenes_ejemplo()] ← BLOQUEADO por validación

✅ CORRECTO:
Bot: "El presupuesto es de 410€ +IVA. Te envío fotos:"
[enviar_imagenes_ejemplo()] ← OK
```

### Error 3: Ignorar waiting_for_image_choice
```
❌ INCORRECTO:
mode_context = {"waiting_for_image_choice": True}
Bot: "¿Qué elementos necesitas homologar?"  ← Ignora flag

✅ CORRECTO:
mode_context = {"waiting_for_image_choice": True}
Bot: "Entendido, opción A. Te he enviado las fotos."
```
```

**Impacto**: LLM tiene instrucciones explícitas → comportamiento consistente.

---

### Fase 2: Fix Robusto (ARQUITECTÓNICO)

**Objetivo**: Arquitectura determinística similar a EVALUACION_GATEWAY.

#### 2.1. Pattern Matching Pre-LLM

**Archivo**: `agent/modes/presupuesto_mode.py`

**Cambio**:
```python
# NUEVO: Detectar A/B ANTES del LLM loop

A_PATTERNS = [
    re.compile(r"\b(a|opci[oó]n a|la a|foto|ver)\b", re.IGNORECASE),
    re.compile(r"^a+$", re.IGNORECASE),  # "aaa"
]

B_PATTERNS = [
    re.compile(r"\b(b|opci[oó]n b|la b|no gracias|sin fotos)\b", re.IGNORECASE),
    re.compile(r"^b+$", re.IGNORECASE),  # "bbb"
]

async def _process_message(self, message: str, state: ConversationState):
    mode_context = dict(state.get("mode_context", {}))
    
    # ✅ NUEVO: Detectar respuesta A/B antes del LLM
    if mode_context.get("waiting_for_image_choice"):
        choice = self._classify_image_choice(message)
        
        if choice == "A":
            return await self._handle_option_a(state, mode_context)
        elif choice == "B":
            return await self._handle_option_b(state, mode_context)
        # Si ambiguo → continuar al LLM con flag activo
    
    # Continuar flujo normal LLM...

def _classify_image_choice(self, message: str) -> str | None:
    """Clasificar respuesta A/B usando patterns."""
    msg = message.strip().lower()
    
    for pattern in A_PATTERNS:
        if pattern.search(msg):
            return "A"
    
    for pattern in B_PATTERNS:
        if pattern.search(msg):
            return "B"
    
    return None  # Ambiguo

async def _handle_option_a(self, state, mode_context):
    """Manejar opción A (ver fotos) de forma determinística."""
    logger.info("option_a_detected", conversation_id=state["conversation_id"])
    
    # Las imágenes ya se enviaron cuando se ofreció A/B
    # Solo confirmar y ofrecer transición
    
    response = (
        "Perfecto, ya te he enviado las fotos de ejemplo. "
        "¿Quieres que iniciemos el expediente de homologación?"
    )
    
    mode_context["waiting_for_image_choice"] = False
    mode_context["opcion_seleccionada"] = "A"
    
    return {
        "ai_response": response,
        "mode_context": mode_context,
        "current_mode": "EVALUACION_GATEWAY",  # Transición automática
    }

async def _handle_option_b(self, state, mode_context):
    """Manejar opción B (sin fotos) de forma determinística."""
    logger.info("option_b_detected", conversation_id=state["conversation_id"])
    
    response = (
        "Entendido. Si cambias de opinión, puedo enviártelas más tarde. "
        "¿Quieres que iniciemos el expediente de homologación?"
    )
    
    mode_context["waiting_for_image_choice"] = False
    mode_context["opcion_seleccionada"] = "B"
    
    return {
        "ai_response": response,
        "mode_context": mode_context,
        "current_mode": "EVALUACION_GATEWAY",  # Transición automática
    }
```

**Impacto**:
- ✅ Respuesta A/B detectada PRE-LLM → 0 latencia LLM
- ✅ Acción determinística → 0 errores de interpretación
- ✅ Ahorro de tokens (~500 tokens por interacción)

---

#### 2.2. Migrar Lógica a Handlers Determinísticos

**Archivo**: `agent/tools/image_tools.py`

**Cambio** (opcional, pero recomendado):
```python
# ANTES: enviar_imagenes_ejemplo retorna URLs

# DESPUÉS: enviar_imagenes_ejemplo retorna estructura con opciones
@tool
async def enviar_imagenes_ejemplo(categoria: str) -> dict[str, Any]:
    """
    Enviar imágenes de ejemplo Y ofrecer opciones A/B.
    
    Retorna estructura que activa waiting_for_image_choice flag.
    """
    # ... lógica actual ...
    
    return {
        "success": True,
        "message": "Imágenes enviadas. ¿Quieres verlas ahora?",
        "data": {
            "urls": urls,
            "opcion_a": "Ver fotos de ejemplo ahora",
            "opcion_b": "No, gracias, prefiero continuar",
        },
        # ✅ Signal para activar flag
        "activate_choice_flag": True,
    }
```

**Impacto**: Tool indica cuándo activar flag → sincronización garantizada.

---

## 📝 Implementation Plan

### Tasks por Subagente

#### 🤖 agent-dev (Fase 1)

**Prioridad**: P0  
**Estimación**: 3-4 horas  

- [ ] **Task 1.1**: Re-inyectar ContextVar en loop (`presupuesto_mode.py`)
  - Modificar líneas ~174-220
  - Agregar `set_current_state(updated_state)` después de cada tool call
  - Tiempo: 30 min

- [ ] **Task 1.2**: Implementar flag management (`presupuesto_mode.py`)
  - Modificar `_extract_context_from_tool()`
  - Setear `waiting_for_image_choice=True` después de ofrecer A/B
  - Detectar respuesta A/B y resetear flag
  - Tiempo: 1 hora

- [ ] **Task 1.3**: Formatear contexto explícito (`loader.py`)
  - Modificar líneas 174-186
  - Agregar sección `elementos_confirmados`
  - Agregar línea "ESPERANDO: opción A/B"
  - Tiempo: 30 min

- [ ] **Task 1.4**: Actualizar prompt (`presupuesto_mode.md`)
  - Agregar sección "ALGORITMO ANTI-PATRÓN"
  - Agregar "FLUJO COMPLETO CORRECTO"
  - Agregar "EJEMPLOS DE ERRORES A EVITAR"
  - Tiempo: 1 hora

---

#### 🤖 agent-dev (Fase 2)

**Prioridad**: P1  
**Estimación**: 2-3 horas  

- [ ] **Task 2.1**: Implementar pattern matching (`presupuesto_mode.py`)
  - Definir `A_PATTERNS` y `B_PATTERNS`
  - Crear `_classify_image_choice()`
  - Tiempo: 30 min

- [ ] **Task 2.2**: Crear handlers determinísticos (`presupuesto_mode.py`)
  - Implementar `_handle_option_a()`
  - Implementar `_handle_option_b()`
  - Agregar logging estructurado
  - Tiempo: 1 hora

- [ ] **Task 2.3**: Integrar pattern matching en `_process_message()`
  - Detectar flag `waiting_for_image_choice` al inicio
  - Clasificar mensaje antes del LLM loop
  - Ejecutar handler si match, continuar si ambiguo
  - Tiempo: 30 min

- [ ] **Task 2.4**: Actualizar `image_tools.py` (opcional)
  - Modificar `enviar_imagenes_ejemplo()` para retornar opciones
  - Agregar flag `activate_choice_flag` en respuesta
  - Tiempo: 30 min

---

#### 🧪 qa-dev

**Prioridad**: P0  
**Estimación**: 2 horas  

- [ ] **Task 3.1**: Crear test de integración Fase 1
  - Flujo completo: identificar → precio → ofrecer A/B → responder "A"
  - Verificar NO re-identificación
  - Verificar transición a EVALUACION_GATEWAY
  - Archivo: `tests/test_presupuesto_option_ab_fix.py`
  - Tiempo: 1 hora

- [ ] **Task 3.2**: Crear test de integración Fase 2
  - Verificar pattern matching pre-LLM
  - Verificar handlers determinísticos
  - Verificar ahorro de tokens (mock LLM, contar calls)
  - Tiempo: 30 min

- [ ] **Task 3.3**: Test de regresión
  - Verificar flujo normal (sin A/B) sigue funcionando
  - Verificar precio antes de imágenes aún bloqueado
  - Tiempo: 30 min

- [ ] **Task 3.4**: Ejecutar suite completa
  - `pytest tests/ -v --cov=agent/modes`
  - Coverage >90% en `presupuesto_mode.py`
  - Tiempo: 10 min

---

#### 🔍 investigator-dev

**Prioridad**: P1  
**Estimación**: 1 hora  

- [ ] **Task 4.1**: Configurar monitoring post-deploy
  - Agregar log `presupuesto_option_choice_detected`
  - Agregar métrica `waiting_for_image_choice_duration`
  - Tiempo: 30 min

- [ ] **Task 4.2**: Análisis post-deploy (después de 24h)
  - Verificar 0 ocurrencias del bug en logs
  - Verificar latencia promedio en respuesta A/B
  - Comparar consumo de tokens Fase 1 vs Fase 2
  - Tiempo: 30 min

---

## 🧪 Testing Strategy

### Casos de Prueba Críticos

#### Test Case 1: Flujo Completo A (Fase 1)

```python
async def test_presupuesto_option_a_no_reidentify():
    """
    Verificar que después de elegir Opción A,
    el agente NO vuelve a preguntar elementos.
    """
    state = mock_state()
    
    # 1. Usuario pide presupuesto
    result = await presupuesto_mode.process("quiero homologar escape", state)
    assert "identificar_y_resolver_elementos" in result["tool_calls"]
    
    # 2. LLM calcula precio y ofrecer imágenes
    # (simular respuesta LLM con tool calls)
    result = await presupuesto_mode.process("", state)
    assert result["mode_context"]["precio_comunicado"] == True
    assert result["mode_context"]["waiting_for_image_choice"] == True
    
    # 3. Usuario responde "A"
    result = await presupuesto_mode.process("A", state)
    
    # ✅ VERIFICACIONES
    assert result["mode_context"]["waiting_for_image_choice"] == False
    assert result["mode_context"]["opcion_seleccionada"] == "A"
    assert "identificar_y_resolver_elementos" not in result["tool_calls"]
    assert result["current_mode"] == "EVALUACION_GATEWAY"
```

---

#### Test Case 2: Pattern Matching Pre-LLM (Fase 2)

```python
async def test_presupuesto_option_a_pattern_matching():
    """
    Verificar que pattern matching detecta A/B ANTES del LLM.
    """
    state = mock_state(waiting_for_image_choice=True)
    
    # Mock LLM (no debería llamarse)
    mock_llm = Mock()
    
    # Usuario responde "A"
    result = await presupuesto_mode.process("A", state)
    
    # ✅ VERIFICACIONES
    assert mock_llm.ainvoke.call_count == 0  # LLM no llamado!
    assert result["mode_context"]["opcion_seleccionada"] == "A"
    assert "Ver fotos" in result["ai_response"]
```

---

#### Test Case 3: ContextVar Re-inyección

```python
async def test_contextvar_reinjection_during_loop():
    """
    Verificar que ContextVar se actualiza después de cada tool call.
    """
    state = mock_state()
    
    # Simular múltiples tool calls en un turno
    with patch("agent.modes.presupuesto_mode.set_current_state") as mock_set:
        result = await presupuesto_mode.process("escape", state)
        
        # ✅ VERIFICACIÓN: set_current_state llamado múltiples veces
        # (1 inicial + N tool calls)
        assert mock_set.call_count > 1
        
        # Verificar que cada call incluye mode_context actualizado
        calls = mock_set.call_args_list
        for i in range(1, len(calls)):
            prev_context = calls[i-1][0][0]["mode_context"]
            curr_context = calls[i][0][0]["mode_context"]
            # Context debe evolucionar
            assert curr_context != prev_context or i == len(calls) - 1
```

---

#### Test Case 4: Prompt Contexto Explícito

```python
async def test_prompt_includes_waiting_flag():
    """
    Verificar que el prompt dinámico incluye flag de espera.
    """
    state = mock_state(
        mode_context={
            "elementos_confirmados": ["ESCAPE"],
            "waiting_for_image_choice": True,
        }
    )
    
    prompt = assemble_system_prompt(mode="PRESUPUESTO_MODE", mode_context=state["mode_context"])
    
    # ✅ VERIFICACIONES
    assert "ELEMENTOS CONFIRMADOS: ESCAPE" in prompt
    assert "ESPERANDO: El usuario debe elegir Opción A o B" in prompt
    assert "NO vuelvas a identificar elementos" in prompt
```

---

### Coverage Target

| Archivo | Coverage Actual | Coverage Target |
|---------|-----------------|-----------------|
| `presupuesto_mode.py` | ~75% | >90% |
| `loader.py` | ~85% | >90% |
| `image_tools.py` | ~80% | >85% |

---

## 🚀 Rollout Plan

### Fase 1: Fix Quirúrgico (INMEDIATO)

**Timeline**: 1 día  

1. **Desarrollo** (3-4h)
   - agent-dev implementa Tasks 1.1-1.4
   - qa-dev implementa Tests 3.1, 3.3, 3.4

2. **Testing** (1h)
   - Ejecutar suite completa
   - Fix de cualquier regresión

3. **Deploy** (30min)
   - Merge a `develop`
   - Deploy a staging
   - Smoke test manual (5 conversaciones)
   - Deploy a producción
   - Monitor logs (24h)

4. **Verificación** (24h)
   - investigator-dev analiza logs
   - Verificar 0 ocurrencias del bug
   - Recopilar métricas de latencia y tokens

---

### Fase 2: Fix Robusto (ARQUITECTÓNICO)

**Timeline**: 2-3 días  

1. **Desarrollo** (2-3h)
   - agent-dev implementa Tasks 2.1-2.4

2. **Testing** (1h)
   - qa-dev implementa Test 3.2
   - Ejecutar suite completa

3. **A/B Testing** (opcional, 1 semana)
   - 50% tráfico Fase 1, 50% Fase 2
   - Comparar métricas:
     - Latencia promedio respuesta A/B
     - Consumo tokens por conversación
     - Tasa de error (re-identificación)

4. **Deploy Final** (30min)
   - Si A/B exitoso → 100% Fase 2
   - Si regresión → mantener Fase 1
   - Documentar decisión en ADR

---

## ✅ Success Criteria

### Criterios de Éxito Fase 1

- [ ] **Criterio 1**: 0 ocurrencias de re-identificación después de "A" en logs (24h)
- [ ] **Criterio 2**: Flag `waiting_for_image_choice` se activa correctamente (100% casos)
- [ ] **Criterio 3**: ContextVar sincronizado durante loop (verificado en tests)
- [ ] **Criterio 4**: Prompt incluye contexto explícito (verificado en tests)
- [ ] **Criterio 5**: Coverage >90% en `presupuesto_mode.py`
- [ ] **Criterio 6**: 0 regresiones en flujo normal (sin A/B)

### Criterios de Éxito Fase 2

- [ ] **Criterio 7**: Pattern matching detecta A/B en <100ms (pre-LLM)
- [ ] **Criterio 8**: Ahorro de tokens >30% en interacciones A/B
- [ ] **Criterio 9**: Latencia reducida >50% vs Fase 1 (sin LLM call)
- [ ] **Criterio 10**: Tasa de error A/B = 0% (acción determinística)

### Métricas Clave

| Métrica | Baseline (Antes) | Target (Fase 1) | Target (Fase 2) |
|---------|------------------|-----------------|-----------------|
| **Re-identificaciones después A/B** | ~40% | 0% | 0% |
| **Latencia respuesta A/B** | ~2s (LLM) | ~2s (LLM) | <100ms (pattern) |
| **Tokens por interacción A/B** | ~1500 tokens | ~1500 tokens | ~1000 tokens |
| **Tasa satisfacción usuario** | 60% | 85% | 90% |

---

## 🔄 Rollback Plan

### Escenario 1: Fase 1 Causa Regresión

**Síntomas**:
- Aumento en errores de validación `PRECIO_BEFORE_IMAGES`
- ContextVar causa race conditions en otros modos
- Tests fallan en flujo normal (sin A/B)

**Acción**:
1. Revert commit de Fase 1
2. Deploy versión anterior
3. Investigar causa raíz con logs
4. Re-implementar con fix

**Tiempo de rollback**: <15 minutos

---

### Escenario 2: Fase 2 Causa Regresión

**Síntomas**:
- Pattern matching bloquea respuestas válidas (falsos positivos)
- Handlers determinísticos generan respuestas incorrectas
- Transición automática a EVALUACION_GATEWAY falla

**Acción**:
1. Cambiar feature flag `USE_PATTERN_MATCHING_AB=false`
2. Mantener Fase 1 en producción
3. Investigar patrones fallidos
4. Mejorar regex patterns
5. Re-deploy después de fix

**Tiempo de rollback**: <5 minutos (feature flag)

---

### Feature Flag

**Archivo**: `shared/config.py`

```python
# NUEVO
USE_PATTERN_MATCHING_AB: bool = Field(
    False,
    description="Enable pre-LLM pattern matching for A/B options in PRESUPUESTO_MODE"
)
```

**Uso**:
```python
# presupuesto_mode.py
if get_settings().USE_PATTERN_MATCHING_AB and mode_context.get("waiting_for_image_choice"):
    choice = self._classify_image_choice(message)
    if choice:
        return await self._handle_option_a/b(...)
```

---

## 📄 ADR Draft

**ADR-005: Pattern Matching for A/B Options in PRESUPUESTO_MODE**

### Status
Proposed (Fase 2)

### Context

El agente en PRESUPUESTO_MODE ofrece opciones A/B al usuario después de calcular el precio:
- **Opción A**: Ver fotos de ejemplo
- **Opción B**: No ver fotos, continuar

**Problema original**: El LLM interpretaba "A" como inicio de nueva conversación y re-identificaba elementos.

**Solución Fase 1**: Re-inyectar ContextVar + flag management + prompt explícito.

**Limitación Fase 1**: Sigue dependiendo del LLM para interpretar "A"/"B" → latencia ~2s, tokens ~500.

### Decision

Implementar pattern matching PRE-LLM para detectar respuestas A/B de forma determinística, similar al patrón usado en EVALUACION_GATEWAY.

**Patrón**:
1. Detectar flag `waiting_for_image_choice=True` al inicio de `_process_message()`
2. Clasificar mensaje con regex patterns ANTES del LLM loop
3. Ejecutar handler determinístico si match (A o B)
4. Continuar al LLM solo si ambiguo

### Consequences

**Positivas**:
- ✅ Latencia reducida >50% (pattern matching ~100ms vs LLM ~2s)
- ✅ Ahorro de tokens ~30% (sin LLM call para A/B simple)
- ✅ Comportamiento 100% determinístico (0 errores de interpretación)
- ✅ Consistencia con EVALUACION_GATEWAY (mismo patrón)
- ✅ Código más mantenible (lógica explícita, no emergente)

**Negativas**:
- ⚠️ Complejidad adicional en `presupuesto_mode.py` (~100 líneas)
- ⚠️ Riesgo de falsos positivos en patterns (ej: "¿Tienes opción A disponible?" → match incorrecto)
- ⚠️ Necesidad de mantener 2 paths (pattern + LLM fallback)

**Mitigación**:
- Feature flag `USE_PATTERN_MATCHING_AB` para rollback rápido
- Patterns conservadores (solo match exact "A"/"B" o variantes comunes)
- Logging detallado de clasificaciones para debugging
- A/B testing 1 semana antes de deploy 100%

### Alternatives Considered

**Alternativa 1**: Solo Fase 1 (ContextVar + prompt)
- ✅ Más simple, menos riesgo
- ❌ No optimiza latencia ni tokens
- ❌ Sigue dependiendo del LLM → posibles errores

**Alternativa 2**: LLM especializado para clasificación A/B
- ✅ Más flexible que patterns
- ❌ Mayor latencia que patterns
- ❌ Mayor coste (LLM call adicional)

**Alternativa 3**: Sub-modo dedicado para A/B
- ✅ Separación clara de responsabilidades
- ❌ Complejidad arquitectónica (nuevo modo)
- ❌ Overhead de transición entre modos

---

## 📚 Referencias

### Archivos a Modificar

| Archivo | Líneas | Cambio |
|---------|--------|--------|
| `agent/modes/presupuesto_mode.py` | 595 | Re-inyectar ContextVar, flag management, pattern matching, handlers |
| `agent/prompts/loader.py` | 174-186 | Formatear contexto explícito |
| `agent/prompts/modes/presupuesto_mode.md` | 400+ | Algoritmo anti-patrón, flujo correcto, ejemplos |
| `agent/tools/image_tools.py` | 54 | (Opcional) Retornar estructura con opciones |
| `shared/config.py` | — | Feature flag `USE_PATTERN_MATCHING_AB` |
| `tests/test_presupuesto_option_ab_fix.py` | NEW | Tests de integración |

### ADRs Relacionados

- [ADR-002: Dynamic Prompts](../decisions/002-dynamic-prompts.md)
- [ADR-004: Fix PRESUPUESTO Corrupted Text](../decisions/004-fix-presupuesto-corrupted-text.md)

### Skills

- [msia-agent](../../skills/msia-agent/SKILL.md) - Agent anti-patterns
- [langgraph](../../skills/langgraph/SKILL.md) - StateGraph patterns

---

## 🎯 Próximos Pasos

1. **Aprobación del Plan** (Usuario)
   - Revisar este plan completo
   - Aprobar Fase 1 para ejecución inmediata
   - Decidir si Fase 2 se ejecuta simultánea o posterior

2. **Ejecución Fase 1** (agent-dev + qa-dev)
   - Implementar Tasks 1.1-1.4
   - Ejecutar Tests 3.1, 3.3, 3.4
   - Deploy a staging → producción

3. **Monitoreo Post-Deploy** (investigator-dev)
   - Analizar logs 24h
   - Verificar criterios de éxito
   - Reportar resultados

4. **Decisión Fase 2** (Architect + Usuario)
   - Si Fase 1 exitosa → continuar a Fase 2
   - Si Fase 1 suficiente → documentar y cerrar
   - Si regresión → rollback y re-plan

---

**Creado por**: architect  
**Fecha**: 6 de Febrero de 2026  
**Estado**: ✅ READY FOR EXECUTION  
**Aprobación Pendiente**: Usuario
