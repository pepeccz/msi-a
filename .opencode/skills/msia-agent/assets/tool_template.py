"""
Template for MSI-a LangGraph tool.

Usage:
1. Copy this file to agent/tools/
2. Rename to your_tools.py
3. Update the tool name, schema, and implementation
4. Add to the tools list in conversational_agent.py
"""

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from database.connection import get_session


class MyToolInput(BaseModel):
    """Input schema for my_tool.
    
    The description of each field is used by the LLM to understand
    what parameters to provide. Make them clear and specific.
    """
    
    required_param: str = Field(
        description="Description of what this parameter is for"
    )
    optional_param: str | None = Field(
        default=None,
        description="Optional parameter with default value"
    )
    numeric_param: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Numeric parameter with constraints"
    )


@tool(args_schema=MyToolInput)
async def my_tool(
    required_param: str,
    optional_param: str | None = None,
    numeric_param: int = 5,
) -> str:
    """One-line description of what this tool does.
    
    Use this tool when:
    - First use case
    - Second use case
    
    Do NOT use this tool when:
    - Case where another tool is better
    
    Returns:
        Formatted result that can be used in the response
    """
    async with get_session() as session:
        # Your tool logic here
        result = await perform_action(
            session,
            required_param,
            optional_param,
            numeric_param,
        )
    
    # Format result for LLM/user
    return format_result(result)


async def perform_action(session, param1, param2, param3):
    """Helper function for tool logic."""
    # Implement your database queries or business logic
    return {"status": "success", "data": param1}


def format_result(result: dict) -> str:
    """Format the result for display."""
    return f"""
**Resultado:**
- Estado: {result['status']}
- Datos: {result['data']}
"""


# Example: Tool that returns images for pending_images
class GetDocumentationInput(BaseModel):
    """Input for get_documentation tool."""
    
    category_slug: str = Field(
        description="Vehicle category slug (e.g., 'aseicars', 'motos')"
    )
    element_code: str | None = Field(
        default=None,
        description="Specific element code to get documentation for"
    )


@tool(args_schema=GetDocumentationInput)
async def get_documentation(
    category_slug: str,
    element_code: str | None = None,
) -> str:
    """Get documentation examples for homologation.
    
    Use this when the user asks about documentation requirements
    or wants to see examples of required documents.
    
    Returns:
        Text description plus images via pending_images state.
    """
    async with get_session() as session:
        docs = await fetch_documentation(session, category_slug, element_code)
    
    # Images will be sent via state update, not tool return
    # The tool should return text description only
    return format_documentation(docs)


async def fetch_documentation(session, category_slug, element_code):
    """Fetch documentation from database."""
    # Implementation
    return []


def format_documentation(docs):
    """Format documentation list."""
    return "Documentation description..."
