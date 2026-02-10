# FASE 2: VIABILIDAD_MODE - Especificación Técnica

## 🎯 Objetivo
Implementar el modo de viabilidad que evalúa si una modificación puede ser homologada.

**Duración**: 1.5 semanas  
**Dependencias**: Fase 1 completada (State, Router, Fallback)  
**Output**: Modo funcional con tests, integrado al grafo

---

## 📊 Contexto de Negocio

### ¿Por qué VIABILIDAD_MODE primero?
- **65% del tráfico** pasa por aquí
- Es el modo más "conversacional" (educar + evaluar)
- No requiere datos personales (más simple que expediente)
- Punto de entrada natural para la mayoría de usuarios

### Flujo de VIABILIDAD_MODE

```
Usuario: "¿Se puede homologar un turbo en mi Golf GTI?"
    ↓
1. IDENTIFICAR elemento ("turbo")
    ↓
2. IDENTIFICAR vehículo ("Golf GTI")
    ↓
3. EVALUAR compatibilidad
    ↓
4. VERIFICAR restricciones legales
    ↓
5. CONSULTAR documentación necesaria
    ↓
6. CALCULAR estimación rápida (rango amplio)
    ↓
Respuesta: "Sí es viable. Requiere fotos de... Estimación: 1200€-1800€"
    ↓
¿Querés presupuesto exacto? → [TRANSICIÓN A PRESUPUESTO_MODE]
Tengo otras dudas → [TRANSICIÓN A CONSULTA_MODE]
```

---

## 📦 Archivos a Crear

### 1. Nodo de Modo

**Archivo**: `agent/v2/modes/viabilidad_mode.py`

