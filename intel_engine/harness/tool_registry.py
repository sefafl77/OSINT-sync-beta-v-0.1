"""Model-neutral tool declarations shared by Codex MCP and the optional SDK runner.

Importing this module never reads model settings, loads an LLM backend, or calls a network API.
"""
from __future__ import annotations

from typing import Any, Callable


class ToolAnnotations:
    def __init__(self, **hints: Any):
        self.__dict__.update(hints)


class SdkMcpTool:
    def __init__(self, name: str, description: str, input_schema: dict,
                 handler: Callable, annotations: Any = None):
        self.name = name
        self.description = description
        self.input_schema = input_schema or {}
        self.handler = handler
        self.annotations = annotations


def tool(name: str, description: str, input_schema: dict | None = None,
         annotations: Any = None):
    def decorate(handler):
        return SdkMcpTool(name, description, input_schema or {}, handler, annotations)
    return decorate


class SdkMcpServer:
    def __init__(self, name: str, tools: list | None = None):
        self.name = name
        self.tools = list(tools or [])


def create_sdk_mcp_server(name: str, tools: list | None = None, **kwargs):
    return SdkMcpServer(name, tools)
