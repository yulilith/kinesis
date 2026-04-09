"""Multi-server MCP client helper.

Manages connections to multiple MCP servers simultaneously and routes tool
calls to the correct server based on which server registered the tool.

Usage:
    async with multi_mcp_session({
        "state":      "http://localhost:8080/mcp",
        "kinesess_hw": "http://localhost:8081/mcp",
        "glasses_hw":  "http://localhost:8082/mcp",
        "whoop":       "http://localhost:8084/mcp",
    }) as mcp:
        tools = await mcp.claude_tools()
        result = await mcp.call_tool("fire_haptic", {...})
        biometrics = await mcp.call_tool("get_biometric_summary", {})
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager, AsyncExitStack
from typing import Any

from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import ClientSession

logger = logging.getLogger(__name__)


class MultiMCPSession:
    """Routes tool calls and resource reads across multiple MCP server sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, ClientSession] = {}
        self._tool_server: dict[str, str] = {}  # tool_name → server_key

    def add_session(self, key: str, session: ClientSession) -> None:
        self._sessions[key] = session

    async def build_tool_index(self) -> None:
        """Build the tool → server routing table from all connected servers."""
        for key, session in self._sessions.items():
            try:
                result = await session.list_tools()
                for tool in result.tools:
                    if tool.name in self._tool_server:
                        logger.warning(
                            "Tool %r registered on both %r and %r — %r wins",
                            tool.name, self._tool_server[tool.name], key, key,
                        )
                    self._tool_server[tool.name] = key
            except Exception as e:
                logger.warning("Could not list tools from server %r: %s", key, e)

    async def claude_tools(self) -> list[dict]:
        """Return merged tool list in the format expected by the Claude API."""
        all_tools: list[dict] = []
        for session in self._sessions.values():
            try:
                result = await session.list_tools()
                for tool in result.tools:
                    all_tools.append({
                        "name": tool.name,
                        "description": tool.description or "",
                        "input_schema": tool.inputSchema,
                    })
            except Exception as e:
                logger.warning("Could not list tools: %s", e)
        return all_tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call a tool on whichever server registered it. Returns raw text."""
        server_key = self._tool_server.get(name)
        if server_key is None:
            return json.dumps({"error": f"unknown tool: {name}"})
        session = self._sessions[server_key]
        try:
            result = await session.call_tool(name, arguments)
            texts = [c.text for c in result.content if hasattr(c, "text")]
            return "\n".join(texts) if texts else "{}"
        except Exception as e:
            logger.error("Tool %r on %r failed: %s", name, server_key, e)
            return json.dumps({"error": str(e)})

    async def read_resource(self, uri: str, server_key: str = "state") -> dict:
        """Read a resource from the specified server. Returns parsed JSON dict."""
        session = self._sessions.get(server_key)
        if session is None:
            return {}
        try:
            result = await session.read_resource(uri)
            content = result.contents[0]
            text = content.text if hasattr(content, "text") else str(content)
            return json.loads(text)
        except Exception as e:
            logger.debug("read_resource %r from %r failed: %s", uri, server_key, e)
            return {}

    def session(self, key: str) -> ClientSession | None:
        return self._sessions.get(key)


@asynccontextmanager
async def multi_mcp_session(server_urls: dict[str, str]):
    """Connect to multiple MCP servers and yield a MultiMCPSession.

    Servers that fail to connect are skipped with a warning (graceful degradation).

    Args:
        server_urls: Mapping of server key → MCP URL.
                     Key "state" is the primary blackboard.
    """
    client = MultiMCPSession()

    async with AsyncExitStack() as stack:
        for key, url in server_urls.items():
            try:
                r, w, _ = await stack.enter_async_context(streamable_http_client(url))
                session = await stack.enter_async_context(ClientSession(r, w))
                await session.initialize()
                client.add_session(key, session)
                logger.info("Connected to MCP server %r at %s", key, url)
            except Exception as e:
                logger.warning("Could not connect to MCP server %r at %s: %s", key, url, e)

        await client.build_tool_index()
        yield client