```python
"""
VIABILIDAD_MODE - Evaluar si una modificación puede homologarse

Propósito: 65% del tráfico - punto de entrada principal
"""

from agent.v2.modes.base_mode import BaseModeNode
from agent.v2.state.conversation_state_v2 import ConversationStateV2
from agent.services.element_service import match_elements_with_unmatched
from agent.services.tarifa_service import calculate_tariff_with_elements

class ViabilidadModeNode(BaseModeNode):
    """
    Modo de evaluación de viabilidad.
    
    Tools disponibles:
    - identificar_elemento: Buscar elemento en catálogo
    - evaluar_compatibilidad: Verificar compatibilidad elemento+vehículo
    - verificar_restricciones: Chequear restricciones legales
    - consultar_documentacion: Qué docs se necesitarían
    - listar_elementos_alternativos: Si no viable, ofrecer alternativas
    - calcular_estimacion_rapida: Rango de precio amplio
    - transicionar_a_presupuesto: Cuando usuario confirma interés
    """
    
    def __init__(self):
        super().__init__("VIABILIDAD_MODE")
        self.max_retries = 3
        self.action_on_limit = "ESCALATE_TO_HUMAN"
    
    async def _process_message(self, message: str, state: ConversationStateV2) -> dict:
        """
        Procesar mensaje en VIABILIDAD_MODE.
        
        Returns:
            Dict con response, context_updates, possible transition
        """
        context = state.get("mode_context", {})
        
        # 1. Detectar transiciones explícitas
        transition = self._detect_transition_intent(message)
        if transition:
            return {
                "response": transition["message"],
                "new_mode": transition["target_mode"],
                "context_updates": {
                    "previous_mode": "VIABILIDAD_MODE",
                    **transition.get("context_updates", {}),
                },
            }
        
        # 2. Si tenemos elemento tentativo, verificar si es respuesta de variantes
        if context.get("elemento_tentativo") and not context.get("variante_resuelta"):
            return await self._handle_variant_resolution(message, context)
        
        # 3. Si tenemos elemento pero no vehículo, extraer vehículo
        if context.get("elemento_confirmado") and not context.get("vehiculo"):
            return await self._extract_vehicle(message, context)
        
        # 4. Si tenemos ambos, evaluar viabilidad completa
        if context.get("elemento_confirmado") and context.get("vehiculo"):
            return await self._evaluate_viability(message, context)
        
        # 5. Si no tenemos nada, intentar identificar elemento
        return await self._identify_element(message, context)
    
    async def _identify_element(self, message: str, context: dict) -> dict:
        """
        Identificar elemento de homologación del mensaje.
        
        Usa element_service.match_elements_with_unmatched()
        """
        # Buscar elementos en el mensaje
        match_result = await match_elements_with_unmatched(
            query=message,
            category_slug=context.get("category_slug", "motos-part"),
        )
        
        elementos = match_result.get("matched_elements", [])
        unmatched = match_result.get("unmatched_terms", [])
        
        if len(elementos) == 0:
            return {
                "response": (
                    "No encontré elementos de homologación en tu mensaje. "
                    "¿Podés decirme específicamente qué querés homologar? "
                    "Por ejemplo: 'escape', 'suspensión', 'turbo', etc."
                ),
                "context_updates": {
                    "identificacion_fallida": True,
                },
            }
        
        elif len(elementos) == 1:
            elemento = elementos[0]
            
            # Verificar si tiene variantes
            if elemento.get("has_variants"):
                return {
                    "response": self._format_variant_question(elemento),
                    "context_updates": {
                        "elemento_tentativo": elemento,
                        "variante_resuelta": False,
                    },
                }
            
            # Elemento único confirmado
            return {
                "response": (
                    f"Entendido, querés homologar: **{elemento['name']}**\n\n"
                    f"¿En qué vehículo querés instalarlo? (marca y modelo)"
                ),
                "context_updates": {
                    "elemento_confirmado": elemento,
                    "elemento_codigo": elemento["code"],
                },
            }
        
        else:
            # Múltiples elementos - pedir clarificación
            elementos_list = "\n".join([f"- {e['name']}" for e in elementos[:5]])
            return {
                "response": (
                    f"Encontré varios elementos:\n{elementos_list}\n\n"
                    f"¿Cuál te interesa específicamente?"
                ),
                "context_updates": {
                    "elementos_tentativos": elementos,
                },
            }
    
    async def _handle_variant_resolution(self, message: str, context: dict) -> dict:
        """
        Resolver ambigüedad de variantes.
        
        Usa element_service.get_element_variants() y matching.
        """
        elemento = context["elemento_tentativo"]
        
        # Intentar match de la respuesta con variantes
        # ... lógica de matching
        
        # Si se resuelve, confirmar elemento
        return {
            "response": "Perfecto. ¿En qué vehículo querés instalarlo?",
            "context_updates": {
                "elemento_confirmado": elemento,
                "variante_resuelta": True,
                "variante_seleccionada": "codigo_variante",
            },
        }
    
    async def _extract_vehicle(self, message: str, context: dict) -> dict:
        """
        Extraer marca y modelo de vehículo del mensaje.
        
        Puede usar vehicle_tools.identificar_tipo_vehiculo() o LLM.
        """
        # Extraer info de vehículo
        # ... lógica de extracción
        
        return {
            "response": (
                f"Perfecto. Evaluando compatibilidad de **{context['elemento_confirmado']['name']}** "
                f"en tu vehículo..."
            ),
            "context_updates": {
                "vehiculo": {
                    "marca": "Yamaha",  # Extraído
                    "modelo": "MT-07",  # Extraído
                },
            },
        }
    
    async def _evaluate_viability(self, message: str, context: dict) -> dict:
        """
        Evaluar viabilidad completa: compatibilidad + restricciones + docs.
        """
        elemento = context["elemento_confirmado"]
        vehiculo = context["vehiculo"]
        
        # 1. Evaluar compatibilidad (service call)
        compatibilidad = await self._check_compatibility(elemento, vehiculo)
        
        if not compatibilidad["compatible"]:
            return {
                "response": (
                    f"Lamentablemente, **{elemento['name']}** no es compatible con tu "
                    f"{vehiculo['marca']} {vehiculo['modelo']}.\n\n"
                    f"Motivo: {compatibilidad['razon']}\n\n"
                    f"¿Te gustaría que te sugiera alternativas similares que sí sean compatibles?"
                ),
                "context_updates": {
                    "viabilidad_resultado": "no_viable",
                    "compatibilidad": compatibilidad,
                },
            }
        
        # 2. Verificar restricciones legales
        restricciones = await self._check_restrictions(elemento, vehiculo)
        
        # 3. Consultar documentación necesaria
        documentacion = await self._get_required_docs(elemento)
        
        # 4. Calcular estimación rápida (rango amplio)
        estimacion = await self._calculate_quick_estimate(elemento, vehiculo)
        
        # Construir respuesta
        respuesta = self._format_viability_response(
            elemento, vehiculo, compatibilidad, restricciones, documentacion, estimacion
        )
        
        return {
            "response": respuesta,
            "context_updates": {
                "viabilidad_resultado": "viable",
                "compatibilidad": compatibilidad,
                "restricciones": restricciones,
                "documentacion": documentacion,
                "estimacion_precio": estimacion,
            },
        }
    
    def _detect_transition_intent(self, message: str) -> dict | None:
        """
        Detectar si el usuario quiere transicionar a otro modo.
        
        Returns:
            None si no hay transición, o dict con target_mode y message
        """
        message_lower = message.lower()
        
        # A PRESUPUESTO_MODE
        presupuesto_triggers = [
            "presupuesto", "cuánto sale", "precio exacto", "cotizar",
            "sí, dame presupuesto", "quiero el presupuesto",
        ]
        if any(t in message_lower for t in presupuesto_triggers):
            return {
                "target_mode": "PRESUPUESTO_MODE",
                "message": "Perfecto, voy a prepararte un presupuesto detallado...",
                "context_updates": {
                    "elementos_para_presupuesto": ["elemento_code"],
                },
            }
        
        # A CONSULTA_MODE (dudas generales)
        consulta_triggers = [
            "tengo una duda", "pregunta", "cómo funciona", "qué es",
            "no entiendo", "explicame",
        ]
        if any(t in message_lower for t in consulta_triggers):
            return {
                "target_mode": "CONSULTA_MODE",
                "message": "Dale, contame qué te gustaría saber...",
            }
        
        # ESCALACIÓN
        if any(word in message_lower for word in ["persona", "humano", "agente"]):
            return {
                "target_mode": "ESCALATION",
                "message": "Te voy a conectar con un especialista...",
            }
        
        return None
    
    def _format_viability_response(self, elemento, vehiculo, compatibilidad, 
                                   restricciones, documentacion, estimacion) -> str:
        """Formatear respuesta de viabilidad"""
        parts = []
        
        # Header
        parts.append(f"✅ **SÍ es homologable**\n")
        parts.append(f"**Elemento:** {elemento['name']}")
        parts.append(f"**Vehículo:** {vehiculo['marca']} {vehiculo['modelo']}\n")
        
        # Restricciones (si hay)
        if restricciones:
            parts.append(f"⚠️ **Consideraciones:**")
            for r in restricciones:
                parts.append(f"- {r}")
            parts.append("")
        
        # Documentación
        parts.append(f"📄 **Documentación necesaria:**")
        for doc in documentacion[:5]:
            parts.append(f"- {doc}")
        parts.append("")
        
        # Estimación (rango amplio)
        min_price, max_price = estimacion
        parts.append(f"💰 **Estimación de inversión:** {min_price}€ - {max_price}€ (+ IVA)")
        parts.append(f"   *Esta es una estimación amplia. Para precio exacto necesito identificar el elemento específico.*\n")
        
        # CTA
        parts.append(f"¿Te gustaría que te prepare un **presupuesto exacto** con el elemento identificado?")
        
        return "\n".join(parts)
    
    async def _check_compatibility(self, elemento: dict, vehiculo: dict) -> dict:
        """
        Verificar compatibilidad elemento-vehículo.
        
        Reciclar lógica de element_service o crear en viabilidad_service.
        """
        # TODO: Implementar o llamar a service
        return {"compatible": True, "razon": None}
    
    async def _check_restrictions(self, elemento: dict, vehiculo: dict) -> list:
        """Verificar restricciones legales/regulatorias"""
        # TODO: Consultar base de datos de restricciones
        return []
    
    async def _get_required_docs(self, elemento: dict) -> list:
        """Obtener documentación necesaria"""
        # TODO: Consultar catálogo de documentación
        return ["Fotos del componente actual", "Factura del nuevo componente"]
    
    async def _calculate_quick_estimate(self, elemento: dict, vehiculo: dict) -> tuple:
        """
        Calcular estimación rápida (rango amplio).
        
        Usa tarifa_service.calculate_tariff_with_elements() con margen amplio.
        """
        # Calcular tarifa base
        tarifa = await calculate_tariff_with_elements([elemento["code"]])
        base_price = tarifa["total"]
        
        # Aplicar rango amplio (±30%)
        min_price = int(base_price * 0.7)
        max_price = int(base_price * 1.3)
        
        return (min_price, max_price)
    
    def get_available_tools(self) -> list:
        """Retornar tools disponibles en VIABILIDAD_MODE"""
        return [
            "identificar_elemento",
            "evaluar_compatibilidad",
            "verificar_restricciones",
            "consultar_documentacion",
            "listar_elementos_alternativos",
            "calcular_estimacion_rapida",
            "transicionar_a_presupuesto",
            "escalar_a_humano",
        ]
```

