#!/usr/bin/env python3
"""mcp_server.py — a standalone stdio MCP server exposing the harness's OSINT tools.

WHY THIS EXISTS
  The SDK driver (orchestrator.py) already gets clean, typed tools instead of shell-flailing.
  Codex can connect to this server and call the same typed, permission-gated tool surface using
  its signed-in model session; no Anthropic SDK or API key is needed for this path.

ZERO DUPLICATION
  It does NOT re-implement any tool. It imports `tools.py` and auto-discovers every `@tool`
  (each an `SdkMcpTool` with .name/.description/.input_schema/.handler) — the handlers, and the
  CLIs underneath them, stay the single source of truth. Add a tool to tools.py and it appears
  here automatically.

RUN / WIRE UP
  Run with the project venv created by `scripts/install-codex.ps1`.
  Codex discovers it via `.codex/config.toml` in this project.

  Protocol: MCP over stdio = newline-delimited JSON-RPC 2.0. Methods handled:
  initialize · notifications/initialized · tools/list · tools/call · ping.

NOTE — egress policy: this server has no phase loop to flip tools.POLICY, so it inherits the
  import-time default, which reads the HARNESS_HOSTILE env var (see tools.py). Run a hostile-infra
  session with `HARNESS_HOSTILE=1` and pivot_extract refuses direct live fetch (forces passive= /
  proxy=), matching the SDK driver's per-phase gate. Left unset it defaults permissive, which suits
  benign interactive use.

  That env gate is now the SECOND lock, not the only one: every tools/call goes through
  `audit.gate()` first — the same policy point the SDK driver reaches via its PreToolUse hook and
  the OpenAI shim calls inline. It blocks hostile egress across ALL outbound tools (not just the
  ones that implement their own refusal), refuses an unapproved sandbox submission, and writes
  every call — allowed or denied — to cases/<case>/tool_calls.jsonl. Interactive calls that carry
  no `case` argument land in MEMORY/tool_calls.jsonl.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # find harness/tools.py first
import audit  # noqa: E402  — the shared tool-call gate + ledger (front-end neutral)
import tools as T  # noqa: E402  (Codex-neutral tool definitions; no Anthropic SDK required)
import case_scope  # noqa: E402
from result_view import present  # noqa: E402

SERVER_INFO = {"name": "intel-harness", "version": "0.2.0"}
DEFAULT_PROTOCOL = "2025-06-18"
SUPPORTED_PROTOCOLS = {"2024-11-05", "2025-03-26", DEFAULT_PROTOCOL}

# Auto-discover every decorated tool in tools.py (duck-typed, so no SDK-internal import needed).
TOOLS = {
    v.name: v
    for v in vars(T).values()
    if hasattr(v, "name") and hasattr(v, "handler") and hasattr(v, "input_schema")
}

_JSON_TYPE = {str: "string", int: "integer", float: "number", bool: "boolean"}

# Executor for blocking tool coroutines (concurrency governed by vendor limits, not a codebase cap)
_EXECUTOR = ThreadPoolExecutor()
_WRITE_LOCK = threading.Lock()
_PENDING: set[asyncio.Task] = set()


def _input_schema(sdk_schema: dict, optional: dict | None = None) -> dict:
    """Convert tools.py's `{param: python_type}` into a JSON Schema object.

    The declared params are REQUIRED (matching how the SDK treated them). `optional` carries the
    documented-but-undeclared arguments from references/tool_params.json — passive, free_only,
    mode, max_domains and the rest — as real properties with types, one-line descriptions and, for
    the fixed-value ones, an `enum`. They used to live only in the description paragraph, which a
    strong model reads reliably and a mid-size open-weight model largely does not; a model that
    cannot see `mode` accepts exactly six values invents a seventh. additionalProperties stays true
    so an argument not yet declared here still passes through."""
    props = {k: {"type": _JSON_TYPE.get(v, "string")} for k, v in (sdk_schema or {}).items()}
    required = list(props.keys())
    for name, spec in (optional or {}).items():
        extra = {k: v for k, v in spec.items() if k in ("type", "description", "enum")}
        if name in props:
            # A REQUIRED param keeps its declared type but still gains the description and the
            # `enum` — censys.mode is required and accepts exactly six values, and without the
            # enum a model sends a seventh. Required-ness is never changed here.
            extra.pop("type", None)
            props[name].update(extra)
        else:
            props[name] = extra
    return {"type": "object", "properties": props,
            "required": required, "additionalProperties": True}


def _list_tools() -> list[dict]:
    result = []
    for t in TOOLS.values():
        entry = {"name": t.name, "description": t.description,
                 "inputSchema": _input_schema(t.input_schema, getattr(t, "optional_schema", None))}
        hints = getattr(t, "annotations", None)
        if hints:
            entry["annotations"] = hints if isinstance(hints, dict) else vars(hints)
        result.append(entry)
    return result


def _argument_error(tool, arguments: dict) -> str:
    """Validate the advertised contract before a handler can spawn a subprocess."""
    schema = _input_schema(tool.input_schema, getattr(tool, "optional_schema", None))
    missing = [k for k in schema["required"] if k not in arguments]
    if missing:
        return "Input belum lengkap. Masukkan: " + ", ".join(missing) + "."
    types = {"string": str, "integer": int, "number": (int, float),
             "boolean": bool, "object": dict, "array": list}
    for key, value in arguments.items():
        prop = schema["properties"].get(key, {})
        kind = prop.get("type")
        if kind in types and (not isinstance(value, types[kind])
                              or (kind in {"integer", "number"} and isinstance(value, bool))):
            return f"Input '{key}' harus bertipe {kind}."
        if key in schema["required"] and kind == "string" and key != "case" and not value.strip():
            return f"Input '{key}' masih kosong. Masukkan nilainya terlebih dahulu."
        if "enum" in prop and value not in prop["enum"]:
            return f"Pilihan '{key}' belum sesuai. Gunakan: {', '.join(map(str, prop['enum']))}."
    case = arguments.get("case")
    if case is not None and case != "":
        from guided import case_path
        try:
            case_path(case, root=audit.ROOT)
        except (ValueError, OSError) as exc:
            return str(exc)
    return ""


async def _call_tool(name: str, arguments: dict) -> dict:
    """Invoke a tool handler and translate its {content, is_error} into an MCP tools/call result.
    A missing tool or a raised handler becomes an isError result (the model sees the message),
    never a transport-level failure.

    Gated: `audit.gate` runs BEFORE the handler. A denial is returned as an isError result carrying
    the reason, so Codex can adapt (re-call passive / free_only, or ask the analyst for the
    approval a sandbox submission needs) instead of silently proceeding."""
    tool = TOOLS.get(name)
    if tool is None:
        return {"content": [{"type": "text", "text": f"unknown tool: {name}"}], "isError": True}
    error = _argument_error(tool, arguments)
    if error:
        return {"content": [{"type": "text", "text": error}], "isError": True}
    case = arguments.get("case")
    scope = case_scope.load(case, root=audit.ROOT) if case else None
    if case and os.path.isfile(case_scope.path(case, root=audit.ROOT)) and scope is None:
        return {"content": [{"type": "text", "text": "Scope case belum dapat dibaca. Periksa scope.json sebelum melanjutkan."}], "isError": True}
    constraints = (scope or {}).get("constraints") or {}
    if not isinstance(constraints, dict):
        return {"content": [{"type": "text", "text": "Format constraints di scope.json belum valid. Perbaiki scope sebelum melanjutkan."}], "isError": True}
    allowed, why = audit.gate(name, arguments, case=case,
                              phase="interactive", backend="codex",
                              hostile=True if scope and case_scope.is_hostile(scope) else None,
                              no_spend=bool(constraints.get("no_spend")))
    if not allowed:
        return {"content": [{"type": "text", "text": f"[BLOCKED by harness policy] {why}"}],
                "isError": True}
    try:
        res = await tool.handler(arguments or {})
    except Exception as e:  # noqa: BLE001 — surface tool faults to the model, keep the server alive
        return {"content": [{"type": "text", "text": f"{name} raised: {e!r}"}], "isError": True}
    result = {"content": res.get("content") or [],
              "isError": bool(res.get("is_error") or res.get("isError"))}
    if isinstance(res.get("structuredContent"), dict):
        result["structuredContent"] = res["structuredContent"]
    return present(name, result)


async def _dispatch(method: str, params: dict) -> dict:
    if method == "initialize":
        return {
            "protocolVersion": (params.get("protocolVersion") if params.get("protocolVersion")
                                in SUPPORTED_PROTOCOLS else DEFAULT_PROTOCOL),
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }
    if method == "tools/list":
        return {"tools": _list_tools()}
    if method == "tools/call":
        if not isinstance(params.get("name"), str) or not params["name"]:
            raise _InvalidParams("tools/call requires a non-empty tool name")
        if not isinstance(params.get("arguments", {}), dict):
            raise _InvalidParams("tool arguments must be an object")
        return await _call_tool(params.get("name", ""), params.get("arguments") or {})
    if method == "ping":
        return {}
    raise _MethodNotFound(method)


class _MethodNotFound(Exception):
    pass


class _InvalidParams(Exception):
    pass


def _write(obj: dict) -> None:
    with _WRITE_LOCK:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()


async def _handle(msg: dict) -> None:
    if (not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0"
            or not isinstance(msg.get("method"), str)):
        _write({"jsonrpc": "2.0", "id": None,
                "error": {"code": -32600, "message": "invalid JSON-RPC request"}})
        return
    mid = msg.get("id")
    method = msg.get("method", "")
    if "id" not in msg:
        return  # Notifications never produce a JSON-RPC response.
    params = msg.get("params", {})
    try:
        if not isinstance(params, dict):
            raise _InvalidParams("params must be an object")
        def _run_dispatch():
            return asyncio.run(_dispatch(method, params))
        result = await asyncio.get_running_loop().run_in_executor(_EXECUTOR, _run_dispatch)
        _write({"jsonrpc": "2.0", "id": mid, "result": result})
    except _InvalidParams as e:
        _write({"jsonrpc": "2.0", "id": mid,
                "error": {"code": -32602, "message": str(e)}})
    except _MethodNotFound:
        if mid is not None:
            _write({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}})
    except Exception as e:  # noqa: BLE001
        if mid is not None:
            _write({"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": f"internal error: {e!r}"}})


def _stdin_reader(loop: asyncio.AbstractEventLoop) -> None:
    """Background thread: reads stdin and schedules work on the main loop."""
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                _write({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
                continue
            loop.call_soon_threadsafe(_schedule, loop, msg)
    finally:
        loop.call_soon_threadsafe(loop.create_task, _drain(loop))


def _schedule(loop: asyncio.AbstractEventLoop, msg) -> None:
    task = loop.create_task(_handle(msg))
    _PENDING.add(task)
    task.add_done_callback(_PENDING.discard)


async def _drain(loop: asyncio.AbstractEventLoop) -> None:
    if _PENDING:
        await asyncio.gather(*list(_PENDING), return_exceptions=True)
    loop.stop()


def _serve() -> None:
    """Main thread owns the event loop. Stdin is read by a daemon thread."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    reader = threading.Thread(target=_stdin_reader, args=(loop,), daemon=True)
    reader.start()
    try:
        loop.run_forever()
    finally:
        loop.close()
        _EXECUTOR.shutdown(wait=False)


if __name__ == "__main__":
    _serve()
