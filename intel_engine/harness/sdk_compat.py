"""Compatibility imports for the optional standalone Python agent harness.

Codex-native use does not import this module: Codex runs the model and connects to
mcp_server.py. The old SDK-driven harness remains available only when explicitly
configured for an OpenAI-compatible endpoint. It never defaults to Anthropic.
"""
from __future__ import annotations

import os

_OPENAI_BACKENDS = {"openai", "deepseek", "kimi", "moonshot", "local", "ollama", "vllm", "lmstudio"}
BACKEND = os.environ.get("HARNESS_BACKEND", "codex").strip().lower()

if BACKEND in _OPENAI_BACKENDS:
    from openai_backend import (  # noqa: F401
        AgentDefinition,
        AssistantMessage,
        ClaudeAgentOptions,
        HookMatcher,
        ResultMessage,
        ToolAnnotations,
        ToolUseBlock,
        create_sdk_mcp_server,
        query,
        tool,
    )
    BACKEND = "openai"
elif BACKEND in {"codex", "claude", "anthropic"}:
    raise RuntimeError(
        "The standalone Python harness does not run Codex as a subprocess. "
        "Use Codex in this repository with its configured intel_harness MCP server. "
        "For explicit API-backed harness runs, set HARNESS_BACKEND to an "
        "OpenAI-compatible provider and configure that provider's credentials."
    )
else:
    raise RuntimeError(
        f"Unsupported HARNESS_BACKEND={BACKEND!r}; choose an OpenAI-compatible "
        "backend or use Codex native MCP."
    )
