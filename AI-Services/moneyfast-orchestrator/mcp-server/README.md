# mcp-server

Build context for the `mcp` container. Copy the six tool modules
and `server.py` from the MoneyFast MCP skeleton into this directory.

`server.py` must serve SSE rather than stdio. With FastMCP that means:

```python
mcp = FastMCP(
    "moneyfast",
    instructions=SERVER_INSTRUCTIONS,
    host="0.0.0.0",   # not 127.0.0.1, or the orchestrator container cannot reach it
    port=8000,
)

if __name__ == "__main__":
    mcp.run(transport="sse")
```

Two things bite here:

- Binding to `127.0.0.1` inside the container makes the port unreachable from
  the other container even on the same network. Bind `0.0.0.0`.
- Pin `mcp<2`. In 2.0 `mcp.server.fastmcp` moved to `mcp.server.mcpserver`.

If you already publish an image for this service, delete this directory and
switch `docker-compose.yml` to the commented `image:` line.
