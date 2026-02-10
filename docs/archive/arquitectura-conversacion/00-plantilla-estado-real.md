# Arquitectura de Conversación - Estado: [NOMBRE_DEL_ESTADO]

## 🎯 Propósito y Alcance

### Objetivo Principal
[Descripción clara de qué debe lograr este estado]

### Objetivos Secundarios
- [Objetivo adicional 1]
- [Objetivo adicional 2]

### Definición del Éxito
[Condición que indica que se puede transicionar al siguiente estado]

---

## 🔄 Contexto de Navegación

### Estados Predecesores

| Estado Origen | Activador de Transición | Condiciones |
|---------------|------------------------|-------------|
| [Estado A] | [Evento/acción que dispara] | [Condiciones] |

### Estados Sucesores

| Estado Destino | Activador de Transición | Condiciones |
|----------------|------------------------|-------------|
| [Estado X] | [Evento/acción que dispara] | [Condiciones] |

---

## 🎬 Activadores de Entrada

### Eventos que Inician este Estado

1. **[Nombre del Evento]**
   - **Descripción**: [Qué sucede]
   - **Origen**: [Usuario / Sistema / Evento externo]
   - **Datos asociados**: [Qué información acompaña al evento]

### Condiciones de Entrada

- [Condición 1]
- [Condición 2]

---

## 🛠️ Capacidades del Agente

### Herramientas Disponibles

#### Herramientas de Consulta
| Herramienta | Propósito | Datos Requeridos | Datos Producidos |
|-------------|-----------|------------------|------------------|
| [Nombre] | [Para qué sirve] | [Qué necesita] | [Qué devuelve] |

#### Herramientas de Acción
| Herramienta | Propósito | Efecto en el Estado | Efecto en el Sistema |
|-------------|-----------|---------------------|---------------------|
| [Nombre] | [Para qué sirve] | [Cambia algo del estado actual] | [Persiste/afecta algo externo] |

#### Herramientas de Transición
| Herramienta | Propósito | Estado Resultante | Condiciones |
|-------------|-----------|-------------------|-------------|
| [Nombre] | [Para qué sirve] | [A dónde lleva] | [Cuándo puede usarse] |

### Herramientas Restringidas
[Herramientas que NO están disponibles en este estado y por qué]

| Herramienta | Razón de Restricción | Alternativa Disponible |
|-------------|---------------------|------------------------|
| [Nombre] | [Por qué no se puede usar] | [Qué usar en su lugar] |

---

## 📊 Datos del Estado

### Datos de Entrada

| Dato | Tipo | Obligatorio | Fuente | Fallback si Ausente | Impacto |
|------|------|-------------|--------|---------------------|---------|
| [Nombre] | [Tipo] | [Sí/No] | [De dónde viene] | [Qué pasa si no llega] | [Bloqueante/Warning/Continúa] |

**Nota sobre Contrato de Contexto**: Si un dato obligatorio no llega, el estado debe:
- [ ] Fallar inmediatamente
- [ ] Intentar recuperar (¿cómo?)
- [ ] Usar valor por defecto: [valor]
- [ ] Escalar a humano

### Datos de Salida

| Dato | Tipo | Obligatorio | Destino | Descripción |
|------|------|-------------|---------|-------------|
| [Nombre] | [Tipo] | [Sí/No] | [Adónde va] | [Qué representa] |

### Datos Temporales

| Dato | Tipo | Duración | Descripción |
|------|------|----------|-------------|
| [Nombre] | [Tipo] | [Durante este estado / Hasta transición] | [Qué representa] |

### Estado Interno

| Variable | Valores Posibles | Significado | Transiciones Internas |
|----------|-------------------|-------------|----------------------|
| [Nombre] | [Valor1, Valor2...] | [Qué significa cada valor] | [Cambia comportamiento cómo] |

---

## 📜 Reglas de Negocio

### Reglas de Entrada

