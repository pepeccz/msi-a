# Manual Testing Guide: Corrupted Text Fix

## Issue con Tests Automatizados

**Status**: Los tests automatizados en `test_presupuesto_corrupted_text_fix.py` no pueden ejecutarse actualmente debido a un problema con el import del módulo `agent` en el entorno de pytest.

**Error**: `ModuleNotFoundError: No module named 'agent.modes'`

**Causa**: El módulo `agent` requiere dependencias específicas del contenedor Docker que no están disponibles en el entorno de testing local.

**Workaround**: Testing manual siguiendo esta guía.

---

## Prerequisites

Antes de empezar, asegúrate de que el servicio agent esté corriendo y actualizado:

```bash
docker-compose restart agent
docker-compose logs agent --tail 20
```

Verifica que veas:
- ✅ "Agent consumer started"
- ✅ "Listening for messages on stream: incoming_messages"
- ❌ NO errors de inicio

---

## Test Case 1: Saludo + Intención (Bug Original)

### Caso Original del Bug

**Input vía Chatwoot**:
```
Holaaa quiero homologar el subchasis de mi moto
```

### Comportamiento ANTES del Fix

- ❌ Texto repetitivo/corrupto
- ❌ Respuestas como "¿Qué tipo de vehículo eres? ¿Qué tipo de vehículo eres?"
- ❌ Longitud excesiva (>1000 caracteres)
- ❌ Precio mencionado multiple veces o no mencionado

### Comportamiento ESPERADO Después del Fix

- ✅ Saludo breve (≤5 palabras): "¡Hola Pepe!" o similar
- ✅ Reconoce elemento: Menciona "subchasis"
- ✅ Respuesta coherente y razonable (<800 caracteres)
- ✅ NO texto repetitivo
- ✅ Flujo normal: identifica → pregunta categoría o calcula precio

### Verificación en Logs

```bash
docker-compose logs agent --tail 100 | grep -A 5 "message_received"
```

Buscar:
- `intent_detected`: Debe ser `presupuesto_directo`
- `mode`: Debe ser `PRESUPUESTO_MODE`
- `tool_called`: Debe incluir `identificar_y_resolver_elementos`
- **NO debe aparecer**: `constraint_validation_failed` o warnings sobre texto corrupto

### Checklist de Validación

- [ ] Bot saluda brevemente
- [ ] Bot reconoce "subchasis"
- [ ] Respuesta longitud <800 chars
- [ ] NO hay frases repetidas
- [ ] Flujo continúa normalmente
- [ ] Logs muestran tool calls correctos
- [ ] NO hay constraint_validation warnings

---

## Test Case 2: Saludo Formal + Intención

**Input**:
```
Buenos días, necesito homologar el escape
```

### Esperado

- ✅ Responde al saludo formal apropiadamente
- ✅ Identifica "escape"
- ✅ Proporciona precio o pregunta por categoría de vehículo
- ✅ Respuesta coherente

### Checklist

- [ ] Bot responde "Buenos días" o similar
- [ ] Bot identifica escape
- [ ] Respuesta profesional y coherente
- [ ] Longitud razonable

---

## Test Case 3: Sin Saludo (Regresión Check)

**Input**:
```
Quiero homologar el escape
```

### Esperado (NO debe cambiar respecto al comportamiento anterior)

- ✅ Identificación directa sin saludo innecesario
- ✅ Comportamiento actual se mantiene
- ✅ No agrega saludos donde no había antes

### Checklist

- [ ] Bot NO agrega saludo innecesario
- [ ] Respuesta directa y enfocada
- [ ] Identifica elemento correctamente

---

## Test Case 4: Solo Saludo (Sin Intención)

**Input**:
```
Hola
```

### Esperado

- ✅ Bot saluda de vuelta
- ✅ Pregunta qué quiere homologar
- ✅ NO llama herramientas sin intención clara
- ✅ Respuesta breve (<300 caracteres)

### Checklist

- [ ] Bot saluda
- [ ] Bot pregunta por intención
- [ ] NO hay tool calls innecesarios
- [ ] Respuesta concisa

---

## Test Case 5: Max Tokens Suficiencia

**Input**:
```
Quiero homologar escape, manillar y suspensión delantera en mi moto
```

### Esperado

- ✅ Respuesta completa (NO truncada)
- ✅ Precio de todos los elementos
- ✅ Warnings comunicados (si aplican)
- ✅ Opciones presentadas (fotos, iniciar expediente)

### Verificación en Logs

```bash
docker-compose logs agent --tail 100 | grep "completion_tokens"
```

Verificar que `completion_tokens` < 2900 (dentro del límite de 3000)

### Checklist

- [ ] Todos los elementos mencionados
- [ ] Precio total calculado
- [ ] Warnings presentados
- [ ] Opciones claras al usuario
- [ ] Respuesta NO truncada

---

## Test Case 6: Respuesta Larga con Múltiples Elementos

**Input**:
```
Holaaa, tengo una moto custom y quiero homologar el escape racing, el manillar alto, la suspensión delantera reforzada y las luces LED delanteras
```

### Esperado

- ✅ Saludo breve
- ✅ Identifica TODOS los elementos o pregunta por clarificaciones
- ✅ Respuesta organizada y estructurada
- ✅ NO supera max_tokens (3000)
- ✅ NO texto corrupto/repetitivo

