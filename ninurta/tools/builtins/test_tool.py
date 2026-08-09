"""Dummy test tool for LangGraph integration."""

from ninurta.tools.registry import tool

@tool
def sample_tool(query: str) -> str:
    """Sample tool for testing tool registry within LangGraph.
    
    Args:
        query: Search query string.
    """
    return f"Test Node executed tool successfully with query: {query}"
