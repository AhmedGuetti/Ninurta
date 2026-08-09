"""Tool Registry & Decorator.

Provides the @tool decorator to automatically parse Python functions 
into OpenAI/Gemini compatible JSON schemas, based on type hints and docstrings.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, List

_TYPE_MAP = {
    int: "integer",
    float: "number",
    str: "string",
    bool: "boolean",
    list: "array",
    List: "array",
    dict: "object",
    Dict: "object",
}


class ToolRegistry:
    """Stores available tools and their auto-generated JSON schemas."""

    def __init__(self) -> None:
        self._tools: dict[str, Callable] = {}
        self._schemas: list[dict] = []

    def _type_to_schema(self, py_type: type | str | Any) -> dict:
        """Convert a Python type annotation to a JSON schema type."""
        # Handle string type hints (e.g., from __future__ import annotations)
        if isinstance(py_type, str):
            py_t_lower = py_type.lower()
            for t_name, json_t in [
                ("int", "integer"),
                ("float", "number"),
                ("str", "string"),
                ("bool", "boolean"),
                ("list", "array"),
                ("dict", "object"),
            ]:
                if t_name in py_t_lower:
                    return {"type": json_t}
            return {"type": "string"}  # Default fallback

        # If it's a generic alias like list[str], the origin will be `list`
        origin = getattr(py_type, "__origin__", py_type)
        json_type = _TYPE_MAP.get(origin, "string")
        return {"type": json_type}

    def register(self, func: Callable) -> Callable:
        """Decorator to register a function and generate its JSON schema."""
        self._tools[func.__name__] = func
        
        sig = inspect.signature(func)
        doc = inspect.getdoc(func) or "No description provided."
        
        # Simple docstring parsing (first paragraph is main description)
        description = doc.split("\n\n")[0].replace("\n", " ").strip()
        
        properties: dict[str, dict] = {}
        required: list[str] = []
        
        for name, param in sig.parameters.items():
            if name == "self":
                continue
                
            param_schema = self._type_to_schema(param.annotation)
            
            # Simple param doc extraction
            param_desc = ""
            for line in doc.split("\n"):
                if line.strip().startswith(f"{name}:") or line.strip().startswith(f"{name} ("):
                    param_desc = line.split(":", 1)[-1].strip()
                    break
                    
            if param_desc:
                param_schema["description"] = param_desc
                
            properties[name] = param_schema
            
            if param.default == inspect.Parameter.empty:
                required.append(name)
                
        schema = {
            "type": "function",
            "function": {
                "name": func.__name__,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False, # Strict mode, helps LLMs
                }
            }
        }
        
        self._schemas.append(schema)
        return func

    def call(self, name: str, kwargs: dict) -> Any:
        """Execute a registered tool by name with the given kwargs."""
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered.")
        return self._tools[name](**kwargs)
        
    def get_schemas(self) -> list[dict]:
        """Return the list of standard JSON schemas for all registered tools."""
        return self._schemas
        
    def clear(self) -> None:
        """Clear all registered tools (useful for testing or specific scopes)."""
        self._tools.clear()
        self._schemas.clear()


# Global default registry instance
registry = ToolRegistry()
tool = registry.register

