---
titulo: Router e intenciones del usuario
ambito: agente
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Router e intenciones del usuario

## Resumen

El **intent router** es un clasificador híbrido que determina a qué modo debe entrar el usuario basándose en su mensaje. Funciona en 2 capas:

1. **Keyword matching** (fast path) — regexes pre-compilados que detectan palabras clave
2. **LLM classification** (fallback) — si keywords no dan confianza ≥ 0.75, consulta `qwen2.5:3b` (o el modelo local configurado)

Hay **11 intents enumerados** (`UserIntent` enum), cada uno mapea a un modo sugerido vía `INTENT_TO_MODE`. El router es invocado por `router_node` en `conversation_graph.py` antes de despachar al modo.

## Escenarios

### 1. Presupuesto directo (keyword: "quiero homologar")
- CUANDO el usuario escribe "Quiero homologar un escape"
- ENTONCES regex `\b(quiero|necesito)\s+(homologar|legalizar)\b` matchea con confidence 0.90, intent → `PRESUPUESTO_DIRECTO`, modo → `PRE_EXPEDIENTE_MODE`, router despacha directo sin LLM call.

### 2. Consulta general (keyword: "qué es" / "cómo funciona")
- CUANDO el usuario escribe "¿Qué es la homologación?"
- ENTONCES regex `\b(qué es|cómo funciona|para qué)\b` matchea con confidence 0.80, intent → `CONSULTA_GENERAL`, modo → `PRE_EXPEDIENTE_MODE`.

### 3. Escalación (keyword: "persona", "humano")
- CUANDO el usuario escribe "Quiero hablar con una persona"
- ENTONCES regex `\b(persona|humano|agente|hablar con alguien)\b` matchea con confidence 0.95, intent → `ESCALAR`, modo → `ESCALATION`, router despacha a `escalation_node`.

### 4. Confirmación simple (keyword: "sí", "ok", "dale")
- CUANDO el usuario escribe "Sí" o "Dale" (respuesta corta confirmativa)
- ENTONCES regex `^\s*(sí|si|ok|dale|vale)\s*[.!?]?\s*$` matchea con confidence 0.90, intent → `CONFIRMACION`, modo → "" (context-dependent), router mantiene modo actual si precio comunicado.

### 5. Ver imágenes (keyword: "A", "ver fotos")
- CUANDO el usuario escribe "A" (en contexto de opciones A/B) o "Ver fotos de ejemplo"
- ENTONCES regex `^\s*([Aa]|opción\s*[Aa]|mostrame\s+fotos)\s*$` matchea con confidence 0.95, intent → `VER_IMAGENES`, router mantiene PRE_EXPEDIENTE y ofrece enviar imágenes.

### 6. Abrir expediente (keyword: "B", "empezar", "abrir expediente")
- CUANDO el usuario escribe "B" (en contexto de opciones A/B) o "Vamos a abrir el expediente"
- ENTONCES regex `^\s*([Bb]|opción\s*[Bb]|abrir\s+expediente)\s*$` matchea con confidence 0.95, intent → `ABRIR_EXPEDIENTE`, modo → `EXPEDIENTE_MODE`, router despacha.

### 7. Fallback a LLM classification
- CUANDO keyword matching no encuentra coincidencia ≥ 0.75 (ej. mensaje ambiguo "mira")
- ENTONCES router invoca al LLM local con el `CLASSIFICATION_SYSTEM_PROMPT`, el LLM responde con JSON `{intent, confidence, entities}`, se parsea, y si confidence < 0.75 → intent → `AMBIGUO`, router mantiene modo actual + pide aclaración.

### 8. Context-aware downgrade (confirmación sin confirmable)
- CUANDO keyword matchea `CONFIRMACION` pero `mode_context.precio_comunicado` es False
- ENTONCES `_validate_keyword_with_context()` downgrade confidence a 0.50, router cae a fallback LLM, que puede clasificar como `AMBIGUO` y pedir aclaración.

### 9. Modificar elementos (keyword: "también", "agregar", "quitar")
- CUANDO el usuario escribe "También quiero homologar el faro" durante PRE_EXPEDIENTE
- ENTONCES regex `\b(también|agregar|añadir|quitar|eliminar|además)\b` matchea con confidence 0.80, intent → `MODIFICAR_ELEMENTOS`, modo → `PRE_EXPEDIENTE_MODE`, router mantiene modo y el agente agrega elementos.

### 10. Cancelación (keyword: "cancelar", "empezar de nuevo")
- CUANDO el usuario escribe "Cancelar todo" / "Empezar de nuevo"
- ENTONCES regex `\b(cancelar|empezar\s+de\s+nuevo|reiniciar|volver\s+al\s+inicio)\b` matchea con confidence 0.90, intent → `CANCELAR`, modo → "" (reset), router borra mode_context, vuelve a START.

## Reglas duras

1. **`CONFIDENCE_THRESHOLD = 0.75`**: keyword confidence ≥ 0.75 → acepta directo. < 0.75 → LLM fallback. Regla inquebrantable.