### Checklist

- [ ] Bot saluda brevemente
- [ ] Bot procesa todos los elementos
- [ ] Respuesta bien estructurada (listas, bullets)
- [ ] NO hay texto repetitivo
- [ ] Longitud reasonable (<1500 chars)

---

## Verificación de Constraint Validation

### Log Pattern a Buscar

```bash
docker-compose logs agent --tail 200 | grep "constraint"
```

### Esperado DESPUÉS del Fix

**NO debe aparecer** para respuestas válidas:
- ❌ `constraint_validation_triggered`
- ❌ `constraint_check: failed`
- ❌ `regenerating_response`

**SÍ puede aparecer** para respuestas inválidas (comportamiento correcto):
- ✅ `constraint_validation_triggered` solo si la respuesta es realmente inválida
- ✅ `constraint_check: passed` para respuestas válidas

---

## Comparativa Antes/Después

### Antes del Fix

**Problema 1**: max_tokens=1500 era insuficiente
- Respuestas truncadas
- Información incompleta

**Problema 2**: Constraint validation en rol "user" causaba loops
- Regeneración infinita
- Texto corrupto/repetitivo

**Problema 3**: Core identity prompt no manejaba saludos
- Respuestas excesivamente verbosas
- Saludos repetitivos

**Problema 4**: PRESUPUESTO_MODE sin guía de primera interacción
- Comportamiento inconsistente
- Mezcla de saludos y contenido

### Después del Fix

**Fix 1**: max_tokens=3000
- ✅ Respuestas completas
- ✅ Suficiente espacio para múltiples elementos + warnings

**Fix 2**: Constraint validation en rol "system"
- ✅ NO interfiere con flujo normal
- ✅ Solo actúa como guardrail pasivo

**Fix 3**: Core identity prompt actualizado
- ✅ Saludos breves y naturales
- ✅ Balance correcto saludo/contenido

**Fix 4**: PRESUPUESTO_MODE prompt mejorado
- ✅ Guía clara para primera interacción
- ✅ Saludos apropiados según contexto

---

## Métricas de Éxito

### Criterios de Aceptación

Para considerar el fix exitoso, TODOS estos deben cumplirse:

1. **Longitud de Respuesta**
   - Inicial: <800 caracteres
   - Con múltiples elementos: <1500 caracteres
   - NUNCA >2000 caracteres para casos normales

2. **Saludos**
   - Presentes cuando el user saluda
   - ≤5 palabras de saludo
   - NO repetitivos

3. **Coherencia**
   - NO frases repetidas
   - NO texto corrupto
   - Estructura lógica

4. **Funcionalidad**
   - Identificación de elementos funciona
   - Tool calls apropiados
   - Flujo continúa sin bloquearse

5. **Performance**
   - completion_tokens <3000
   - Respuestas completas (NO truncadas)
   - Tiempo de respuesta <5 segundos

---

## Issues a Reportar

Si encuentras alguno de estos síntomas, reportar INMEDIATAMENTE:

### 🔴 Crítico (Rollback necesario)

- Texto corrupto/repetitivo sigue ocurriendo
- Bot no responde o se bloquea
- Errores 500 en el servicio
- Loops infinitos de regeneración

### 🟠 Alto (Fix needed)

- Saludos excesivamente largos (>10 palabras)
- Respuestas truncadas (información incompleta)
- Tool calls no se ejecutan
- constraint_validation se dispara incorrectamente

### 🟡 Medio (Observar)

- Saludos ligeramente más largos de lo esperado
- Respuestas cerca del límite de tokens (>2500)
- Comportamiento inconsistente ocasional

### 🟢 Bajo (Documentar)

- Pequeñas variaciones en estilo de saludo
- Edge cases no cubiertos
- Sugerencias de mejora

---

## Formato de Reporte

```markdown
### [SEVERITY] Issue Title

**Test Case**: [Número del test case]
**Input**: "[input exact usado]"
**Expected**: [Comportamiento esperado]
**Actual**: [Comportamiento observado]
**Logs**: 
```
[pegar logs relevantes]
```

**Screenshots**: [Si aplica]

**Reproducible**: [Siempre / A veces / Una vez]

**Impact**: [Descripción del impacto en users]
```

---

## Aprobación Final

Para aprobar el fix completamente, confirmar:

- [x] Fix 1: max_tokens=3000 implementado
- [x] Fix 2: Constraint validation mejorado
- [x] Fix 3: Core identity prompt actualizado
- [x] Fix 4: PRESUPUESTO_MODE prompt reforzado
- [ ] Test Case 1: PASSED (saludo + intención)
- [ ] Test Case 2: PASSED (saludo formal)
- [ ] Test Case 3: PASSED (sin saludo - no regresión)
- [ ] Test Case 4: PASSED (solo saludo)
- [ ] Test Case 5: PASSED (max tokens suficiente)
- [ ] Test Case 6: PASSED (múltiples elementos)
- [ ] No constraint validation warnings en logs
- [ ] No regresiones en otros modos
- [ ] Performance acceptable (<5s response time)

---

## Notas del QA

[Agregar observaciones aquí después del testing]

**Fecha de Testing**: _______________
**Testeado por**: _______________
**Resultado**: [ ] APROBADO [ ] RECHAZADO [ ] CON OBSERVACIONES

