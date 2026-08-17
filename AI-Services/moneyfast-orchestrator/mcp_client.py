"""MCP client over SSE for container-to-container calls.

The orchestrator and the MCP server are separate containers on one Docker
network, so the host is the SERVICE NAME (mcp-market-data), never localhost.
localhost inside a container is that container.

A fresh session is opened per tool call. That costs one round trip but
removes the failure mode that matters in production: a long-lived SSE stream
that silently dies and returns stale or hung reads. Swap to a pooled session
only after you have reconnect logic you trust.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp import ClientSession
from mcp.client.sse import sse_client

log = logging.getLogger("moneyfast.mcp")


class MCPUnavailable(RuntimeError):
    """The tool server could not be reached or returned a transport error."""


class MCPToolError(RuntimeError):
    """The tool ran and reported an error."""


class MCPToolClient:
    def __init__(
        self,
        url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.url = url or os.getenv("MCP_SERVER_URL", "http://mcp-market-data:8000/sse")
        self.timeout = timeout if timeout is not None else float(
            os.getenv("MCP_TIMEOUT_SECONDS", "30")
        )
        self.max_retries = (
            max_retries if max_retries is not None else int(os.getenv("MCP_MAX_RETRIES", "1"))
        )

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[ClientSession]:
        async with sse_client(self.url, timeout=self.timeout) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    async def list_tools(self) -> list[str]:
        async with self._session() as session:
            result = await session.list_tools()
            return [t.name for t in result.tools]

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool and return its payload as a dict.

        Raises MCPUnavailable on transport failure after retries, MCPToolError
        when the tool itself reports an error. Never returns a fabricated
        payload: an unreachable tool must surface as an error so the graph can
        tell the user the data could not be retrieved.
        """
        attempt = 0
        last: Exception | None = None
        while attempt <= self.max_retries:
            try:
                async with self._session() as session:
                    result = await session.call_tool(name, arguments=arguments)
                if getattr(result, "isError", False):
                    raise MCPToolError(f"{name} reported an error: {_as_text(result)}")
                return _payload(result)
            except MCPToolError:
                raise
            except Exception as exc:  # transport, timeout, protocol
                last = exc
                attempt += 1
                if attempt > self.max_retries:
                    break
                backoff = 0.5 * (2 ** (attempt - 1))
                log.warning(
                    "mcp call %s failed (%s), retry %d/%d in %.1fs",
                    name, exc.__class__.__name__, attempt, self.max_retries, backoff,
                )
                await asyncio.sleep(backoff)
        raise MCPUnavailable(f"{name} unreachable at {self.url}: {last}") from last


def _as_text(result: Any) -> str:
    parts = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


def _payload(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        # FastMCP wraps non-model returns under "result".
        if set(structured.keys()) == {"result"} and isinstance(structured["result"], dict):
            return structured["result"]
        return structured
    text = _as_text(result)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}
    return parsed if isinstance(parsed, dict) else {"result": parsed}


_client: MCPToolClient | None = None


def get_mcp_client() -> MCPToolClient:
    global _client
    if _client is None:
        _client = MCPToolClient()
        log.info("mcp client bound to %s", _client.url)
    return _client