2. **Keyword es más rápido que LLM**: siempre se intenta keyword matching primero. LLM solo si keyword falla o es ambiguo. Reduce latencia y uso de recursos.

3. **Intent es enum, no string libre**: los intents deben ser miembros de `UserIntent` enum (11 valores). Intents desconocidos → `AMBIGUO` automáticamente, nunca se inventa uno nuevo.

4. **`INTENT_TO_MODE` es la fuente de verdad**: cada intent mapea a exactamente 1 modo (o "" si context-dependent). Cambiar `INTENT_TO_MODE` requiere cambiar toda la lógica downstream.

5. **Las keywords son case-insensitive (`re.I`)**: "QUIERO", "Quiero", "quiero" todos matchean. No hay case-sensitive branching.

6. **El JSON del LLM se parsea estrictamente**: si el LLM retorna JSON malformado, se loguea WARNING y se usa `AMBIGUO` como fallback. Nunca se propaga excepción al user.

7. **History context (últimos 6 mensajes) es opcional**: si se proporciona history, se inyecta en el prompt LLM como "CONTEXTO RECIENTE" (≤ 500 chars). Sin history → prompt estándar.

8. **Las palabras clave para opciones (A/B) son determinísticas**: "A", "opción A", "mostrame fotos" → `VER_IMAGENES` (0.95). "B", "opción B" → `ABRIR_EXPEDIENTE` (0.95). No hay ambigüedad.

9. **Escalación es siempre de alta prioridad**: si el usuario menciona "persona" o "humano", la regex tiene confidence 0.95, bloqueando otros matches más débiles.

10. **Router NO hace cambios de estado directo**: solo clasifica y retorna `IntentResult`. El cambio de modo lo hace `conversation_graph` vía `_transition_to`.

## Catálogo de intents

| Intent | Confidence (keyword) | Modo | Cuándo ocurre |
|--------|-----------------------|------|---------------|
| `CONSULTA_GENERAL` | 0.80 | PRE_EXPEDIENTE_MODE | "¿Qué es?", "¿cómo funciona?", "¿cuánto tarda?" |
| `PRESUPUESTO_DIRECTO` | 0.85-0.90 | PRE_EXPEDIENTE_MODE | "Quiero homologar X", "¿precio de...", "¿documentación para X?" |
| `INICIAR_EXPEDIENTE` | 0.90 | EXPEDIENTE_MODE | "Iniciar expediente", "empezar trámite" (solo si ya hay presupuesto) |
| `ESCALAR` | 0.95 | ESCALATION | "Persona", "humano", "agente" |
| `CONFIRMACION` | 0.90 | "" (current mode) | "Sí", "ok", "dale" (solo válido si hay algo que confirmar) |
| `RECHAZO` | 0.90 | "" (current mode) | "No", "mejor no", "ahora no" |
| `CANCELAR` | 0.90 | "" (START) | "Cancelar", "empezar de nuevo", "reiniciar" |
| `VER_IMAGENES` | 0.90-0.95 | "" (PRE_EXPEDIENTE) | "A", "fotos", "mostrame imágenes" |
| `ABRIR_EXPEDIENTE` | 0.90-0.95 | EXPEDIENTE_MODE | "B", "abrir expediente", "vamos" |
| `MODIFICAR_ELEMENTOS` | 0.80 | PRE_EXPEDIENTE_MODE | "También", "agregar", "quitar" |
| `AMBIGUO` | 0.30-0.75 | PRE_EXPEDIENTE_MODE | No se clasifica → fallback, pedir aclaración |

## Mapeo al código

### Router principal
- `agent/router/intent_router.py:286-596` — clase `IntentRouter.classify(message, current_mode, history, mode_context)`
- `agent/router/intent_router.py:384-400` — `_classify_keywords()` (keyword matching)
- `agent/router/intent_router.py:487-522` — `_classify_llm()` (LLM fallback)

### Patterns
- `agent/router/intent_router.py:83-241` — `_KEYWORD_PATTERNS` lista de 20+ regex tuplas

### LLM prompt para clasificación
- `agent/router/intent_router.py:248-278` — `CLASSIFICATION_SYSTEM_PROMPT`

### Inyección en graph
- `agent/graph/conversation_graph.py` — `router_node` invoca `get_intent_router().classify(...)` y valida transiciones

### Validación de transiciones (whitelist)
- `agent/router/mode_transitions.py:28-43` — `ALLOWED_TRANSITIONS` (matriz de modos válidos)
- `agent/router/mode_transitions.py:97+` — `is_transition_allowed(source, target)`

### Digression manager
- `agent/router/digression_manager.py` — clasifica si el intent es una "digression" (cambio inesperado de intención dentro de modo)

## Fuera de alcance

- `agent/graph/conversation_graph.py` — wiring de `router_node` (otro scope)
- `shared/llm_router.py` — servicio LLM local (scope transversal)
- Cambios al umbral de confianza 0.75 sin nueva evidencia y ADR explícito