1. **[Nombre de la Regla]**
   - **Condición**: [Qué debe cumplirse]
   - **Acción si falla**: [Qué hacer si no se cumple]
   - **Mensaje al usuario**: [Qué comunicar]

### Reglas de Ejecución

1. **[Nombre de la Regla]**
   - **Descripción**: [Qué restricción aplica]
   - **Prioridad**: [Alta/Media/Baja]
   - **Consecuencia de incumplimiento**: [Qué sucede si se viola]

### Reglas de Salida

1. **[Nombre de la Regla]**
   - **Condición de completitud**: [Qué debe estar listo]
   - **Validación requerida**: [Qué verificaciones hacer]
   - **Rollback posible**: [Si se puede deshacer o no]

---

## 🚨 Estrategia de Recuperación de Errores

### Errores de NLU (Modelo no entiende intención)

| Síntoma | Umbral | Acción | Mensaje al Usuario |
|---------|--------|--------|-------------------|
| [Ej: Intent confidence < 0.7] | [N intentos] | [Escalar/Reintentar/ Default] | ["No entendí bien..."] |

**⚠️ GAP DOCUMENTADO**: [Si no hay manejo definido, describir el gap]

### Errores de Herramienta (API/DB falla)

| Síntoma | Umbral | Acción | Mensaje al Usuario |
|---------|--------|--------|-------------------|
| [Ej: Timeout 5s] | [N reintentos] | [Backoff/Escalar] | ["Problema técnico..."] |

### Errores de Validación (Dato inválido lógicamente)

| Síntoma | Umbral | Acción | Mensaje al Usuario |
|---------|--------|--------|-------------------|
| [Ej: Email mal formado] | [N intentos] | [Re-preguntar/Escalar] | ["Formato incorrecto..."] |

