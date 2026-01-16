---
name: msia-agent
description: >
  MSI-a conversational agent patterns using LangGraph.
  Trigger: When working on agent conversation flow, nodes, state, tools, or prompts.
metadata:
  author: msi-automotive
  version: "1.0"
  scope: [root, agent]
  auto_invoke: "Working on agent conversation flow"
---

## Agent Structure

```
agent/
├── main.py                 # Entry point, Redis stream consumer
├── graphs/
│   └── conversation_flow.py  # StateGraph definition
├── nodes/
│   ├── process_message.py    # Message preprocessing
│   └── conversational_agent.py  # LLM response generation
├── tools/
│   ├── tarifa_tools.py       # Tariff calculation tools
│   ├── element_tools.py      # Element matching tools
│   ├── vehicle_tools.py      # Vehicle identification
│   └── case_tools.py         # Case management tools
├── services/
│   ├── tarifa_service.py     # Tariff business logic
│   ├── element_service.py    # Element matching service
│   └── prompt_service.py     # Dynamic prompt generation
├── state/
│   ├── schemas.py            # ConversationState TypedDict
│   ├── checkpointer.py       # Redis checkpointer
│   └── helpers.py            # State utilities
├── fsm/
│   └── case_collection.py    # Data collection FSM
└── prompts/
    ├── system.md             # Main system prompt
    └── calculator_base.py    # Calculator prompt template
```

## ConversationState Schema

```python
class ConversationState(TypedDict, total=False):
    # Core Metadata
    conversation_id: str          # LangGraph thread_id
    user_phone: str               # E.164 format
    user_name: str | None
    user_id: str | None           # Database UUID
    client_type: str | None       # "particular" or "professional"
    
    # Messages
    messages: list[dict[str, Any]]  # Conversation history
    user_message: str | None        # Current message
    conversation_summary: str | None
    
    # State
    current_state: str              # "idle", "inquiry", etc.
    fsm_state: dict[str, Any] | None
    
    # Flags
    is_first_interaction: bool
    escalation_triggered: bool
    agent_disabled: bool            # Panic button
    
    # Tool Results
    pending_images: list[dict[str, Any]]  # Images to send
    incoming_attachments: list[dict[str, Any]]  # User attachments
```

## Graph Flow

```
START
  ↓
process_incoming_message
  ↓
[conditional: agent_disabled?]
  ├─ Yes → END (auto-response sent)
  └─ No → conversational_agent
           ↓
         END
```

## Node Pattern

```python
async def my_node(state: ConversationState) -> dict:
    """
    Node documentation.
    
    Args:
        state: Current conversation state
        
    Returns:
        State updates to merge
    """
    # Access state
    messages = state.get("messages", [])
    user_message = state.get("user_message", "")
    
    # Process logic
    result = await process_something(user_message)
    
    # Return state updates (will be merged)
    return {
        "last_node": "my_node",
        "context": {"processed": True},
    }
```

## Tool Pattern

```python
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class CalculateTariffInput(BaseModel):
    category_slug: str = Field(description="Vehicle category slug")
    elements: list[str] = Field(description="List of element names")
    client_type: str = Field(description="particular or professional")

@tool(args_schema=CalculateTariffInput)
async def calculate_tariff(
    category_slug: str,
    elements: list[str],
    client_type: str
) -> str:
    """Calculate homologation tariff based on elements.
    
    Use this when the user asks about prices or wants a quote.
    Returns tariff tier, price, and required documentation.
    """
    async with get_session() as session:
        result = await TarifaService.calculate(
            session, category_slug, elements, client_type
        )
    return format_tariff_result(result)
```

## Message History Format

```python
# Messages in state
messages = [
    {
        "role": "user",
        "content": "Hola, quiero homologar mi autocaravana",
        "timestamp": "2026-01-15T10:30:00+01:00"
    },
    {
        "role": "assistant", 
        "content": "¡Hola! Encantado de ayudarte...",
        "timestamp": "2026-01-15T10:30:05+01:00"
    }
]
```

## Pending Images Pattern

```python
# When tools find documentation images
return {
    "pending_images": [
        {
            "url": "https://api.msi-a.es/images/ficha-tecnica.jpg",
            "tipo": "base",  # or "elemento"
            "descripcion": "Ejemplo de ficha técnica"
        }
    ]
}
```

## Critical Rules

- ALWAYS use `total=False` in TypedDict for partial updates
- ALWAYS return dict from nodes (state updates to merge)
- NEVER modify state directly; return updates
- ALWAYS use async for database/API calls
- ALWAYS handle missing state keys with `.get()`
- ALWAYS set `last_node` in return for debugging
- Tool descriptions are used by LLM - make them clear

## Resources

- [langgraph skill](../langgraph/SKILL.md) - Generic LangGraph patterns
- [System prompt](../../agent/prompts/system.md) - Main agent prompt