---

### 2. Prompt de Modo

**Archivo**: `agent/v2/prompts/modes/viabilidad_mode.md`

```markdown
# MODO: VIABILIDAD_MODE

## Propósito
Evaluar si una modificación específica puede ser homologada legalmente en un vehículo determinado.

Este es el modo de **entrada principal** (65% del tráfico). La mayoría de las conversaciones empiezan aquí.

## Cuándo estás en este modo
- El usuario pregunta "¿Se puede homologar X?"
- El usuario pregunta "¿Es posible/llegal poner Y en mi Z?"
- Transición desde CONSULTA_MODE cuando detecta interés específico
- El IntentRouter clasificó: EVALUAR_VIABILIDAD

## Objetivo de este modo
1. Identificar el elemento de homologación (escape, suspensión, turbo, etc.)
2. Identificar el vehículo (marca, modelo, año)
3. Evaluar compatibilidad técnica
4. Verificar restricciones legales
5. Informar documentación necesaria
6. Proporcionar **estimación de rango amplio** (NO precio exacto)
7. Transicionar a PRESUPUESTO_MODE si hay interés

## Flujo esperado

### Paso 1: Identificar Elemento
- Usar `identificar_elemento(query)` para buscar en catálogo
- Si hay múltiples opciones: pedir clarificación
- Si tiene variantes: preguntar cuál (ej: "¿Delantera o trasera?")

### Paso 2: Identificar Vehículo
- Preguntar marca y modelo específicos
- Extraer del mensaje del usuario si lo menciona
- No requiere datos exactos del vehículo aún (eso es en expediente)

### Paso 3: Evaluar Viabilidad
Una vez tenés elemento + vehículo:
- `evaluar_compatibilidad(elemento, vehiculo)` → ¿Es compatible?
- `verificar_restricciones(elemento, vehiculo)` → ¿Hay restricciones legales?
- `consultar_documentacion(elemento)` → ¿Qué documentación necesitaría?
- `calcular_estimacion_rapida(elemento)` → Rango de precio amplio

### Paso 4: Responder al Usuario
Estructura de respuesta:
1. **¿Es viable?** (Sí/No/Dudoso) - claro y directo
2. **Consideraciones** (si aplica)
3. **Documentación necesaria** (lista bullet points)
4. **Estimación de inversión** (rango amplio, ej: 800€-1200€)
5. **Call to action**: "¿Querés un presupuesto exacto?"

## Reglas CRÍTICAS

### ❌ NUNCA
- NUNCA des precios exactos en este modo (solo estimaciones amplias)
- NUNCA pidas datos personales (nombre, DNI, email) - eso es en expediente
- NUNCA inventes información de compatibilidad
- NUNCA ignores restricciones legales

### ✅ SIEMPRE
- SIEMPRE evaluar viabilidad antes de mencionar precios
- SIEMPRE explicar por qué algo NO es viable (si aplica)
- SIEMPRE ofrecer alternativas si algo no es compatible
- SIEMPRE transicionar a PRESUPUESTO_MODE cuando el usuario muestre interés concreto

## Transiciones permitidas

| Desde | Hacia | Condición | Mensaje de transición |
|-------|-------|-----------|----------------------|
| VIABILIDAD_MODE | PRESUPUESTO_MODE | Usuario dice "sí, quiero presupuesto" | "Perfecto, voy a calcular tu presupuesto exacto..." |
| VIABILIDAD_MODE | CONSULTA_MODE | Usuario tiene dudas generales | "Dale, contame qué necesitás saber..." |
| VIABILIDAD_MODE | ESCALATION | Caso complejo/dudoso | "Este caso necesita revisión de un especialista..." |

## Estimaciones de precio

En VIABILIDAD_MODE solo damos **rangos amplios**:
- Rango: ±30% del precio base estimado
- Ejemplo: "Entre 800€ y 1200€ (+IVA)"
- Clarificar: "Esta es una estimación. Para precio exacto necesito identificar el elemento específico."

El precio exacto se calcula en PRESUPUESTO_MODE.

## Ejemplos de interacción

### Ejemplo 1: Viable
Usuario: "¿Se puede homologar un escape en una MT-07?"
→ identificar_elemento("escape", "motos-part")
→ evaluar_compatibilidad(escape, MT-07)
→ calcular_estimacion_rapida(escape)

Respuesta:
"✅ **SÍ es homologable**

**Elemento:** Escape deportivo
**Vehículo:** Yamaha MT-07

📄 **Documentación necesaria:**
- Fotos del escape actual (múltiples ángulos)
- Factura de compra del nuevo escape
- Foto del número de serie del escape

💰 **Estimación de inversión:** 410€ - 590€ (+ IVA)
*Esta es una estimación amplia. Para precio exacto necesito identificar el elemento específico.*

¿Te gustaría que te prepare un **presupuesto exacto**?"

### Ejemplo 2: No viable
Usuario: "¿Se puede poner un turbo en una moto 125cc?"
→ evaluar_compatibilidad(turbo, moto_125cc)

Respuesta:
"❌ **NO es homologable**

**Motivo:** Las motocicletas de 125cc no pueden homologar cambios de motor que aumenten la potencia significativamente según el Real Decreto XXX.

**Alternativas que SÍ podrías homologar:**
- Escape deportivo homologado
- Filtro de aire de alto flujo
- Piñón de ataque (-1 diente)

¿Te gustaría que evaluemos alguna de estas alternativas?"

### Ejemplo 3: Caso dudoso → Escalación
Usuario: "¿Se puede homologar una preparación completa de motor con cambio de cilindrada?"

Respuesta:
"⚠️ **Caso complejo**

Las modificaciones de cilindrada son casos especiales que requieren análisis técnico detallado según la normativa ITV vigente. Depende de:
- Nueva cilindrada resultante
- Potencia original vs final
- Año de fabricación del vehículo

Te voy a conectar con un especialista que te puede dar información precisa sobre tu caso específico."
→ [TRANSICIÓN A ESCALATION]

## Herramientas disponibles

### identificar_elemento(query: str, category_slug: str)
Buscar elemento en el catálogo MSI.
- Input: descripción del usuario (ej: "escape")
- Output: lista de elementos coincidentes con scores

### evaluar_compatibilidad(elemento_code: str, vehiculo: dict)
Verificar si elemento es compatible con vehículo.
- Input: código de elemento, {marca, modelo, año}
- Output: {compatible: bool, razon: str | None}

### verificar_restricciones(elemento_code: str, vehiculo: dict)
Chequear restricciones legales/regulatorias.
- Output: lista de restricciones aplicables

### consultar_documentacion(elemento_code: str)
Obtener lista de documentación necesaria.
- Output: lista de descripciones de documentos

### listar_elementos_alternativos(elemento_code: str, vehiculo: dict)
Si no es compatible, sugerir alternativas.
- Output: lista de elementos similares compatibles

### calcular_estimacion_rapida(elemento_codes: list[str])
Calcular rango de precio amplio (±30%).
- Output: (min_price, max_price)

### transicionar_a_presupuesto(elemento_codes: list[str])
Preparar transición a PRESUPUESTO_MODE.
- Guarda elementos tentativos en contexto
- Retorna mensaje de transición

### escalar_a_humano(razon: str)
Solicitar escalación a agente humano.
```