**Nota**: Ver también [Política de Reintentos](#política-de-reintentos)

---

## 🔄 Política de Reintentos

### Reintentos del Sistema (Técnicos)

| Tipo de Fallo | Mecanismo Actual | Límite | Acción al Alcanzar Límite |
|---------------|------------------|--------|--------------------------|
| Validación de constraints | `MAX_VALIDATION_RETRIES` | 3 | Inyectar error al LLM, forzar regeneración |
| Conexión Redis | Exponential backoff | ∞ (loop) | Log error, continuar intentando |
| Llamada a herramienta | `handle_tool_errors` decorator | 1 (por defecto) | Mensaje genérico al usuario |
| Timeout Ollama | `timeout=5.0` en cliente | 1 | Fallback a OpenRouter |

### Reintentos del Usuario (Validaciones)

| Tipo de Error | Contador en Estado | Límite | Acción al Alcanzar Límite |
|---------------|-------------------|--------|--------------------------|
| Dato inválido | `retry_count` | `MAX_RETRIES_PER_STEP = 3` | **⚠️ GAP**: No hay acción definida, solo contador |
| NLU ambiguo | No hay contador | ∞ | Bucle potencial |
| Rechazo de propuesta | No hay contador | ∞ | Bucle potencial |

**🔴 CRÍTICO**: El sistema tiene `MAX_RETRIES_PER_STEP = 3` pero no especifica qué sucede después. ¿Escalación forzada? ¿Mensaje diferente? ¿Cambio de estrategia?

---

## ⏱️ Timeouts y Expiración

### Timeouts de Actividad del Usuario

| Inactividad | Comportamiento Actual | Comportamiento Deseado | Gap |
|-------------|----------------------|------------------------|-----|
| 5 minutos | Sin acción | ??? | **⚠️ NO IMPLEMENTADO** |
| 20 minutos | Sin acción | ??? | **⚠️ NO IMPLEMENTADO** |
| 24 horas | Sesión expira (Redis TTL) | Persistir estado | ✅ Implementado |

**🔴 CRÍTICO**: No hay mecanismo de "nudge" ni cierre por inactividad. El estado persiste indefinidamente esperando al usuario.

### Timeouts Técnicos

| Operación | Timeout Actual | Acción en Timeout |
|-----------|---------------|-------------------|
| Llamada Ollama | 5 segundos | Fallback a OpenRouter |
| Conexión Redis | Exponential backoff | Reintento indefinido |
| Webhook Chatwoot | ??? | ??? |

---

## 🎭 Trazas de Conversación

### Traza 1: Flujo Principal Exitoso

```
Usuario: [Mensaje que activa el estado]
Agente: [Respuesta del agente]
[...]
Usuario: [Mensaje que completa el estado]
Agente: [Confirmación + Transición al siguiente estado]
```
**Resultado**: [Qué se logra]

### Traza 2: Recuperación de Error de Validación

```
Usuario: [Dato inválido]
Agente: [Detección del error + Mensaje de recuperación]
Usuario: [Corrección]
Agente: [Validación + Continuación]
```
**Resultado**: [Cómo se recupera]

### Traza 3: Escalación Durante el Estado

```
Usuario: [Solicitud de humano / Error persistente]
Agente: [Confirmación de escalación + Mensaje de cierre]
```
**Resultado**: [Qué sucede con el estado actual]

---

## 🚧 Permisividad de Digresiones

### ¿Permite este estado consultas off-topic?

- [ ] **ESTADO BLOQUEANTE**: El usuario DEBE responder al prompt actual. Cualquier otra cosa se rechaza o ignora.
- [ ] **ESTADO PERMISIVO**: El usuario puede hacer consultas. Se responde y se retorna al estado.

**Mecanismo Actual**:
- `consulta_durante_expediente()` permite digresiones en todos los estados
- **⚠️ GAP**: No hay estados marcados explícitamente como bloqueantes
- El prompt de fase determina si se permite o no

**Comportamiento Real Observado**:
| Estado | Bloqueante | Justificación |
|--------|------------|---------------|
| IDLE | No | Puedes preguntar lo que sea |
| COLLECT_ELEMENT_DATA (photos) | Parcial | Fotos sí, pero puedes preguntar "¿qué necesitas?" |
| COLLECT_ELEMENT_DATA (data) | Parcial | Datos primero, consultas secundarias |
| REVIEW_SUMMARY | **Sí** | Debes confirmar sí/no explícitamente |

---

## 📝 Referencias a Prompts

### Prompt de Fase Asociado
- **Archivo**: `prompts/phases/[nombre_fase].md`
- **Líneas**: ~[N] tokens
- **Contenido clave**: [Resumen de instrucciones específicas]

### Prompts Core Siempre Presentes
- `prompts/core/01_security.md` - Seguridad
- `prompts/core/02_identity.md` - Identidad
- `prompts/core/03_format_style.md` - Estilo
- `prompts/core/04_anti_patterns.md` - Anti-patrones
- `prompts/core/05_tools_efficiency.md` - Eficiencia de tools
- `prompts/core/06_escalation.md` - Escalación
- `prompts/core/07_pricing_rules.md` - Precios
- `prompts/core/08_documentation.md` - Documentación
- `prompts/core/09_fsm_awareness.md` - Conciencia FSM

---

## ⚠️ Gaps y Deuda Técnica Documentada

### Gaps Críticos (Riesgo Alto)

1. **[Nombre del Gap]**
   - **Descripción**: [Qué falta]
   - **Impacto**: [Qué puede salir mal]
   - **Ubicación en código**: [Archivo/línea si aplica]

### Deuda Técnica (Mejoras Futuras)

1. **[Descripción de mejora]**
   - **Prioridad**: [Alta/Media/Baja]
   - **Esforzo estimado**: [Pequeño/Medio/Grande]

---

## 📚 Referencias

- **Documento técnico**: [Link a documentación de implementación si existe]
- **Tests relacionados**: [Link a tests que cubren este estado]
- **Decisiones de Arquitectura**: [ADR relacionado]

---

**Estado de implementación**: [En diseño / En desarrollo / En producción / Obsoleto]

**Nota**: Esta documentación refleja el estado ACTUAL del sistema (no el ideal). Los gaps están marcados explícitamente para priorizar trabajo futuro.
