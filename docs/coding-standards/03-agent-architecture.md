# Estándares Agent Architecture (LangGraph + FSM)

Patrones para el agente conversacional MSI-a.

---

## 1. Anti-Patterns (CRÍTICO)

### NUNCA Re-identificar Después de Variante

```python
# ❌ INCORRECTO
User: "delantera"
→ identificar_y_resolver_elementos(...)  # WRONG!

# ✅ CORRECTO
User: "delantera"
→ seleccionar_variante_por_respuesta("motos-part", "SUSPENSION", "delantera")
```

### SIEMPRE Precio Antes de Imágenes

```python
# ❌ INCORRECTO
calcular_tarifa_con_elementos(...)  # → 410€
Bot: "Te envío fotos:"  # Missing price!

# ✅ CORRECTO
calcular_tarifa_con_elementos(...)  # → 410€
Bot: "El presupuesto es de 410€ +IVA. Te envío fotos:"
```

### SIEMPRE skip_validation Después de ID

```python
# ❌ INCORRECTO
await calcular_tarifa_con_elementos(elementos, categoria)

# ✅ CORRECTO
await calcular_tarifa_con_elementos(elementos, categoria, skip_validation=True)
```

---

## 2. Tool Pattern

```python
from langchain.tools import tool
from typing import Any

@tool
async def my_tool(
    param1: str,
    param2: int | None = None,
) -> dict[str, Any]:
    """
    Tool description for LLM (clear, specific).
    
    Args:
        param1: Description
        param2: Optional description
    
    Returns:
        Dict with success, message, data, error
    """
    try:
        # Business logic
        result = await some_service_call()
        
        return {
            "success": True,
            "message": "Acción completada correctamente",
            "data": result,
        }
    except Exception as e:
        logger.error("tool_error", tool="my_tool", error=str(e))
        return {
            "success": False,
            "error": str(e),
            "message": "Ha ocurrido un error. Intenta de nuevo.",
        }
```

---

## 3. Mode Node Pattern

```python
from agent.modes.base_mode import BaseModeNode

class MyModeNode(BaseModeNode):
    def __init__(self):
        super().__init__("MY_MODE")
    
    async def _process_message(self, message: str, state: dict) -> dict:
        # 1. Build system prompt
        system_prompt = assemble_system_prompt(mode="MY_MODE", mode_context=state.get("mode_context"))
        
        # 2. Get tools
        tools = self.get_tools()
        llm = self._get_llm(tools)
        
        # 3. LLM loop
        for iteration in range(MAX_ITERATIONS):
            response = await llm.ainvoke([...])
            # Execute tools, update context
        
        return {"ai_response": response}
    
    def get_tools(self) -> list:
        return [tool1, tool2, tool3]
```

---

## 4. Dynamic Prompts

```python
def assemble_system_prompt(mode: str, mode_context: dict | None = None) -> str:
    parts = []
    
    # 1. Security start
    parts.append(SECURITY_START)
    
    # 2. Core modules (always)
    parts.append(load_core_modules())
    
    # 3. Mode-specific module
    parts.append(load_mode_module(mode))
    
    # 4. Mode context
    if mode_context:
        parts.append(format_mode_context(mode_context))
    
    # 5. Security end
    parts.append(SECURITY_END)
    
    return "\n\n---\n\n".join(parts)
```

---

## 5. FSM Tools (NUNCA modificar state directamente)

```python
# ❌ INCORRECTO
state["fsm_phase"] = "COLLECTING"  # WRONG!

# ✅ CORRECTO
from agent.tools.case_tools import avanzar_fase_expediente

result = await avanzar_fase_expediente(
    nueva_fase="COLLECT_BASE_DOCS"
)
```

---

## 6. Hybrid LLM Routing

```python
from shared.llm_router import get_llm_router, TaskType

router = get_llm_router()

# For conversation
response = await router.invoke(
    task_type=TaskType.CONVERSATION,  # → Tier 3 (cloud)
    messages=[...],
)

# For simple RAG
response = await router.invoke(
    task_type=TaskType.SIMPLE_RAG,  # → Tier 2 (local capable)
    messages=[...],
)

# For classification
response = await router.invoke(
    task_type=TaskType.CLASSIFICATION,  # → Tier 1 (local fast)
    messages=[...],
)
```

---

## 7. Reglas Críticas

1. ❌ **NUNCA** re-identificar después de variante
2. ✅ **SIEMPRE** precio antes de imágenes
3. ✅ **SIEMPRE** skip_validation=True después de ID
4. ✅ **SIEMPRE** usar FSM tools para transiciones
5. ✅ **SIEMPRE** field_key exacto de obtener_campos_elemento()
6. ✅ **SIEMPRE** async/await para tools
7. ✅ **SIEMPRE** return dict con success/message/data/error
8. ❌ **NUNCA** hardcoded flow → LLM decide
9. ❌ **NUNCA** modificar fsm_state directamente
10. ❌ **NUNCA** inventar variantes no en preguntas_variantes

---

**Referencias:**
- `agent/AGENTS.md` - Anti-Patterns section
- `skills/langgraph/SKILL.md`
- `skills/msia-agent/SKILL.md`

**Última actualización:** Febrero 2026
