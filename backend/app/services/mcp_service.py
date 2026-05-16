"""
MCP (Model Context Protocol) service.

Handles connecting to MCP servers, discovering tools, and invoking them.
Supports two transports:
  - stdio : spawn a local subprocess (e.g. `npx @modelcontextprotocol/server-filesystem`)
  - sse   : connect to an already-running HTTP/SSE MCP server by URL
"""

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _tool_to_litellm(tool) -> Dict:
    """Convert an MCP tool object to a litellm-compatible function definition."""
    schema: Dict = {}
    if hasattr(tool, "inputSchema") and tool.inputSchema is not None:
        raw = tool.inputSchema
        schema = raw if isinstance(raw, dict) else raw.model_dump()
    # Ensure the schema has at minimum an object type
    if not schema:
        schema = {"type": "object", "properties": {}}

    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": schema,
        },
    }


def _content_to_text(result) -> str:
    """Flatten MCP tool call result content into a plain string."""
    parts: List[str] = []
    for item in result.content:
        if hasattr(item, "text"):
            parts.append(item.text)
        elif hasattr(item, "data"):
            parts.append(f"[Binary data: {len(item.data)} bytes]")
        else:
            parts.append(str(item))
    return "\n".join(parts) if parts else "(empty result)"


# ── stdio transport ───────────────────────────────────────────────────────────

async def _list_tools_stdio(command: str, args: List[str], env: Dict[str, str]) -> List[Dict]:
    merged_env = {**os.environ, **env}
    params = StdioServerParameters(command=command, args=args, env=merged_env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [_tool_to_litellm(t) for t in result.tools]


async def _call_tool_stdio(
    command: str,
    args: List[str],
    env: Dict[str, str],
    tool_name: str,
    tool_args: Dict,
) -> str:
    merged_env = {**os.environ, **env}
    params = StdioServerParameters(command=command, args=args, env=merged_env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, tool_args)
            return _content_to_text(result)


# ── SSE transport ─────────────────────────────────────────────────────────────

async def _list_tools_sse(url: str, headers: Dict[str, str]) -> List[Dict]:
    async with sse_client(url, headers=headers or {}) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [_tool_to_litellm(t) for t in result.tools]


async def _call_tool_sse(
    url: str,
    headers: Dict[str, str],
    tool_name: str,
    tool_args: Dict,
) -> str:
    async with sse_client(url, headers=headers or {}) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, tool_args)
            return _content_to_text(result)


# ── Public API ────────────────────────────────────────────────────────────────

async def get_tools_for_servers(
    servers: List[Any],
) -> Tuple[List[Dict], Dict[str, Any]]:
    """
    Given a list of MCPServer ORM objects, return:
      - litellm_tools : list of tool defs ready to pass to litellm as `tools=`
      - registry      : {tool_name: server_orm} so we know which server to call

    Errors from individual servers are logged but do not abort the whole call.
    """
    litellm_tools: List[Dict] = []
    registry: Dict[str, Any] = {}

    for server in servers:
        if not server.is_active:
            continue
        try:
            if server.transport == "stdio":
                tools = await _list_tools_stdio(
                    server.command or "",
                    server.args or [],
                    server.env or {},
                )
            else:
                tools = await _list_tools_sse(server.url or "", server.headers or {})

            for tool_def in tools:
                name = tool_def["function"]["name"]
                if name not in registry:          # first server wins on collision
                    litellm_tools.append(tool_def)
                    registry[name] = server
        except Exception as exc:
            print(f"[MCP] Cannot load tools from '{server.name}': {exc}")

    return litellm_tools, registry


async def invoke_tool(server: Any, tool_name: str, tool_args: Dict) -> str:
    """Call a single tool on the appropriate MCP server and return the text result."""
    try:
        if server.transport == "stdio":
            return await _call_tool_stdio(
                server.command or "",
                server.args or [],
                server.env or {},
                tool_name,
                tool_args,
            )
        else:
            return await _call_tool_sse(
                server.url or "",
                server.headers or {},
                tool_name,
                tool_args,
            )
    except Exception as exc:
        return f"[MCP error calling '{tool_name}': {exc}]"


async def test_server(server: Any) -> Dict:
    """
    Attempt to connect and list tools; returns a summary dict.
    Raises on connection failure so the router can return a 4xx/5xx.
    """
    if server.transport == "stdio":
        tools = await _list_tools_stdio(
            server.command or "",
            server.args or [],
            server.env or {},
        )
    else:
        tools = await _list_tools_sse(server.url or "", server.headers or {})

    return {
        "ok": True,
        "tool_count": len(tools),
        "tools": [t["function"]["name"] for t in tools],
    }
