# MCP tool server, SSE transport on 8000.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN pip install "mcp>=1.9,<2" "uvicorn[standard]>=0.32,<0.40"

# Drop the six tool modules and server.py from the MCP skeleton here.
COPY . /app

RUN useradd --create-home --uid 10002 mcpuser && chown -R mcpuser:mcpuser /app
USER mcpuser

EXPOSE 8000
CMD ["python", "server.py"]