---

### 3. Tools Específicas

**Archivo**: `agent/v2/tools/viabilidad_tools.py`

```python
"""
Tools específicas para VIABILIDAD_MODE

Estas tools encapsulan la lógica de negocio del modo.
"""

from langchain_core.tools import tool
from agent.services.element_service import (
    match_elements_with_unmatched,
    get_element_variants,
)
from agent.services.tarifa_service import calculate_tariff_with_elements

@tool
def identificar_elemento(query: str, category_slug: str = "motos-part") -> dict:
    """
    Identificar elemento de homologación en el catálogo.
    
    Args:
        query: Descripción del elemento (ej: "escape deportivo")
        category_slug: Categoría de vehículo (default: motos-part)
    
    Returns:
        {
            "elementos": [...],
            "unmatched_terms": [...],
            "necesita_clarificacion": bool,
        }
    """
    result = match_elements_with_unmatched(query, category_slug)
    return {
        "elementos": result["matched_elements"],
        "unmatched_terms": result["unmatched_terms"],
        "necesita_clarificacion": len(result["matched_elements"]) != 1,
    }

@tool
def evaluar_compatibilidad(elemento_code: str, vehiculo_marca: str, 
                           vehiculo_modelo: str) -> dict:
    """
    Evaluar compatibilidad técnica entre elemento y vehículo.
    
    Args:
        elemento_code: Código del elemento (ej: "ESC_DEPORT")
        vehiculo_marca: Marca del vehículo
        vehiculo_modelo: Modelo del vehículo
    
    Returns:
        {
            "compatible": bool,
            "razon": str | None,
            "notas_tecnicas": str,
        }
    """
    # Lógica de negocio de compatibilidad
    # TODO: Implementar consulta a base de datos
    pass

@tool  
def calcular_estimacion_rapida(elemento_codes: list[str]) -> dict:
    """
    Calcular estimación de rango amplio (±30%).
    
    Args:
        elemento_codes: Lista de códigos de elemento
    
    Returns:
        {
            "rango_min": int,
            "rango_max": int,
            "nota": str,
        }
    """
    tarifa = calculate_tariff_with_elements(elemento_codes)
    base = tarifa["total"]
    
    return {
        "rango_min": int(base * 0.7),
        "rango_max": int(base * 1.3),
        "nota": "Estimación amplia. Precio exacto en presupuesto.",
    }

# ... más tools según necesidad
```

