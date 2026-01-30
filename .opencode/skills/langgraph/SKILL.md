---
name: langgraph
description: >
  LangGraph patterns for building AI agents.
  Trigger: When working on StateGraph, nodes, edges, checkpointers, or tool calling.
metadata:
  author: msi-automotive
  version: "1.0"
  scope: [root, agent]
  auto_invoke: "Working on LangGraph graphs/nodes"
---

## StateGraph Pattern

```python
from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated
from operator import add

class AgentState(TypedDict):
    messages: Annotated[list, add]  # Append-only list
    current_step: str
    context: dict

def create_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    
    # Add nodes
    graph.add_node("process", process_node)
    graph.add_node("respond", respond_node)
    graph.add_node("tools", tools_node)
    
    # Add edges
    graph.add_edge(START, "process")
    graph.add_conditional_edges(
        "process",
        route_decision,
        {
            "respond": "respond",
            "tools": "tools",
        }
    )
    graph.add_edge("tools", "process")
    graph.add_edge("respond", END)
    
    return graph.compile()
```

## Node Pattern

```python
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

async def process_node(state: AgentState) -> dict:
    """Process incoming message and decide next action."""
    messages = state["messages"]
    last_message = messages[-1]
    
    # Process logic here
    result = await process_message(last_message)
    
    # Return state updates (will be merged)
    return {
        "current_step": "processed",
        "context": {"processed_at": datetime.now().isoformat()}
    }

async def respond_node(state: AgentState) -> dict:
    """Generate response using LLM."""
    messages = state["messages"]
    
    response = await llm.ainvoke(messages)
    
    return {
        "messages": [response]  # Appended due to Annotated[list, add]
    }
```

## Conditional Routing

```python
def route_decision(state: AgentState) -> str:
    """Determine next node based on state."""
    messages = state["messages"]
    last_message = messages[-1]
    
    # Check if tool call is needed
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    
    return "respond"
```

## Tool Definition

```python
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class SearchInput(BaseModel):
    query: str = Field(description="Search query")
    limit: int = Field(default=5, description="Max results")

@tool(args_schema=SearchInput)
async def search_database(query: str, limit: int = 5) -> str:
    """Search the database for relevant information.
    
    Use this when you need to find specific data.
    """
    results = await db.search(query, limit=limit)
    return format_results(results)

# Bind tools to LLM
llm_with_tools = llm.bind_tools([search_database, other_tool])
```

## Tool Node

```python
from langgraph.prebuilt import ToolNode

# Automatic tool execution
tools = [search_database, calculate_price]
tool_node = ToolNode(tools)

# Or manual tool handling
async def tools_node(state: AgentState) -> dict:
    messages = state["messages"]
    last_message = messages[-1]
    
    results = []
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        
        # Execute tool
        if tool_name == "search_database":
            result = await search_database(**tool_args)
        else:
            result = f"Unknown tool: {tool_name}"
        
        results.append(ToolMessage(
            content=result,
            tool_call_id=tool_call["id"]
        ))
    
    return {"messages": results}
```

## Checkpointer (State Persistence)

```python
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

# In-memory (development)
memory = MemorySaver()
graph = graph_builder.compile(checkpointer=memory)

# PostgreSQL (production)
async with AsyncPostgresSaver.from_conn_string(DATABASE_URL) as checkpointer:
    graph = graph_builder.compile(checkpointer=checkpointer)

# Redis (custom implementation)
class RedisCheckpointer(BaseCheckpointSaver):
    async def aget(self, config: RunnableConfig) -> Checkpoint | None:
        thread_id = config["configurable"]["thread_id"]
        data = await redis.get(f"checkpoint:{thread_id}")
        return deserialize(data) if data else None
    
    async def aput(self, config: RunnableConfig, checkpoint: Checkpoint) -> None:
        thread_id = config["configurable"]["thread_id"]
        await redis.set(f"checkpoint:{thread_id}", serialize(checkpoint))
```

## Invoking the Graph

```python
# With thread_id for persistence
config = {"configurable": {"thread_id": "user-123"}}

# Single invocation
result = await graph.ainvoke(
    {"messages": [HumanMessage(content="Hello")]},
    config=config
)

# Streaming
async for event in graph.astream(
    {"messages": [HumanMessage(content="Hello")]},
    config=config
):
    print(event)

# Stream specific events
async for event in graph.astream_events(
    {"messages": [HumanMessage(content="Hello")]},
    config=config,
    version="v2"
):
    if event["event"] == "on_chat_model_stream":
        print(event["data"]["chunk"].content, end="")
```

## State Reducers

```python
from typing import Annotated
from operator import add

class AgentState(TypedDict):
    # Append-only (messages accumulate)
    messages: Annotated[list, add]
    
    # Last value wins (overwrites)
    current_step: str
    
    # Custom reducer
    counters: Annotated[dict, merge_counters]

def merge_counters(current: dict, update: dict) -> dict:
    result = current.copy()
    for key, value in update.items():
        result[key] = result.get(key, 0) + value
    return result
```

## Critical Rules

- ALWAYS use TypedDict for state definition
- ALWAYS use Annotated with reducers for lists that accumulate
- NEVER modify state directly; return updates from nodes
- ALWAYS use async functions for nodes with I/O
- ALWAYS use thread_id in config for conversation persistence
- ALWAYS define clear routing logic in conditional edges