---

### 4. Integración al Grafo

**Modificar**: `agent/v2/graph/conversation_graph_v2.py`

```python
from agent.v2.modes.viabilidad_mode import ViabilidadModeNode

# Instanciar nodo
viabilidad_node = ViabilidadModeNode()

# Agregar al grafo
graph.add_node("viabilidad_mode", viabilidad_node.process)

# Routing
async def route_from_viabilidad(state: ConversationStateV2):
    """Route después de VIABILIDAD_MODE"""
    result = state.get("last_result", {})
    
    if result.get("new_mode"):
        return result["new_mode"]
    
    # Si no hay transición explícita, seguir en VIABILIDAD
    return "VIABILIDAD_MODE"

graph.add_conditional_edges(
    "viabilidad_mode",
    route_from_viabilidad,
    {
        "VIABILIDAD_MODE": "viabilidad_mode",
        "CONSULTA_MODE": "consulta_mode",
        "PRESUPUESTO_MODE": "presupuesto_mode",
        "ESCALATION": "escalation_node",
    }
)
```

---

## ✅ Checklist Fase 2

- [ ] `viabilidad_mode.py` implementa todos los métodos
- [ ] Identificación de elemento funciona con variants
- [ ] Extracción de vehículo funciona
- [ ] Evaluación de compatibilidad retorna resultados coherentes
- [ ] Estimaciones de precio usan rango amplio (±30%)
- [ ] Detección de transiciones funciona (presupuesto, consulta, escalación)
- [ ] Prompt `viabilidad_mode.md` cubre todos los casos
- [ ] Tools específicas implementadas y testeadas
- [ ] Integración al grafo funciona
- [ ] Tests E2E de flujos completos pasan

---

## 🧪 Tests E2E a Crear

### Test 1: Flujo básico viable
```python
async def test_viabilidad_flow_viable():
    """Usuario pregunta por escape en MT-07 - flujo completo"""
    state = create_test_state()
    
    # Mensaje 1: "¿Se puede homologar un escape?"
    result1 = await viabilidad_node.process(set_message(state, "¿Se puede homologar un escape?"))
    assert "escape" in result1["response"].lower()
    assert "vehículo" in result1["response"].lower()  # Pide vehículo
    
    # Mensaje 2: "En una Yamaha MT-07"
    state["mode_context"] = result1["context_updates"]
    result2 = await viabilidad_node.process(set_message(state, "En una Yamaha MT-07"))
    assert "sí" in result2["response"].lower() or "✅" in result2["response"]
    assert "estimación" in result2["response"].lower()
    assert "presupuesto exacto" in result2["response"].lower()
```

### Test 2: Variante resolution
```python
async def test_viabilidad_variant_resolution():
    """Elemento con variantes (suspensión delantera/trasera)"""
    state = create_test_state()
    
    # Mensaje: "¿Se puede homologar una suspensión?"
    result = await viabilidad_node.process(set_message(state, "¿Se puede homologar una suspensión?"))
    
    # Debe preguntar delantera o trasera
    assert "delantera" in result["response"].lower() or "trasera" in result["response"].lower()
    assert result["context_updates"].get("elemento_tentativo")
    assert not result["context_updates"].get("variante_resuelta")
```

### Test 3: Fallback trigger
```python
async def test_viabilidad_fallback():
    """3 errores consecutivos deben trigger escalation"""
    state = create_test_state()
    state["retry_state"] = {"retry_count": 2, "consecutive_errors": 2}
    
    # 3er error
    result = await viabilidad_node.process(set_message(state, "Mensaje incomprensible"))
    
    assert result.get("new_mode") == "ESCALATION"
    assert "especialista" in result["response"].lower()
```

---

**Fase 2 completa cuando**: VIABILIDAD_MODE funciona end-to-end con tests pasando.
